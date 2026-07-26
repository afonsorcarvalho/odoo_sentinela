# Portal público de verificação de autenticidade — design

**Data:** 2026-07-25
**Branch:** `worktree-portal-autenticidade`

## Contexto e propósito

O núcleo de verificação (`ingestao/verificador.py::verificar_itens`) já existe e roda
no serviço **api** (FastAPI), que monta `./ingestao` e `./contrato` e tem a lib
`cryptography`. Falta a interface pública: um **portal web** onde qualquer pessoa
sobe um arquivo de leitura assinado — ou um **zip com vários** — e recebe um
**relatório de autenticidade de todos os arquivos**.

Produto comercial: o portal é a face pública do "prove você mesmo". Como é anônimo e
a verificação é CPU-bound (ECDSA por linha; um arquivo diário tem ~2880 linhas), o
portal precisa se proteger de sobrecarga: **rate-limit por-IP + limite global + fila
com backpressure** ("aguarde") em vez de estourar o servidor.

## Decisões (brainstorm)

- **Acesso:** website público (dep. Odoo `website`), sem login.
- **Arquitetura:** split. **Odoo** = página pública + upload + throttle de borda +
  proxy; **api** = descompacta zip + verifica (crypto) + fila + limite global. Odoo
  renderiza o relatório e gera o laudo.
- **Backpressure:** assíncrono com fila/ticket. Sobe → recebe `job_id` → página faz
  polling → quando pronto, mostra relatório.
- **Jobs:** em memória no api (pool com concorrência N + fila limitada). Efêmeros.
- **Sinalização de término:** polling via proxy Odoo (browser → Odoo → `GET` no api).
  Sem webhook, sem SSE público.
- **Chave (trust):** só modo A (registro do servidor `coletores_conhecidos.json`).
  Coletor desconhecido → `indeterminado`.
- **Zip:** o api descompacta (não o Odoo). Guards: upload ≤ 25 MB, total
  descomprimido ≤ 200 MB, ≤ 500 arquivos, zip aninhado ignorado, todo arquivo regular
  é verificado e entra no relatório.
- **Saída:** tela (relatório por arquivo + resumo) + download **PDF** (laudo QWeb com
  timestamp) + download **JSON** (`VerificacaoLote`).

## Riscos e constraints (verificados)

### RISCO #1 — completude do registro (bloqueia utilidade)

`coletores_conhecidos.json` hoje tem **1 coletor** (`COL-RS485-BUS0`). O modelo Odoo
`sensor_monitor.coletor` guarda só `pubkey_fingerprint`, **não o PEM**. Sem popular o
registro com as chaves públicas dos coletores de produção, todo upload real vira
`indeterminado` e o portal parece quebrado.

**Pré-requisito operacional (MVP):** o registro que o api usa
(`SENTINELA_REGISTRO`, default `ingestao/coletores_conhecidos.json`) deve conter o PEM
de cada coletor de produção (via `ingestao/registro_coletores.py`).

**Fix durável (stage posterior, recomendado, fora do MVP):** adicionar campo
`pubkey_pem` a `sensor_monitor.coletor` e fazer o api resolver a chave a partir do
Odoo (o api já fala com o Odoo via `api/odoo.py`), tornando o Odoo a fonte única e
eliminando o JSON manual. Este design **não** implementa o fix durável; apenas o
registra e mantém o portal usando o registro atual.

### CONSTRAINT — api single-worker

Dockerfile roda `uvicorn api.main:app` **sem `--workers`** (1 processo), sem replicas
no compose. Jobs em memória, estado de rate-limit e polling **dependem disso**.
O spec fixa: **api deve permanecer single-worker**; escalar exige store compartilhado
(Redis/DB) — fora de escopo.

## Arquitetura

```
Browser (público)
  │  1. POST /verificar-autenticidade  (multipart: arquivo|zip)
  ▼
Odoo website controller  ── throttle por-IP de borda (rejeita cedo) ──┐
  │  2. repassa bytes crus + IP real (X-Forwarded-For) ──► api        │
  ▼                                                                    │
api  POST /verificar  →  cria job, enfileira, retorna {job_id, posicao}│
  │      (limite global de concorrência + fila + rate-limit por-IP)    │
  │  worker pool (N) consome fila: descompacta zip + verificar_itens   │
  ▼                                                                    │
Browser  ── polling ──►  Odoo GET /verificar-autenticidade/<job_id>    │
                              └─ proxy ─► api GET /verificar/<job_id>   │
                                   {estado: fila|processando|pronto,    │
                                    posicao, VerificacaoLote}           │
Pronto → Odoo renderiza relatório (QWeb website) + botões PDF/JSON ◄────┘
```

### 1. api — endpoint de verificação + fila (novo módulo `api/verificacao.py` + router)

- `POST /verificar` — recebe o upload cru (arquivo ou zip). Aplica **rate-limit
  por-IP** (do `X-Forwarded-For`, confiável só vindo do Odoo interno) e **limite de
  fila global**. Se IP estourou a cota **ou** a fila está cheia → `429` +
  `Retry-After`. Senão cria `job_id`, enfileira, responde `{job_id, posicao}`.
- **Worker pool** (asyncio, concorrência N via `asyncio.Semaphore`): consome a fila.
  Para cada job: se zip → descompacta em memória com guards (tamanho total, contagem,
  sem aninhado) → coleção `(nome, bytes)`; senão item único. Chama
  `verificador.verificar_itens(itens, registro_path=SENTINELA_REGISTRO)`.
- **Store de jobs em memória:** `dict[job_id] -> Job(estado, posicao, criado_em,
  lote|erro, expira_em)`. Estados: `fila` → `processando` → `pronto` | `erro`.
- **TTL / lifecycle (RISCO #4 do review):** job concluído fica disponível por
  `TTL_RESULTADO` (ex. 10 min) para os downloads (PDF/JSON são requests posteriores);
  um sweep remove expirados. Display, PDF e JSON leem o **mesmo** resultado dentro da
  janela. Após o TTL → `404` (Odoo mostra "resultado expirou, reenvie").
- `GET /verificar/{job_id}` — status: `{estado, posicao, lote?}`. `lote` (o
  `VerificacaoLote` como dict) só quando `pronto`.
- **Rate-limit por-IP e fila são só do api** (single-worker, estado em memória
  compartilhado). O Odoo faz um throttle de borda barato (defesa em profundidade) mas
  a cota autoritativa é do api. `X-Forwarded-For` é confiado **apenas** quando a
  conexão vem do Odoo interno; o Odoo grava o IP real do cliente nesse header.

Defaults (ir/config-like, ajustáveis por env):
`FILA_MAX` (profundidade), `CONCORRENCIA_N` (workers), `IP_COTA` (req/janela),
`IP_JANELA_S`, `UPLOAD_MAX_MB=25`, `DESCOMPRIMIDO_MAX_MB=200`, `ARQUIVOS_MAX=500`,
`TTL_RESULTADO_S=600`.

### 2. Odoo — novo módulo `afr_sentinela_portal_autenticidade`

Novo addon (não altera `afr_sentinela_sensor_monitor`), depende de
`['website', 'afr_sentinela_sensor_monitor']`.

- **Controller** (`controllers/portal.py`, rotas `website`, `auth='public'`,
  `csrf` conforme upload):
  - `GET /verificar-autenticidade` — página com o formulário de upload (arquivo ou
    zip) + explicação.
  - `POST /verificar-autenticidade` — throttle por-IP de borda; repassa bytes +
    `X-Forwarded-For` (IP real do cliente) ao api `POST /verificar`; devolve página
    de "processando" com `job_id` (ou "aguarde N s" em `429`).
  - `GET /verificar-autenticidade/<job_id>` — proxy pro api `GET /verificar/{id}`;
    devolve JSON de status pro polling do front (ou renderiza a página de relatório
    quando `pronto`).
  - `GET /verificar-autenticidade/<job_id>/laudo.pdf` — renderiza o QWeb report.
  - `GET /verificar-autenticidade/<job_id>/relatorio.json` — repassa o `VerificacaoLote`.
- **Cliente ao api:** `models/verificacao_client.py` (helper que chama o api via
  `requests`, base URL de `ir.config_parameter` `sentinela.api_base_url`, com o
  segredo/rede interna). Reusa o padrão de `api/odoo.py`/config-publish já existente.
- **Templates** (`views/portal_templates.xml`, QWeb website):
  - form de upload; página "processando" (JS de polling); página de relatório.
- **Laudo PDF** (`report/laudo_report.xml` + `report/laudo_templates.xml`): QWeb
  report renderizado a partir do `VerificacaoLote` — **sem persistir**. Usa um
  `models.TransientModel` (`sensor_monitor.verificacao.laudo`) preenchido on-the-fly
  a partir do JSON que o Odoo obteve no polling, OU `render_qweb_pdf` com `data`.
  (Detalhe de implementação decidido no plano; transient é auto-vacuumado = efêmero.)
- **Front JS** (`static/src/js/portal_polling.js`): faz o polling do status a cada
  ~2 s, mostra posição na fila, e troca pra página de relatório quando `pronto`.

### 3. Fluxo de erro / estados na UI

- Upload > limite / zip inválido → mensagem clara na página (não 500).
- `429` (IP ou fila) → página "servidor ocupado, aguarde N s" com auto-retry.
- Job `erro` (zip-bomb, corrompido) → relatório marca o motivo.
- Resultado expirado (TTL) → "reenvie o arquivo".
- Coletor não registrado → item `indeterminado` (não é adulteração; a página explica
  a diferença).

## Componentes e responsabilidades (isolamento)

| Unidade | Faz | Depende de |
|---|---|---|
| `api/verificacao.py` (core fila) | job store, pool, TTL, descompactar zip, chamar `verificar_itens` | `ingestao.verificador`, stdlib `zipfile`/`asyncio` |
| `api/verificacao_router.py` | rotas HTTP, rate-limit por-IP, 429 | `verificacao.py` |
| Odoo controller | página pública, throttle borda, proxy, polling, downloads | website, `verificacao_client` |
| `verificacao_client` | fala com api | `requests`, ir.config |
| QWeb templates + report | relatório na tela + laudo PDF | website, report |

## Testes

- **api core (pytest, puro):** fila enfileira/ordena; concorrência respeita N; 429
  quando fila cheia e quando IP estoura; zip válido → N itens; zip-bomb (total >
  limite) → erro; contagem > limite → erro; job TTL expira → 404; `verificar_itens`
  chamado com o registro certo. Reusa fixtures de arquivo assinado do verificador.
- **api router (FastAPI TestClient):** POST retorna job_id; GET status transita
  fila→processando→pronto; 429 + Retry-After; XFF confiável só do hop interno.
- **Odoo (`HttpCase`):** GET da página pública 200; POST repassa e retorna job_id
  (api mockado); polling proxy; laudo.pdf gera PDF não-vazio; relatorio.json bate.
  *(Superfície de teste mais difícil que a do verificador — controller público +
  QWeb PDF a partir de dados transientes; o plano trata explicitamente, sem
  hand-wave.)*

## Staging (subsistemas independentes)

1. **api verify+zip** — endpoint síncrono `verificar_itens` + descompactação com
   guards (sem fila ainda). Shippable/testável sozinho.
2. **api fila + rate-limit + backpressure** — job store, pool, 429, TTL, status.
3. **Odoo página pública + upload + proxy/polling** — controller + templates + JS.
4. **Relatório na tela + laudo PDF (QWeb) + JSON.**

Cada stage tem entregável testável. Um spec, plano em 4 estágios.

## Não-escopo

- Modo B (PEM do usuário), histórico/auditoria persistente de verificações, login/
  portal autenticado, Redis/multi-worker, o fix durável de `pubkey_pem` no Odoo.
