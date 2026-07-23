# Confronto de Auditoria Timescale ↔ Arquivo Assinado (C / §5.2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Motor de **confronto de veracidade**: antes de tratar o Timescale como fonte confiável (ex. relatório com valor legal), reconciliar cada período contra os arquivos assinados — (1) assinaturas válidas (`hdr_sig` + cadeia de `sig` por linha) e (2) valores batem (`valor` do arquivo == `valor` no Timescale). Divergência em qualquer parte = alerta de auditoria.

**Architecture:** O confronto reusa o `ingestao/validador.py` v2 (Plano B, Task 5) para a parte (1) — nenhuma reimplementação de cripto. A parte (2) casa cada linha verificada do arquivo contra a linha correspondente no Timescale por `(sensor_id, timestamp_utc)`. O motor confronta **um arquivo** (unidade testável); um CLI itera os arquivos arquivados de um período. **Timescale = cache re-verificável; arquivo = fonte da verdade** — adulteração direta no Timescale é pega aqui.

**Tech Stack:** Python 3.9, `psycopg2` (via `ingestao.timescale`), `cryptography` (via `ingestao.validador`), pytest (integração contra TimescaleDB real — este projeto não mocka o banco, ver `ingestao/tests/test_timescale.py`).

## Global Constraints

- **Depende do Plano B** (schema v2): `validador.validar_arquivo` já verifica `hdr_sig` + `sig` por linha e devolve `status_validacao ∈ {valido, incompleto, invalido}` e `.leituras` com `valor`/`timestamp`/`sensor_id`. Executar este plano **depois** de B.
- Value-match com **tolerância** (`valor` é `double`/texto formatado): `abs(a - b) <= 1e-6`.
- Timestamps do arquivo são ISO com offset (`-03:00`); Timescale guarda `TIMESTAMPTZ` (UTC). Casar convertendo o ts do arquivo para UTC.
- `incompleto` (arquivo sem rodapé, mas autêntico linha-a-linha) **conta** para o confronto das linhas que tem — mas o resultado sinaliza `arquivo_nao_fechado=True` (não prova ausência de truncamento, §5.1).
- O writer de produção emite timestamps **tz-aware** (`main.py`: `agora_fn=lambda: datetime.now(tz)`), então o `timezone_offset` sempre aparece no ts do arquivo — o motor pode exigir ts aware sem quebrar produção.
- **Confronto é bidirecional:** file→Timescale pega linhas deletadas/alteradas; Timescale→file (count-match) pega linhas **injetadas** no cache sem contraparte assinada. Ambos entram no veredito.
- **Escopo:** este plano entrega o motor + CLI de confronto. O acoplamento a um gerador de relatório legal em PDF **não existe hoje** e fica fora. A verificação de "device não-revogado naquele instante" usa a pubkey **atual** do registro; histórico de revogação (§6, v2) é lacuna documentada.
- TDD, DRY, YAGNI, commits frequentes.

---

### Task 1: Query Timescale para confronto — linhas exatas por `(sensor_id, intervalo)`

**Files:**
- Modify: `ingestao/timescale.py` (nova função `buscar_leituras_para_confronto`)
- Test: `ingestao/tests/test_timescale.py`

**Interfaces:**
- Produces: `buscar_leituras_para_confronto(conn, coletor_id, ts_inicio, ts_fim) -> dict[(sensor_id, ts_utc_iso)] -> valor`. Consumido pela Task 2.

- [ ] **Step 1: Write the failing test**

Adicionar a `ingestao/tests/test_timescale.py` (segue o padrão de conexão real + limpeza dos testes existentes; ajuste o DSN/fixture conforme o arquivo):

```python
def test_buscar_leituras_para_confronto_indexa_por_sensor_e_ts():
    from datetime import datetime, timezone
    from ingestao import timescale
    conn = timescale.conectar(DSN)  # DSN já definido no módulo de teste
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE coletor_id = 'COL-CONF'")
        t = datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc)
        timescale.inserir_leituras(
            conn, 'SITE-1', 'COL-CONF',
            [{'timestamp': t, 'sensor_id': 'SNR-1', 'area_id': 'EXPURGO',
              'tipo_medida': 'temperatura', 'valor': 96.83, 'unidade': 'C',
              'protocolo_origem': '4-20ma', 'status_leitura': 'ok'}])
        mapa = timescale.buscar_leituras_para_confronto(
            conn, 'COL-CONF',
            datetime(2026, 7, 16, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc))
        assert mapa[('SNR-1', '2026-07-16T03:01:00+00:00')] == 96.83
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sensor_reading WHERE coletor_id = 'COL-CONF'")
        conn.commit()
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_timescale.py::test_buscar_leituras_para_confronto_indexa_por_sensor_e_ts -q`
Expected: FAIL — `AttributeError: module 'ingestao.timescale' has no attribute 'buscar_leituras_para_confronto'`.

- [ ] **Step 3: Write minimal implementation**

Adicionar a `ingestao/timescale.py`:

```python
def buscar_leituras_para_confronto(conn, coletor_id, ts_inicio, ts_fim):
    """Devolve {(sensor_id, ts_utc_iso): valor} das leituras de um coletor no
    intervalo [ts_inicio, ts_fim). A chave usa o timestamp em UTC ISO para casar
    com o timestamp do arquivo convertido para UTC."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sensor_id, time, valor
            FROM sensor_reading
            WHERE coletor_id = %s AND time >= %s AND time < %s
            """,
            (coletor_id, ts_inicio, ts_fim),
        )
        linhas = cur.fetchall()
    return {
        (sensor_id, time.astimezone(__import__('datetime').timezone.utc).isoformat()): valor
        for sensor_id, time, valor in linhas
    }
```

> Preferir importar `timezone` no topo do módulo (`from datetime import timezone`) e usar `time.astimezone(timezone.utc).isoformat()` — o `__import__` inline acima é só para não depender de edição do topo; ajuste para o import limpo.

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_timescale.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add ingestao/timescale.py ingestao/tests/test_timescale.py
git commit -m "feat(timescale): buscar_leituras_para_confronto indexada por sensor+ts UTC"
```

---

### Task 2: Motor de confronto de um arquivo — assinaturas + value-match

**Files:**
- Create: `ingestao/confronto.py`
- Test: `ingestao/tests/test_confronto.py`

**Interfaces:**
- Consumes: `validador.validar_arquivo` (Plano B, Task 5); `timescale.buscar_leituras_para_confronto` (Task 1).
- Produces: `confrontar_arquivo(caminho, registro_path, conn) -> ResultadoConfronto` com campos:
  `assinaturas_ok: bool`, `valores_ok: bool`, `arquivo_nao_fechado: bool`, `divergencias: list[dict]`, `motivo: str|None`, `coletor_id: str`, `data_referencia: str`.

- [ ] **Step 1: Write the failing test**

Criar `ingestao/tests/test_confronto.py`:

```python
from datetime import datetime, timezone

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import confronto, registro_coletores, timescale

DSN = 'postgresql://sentinela:sentinela@localhost:5433/sentinela'


def _leitura(ts, valor):
    return {'timestamp': ts, 'sensor_id': 'SNR-1', 'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura', 'valor': valor, 'unidade': 'C',
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
            'cert_ver': 3, 'cal_ganho': 0.965, 'cal_offset': 0.33}


def _gerar_arquivo(tmp_path, leituras=None):
    # ts SEMPRE tz-aware (UTC aqui) — o writer emite offset e o confronto exige
    # timestamp aware (_ts_utc_iso levanta em naive).
    leituras = leituras or [(datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc), 96.83)]
    assinador = AssinadorSoftware(str(tmp_path / "k.pem"))
    arq = ArquivoDiario('COL-CONF', 'HUB-1', '2.3.1', '+00:00', str(tmp_path / "d"),
                        assinador, cliente_id='CLI-1', site_id='SITE-1')
    for ts, valor in leituras:
        arq.registrar(_leitura(ts, valor))
    arq.selar('2026-07-16')
    registro = str(tmp_path / "reg.json")
    registro_coletores.registrar_coletor(registro, 'COL-CONF', assinador.chave_publica_pem())
    return arq.caminho('2026-07-16'), registro


def _limpar(conn):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sensor_reading WHERE coletor_id = 'COL-CONF'")
    conn.commit()


def test_confronto_ok_quando_assinaturas_e_valores_batem(tmp_path):
    caminho, registro = _gerar_arquivo(tmp_path)
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        timescale.inserir_leituras(
            conn, 'SITE-1', 'COL-CONF',
            [{'timestamp': datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc),
              'sensor_id': 'SNR-1', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
              'valor': 96.83, 'unidade': 'C', 'protocolo_origem': '4-20ma',
              'status_leitura': 'ok'}])
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.assinaturas_ok is True
        assert r.valores_ok is True
        assert r.divergencias == []
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_detecta_valor_adulterado_no_timescale(tmp_path):
    caminho, registro = _gerar_arquivo(tmp_path)
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        timescale.inserir_leituras(
            conn, 'SITE-1', 'COL-CONF',
            [{'timestamp': datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc),
              'sensor_id': 'SNR-1', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
              'valor': 42.00, 'unidade': 'C', 'protocolo_origem': '4-20ma',  # adulterado!
              'status_leitura': 'ok'}])
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.assinaturas_ok is True   # arquivo íntegro
        assert r.valores_ok is False      # Timescale diverge do arquivo
        assert len(r.divergencias) == 1
        assert r.divergencias[0]['sensor_id'] == 'SNR-1'
        assert r.divergencias[0]['valor_arquivo'] == 96.83
        assert r.divergencias[0]['valor_timescale'] == 42.00
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_detecta_ausencia_no_timescale(tmp_path):
    caminho, registro = _gerar_arquivo(tmp_path)
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)  # nada inserido → linha do arquivo não existe no Timescale
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.valores_ok is False
        assert r.divergencias[0]['valor_timescale'] is None
    finally:
        _limpar(conn)
        conn.close()


def test_confronto_detecta_injecao_no_timescale(tmp_path):
    # arquivo com 2 linhas (03:01 e 03:03) → janela cobre 03:02 (injeção ENTRE linhas)
    caminho, registro = _gerar_arquivo(tmp_path, leituras=[
        (datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc), 96.83),
        (datetime(2026, 7, 16, 3, 3, 0, tzinfo=timezone.utc), 97.10)])
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        base = {'sensor_id': 'SNR-1', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
                'unidade': 'C', 'protocolo_origem': '4-20ma', 'status_leitura': 'ok'}
        timescale.inserir_leituras(conn, 'SITE-1', 'COL-CONF', [
            {**base, 'timestamp': datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc), 'valor': 96.83},
            {**base, 'timestamp': datetime(2026, 7, 16, 3, 3, 0, tzinfo=timezone.utc), 'valor': 97.10},
            {**base, 'timestamp': datetime(2026, 7, 16, 3, 2, 0, tzinfo=timezone.utc), 'valor': 50.00}])  # injetada
        r = confronto.confrontar_arquivo(str(caminho), registro, conn)
        assert r.assinaturas_ok is True
        assert r.valores_ok is False
        assert len(r.injetadas_timescale) == 1
        assert r.divergencias == []  # as 2 linhas do arquivo batem; só há injeção
    finally:
        _limpar(conn)
        conn.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_confronto.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingestao.confronto'`.

- [ ] **Step 3: Write minimal implementation**

Criar `ingestao/confronto.py`:

```python
"""Confronto de veracidade (§5.2): Timescale (cache) vs arquivo assinado (verdade).

Parte 1 — assinaturas: reusa validador.validar_arquivo (hdr_sig + sig por linha).
Parte 2 — valores: cada linha verificada do arquivo tem que bater com a linha
correspondente no Timescale, por (sensor_id, timestamp_utc). Divergência em
qualquer parte = alerta de auditoria.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import timescale, validador

_TOLERANCIA = 1e-6


@dataclass
class ResultadoConfronto:
    coletor_id: str
    data_referencia: str
    assinaturas_ok: bool
    valores_ok: bool
    arquivo_nao_fechado: bool
    divergencias: list = field(default_factory=list)
    injetadas_timescale: list = field(default_factory=list)  # rows sem contraparte assinada
    motivo: str = None


def _ts_utc_iso(timestamp_iso):
    dt = datetime.fromisoformat(timestamp_iso)
    # Falha ALTO em timestamp naive: astimezone() num naive assume o TZ do host,
    # o que produziria uma chave UTC dependente de locale — inaceitável num tool
    # de veracidade (falsas divergências ou omissões). O header v2 sempre grava
    # offset (timezone_offset), então o ts do arquivo é sempre aware.
    if dt.tzinfo is None:
        raise ValueError(f"timestamp sem offset (naive), não confrontável: {timestamp_iso!r}")
    return dt.astimezone(timezone.utc).isoformat()


def confrontar_arquivo(caminho, registro_path, conn):
    rv = validador.validar_arquivo(caminho, registro_path)

    # Parte 1: assinaturas
    assinaturas_ok = rv.status_validacao in ('valido', 'incompleto')
    arquivo_nao_fechado = rv.status_validacao == 'incompleto'
    if not assinaturas_ok:
        return ResultadoConfronto(
            coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
            assinaturas_ok=False, valores_ok=False, arquivo_nao_fechado=False,
            motivo=f'assinatura inválida: {rv.motivo_rejeicao}')

    # Parte 2: value-match contra o Timescale
    linhas = rv.leituras
    if not linhas:
        return ResultadoConfronto(
            coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
            assinaturas_ok=True, valores_ok=True, arquivo_nao_fechado=arquivo_nao_fechado)

    ts_chaves = [_ts_utc_iso(l['timestamp']) for l in linhas]
    ts_inicio = min(datetime.fromisoformat(k) for k in ts_chaves)
    # +1s: a query usa `time < ts_fim`; sem isso a última linha do dia escaparia.
    ts_fim = max(datetime.fromisoformat(k) for k in ts_chaves) + timedelta(seconds=1)
    mapa = timescale.buscar_leituras_para_confronto(
        conn, rv.coletor_id, ts_inicio, ts_fim)

    divergencias = []
    chaves_arquivo = set()
    for linha in linhas:
        chave = (linha['sensor_id'], _ts_utc_iso(linha['timestamp']))
        chaves_arquivo.add(chave)
        valor_ts = mapa.get(chave)
        if valor_ts is None or abs(valor_ts - linha['valor']) > _TOLERANCIA:
            divergencias.append({
                'sensor_id': linha['sensor_id'], 'timestamp': linha['timestamp'],
                'valor_arquivo': linha['valor'], 'valor_timescale': valor_ts,
            })

    # count-match reverso: rows no Timescale sem contraparte assinada = injeção.
    # Só confiável quando o arquivo está fechado (senão pode ser cauda legítima
    # que o crash não gravou no arquivo).
    injetadas = []
    if not arquivo_nao_fechado:
        injetadas = [{'sensor_id': s, 'timestamp': ts}
                     for (s, ts) in mapa if (s, ts) not in chaves_arquivo]

    return ResultadoConfronto(
        coletor_id=rv.coletor_id, data_referencia=rv.data_referencia,
        assinaturas_ok=True, valores_ok=(not divergencias and not injetadas),
        arquivo_nao_fechado=arquivo_nao_fechado, divergencias=divergencias,
        injetadas_timescale=injetadas)
```

> **Blind-spot do count-match:** a janela de query é `[min_ts, max_ts+1s]` das linhas do arquivo — pega injeções **entre** leituras (o caso comum). Injeções **antes da primeira** ou **depois da última** leitura do dia ficam fora da janela e não são vistas (mesma classe da limitação "sem rodapé → sem prova de truncamento", §5.1). Num dia com cadência ≥1/min o span cobre quase o dia inteiro. Documentado, aceito na v1.

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_confronto.py -q`
Expected: PASS. (Se a última linha escapar do intervalo, aplicar o fix do `ts_fim` da nota acima.)

- [ ] **Step 5: Commit**

```bash
git add ingestao/confronto.py ingestao/tests/test_confronto.py
git commit -m "feat(confronto): motor de veracidade Timescale vs arquivo assinado"
```

---

### Task 3: CLI de confronto por período + saída de alerta

**Files:**
- Modify: `ingestao/confronto.py` (adicionar `confrontar_periodo` + `main`)
- Test: `ingestao/tests/test_confronto.py` (adicionar caso de `confrontar_periodo`)

**Interfaces:**
- Consumes: `confrontar_arquivo` (Task 2).
- Produces:
  - `confrontar_periodo(diretorio_arquivos, coletor_id, datas, registro_path, conn) -> list[ResultadoConfronto]` — itera os arquivos `{data}_leituras.txt` do coletor no diretório arquivado.
  - `main()` CLI: `python -m ingestao.confronto --diretorio <dir> --coletor COL-X --de 2026-07-01 --ate 2026-07-31` → imprime relatório e **exit code 1** se houver qualquer divergência (para o operador/CI barrar a emissão do relatório legal).

- [ ] **Step 1: Write the failing test**

Adicionar a `ingestao/tests/test_confronto.py`:

```python
def test_confrontar_periodo_agrega_por_dia(tmp_path):
    caminho, registro = _gerar_arquivo(tmp_path)  # gera d/COL-CONF/2026-07-16_leituras.txt
    diretorio = str(tmp_path / "d" / "COL-CONF")
    conn = timescale.conectar(DSN)
    try:
        _limpar(conn)
        timescale.inserir_leituras(
            conn, 'SITE-1', 'COL-CONF',
            [{'timestamp': datetime(2026, 7, 16, 3, 1, 0, tzinfo=timezone.utc),
              'sensor_id': 'SNR-1', 'area_id': 'EXPURGO', 'tipo_medida': 'temperatura',
              'valor': 96.83, 'unidade': 'C', 'protocolo_origem': '4-20ma',
              'status_leitura': 'ok'}])
        resultados = confronto.confrontar_periodo(
            diretorio, 'COL-CONF', ['2026-07-16'], registro, conn)
        assert len(resultados) == 1
        assert resultados[0].valores_ok is True
    finally:
        _limpar(conn)
        conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_confronto.py::test_confrontar_periodo_agrega_por_dia -q`
Expected: FAIL — `AttributeError: ... has no attribute 'confrontar_periodo'`.

- [ ] **Step 3: Write minimal implementation**

Adicionar a `ingestao/confronto.py`:

```python
import argparse
from pathlib import Path


def confrontar_periodo(diretorio_arquivos, coletor_id, datas, registro_path, conn):
    resultados = []
    for data in datas:
        caminho = Path(diretorio_arquivos) / f"{data}_leituras.txt"
        if not caminho.exists():
            resultados.append(ResultadoConfronto(
                coletor_id=coletor_id, data_referencia=data,
                assinaturas_ok=False, valores_ok=False, arquivo_nao_fechado=False,
                motivo='arquivo ausente no acervo (fonte da verdade faltando)'))
            continue
        resultados.append(confrontar_arquivo(str(caminho), registro_path, conn))
    return resultados


def _datas_entre(de, ate):
    from datetime import date, timedelta
    d0, d1 = date.fromisoformat(de), date.fromisoformat(ate)
    dias, atual = [], d0
    while atual <= d1:
        dias.append(atual.isoformat())
        atual += timedelta(days=1)
    return dias


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Confronto de veracidade Timescale vs arquivos assinados (§5.2)')
    parser.add_argument('--diretorio', required=True, help='dir do acervo do coletor')
    parser.add_argument('--coletor', required=True)
    parser.add_argument('--de', required=True, help='YYYY-MM-DD')
    parser.add_argument('--ate', required=True, help='YYYY-MM-DD')
    parser.add_argument('--registro', default='ingestao/coletores_conhecidos.json')
    parser.add_argument('--dsn', default='postgresql://sentinela:sentinela@localhost:5433/sentinela')
    args = parser.parse_args(argv)

    conn = timescale.conectar(args.dsn)
    try:
        resultados = confrontar_periodo(
            args.diretorio, args.coletor, _datas_entre(args.de, args.ate),
            args.registro, conn)
    finally:
        conn.close()

    houve_alerta = False
    for r in resultados:
        alerta = (not r.assinaturas_ok) or (not r.valores_ok)
        houve_alerta = houve_alerta or alerta
        marca = 'ALERTA' if alerta else 'ok'
        extra = f" motivo={r.motivo}" if r.motivo else ''
        extra += f" divergencias={len(r.divergencias)}" if r.divergencias else ''
        extra += f" injetadas={len(r.injetadas_timescale)}" if r.injetadas_timescale else ''
        extra += ' (arquivo_nao_fechado)' if r.arquivo_nao_fechado else ''
        print(f"[{marca}] {r.coletor_id} {r.data_referencia} "
              f"assinaturas={r.assinaturas_ok} valores={r.valores_ok}{extra}")

    return 1 if houve_alerta else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest ingestao/tests/test_confronto.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add ingestao/confronto.py ingestao/tests/test_confronto.py
git commit -m "feat(confronto): CLI por periodo com exit-code de alerta de auditoria"
```

---

## Self-Review (C)

- **§5.2 parte 1 (assinaturas válidas: hdr_sig + sig por linha):** reusa `validador.validar_arquivo` (Plano B) — sem reimplementação. ✔
- **§5.2 parte 2 (valores batem):** Task 2 casa cada linha por `(sensor_id, ts_utc)` com tolerância. ✔
- **§5.2 (só 1 sem 2 não prova nada):** `ResultadoConfronto` exige AMBOS `assinaturas_ok` e `valores_ok`; o CLI dispara alerta se qualquer um falhar. ✔
- **§5.2 (Timescale=cache re-verificável; arquivo=fonte):** adulteração no Timescale vira divergência (`test_confronto_detecta_valor_adulterado_no_timescale`); linha injetada vira `injetadas_timescale` (count-match reverso); arquivo ausente vira alerta (`confrontar_periodo`). ✔
- **Timezone (correção):** `_ts_utc_iso` levanta em ts naive (chave UTC seria locale-dependente); writer de produção é tz-aware. ✔
- **Count-match blind-spot:** injeção fora do span de tempo do arquivo não é vista — documentado, aceito v1. ✔
- **§5.1 (incompleto conta, mas sinaliza):** `arquivo_nao_fechado=True` propagado. ✔
- **Lacuna documentada:** revogação-no-tempo (pubkey vigente na época, §6 v2) usa a pubkey atual do registro; sem histórico de revogação ainda. Gerador de relatório legal em PDF inexistente → hook fora de escopo. ✔
- **Fix de borda registrado:** `ts_fim` inclusivo (nota na Task 2) — a última linha do dia não pode escapar do intervalo. ✔
