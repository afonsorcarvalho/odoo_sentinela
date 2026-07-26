# Alarme na Borda + Tempo Real — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O hub avalia limiares de alarme por sensor e sinaliza cada cruzamento por dois caminhos — MQTT efêmero (toast instantâneo no dashboard) e `alarmes.txt` assinado (único registro durável no Odoo).

**Architecture:** Edge-detection. Detector puro no hub roda dentro do loop de leitura; ao cruzar (histerese N=3, só leitura `ok`) emite evento em `alarmes.txt` assinado (→ SFTP → watcher → Odoo, caminho durável já existente) **e** publica em MQTT `sentinela/alarme/...`. A bridge repassa o MQTT como `pg_notify('alarme_ao_vivo')`; a API reaproveita o cano SSE (`live.publicar`) → dashboard mostra toast na hora. MQTT nunca persiste → zero dedup de persistência; a única reconciliação é de UI (não duplicar toast ao vivo + toast do poll).

**Tech Stack:** Python 3 (hub, api, ingestao, scripts), pytest; TypeScript/React + Vitest (frontend); MQTT (paho), Postgres LISTEN/NOTIFY (asyncpg), Odoo XML-RPC.

**Spec:** `docs/superpowers/specs/2026-07-26-alarme-borda-tempo-real-design.md`

## Global Constraints

- **Alarme só avalia leitura `status_leitura == "ok"`.** `suspeito`/`erro_leitura`/`sensor_offline` são ignorados (não avançam nem zeram o contador de histerese).
- **Histerese:** `entrada_alarme` só após **N=3** leituras `ok` consecutivas fora do limite; `saida_alarme` só quando o valor volta com **folga** (`< limite_max - margem` e `> limite_min + margem`). N e margem são hub-level (config local do hub), default `alarme_n=3`, `alarme_margem=0.0`.
- **MQTT nunca persiste** (só `alarmes.txt` vira evento no Odoo). `retain=False`.
- **Nenhuma falha de MQTT/rede propaga** — o arquivo assinado é a fonte de verdade (padrão já usado em `PublicadorMqtt`).
- **Formato de arquivo congelado:** reusar `contrato/formato.gerar_linha_alarme`, `montar_cabecalho`, `montar_rodape` (campo total `"total_eventos"`) e a assinatura-por-linha de `hub/assinador.py`. Nome do arquivo: `{data}_{hub}-{coletor}_alarmes.txt`.
- **Um-aberto-por-sensor:** no máximo um `alarm.event` aberto por sensor.
- **Discriminador SSE:** payload de alarme ao vivo carrega `tipo: "alarme_ao_vivo"`; leituras normais não têm `tipo` (ausência = leitura).
- Rodar testes python com `PYTHONPATH=/home/afonso/docker/odoo_sentinela`. Testes de hub: `python -m pytest hub/tests/...`. Frontend: `cd frontend && npx vitest run ...`.

---

## File Structure

- **Create** `hub/detector_alarme.py` — lógica pura de detecção + estado persistido (Task 1).
- **Create** `hub/arquivo_alarmes.py` — escritor do `alarmes.txt` assinado (Task 3).
- **Modify** `hub/config.py` — `CanalConfig.limite_min/max`, `HubConfig.alarme_n/alarme_margem` (Task 2).
- **Modify** `hub/publicador_mqtt.py` — `publicar_alarme(...)` (Task 4).
- **Modify** `hub/main.py` — fiação detector + arquivo_alarmes + publish no loop (Task 5).
- **Modify** `api/config_publisher.py` — serializa `limite_min/max` por canal (Task 6).
- **Modify** `scripts/bridge_telemetria.py` — assina `sentinela/alarme/#` → `pg_notify` (Task 7).
- **Modify** `api/live_listener.py` — listener do canal `alarme_ao_vivo` (Task 8).
- **Modify** `ingestao/odoo_cliente.py` — guard um-aberto-por-sensor (Task 9).
- **Modify** `frontend/src/lib/api/contracts.ts`, `.../real/liveApi.ts`, `.../mock/liveApi.ts` — `subscribeAlarme` (Task 10).
- **Modify** `frontend/src/components/ToastContainer.tsx` — toast ao vivo + reconciliação/fallback (Task 11).

Test files sit next to their module following the repo convention (`hub/tests/`, `frontend/src/**/*.test.tsx`, `tests/`/inline para api/ingestao — seguir o padrão vizinho do arquivo modificado).

---

## Task 1: Detector de alarme (núcleo puro)

**Files:**
- Create: `hub/detector_alarme.py`
- Test: `hub/tests/test_detector_alarme.py`

**Interfaces:**
- Produces:
  - `DetectorAlarme(limites: dict[str, dict], n: int = 3, margem: float = 0.0, estado_path: str | None = None)`
    - `limites`: `{sensor_id: {"min": float | None, "max": float | None}}`
  - `.avaliar(leitura: dict) -> list[dict]` — recebe uma leitura normalizada (mesmo dict de `hub/leitor.py::_normalizar`: chaves `sensor_id, area_id, tipo_medida, valor, status_leitura, timestamp`). Retorna 0 ou 1 evento:
    - evento: `{"sensor_id", "area_id", "tipo_medida", "timestamp", "tipo_evento": "entrada_alarme"|"saida_alarme", "tipo_violacao": "acima_limite"|"abaixo_limite", "valor", "limite_min_vigente": float|None, "limite_max_vigente": float|None}`
  - Estado por sensor persistido em JSON (`estado_path`), carregado no `__init__`, gravado a cada transição. Restart no meio de excursão NÃO re-emite `entrada_alarme`.

- [ ] **Step 1: Write the failing test**

```python
# hub/tests/test_detector_alarme.py
import json
from datetime import datetime, timezone

from hub.detector_alarme import DetectorAlarme

TS = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)


def _leitura(valor, status="ok", sensor="S1"):
    return {"sensor_id": sensor, "area_id": "A1", "tipo_medida": "temperatura",
            "valor": valor, "status_leitura": status, "timestamp": TS}


def _det(**kw):
    limites = {"S1": {"min": 18.0, "max": 25.0}}
    return DetectorAlarme(limites, n=3, margem=0.5, **kw)


def test_entrada_apos_n_leituras_fora():
    d = _det()
    assert d.avaliar(_leitura(30.0)) == []      # 1 fora
    assert d.avaliar(_leitura(30.0)) == []      # 2 fora
    eventos = d.avaliar(_leitura(30.0))         # 3 fora -> entrada
    assert len(eventos) == 1
    e = eventos[0]
    assert e["tipo_evento"] == "entrada_alarme"
    assert e["tipo_violacao"] == "acima_limite"
    assert e["valor"] == 30.0
    assert e["limite_max_vigente"] == 25.0
    assert e["sensor_id"] == "S1"


def test_dentro_zera_contador():
    d = _det()
    d.avaliar(_leitura(30.0)); d.avaliar(_leitura(30.0))
    assert d.avaliar(_leitura(20.0)) == []      # volta pra dentro: zera
    assert d.avaliar(_leitura(30.0)) == []      # recomeça do 1
    assert d.avaliar(_leitura(30.0)) == []
    assert len(d.avaliar(_leitura(30.0))) == 1  # agora sim (3 seguidas)


def test_suspeito_nao_avanca_nem_zera():
    d = _det()
    d.avaliar(_leitura(30.0)); d.avaliar(_leitura(30.0))
    assert d.avaliar(_leitura(0.0, status="suspeito")) == []   # ignora
    eventos = d.avaliar(_leitura(30.0))         # 3ª "ok" fora -> entrada
    assert len(eventos) == 1


def test_saida_so_com_folga():
    d = _det()
    for _ in range(3):
        d.avaliar(_leitura(30.0))               # entra em alarme
    assert d.avaliar(_leitura(24.9)) == []      # dentro do limite mas sem folga (25-0.5=24.5)
    eventos = d.avaliar(_leitura(24.4))         # abaixo de 24.5 -> saida
    assert len(eventos) == 1 and eventos[0]["tipo_evento"] == "saida_alarme"


def test_abaixo_limite():
    d = DetectorAlarme({"S1": {"min": 18.0, "max": 25.0}}, n=1, margem=0.0)
    eventos = d.avaliar(_leitura(10.0))
    assert eventos[0]["tipo_violacao"] == "abaixo_limite"
    assert eventos[0]["limite_min_vigente"] == 18.0


def test_restart_nao_reemite_entrada(tmp_path):
    caminho = str(tmp_path / "estado.json")
    d1 = _det(estado_path=caminho)
    for _ in range(3):
        d1.avaliar(_leitura(30.0))              # entra em alarme, persiste
    d2 = _det(estado_path=caminho)              # "reinicia" carregando estado
    assert d2.avaliar(_leitura(30.0)) == []     # já em alarme -> não re-emite
    eventos = d2.avaliar(_leitura(24.0))        # com folga -> saida
    assert len(eventos) == 1 and eventos[0]["tipo_evento"] == "saida_alarme"


def test_sensor_sem_limite_configurado_ignora():
    d = DetectorAlarme({}, n=1)
    assert d.avaliar(_leitura(999.0)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_detector_alarme.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.detector_alarme'`

- [ ] **Step 3: Write minimal implementation**

```python
# hub/detector_alarme.py
"""Detector de alarme na borda: por sensor, com histerese, avalia cruzamento
de limiar SÓ em leitura "ok" (gate de plausibilidade fica no leitor). Estado
por sensor persistido em disco para sobreviver a restart sem re-emitir entrada.
"""
import json
from pathlib import Path


class DetectorAlarme:
    def __init__(self, limites, n=3, margem=0.0, estado_path=None):
        self._limites = limites or {}
        self._n = n
        self._margem = margem
        self._estado_path = estado_path
        # estado[sensor_id] = {"em_alarme": bool, "tipo_violacao": str|None, "contador": int}
        self._estado = {}
        self._carregar()

    def _carregar(self):
        if not self._estado_path:
            return
        p = Path(self._estado_path).expanduser()
        if p.exists():
            try:
                self._estado = json.loads(p.read_text())
            except (ValueError, OSError):
                self._estado = {}

    def _salvar(self):
        if not self._estado_path:
            return
        p = Path(self._estado_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._estado))

    def _st(self, sensor_id):
        return self._estado.setdefault(
            sensor_id, {"em_alarme": False, "tipo_violacao": None, "contador": 0})

    def avaliar(self, leitura):
        sensor_id = leitura["sensor_id"]
        limite = self._limites.get(sensor_id)
        if limite is None:
            return []
        if leitura.get("status_leitura") != "ok":
            return []  # gate de plausibilidade: leitura suspeita não carrega info

        lmin, lmax = limite.get("min"), limite.get("max")
        valor = leitura["valor"]
        st = self._st(sensor_id)

        if st["em_alarme"]:
            dentro_com_folga = (
                (lmax is None or valor < lmax - self._margem)
                and (lmin is None or valor > lmin + self._margem)
            )
            if dentro_com_folga:
                st["em_alarme"] = False
                tipo_violacao = st["tipo_violacao"]
                st["tipo_violacao"] = None
                st["contador"] = 0
                self._salvar()
                return [self._evento(leitura, "saida_alarme", tipo_violacao, lmin, lmax)]
            return []

        acima = lmax is not None and valor > lmax
        abaixo = lmin is not None and valor < lmin
        if not (acima or abaixo):
            st["contador"] = 0
            return []
        st["contador"] += 1
        if st["contador"] < self._n:
            return []
        st["em_alarme"] = True
        st["tipo_violacao"] = "acima_limite" if acima else "abaixo_limite"
        st["contador"] = 0
        self._salvar()
        return [self._evento(leitura, "entrada_alarme", st["tipo_violacao"], lmin, lmax)]

    @staticmethod
    def _evento(leitura, tipo_evento, tipo_violacao, lmin, lmax):
        return {
            "sensor_id": leitura["sensor_id"], "area_id": leitura["area_id"],
            "tipo_medida": leitura["tipo_medida"], "timestamp": leitura["timestamp"],
            "tipo_evento": tipo_evento, "tipo_violacao": tipo_violacao,
            "valor": leitura["valor"], "limite_min_vigente": lmin, "limite_max_vigente": lmax,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_detector_alarme.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add hub/detector_alarme.py hub/tests/test_detector_alarme.py
git commit -m "feat(hub): detector de alarme na borda com histerese e estado persistido"
```

---

## Task 2: Config do hub — limites por canal + params de histerese

**Files:**
- Modify: `hub/config.py` (`CanalConfig` dataclass ~L11-24; `_canal` ~L93-107; `HubConfig` ~L55-69; `carregar_config` return ~L206-214)
- Test: `hub/tests/test_config.py` (adicionar casos; se não existir, criar)

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `CanalConfig.limite_min: float|None`, `CanalConfig.limite_max: float|None`; `HubConfig.alarme_n: int = 3`, `HubConfig.alarme_margem: float = 0.0`.

- [ ] **Step 1: Write the failing test**

```python
# hub/tests/test_config.py  (adicionar; imports/util conforme os testes existentes)
import textwrap
from pathlib import Path

from hub.config import carregar_config


def _yaml_base(extra_canal="", extra_top=""):
    return textwrap.dedent(f"""
    hub_id: HUB-T
    coletor_id: COL-T
    firmware_version: 0.1.0
    timezone_offset: "-03:00"
    intervalo_leitura_s: 5
    caminho_chave: /tmp/k.pem
    caminho_dados: /tmp/dados
    {extra_top}
    barramentos:
      - porta: /dev/ttyUSB0
        baud: 9600
        dispositivos:
          - endereco: 1
            driver: n4aib16
            canais:
              - ch: 1
                sensor_id: SNR-T-01
                area_id: AREA-T
                tipo_medida: temperatura
                unidade: C
                protocolo_origem: 4-20ma
                {extra_canal}
    """)


def test_limite_por_canal(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(_yaml_base(extra_canal="limite_min: 18.0\n                limite_max: 25.0"))
    cfg = carregar_config(str(p))
    canal = cfg.barramentos[0].dispositivos[0].canais[0]
    assert canal.limite_min == 18.0
    assert canal.limite_max == 25.0


def test_limite_ausente_vira_none(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(_yaml_base())
    cfg = carregar_config(str(p))
    canal = cfg.barramentos[0].dispositivos[0].canais[0]
    assert canal.limite_min is None
    assert canal.limite_max is None


def test_params_histerese_default_e_override(tmp_path):
    p1 = tmp_path / "d.yaml"; p1.write_text(_yaml_base())
    cfg = carregar_config(str(p1))
    assert cfg.alarme_n == 3
    assert cfg.alarme_margem == 0.0
    p2 = tmp_path / "o.yaml"
    p2.write_text(_yaml_base(extra_top="alarme_n: 5\nalarme_margem: 0.25"))
    cfg2 = carregar_config(str(p2))
    assert cfg2.alarme_n == 5
    assert cfg2.alarme_margem == 0.25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_config.py -v -k "limite or histerese"`
Expected: FAIL — `AttributeError: 'CanalConfig' object has no attribute 'limite_min'`

- [ ] **Step 3: Write minimal implementation**

Em `CanalConfig` (após `faixa_max`):
```python
    limite_min: float = None
    limite_max: float = None
```

Em `_canal(...)` return (após `faixa_max=...`):
```python
        limite_min=(float(bruto["limite_min"]) if bruto.get("limite_min") is not None else None),
        limite_max=(float(bruto["limite_max"]) if bruto.get("limite_max") is not None else None),
```

Em `HubConfig` (após `site_id`):
```python
    alarme_n: int = 3
    alarme_margem: float = 0.0
```

Em `carregar_config` return `HubConfig(...)` (após `site_id=...`):
```python
        alarme_n=int(dados.get("alarme_n", 3)),
        alarme_margem=float(dados.get("alarme_margem", 0.0)),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_config.py -v`
Expected: PASS (todos, incl. os existentes)

- [ ] **Step 5: Commit**

```bash
git add hub/config.py hub/tests/test_config.py
git commit -m "feat(hub): config carrega limite_min/max por canal e params de histerese"
```

---

## Task 3: Escritor do `alarmes.txt` assinado

**Files:**
- Create: `hub/arquivo_alarmes.py`
- Test: `hub/tests/test_arquivo_alarmes.py`

**Interfaces:**
- Consumes: evento dict de `DetectorAlarme.avaliar` (Task 1); `hub/assinador.AssinadorSoftware`; `hub/arquivo_diario.{reconstruir_estado,_esta_selado}`.
- Produces:
  - `ArquivoAlarmes(coletor_id, hub_id, firmware_version, timezone_offset, caminho_dados, assinador, cliente_id='', site_id='')`
  - `.registrar_evento(evento: dict) -> None` — grava linha assinada (cria o arquivo do dia com cabeçalho na 1ª chamada).
  - `.selar(data_referencia=None, caminho=None) -> None`
  - `.recuperar_pendentes(hoje: date) -> None`
  - `.caminho(data_referencia) -> Path`

- [ ] **Step 1: Write the failing test**

```python
# hub/tests/test_arquivo_alarmes.py
from datetime import date, datetime, timezone

from cryptography.hazmat.primitives.serialization import load_pem_public_key

from hub.arquivo_alarmes import ArquivoAlarmes
from hub.assinador import AssinadorSoftware
from ingestao import validador


def _assinador(tmp_path):
    return AssinadorSoftware(str(tmp_path / "chave.pem"))  # cria se não existe


def _pubkey(ass):
    return load_pem_public_key(ass.chave_publica_pem().encode())


def _evento(valor, tipo_evento, tipo_violacao):
    return {"sensor_id": "SNR-T-01", "area_id": "AREA-T", "tipo_medida": "temperatura",
            "timestamp": datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
            "tipo_evento": tipo_evento, "tipo_violacao": tipo_violacao, "valor": valor,
            "limite_min_vigente": 18.0, "limite_max_vigente": 25.0}


def test_arquivo_alarmes_valido_para_o_validador(tmp_path):
    ass = _assinador(tmp_path)
    arq = ArquivoAlarmes("COL-T", "HUB-T", "0.1.0", "-03:00", str(tmp_path / "dados"), ass,
                         cliente_id="CLI-T", site_id="SITE-T")
    arq.registrar_evento(_evento(30.0, "entrada_alarme", "acima_limite"))
    arq.registrar_evento(_evento(24.0, "saida_alarme", "acima_limite"))
    arq.selar("2026-07-26")

    conteudo = arq.caminho("2026-07-26").read_text()
    resultado = validador.validar_texto(conteudo, _pubkey(ass))
    assert resultado.status_validacao == "valido", resultado.motivo_rejeicao
    assert resultado.tipo_arquivo == "alarmes"
    assert resultado.total_linhas == 2


def test_recuperar_pendentes_sela_dia_anterior(tmp_path):
    ass = _assinador(tmp_path)
    arq = ArquivoAlarmes("COL-T", "HUB-T", "0.1.0", "-03:00", str(tmp_path / "dados"), ass)
    ev = _evento(30.0, "entrada_alarme", "acima_limite")
    ev["timestamp"] = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
    arq.registrar_evento(ev)
    arq2 = ArquivoAlarmes("COL-T", "HUB-T", "0.1.0", "-03:00", str(tmp_path / "dados"), ass)
    arq2.recuperar_pendentes(date(2026, 7, 26))
    from hub.arquivo_diario import _esta_selado
    assert _esta_selado(arq2.caminho("2026-07-25"))
```

**Confirmado:** `AssinadorSoftware.chave_publica_pem()` devolve o PEM; `validar_texto(texto, chave_publica)` (`ingestao/validador.py:114`) espera o **objeto** de chave pública (padrão do teste existente `ingestao/tests/test_validador.py::test_validar_texto_aceita_chave_publica_resolvida`). Por isso `_pubkey()` faz `load_pem_public_key(...)`. Resultado usa `status_validacao == 'valido'` / `motivo_rejeicao` / `total_linhas` (não `.valido`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_arquivo_alarmes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hub.arquivo_alarmes'`

- [ ] **Step 3: Write minimal implementation**

```python
# hub/arquivo_alarmes.py
"""Escritor do .txt diário de ALARMES (eventos entrada/saida), no formato
congelado. Espelha ArquivoDiario (hash encadeado por dia, selagem diária,
recuperação no boot) mas para eventos esparsos de alarme. Reusa as funções de
módulo reconstruir_estado/_esta_selado de arquivo_diario.
"""
import base64
import glob
import os
from datetime import date
from pathlib import Path

from contrato import formato
from hub.arquivo_diario import _esta_selado, reconstruir_estado


class ArquivoAlarmes:
    def __init__(self, coletor_id, hub_id, firmware_version, timezone_offset,
                 caminho_dados, assinador, cliente_id='', site_id=''):
        self._coletor_id = coletor_id
        self._hub_id = hub_id
        self._firmware = firmware_version
        self._tz_offset = timezone_offset
        self._cliente_id = cliente_id
        self._site_id = site_id
        self._dir = Path(caminho_dados).expanduser() / coletor_id
        self._assinador = assinador
        self._data_atual = None
        self._hash = None
        self._seq = 1

    def caminho(self, data_referencia):
        nome = f"{data_referencia}_{self._hub_id}-{self._coletor_id}_alarmes.txt"
        return self._dir / nome

    def _abrir(self, data_referencia):
        self._dir.mkdir(parents=True, exist_ok=True)
        caminho = self.caminho(data_referencia)
        if caminho.exists():
            self._hash, self._seq = reconstruir_estado(caminho.read_text())
        else:
            cabecalho = formato.montar_cabecalho(
                "alarmes", self._coletor_id, self._hub_id,
                self._assinador.fingerprint(), data_referencia,
                self._tz_offset, self._firmware, self._cliente_id, self._site_id,
            )
            self._hash = formato.hash_seed(cabecalho)
            hdr_sig = base64.b64encode(self._assinador.assinar(self._hash.encode())).decode()
            caminho.write_text(cabecalho + f"# hdr_sig: {hdr_sig}\n")
            self._seq = 1
        self._data_atual = data_referencia

    def registrar_evento(self, evento):
        data_referencia = evento["timestamp"].date().isoformat()
        if self._data_atual is not None and data_referencia != self._data_atual:
            self.selar(self._data_atual)
            self._data_atual = None
        if self._data_atual is None:
            self._abrir(data_referencia)
        ts = evento["timestamp"].isoformat(timespec="seconds")
        linha, self._hash = formato.gerar_linha_alarme(
            self._hash, self._seq, ts, evento["sensor_id"], evento["area_id"],
            evento["tipo_medida"], evento["tipo_evento"], evento["tipo_violacao"],
            evento["valor"], evento["limite_min_vigente"], evento["limite_max_vigente"],
        )
        sig = base64.b64encode(self._assinador.assinar(self._hash.encode())).decode()
        with self.caminho(data_referencia).open("a") as fh:
            fh.write(linha + "|" + sig + "\n")
        self._seq += 1

    def selar(self, data_referencia=None, caminho=None):
        data_referencia = data_referencia or self._data_atual
        if data_referencia is None:
            return
        caminho = Path(caminho) if caminho is not None else self.caminho(data_referencia)
        if _esta_selado(caminho) or not caminho.exists():
            return
        hash_final, proximo_seq = reconstruir_estado(caminho.read_text())
        assinatura = base64.b64encode(self._assinador.assinar(hash_final.encode())).decode()
        rodape = formato.montar_rodape(proximo_seq - 1, hash_final, assinatura, "total_eventos")
        with caminho.open("a") as fh:
            fh.write(rodape)

    def recuperar_pendentes(self, hoje: date):
        for nome in glob.glob(str(self._dir / "*_alarmes.txt")):
            data_str = os.path.basename(nome)[:10]
            if date.fromisoformat(data_str) < hoje and not _esta_selado(Path(nome)):
                self.selar(data_str, caminho=Path(nome))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_arquivo_alarmes.py -v`
Expected: PASS (2 passed). Se `validar_texto` reprovar, comparar byte-a-byte com um arquivo do `coletor_simulado/gerador.py --injetar-alarme` (mesmas funções `formato.*`) e ajustar.

- [ ] **Step 5: Commit**

```bash
git add hub/arquivo_alarmes.py hub/tests/test_arquivo_alarmes.py
git commit -m "feat(hub): escritor do alarmes.txt assinado (formato congelado)"
```

---

## Task 4: MQTT — `publicar_alarme`

**Files:**
- Modify: `hub/publicador_mqtt.py` (adicionar método)
- Test: `hub/tests/test_publicador_mqtt.py` (adicionar; se não existir, criar com um fake client)

**Interfaces:**
- Consumes: evento dict (Task 1).
- Produces: `PublicadorMqtt.publicar_alarme(hub_id, coletor_id, evento) -> str | None` — publica em `sentinela/alarme/{hub_id}/{coletor_id}/{sensor_id}`, `qos=0`, `retain=False`.

- [ ] **Step 1: Write the failing test**

```python
# hub/tests/test_publicador_mqtt.py
import json
from datetime import datetime, timezone

from hub.publicador_mqtt import PublicadorMqtt


class _FakeClient:
    def __init__(self): self.publicados = []
    def connect(self, *a, **k): pass
    def publish(self, topico, payload, qos=0): self.publicados.append((topico, payload, qos))
    def disconnect(self): pass


def _evento():
    return {"sensor_id": "SNR-T-01", "area_id": "AREA-T", "tipo_medida": "temperatura",
            "timestamp": datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc),
            "tipo_evento": "entrada_alarme", "tipo_violacao": "acima_limite", "valor": 30.0,
            "limite_min_vigente": 18.0, "limite_max_vigente": 25.0}


def test_publicar_alarme_topico_e_payload():
    fake = _FakeClient()
    pub = PublicadorMqtt("localhost", 1883, client=fake)
    topico = pub.publicar_alarme("HUB-T", "COL-T", _evento())
    assert topico == "sentinela/alarme/HUB-T/COL-T/SNR-T-01"
    assert len(fake.publicados) == 1
    t, payload, qos = fake.publicados[0]
    p = json.loads(payload)
    assert p["tipo_evento"] == "entrada_alarme"
    assert p["tipo_violacao"] == "acima_limite"
    assert p["valor"] == 30.0
    assert p["limite_max"] == 25.0
    assert p["sensor_id"] == "SNR-T-01"
    assert p["area_id"] == "AREA-T"
    assert p["timestamp"] == "2026-07-26T12:00:00+00:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_publicador_mqtt.py -v`
Expected: FAIL — `AttributeError: 'PublicadorMqtt' object has no attribute 'publicar_alarme'`

- [ ] **Step 3: Write minimal implementation**

Adicionar em `hub/publicador_mqtt.py` (dentro da classe, após `publicar`):
```python
    def publicar_alarme(self, hub_id, coletor_id, evento):
        topico = f"sentinela/alarme/{hub_id}/{coletor_id}/{evento['sensor_id']}"
        payload = json.dumps({
            "timestamp": evento["timestamp"].isoformat(timespec="seconds"),
            "sensor_id": evento["sensor_id"],
            "area_id": evento["area_id"],
            "tipo_medida": evento["tipo_medida"],
            "tipo_evento": evento["tipo_evento"],
            "tipo_violacao": evento["tipo_violacao"],
            "valor": evento["valor"],
            "limite_min": evento["limite_min_vigente"],
            "limite_max": evento["limite_max_vigente"],
        })
        try:
            self._client.publish(topico, payload, qos=0)
            return topico
        except OSError:
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_publicador_mqtt.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub/publicador_mqtt.py hub/tests/test_publicador_mqtt.py
git commit -m "feat(hub): PublicadorMqtt.publicar_alarme em sentinela/alarme/..."
```

---

## Task 5: Fiação no loop do hub (`main.py`)

**Files:**
- Modify: `hub/main.py` (`executar(...)` ~L25-78; `main(...)` ~L81-140)
- Test: `hub/tests/test_main_alarme.py`

**Interfaces:**
- Consumes: `DetectorAlarme` (T1), `ArquivoAlarmes` (T3), `PublicadorMqtt.publicar_alarme` (T4), `HubConfig.alarme_n/alarme_margem` + `CanalConfig.limite_min/max` (T2).
- Produces: no loop, para cada leitura: `arquivo.registrar` + `publicador.publicar` (como hoje) **e** para cada evento de `detector.avaliar(leitura)`: `arquivo_alarmes.registrar_evento(evento)` + `publicador.publicar_alarme(hub_id, coletor_id, evento)`. `recuperar_pendentes` e `selar` também para o arquivo de alarmes. Helper `montar_limites(config) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# hub/tests/test_main_alarme.py
from datetime import datetime, timezone
from threading import Event

from hub import main as main_mod
from hub.detector_alarme import DetectorAlarme
from hub.config import CanalConfig, DispositivoConfig, BarramentoConfig, HubConfig

TS = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)


def _config():
    canal = CanalConfig(ch=1, sensor_id="SNR-T-01", area_id="AREA-T",
                        tipo_medida="temperatura", unidade="C", protocolo_origem="4-20ma",
                        limite_min=18.0, limite_max=25.0)
    disp = DispositivoConfig(endereco=1, driver="n4aib16", canais=[canal])
    bus = BarramentoConfig(porta="/dev/ttyUSB0", baud=9600, paridade="N", stop_bits=1,
                           dispositivos=[disp])
    return HubConfig(hub_id="HUB-T", coletor_id="COL-T", firmware_version="0.1.0",
                     timezone_offset="-03:00", intervalo_leitura_s=0, caminho_chave="/tmp/k",
                     caminho_dados="/tmp/d", mqtt_host="localhost", mqtt_port=1883,
                     barramentos=[bus], alarme_n=3, alarme_margem=0.5)


def test_montar_limites_extrai_da_config():
    limites = main_mod.montar_limites(_config())
    assert limites == {"SNR-T-01": {"min": 18.0, "max": 25.0}}


class _LeitorFake:
    def __init__(self, sequencia): self._seq = sequencia; self._i = 0
    def ler_todos(self, agora):
        vals = self._seq[min(self._i, len(self._seq) - 1)]; self._i += 1
        return [{"sensor_id": "SNR-T-01", "area_id": "AREA-T", "tipo_medida": "temperatura",
                 "valor": v, "unidade": "C", "protocolo_origem": "4-20ma",
                 "status_leitura": "ok", "cert_ver": 0, "cal_ganho": 1.0, "cal_offset": 0.0,
                 "timestamp": agora} for v in [vals]]
    def fechar(self): pass


class _ArquivoFake:
    def __init__(self): self.leituras = []
    def recuperar_pendentes(self, hoje): pass
    def registrar(self, leitura): self.leituras.append(leitura)
    def selar(self, data=None, caminho=None): pass


class _ArquivoAlarmesFake(_ArquivoFake):
    def __init__(self): self.eventos = []
    def registrar(self, *a, **k): pass
    def registrar_evento(self, evento): self.eventos.append(evento)


class _PubFake:
    def __init__(self): self.alarmes = []
    def conectar(self): pass
    def publicar(self, *a, **k): pass
    def publicar_alarme(self, hub_id, coletor_id, evento): self.alarmes.append(evento)
    def fechar(self): pass


def test_loop_emite_evento_para_arquivo_e_mqtt():
    cfg = _config()
    leitor = _LeitorFake([30.0, 30.0, 30.0])   # 3 leituras fora -> 1 entrada
    arquivo = _ArquivoFake()
    arquivo_alarmes = _ArquivoAlarmesFake()
    pub = _PubFake()
    detector = DetectorAlarme(main_mod.montar_limites(cfg), n=cfg.alarme_n, margem=cfg.alarme_margem)
    main_mod.executar(cfg, leitor, arquivo, pub, agora_fn=lambda: TS, parar=Event(),
                      max_ciclos=3, detector=detector, arquivo_alarmes=arquivo_alarmes)
    assert len(arquivo_alarmes.eventos) == 1
    assert arquivo_alarmes.eventos[0]["tipo_evento"] == "entrada_alarme"
    assert len(pub.alarmes) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_main_alarme.py -v`
Expected: FAIL — `AttributeError: module 'hub.main' has no attribute 'montar_limites'` (e `executar` sem params `detector`/`arquivo_alarmes`).

- [ ] **Step 3: Write minimal implementation**

Em `hub/main.py`, adicionar helper (topo, após imports):
```python
def montar_limites(config):
    limites = {}
    for bus in config.barramentos:
        for disp in bus.dispositivos:
            for canal in disp.canais:
                if canal.limite_min is not None or canal.limite_max is not None:
                    limites[canal.sensor_id] = {"min": canal.limite_min, "max": canal.limite_max}
    return limites
```

Estender a assinatura de `executar(...)` com `detector=None, arquivo_alarmes=None`. No boot, após `arquivo.recuperar_pendentes(...)`:
```python
    if arquivo_alarmes is not None:
        arquivo_alarmes.recuperar_pendentes(agora_fn().date())
```
No loop, dentro do `for leitura in leitor.ler_todos(agora):`, após `publicador.publicar(...)`:
```python
            if detector is not None:
                for evento in detector.avaliar(leitura):
                    if arquivo_alarmes is not None:
                        arquivo_alarmes.registrar_evento(evento)
                    publicador.publicar_alarme(config.hub_id, config.coletor_id, evento)
```
Após o loop, junto do `arquivo.selar(data_corrente)`:
```python
    if arquivo_alarmes is not None:
        arquivo_alarmes.selar(data_corrente)
```
No `_recarregar()`, recriar `arquivo_alarmes` e reconstruir `detector` a partir da nova config, se `arquivo_alarmes_factory`/`detector_factory` forem passados (espelhar o padrão de `arquivo_factory`). **Manter simples:** se não houver factories, o reload só troca leitor/arquivo (comportamento atual) e mantém detector/arquivo_alarmes — os limites raramente mudam no mesmo dia; documentar. (YAGNI: factories de alarme só se um teste exigir.)

Em `main(...)`, construir e passar os novos objetos:
```python
    from hub.arquivo_alarmes import ArquivoAlarmes
    from hub.detector_alarme import DetectorAlarme

    def _novo_arquivo_alarmes(c):
        return ArquivoAlarmes(c.coletor_id, c.hub_id, c.firmware_version, c.timezone_offset,
                              c.caminho_dados, assinador, cliente_id=c.cliente_id, site_id=c.site_id)

    arquivo_alarmes = _novo_arquivo_alarmes(cfg)
    estado_alarme_path = str(Path(cfg.caminho_dados).expanduser() / cfg.coletor_id / "estado_alarme.json")
    detector = DetectorAlarme(montar_limites(cfg), n=cfg.alarme_n, margem=cfg.alarme_margem,
                              estado_path=estado_alarme_path)
```
E passar `detector=detector, arquivo_alarmes=arquivo_alarmes` na chamada `executar(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub/tests/test_main_alarme.py hub/tests/ -v`
Expected: PASS (novos + regressão do hub verde). Rodar a suíte inteira do hub garante que a nova assinatura de `executar` não quebrou os testes existentes.

- [ ] **Step 5: Commit**

```bash
git add hub/main.py hub/tests/test_main_alarme.py
git commit -m "feat(hub): loop avalia alarme e emite p/ arquivo assinado + MQTT"
```

---

## Task 6: Serializar `limite_min/max` no config publicado (Odoo → hub)

**Files:**
- Modify: `api/config_publisher.py` (`serializar_config_hub`: bloco de leitura de sensores ~L96-102 e montagem do `canal` ~L127-174)
- Test: `api/tests/test_config_publisher_limite.py` (seguir o padrão de mock de `odoo_cliente.executar` usado nos testes existentes de `config_publisher`; procurar `test_config_publisher*` no repo e reusar o fake).

**Interfaces:**
- Consumes: modelo `sensor_monitor.alarm.threshold` (`sensor_id`, `limite_min`, `limite_max`; `unique(sensor_id)`).
- Produces: cada `canal` no config publicado ganha `limite_min`/`limite_max` **quando existe threshold** para o sensor. Sem threshold → chaves ausentes (hub trata como None, T2).

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_config_publisher_limite.py
from api import config_publisher


def _fake_executar(respostas):
    """respostas: função (model, metodo, *args, **kw) -> valor, roteando por (model, metodo)."""
    def ex(cliente, model, metodo, *args, **kw):
        return respostas(model, metodo, args, kw)
    return ex


def test_canal_recebe_limite_quando_ha_threshold(monkeypatch):
    def respostas(model, metodo, args, kw):
        if model == 'sensor_monitor.hub' and metodo == 'search_read':
            return [{'id': 1, 'config_version_desejada': 7}]
        if model == 'sensor_monitor.rs485.bus' and metodo == 'search_read':
            return [{'id': 10, 'serial_port': '/dev/ttyUSB0', 'baud_rate': 9600,
                     'parity': 'none', 'stop_bits': 1}]
        if model == 'sensor_monitor.modbus.device' and metodo == 'search_read':
            return [{'id': 20, 'slave_address': 1, 'profile_id': (30, 'P'),
                     'reconexao_n': 3, 'reconexao_m': 5, 'reconexao_k': 10}]
        if model == 'sensor_monitor.modbus.profile' and metodo == 'read':
            return [{'driver': 'n4aib16'}]
        if model == 'sensor_monitor.modbus.profile.register' and metodo == 'search':
            return [40]
        if model == 'sensor_monitor.sensor' and metodo == 'search_read':
            return [{'sensor_code': 'SNR-T-01', 'modbus_channel': 1, 'ma_in_min': 4,
                     'ma_in_max': 20, 'eng_out_min': 0, 'eng_out_max': 100,
                     'filtro_tipo': 'none', 'filtro_alpha': 0.0, 'unidade': 'C',
                     'protocolo_origem': 'rs485', 'area_id': (50, 'Area'),
                     'measurement_type_id': (60, 'Temp'), 'calibracao_vigente_id': False,
                     'usa_map': False, 'modbus_register_id': (40, 'R'),
                     'usa_faixa': False, 'faixa_min': 0, 'faixa_max': 0, 'id': 70}]
        if model == 'sensor_monitor.alarm.threshold' and metodo == 'search_read':
            return [{'sensor_id': (70, 'SNR-T-01'), 'limite_min': 18.0, 'limite_max': 25.0}]
        if model == 'sensor_monitor.area' and metodo == 'read':
            return [{'id': 50, 'area_code': 'AREA-T'}]
        if model == 'sensor_monitor.measurement.type' and metodo == 'read':
            return [{'id': 60, 'code': 'temperatura'}]
        if model == 'sensor_monitor.hub' and metodo == 'read':
            return [{'site_id': (80, 'Site')}]
        if model == 'sensor_monitor.site' and metodo == 'read':
            return [{'site_code': 'SITE-T', 'partner_id': (90, 'P')}]
        if model == 'res.partner' and metodo == 'read':
            return [{'ref': 'CLI-T'}]
        raise AssertionError(f"chamada inesperada: {model}.{metodo}")

    monkeypatch.setattr(config_publisher.odoo_cliente, 'executar', _fake_executar(respostas))
    cfg = config_publisher.serializar_config_hub(cliente=None, hub_code='HUB-T')
    canal = cfg['barramentos'][0]['dispositivos'][0]['canais'][0]
    assert canal['limite_min'] == 18.0
    assert canal['limite_max'] == 25.0


def test_canal_sem_threshold_nao_tem_limite(monkeypatch):
    # igual ao anterior, mas alarm.threshold.search_read -> []
    ...  # o implementador copia o dict acima trocando o ramo do threshold para `return []`
        # e afirma: assert 'limite_min' not in canal and 'limite_max' not in canal
```

**Nota:** o 2º teste repete o `respostas` do 1º trocando só o ramo `alarm.threshold` para `return []` — escrever por extenso (não deixar `...`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest api/tests/test_config_publisher_limite.py -v`
Expected: FAIL — `KeyError: 'limite_min'` / `AssertionError` (canal sem a chave).

- [ ] **Step 3: Write minimal implementation**

Em `serializar_config_hub`, dentro do laço `for dev in devices:`, após ler `sensores` (search_read, ~L102), buscar os thresholds em lote:
```python
            sensor_ids_odoo = [s['id'] for s in sensores]
            limites_por_sensor = {}
            if sensor_ids_odoo:
                thresholds = ex('sensor_monitor.alarm.threshold', 'search_read',
                                [('sensor_id', 'in', sensor_ids_odoo)],
                                fields=['sensor_id', 'limite_min', 'limite_max'])
                limites_por_sensor = {t['sensor_id'][0]: t for t in thresholds}
```
Na montagem do `canal` (dentro de `for s in sensores:`), após o bloco `usa_faixa`:
```python
                th = limites_por_sensor.get(s['id'])
                if th is not None:
                    canal['limite_min'] = th['limite_min']
                    canal['limite_max'] = th['limite_max']
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest api/tests/test_config_publisher_limite.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add api/config_publisher.py api/tests/test_config_publisher_limite.py
git commit -m "feat(api): config-publish serializa limite_min/max de alarme por canal"
```

---

## Task 7: Bridge assina `sentinela/alarme/#` → `pg_notify('alarme_ao_vivo')`

**Files:**
- Modify: `scripts/bridge_telemetria.py` (`_on_message` ~L45-65; `main` subscribe ~L74)
- Test: `scripts/tests/test_bridge_alarme.py` (criar; seguir padrão de testes de scripts se houver, senão pytest simples)

**Interfaces:**
- Consumes: payload MQTT de `publicar_alarme` (T4).
- Produces: ao receber mensagem em `sentinela/alarme/...`, emite `pg_notify('alarme_ao_vivo', <json>)` na conexão Timescale (payload com `sensor_id, area_id, valor, limite_min, limite_max, tipo_violacao, tipo_evento, timestamp, site_id, tipo:"alarme_ao_vivo"`). **NÃO** chama `timescale.inserir_leituras` para alarmes.

- [ ] **Step 1: Write the failing test**

```python
# scripts/tests/test_bridge_alarme.py
import json
from types import SimpleNamespace

import scripts.bridge_telemetria as bridge


class _Conn:
    def __init__(self): self.notifies = []; self.inseridos = []
    def execute(self, sql, params=None): self.notifies.append((sql, params))


def _msg(topic, payload):
    return SimpleNamespace(topic=topic, payload=json.dumps(payload).encode())


def test_alarme_vira_pg_notify_sem_inserir(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(bridge, '_site_code', lambda coletor_id: 'SITE-T')
    inseriu = []
    monkeypatch.setattr(bridge.timescale, 'inserir_leituras',
                        lambda *a, **k: inseriu.append(a))

    handler = bridge._on_message(conn)
    payload = {"timestamp": "2026-07-26T12:00:00+00:00", "sensor_id": "SNR-T-01",
               "area_id": "AREA-T", "tipo_medida": "temperatura",
               "tipo_evento": "entrada_alarme", "tipo_violacao": "acima_limite",
               "valor": 30.0, "limite_min": 18.0, "limite_max": 25.0}
    handler(None, None, _msg("sentinela/alarme/HUB-T/COL-T/SNR-T-01", payload))

    assert inseriu == []                       # não insere leitura
    assert len(conn.notifies) == 1
    sql, params = conn.notifies[0]
    assert 'pg_notify' in sql and 'alarme_ao_vivo' in (sql + str(params))
    enviado = json.loads(params[0] if params else sql.split("'")[-2])
    assert enviado["tipo"] == "alarme_ao_vivo"
    assert enviado["sensor_id"] == "SNR-T-01"
    assert enviado["site_id"] == "SITE-T"
    assert enviado["valor"] == 30.0


def test_telemetria_continua_inserindo(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(bridge, '_site_code', lambda coletor_id: 'SITE-T')
    inseriu = []
    monkeypatch.setattr(bridge.timescale, 'inserir_leituras',
                        lambda *a, **k: inseriu.append(a))
    handler = bridge._on_message(conn)
    handler(None, None, _msg("sentinela/telemetria/HUB-T/COL-T/SNR-T-01",
            {"timestamp": "2026-07-26T12:00:00+00:00", "valor": 20.0}))
    assert len(inseriu) == 1
    assert conn.notifies == []                 # telemetria não emite alarme
```

**Nota p/ implementador:** confirmar a API da conexão Timescale (`timescale.conectar`). Se for psycopg2/psycopg3, `pg_notify` via `conn.execute("SELECT pg_notify('alarme_ao_vivo', %s)", (json_str,))` e `conn.commit()`. Ajustar o placeholder (`%s`) e o commit conforme o driver real; o teste usa um `_Conn` fake com `.execute(sql, params)` — casar a assinatura chamada na implementação com a do fake.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest scripts/tests/test_bridge_alarme.py -v`
Expected: FAIL — o handler atual quebra em `partes[3]` OK mas trata como telemetria e chama `inserir_leituras` (ou dá KeyError em `p['valor']` conforme payload). Confirmar a falha, então implementar.

- [ ] **Step 3: Write minimal implementation**

Em `_on_message`, no início do `handler`, ramificar por tópico:
```python
    def handler(client, userdata, msg):
        try:
            partes = msg.topic.split('/')
            if partes[1] == 'alarme':          # sentinela/alarme/<hub>/<coletor>/<sensor>
                coletor_id = partes[3]
                p = json.loads(msg.payload)
                site = _site_code(coletor_id)
                if not site:
                    return
                evento = {**p, "site_id": site, "tipo": "alarme_ao_vivo"}
                conn.execute("SELECT pg_notify('alarme_ao_vivo', %s)", (json.dumps(evento),))
                if hasattr(conn, "commit"):
                    conn.commit()
                print(f'[bridge] ALARME {p.get("sensor_id")} {p.get("tipo_evento")} → SSE ({site})')
                return
            # ... telemetria (código atual, inalterado) ...
```
Manter o corpo de telemetria atual no `else`/fluxo abaixo. Em `main`, trocar a subscription para cobrir os dois tópicos:
```python
    c.on_connect = lambda cl, u, f, rc, p=None: (
        cl.subscribe('sentinela/telemetria/#', qos=0),
        cl.subscribe('sentinela/alarme/#', qos=0),
    )
```
E ajustar o print de boot para citar os dois tópicos.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest scripts/tests/test_bridge_alarme.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/bridge_telemetria.py scripts/tests/test_bridge_alarme.py
git commit -m "feat(bridge): assina sentinela/alarme e repassa como pg_notify(alarme_ao_vivo)"
```

---

## Task 8: Listener SSE do canal `alarme_ao_vivo`

**Files:**
- Modify: `api/live_listener.py` (adicionar canal + handler)
- Test: `api/tests/test_live_listener_alarme.py`

**Interfaces:**
- Consumes: `pg_notify('alarme_ao_vivo', json)` (T7); `api/live.publicar` (existente).
- Produces: `_receber_alarme(conn, pid, channel, payload)` → `live.publicar(dados['sensor_id'], dados)` (o payload já traz `site_id` e `tipo`); `escutar` registra `add_listener('alarme_ao_vivo', _receber_alarme)` além do canal de leituras.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_live_listener_alarme.py
import json

from api import live_listener


def test_receber_alarme_publica_no_live(monkeypatch):
    publicados = []
    monkeypatch.setattr(live_listener.live, 'publicar',
                        lambda sensor_code, payload: publicados.append((sensor_code, payload)))
    payload = json.dumps({"tipo": "alarme_ao_vivo", "sensor_id": "SNR-T-01",
                          "site_id": "SITE-T", "valor": 30.0, "tipo_evento": "entrada_alarme"})
    live_listener._receber_alarme(None, None, 'alarme_ao_vivo', payload)
    assert len(publicados) == 1
    sensor_code, enviado = publicados[0]
    assert sensor_code == "SNR-T-01"
    assert enviado["tipo"] == "alarme_ao_vivo"
    assert enviado["site_id"] == "SITE-T"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest api/tests/test_live_listener_alarme.py -v`
Expected: FAIL — `AttributeError: module 'api.live_listener' has no attribute '_receber_alarme'`

- [ ] **Step 3: Write minimal implementation**

Em `api/live_listener.py`, adicionar constante e handler, e registrar o segundo listener:
```python
CANAL_ALARME = 'alarme_ao_vivo'


def _receber_alarme(connection, pid, channel, payload):
    dados = json.loads(payload)
    live.publicar(dados['sensor_id'], dados)
```
Dentro de `escutar`, junto do `add_listener(CANAL, ...)`:
```python
                await conn.add_listener(CANAL, _receber_notificacao)
                await conn.add_listener(CANAL_ALARME, _receber_alarme)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest api/tests/test_live_listener_alarme.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/live_listener.py api/tests/test_live_listener_alarme.py
git commit -m "feat(api): listener do canal alarme_ao_vivo repassa p/ SSE via live.publicar"
```

---

## Task 9: Guard "um-aberto-por-sensor" no Odoo

**Files:**
- Modify: `ingestao/odoo_cliente.py` (`processar_entrada_alarme` ~L101-119)
- Test: `ingestao/tests/test_odoo_cliente_guard.py` (seguir o padrão de fake `executar` dos testes existentes de `odoo_cliente`)

**Interfaces:**
- Consumes: `executar(cliente, model, metodo, ...)` (existente).
- Produces: `processar_entrada_alarme` NÃO cria segundo evento se já houver um aberto (`timestamp_resolucao_sensor = False`) para o sensor; retorna o id do existente.

- [ ] **Step 1: Write the failing test**

```python
# ingestao/tests/test_odoo_cliente_guard.py
from ingestao import odoo_cliente


def test_entrada_nao_duplica_evento_aberto(monkeypatch):
    chamadas = []

    def fake_executar(cliente, model, metodo, *args, **kw):
        chamadas.append((model, metodo))
        if model == 'sensor_monitor.alarm.event' and metodo == 'search':
            return [55]                       # já existe aberto
        if metodo == 'create':
            raise AssertionError("não deveria criar quando já há aberto")
        return []

    monkeypatch.setattr(odoo_cliente, 'executar', fake_executar)
    evento = {'tipo_violacao': 'acima_limite', 'timestamp': '2026-07-26T12:00:00-03:00',
              'valor': 30.0, 'limite_min_vigente': 18.0, 'limite_max_vigente': 25.0}
    res = odoo_cliente.processar_entrada_alarme(None, evento, 70, 50, 20, 'HASH')
    assert res == 55


def test_entrada_cria_quando_nao_ha_aberto(monkeypatch):
    def fake_executar(cliente, model, metodo, *args, **kw):
        if model == 'sensor_monitor.alarm.event' and metodo == 'search':
            return []
        if metodo == 'create':
            return 99
        return []
    monkeypatch.setattr(odoo_cliente, 'executar', fake_executar)
    evento = {'tipo_violacao': 'acima_limite', 'timestamp': '2026-07-26T12:00:00-03:00',
              'valor': 30.0, 'limite_min_vigente': 18.0, 'limite_max_vigente': 25.0}
    assert odoo_cliente.processar_entrada_alarme(None, evento, 70, 50, 20, 'HASH') == 99
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest ingestao/tests/test_odoo_cliente_guard.py -v`
Expected: FAIL — `test_entrada_nao_duplica...` falha (a função hoje sempre cria; a asserção do `create` dispara).

- [ ] **Step 3: Write minimal implementation**

No início de `processar_entrada_alarme`, antes de montar `valores`:
```python
    abertos = executar(
        cliente, 'sensor_monitor.alarm.event', 'search',
        [('sensor_id', '=', sensor_odoo_id), ('timestamp_resolucao_sensor', '=', False)],
        limit=1,
    )
    if abertos:
        return abertos[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest ingestao/tests/test_odoo_cliente_guard.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ingestao/odoo_cliente.py ingestao/tests/test_odoo_cliente_guard.py
git commit -m "feat(ingestao): guard um-aberto-por-sensor em processar_entrada_alarme"
```

---

## Task 10: Frontend — `subscribeAlarme` no LiveApi

**Files:**
- Modify: `frontend/src/lib/api/contracts.ts` (interface `LiveApi`)
- Modify: `frontend/src/lib/api/real/liveApi.ts` (`onmessage` branch + listeners + `subscribeAlarme`)
- Modify: `frontend/src/lib/api/mock/liveApi.ts` (stub `subscribeAlarme`)
- Modify: `frontend/src/lib/types.ts` (tipo `LiveAlarme`)
- Test: `frontend/src/lib/api/real/liveApi.test.ts` (adicionar caso; usar o stub de EventSource já usado nos testes existentes)

**Interfaces:**
- Produces:
  - `type LiveAlarme = { sensor_code: string; area_code: string; tipo_evento: 'entrada_alarme'|'saida_alarme'; tipo_violacao: string; valor: number; timestamp: string }`
  - `LiveApi.subscribeAlarme(cb: (a: LiveAlarme) => void): () => void`
  - `onmessage` ramifica: `data.tipo === 'alarme_ao_vivo'` → notifica listeners de alarme (mapeando `sensor_id`→`sensor_code`, `area_id`→`area_code`) e **não** processa como leitura.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/lib/api/real/liveApi.test.ts (adicionar)
import { describe, it, expect, vi } from 'vitest'
import { realLiveApi } from './liveApi'

// Reusar o stub de EventSource dos testes existentes deste arquivo. Se o stub
// expõe uma forma de injetar mensagens (ex.: `lastSource.emit(data)`), usar.
describe('subscribeAlarme', () => {
  it('entrega payload alarme_ao_vivo e não o trata como leitura', () => {
    const alarmes: unknown[] = []
    realLiveApi.subscribe('', () => {})            // abre o EventSource compartilhado
    const off = realLiveApi.subscribeAlarme((a) => alarmes.push(a))
    // dispara uma mensagem SSE simulada de alarme via o stub:
    // (adaptar à mecânica do stub deste arquivo de teste)
    emitirMensagemSSE({ tipo: 'alarme_ao_vivo', sensor_id: 'SNR-T-01', area_id: 'AREA-T',
                        tipo_evento: 'entrada_alarme', tipo_violacao: 'acima_limite',
                        valor: 30.0, timestamp: '2026-07-26T12:00:00+00:00' })
    expect(alarmes).toHaveLength(1)
    expect((alarmes[0] as any).sensor_code).toBe('SNR-T-01')
    expect((alarmes[0] as any).area_code).toBe('AREA-T')
    off()
  })
})
```
**Nota:** `emitirMensagemSSE` é pseudocódigo — o implementador liga na mecânica real do stub de `EventSource` já presente em `liveApi.test.ts` (procurar como os testes existentes disparam `onmessage`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela/frontend && npx vitest run src/lib/api/real/liveApi.test.ts -t subscribeAlarme`
Expected: FAIL — `realLiveApi.subscribeAlarme is not a function`

- [ ] **Step 3: Write minimal implementation**

Em `types.ts`:
```typescript
export type LiveAlarme = {
  sensor_code: string
  area_code: string
  tipo_evento: 'entrada_alarme' | 'saida_alarme'
  tipo_violacao: string
  valor: number
  timestamp: string
}
```
Em `contracts.ts`, na interface `LiveApi`, adicionar:
```typescript
  subscribeAlarme(cb: (a: LiveAlarme) => void): () => void
```
Em `real/liveApi.ts`, nível de módulo:
```typescript
const alarmeListeners = new Set<(a: import('../../types').LiveAlarme) => void>()
```
No `es.onmessage`, no topo:
```typescript
    const data = JSON.parse(event.data)
    if (data.tipo === 'alarme_ao_vivo') {
      const alarme = {
        sensor_code: data.sensor_id, area_code: data.area_id,
        tipo_evento: data.tipo_evento, tipo_violacao: data.tipo_violacao,
        valor: data.valor, timestamp: data.timestamp,
      }
      alarmeListeners.forEach((cb) => cb(alarme))
      return
    }
    const { sensor_id, time, valor } = data
```
(remover o `const { sensor_id, time, valor } = JSON.parse(event.data)` antigo — agora vem de `data`).
No objeto `realLiveApi`, adicionar:
```typescript
  subscribeAlarme(cb) {
    alarmeListeners.add(cb)
    return () => { alarmeListeners.delete(cb) }
  },
```
Em `mock/liveApi.ts`, adicionar stub que satisfaz o tipo:
```typescript
  subscribeAlarme() { return () => {} },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela/frontend && npx vitest run src/lib/api/real/liveApi.test.ts && npx tsc --noEmit`
Expected: PASS + tsc limpo.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/contracts.ts frontend/src/lib/api/real/liveApi.ts frontend/src/lib/api/mock/liveApi.ts frontend/src/lib/types.ts frontend/src/lib/api/real/liveApi.test.ts
git commit -m "feat(front): LiveApi.subscribeAlarme consome eventos alarme_ao_vivo do SSE"
```

---

## Task 11: Frontend — toast ao vivo + reconciliação/fallback

**Files:**
- Modify: `frontend/src/components/ToastContainer.tsx`
- Test: `frontend/src/components/ToastContainer.test.tsx` (adicionar casos)

**Interfaces:**
- Consumes: `useLive().subscribeAlarme` / `realLiveApi.subscribeAlarme` (T10) via a camada de api já usada pelo componente; `LiveAlarme` (T10).
- Produces: comportamento —
  1. Assina alarmes ao vivo; ao chegar um `entrada_alarme`/`saida_alarme`, mostra um `Toast` **imediatamente** (efêmero, auto-dismiss como hoje).
  2. Registra a chave `${sensor_code}|${timestamp}` (arredondado ao segundo) das que já toastou ao vivo.
  3. Quando o poll `/alarmes` traz um evento durável cuja chave já foi toasteada ao vivo → **suprime** o toast durável (o card + flash `isNew` no painel bastam).
  4. **Fallback:** evento durável sem chave ao vivo correspondente → toasta normalmente (como hoje). Nenhum alarme fica sem sinal.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/ToastContainer.test.tsx (adicionar)
// Estratégia: mockar o subscribeAlarme da api (vi.mock do módulo de api usado
// pelo ToastContainer) para capturar o callback e dispará-lo no teste; e
// re-renderizar com uma nova lista de alarms (poll) contendo o mesmo evento.

it('mostra toast ao vivo imediatamente e não duplica quando o durável chega', async () => {
  // 1. render com alarms=[] (baseline)
  // 2. dispara subscribeAlarme com { sensor_code:'SNR-T-01', timestamp:'2026-07-26T12:00:00Z', tipo_evento:'entrada_alarme', ... }
  //    -> espera 1 Toast visível (getByText contendo o sensor)
  // 3. re-render com alarms=[{ id:1, sensor_code:'SNR-T-01', timestamp_deteccao: Date.parse('2026-07-26T12:00:00Z'), ... }]
  //    -> continua 1 Toast (não 2): o durável foi suprimido
})

it('fallback: alarme durável sem sinal ao vivo ainda toasta', async () => {
  // render baseline; re-render com um alarm novo do poll SEM ter havido subscribeAlarme
  // -> espera 1 Toast (comportamento atual preservado)
})
```
**Nota:** escrever os dois testes por extenso ligando na mecânica de mock de api já usada nos testes do frontend (ver como `ToastContainer.test.tsx`/`queries.test.tsx` mockam a camada de api). Chave de reconciliação = `sensor_code + timestamp` arredondado ao segundo (o durável usa epoch ms `timestamp_deteccao`; converter ambos para ISO-segundo antes de comparar).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/afonso/docker/odoo_sentinela/frontend && npx vitest run src/components/ToastContainer.test.tsx`
Expected: FAIL — toast ao vivo não existe / durável duplica.

- [ ] **Step 3: Write minimal implementation**

Em `ToastContainer.tsx`:
- Adicionar um `useEffect` que chama `subscribeAlarme` (via a api já importada onde o componente busca dados ao vivo — usar o mesmo ponto de acesso que `useAlarms`/`liveApi` expõe no app; se necessário, importar `liveApi` da camada `../lib/api`).
- Manter um `useRef<Set<string>>` `liveKeys` com as chaves toasteadas ao vivo.
- Ao receber um alarme ao vivo: construir um `AlarmEvent` sintético mínimo para o `Toast` (id negativo/efêmero único, `sensor_code`, `area_code`, `status` = `tipo_evento==='saida_alarme' ? 'resolvido' : 'aberto'`, `timestamp_deteccao` = `Date.parse(timestamp)`), adicioná-lo a `visible` com auto-dismiss; registrar a chave.
- No `useEffect` existente do poll (diff por `id`), antes de disparar o toast de um novo alarme durável, checar se `liveKeys` tem a chave `${a.sensor_code}|${isoSegundo(a.timestamp_deteccao)}`; se tiver, marcar como visto (não toastar). Senão, toastar (fallback, comportamento atual).
- Helper `isoSegundo(ts)` para normalizar epoch-ms e ISO-string ao mesmo segundo.

**Cuidado (id):** o `Toast` e o `dismiss`/`timers` usam `id: number`. Para toasts ao vivo, gerar ids efêmeros únicos que não colidam com ids do Odoo (ex.: contador decrescente a partir de `-1`). O `key` do `<Toast>` e o `dismiss(id)` continuam funcionando por id.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/afonso/docker/odoo_sentinela/frontend && npx vitest run src/components/ToastContainer.test.tsx && npx tsc --noEmit`
Expected: PASS + tsc limpo.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ToastContainer.tsx frontend/src/components/ToastContainer.test.tsx
git commit -m "feat(front): toast de alarme ao vivo (SSE) com reconciliação e fallback do poll"
```

---

## Final: verificação de ponta a ponta

- [ ] **Step F1: Suíte completa**

```bash
cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. python -m pytest hub api ingestao scripts -q
cd /home/afonso/docker/odoo_sentinela/frontend && npx vitest run && npx tsc --noEmit && npm run build
```
Expected: tudo verde.

- [ ] **Step F2: Verificação no hardware/stack real (manual, guiada)**

Com a stack de pé (ver `ACESSOS.local.md`): republicar config do hub (agora com `limite_min/max`), confirmar que o hub baixou; provocar (ou aguardar) um sensor real cruzar o limite por ≥3 leituras `ok`; confirmar no dashboard (localhost:5199): **toast vermelho na hora** e, segundos depois, **card no painel de alarmes** (com data DD/MM). Conferir `alarmes.txt` assinado no SFTP e o evento aberto no Odoo. **Não** apagar dados (regra de produção persistente).

---

## Self-Review (preenchido pelo autor do plano)

- **Cobertura do spec:** §1 limiar→hub (T6/T2), §2 state machine (T1), §3 saídas arquivo+MQTT (T3/T4/T5), §4 ingestão bridge+SSE (T7/T8) e arquivo→Odoo (existente + guard T9), §5 guard (T9), §6 frontend toast+reconciliação (T10/T11), testes (todas). ✔
- **Placeholders:** os `...` em T6 (2º teste) e T11 (testes) estão marcados com nota explícita "escrever por extenso"; são pontos onde o código exato depende de mecânica de mock local (stub de EventSource / fake de `executar`) que o implementador liga ao padrão vizinho. Não são lacunas de design.
- **Consistência de tipos:** evento dict (T1) consumido igual em T3/T4/T5; payload MQTT (T4) casa com o parse do bridge (T7) e o discriminador `tipo` (T7→T8→T10); `LiveAlarme` (T10) consumido em T11. ✔
- **Risco conhecido (documentar na implementação):** `limite_min/max` são `Float` no Odoo (0.0 ≠ "sem limite"). Hoje todo sensor tem ambos setados com valores reais (confirmado no DB). Modelar "sem limite inferior/superior" (ex.: sensor só-máximo) exigiria flags `has_min/has_max` no modelo — **fora de escopo**; se um sensor precisar de bound único, tratar como follow-up.
