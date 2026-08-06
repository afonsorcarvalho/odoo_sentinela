# Download dos arquivos do dia pelo Odoo

Data: 2026-08-05
Status: aprovado (design)

## Problema

O acervo de arquivos diários assinados — a prova de lastro do produto — vive
apenas no volume `sftpgo-data`. Quem opera o sistema pelo Odoo vê o
`sensor_monitor.file.ledger` com hash, assinatura e status de validação, mas não
tem como obter o arquivo em si. Para auditoria, para reenviar ao portal de
autenticidade, ou simplesmente para arquivar fora do servidor, hoje é preciso
acesso SFTP direto.

## Escopo

Um wizard no Odoo que recebe **data + site** e devolve um **ZIP com todos os
arquivos daquele dia naquele site** — leituras e alarmes, de todos os hubs e
coletores — com os bytes originais intactos.

Fora de escopo (decidido, não esquecido):

- Download de arquivo individual por linha do ledger.
- Manifesto de integridade dentro do ZIP. O rodapé assinado já vai dentro de
  cada `.txt`; o ledger continua sendo a visão de metadados no Odoo.
- Relatório PDF de auditoria.
- Intervalo de datas. Um dia por vez.
- Qualquer mudança em `docker-compose.yml`.

## Arquitetura

O container `odoo` não tem o volume do acervo nem chave SFTP. O container `api`
tem os dois, mais `paramiko`, e já expõe rotas `/internal/` autenticadas pelo
segredo compartilhado `sentinela.config_publish_secret` (usado hoje por
`hub.action_publicar_config`). O download reusa exatamente esse canal.

```
Wizard (data + site)
  └─ act_url → /sentinela/arquivos/zip?site_id=7&data=2026-07-29
       └─ controller: site = env['sensor_monitor.site'].browse(7)   ← ir.rule isola por partner
            cliente_id = site.partner_id.ref or f'CLI-{partner_id}'
            └─ client.baixar_zip(cliente_id, site.site_code, data)
                 └─ GET http://api:8000/internal/arquivos/zip?cliente=..&site=..&data=..
                      X-Config-Secret: <segredo>
                      └─ api: SFTP listdir /uploads/{cliente}/{AAAA}/{MM}/{DD}/{site}/**
                              zip em tempfile → FileResponse
            └─ Response(resp.iter_content(64 KB), Content-Disposition: attachment)
```

### Alternativas descartadas

- **`ir.attachment` no ledger.** 8–16 MB/dia/coletor trafegando por XML-RPC em
  base64 e duplicados no `odoo-filestore`. Custo alto para nenhum ganho: o
  acervo já é persistente e não tem política de expurgo.
- **Montar `sftpgo-data` read-only no container `odoo`.** Exige mexer no
  `docker-compose.yml` de uma stack que é produção de-facto, e acopla o Odoo ao
  layout de armazenamento que hoje só a api conhece.
- **Campo `caminho_arquivo` no ledger + backfill.** Desnecessário: a consulta é
  por data+site, que é exatamente o recorte de uma pasta da árvore. A árvore é o
  índice. De quebra, arquivos anteriores à convenção de nome atual entram sem
  tratamento especial.

## Componentes

### 1. `sensor_monitor.arquivo.download.wizard` (TransientModel)

Campos:

- `data` — `Date`, obrigatório, default hoje.
- `site_id` — `Many2one('sensor_monitor.site')`, obrigatório. O `ir.rule`
  `rule_site_tenant` limita a seleção aos sites do partner do usuário.

Método `action_baixar()`: `ensure_one()`, retorna
`{'type': 'ir.actions.act_url', 'url': f'/sentinela/arquivos/zip?site_id={id}&data={iso}', 'target': 'self'}`.

Menu **Sentinela → Arquivos do Dia**, ao lado de *Ledger de Arquivos*.

### 2. Controller `/sentinela/arquivos/zip`

Novo arquivo `addons/afr_sentinela_sensor_monitor/controllers/arquivos.py`
(diretório `controllers/` ainda não existe neste addon; criar com `__init__.py`).

`@http.route('/sentinela/arquivos/zip', type='http', auth='user', methods=['GET'])`

1. Faz parse de `site_id` (int) e `data` (`date.fromisoformat`). Malformado →
   `UserError`.
2. `site = request.env['sensor_monitor.site'].browse(site_id).exists()`
   **sem `sudo`**. Recordset vazio (site inexistente ou de outro partner) →
   resposta 403. Não diferenciar as duas causas: não vazar existência.
3. `cliente_id = site.partner_id.ref or f'CLI-{site.partner_id.id}'` — mesma
   regra de `ingestao/odoo_cliente.py::_info_coletor`, que é quem escreve a
   árvore.
4. Chama o client; repassa `resp.iter_content(64 * 1024)` num
   `werkzeug` `Response` com
   `Content-Disposition: attachment; filename=sentinela_{site_code}_{data}.zip`
   e `Content-Type: application/zip`.

### 3. `sensor_monitor.arquivo.client` (AbstractModel)

Envelope HTTP, espelhando `sensor_monitor.verificacao.client` do addon do
portal. Lê `sentinela.api_url` e `sentinela.config_publish_secret` de
`ir.config_parameter`. Método `baixar_zip(cliente_id, site_code, data)` faz
`requests.get(..., stream=True, timeout=300)` e devolve a resposta.

Existir como model separado é o que torna o controller testável sem api de pé.

Tradução de erro para o usuário:

| HTTP da api | Mensagem |
|---|---|
| 404 | `Nenhum arquivo encontrado para {site_code} em {dd/mm/aaaa}.` |
| 413 | `Volume acima do limite; escolha um dia com menos coletores.` |
| 401 / 5xx / timeout / conexão | `Serviço de arquivos indisponível. Tente novamente.` |

### 4. `GET /internal/arquivos/zip` (api)

Novo `api/arquivos_router.py`, registrado em `api/main.py`.

```
GET /internal/arquivos/zip?cliente=CLI-43&site=SITE-DEMO-01&data=2026-07-29
Header: X-Config-Secret: <CONFIG_PUBLISH_SECRET>
→ 200 application/zip
→ 401 secret inválido | 400 parâmetro malformado | 404 nada naquele dia | 413 acima do teto
```

Passos:

1. Compara `X-Config-Secret` com `CONFIG_PUBLISH_SECRET`; vazio ou diferente →
   401. Mesma checagem de `config_publish_router`.
2. Valida `cliente` e `site` contra `^[A-Za-z0-9_-]{1,64}$` → 400. Isso é o que
   mata path traversal: `..`, `/` e `%2e%2e` não passam.
3. `date.fromisoformat(data)` → 400 se inválida.
4. Monta o caminho remoto ele mesmo:
   `f'{SFTP_UPLOADS}/{cliente}/{d.year:04d}/{d.month:02d}/{d.day:02d}/{site}'`,
   com `SFTP_UPLOADS = os.environ.get('SFTP_UPLOADS', '/uploads')`. Nenhum
   fragmento de caminho vem do chamador.
5. Varre recursivamente com `listdir_attr`, **profundidade máxima 3**
   (HUB/COLETOR/arquivo), incluindo só o que `stat.S_ISREG` aprova — symlink e
   diretório fundo ficam de fora.
6. Pasta inexistente ou sem nenhum arquivo → 404.
7. Soma `st_size`; acima de `ARQUIVOS_ZIP_MAX_BYTES`
   (`os.environ`, default 500 MB) → 413, antes de baixar qualquer byte.
8. Monta o ZIP em `tempfile.NamedTemporaryFile` com `ZIP_DEFLATED`
   (arquivo de leitura é texto, comprime ~10×), `arcname` = caminho relativo à
   pasta do dia, isto é `HUB-xxxx/COL-yyyy/nome.txt`.
9. Devolve `FileResponse` com `BackgroundTask` que apaga o temporário.

Nem a api nem o Odoo seguram o ZIP inteiro em memória: a api escreve em disco e
serve por `FileResponse`; o Odoo repassa em blocos de 64 KB.

## Segurança

- **Multi-tenant sem código novo.** `rule_site_tenant` em
  `security/security_rules.xml` já filtra `sensor_monitor.site` por
  `partner_id = user.partner_id.commercial_partner_id`. Forjar `site_id` na URL
  devolve recordset vazio. O controller nunca usa `sudo` para resolver o site.
- **O endpoint da api não aceita caminho.** Recebe três tokens validados e
  compõe o caminho internamente.
- Rota sob `/internal/`, o mesmo prefixo de `publicar-config`, protegida
  SÓ pelo segredo compartilhado (`X-Config-Secret`). Isso não é um filtro de
  rede: `docker-compose.yml` publica `"8000:8000"` em todas as interfaces do
  host, e nada neste repositório — nenhum reverse proxy, nenhuma regra de
  firewall — restringe `/internal/` por origem. Quem alcançar a porta 8000 do
  host com o segredo em mãos enumera `cliente` × `site` × data à vontade; o
  nome "interno" descreve a intenção de uso, não uma barreira técnica.
  Antes de expor esta stack a uma rede não confiável, ligar o publish a
  `127.0.0.1:8000:8000` e usar um segredo que não esteja versionado.

## Casos de borda

| Situação | Comportamento |
|---|---|
| Dia sem arquivo, ou site recém-criado | 404 da api → `UserError` legível |
| Site de outro cliente | 403 do controller, sem diferenciar de site inexistente |
| api fora do ar ou lenta | `UserError`; timeout de 300 s (SFTP lento não pode estourar em 15 s) |
| Dia corrente, arquivo ainda parcial | Entra no ZIP como está. O ZIP reflete o disco, não o ledger |
| Linha `faltante`/`pendente` no ledger | Irrelevante: o ZIP não consulta o ledger |
| Dois coletores com o mesmo nome de arquivo | Impossível colidir: o `arcname` carrega `HUB/COLETOR/` |

## Testes

`api/tests/test_arquivos_zip.py`, com um duplo de SFTP injetado (o
`test_config_sftp.py` existente é integração contra o SFTP real; este é de
unidade):

- secret ausente e secret errado → 401
- `cliente=../..`, `site=a/b`, data não-ISO → 400
- pasta do dia inexistente → 404
- pasta com arquivos somando acima do teto → 413, sem ler conteúdo
- **byte-identidade**: extrai cada membro do ZIP e compara o SHA-256 com o do
  arquivo de origem; confere `arcname == 'HUB-x/COL-y/nome.txt'`
- profundidade: arquivo a 4 níveis e symlink não entram no ZIP

`addons/afr_sentinela_sensor_monitor/tests/test_arquivo_download.py`:

- wizard devolve `act_url` com `site_id` e `data` corretos
- controller com site de outro partner → 403 (estende o cenário de
  `test_security_rules.py`)
- api respondendo 404 → `UserError` com a mensagem legível
- client monta a URL e o header `X-Config-Secret` a partir de
  `ir.config_parameter`

A byte-identidade é o teste que sustenta a feature: o valor do acervo é o rodapé
assinado. Um download que re-encode, normalize newline ou insira BOM produz um
arquivo que não passa mais no portal de autenticidade — e aí o ZIP vira lixo com
aparência de prova.

## Sequenciamento sugerido

1. Endpoint da api (`arquivos_router.py`) com os testes de unidade — é a peça que
   carrega a lógica e a superfície de risco.
2. `sensor_monitor.arquivo.client` + testes.
3. Controller + regra de ACL + testes.
4. Wizard, view e menu.
5. Verificação ponta-a-ponta contra a stack real: baixar o ZIP de um dia que
   existe no acervo, extrair e submeter um `.txt` ao portal de autenticidade
   (`/verificar-autenticidade`) — veredito válido.
