# Backfill de Histórico Sintético da Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** As janelas 24h/7d/30d do gráfico de detalhe do sensor não mudam de escala na demo porque o `simulador_continuo.py` só gera leituras a partir de "agora" — com a demo rodando há menos de 1h, o histórico bruto (`sensor_reading`) só cobre essa janela curta, e os continuous aggregates (`sensor_reading_hourly`/`sensor_reading_daily`) que alimentam essas janelas maiores (ver `api/historico.py`) estão quase vazios (confirmado: 9 buckets horários, 0 diários). Este plano adiciona um script de backfill que insere ~30 dias de histórico sintético para os 8 sensores da demo e atualiza manualmente os continuous aggregates sobre esse range (a policy automática do Timescale só olha para uma janela recente — `[now-3h, now-1h]` no hourly, `[now-3d, now-1d]` no daily — e nunca alcançaria dados inseridos retroativamente).

**Architecture:** Um script novo, `ingestao/backfill_demo.py`, reaproveita a lista `SENSORES` já definida em `ingestao/simulador_continuo.py` (mesmos 8 sensores, mesmas faixas) e a função `timescale.inserir_leituras` já existente. Gera pontos sintéticos (senoide + ruído, mesmo estilo do `simulador_continuo.gerar_leitura`) num intervalo fixo ao longo de `--dias` dias, terminando 1h antes de "agora" (para nunca sobrepor as leituras ao vivo do simulador contínuo). Antes de inserir, limpa qualquer backfill anterior no mesmo range (idempotente — pode rodar de novo sem duplicar). Depois de inserir, chama `CALL refresh_continuous_aggregate(...)` manualmente (fora de transação, como já feito em `api/tests/test_historico.py`) para materializar os buckets `hourly`/`daily` sobre o range inteiro do backfill.

**Tech Stack:** Python 3.9, psycopg2 (via `ingestao.timescale`), pytest (testes de integração contra o TimescaleDB real — este projeto não mocka o banco, ver `ingestao/tests/test_timescale.py`).

## Global Constraints

- Não sobrepor as leituras ao vivo do simulador contínuo: o backfill nunca escreve na última 1h (`fim = agora - timedelta(hours=1)`).
- Idempotente: rodar o script duas vezes não deve duplicar linhas — limpar o range do backfill antes de reinserir.
- Reusar `SENSORES` de `ingestao/simulador_continuo.py` — não duplicar a lista de sensores/faixas.
- Testes de integração usam o DSN real (`postgresql://sentinela:sentinela@localhost:5433/sentinela`, mesmo padrão de `ingestao/tests/test_timescale.py`), com limpeza no `finally`.

---

### Task 1: Script de backfill + testes de integração

**Files:**
- Create: `ingestao/backfill_demo.py`
- Test: `ingestao/tests/test_backfill_demo.py`

**Interfaces:**
- Consumes: `ingestao.timescale.conectar(dsn)`, `ingestao.timescale.inserir_leituras(conn, site_id, coletor_id, leituras)` (já existentes); `ingestao.simulador_continuo.SENSORES` (lista de tuplas `(sensor_id, area_id, tipo_medida, unidade, (faixa_min, faixa_max))`, já existente).
- Produces: `gerar_historico(dias, intervalo_minutos, agora=None) -> list[dict]`, `limpar_backfill(conn, dias, agora=None) -> None`, `refrescar_agregados(conn, dias, agora=None) -> None`, `main()` (CLI). Nenhuma outra task consome estas funções — é a única task deste plano.

- [ ] **Step 1: Escrever os testes de integração (falhando)**

Criar `ingestao/tests/test_backfill_demo.py`:

```python
from datetime import datetime, timedelta, timezone

from ingestao import timescale, backfill_demo

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'


def _limpar_todos_sensores(conn):
    sensor_ids = [s[0] for s in backfill_demo.SENSORES]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sensor_reading WHERE sensor_id = ANY(%s)", (sensor_ids,))
    conn.commit()


def test_gerar_historico_cobre_todos_sensores_dentro_do_range_pedido():
    agora = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
    leituras = backfill_demo.gerar_historico(dias=2, intervalo_minutos=60, agora=agora)

    sensor_ids_esperados = {s[0] for s in backfill_demo.SENSORES}
    assert {l['sensor_id'] for l in leituras} == sensor_ids_esperados

    por_sensor = [l for l in leituras if l['sensor_id'] == backfill_demo.SENSORES[0][0]]
    # janela meia-aberta [agora-2d, agora-1h), passo de 1h -> 47 pontos
    assert len(por_sensor) == 47
    assert all(l['timestamp'] >= agora - timedelta(days=2) for l in por_sensor)
    assert all(l['timestamp'] < agora - timedelta(hours=1) for l in por_sensor)
    # dentro da faixa configurada do sensor (com folga pro ruido gaussiano)
    faixa = backfill_demo.SENSORES[0][4]
    margem = (faixa[1] - faixa[0]) * 0.5
    assert all(faixa[0] - margem <= l['valor'] <= faixa[1] + margem for l in por_sensor)


def test_limpar_backfill_remove_so_o_range_do_backfill_preserva_fora_dele():
    conn = timescale.conectar(DSN)
    _limpar_todos_sensores(conn)
    agora = datetime.now(timezone.utc)
    sensor_id = backfill_demo.SENSORES[0][0]
    try:
        dentro = {
            'timestamp': agora - timedelta(days=1), 'sensor_id': sensor_id,
            'area_id': backfill_demo.SENSORES[0][1], 'tipo_medida': backfill_demo.SENSORES[0][2],
            'valor': 20.0, 'unidade': backfill_demo.SENSORES[0][3],
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
        }
        fora = {**dentro, 'timestamp': agora - timedelta(minutes=10)}  # dentro da ultima 1h, fora do range do backfill
        timescale.inserir_leituras(conn, 'SITE-DEMO-01', 'COL-DEMO-01', [dentro, fora])

        backfill_demo.limpar_backfill(conn, dias=30, agora=agora)

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM sensor_reading WHERE sensor_id = %s", (sensor_id,))
            (restantes,) = cur.fetchone()
        assert restantes == 1  # so' a leitura 'fora' (ultima 1h) sobrevive
    finally:
        _limpar_todos_sensores(conn)
        conn.close()


def test_refrescar_agregados_materializa_bucket_horario_para_o_range_do_backfill():
    conn = timescale.conectar(DSN)
    _limpar_todos_sensores(conn)
    agora = datetime.now(timezone.utc)
    sensor_id = backfill_demo.SENSORES[0][0]
    try:
        leitura = {
            'timestamp': agora - timedelta(days=5), 'sensor_id': sensor_id,
            'area_id': backfill_demo.SENSORES[0][1], 'tipo_medida': backfill_demo.SENSORES[0][2],
            'valor': 21.5, 'unidade': backfill_demo.SENSORES[0][3],
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
        }
        timescale.inserir_leituras(conn, 'SITE-DEMO-01', 'COL-DEMO-01', [leitura])

        backfill_demo.refrescar_agregados(conn, dias=30, agora=agora)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT avg(valor_avg) FROM sensor_reading_hourly WHERE sensor_id = %s "
                "AND bucket = date_trunc('hour', %s::timestamptz)",
                (sensor_id, leitura['timestamp']),
            )
            resultado = cur.fetchone()
        assert resultado is not None and resultado[0] == 21.5
    finally:
        _limpar_todos_sensores(conn)
        conn.close()
```

- [ ] **Step 2: Rodar os testes e confirmar falha**

Run: `python -m pytest ingestao/tests/test_backfill_demo.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'ingestao.backfill_demo'` (ou `AttributeError`, já que o módulo ainda não existe).

- [ ] **Step 3: Implementar o script de backfill**

Criar `ingestao/backfill_demo.py`:

```python
import argparse
import math
import random
from datetime import datetime, timedelta, timezone

from . import timescale
from .simulador_continuo import SENSORES

SITE_ID = 'SITE-DEMO-01'
COLETOR_ID = 'COL-DEMO-01'


def _gerar_leitura_historica(sensor_id, area_id, tipo_medida, unidade, faixa, ts):
    meio = (faixa[0] + faixa[1]) / 2
    amplitude = (faixa[1] - faixa[0]) / 3
    ruido = (faixa[1] - faixa[0]) * 0.05
    fase_horas = ts.timestamp() / 3600
    valor = round(meio + amplitude * math.sin(fase_horas / 12) + random.gauss(0, ruido), 2)
    return {
        'timestamp': ts, 'sensor_id': sensor_id, 'area_id': area_id, 'tipo_medida': tipo_medida,
        'valor': valor, 'unidade': unidade, 'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
    }


def gerar_historico(dias, intervalo_minutos, agora=None):
    agora = agora or datetime.now(timezone.utc)
    inicio = agora - timedelta(days=dias)
    fim = agora - timedelta(hours=1)
    passo = timedelta(minutes=intervalo_minutos)

    leituras = []
    ts = inicio
    while ts < fim:
        for sensor_id, area_id, tipo_medida, unidade, faixa in SENSORES:
            leituras.append(_gerar_leitura_historica(sensor_id, area_id, tipo_medida, unidade, faixa, ts))
        ts += passo
    return leituras


def limpar_backfill(conn, dias, agora=None):
    agora = agora or datetime.now(timezone.utc)
    inicio = agora - timedelta(days=dias)
    fim = agora - timedelta(hours=1)
    sensor_ids = [s[0] for s in SENSORES]
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM sensor_reading WHERE sensor_id = ANY(%s) AND time >= %s AND time < %s",
            (sensor_ids, inicio, fim),
        )
    conn.commit()


def refrescar_agregados(conn, dias, agora=None):
    agora = agora or datetime.now(timezone.utc)
    inicio = agora - timedelta(days=dias, hours=1)
    fim = agora + timedelta(hours=1)
    # refresh_continuous_aggregate() do Timescale so' roda fora de bloco de
    # transacao — autocommit so' pra essa chamada, restaurado em seguida
    # (mesmo padrao de api/tests/test_historico.py).
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CALL refresh_continuous_aggregate('sensor_reading_hourly', %s, %s)", (inicio, fim))
            cur.execute("CALL refresh_continuous_aggregate('sensor_reading_daily', %s, %s)", (inicio, fim))
    finally:
        conn.autocommit = False


def main():
    parser = argparse.ArgumentParser(
        description='Backfill de historico sintetico pros sensores da demo + refresh manual dos continuous aggregates '
                     '(a policy automatica do Timescale nao alcanca dados inseridos retroativamente)',
    )
    parser.add_argument('--dsn', default='postgresql://sentinela:sentinela@localhost:5433/sentinela')
    parser.add_argument('--dias', type=int, default=30)
    parser.add_argument('--intervalo-minutos', type=int, default=15)
    args = parser.parse_args()

    conn = timescale.conectar(args.dsn)
    try:
        limpar_backfill(conn, args.dias)
        leituras = gerar_historico(args.dias, args.intervalo_minutos)
        total = timescale.inserir_leituras(conn, SITE_ID, COLETOR_ID, leituras)
        print(f"{total} leituras historicas inseridas ({args.dias} dias, {len(SENSORES)} sensores, passo {args.intervalo_minutos}min)")
        refrescar_agregados(conn, args.dias)
        print("Continuous aggregates (hourly/daily) atualizados sobre o range do backfill")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Rodar os testes e confirmar sucesso**

Run: `python -m pytest ingestao/tests/test_backfill_demo.py -v`
Expected: PASS (3/3)

- [ ] **Step 5: Rodar a suíte completa de `ingestao/`**

Run: `python -m pytest ingestao/ -v`
Expected: PASS — nenhuma regressão nos testes pré-existentes (`test_ingestor.py`, `test_odoo_cliente.py`, `test_provisionar_odoo_sim.py`, `test_registro_coletores.py`, `test_timescale.py`, `test_validador.py`).

- [ ] **Step 6: Commit**

```bash
git add ingestao/backfill_demo.py ingestao/tests/test_backfill_demo.py
git commit -m "feat: script de backfill de historico sintetico (30d) + refresh manual dos continuous aggregates"
```
