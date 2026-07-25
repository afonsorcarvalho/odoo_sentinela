# Design — Detecção de leitura implausível + self-healing serial

Data: 2026-07-25

## Problema

Em 2026-07-25 o sensor Henke (RS-WS-N01-2D) passou a gravar `0.0` (temperatura e
umidade) por horas. **O sensor estava perfeito** — sonda direta lia 27,5 °C /
53,5 %RH. Causa raiz: o driver abre o fd serial **uma vez** no `__init__` e o reusa
por horas; um glitch de USB (`ch341-uart ttyUSB1: urb stopped: -32`) corrompeu esse
fd de longa duração, que passou a entregar **frames Modbus válidos (CRC OK) contendo
0,0**. Como o frame é bem-formado, `read_raw()`/`probe()` retornam `ok=True,
values=[0,0]` — **não** levantam `RuntimeError` — e o `0.0` é gravado como leitura
real com `status_leitura="ok"`. Restart (fd novo) resolve na hora.

Dois modos de falha, dos quais só um estava tratado:

1. **Device mudo (timeout)** → `RuntimeError` → resiliência marca `sensor_offline`. ✅
2. **fd zumbi entrega frame válido de 0** → gravado como `ok` valor `0.0`. ❌

O objetivo é (a) **detectar e marcar** leituras implausíveis sem sumir com a
evidência (é sistema de conformidade — o arquivo assinado é a fonte da verdade), e
(b) **recuperar sozinho** (o device ficou preso em 0 até um restart manual).

Ver memória `serial-fd-zumbi-zeros` e `docs/discussao-drivers-extensibilidade.md`.

## Estado atual (referência)

- Linha assinada de leitura já carrega `status_leitura`
  ([contrato/formato.py:50-58](../../../contrato/formato.py#L50)); valores hoje:
  `ok` / `erro_leitura` / `sensor_offline`.
- `hub/leitor.py:ler_todos` já isola falha por dispositivo (resiliência Plano A):
  exceção → `sensor_offline`; sucesso → grava valor com `ok`. É aqui que o `0.0`
  do fd zumbi entra pelo caminho de sucesso.
- Cabeçalho assinado começa em `# schema_version: 2` e é o **seed do hash**
  (`hash_seed(cabecalho_canonico)`), então mexer nele é mudança de schema.
- Odoo: `sensor_monitor.sensor`
  ([addons/afr_sentinela_sensor_monitor/models/sensor.py](../../../addons/afr_sentinela_sensor_monitor/models/sensor.py))
  — sem campo de faixa-válida hoje. `sensor_monitor.modbus.device`
  ([models/modbus_device.py](../../../addons/afr_sentinela_sensor_monitor/models/modbus_device.py))
  já tem `_check_slave_address_range` — é onde entram os params de reconexão.
- `alarm_threshold.limite_min/max` existe mas é **alarme** (fora do conforto,
  notifica), NÃO plausibilidade (fisicamente impossível). Não reutilizar.
- config-publish (`api/config_publisher.py`) já valida e serializa a config do hub;
  padrão `ConfigInvalida → HTTP 422` (C1, já mergeado). Novos campos entram aí.

## Decisões (aprovadas no brainstorm)

### 1. Gate de plausibilidade — detecta + marca

- **Odoo, no sensor:** `faixa_min` e `faixa_max` (`fields.Float`, **opcionais**).
  Vazios ⇒ sem gate para aquele sensor (backward-compatible; sensores existentes
  seguem funcionando). Ex. umidade: `faixa_min=0.1`, `faixa_max=100`.
- **Validação no Odoo:** se ambos preenchidos, exigir `faixa_min < faixa_max`
  (constraint); a publicação rejeita config inconsistente com `ConfigInvalida →
  HTTP 422`. Falha no Odoo, nunca no Pi.
- **config-publish:** serializa `faixa_min`/`faixa_max` por canal para o hub.
- **hub `leitor.ler_todos`:** para cada canal com faixa definida, se
  `valor < faixa_min` ou `valor > faixa_max`, grava o **valor real** (não zera,
  não descarta) com `status_leitura="suspeito"`. Sem faixa definida → comportamento
  atual inalterado.
- **Enum `status_leitura`** passa a: `ok` / **`suspeito`** (novo) / `erro_leitura`
  / `sensor_offline`. NÃO renomear os existentes (evita churn em todo o pipeline;
  `erro_leitura` e `sensor_offline` são causas distintas que a auditoria separa).
- **Downstream:** `ingestao/validador` e `ingestor` aceitam `suspeito`; Timescale
  grava; frontend exibe/sinaliza `suspeito` (visual próximo de offline/alerta).

### 2. Self-healing serial — recupera sozinho

- No `hub/leitor`, por dispositivo: contar leituras consecutivas **suspeitas OU
  falhas** (`suspeito`/`erro_leitura`/exceção). Ao atingir **N** seguidas, fechar e
  **recriar o driver** do device (`disp.driver.close()` + `criar_driver(...)` novo →
  fd serial novo). Encaixa no contrato de adapter existente (`ler`/`close`).
- **Teto:** após **M** reconexões sem voltar a `ok`, o device cai para
  `sensor_offline` e só re-tenta reconectar a cada **K** ciclos de leitura (não fica
  reabrindo indefinidamente num device fisicamente ausente).
- Ao primeiro `ok` após reconexão, zerar contadores e logar recuperação (o
  `leitor` já loga "leitura recuperada").
- **Parâmetros `N`, `M`, `K` configuráveis no Odoo, por `modbus.device`**, com
  defaults `N=3`, `M=5`, `K=10`. Publicados na config; `hub/config.py` os parseia
  (com os mesmos defaults como fallback, para config antiga sem os campos).

### 3. Legenda de colunas no cabeçalho — schema v3

- `montar_cabecalho` passa a emitir `# schema_version: 3` e uma linha
  `# colunas: <lista>` conforme `tipo_arquivo`:
  - leituras: `seq|timestamp|sensor_id|area_id|tipo_medida|valor|unidade|protocolo_origem|status_leitura|cert_ver|cal_ganho|cal_offset|hash|sig`
  - alarmes: as colunas de `gerar_linha_alarme`.
- A linha entra no **cabeçalho canônico** → é coberta pela assinatura (legenda
  **à prova de adulteração**; bônus de auditoria).
- **Validador aceita v2 (sem `# colunas:`) e v3 (com)** — arquivos antigos seguem
  válidos. `_eh_linha_cabecalho` já trata linhas `#`; garantir que `# colunas:` é
  reconhecida como metadado de cabeçalho e não como corpo.
- Reconstrução de estado (`hub/arquivo_diario.reconstruir_estado`) já deriva o hash
  do cabeçalho inteiro — a linha nova é absorvida naturalmente, mas **arquivos v3
  não são intercambiáveis com v2 no mesmo dia** (o seed muda). Como o nome do
  arquivo é por dia e o schema sobe no deploy, não há mistura dentro de um arquivo.

## Interações e riscos

- **Cadeia de hash:** o `status_leitura` é campo **existente** da linha — usar
  `suspeito` não muda o formato nem o hash. A legenda muda o **cabeçalho** → por
  isso o bump v2→v3 (item 3), isolado e versionado.
- **Contador de reconexão conta suspeito E falha:** um device que lê fora da faixa
  repetidamente (fd zumbi) dispara reconexão igual a um que dá timeout — ambos são
  "device precisa de fd novo". Correto para o caso do Henke.
- **`faixa` opcional (precondição de proteção):** sensores sem faixa definida
  continuam vulneráveis ao zumbi-0 (só o self-healing os cobre). Auditar/definir
  faixa nos sensores que importam (ex.: Henke). Análogo à precondição `usa_map` do
  C1.
- **Self-healing não mascara falha real:** enquanto reconecta, as leituras saem
  `suspeito`/`sensor_offline` (registradas). A recuperação é visível no lastro, não
  silenciosa.
- **Boot vs runtime:** recriar o driver em runtime não pode derrubar o hub se a
  porta sumiu (ex.: USB removido) — a recriação fica dentro do `try` por device do
  `ler_todos`; falha ao reabrir → `sensor_offline`, não crash.

## Testes (o que precisa passar)

- **Gate:** valor fora de `[min,max]` → `status_leitura="suspeito"`, valor real
  preservado; dentro → `ok`; sem faixa → `ok` (inalterado). Umidade `0.0` com
  `faixa_min=0.1` → `suspeito` (o caso Henke).
- **Odoo:** `faixa_min >= faixa_max` → constraint/`ConfigInvalida` (HTTP 422 na
  publicação). Faixa vazia publica sem gate.
- **config-publish round-trip:** faixa e N/M/K saem na config do hub; `hub/config`
  parseia com defaults quando ausentes.
- **Self-healing:** N leituras suspeitas seguidas → `close()`+recria driver
  (transporte/driver fake registra a reabertura). M reconexões sem `ok` → cai para
  `sensor_offline` + re-tenta a cada K. Primeiro `ok` → zera contadores.
  Reabertura que falha (porta ausente) → `sensor_offline`, hub sobrevive.
- **Schema v3:** cabeçalho tem `# schema_version: 3` + `# colunas:` correta por
  tipo; assinatura do cabeçalho cobre a legenda; validador aceita v2 e v3;
  reconstrução de estado e selagem inalteradas no conteúdo (regressão).
- **Ingestão:** arquivo v3 com linha `suspeito` ingere; Timescale grava o status;
  não quebra o confronto.

## Fora de escopo (YAGNI)

- Detecção de "stuck/travado" (N leituras idênticas dentro da faixa) — backlog; o
  gate de faixa + self-healing cobrem o caso atual.
- Migração de arquivos v2 existentes — permanecem v2, válidos.
- Faixa por tipo-de-medida como default global — hoje é por sensor; se virar
  repetitivo, um default por `measurement.type` é evolução futura.
- Cutover do Henke para o driver genérico (assunto do doc de extensibilidade).
