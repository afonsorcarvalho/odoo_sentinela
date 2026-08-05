# Análise Histórica — Plano A (Backend) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O endpoint `/historico` passa a aceitar intervalo arbitrário com escolha automática de resolução (raw → minuto → hora → dia → semana → mês), com estatísticas mín/máx/média exatas e sem buraco na borda mais recente.

**Architecture:** Uma escada de resolução versionada em `contrato/escada_resolucao.json` decide o bucket a partir do span. As continuous aggregates ganham agregação em tempo real (`materialized_only = false`), o agregado diário ganha `valor_count` para média ponderada nos rollups de semana/mês, e nasce uma CAgg de minuto para o degrau que hoje falta. O endpoint mantém `?window=` intacto para os widgets do dashboard.

**Tech Stack:** TimescaleDB 2.28.3 sobre PG16, FastAPI, psycopg2, pytest contra o Timescale real em `localhost:5433`.

**Spec:** `docs/superpowers/specs/2026-08-05-analise-historica-sobreposta-design.md` (Parte A)

## Global Constraints

- **Dado bruto nunca é apagado.** `sensor_reading` não é tocado por nenhuma task. As views são derivadas e re-materializam a partir dele. A stack local é produção de-facto.
- **`?window=` continua funcionando exatamente como hoje.** Os widgets do dashboard dependem dele; qualquer mudança de comportamento é regressão.
- **Guard de site em toda consulta nova.** Esta API já vazou dado entre clientes uma vez. Nenhuma query nova entra sem conferir o `site_id` do sensor contra `sites_permitidos`.
- **Fronteiras da escada num arquivo só:** `contrato/escada_resolucao.json`. Nada de tabela copiada à mão.
- `desde`/`ate` são ISO 8601 **com timezone**. Sem offset → 400.
- Teto de segurança de bucket forçado: `MAX_PONTOS = 20000`.
- Testes de integração limpam apenas os `sensor_id` sintéticos que eles mesmos inserem (convenção de `api/tests/test_timescale.py`).

## File Structure

**Criar:**

| Arquivo | Responsabilidade |
|---|---|
| `contrato/escada_resolucao.json` | Fronteiras de span de cada degrau. Fonte única, lida pelo backend e pelos testes do frontend. |
| `api/escada.py` | `escolher_bucket(span_segundos)` e metadados de cada degrau. Puro. |
| `api/tests/test_escada.py` | Fronteiras exatas, dos dois lados de cada uma. |
| `timescale/migracoes/001_escada_resolucao.sql` | Migração aplicável à base que já roda. |
| `api/tests/test_caggs.py` | Prova que a migração corrigiu o buraco de borda e que `valor_count` bate com o bruto. |

**Modificar:**

| Arquivo | Mudança |
|---|---|
| `timescale/init.sql:34-66` | Views com `materialized_only = false`, `valor_count` no diário, view de minuto nova |
| `api/timescale.py` | Consultas por intervalo e rollups |
| `api/tests/test_timescale.py` | Testes das consultas novas |
| `api/historico.py` | Parâmetros `desde`/`ate`/`bucket` |
| `api/tests/test_historico.py` | Testes do contrato novo + regressão do `window` |

## Como rodar os testes

Da raiz do repositório, com a stack de pé e o venv ativo:

```bash
source .venv/bin/activate
python -m pytest api/tests/test_escada.py api/tests/test_caggs.py \
                 api/tests/test_timescale.py api/tests/test_historico.py -q
```

A suíte inteira da api, antes de fechar cada task que toca `historico.py`:

```bash
python -m pytest api -q
```

---

### Task 1: Escada de resolução

**Files:**
- Create: `contrato/escada_resolucao.json`
- Create: `api/escada.py`
- Create: `api/tests/test_escada.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `DEGRAUS: list[dict]` — carregado do JSON, cada item `{'bucket': str, 'span_max_s': int | None}`
  - `escolher_bucket(span_segundos: float) -> str`
  - `BUCKETS_VALIDOS: set[str]`
  - `largura_segundos(bucket: str) -> int | None` — `None` para `raw`

- [ ] **Step 1: Write the failing test**

Criar `api/tests/test_escada.py`:

```python
import json
from pathlib import Path

import pytest

from api.escada import BUCKETS_VALIDOS, DEGRAUS, escolher_bucket, largura_segundos

H = 3600
D = 86400


def test_degraus_vem_do_arquivo_de_contrato():
    # A escada não pode ser hard-coded: o frontend lê o mesmo arquivo nos
    # testes dele. Duas tabelas copiadas à mão divergem em silêncio.
    bruto = json.loads(
        (Path(__file__).resolve().parents[2] / 'contrato' / 'escada_resolucao.json').read_text())
    assert DEGRAUS == bruto['degraus']


@pytest.mark.parametrize('span,esperado', [
    (60, 'raw'),
    (3 * H, 'raw'),            # fronteira: cabe ainda em raw
    (3 * H + 1, 'minuto'),     # um segundo além: desce um degrau
    (36 * H, 'minuto'),
    (36 * H + 1, 'hora'),
    (90 * D, 'hora'),
    (90 * D + 1, 'dia'),
    (5 * 365 * D, 'dia'),
    (5 * 365 * D + 1, 'semana'),
    (20 * 365 * D, 'semana'),
    (20 * 365 * D + 1, 'mes'),
    (200 * 365 * D, 'mes'),
])
def test_escolher_bucket_nas_fronteiras(span, esperado):
    assert escolher_bucket(span) == esperado


def test_span_zero_ou_negativo_cai_no_degrau_mais_fino():
    assert escolher_bucket(0) == 'raw'
    assert escolher_bucket(-10) == 'raw'


def test_buckets_validos_bate_com_os_degraus():
    assert BUCKETS_VALIDOS == {d['bucket'] for d in DEGRAUS}


def test_largura_de_cada_bucket():
    assert largura_segundos('raw') is None
    assert largura_segundos('minuto') == 60
    assert largura_segundos('hora') == 3600
    assert largura_segundos('dia') == 86400
    assert largura_segundos('semana') == 7 * 86400
    assert largura_segundos('mes') == 30 * 86400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_escada.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'api.escada'`

- [ ] **Step 3: Write minimal implementation**

Criar `contrato/escada_resolucao.json`:

```json
{
  "comentario": "Fronteiras da escada de resolucao do historico. span_max_s e o maior intervalo, em segundos, que ainda usa este degrau; null = degrau final. Cada limite e o span em que o degrau ainda cabe em ~2000 pontos por serie, dada a cadencia real de ~10s por sensor. Lido pelo backend (api/escada.py) e pelos testes do frontend (lib/escolherBucket.ts) - nao duplicar estes numeros em codigo.",
  "degraus": [
    { "bucket": "raw",    "span_max_s": 10800 },
    { "bucket": "minuto", "span_max_s": 129600 },
    { "bucket": "hora",   "span_max_s": 7776000 },
    { "bucket": "dia",    "span_max_s": 157680000 },
    { "bucket": "semana", "span_max_s": 630720000 },
    { "bucket": "mes",    "span_max_s": null }
  ]
}
```

Criar `api/escada.py`:

```python
"""Escada de resolução do histórico: span -> bucket.

As fronteiras vêm de contrato/escada_resolucao.json, não daqui. O frontend
tem a sua própria implementação (lib/escolherBucket.ts) e o teste dele lê o
mesmo arquivo — é assim que as duas não divergem.
"""
import json
from pathlib import Path

_ARQUIVO = Path(__file__).resolve().parent.parent / 'contrato' / 'escada_resolucao.json'

DEGRAUS = json.loads(_ARQUIVO.read_text())['degraus']
BUCKETS_VALIDOS = {d['bucket'] for d in DEGRAUS}

# Largura nominal de cada bucket, para estimar quantos pontos um intervalo
# produz sem precisar consultar o banco. 'mes' usa 30 dias: é estimativa de
# volume, não aritmética de calendário.
_LARGURAS = {'minuto': 60, 'hora': 3600, 'dia': 86400,
             'semana': 7 * 86400, 'mes': 30 * 86400}


def escolher_bucket(span_segundos):
    """Degrau mais fino que ainda cabe no span pedido."""
    for degrau in DEGRAUS:
        limite = degrau['span_max_s']
        if limite is None or span_segundos <= limite:
            return degrau['bucket']
    return DEGRAUS[-1]['bucket']


def largura_segundos(bucket):
    """Largura nominal do bucket; None para raw (depende da cadência do sensor)."""
    return _LARGURAS.get(bucket)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_escada.py -q`
Expected: PASS (16 testes — 12 do parametrize mais 4 avulsos)

- [ ] **Step 5: Commit**

```bash
git add contrato/escada_resolucao.json api/escada.py api/tests/test_escada.py
git commit -m "feat(api): escada de resolucao do historico a partir do contrato"
```

---

### Task 2: Migração das continuous aggregates

A task com a única operação destrutiva do plano. Leia o passo 1 inteiro antes de rodar qualquer coisa.

**Files:**
- Create: `timescale/migracoes/001_escada_resolucao.sql`
- Create: `api/tests/test_caggs.py`
- Modify: `timescale/init.sql:34-66`

**Interfaces:**
- Consumes: nada.
- Produces: as views `sensor_reading_minutely` (nova), `sensor_reading_daily` (com `valor_count`) e `sensor_reading_hourly` (com agregação em tempo real), todas com `materialized_only = false`.

- [ ] **Step 1: Registrar o estado atual antes de mexer**

O `sensor_reading_daily` é **derrubado e recriado**. Durante a recriação, `/historico?window=30d` devolve vazio — a stack fica de pé, mas essa rota degrada por alguns segundos. O dado bruto não é tocado; a view é reconstruída a partir dele.

```bash
docker exec odoo_sentinela-timescaledb-1 psql -U sentinela -d sentinela -c \
  "SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates;"
docker exec odoo_sentinela-timescaledb-1 psql -U sentinela -d sentinela -c \
  "SELECT (SELECT count(*) FROM sensor_reading) AS bruto,
          (SELECT count(*) FROM sensor_reading_daily) AS diario,
          (SELECT max(time) FROM sensor_reading) AS max_bruto;"
```

Anotar os três números. Duas conferências saem daí, no passo 4:

- O `count(*)` do **bruto** tem que ser idêntico — garantia de que nenhum dado real se perdeu.
- O `count(*)` do **diário** tem que voltar **maior ou igual** ao anotado. Hoje são 28 linhas de uma view 10 dias defasada; depois do `refresh_continuous_aggregate(..., NULL, NULL)` ele cobre até o presente, então tem que crescer. Se voltar **menor**, o refresh não cobriu o intervalo inteiro e os rollups de semana e mês vão sub-reportar em silêncio — exatamente a classe de erro que o `valor_count` existe para evitar. Nesse caso, pare e reporte.

- [ ] **Step 2: Write the failing test**

Criar `api/tests/test_caggs.py`:

```python
"""Estado das continuous aggregates depois da migração 001.

Testes de integração contra o Timescale real: não inserem nem apagam nada,
só inspecionam. Falham na base pré-migração — é o ponto.
"""
from ingestao.timescale import conectar

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'
VIEWS = ('sensor_reading_minutely', 'sensor_reading_hourly', 'sensor_reading_daily')


def _consultar(sql, params=None):
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def test_as_tres_views_existem():
    nomes = {linha[0] for linha in _consultar(
        "SELECT view_name FROM timescaledb_information.continuous_aggregates")}
    for view in VIEWS:
        assert view in nomes, f'{view} não existe — migração 001 não foi aplicada'


def test_agregacao_em_tempo_real_ligada_nas_tres():
    # materialized_only=true faz a consulta enxergar SÓ o materializado: o
    # diário estava 10 dias atrás do bruto e o gráfico parava no meio.
    linhas = _consultar(
        "SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates")
    por_view = dict(linhas)
    for view in VIEWS:
        assert por_view[view] is False, f'{view} ainda é materialized_only'


def test_diario_tem_valor_count():
    colunas = {linha[0] for linha in _consultar(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        ('sensor_reading_daily',))}
    assert 'valor_count' in colunas


def test_minutely_tem_as_quatro_estatisticas():
    colunas = {linha[0] for linha in _consultar(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        ('sensor_reading_minutely',))}
    assert {'valor_min', 'valor_max', 'valor_avg', 'valor_count'} <= colunas


def test_valor_count_do_diario_bate_com_o_bruto():
    linhas = _consultar(
        "SELECT d.sensor_id, d.bucket, d.valor_count, "
        "  (SELECT count(*) FROM sensor_reading r "
        "   WHERE r.sensor_id = d.sensor_id "
        "     AND r.time >= d.bucket AND r.time < d.bucket + INTERVAL '1 day') "
        "FROM sensor_reading_daily d ORDER BY d.bucket DESC LIMIT 5")
    assert linhas, 'sem dado no agregado diário para conferir'
    for sensor_id, bucket, contagem_view, contagem_bruto in linhas:
        assert contagem_view == contagem_bruto, f'{sensor_id} em {bucket}'


def test_sem_buraco_de_borda_em_nenhuma_view():
    # O teste que prova a correção do problema medido na spec (A.2): o bucket
    # mais recente de cada view tem que alcançar o dado mais recente do bruto.
    max_bruto = _consultar("SELECT max(time) FROM sensor_reading")[0][0]
    assert max_bruto is not None, 'sem dado bruto para comparar'
    larguras = {'sensor_reading_minutely': '1 minute',
                'sensor_reading_hourly': '1 hour',
                'sensor_reading_daily': '1 day'}
    for view, largura in larguras.items():
        fim = _consultar(
            f"SELECT max(bucket) + INTERVAL '{largura}' FROM {view}")[0][0]
        assert fim is not None, f'{view} vazia'
        assert fim >= max_bruto, (
            f'{view} para em {fim}, bruto vai até {max_bruto} — buraco de borda')
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest api/tests/test_caggs.py -q`
Expected: FAIL — `test_as_tres_views_existem` (não há `sensor_reading_minutely`), `test_agregacao_em_tempo_real_ligada_nas_tres` (as duas são `materialized_only`), `test_diario_tem_valor_count` e `test_sem_buraco_de_borda_em_nenhuma_view` (diário 10 dias atrás).

- [ ] **Step 4: Escrever e aplicar a migração**

Criar `timescale/migracoes/001_escada_resolucao.sql`:

```sql
-- Migração 001: escada de resolução do histórico.
--
-- 1. Agregação em tempo real nas três views. Com materialized_only=true (default
--    do TimescaleDB desde a 2.13) a consulta só enxerga o que já foi
--    materializado: medido em 2026-08-05, o diário estava 10 dias atrás do dado
--    bruto e o horário 3 horas. A página de análise não tem cauda ao vivo para
--    disfarçar esse buraco.
-- 2. valor_count no diário, para média ponderada exata nos rollups de semana e
--    mês: avg(valor_avg) sobre dias com contagens diferentes dá número errado.
-- 3. sensor_reading_minutely, o degrau que falta entre raw (3h) e hora.
--
-- NÃO roda dentro de transação: CREATE MATERIALIZED VIEW ... WITH
-- (timescaledb.continuous) e refresh_continuous_aggregate não são permitidos
-- em bloco transacional.
--
-- sensor_reading não é tocado em nenhum ponto.

-- (1) Horário: só liga tempo real. Nenhum rollup lê desta view, então ela não
--     precisa de valor_count e não é recriada.
ALTER MATERIALIZED VIEW sensor_reading_hourly
    SET (timescaledb.materialized_only = false);

-- (2) Diário: única view derrubada. Durante este trecho, /historico?window=30d
--     devolve vazio.
DROP MATERIALIZED VIEW IF EXISTS sensor_reading_daily CASCADE;

CREATE MATERIALIZED VIEW sensor_reading_daily
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
    sensor_id,
    time_bucket('1 day', time) AS bucket,
    min(valor) AS valor_min,
    max(valor) AS valor_max,
    avg(valor) AS valor_avg,
    count(*) AS valor_count
FROM sensor_reading
GROUP BY sensor_id, bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy('sensor_reading_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day');

CALL refresh_continuous_aggregate('sensor_reading_daily', NULL, NULL);

-- (3) Minuto: view nova, nada é derrubado.
CREATE MATERIALIZED VIEW sensor_reading_minutely
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT
    sensor_id,
    time_bucket('1 minute', time) AS bucket,
    min(valor) AS valor_min,
    max(valor) AS valor_max,
    avg(valor) AS valor_avg,
    count(*) AS valor_count
FROM sensor_reading
GROUP BY sensor_id, bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy('sensor_reading_minutely',
    start_offset => INTERVAL '1 day',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes');

CALL refresh_continuous_aggregate('sensor_reading_minutely', NULL, NULL);
```

Aplicar:

```bash
docker exec -i odoo_sentinela-timescaledb-1 psql -U sentinela -d sentinela -v ON_ERROR_STOP=1 \
  < timescale/migracoes/001_escada_resolucao.sql
```

Conferir os dois números contra os anotados no passo 1 — bruto idêntico, diário maior ou igual:

```bash
docker exec odoo_sentinela-timescaledb-1 psql -U sentinela -d sentinela -c \
  "SELECT (SELECT count(*) FROM sensor_reading) AS bruto,
          (SELECT count(*) FROM sensor_reading_daily) AS diario,
          (SELECT count(*) FROM sensor_reading_minutely) AS minutely;"
```

Se o `ALTER … SET (timescaledb.materialized_only = false)` for recusado nesta versão, **pare e reporte** — a spec prevê um fallback (span que alcança a borda cai para `raw`), mas ele muda o desenho e não deve ser improvisado dentro da task.

Atualizar `timescale/init.sql`, substituindo o bloco das linhas 34-66 pelas mesmas três definições (as duas `CREATE MATERIALIZED VIEW` com `materialized_only = false` e `valor_count`, mais a de minuto e as três políticas). Sem isso, um volume novo nasce com o schema velho e a migração nunca é aplicada nele.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest api/tests/test_caggs.py -q`
Expected: PASS (6 testes)

Rodar também a suíte que consome as views, para confirmar que `?window=` sobreviveu:

Run: `python -m pytest api/tests/test_historico.py api/tests/test_timescale.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add timescale/migracoes/001_escada_resolucao.sql timescale/init.sql api/tests/test_caggs.py
git commit -m "feat(timescale): tempo real nas CAggs, valor_count no diario e bucket de minuto"
```

---

### Task 3: Consultas por intervalo e rollups

**Files:**
- Modify: `api/timescale.py`
- Modify: `api/tests/test_timescale.py`

**Interfaces:**
- Consumes: as views da Task 2.
- Produces:
  - `VIEWS_BUCKET: dict[str, str]` — `minuto`/`hora`/`dia` → nome da view
  - `ROLLUP_INTERVALO: dict[str, str]` — `semana` → `'7 days'`, `mes` → `'1 month'`
  - `buscar_raw_intervalo(conn, sensor_code, desde, ate, sites_permitidos) -> list[dict]` — `{'time', 'valor'}`
  - `buscar_bucket(conn, sensor_code, bucket, desde, ate, sites_permitidos) -> list[dict]` — `{'bucket', 'min', 'max', 'avg', 'count'}`
  - `contar_raw(conn, sensor_code, desde, ate, sites_permitidos) -> int`

`buscar_bucket` despacha entre view direta e rollup; quem chama não precisa saber a diferença.

- [ ] **Step 1: Write the failing test**

Acrescentar a `api/tests/test_timescale.py`:

```python
from api.timescale import buscar_bucket, buscar_raw_intervalo, contar_raw

SENSOR_ROLLUP = 'SNR-ROLLUP-TEST-01'


def _limpar_rollup():
    conn = conectar(DSN)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE sensor_id = %s", (SENSOR_ROLLUP,))
        conn.commit()
    finally:
        conn.close()


def _inserir(conn, sensor_id, quando, valor, site='SITE-TEST'):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sensor_reading "
            "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, "
            " protocolo_origem, status_leitura) "
            "VALUES (%s, %s, 'COL-TEST', %s, 'AREA-TEST', 'temperatura', %s, 'C', '4-20ma', 'ok')",
            (quando, site, sensor_id, valor))


def _refrescar_diario(desde, ate):
    """Materializa o agregado diário no intervalo dado.

    Necessário porque agregação em tempo real cobre apenas o que vem DEPOIS da
    marca-d'água de materialização. Estes testes inserem dado no passado (datas
    fixas de março), que fica atrás da marca e não aparece na view até um
    refresh explícito daquele intervalo.

    refresh_continuous_aggregate não roda em bloco transacional, daí o
    autocommit numa conexão à parte.
    """
    conn = conectar(DSN)
    try:
        conn.set_session(autocommit=True)
        with conn.cursor() as cur:
            cur.execute("CALL refresh_continuous_aggregate('sensor_reading_daily', %s, %s)",
                        (desde, ate))
    finally:
        conn.close()


def test_buscar_raw_intervalo_respeita_os_dois_extremos():
    conn = conectar(DSN)
    _limpar_rollup()
    try:
        base = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        _inserir(conn, SENSOR_ROLLUP, base - timedelta(minutes=10), 1.0)
        _inserir(conn, SENSOR_ROLLUP, base, 2.0)
        _inserir(conn, SENSOR_ROLLUP, base + timedelta(minutes=10), 3.0)
        conn.commit()
        pontos = buscar_raw_intervalo(
            conn, SENSOR_ROLLUP, base - timedelta(minutes=1), base + timedelta(minutes=1),
            ['SITE-TEST'])
        assert [p['valor'] for p in pontos] == [2.0]
    finally:
        _limpar_rollup()
        conn.close()


def test_buscar_raw_intervalo_bloqueia_site_nao_permitido():
    conn = conectar(DSN)
    _limpar_rollup()
    try:
        base = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        _inserir(conn, SENSOR_ROLLUP, base, 2.0, site='SITE-OUTRO')
        conn.commit()
        assert buscar_raw_intervalo(
            conn, SENSOR_ROLLUP, base - timedelta(hours=1), base + timedelta(hours=1),
            ['SITE-TEST']) == []
    finally:
        _limpar_rollup()
        conn.close()


def test_rollup_semanal_usa_media_ponderada_nao_media_das_medias():
    # O caso que expõe a diferença: um dia com 3 leituras e outro com 1.
    # Média das médias = (2 + 10) / 2 = 6. Ponderada = (1+2+3+10)/4 = 4.
    conn = conectar(DSN)
    _limpar_rollup()
    try:
        dia1 = datetime(2026, 3, 10, 6, 0, tzinfo=timezone.utc)
        dia2 = datetime(2026, 3, 11, 6, 0, tzinfo=timezone.utc)
        for i, v in enumerate((1.0, 2.0, 3.0)):
            _inserir(conn, SENSOR_ROLLUP, dia1 + timedelta(minutes=i), v)
        _inserir(conn, SENSOR_ROLLUP, dia2, 10.0)
        conn.commit()
        _refrescar_diario(datetime(2026, 3, 9, tzinfo=timezone.utc),
                          datetime(2026, 3, 17, tzinfo=timezone.utc))

        pontos = buscar_bucket(
            conn, SENSOR_ROLLUP, 'semana',
            datetime(2026, 3, 9, tzinfo=timezone.utc),
            datetime(2026, 3, 17, tzinfo=timezone.utc), ['SITE-TEST'])
        assert len(pontos) == 1
        assert pontos[0]['count'] == 4
        assert pontos[0]['min'] == 1.0
        assert pontos[0]['max'] == 10.0
        assert abs(pontos[0]['avg'] - 4.0) < 1e-9
    finally:
        _limpar_rollup()
        conn.close()


def test_rollup_mensal_agrupa_o_mes_inteiro():
    conn = conectar(DSN)
    _limpar_rollup()
    try:
        for dia in (2, 15, 27):
            _inserir(conn, SENSOR_ROLLUP,
                     datetime(2026, 3, dia, 6, 0, tzinfo=timezone.utc), float(dia))
        conn.commit()
        _refrescar_diario(datetime(2026, 3, 1, tzinfo=timezone.utc),
                          datetime(2026, 4, 1, tzinfo=timezone.utc))
        pontos = buscar_bucket(
            conn, SENSOR_ROLLUP, 'mes',
            datetime(2026, 3, 1, tzinfo=timezone.utc),
            datetime(2026, 4, 1, tzinfo=timezone.utc), ['SITE-TEST'])
        assert len(pontos) == 1
        assert pontos[0]['count'] == 3
    finally:
        _limpar_rollup()
        conn.close()


def test_buscar_bucket_bloqueia_site_nao_permitido_tambem_no_rollup():
    conn = conectar(DSN)
    _limpar_rollup()
    try:
        base = datetime(2026, 3, 10, 6, 0, tzinfo=timezone.utc)
        _inserir(conn, SENSOR_ROLLUP, base, 5.0, site='SITE-OUTRO')
        conn.commit()
        _refrescar_diario(datetime(2026, 3, 9, tzinfo=timezone.utc),
                          datetime(2026, 3, 17, tzinfo=timezone.utc))
        assert buscar_bucket(
            conn, SENSOR_ROLLUP, 'semana',
            datetime(2026, 3, 9, tzinfo=timezone.utc),
            datetime(2026, 3, 17, tzinfo=timezone.utc), ['SITE-TEST']) == []
    finally:
        _limpar_rollup()
        conn.close()


def test_buscar_bucket_recusa_bucket_desconhecido():
    conn = conectar(DSN)
    try:
        with pytest.raises(ValueError):
            buscar_bucket(conn, SENSOR_ROLLUP, 'quinzena',
                          datetime(2026, 3, 1, tzinfo=timezone.utc),
                          datetime(2026, 4, 1, tzinfo=timezone.utc), ['SITE-TEST'])
    finally:
        conn.close()


def test_contar_raw_conta_so_dentro_do_intervalo():
    conn = conectar(DSN)
    _limpar_rollup()
    try:
        base = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        for i in range(5):
            _inserir(conn, SENSOR_ROLLUP, base + timedelta(minutes=i), float(i))
        conn.commit()
        assert contar_raw(conn, SENSOR_ROLLUP, base, base + timedelta(minutes=2),
                          ['SITE-TEST']) == 3
    finally:
        _limpar_rollup()
        conn.close()
```

Acrescentar `import pytest` no topo de `api/tests/test_timescale.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_timescale.py -q`
Expected: FAIL com `ImportError: cannot import name 'buscar_bucket'`

- [ ] **Step 3: Write minimal implementation**

Acrescentar a `api/timescale.py`:

```python
# Buckets servidos direto por uma continuous aggregate.
VIEWS_BUCKET = {
    'minuto': 'sensor_reading_minutely',
    'hora': 'sensor_reading_hourly',
    'dia': 'sensor_reading_daily',
}

# Buckets derivados do agregado diário por rollup. Semana e mês não têm view
# própria: materializar mais duas para 156 e 36 linhas/ano não se paga.
ROLLUP_INTERVALO = {'semana': '7 days', 'mes': '1 month'}


def _site_permitido(conn, sensor_code, sites_permitidos):
    """Sensor pertence a um site que o usuário pode ver.

    Mesmo guard de buscar_agregado. As views agregadas não carregam site_id,
    então a checagem tem que vir do bruto — sem ela, qualquer consulta nova
    vira vazamento entre clientes.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT site_id FROM sensor_reading WHERE sensor_id = %s LIMIT 1",
                    (sensor_code,))
        linha = cur.fetchone()
    return linha is not None and linha[0] in sites_permitidos


def buscar_raw_intervalo(conn, sensor_code, desde, ate, sites_permitidos):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT time, valor FROM sensor_reading "
            "WHERE sensor_id = %s AND time >= %s AND time <= %s AND site_id = ANY(%s) "
            "ORDER BY time",
            (sensor_code, desde, ate, sites_permitidos),
        )
        linhas = cur.fetchall()
    return [{'time': linha[0], 'valor': linha[1]} for linha in linhas]


def contar_raw(conn, sensor_code, desde, ate, sites_permitidos):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM sensor_reading "
            "WHERE sensor_id = %s AND time >= %s AND time <= %s AND site_id = ANY(%s)",
            (sensor_code, desde, ate, sites_permitidos),
        )
        return cur.fetchone()[0]


def buscar_bucket(conn, sensor_code, bucket, desde, ate, sites_permitidos):
    """Série agregada no bucket pedido, entre desde e ate.

    Despacha entre view direta (minuto/hora/dia) e rollup do diário
    (semana/mês); quem chama não precisa saber a diferença.
    """
    if bucket in VIEWS_BUCKET:
        if not _site_permitido(conn, sensor_code, sites_permitidos):
            return []
        view = VIEWS_BUCKET[bucket]
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT bucket, valor_min, valor_max, valor_avg, valor_count FROM {view} "
                "WHERE sensor_id = %s AND bucket >= %s AND bucket <= %s ORDER BY bucket",
                (sensor_code, desde, ate),
            )
            linhas = cur.fetchall()
    elif bucket in ROLLUP_INTERVALO:
        if not _site_permitido(conn, sensor_code, sites_permitidos):
            return []
        intervalo = ROLLUP_INTERVALO[bucket]
        with conn.cursor() as cur:
            # Média ponderada por valor_count: avg(valor_avg) daria número
            # errado quando os dias têm quantidade diferente de leitura
            # (sensor offline parte do dia).
            cur.execute(
                f"SELECT time_bucket(INTERVAL '{intervalo}', bucket) AS janela, "
                "       min(valor_min), max(valor_max), "
                "       sum(valor_avg * valor_count) / nullif(sum(valor_count), 0), "
                "       sum(valor_count) "
                "FROM sensor_reading_daily "
                "WHERE sensor_id = %s AND bucket >= %s AND bucket <= %s "
                "GROUP BY janela ORDER BY janela",
                (sensor_code, desde, ate),
            )
            linhas = cur.fetchall()
    else:
        raise ValueError(f'bucket desconhecido: {bucket}')

    return [
        {'bucket': l[0], 'min': l[1], 'max': l[2], 'avg': l[3], 'count': int(l[4] or 0)}
        for l in linhas
    ]
```

Nota sobre o f-string no SQL: `view` e `intervalo` vêm de dicionários fechados no módulo, nunca do usuário — mesmo padrão já usado por `buscar_agregado`, que valida contra `TABELAS_AGREGADO`. O `bucket` do usuário é conferido contra as chaves antes de chegar aqui, e qualquer valor fora delas levanta `ValueError`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_timescale.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/timescale.py api/tests/test_timescale.py
git commit -m "feat(api): consultas por intervalo e rollup ponderado de semana/mes"
```

---

### Task 4: Endpoint `/historico` com intervalo e bucket

**Files:**
- Modify: `api/historico.py`
- Modify: `api/tests/test_historico.py`

**Interfaces:**
- Consumes: `escolher_bucket`, `largura_segundos`, `BUCKETS_VALIDOS` (Task 1); `buscar_raw_intervalo`, `buscar_bucket`, `contar_raw` (Task 3).
- Produces: contrato HTTP consumido pelo Plano B.

- [ ] **Step 1: Write the failing test**

Acrescentar a `api/tests/test_historico.py`:

```python
def _inserir_serie(conn, sensor_id, base, quantos, passo_min=1):
    with conn.cursor() as cur:
        for i in range(quantos):
            cur.execute(
                "INSERT INTO sensor_reading "
                "(time, site_id, coletor_id, sensor_id, area_id, tipo_medida, valor, unidade, "
                " protocolo_origem, status_leitura) "
                "VALUES (%s, 'SITE-SIM-0001', 'COL-SIM-0001', %s, 'AREA-SIM-EXPURGO', "
                "        'temperatura', %s, 'C', '4-20ma', 'ok')",
                (base + timedelta(minutes=i * passo_min), sensor_id, 20.0 + i))
    conn.commit()


def test_window_continua_igual_ao_de_antes():
    # Regressão: os widgets do dashboard dependem deste contrato.
    conn = conectar(DSN)
    _limpar()
    try:
        _inserir_serie(conn, SENSOR_CODE, datetime.now(timezone.utc) - timedelta(minutes=30), 3)
        resposta = client.get(f'/sensores/{SENSOR_CODE}/historico',
                              params={'window': '1h'}, headers=_headers())
        corpo = resposta.json()
        assert resposta.status_code == 200
        assert corpo['window'] == '1h'
        assert corpo['resolution'] == 'raw'
        assert all('value' in p for p in corpo['points'])
    finally:
        _limpar()
        conn.close()


def test_intervalo_curto_resolve_para_raw():
    conn = conectar(DSN)
    _limpar()
    try:
        base = datetime.now(timezone.utc) - timedelta(hours=1)
        _inserir_serie(conn, SENSOR_CODE, base, 5)
        resposta = client.get(
            f'/sensores/{SENSOR_CODE}/historico',
            params={'desde': base.isoformat(), 'ate': (base + timedelta(hours=1)).isoformat(),
                    'bucket': 'auto'},
            headers=_headers())
        corpo = resposta.json()
        assert resposta.status_code == 200
        assert corpo['bucket'] == 'raw'
        assert corpo['resolution'] == 'raw'
        assert len(corpo['points']) == 5
    finally:
        _limpar()
        conn.close()


def test_intervalo_de_uma_semana_resolve_para_hora():
    conn = conectar(DSN)
    _limpar()
    try:
        ate = datetime.now(timezone.utc)
        desde = ate - timedelta(days=7)
        _inserir_serie(conn, SENSOR_CODE, ate - timedelta(hours=2), 3)
        resposta = client.get(
            f'/sensores/{SENSOR_CODE}/historico',
            params={'desde': desde.isoformat(), 'ate': ate.isoformat(), 'bucket': 'auto'},
            headers=_headers())
        corpo = resposta.json()
        assert corpo['bucket'] == 'hora'
        assert corpo['resolution'] == 'agg'
        assert all({'min', 'max', 'avg', 'count'} <= set(p) for p in corpo['points'])
    finally:
        _limpar()
        conn.close()


def test_bucket_forcado_vence_o_auto():
    conn = conectar(DSN)
    _limpar()
    try:
        ate = datetime.now(timezone.utc)
        desde = ate - timedelta(hours=2)
        _inserir_serie(conn, SENSOR_CODE, desde, 5)
        resposta = client.get(
            f'/sensores/{SENSOR_CODE}/historico',
            params={'desde': desde.isoformat(), 'ate': ate.isoformat(), 'bucket': 'hora'},
            headers=_headers())
        assert resposta.json()['bucket'] == 'hora'
    finally:
        _limpar()
        conn.close()


def test_window_e_intervalo_juntos_e_400():
    agora = datetime.now(timezone.utc)
    resposta = client.get(
        f'/sensores/{SENSOR_CODE}/historico',
        params={'window': '1h', 'desde': (agora - timedelta(hours=1)).isoformat(),
                'ate': agora.isoformat()},
        headers=_headers())
    assert resposta.status_code == 400


def test_sem_window_e_sem_intervalo_e_400():
    resposta = client.get(f'/sensores/{SENSOR_CODE}/historico', headers=_headers())
    assert resposta.status_code == 400


def test_desde_maior_que_ate_e_400():
    agora = datetime.now(timezone.utc)
    resposta = client.get(
        f'/sensores/{SENSOR_CODE}/historico',
        params={'desde': agora.isoformat(), 'ate': (agora - timedelta(hours=1)).isoformat()},
        headers=_headers())
    assert resposta.status_code == 400


def test_datetime_sem_timezone_e_400():
    # Sistema roda em America/Sao_Paulo e grava em UTC: data sem fuso é erro
    # esperando acontecer, não conveniência.
    resposta = client.get(
        f'/sensores/{SENSOR_CODE}/historico',
        params={'desde': '2026-03-10T00:00:00', 'ate': '2026-03-10T06:00:00'},
        headers=_headers())
    assert resposta.status_code == 400


def test_bucket_desconhecido_e_400():
    agora = datetime.now(timezone.utc)
    resposta = client.get(
        f'/sensores/{SENSOR_CODE}/historico',
        params={'desde': (agora - timedelta(hours=1)).isoformat(), 'ate': agora.isoformat(),
                'bucket': 'quinzena'},
        headers=_headers())
    assert resposta.status_code == 400


def test_bucket_forcado_acima_do_teto_e_400_com_sugestao():
    agora = datetime.now(timezone.utc)
    resposta = client.get(
        f'/sensores/{SENSOR_CODE}/historico',
        params={'desde': (agora - timedelta(days=365 * 3)).isoformat(),
                'ate': agora.isoformat(), 'bucket': 'minuto'},
        headers=_headers())
    assert resposta.status_code == 400
    assert 'dia' in resposta.json()['detail']


def test_window_invalida_continua_422():
    # Regressão explícita: `window` é Literal no FastAPI, então valor fora da
    # lista dá 422 (validação do framework), não 400. Já existe um teste com
    # essa asserção neste arquivo; este documenta a razão.
    resposta = client.get(f'/sensores/{SENSOR_CODE}/historico',
                          params={'window': '99x'}, headers=_headers())
    assert resposta.status_code == 422


def test_sensor_inexistente_continua_404():
    agora = datetime.now(timezone.utc)
    resposta = client.get(
        '/sensores/SNR-NAO-EXISTE/historico',
        params={'desde': (agora - timedelta(hours=1)).isoformat(), 'ate': agora.isoformat()},
        headers=_headers())
    assert resposta.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_historico.py -q`
Expected: FAIL — os testes de intervalo recebem 422 do FastAPI (parâmetro `window` obrigatório).

- [ ] **Step 3: Write minimal implementation**

Substituir o corpo de `api/historico.py` (mantendo `_JANELAS` e o caminho de `window` intactos):

```python
import os
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException

from ingestao.timescale import conectar

from . import timescale as api_timescale
from .auth import get_cliente_usuario, verificar_token
from .escada import BUCKETS_VALIDOS, escolher_bucket, largura_segundos
from .meta import obter_sensor
from .permissions import obter_sites_permitidos

router = APIRouter()

DSN = os.environ.get('TIMESCALE_DSN', 'postgresql://sentinela:sentinela@localhost:5433/sentinela')

MAX_PONTOS = int(os.environ.get('HISTORICO_MAX_PONTOS', '20000'))

_JANELAS = {
    '1h': {'resolution': 'raw', 'delta': timedelta(hours=1)},
    '24h': {'resolution': 'agg', 'tabela': 'sensor_reading_hourly', 'delta': timedelta(hours=24)},
    '7d': {'resolution': 'agg', 'tabela': 'sensor_reading_hourly', 'delta': timedelta(days=7)},
    '30d': {'resolution': 'agg', 'tabela': 'sensor_reading_daily', 'delta': timedelta(days=30)},
}


def _parse_instante(valor, nome):
    try:
        instante = datetime.fromisoformat(valor)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"'{nome}' não é ISO 8601: {valor}")
    if instante.tzinfo is None:
        raise HTTPException(
            status_code=400,
            detail=f"'{nome}' precisa de timezone (ex.: 2026-07-29T03:00:00Z)")
    return instante


def _resposta_window(sensor_code, window, sites_permitidos):
    """Caminho legado, byte-a-byte igual ao de antes — os widgets dependem dele."""
    config = _JANELAS[window]
    desde = datetime.now(timezone.utc) - config['delta']
    conn = conectar(DSN)
    try:
        if config['resolution'] == 'raw':
            linhas = api_timescale.buscar_raw(conn, sensor_code, desde, sites_permitidos)
            points = [{'ts': int(l['time'].timestamp() * 1000), 'value': l['valor']} for l in linhas]
        else:
            linhas = api_timescale.buscar_agregado(
                conn, sensor_code, config['tabela'], desde, sites_permitidos)
            points = [
                {'ts': int(l['bucket'].timestamp() * 1000),
                 'min': l['min'], 'max': l['max'], 'avg': l['avg']}
                for l in linhas
            ]
    finally:
        conn.close()
    return {'sensor_code': sensor_code, 'window': window,
            'resolution': config['resolution'], 'points': points}


@router.get('/sensores/{sensor_code}/historico')
def get_historico(
    sensor_code: str,
    # Literal, não str: `test_historico_window_invalida_retorna_422` depende do
    # 422 que o FastAPI gera sozinho para window fora da lista. Trocar por str
    # e validar à mão viraria 400 e quebraria esse teste.
    window: Optional[Literal['1h', '24h', '7d', '30d']] = None,
    desde: Optional[str] = None,
    ate: Optional[str] = None,
    bucket: str = 'auto',
    cliente=Depends(get_cliente_usuario),
    _claims=Depends(verificar_token),
):
    if obter_sensor(cliente, sensor_code) is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")

    sites_permitidos = obter_sites_permitidos(cliente)
    tem_intervalo = desde is not None or ate is not None

    # Dois donos do mesmo recorte é ambiguidade que vira bug silencioso.
    if window is not None and tem_intervalo:
        raise HTTPException(status_code=400, detail="use 'window' OU 'desde'/'ate', não os dois")
    if window is not None:
        return _resposta_window(sensor_code, window, sites_permitidos)
    if desde is None or ate is None:
        raise HTTPException(status_code=400, detail="informe 'window' ou 'desde' e 'ate'")

    inicio = _parse_instante(desde, 'desde')
    fim = _parse_instante(ate, 'ate')
    if inicio >= fim:
        raise HTTPException(status_code=400, detail="'desde' precisa ser anterior a 'ate'")

    span = (fim - inicio).total_seconds()
    if bucket == 'auto':
        bucket = escolher_bucket(span)
    elif bucket not in BUCKETS_VALIDOS:
        raise HTTPException(status_code=400, detail=f'bucket desconhecido: {bucket}')
    else:
        # Teto de segurança de quem forçou o degrau na mão: recusar com o
        # bucket certo no corpo é melhor do que devolver 2 milhões de pontos
        # e travar o browser.
        largura = largura_segundos(bucket)
        if largura is not None and span / largura > MAX_PONTOS:
            raise HTTPException(
                status_code=400,
                detail=(f"bucket '{bucket}' geraria mais de {MAX_PONTOS} pontos neste "
                        f"intervalo; use '{escolher_bucket(span)}'"))

    conn = conectar(DSN)
    try:
        if bucket == 'raw':
            total = api_timescale.contar_raw(conn, sensor_code, inicio, fim, sites_permitidos)
            if total > MAX_PONTOS:
                raise HTTPException(
                    status_code=400,
                    detail=(f'intervalo tem {total} leituras cruas, acima de {MAX_PONTOS}; '
                            f"use '{escolher_bucket(span)}'"))
            linhas = api_timescale.buscar_raw_intervalo(
                conn, sensor_code, inicio, fim, sites_permitidos)
            resolution = 'raw'
            points = [{'ts': int(l['time'].timestamp() * 1000), 'value': l['valor']} for l in linhas]
        else:
            linhas = api_timescale.buscar_bucket(
                conn, sensor_code, bucket, inicio, fim, sites_permitidos)
            resolution = 'agg'
            points = [
                {'ts': int(l['bucket'].timestamp() * 1000), 'min': l['min'],
                 'max': l['max'], 'avg': l['avg'], 'count': l['count']}
                for l in linhas
            ]
    finally:
        conn.close()

    return {'sensor_code': sensor_code, 'desde': inicio.isoformat(), 'ate': fim.isoformat(),
            'bucket': bucket, 'resolution': resolution, 'points': points}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_historico.py -q`
Expected: PASS

Suíte inteira da api, para confirmar que nada mais consumia o contrato antigo:

Run: `python -m pytest api -q`
Expected: PASS

- [ ] **Step 5: Verificar o contrato por curl contra a stack real**

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"usuario":"admin","senha":"admin"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# Auto deve resolver para minuto num span de ~12h
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/sensores/SNR-E2E-CH1/historico?desde=$(date -u -d '12 hours ago' +%Y-%m-%dT%H:%M:%SZ)&ate=$(date -u +%Y-%m-%dT%H:%M:%SZ)&bucket=auto" \
  | python -c 'import sys,json; c=json.load(sys.stdin); print(c["bucket"], c["resolution"], len(c["points"]), c["points"][-1] if c["points"] else None)'
```
Expected: `minuto agg <n> {...}` com `n` na casa das centenas e o último ponto **alcançando a hora atual** — é a prova prática de que o buraco de materialização acabou.

- [ ] **Step 6: Commit**

```bash
git add api/historico.py api/tests/test_historico.py
git commit -m "feat(api): historico por intervalo com escada de resolucao automatica"
```

---

## Self-Review

**Cobertura da spec (Parte A):**

| Requisito | Task |
|---|---|
| A.1 escada de resolução, fixture única | 1 |
| A.2 agregação em tempo real nas três views | 2 |
| A.2 teste que prova a ausência de buraco de borda | 2 |
| A.3 `ALTER` no horário (sem drop) | 2 |
| A.3 diário recriado com `valor_count` | 2 |
| A.3 `sensor_reading_minutely` nova | 2 |
| A.3 `init.sql` atualizado junto | 2 |
| A.4 rollup ponderado de semana e mês | 3 |
| A.5 `desde`/`ate`/`bucket` | 4 |
| A.5 `window` inalterado | 4 (teste de regressão) |
| A.5 exclusividade `window` × intervalo → 400 | 4 |
| A.5 ISO sem timezone → 400 | 4 |
| A.5 `MAX_PONTOS` com bucket sugerido | 4 |
| Guard de site em toda consulta nova | 3 (`_site_permitido`, testado nos dois caminhos) |

**Consistência de nomes:** `escolher_bucket`/`largura_segundos`/`BUCKETS_VALIDOS` (Task 1) são importados com esses nomes na Task 4. `buscar_raw_intervalo`/`buscar_bucket`/`contar_raw` (Task 3) idem. O campo `count` aparece na resposta de `buscar_bucket` e é propagado para o JSON na Task 4.

**Sem placeholders:** todo passo de código traz o código; todo passo de teste traz comando e resultado esperado.

**Fora deste plano, por desenho:** tudo da Parte B da spec (página, chart, zoom, entradas) vai para o Plano B, que consome o contrato fechado na Task 4.
