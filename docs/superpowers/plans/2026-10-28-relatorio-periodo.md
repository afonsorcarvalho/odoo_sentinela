# Relatório de Período Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tela `/relatorios` que mostra histórico agregado (hora/dia/mês) de sensores escolhidos num período de datas e gera PDF A4 idêntico para fiscalização.

**Architecture:** API FastAPI ganha `api/relatorio_dados.py` (SQL na hypertable bruta, fuso America/Sao_Paulo, buckets completos), `api/relatorio_odoo.py` (alarmes por sobreposição, histórico de limites, nome do emissor), `api/relatorio.py` (router: `GET /relatorio` JSON e `GET /relatorio.pdf`) e `api/relatorio_pdf.py` (render reportlab). Frontend ganha `reportApi` (real+mock) e `RelatoriosPage` com gráfico ECharts.

**Tech Stack:** Python 3.11, FastAPI, psycopg (via `ingestao.timescale.conectar`), TimescaleDB, Odoo XML-RPC (`ingestao.odoo_cliente.executar`), reportlab; React 19, react-router 8, react-query, ECharts 6, Tailwind 4, vitest.

**Spec:** `docs/superpowers/specs/2026-10-28-relatorio-periodo-design.md`

## Global Constraints

- Fuso de todo cálculo e rótulo: `America/Sao_Paulo`. Intervalo efetivo = [inicio 00:00 local, (fim+1 dia) 00:00 local).
- Granularidade: inicio == fim → `hora`; (fim − inicio) + 1 ≤ 62 dias → `dia`; senão `mes`.
- Máx 366 dias, máx 20 sensores; violação → HTTP 422. fim < inicio → 422.
- Leitura válida = `status_leitura = 'ok'` (lista branca). Bucket: `n_ok`, `n_falha` (status ≠ ok). Estado: `ok` (n_ok>0), `falha_instrumento` (n_ok=0, n_falha>0), `sem_dados` (ambos 0).
- `fora_limite` = `max > limite_max` ou `min < limite_min` (limite **atual**).
- Aviso de limite: "Limite alterado em DD/MM/AAAA HH:MM (de X para Y)", uma linha por alteração com data ≥ inicio do período.
- Não alterar continuous aggregates nem `listar_alarmes`/`/historico`.
- **Produção persistente:** testes só inserem/apagam linhas de sensores `SNR-SIM-*` (padrão de `api/tests/test_historico.py`). Nada apaga dados reais.
- Isolamento: todo sensor validado com `obter_sensor(cliente, code)` + `site_id = ANY(sites_permitidos)` no SQL.
- Números pt-BR (vírgula decimal) na tela e no PDF. Datas DD/MM/AAAA.
- Testes API: `cd /home/afonso/docker/odoo_sentinela && python -m pytest api/tests/<arq> -v` (precisa Timescale :5433 e Odoo de pé, como os testes atuais). Frontend: `cd frontend && npx vitest run <arq>`.

## Review Focus

1. Borda de meia-noite local: leitura às 02:30 UTC do dia 29 pertence ao dia 28 local → teste em Task 1.
2. Hora inteira só com `falha_sensor` → `falha_instrumento`, não `sem_dados`, e não altera avg → Task 1.
3. Sensor de outro cliente/site no parâmetro `sensores` → 404, sem vazar dados → Task 3.
4. Alarme iniciado antes do período e ainda aberto aparece → Task 2.
5. Sensor sem limite cadastrado → `limites: null`, sem destaque, sem quebrar gráfico/PDF → Tasks 3, 4, 6.

---

### Task 1: Agregação por bucket (`api/relatorio_dados.py`)

**Files:**
- Create: `api/relatorio_dados.py`
- Test: `api/tests/test_relatorio_dados.py`

**Interfaces:**
- Produces:
  - `TZ = 'America/Sao_Paulo'`
  - `granularidade(inicio: date, fim: date) -> Literal['hora','dia','mes']`
  - `intervalo_utc(inicio: date, fim: date) -> tuple[datetime, datetime]` (aware UTC, fim exclusivo)
  - `buscar_buckets(conn, sensor_code: str, inicio: date, fim: date, gran: str, sites_permitidos: list[str]) -> list[dict]` — cada dict: `{'bucket': datetime (aware, início local), 'avg': float|None, 'min': float|None, 'max': float|None, 'n_ok': int, 'n_falha': int, 'estado': 'ok'|'falha_instrumento'|'sem_dados'}`, ordenado, série completa.

- [ ] **Step 1: Write failing tests** (insere leituras para `SNR-SIM-TEMP-01`, site `SITE-SIM-0001`, limpa no finally como `test_historico.py`; usar datas passadas fixas, ex. 2026-01-10)
  - `test_granularidade`: `(d,d)→'hora'`, `(d, d+61)→'dia'`, `(d, d+62)→'mes'`.
  - `test_hora_retorna_24_buckets_com_sem_dados`: 1 leitura 10:15 local → 24 itens, item 10 `estado=='ok'`, demais `'sem_dados'` com `avg is None`.
  - `test_borda_meia_noite_local`: leitura em `2026-01-11 02:30 UTC` (= 10/01 23:30 local) aparece no dia 10 em `gran='dia'` para período 10–11.
  - `test_falha_excluida`: na mesma hora 20.0 ok + 0.0 `falha_sensor` → `avg==20.0`, `min==20.0`, `n_ok==1`, `n_falha==1`; outra hora só falha → `estado=='falha_instrumento'`.
  - `test_mes`: período 2026-01-10 a 2026-04-10 → 4 buckets (jan, fev, mar, abr), primeiro bucket = 2026-01-01 local.
  - `test_site_nao_permitido_retorna_sem_dados`: `sites_permitidos=['OUTRO']` → todos `sem_dados`.
- [ ] **Step 2: Run** `python -m pytest api/tests/test_relatorio_dados.py -v` → FAIL (ImportError).
- [ ] **Step 3: Implement.** SQL: `generate_series` de buckets locais (`date_trunc(<unit>, ts AT TIME ZONE TZ)` convertidos de volta com `AT TIME ZONE TZ`) LEFT JOIN em `time_bucket(<'1 hour'|'1 day'|'1 month'>, time, TZ)` sobre `sensor_reading` filtrado por `sensor_id`, `site_id = ANY(%s)`, intervalo UTC; agregados com `FILTER (WHERE status_leitura='ok')`. Para mês, buckets começam em `date_trunc('month', inicio)`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(api): relatorio bucket aggregation in local tz`

### Task 2: Dados Odoo do relatório (`api/relatorio_odoo.py`)

**Files:**
- Create: `api/relatorio_odoo.py`
- Test: `api/tests/test_relatorio_odoo.py`

**Interfaces:**
- Consumes: `odoo_cliente.executar`, `api.alarmes._serializar_evento` (reusar formato; ler `listar_alarmes` em `api/alarmes.py` para nomes de model/campos).
- Produces:
  - `alarmes_periodo(cliente, sensor_code: str, inicio_utc: datetime, fim_utc: datetime) -> list[dict]` — mesmo formato de item de `/alarmes`; domínio de sobreposição: `timestamp_deteccao < fim` E (`timestamp_resolucao` vazio OU `>= inicio`); sem `limit`; ordenado por detecção.
  - `alteracoes_limite(cliente, sensor_code: str, desde_utc: datetime) -> list[dict]` — `{'quando': datetime aware UTC, 'campo': 'limite_min'|'limite_max', 'de': float, 'para': float}` lidos de `mail.tracking.value` (via `mail.message` com `model='sensor_monitor.alarm.threshold'`, `res_id` = threshold do sensor; confirmar nomes dos campos de tracking no Odoo 16: `old_value_float`/`new_value_float`, `field`/`field_id`), ordenado.
  - `nome_emissor(cliente) -> str` — `"<name> (<login>)"` do usuário da sessão (`res.users` `read` do uid do cliente).
- [ ] **Step 1: Write failing tests** (usam Odoo real como `test_alarmes.py`/`tenant_fixtures`; criar e remover registros próprios de teste):
  - `test_alarme_aberto_antes_do_periodo_aparece`
  - `test_alarme_resolvido_antes_do_periodo_nao_aparece`
  - `test_alteracoes_limite_retorna_mudanca`: escrever `limite_max` 30→35 num threshold de teste → item `campo=='limite_max'`, `de==30.0`, `para==35.0`.
  - `test_nome_emissor_contem_login`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(api): relatorio odoo data (alarms overlap, limit history)`

### Task 3: Endpoint JSON `GET /relatorio` (`api/relatorio.py`)

**Files:**
- Create: `api/relatorio.py`
- Modify: `api/main.py` (include_router)
- Test: `api/tests/test_relatorio_router.py`

**Interfaces:**
- Consumes: Task 1, Task 2, `obter_sensor`, `obter_threshold`, `obter_sites_permitidos`, `get_cliente_usuario`, `verificar_token`.
- Produces:
  - `montar_relatorio(cliente, sensores: list[str], inicio: date, fim: date) -> dict` (reusado pelo PDF)
  - `GET /relatorio?sensores=A,B&inicio=YYYY-MM-DD&fim=YYYY-MM-DD` → 
    ```json
    {"inicio":"2026-01-10","fim":"2026-01-10","granularidade":"hora","fuso":"America/Sao_Paulo",
     "emitido_em":"<iso>","emissor":"Nome (login)",
     "sensores":[{"sensor_code":"...","nome":"...","unidade":"...","site":"...",
       "limites":{"limite_min":2.0,"limite_max":8.0}|null,
       "alteracoes_limite":[{"quando":"<iso>","campo":"limite_max","de":30.0,"para":35.0}],
       "buckets":[{"bucket":"<iso local>","avg":..,"min":..,"max":..,"n_ok":..,"n_falha":..,"estado":"ok","fora_limite":false}],
       "alarmes":[...]}]}
    ```
    (campos `nome/unidade/site` vindos de `obter_sensor` — ver `_serializar_sensor`.)
- [ ] **Step 1: Write failing tests:** 200 com formato acima para 1 dia/`SNR-SIM-TEMP-01`; `fora_limite` true quando max>limite_max; 422 para 21 sensores, para 367 dias, para fim<inicio; 404 para sensor inexistente/de outro tenant (usar `tenant_fixtures.criar_tenant`); sensor sem threshold → `limites is None` e todos `fora_limite False`; 401 sem token.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS (+ `python -m pytest api/tests -q` sem regressão nova).
- [ ] **Step 5: Commit** `feat(api): GET /relatorio period report JSON`

### Task 4: PDF `GET /relatorio.pdf` (`api/relatorio_pdf.py`)

**Files:**
- Create: `api/relatorio_pdf.py`
- Modify: `api/relatorio.py` (rota), `api/requirements.txt` (`reportlab>=4.0`)
- Test: `api/tests/test_relatorio_pdf.py`

**Interfaces:**
- Consumes: `montar_relatorio` (Task 3).
- Produces: `gerar_pdf(relatorio: dict, cliente_nome: str) -> bytes`; rota `GET /relatorio.pdf` (mesmos params) → `application/pdf`, `Content-Disposition: attachment; filename="relatorio_<cliente-slug>_<inicio>_<fim>.pdf"`.
- Conteúdo: A4 retrato; cabeçalho (cliente, período DD/MM/AAAA–DD/MM/AAAA, granularidade, fuso, emitido em, emissor); por sensor: título (nome, código, site, unidade, limites ou "sem limite cadastrado"), avisos de alteração de limite, gráfico (reportlab.graphics: linha avg, área min–max, linhas tracejadas de limite; buckets sem dados como quebra da linha), tabela (Período | Média | Mín | Máx | Leituras | Falhas), linhas fora do limite com fundo destacado, `sem_dados`/`falha_instrumento` escritos por extenso, lista de alarmes; rodapé "Página X de Y".
- [ ] **Step 1: Write failing tests:** `gerar_pdf` com dict sintético (2 sensores, um sem limites, um com alteração de limite) → bytes começam com `%PDF`; texto extraído (usar `pypdf` só em teste se disponível, senão checar com `reportlab` + busca de strings não-comprimidas desligando compressão via parâmetro `compress=False`) contém "Limite alterado em", "Sem dados", "Página 1 de"; rota retorna 200, content-type pdf, filename com datas.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (rebuild da imagem da API: `docker compose build api` se rodar em container). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(api): relatorio PDF export`

### Task 5: Frontend reportApi

**Files:**
- Modify: `frontend/src/lib/api/contracts.ts`, `frontend/src/lib/api/index.ts`
- Create: `frontend/src/lib/api/real/reportApi.ts`, `frontend/src/lib/api/mock/reportApi.ts`, `frontend/src/lib/api/real/reportApi.test.ts`
- Modify (se necessário): `frontend/src/lib/api/real/http.ts` — add `authFetchBlob(path): Promise<Blob>` mesmo padrão de `authFetchJson`.

**Interfaces:**
- Produces: tipos `Report`, `ReportSensor`, `ReportBucket`, `Granularidade` espelhando JSON da Task 3; `ReportApi { getReport(p: ReportParams): Promise<Report>; getReportPdf(p: ReportParams): Promise<Blob> }`, `ReportParams { sensores: string[]; inicio: string; fim: string }`; exportado como `reportApi` em `index.ts` seguindo mock/real existente. Mock gera buckets plausíveis conforme granularidade (inclui um `sem_dados` e um `fora_limite`).
- [ ] **Step 1: Tests:** real chama `/relatorio?sensores=A%2CB&inicio=...&fim=...` com Bearer; `getReportPdf` chama `/relatorio.pdf?...` e devolve Blob.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(frontend): report api client`

### Task 6: Tela `/relatorios`

**Files:**
- Create: `frontend/src/pages/RelatoriosPage.tsx`, `frontend/src/pages/RelatoriosPage.test.tsx`, `frontend/src/components/reportChartOption.ts`, `frontend/src/components/reportChartOption.test.ts`
- Modify: `frontend/src/App.tsx` (rota dentro do `AuthGuard`), `frontend/src/components/Topbar.tsx` (link "Relatórios")

**Interfaces:**
- Consumes: `reportApi`, `metaApi` (lista de sensores), `useECharts`, design system AFR existente (ver `DESIGN.md`, componentes em `components/select`).
- Produces: `buildReportChartOption(s: ReportSensor, gran: Granularidade): EChartsOption` — série linha `avg` (null em buckets não-ok → gap, `connectNulls:false`), área min–max (stack de `min` e `max-min`, sem `appendData`), `markLine` para limites quando houver.
- Tela: filtros data início/fim (`<input type="date">`, default hoje), multi-seleção de sensores, botão "Gerar"; por sensor: título, avisos de limite, gráfico, tabela com destaque `fora_limite`, textos "Sem dados"/"Falha de instrumento", lista de alarmes; botões **Baixar PDF** (blob → `<a download>`) e **Imprimir** (blob → `window.open(URL.createObjectURL)`); estado de carregamento/erro (mostrar mensagem 422 da API).
- [ ] **Step 1: Tests:** `reportChartOption`: avg null onde `estado!=='ok'`; markLine ausente com `limites null`. Page (mock api): gera relatório e mostra 24 linhas para mesmo dia; linha fora do limite tem marcador acessível (ex. `aria-label="fora do limite"`); "Limite alterado em" visível; clicar Baixar PDF chama `getReportPdf` com params atuais.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `npx vitest run` (suite inteira) + `npx tsc -b` → PASS.
- [ ] **Step 5: Commit** `feat(frontend): relatorios page with chart, table and pdf`

### Task 7: Verificação ponta a ponta

- [ ] Subir API de teste e frontend via `~/.claude/bin/devserver` (nunca nohup/pkill), modo mock e real.
- [ ] Playwright: gerar relatório de 1 dia, 10 dias e 6 meses para sensor real com dados; screenshot; baixar PDF e abrir (Read do PDF) conferindo conteúdo.
- [ ] Conferir 1 bucket manualmente: `SELECT avg(valor) ... WHERE status_leitura='ok' AND time >= '<dia> 10:00-03' AND time < '<dia> 11:00-03'` == valor da tabela.
- [ ] Sem deploy em prod nesta task (pedir ao usuário).
