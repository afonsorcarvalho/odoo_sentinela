# Geração de alarme na borda + sinal em tempo real

**Data:** 2026-07-26
**Status:** aprovado (brainstorming) — pendente plano de implementação

## Problema

Sensores reais cruzam seus limiares continuamente, mas **nenhum alarme é
gerado**. Diagnóstico da revisão:

- Os únicos 4 eventos em `sensor_monitor.alarm.event` são os seeds de
  `ingestao/seed_alarmes_demo.py` (2026-07-21). Em ~5 dias de hardware real:
  zero alarmes, apesar de furos claros (`SNR-E2E-CH1` limite 18–25, leituras
  até 67; `TEMP-HENKE` limite 18–25, até 28.6).
- Arquitetura é **edge-detection**: `ingestao/ingestor._processar_alarmes` só
  cria alarme a partir de arquivos `*_alarmes.txt` (eventos `entrada_alarme` /
  `saida_alarme`). O único emissor desses arquivos hoje é
  `coletor_simulado/gerador.py`.
- O **hub real (`hub/`) não avalia limiar de alarme nem emite `*_alarmes.txt`**.
- O limiar de alarme (`sensor_monitor.alarm.threshold.limite_min/limite_max`)
  **nunca é enviado ao hub**. O que o hub recebe é a **faixa de plausibilidade**
  física (`sensor.faixa_min/faixa_max`, `usa_faixa`) — conceito distinto: fora
  dela a leitura vira `status_leitura="suspeito"` (gate anti-lixo, ver
  `hub/leitor.py::_fora_da_faixa`), não gera alarme.

## Objetivo

O hub passa a **detectar cruzamento de limiar** e sinalizar por **dois
caminhos**:

1. **MQTT (efêmero, instantâneo)** — dashboard pisca/toast na hora.
2. **`alarmes.txt` assinado (durável, auditável)** — único registro que vira
   evento no Odoo, preservando a cadeia de integridade (nada vira verdade sem
   lastro criptográfico).

## Decisões (brainstorming)

| # | Decisão |
|---|---------|
| 1 | **Caminho duplo.** MQTT (velocidade) + arquivo assinado (verdade legal). |
| 2 | **Alarme só avalia leitura `status_leitura="ok"`.** Leitura `suspeito`/`erro_leitura` nunca dispara alarme (evita alarme falso por glitch/fd-zumbi). |
| 3 | **MQTT nunca persiste.** Só o `alarmes.txt` assinado vira evento no Odoo → **zero dedup de persistência** (os caminhos nunca colidem no banco). A única reconciliação é de UI (evitar toast duplo), ver §6. |
| 4 | **Histerese.** `entrada_alarme` após **N=3** leituras `ok` consecutivas fora do limite; `saida_alarme` só quando o valor volta com **folga** (limite ∓ margem). N e margem configuráveis (hub-level). |
| 5 | **Sinal ao vivo = toast vermelho** (reusa `Toast`/`ToastContainer`); o card durável aparece no painel e pisca (`isNew`) quando o arquivo é ingerido. |

**Fora de escopo (YAGNI):** alerta sonoro; evento provisório "pendente de
lastro" no Odoo; histerese por-sensor.

## Arquitetura / fluxo

```
                            ┌─ MQTT sentinela/alarme/<hub>/<coletor>/<sensor>
hub detecta cruzamento ─────┤      → bridge_telemetria → SSE "alarme_ao_vivo" → TOAST (efêmero, sem id Odoo)
  (N=3 leituras "ok",       │
   histerese na saída)      └─ alarmes.txt (assinado, mesmo formato do coletor_simulado)
                                   → SFTP → watcher_ingestao → ingestor → Odoo alarm.event
                                   → /alarmes (poll 5s) → CARD no painel (durável, pisca isNew)
```

Só o ramo do arquivo persiste. O toast ao vivo cobre a janela (segundos) até o
card durável chegar.

## Componentes

### 1. Odoo → hub: entrega do limiar

- **`api/config_publisher.py` / `config_publish_router.py`** (o serializer que
  hoje já manda a faixa plausível — commit 637abe8): incluir, por sensor/canal,
  `limite_min` e `limite_max` de `sensor_monitor.alarm.threshold`, além de um
  flag `usa_limite` (há threshold configurado?) e os params de histerese
  hub-level (`alarme_n=3`, `alarme_margem`).
- **`hub/config.py`**: novos campos por canal `limite_min: float|None`,
  `limite_max: float|None`; e no nível do hub `alarme_n: int = 3`,
  `alarme_margem: float`. Parse defensivo (ausente → None / default), igual ao
  padrão já usado para `faixa_min/max`.

### 2. Hub — máquina de estado de alarme

Local: `hub/leitor.py` (onde `_fora_da_faixa` já roda por canal). Novo módulo
coeso `hub/detector_alarme.py` com a lógica pura (testável isolado), consumido
pelo leitor.

Estado **por canal**, persistido em disco (JSON, ex.: ao lado do estado do
leitor) para sobreviver a restart:

```
{ em_alarme: bool, tipo_violacao: 'acima_limite'|'abaixo_limite'|None,
  contador_fora: int }
```

Regra por leitura (chamada com o valor normalizado e o `status_leitura`):

- `status_leitura != "ok"` → **ignora** (não avança nem zera `contador_fora`;
  leitura suspeita não carrega informação de alarme).
- `status == "ok"` e **não** `em_alarme`:
  - valor `> limite_max` ou `< limite_min` → `contador_fora += 1`; se
    `contador_fora >= N` → **emite `entrada_alarme`**, `em_alarme=True`,
    `tipo_violacao` conforme o lado, `contador_fora=0`.
  - valor dentro → `contador_fora = 0`.
- `status == "ok"` e `em_alarme`:
  - valor voltou **com folga** (`< limite_max - margem` e `> limite_min +
    margem`) → **emite `saida_alarme`**, `em_alarme=False`.
  - senão → mantém.

Persistência: carrega no boot; grava a cada transição. Restart no meio de uma
excursão **não** re-emite `entrada_alarme` (o estado já está `em_alarme`).

### 3. Hub — saídas ao cruzar

Ao emitir `entrada_alarme` / `saida_alarme`:

- **Arquivo:** grava linha assinada em `alarmes.txt` do dia. Reusa
  `contrato/formato.gerar_linha_alarme` (mesma função do `coletor_simulado`) e
  o `hub/assinador.py` (assinatura-por-linha já usada em
  `hub/arquivo_diario.py` para leituras). Provável extensão de
  `arquivo_diario.py` (ou módulo irmão) para o arquivo `*_alarmes.txt`,
  mantendo cabeçalho+hdr_sig+rodapé no mesmo padrão. `enviador_sftp.py` já
  varre e envia; confirmar que o padrão de nome `*_alarmes.txt` entra na
  varredura.
- **MQTT:** publica em `sentinela/alarme/<hub>/<coletor>/<sensor>` (reusa
  `hub/publicador_mqtt.py`), payload:
  `{ sensor_id, area_id, tipo_medida, tipo_violacao, tipo_evento, valor,
  limite, timestamp }`. `retain=False` (efêmero).

### 4. Ingestão

- **`scripts/bridge_telemetria.py`**: além do tópico de telemetria, assina
  `sentinela/alarme/#`. Ao receber, **não** grava em Timescale nem Odoo —
  apenas repassa como evento SSE `alarme_ao_vivo` (via o mesmo mecanismo NOTIFY
  → `api/live_listener.py` → `api/live.py` que a telemetria usa). Canal/rótulo
  SSE distinto do `leitura`.
- **`alarmes.txt`**: `scripts/watcher_ingestao.py` já aceita `*_alarmes.txt`
  (linha 72) → `ingestor._processar_alarmes` → `odoo_cliente`. **Inalterado.**

### 5. Odoo — guard "um-aberto-por-sensor"

`ingestao/odoo_cliente.processar_entrada_alarme`: antes de `create`, buscar
evento aberto (`timestamp_resolucao_sensor = False`) do mesmo sensor; se
existir, **não cria** (retorna o existente). Defesa contra duplicata em
restart / reingestão. `processar_saida_alarme` já resolve o aberto mais recente
(inalterado).

### 6. Frontend

- **Cliente SSE** (`frontend/src/lib/api/real/liveApi.ts` + o EventSource já
  existente): tratar o evento `alarme_ao_vivo`.
- **Toast ao vivo:** disparar um `Toast` vermelho imediatamente com os dados do
  payload MQTT. O evento efêmero **não tem `id` do Odoo** — chavear por
  `sensor_code + timestamp` (arredondado).
- **Reconciliação toast ao vivo × toast durável** (`ToastContainer.tsx`): hoje
  o `ToastContainer` já dispara toast pra cada alarme novo vindo do poll
  `/alarmes` (diff por `id`). Para não duplicar:
  - Registrar as chaves `(sensor_code, timestamp)` já toasteadas ao vivo.
  - Quando o evento durável chega pelo poll, **suprimir** seu toast se a chave
    já foi toasteada ao vivo (o card + flash `isNew` bastam).
  - **Fallback de resiliência:** se nenhum toast ao vivo ocorreu para aquele
    evento (ex.: MQTT caiu), o `ToastContainer` **ainda** toasta pelo poll —
    nenhum alarme fica sem sinal visual.
- Card do painel: `AlarmItem`/`AlarmPanel` já piscam `isNew`. **Inalterado.**

## Testes

- **Detector (`hub/detector_alarme.py`), unitário:** entrada após N=3;
  não-entrada com N-1; gate de plausibilidade (`suspeito` não avança contador);
  saída só com folga (banda morta); flapping perto do limite não gera
  enxurrada; persistência/restore de estado (restart não re-emite `entrada`).
- **`hub/config.py`:** parse de `limite_min/max`, ausência → None, params de
  histerese default.
- **Arquivo:** `alarmes.txt` do hub bate byte-a-byte no formato que
  `ingestao/validador` aceita (cabeçalho, hdr_sig, linha assinada, rodapé).
- **MQTT publish:** tópico e payload corretos em entrada/saída.
- **`bridge_telemetria`:** mensagem de alarme vira SSE `alarme_ao_vivo` e **não**
  toca Odoo/Timescale.
- **Frontend:** SSE `alarme_ao_vivo` → toast; supressão de toast durável
  duplicado; fallback de toast quando não houve sinal ao vivo.
- **Odoo guard:** `processar_entrada_alarme` não duplica evento aberto do mesmo
  sensor; `saida` fecha o aberto.
- **Integração (opcional):** furo real ponta-a-ponta em ambiente de teste
  (leitura ok fora do limite ×3 → arquivo + MQTT → toast + card).

## Riscos / notas

- **Faixa de plausibilidade apertada demais** pode engolir excursão real como
  `suspeito` e suprimir alarme (decisão Q2 aceita o trade-off). Documentar:
  faixa de plausibilidade deve ter folga sobre o limiar de alarme.
- **Latência do ramo durável** (flush do arquivo diário + poll do watcher +
  poll de 5s) é coberta pelo toast ao vivo; se o toast ao vivo falhar, o card
  ainda chega (e toasta via fallback), só mais devagar.
- **`limite_configurado_snapshot`** no evento vem do arquivo
  (`limite_min/max_vigente` da linha), não do Odoo no momento da ingestão —
  preserva o valor vigente no instante da detecção (auditoria).
