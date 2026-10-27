# Falha de instrumento vira alarme — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Laço 4–20 mA aberto e módulo sem comunicação viram alarme na borda, e o dashboard nunca mostra verde/"OK" para leitura sem limite, inválida ou de instrumento em falha.

**Architecture:** O hub (`leitor.py`) classifica a leitura (`status_leitura`), o `DetectorAlarme` ganha uma via de falha independente de limite, e o resto do pipeline (alarmes.txt assinado → MQTT → bridge/ingestão → Odoo/SSE) só aprende o novo `tipo_violacao`. O `status_leitura` passa a viajar até o frontend (NOTIFY do Timescale + histórico raw), onde tem precedência sobre `computeStatus`.

**Tech Stack:** Python 3.11/3.13 (hub, ingestão, API FastAPI), Odoo 18 addon, TimescaleDB (trigger PL/pgSQL), React 19 + Vitest.

**Spec:** `docs/superpowers/specs/2026-10-27-falha-instrumento-alarme-design.md`

## Global Constraints

- NE43: falha se corrente < **3.6 mA** ou > **21.0 mA**; só para canal com `map_in == (4, 20)`.
- `status_leitura` novo: **`falha_sensor`**. Precedência: `sensor_offline` > `falha_sensor` > `erro_leitura` > `suspeito` > `ok`.
- Alarme `falha_sensor`: entrada na **1ª** leitura. Alarme `sensor_offline`: entrada após **3** leituras `sensor_offline` seguidas. Saída de ambos: **3** leituras `ok` seguidas.
- Novo `tipo_violacao`: `falha_sensor` (rótulo Odoo "Falha do sensor"). `sensor_offline` já existe.
- Rótulos de UI (texto exato): `falha_sensor` → **"Sensor desconectado"**; `sensor_offline` → **"Sem comunicação"**; `erro_leitura`/`suspeito` → **"Leitura inválida"**; sem limite → **"Não avaliado"**; ajuda sem limite → **"Sem limite configurado — defina no Odoo"**.
- Leitura em falha/inválida continua gravada; a UI não a exibe como número de leitura (mostra "—").
- "Editar" já é gated por `isAdmin` (`frontend/src/pages/DashboardPage.tsx:89`) — sem trabalho; não regredir.
- Testes Odoo: sempre `--test-tags /afr_sentinela_sensor_monitor` (memória `odoo-test-command-tags`).
- Prod é persistente: nenhuma migração apaga dados (memória `sentinela-prod-persistente`).

## Review Focus

- Alarme de faixa aberto + cabo cai: deve emitir `saida_alarme` (faixa) e depois `entrada_alarme` (`falha_sensor`), nessa ordem → Task 2.
- Falha ↔ offline alternando com alarme aberto: nenhum evento novo → Task 2.
- Restart do hub com alarme de falha aberto: estado persistido, não re-emite entrada → Task 2.
- Sensor sem limite e sem leitura (antes do 1º SSE) não pode ficar verde → Task 5.
- Leitura `ok` acima do NE43 superior (ex. 22 mA = 112,5 ppm) também é falha, não "fora de faixa" → Task 1.

---

### Task 1: Hub — classificar leitura NE43 (`falha_sensor`)

**Files:**
- Modify: `hub/leitor.py` (`_ler_device`, novo helper)
- Test: `hub/tests/test_leitor.py`

**Interfaces:**
- Produces: leituras com `status_leitura == "falha_sensor"`; helper `Leitor._corrente_ma(canal, valor_eng) -> float | None` (None se canal não é 4–20).

- [ ] **Step 1: Write the failing tests**

```python
def test_laco_aberto_4_20_vira_falha_sensor(tmp_path):
    # canal map_in (4,20) -> map_out (0,100); driver devolve -25.0 (0 mA)
    ...
    assert leituras[0]["status_leitura"] == "falha_sensor"
    assert leituras[0]["valor"] == -25.0          # valor gravado, não mascarado

def test_corrente_acima_de_21ma_vira_falha_sensor(tmp_path):   # 112.5 ppm = 22 mA
def test_corrente_3_6ma_exato_nao_e_falha(tmp_path):          # -2.5 ppm = 3.6 mA -> "ok"
def test_canal_0_20_sem_gate_ne43(tmp_path):                   # map_in (0,20), valor 0 -> "ok"
def test_falha_sensor_prevalece_sobre_faixa(tmp_path):         # faixa_min=0 e 0 mA -> "falha_sensor", não "suspeito"
```

Use os fakes existentes (`_DriverFaixa` / config helpers do arquivo) para montar canais.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest hub/tests/test_leitor.py -q` — Expected: os 5 novos FAIL.
- [ ] **Step 3: Implement** — corrente = inversão linear do map sobre `entrada["value"]` (valor **antes** da calibração): `mA = in_min + (v - out_min) * (in_max - in_min) / (out_max - out_min)`. Em `_ler_device`, checar NE43 antes do gate de faixa; falha marca `ruim = True` (entra na lógica de reconexão como hoje faz `suspeito`).
- [ ] **Step 4: Run** `.venv/bin/python -m pytest hub/tests -q` — Expected: all PASS.
- [ ] **Step 5: Commit** `feat(hub): classify NAMUR NE43 out-of-envelope current as falha_sensor`

---

### Task 2: Hub — via de alarme de falha no `DetectorAlarme`

**Files:**
- Modify: `hub/detector_alarme.py`
- Test: `hub/tests/test_detector_alarme.py`

**Interfaces:**
- Consumes: leituras com `status_leitura` de Task 1.
- Produces: eventos `{"tipo_evento": "entrada_alarme"|"saida_alarme", "tipo_violacao": "falha_sensor"|"sensor_offline"|..., ...}` no mesmo formato de `_evento` (limites vigentes `None` quando não há limite). Estado por sensor ganha `"falha_contador": int`, `"ok_contador": int` (persistidos no mesmo JSON; estado antigo sem essas chaves deve carregar).

- [ ] **Step 1: Write the failing tests**

```python
def test_falha_sensor_entra_na_primeira_leitura_sem_limite():
    d = DetectorAlarme({}, n=3)                         # sensor SEM limite
    ev = d.avaliar(leitura(status="falha_sensor"))
    assert [e["tipo_evento"] for e in ev] == ["entrada_alarme"]
    assert ev[0]["tipo_violacao"] == "falha_sensor"

def test_sensor_offline_entra_so_na_terceira_seguida():
    # 1ª e 2ª -> [], 3ª -> entrada sensor_offline; uma "ok" no meio zera a contagem

def test_saida_falha_apos_tres_ok_seguidas():
    # entrada falha; ok, ok -> []; 3ª ok -> saida_alarme tipo_violacao "falha_sensor"

def test_falha_fecha_alarme_de_faixa_aberto_e_abre_falha():
    # limite max 10; 3 leituras ok com valor 20 -> entrada acima_limite
    # depois falha_sensor -> eventos == [saida(acima_limite), entrada(falha_sensor)] nessa ordem

def test_troca_falha_offline_com_alarme_aberto_nao_emite():
    # falha_sensor (entra) -> 3x sensor_offline -> []

def test_apos_recuperar_faixa_reavalia_com_histerese():
    # falha, 3 ok dentro da faixa -> saida; depois 3 leituras acima -> entrada acima_limite só na 3ª

def test_erro_leitura_e_suspeito_nao_alarmam():

def test_estado_de_falha_persiste_entre_instancias(tmp_path):
    # entra falha com estado_path; nova instância + falha_sensor -> [] (não re-emite)
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest hub/tests/test_detector_alarme.py -q` — Expected: novos FAIL.
- [ ] **Step 3: Implement** — `avaliar` passa a tratar primeiro a via de falha (qualquer sensor, com ou sem limite); a via de faixa existente só roda com leitura `ok`, sem alarme de falha aberto e com limite. Constante `N_OFFLINE = 3`, `N_SAIDA_FALHA = 3` no módulo (valores da spec; não configuráveis). Estado com `tipo_violacao` em `("falha_sensor", "sensor_offline")` = alarme de falha aberto.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest hub/tests -q` — Expected: all PASS (inclui `test_main*` que montam o detector).
- [ ] **Step 5: Commit** `feat(hub): alarm on instrument failure (falha_sensor immediate, sensor_offline after 3)`

---

### Task 3: Odoo + ingestão — aceitar `falha_sensor`

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/alarm_event.py:15-20` (selection), `addons/afr_sentinela_sensor_monitor/__manifest__.py` (bump version)
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_alarm_event.py`, `ingestao/tests/` (teste de ingestão de alarme existente — achar com `grep -l processar_entrada_alarme ingestao/tests`)

**Interfaces:**
- Produces: `sensor_monitor.alarm.event.tipo_violacao` aceita `'falha_sensor'`.

- [ ] **Step 1: Write failing tests** — Odoo: `test_cria_alarme_falha_sensor` (create com `tipo_violacao='falha_sensor'`, `limite_configurado_snapshot` 0.0). Ingestão: um `alarmes.txt` assinado com entrada `falha_sensor` (limites vazios) é ingerido como `valido` e chama `processar_entrada_alarme` com `tipo_violacao == 'falha_sensor'`.
- [ ] **Step 2: Run** Odoo test (comando da memória `odoo-addon-dev-gotchas`, `--test-tags /afr_sentinela_sensor_monitor`, `--http-port=8169`) e `.venv/bin/python -m pytest ingestao/tests -q` — Expected: Odoo FAIL (valor inválido de selection); ingestão PASS ou FAIL (se o parse rejeitar limite vazio — então corrigir em `contrato/`).
- [ ] **Step 3: Implement** — adicionar `('falha_sensor', 'Falha do sensor')`; ajustar contrato/ingestão só se o teste mostrar rejeição.
- [ ] **Step 4: Run** os mesmos comandos — Expected: PASS.
- [ ] **Step 5: Commit** `feat(odoo): falha_sensor alarm violation type`

---

### Task 4: `status_leitura` chega ao frontend (NOTIFY + histórico)

**Files:**
- Modify: `timescale/init.sql:70-78` (adicionar `'status_leitura', NEW.status_leitura` ao `json_build_object`)
- Create: `timescale/migracoes/2026-10-27-notify-status-leitura.sql` (o `CREATE OR REPLACE FUNCTION` completo, idempotente, sem tocar dados)
- Modify: `api/timescale.py:4-12` (`buscar_raw` retorna `status_leitura`), `api/historico.py` (repassa no raw), `frontend/src/lib/types.ts` (tipos)
- Test: `api/tests/test_live_trigger.py`, `api/tests/test_historico.py`

**Interfaces:**
- Produces: payload NOTIFY/SSE `{"sensor_id","site_id","time","valor","status_leitura"}`; histórico raw `[{time, valor, status_leitura}]`; TS: `export type StatusLeitura = 'ok'|'suspeito'|'erro_leitura'|'falha_sensor'|'sensor_offline'`; `LivePoint.status_leitura: StatusLeitura`; ponto raw do histórico com `status_leitura?: StatusLeitura`.

- [ ] **Step 1: Failing tests** — `test_notify_inclui_status_leitura` (insert com `status_leitura='falha_sensor'` → payload tem a chave); `test_historico_raw_inclui_status_leitura`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest api/tests/test_live_trigger.py api/tests/test_historico.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** + criar o arquivo de migração (mesmo corpo da função do init.sql).
- [ ] **Step 4: Run** `.venv/bin/python -m pytest api/tests -q` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(api): carry status_leitura in live NOTIFY and raw history`

---

### Task 5: Frontend — estado honesto (falha, inválido, não avaliado)

**Files:**
- Modify: `frontend/src/lib/status.ts` (estados + rótulos), `frontend/src/lib/api/real/liveApi.ts` (~linha 84-90: parar de mapear `unknown`→`ok`; levar `status_leitura`), `frontend/src/lib/aggregateStatus.ts` (severidade), `frontend/src/components/statusVisuals.tsx` (forma/cor dos novos estados), `frontend/src/components/SensorDetailPanel.tsx`, `frontend/src/components/AreaCard.tsx`, `frontend/src/components/widgets/KpiWidget.tsx` (esconder número), alarm labels (`AlarmItem.tsx`/onde `tipo_violacao` vira texto), `frontend/src/lib/types.ts` (`AlarmTipoViolacao` += `'falha_sensor'`)
- Test: `frontend/src/lib/status.test.ts`, `frontend/src/lib/aggregateStatus.test.ts`, `frontend/src/lib/api/real/liveApi.test.ts` (ou o teste existente do liveApi), `frontend/src/components/SensorDetailPanel.test.tsx`, `frontend/src/components/AreaCard.test.tsx`

**Interfaces:**
- Consumes: `StatusLeitura`, `LivePoint.status_leitura` (Task 4).
- Produces: `StatusResult['state']` = `'ok'|'warn'|'crit'|'unknown'|'fault'|'invalid'`; `resolveStatus(value: number | null, statusLeitura: StatusLeitura | undefined, t: Threshold | null): StatusResult` em `lib/status.ts` (precedência status→limite); `LABELS` com `fault`/`invalid`/`unknown = 'Não avaliado'`; `AlarmState` ganha `'fault'|'invalid'|'unknown'`. Severidade: `unknown 0 < ok 1 < invalid 2 < warn 3 < crit 4 = fault 4`.

- [ ] **Step 1: Failing tests**

```ts
it('falha_sensor vira fault "Sensor desconectado" mesmo dentro do limite', () =>
  expect(resolveStatus(-25, 'falha_sensor', t)).toMatchObject({ state: 'fault', label: 'Sensor desconectado' }))
it('sensor_offline vira fault "Sem comunicação"', ...)
it('suspeito/erro_leitura viram invalid "Leitura inválida"', ...)
it('sem limite e leitura ok vira unknown "Não avaliado", nunca ok', () =>
  expect(resolveStatus(10, 'ok', null).state).toBe('unknown'))
it('liveApi não converte unknown em ok', ...)              // ponto sem threshold -> alarm_state 'unknown'
it('drawer em fault mostra "Sensor desconectado" e não mostra "-25.0"', ...)
it('card em fault não mostra o valor numérico', ...)
it('área com um sensor fault agrega como fault/crit', ...)
```

- [ ] **Step 2: Run** `cd frontend && npx vitest run src/lib src/components/SensorDetailPanel.test.tsx src/components/AreaCard.test.tsx` — Expected: novos FAIL.
- [ ] **Step 3: Implement** — `resolveStatus` é o único lugar com a precedência; `computeStatus` continua para o caso `ok`. Forma do estado `fault` distinta de `crit` em `statusVisuals.tsx` (ex. quadrado vazado com ✕) e `invalid`/`unknown` com tracejado neutro — nunca o tom de `good`. Onde há número de leitura, `fault`/`invalid` mostram "—" + rótulo. Linha de ajuda "Sem limite configurado — defina no Odoo" no drawer quando `unknown`.
- [ ] **Step 4: Run** `cd frontend && npx vitest run && npx tsc -b` — Expected: all PASS, sem erro de tipo.
- [ ] **Step 5: Commit** `feat(frontend): honest sensor state — fault, invalid, not evaluated`

---

### Task 6: Deploy e verificação em produção (controller, não subagente)

- [ ] Local: aplicar migração no Timescale local (`psql ... -f timescale/migracoes/2026-10-27-notify-status-leitura.sql`), upgrade do addon + restart do Odoo local, restart `sentinela-bridge`/`sentinela-watcher`.
- [ ] VPS: copiar arquivos alterados (`tar` como no deploy), migração no `timescaledb`, `odoo -u afr_sentinela_sensor_monitor --stop-after-init` + restart, restart `api`/`bridge`/`watcher`, `vite build` → rsync `~/www`.
- [ ] Pi OXIMED: `rsync -a --exclude __pycache__ --exclude tests hub contrato sentinela-pi:odoo_sentinela/` + `sudo systemctl restart sentinela-hub`.
- [ ] Critério de pronto da spec (itens 1–5) verificado em prod: `entrada_alarme falha_sensor` no journal do hub, alarme aberto no Odoo VPS, toast + "Sensor desconectado" no dashboard sem "-25.0", desligar RS-485 → `sensor_offline` em ~18 s, religar → saída após 3 ok.
