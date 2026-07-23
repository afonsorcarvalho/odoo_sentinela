# Spec técnica — Malha de calibração + lastro por-linha (delta)

> Documento de especificação **incremental**. Não substitui os specs canônicos — **estende** e, em pontos marcados, **revisa** [`esp32_coletor_spec.md`](esp32_coletor_spec.md), [`odoo_modelo_dados_spec.md`](odoo_modelo_dados_spec.md) e `diretrizes_projeto.md`. Escrito para ser entregue a uma sessão de implementação.
>
> **Origem**: sessão de discussão de arquitetura (2026-07-22) sobre como modelar a cadeia sensor→hub com Hub/coletor fazendo papel de assinante, e como fechar o lastro criptográfico das leituras. Ver handoff em `.remember/remember.md`.

---

## 0. Escopo e relação com o canon

Cada decisão da discussão foi confrontada com o que já estava "resolvido" no canon. Resultado (decisão do usuário, ponto a ponto):

| # | Tema | Decisão | Efeito nesta spec |
|---|---|---|---|
| A | Granularidade do arquivo | **Mantém canon**: 1 arquivo por coletor/dia (multi-sensor) | — (sem mudança) |
| G | Rotação de arquivo | **Mantém canon**: rollover diário; sem "rotação por troca de cert" | — (mid-dia tratado por marcador, §4.4) |
| C | Compactação | **Mantém canon**: sem compactação na v1 (se precisar, servidor pós-validação) | — |
| D | Enrollment | **Mantém canon**: provisionamento manual na v1. Token automático = **v2/escala** (§6) | doc de evolução |
| **B** | Frequência da assinatura | **REVISA código em produção**: assinatura ECDSA **por linha** (Fase 5 assina 1×/dia) | §4 |
| **E** | Calibração | **ADICIONA**: malha + certificado de calibração first-class (ganho+offset+validade+histórico) | §2 |
| **F** | Tenant | **ADICIONA**: `cliente_id`/`site_id` dentro do header assinado | §3 |

O que **já batia** com a discussão e não muda: coletor = fonte de verdade; hub **não** re-assina (só transporta/verifica); hub assina direto no caso RS-485 embutido; formato linha-orientado pipe-delimited; cadeia de hash por dia (não atravessa dias); snapshot auto-contido por linha.

---

## 1. Modelo conceitual (para orientar o resto)

Pipeline de valor **no dispositivo assinante** (coletor ESP32, ou hub no papel RS-485 embutido):

```
sinal cru
   │  escala (transfer function nominal do canal — ex. 4-20mA→eng, ou scale/offset Modbus)
   ▼
valor eng nominal
   │  calibração (offset + ganho do certificado vigente da malha)
   ▼
valor eng corrigido  ──►  grava no arquivo (linha assinada)
```

Dois ajustes **distintos**, não confundir (nomes distintos obrigatórios no código e no arquivo):
- **Escala** = mapeamento nominal de fábrica do canal. Já existe para RS-485 (`modbus.profile.register.scale`/`.offset`, [odoo spec §4.13](odoo_modelo_dados_spec.md)). **Lacuna a preencher**: 4-20mA não tem escala hoje (§2.3).
- **Calibração** = correção certificada (offset + ganho), com validade e rastreabilidade, da **malha** (sensor + conversor). Novo (§2).

---

## 2. E — Malha de medição e certificado de calibração (novo, camada Odoo)

### 2.1 Conceito

**Malha** = unidade calibrada = **sensor + conversor (opcional)**. É o que a empresa de calibração certifica. Regras travadas na discussão:
- A malha **existe sempre** (1:1 com o sensor, no mínimo). Sensor sem conversor → malha = só o sensor.
- **Conversor = atributo, não entidade** (decisão: não rastrear conversor como peça física). Vira um campo no sensor.
- O **certificado de calibração pertence à malha** (ao par), nos dois casos.
- Calibração é **correção** (muda o valor): `valor = ganho × nominal + offset`.

### 2.2 Modelos

**Extensão em `sensor_monitor.sensor`** (novos campos):

| Campo | Tipo | Descrição |
|---|---|---|
| `conversor_tipo` | Selection (`nenhum`, `485_pt100`, `485_4_20ma`, `485_0_30v`, …) | Conversor da malha, como atributo. `nenhum` = sensor entrega direto. Extensível. |
| `calibracao_ids` | One2many → `sensor_monitor.calibracao` | Histórico de certificados desta malha |
| `calibracao_vigente_id` | Many2one (computed) | Certificado cuja janela de validade contém hoje |

> **Decisão travada (§7.1)**: **bundle, sem tabela `malha` dedicada.** Sensor↔malha é 1:1 sempre-presente, sem ciclo de vida próprio, sem referência externa por id (o arquivo referencia `sensor_id`), sem mudança de cardinalidade futura — uma tabela 1:1 só adicionaria join sem ganho. A calibração vira first-class via o model `calibracao` abaixo; "malha" fica como vocabulário de domínio (rótulos de UI/docs).

**Novo model `sensor_monitor.calibracao`** (o certificado):

| Campo | Tipo | Descrição |
|---|---|---|
| `sensor_id` | Many2one → `sensor_monitor.sensor` | A malha certificada (obrigatório) |
| `cert_numero` | Char | Número do certificado emitido pela empresa de calibração |
| `versao` | Integer | Incremental por malha (v1, v2, …) — entra no snapshot do arquivo |
| `cal_ganho` | Float | Ganho multiplicativo aplicado sobre o valor nominal |
| `cal_offset` | Float | Offset aditivo da calibração (distinto do `offset` da escala Modbus) |
| `validade_de` | Date | Início da validade |
| `validade_ate` | Date | Fim da validade |
| `conversor_tipo_snapshot` | Selection | Conversor da malha no momento da calibração (a calibração é do par) |
| `empresa_calibracao_id` | Many2one → `res.partner` | Quem calibrou |
| `documento` | Binary | PDF do certificado físico anexado |
| `estado` | Selection (`vigente`, `expirado`, `futuro`) | Computed pela janela vs hoje |

**Regras**:
- Trocar o conversor da malha (`sensor.conversor_tipo`) **invalida a calibração** → exige novo certificado (a calibração é do par).
- Histórico **append-only**: certificados antigos nunca são apagados (rastreabilidade — leituras passadas referenciam a versão vigente na época).
- **Confronto na recalibração** (objetivo central): quando a empresa recalibra, compara-se `cal_ganho`/`cal_offset` **em uso nos arquivos** (§4.3) vs os novos medidos → detecção de drift + prova de que o dispositivo honrou o certificado.

### 2.3 Map nominal no sensor + as três transformações (§7.2 travado)

Decisão: **shape único no sensor com flag explícita `usa_map`** (não ramificar implicitamente por protocolo). O pipeline tem **três** transformações que **nunca devem se misturar** — a fonte de confusão do operador, mitigada por help text obrigatório (§2.4):

| Camada | O que é | Onde vive | Exemplo |
|---|---|---|---|
| **Map** (nominal) | reta de range do sinal → engenharia | **no `sensor`** (esta seção) | 4-20mA → 0-150 °C |
| **Decode Modbus** | decodificação binária (tipo de dado, endianness, scale do registrador) | **`modbus.profile.register`** (perfil compartilhado — datasheet do transdutor, igual em todas as unidades) | int16×0.1 |
| **Calibração** | correção **certificada**, com validade + histórico | **`calibracao`** (cert, §2.2) | ×0.965 +0.33 |

**Novos campos em `sensor_monitor.sensor`** (map nominal, uniforme):

| Campo | Tipo | Descrição |
|---|---|---|
| `usa_map` | Boolean | Se aplica o map. `True` p/ analógico (4-20mA/0-30V); `False` p/ digital/RS-485 (valor já sai em engenharia após o decode do perfil) |
| `map_in_min` | Float | Ex. 4.0 (mA) — só relevante quando `usa_map` |
| `map_in_max` | Float | Ex. 20.0 (mA) |
| `map_out_min` | Float | Ex. 0.0 (eng) |
| `map_out_max` | Float | Ex. 150.0 (eng) |
| `map_versao` | Char | Versão do map (entra no snapshot do header do arquivo) |

`nominal = map_out_min + (raw − map_in_min)/(map_in_max − map_in_min) × (map_out_max − map_out_min)` quando `usa_map`; senão `nominal = raw` (já em engenharia).

Pipeline completo: `raw → [map se usa_map] → nominal → [calibração vigente: cal_ganho, cal_offset] → valor corrigido`.

### 2.4 Requisito de UX — help text obrigatório nos forms (anti-confusão)

Quem configura um sensor no Odoo vê map, decode Modbus e calibração perto uns dos outros e **pode confundir** (há dois pares "ganho/offset": o do map e o da calibração). **Obrigatório**: `help=` em cada campo + notas na view. Textos sugeridos:

- `usa_map` → *"Marque para sensores analógicos (4-20mA, 0-30V) que precisam converter o sinal físico em unidade de engenharia. Desmarque para sensores digitais/RS-485, que já entregam o valor pronto."*
- `map_in_min`/`map_in_max` → *"Faixa do sinal FÍSICO de entrada (ex. 4 e 20 mA). NÃO é calibração."*
- `map_out_min`/`map_out_max` → *"Faixa correspondente em unidade de ENGENHARIA (ex. 0 e 150 °C)."*
- Bloco de calibração (`calibracao`) → *"Correção CERTIFICADA da malha (ganho/offset do certificado de calibração), aplicada DEPOIS do map. Não confundir com a faixa do map acima — esta vem do laboratório de calibração e tem validade."*
- Campos do perfil Modbus (`scale`/`offset` do registrador) → *"Decodificação do registrador Modbus (datasheet do transdutor). Não é o map do sensor nem a calibração."*

---

## 3. F — Tenant dentro do header assinado (novo)

Motivação: o projeto já teve vulnerabilidade de isolamento multi-tenant (A↔B). Colocar o cliente **dentro da assinatura** impede que uma ingestão comprometida reatribua um arquivo a outro cliente — o vínculo passa a ser criptográfico, não só relacional.

- **Header do arquivo** (§4.2) ganha `cliente_id` e `site_id`, ambos **cobertos pela assinatura** (entram no seed da cadeia de hash).
- O dispositivo já sabe seu `site_id`/`cliente_id` por config (control plane; derivável de `coletor → hub → site → partner`). Custo: dois campos no header.
- **Ingestão** valida que `cliente_id`/`site_id` do header conferem com o cadastro do `coletor_id` no Odoo. Divergência = rejeição.

---

## 4. B — Assinatura ECDSA por linha (revisa código em produção)

> **Reversão de código já validado em hardware**, não de um doc. A Fase 5 em produção assina **1× por dia**: [`hub/arquivo_diario.py`](hub/arquivo_diario.py) `selar()` faz `assinatura = ECDSA(hash_final)` no fecho do dia; cada linha carrega só `hash` encadeado ([`contrato/formato`](hub/arquivo_diario.py)). O doc [`esp32_coletor_spec.md` §4](esp32_coletor_spec.md) descreve o mesmo. **B passa a exigir uma assinatura ECDSA por linha** — muda `arquivo_diario.py`, `assinador.py`, o formato e a ingestão.

### 4.1 Racional (por que reverter) — e o custo é load-bearing

Hoje (1×/dia), um crash antes do fecho deixa a cauda do dia **não-assinada**. O código já mitiga: [`recuperar_pendentes()`](hub/arquivo_diario.py) sela no boot arquivos de dias passados sem rodapé. Mas a janela **entre o crash e o reboot-selagem** fica com a cauda apenas encadeada por `hash` (recomputável sem chave) → **forjável** por quem tiver acesso de escrita ao SD nessa janela. Assinar cada linha **sela no instante da escrita** → essa janela fecha. É exatamente esse buraco que B fecha.

**Custo — resolvido (§7.3 travado):** produção amostra a **≥ 1/min** (`intervalo_leitura_s` config-driven em [`hub/config.py`](hub/config.py); os 5s são **só de desenvolvimento**). A ≥1/min → **≤ 1440 assinaturas/dia/coletor** → trivial para o secure element (ATECC608A / SE do hub). B é acessível. Ainda **prudente validar a vazão de assinatura do secure element** sob `taxa × nº sensores` no bring-up do firmware, mas **não é bloqueio** — a taxa de produção sai da zona de risco. (Se algum dia produção precisar de sub-10s, reabrir B — janela forjável ≤ 1min via cadência de tempo é o fallback registrado.)

### 4.2 Header (delta sobre `esp32_coletor_spec.md` §4)

```
# schema_version: 2
# tipo_arquivo: leituras
# cliente_id: CLI-000123           ← F (novo, coberto pela assinatura)
# site_id: SITE-0001               ← F (novo)
# coletor_id: COL-0007A1B2
# hub_id: HUB-0001A2F3
# coletor_pubkey_fingerprint: 9F:3A:...
# data_referencia: 2026-07-16
# timezone_offset: -03:00
# firmware_version: 2.3.1
# dia_anterior_hash_final: 7e3b...  (informativo)
# hdr_sig: MEUCIQD...==             ← header é assinado; semeia a cadeia
```

`hash_0 = SHA256(cabeçalho_canônico)`; `hdr_sig = ECDSA(priv, hash_0)`.

> O snapshot de calibração **não** fica no header — vai **em cada linha** (§4.3, §7.5 travado), tornando cada leitura auto-descritível e dispensando parsing com estado.

### 4.3 Corpo (uma linha por leitura) — delta

Formato canon + coeficientes de calibração (§7.5) + coluna `sig`:

```
seq|timestamp|sensor_id|area_id|tipo_medida|valor|unidade|protocolo_origem|status_leitura|cert_ver|cal_ganho|cal_offset|hash|sig
1|2026-07-16T00:01:00-03:00|SNR-EXP-TEMP-01|EXPURGO|temperatura|130.60|C|4-20mA|ok|3|0.9650|0.33|3f2a...|MEQCIB...==
```

- `valor` = **valor corrigido** (nominal já com calibração aplicada). Só `valor` (decisão: não gravar raw/nominal por linha).
- `cert_ver`/`cal_ganho`/`cal_offset` = **snapshot da calibração vigente naquela leitura** (§7.5 travado: repetir por linha). Cada linha fica **auto-descritível** — a empresa de calibração confronta os coeficientes lendo a própria linha, sem reconstruir estado.
- `hash_n = SHA256(hash_{n-1} + linha_sem_hash_sem_sig)` — cadeia de hash **inalterada** do canon.
- `sig_n = ECDSA(priv, hash_n)` — **novo**. Como `hash_n` já encadeia todo o prefixo, cada assinatura cobre transitivamente tudo que veio antes.

### 4.4 Recalibração no meio do dia (rollover é diário — G)

Com os coeficientes **em cada linha** (§4.3), recalibração mid-dia **não precisa de marcador nem parsing com estado**: as linhas anteriores à troca já carregam `cert_ver=3` (g=0.9650), as posteriores carregam `cert_ver=4` (g=0.9710). O ponto exato da troca é visível pela mudança de `cert_ver` entre linhas consecutivas. Cada leitura sempre reflete os coeficientes que a produziram. (O `map_versao`, se o map mudar, segue a mesma lógica — pode virar coluna se necessário; hoje o map é estático.)

### 4.5 Rodapé

```
# total_linhas: 1440
# hash_final: 5d9c...
# arquivo_sig: MEUCIQD...==   ← selo de "arquivo fechado" (ECDSA sobre hash_final)
```

Cada linha já é assinada (não-repúdio por linha). O `arquivo_sig` do rodapé é um **selo de fechamento** (marca o arquivo como completo) e é o que popula `file.ledger.assinatura` — mantém o modelo de ledger existente ([odoo spec §4.10](odoo_modelo_dados_spec.md)) coerente.

---

## 5. Ingestão e confronto (fluxo)

### 5.1 Na ingestão (porta guardada — rejeita cedo)

Antes de aceitar o arquivo no caminho quente (Timescale):
1. Verifica `hdr_sig` contra a `pubkey_fingerprint` do `coletor_id` (rejeita se device desconhecido/revogado).
2. Valida `cliente_id`/`site_id` do header vs cadastro (F).
3. **Caminha a cadeia**: para cada linha, recomputa `hash_n` e verifica `sig_n`. Qualquer falha = rejeição, com a `seq` exata do ponto de quebra em `file.ledger.motivo_rejeicao`.
4. Grava leituras no Timescale, cada linha taggeada com: `sensor_id`, `cliente_id`/`site_id`, `pubkey_fingerprint`, `file_id`/`hash` (link ao arquivo arquivado), `ts_ingestao`.
5. Arquiva o arquivo original assinado (object storage / SFTPGo) — **verdade canônica**.

**Arquivo sem rodapé (crash não-recuperado)** — regra explícita (é o cenário de durabilidade que justificou B): um device que trava e **não** chega a rodar `recuperar_pendentes()` produz um arquivo com `hdr_sig` + `sig` por linha **válidos, mas sem `arquivo_sig`/`total_linhas`**. Com B (assinatura por linha) esse arquivo é verificável linha a linha até a última `sig` válida. Regra de ingestão:
- Aceitar as linhas verificadas até a última `sig` válida (o dado É autêntico — cada linha foi selada na origem).
- Marcar `file.ledger.status_validacao = incompleto` (novo valor) — arquivo autêntico porém **não fechado**; não conta como atestado de dia completo (a detecção de lacuna do cron trata como dia parcial).
- **Sem `arquivo_sig` não há prova de truncamento**: não dá para saber se faltam linhas após a última verificada. Registrar isso; não tratar `incompleto` como equivalente a `valido`.

> **Custo**: passa de 1 verificação/dia para N verificações/dia/coletor. Dimensionar o serviço de ingestão para isso (verify ECDSA é barato no servidor, mas N pode ser grande — ver §4.1).

### 5.2 No relatório (confronto de auditoria — prova de veracidade)

Antes de imprimir um relatório com valor legal, confronta-se o Timescale contra os arquivos assinados do período. O confronto tem **duas partes** (as duas necessárias):
1. **Assinaturas válidas** — `hdr_sig` + cadeia de `sig` por linha, contra a pubkey vigente do device na época (device não-revogado naquele instante).
2. **Valores batem** — `valor` do arquivo == valor no Timescale, no intervalo do relatório.

Só (1) sem (2), ou (2) sem (1), não prova nada: é a assinatura que ancora a verdade; o value-match valida o Timescale contra ela. Divergência em qualquer parte = alerta de auditoria (Timescale adulterado, ou arquivo adulterado/ausente).

**Timescale = cache re-verificável**; **arquivo = fonte da verdade**. Adulteração direta no Timescale é pega no confronto contra os arquivos.

---

## 6. D — Enrollment: manual na v1, token na v2 (documentado)

**v1 (mantém canon, [esp32 spec §8](esp32_coletor_spec.md))**: chave gerada no device (secure element ATECC608A / secure element do hub); pubkey extraída na fábrica/instalação e registrada **manualmente** no Odoo (`coletor.pubkey_fingerprint` / `hub.secure_element_pubkey_fingerprint`). Simples e suficiente para poucos devices.

**v2 — token de enrollment (quando a escala crescer)**: automatiza o vínculo pubkey↔device sem aprovação manual, mantendo **1 chave por device** e non-repudiation. Esboço (da discussão, para retomar):
- Odoo gera token single-use, curta validade, vinculado a `device_code`+tenant; guarda só o **hash** do token.
- 1º boot: device gera par, envia `{device_code, pubkey, nonce, ts}` + **self-signature** (prova posse da privada) + **HMAC(token, req)** (prova autorização).
- Coletor **relaya via hub** (sem rota direta ao server); o server auto-popula o vínculo `coletor→hub`.
- Server valida `hash(token)` (não expirado, não usado), vincula pubkey→device, consome o token.
- Rotação = novo token; revogação = pubkey vai pro histórico (arquivos antigos ainda verificam).

**Não implementar na v1.** Registrado para não se perder.

---

## 7. Decisões de implementação a confirmar (não bloqueiam o desenho)

1. ~~Model `malha` dedicado vs bundle~~ — **TRAVADO: bundle** (ver §2.2).
2. ~~Onde mora a escala do 4-20mA~~ — **TRAVADO: map no `sensor` com flag `usa_map`** (§2.3). Decode Modbus fica no perfil compartilhado; calibração no cert. "Canal genérico" (Opção A antiga) descartado — o canon já separa melhor (RS-485 compartilhado vs analógico por-sensor). **Requisito UX travado**: help text obrigatório nos forms (§2.4) para evitar confusão entre map/decode/calibração.
3. ~~Taxa de assinatura por linha~~ — **TRAVADO: produção ≥ 1/min** (5s é só dev). ≤1440 sigs/dia/coletor → trivial; B acessível (§4.1). Resta apenas validar a vazão do secure element no bring-up (prudência, não bloqueio).
4. ~~Nome dos campos de offset~~ — **TRAVADO** via a distinção de 3 camadas + help text (§2.3/§2.4): `map_*` (sensor), `scale`/`offset` do registrador (perfil Modbus), `cal_ganho`/`cal_offset` (cert). Nomes distintos obrigatórios.
5. ~~Coeficientes no header vs por linha~~ — **TRAVADO: repetir por linha** (`cert_ver`/`cal_ganho`/`cal_offset`, §4.3). Cada leitura auto-descritível; recalibração mid-dia sem marcador nem parsing com estado (§4.4). Custo de bytes aceito (produção ≥1min → arquivo pequeno).

---

## 8. Explicitamente NÃO muda (considerado e mantido do canon)

- **A** — 1 arquivo por coletor/dia (multi-sensor). Não vira por-sensor.
- **G** — rollover diário; sem rotação por troca de cert (mid-dia via marcador, §4.4).
- **C** — sem compactação na v1 (candidata a v2, no servidor pós-validação).
- Arquivo de **alarme** ([esp32 spec §5](esp32_coletor_spec.md)) — mesma mudança de B se aplica (assinar por linha de transição), mas eventos são esparsos → custo desprezível. `cliente_id`/`site_id` (F) também entram no header do arquivo de alarme.
- Cadeia de hash **não atravessa dias**; proibição de `|`/`\n`/`\r` nos identificadores; control plane (config/comandos via MQTT).
