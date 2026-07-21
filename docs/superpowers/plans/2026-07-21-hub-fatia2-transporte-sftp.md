# Hub — Fatia 2 / Transporte T1: Espinha de arquivo SFTP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O Hub envia os arquivos `.txt` selados ao servidor via SFTP (auth por chave SSH ed25519), e o servidor ingere cada upload (valida → Timescale/Odoo/ledger).

**Architecture:** Lado-Hub (este Pi, TDD aqui): identidade SSH + cliente SFTP (`EnviadorSftp` com transporte injetável + `TransporteParamiko`) + estado de envio por índice JSON + wiring no `main`. Lado-servidor (código + runbook, Afonso implanta no LAN): serviço SFTPGo no compose + `ingestao/receber_upload.py` disparado pelo Event Manager pós-upload.

**Tech Stack:** Python 3.13, `paramiko` (SFTP), `cryptography` (Ed25519 OpenSSH), `PyYAML`, `pytest`. Dev venv em `.venv/`.

## Global Constraints

- **Não reenviar:** um arquivo já no índice `_enviados.json` nunca é reenviado.
- **Só selados sobem:** apenas arquivos com rodapé/assinatura (`hub.arquivo_diario._esta_selado`) são enviados.
- **Falha de envio é não-fatal:** exceção no transporte deixa o arquivo pendente (retry no próximo `varrer`), nunca derruba o loop.
- **Auth SFTP:** chave SSH **ed25519** por hub; sem senha em disco. A chave SSH é separada da chave EC de assinatura.
- **T1 sem ack MQTT:** a ingestão só processa e grava no ledger; feedback de volta é o T2.
- **Ausência do bloco `sftp` na config → enviador desligado** (Fatia 1 segue funcionando).
- **Assinatura de `ingerir_arquivo`:** `ingerir_arquivo(caminho, registro_path, dsn, cliente_odoo)`; conexão Odoo via `odoo_cliente.conectar(url, db, usuario, senha)`.
- **Comandos com venv ativo:** `cd /home/fitadigital/odoo_sentinela && . .venv/bin/activate`.

---

## File Structure

```
hub/
  identidade_ssh.py         # NOVO — gera/carrega par ed25519, pubkey OpenSSH
  enviador_sftp.py          # NOVO — EnviadorSftp (lógica) + TransporteParamiko (impl)
  config.py                 # MODIFICAR — bloco sftp opcional
  main.py                   # MODIFICAR — constrói enviador; varrer() por ciclo + no fim
  requirements.txt          # MODIFICAR — + paramiko
  tests/
    test_identidade_ssh.py  # NOVO
    test_enviador_sftp.py    # NOVO
    test_config.py           # MODIFICAR — casos do bloco sftp
    test_main.py             # MODIFICAR — varrer chamado quando há enviador
ingestao/
  receber_upload.py         # NOVO — entrypoint pós-upload do SFTPGo
  tests/test_receber_upload.py  # NOVO
docker-compose.yml          # MODIFICAR — serviço sftpgo
docs/runbooks/
  transporte-sftp-servidor.md   # NOVO — runbook de deploy/verificação do servidor
```

---

### Task 1: `hub/identidade_ssh.py` — identidade SSH do Hub (ed25519)

**Files:**
- Create: `hub/identidade_ssh.py`, `hub/tests/test_identidade_ssh.py`

**Interfaces:**
- Produces: `carregar_ou_criar_chave_ssh(caminho) -> Ed25519PrivateKey` (cria o arquivo privado OpenSSH em `caminho` com modo 0600 e o `.pub` ao lado, se não existirem); `pubkey_openssh(chave) -> str` (linha `ssh-ed25519 AAAA...`).

- [ ] **Step 1: Escrever o teste falho**

Create `hub/tests/test_identidade_ssh.py`:
```python
from hub import identidade_ssh


def test_cria_par_e_pubkey_openssh(tmp_path):
    caminho = tmp_path / "ssh_hub"
    chave = identidade_ssh.carregar_ou_criar_chave_ssh(caminho)
    assert caminho.exists()
    assert caminho.with_suffix(".pub").exists()
    pub = identidade_ssh.pubkey_openssh(chave)
    assert pub.startswith("ssh-ed25519 ")


def test_idempotente_recarrega_mesma_chave(tmp_path):
    caminho = tmp_path / "ssh_hub"
    a = identidade_ssh.carregar_ou_criar_chave_ssh(caminho)
    b = identidade_ssh.carregar_ou_criar_chave_ssh(caminho)
    assert identidade_ssh.pubkey_openssh(a) == identidade_ssh.pubkey_openssh(b)
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_identidade_ssh.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'hub.identidade_ssh'`)

- [ ] **Step 3: Implementar `hub/identidade_ssh.py`**

```python
"""Identidade SSH do Hub para o transporte SFTP (par ed25519).

Separada da chave EC de assinatura (contrato/identidade): esta autentica o
upload no SFTPGo; aquela assina o conteúdo dos arquivos.
"""
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def pubkey_openssh(chave) -> str:
    return chave.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()


def carregar_ou_criar_chave_ssh(caminho):
    caminho = Path(caminho).expanduser()
    if caminho.exists():
        return serialization.load_ssh_private_key(caminho.read_bytes(), password=None)
    chave = Ed25519PrivateKey.generate()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(chave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    os.chmod(caminho, 0o600)
    caminho.with_suffix(".pub").write_text(pubkey_openssh(chave) + "\n")
    return chave
```

- [ ] **Step 4: Rodar — deve passar**

Run: `python -m pytest hub/tests/test_identidade_ssh.py -q`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add hub/identidade_ssh.py hub/tests/test_identidade_ssh.py
git commit -m "feat(hub): identidade_ssh.py — par ed25519 do Hub para SFTP"
```

---

### Task 2: `hub/config.py` — bloco `sftp` opcional

**Files:**
- Modify: `hub/config.py`
- Modify: `hub/tests/test_config.py`

**Interfaces:**
- Produces: dataclass `SftpConfig(host, port:int, username, ssh_key_path, remote_dir)`; campo novo `HubConfig.sftp: SftpConfig|None` (None quando ausente). `carregar_config` valida `host`/`username`/`ssh_key_path` obrigatórios quando `sftp` presente.

- [ ] **Step 1: Escrever os testes falhos**

Append em `hub/tests/test_config.py`:
```python
SFTP_BLOCO = """
    sftp:
      host: 192.168.0.10
      port: 2022
      username: hub-0001A2F3
      ssh_key_path: /tmp/ssh_hub
      remote_dir: /uploads
"""


def test_sem_sftp_fica_none(tmp_path):
    cfg = config.carregar_config(_escrever(tmp_path, VALIDA))
    assert cfg.sftp is None


def test_com_sftp_carrega(tmp_path):
    cfg = config.carregar_config(_escrever(tmp_path, VALIDA + SFTP_BLOCO))
    assert cfg.sftp.host == "192.168.0.10"
    assert cfg.sftp.port == 2022
    assert cfg.sftp.username == "hub-0001A2F3"
    assert cfg.sftp.remote_dir == "/uploads"


def test_sftp_sem_host_falha(tmp_path):
    ruim = VALIDA + SFTP_BLOCO.replace("host: 192.168.0.10", "port: 2022")
    with pytest.raises(ValueError):
        config.carregar_config(_escrever(tmp_path, ruim))
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_config.py -q`
Expected: FAIL (`AttributeError: 'HubConfig' object has no attribute 'sftp'` no primeiro teste novo)

- [ ] **Step 3: Implementar as mudanças em `hub/config.py`**

Adicionar a dataclass após `BarramentoConfig`:
```python
@dataclass
class SftpConfig:
    host: str
    port: int
    username: str
    ssh_key_path: str
    remote_dir: str
```

Adicionar o campo ao final de `HubConfig` (após `barramentos`):
```python
    sftp: object = None
```

Em `carregar_config`, antes do `return`, montar o `sftp`:
```python
    sftp = None
    bloco_sftp = dados.get("sftp")
    if bloco_sftp:
        for campo in ("host", "username", "ssh_key_path"):
            if not bloco_sftp.get(campo):
                raise ValueError(f"sftp.{campo} é obrigatório quando 'sftp' está presente")
        sftp = SftpConfig(
            host=bloco_sftp["host"], port=int(bloco_sftp.get("port", 22)),
            username=bloco_sftp["username"], ssh_key_path=bloco_sftp["ssh_key_path"],
            remote_dir=bloco_sftp.get("remote_dir", "/uploads"),
        )
```

E passar `sftp=sftp` na construção do `HubConfig`:
```python
    return HubConfig(
        hub_id=dados["hub_id"], coletor_id=dados["coletor_id"],
        firmware_version=dados["firmware_version"], timezone_offset=dados["timezone_offset"],
        intervalo_leitura_s=int(dados["intervalo_leitura_s"]),
        caminho_chave=dados["caminho_chave"], caminho_dados=dados["caminho_dados"],
        mqtt_host=mqtt.get("host", "localhost"), mqtt_port=int(mqtt.get("port", 1883)),
        barramentos=barramentos, sftp=sftp,
    )
```

- [ ] **Step 4: Rodar — deve passar (novos + antigos)**

Run: `python -m pytest hub/tests/test_config.py -q`
Expected: PASS (3 antigos + 3 novos = 6)

- [ ] **Step 5: Atualizar `hub/config.example.yaml`**

Adicionar ao final do arquivo:
```yaml
sftp:                                # opcional — sem este bloco, o envio fica desligado
  host: 192.168.0.10                 # IP do servidor no LAN
  port: 2022
  username: hub-0001A2F3
  ssh_key_path: ~/sentinela-hub/chaves/ssh_hub
  remote_dir: /uploads
```

- [ ] **Step 6: Commit**

```bash
git add hub/config.py hub/config.example.yaml hub/tests/test_config.py
git commit -m "feat(hub): config — bloco sftp opcional (host/port/username/chave/remote_dir)"
```

---

### Task 3: `hub/enviador_sftp.py` — lógica de envio (varredura + estado)

**Files:**
- Create: `hub/enviador_sftp.py`, `hub/tests/test_enviador_sftp.py`

**Interfaces:**
- Consumes: `hub.arquivo_diario._esta_selado(caminho: Path) -> bool`.
- Produces: `Transporte` (Protocol com `enviar(caminho_local: str, nome_remoto: str) -> None`, raise em falha); `EnviadorSftp(coletor_id, caminho_dados, transporte, caminho_estado=None)` com `varrer() -> list[str]` (nomes enviados nesta varredura).

- [ ] **Step 1: Escrever o teste falho**

Create `hub/tests/test_enviador_sftp.py`:
```python
import json

from hub.enviador_sftp import EnviadorSftp

COLETOR = "COL-RS485-BUS0"

CABECALHO = "# schema_version: 1\n# coletor_id: COL-RS485-BUS0\n"
CORPO = "1|2026-07-21T00:01:00-03:00|SNR|AREA|temperatura|19.8|C|4-20ma|ok|abc\n"
RODAPE_SELADO = "# total_linhas: 1\n# hash_final: abc\n# assinatura: ZZ==\n"


def _dir(tmp_path):
    d = tmp_path / "dados" / COLETOR
    d.mkdir(parents=True)
    return d


def _selado(d, nome):
    (d / nome).write_text(CABECALHO + CORPO + RODAPE_SELADO)


def _aberto(d, nome):
    (d / nome).write_text(CABECALHO + CORPO)  # sem rodapé/assinatura


class _TransporteFake:
    def __init__(self, falhar=False):
        self.enviados = []
        self.falhar = falhar
    def enviar(self, caminho_local, nome_remoto):
        if self.falhar:
            raise OSError("sem rede")
        self.enviados.append(nome_remoto)


def test_envia_selado_nao_enviado(tmp_path):
    d = _dir(tmp_path)
    _selado(d, "2026-07-21_leituras.txt")
    t = _TransporteFake()
    env = EnviadorSftp(COLETOR, tmp_path / "dados", t)
    enviados = env.varrer()
    assert enviados == ["2026-07-21_leituras.txt"]
    assert t.enviados == ["2026-07-21_leituras.txt"]


def test_ignora_aberto_nao_selado(tmp_path):
    d = _dir(tmp_path)
    _aberto(d, "2026-07-22_leituras.txt")
    t = _TransporteFake()
    env = EnviadorSftp(COLETOR, tmp_path / "dados", t)
    assert env.varrer() == []
    assert t.enviados == []


def test_nao_reenvia(tmp_path):
    d = _dir(tmp_path)
    _selado(d, "2026-07-21_leituras.txt")
    t = _TransporteFake()
    env = EnviadorSftp(COLETOR, tmp_path / "dados", t)
    env.varrer()
    assert env.varrer() == []          # segunda varredura não reenvia
    assert t.enviados == ["2026-07-21_leituras.txt"]


def test_falha_deixa_pendente_para_retry(tmp_path):
    d = _dir(tmp_path)
    _selado(d, "2026-07-21_leituras.txt")
    falho = _TransporteFake(falhar=True)
    env = EnviadorSftp(COLETOR, tmp_path / "dados", falho)
    assert env.varrer() == []          # falhou, nada registrado
    ok = _TransporteFake()
    env2 = EnviadorSftp(COLETOR, tmp_path / "dados", ok)
    assert env2.varrer() == ["2026-07-21_leituras.txt"]   # retry envia


def test_estado_persiste_entre_instancias(tmp_path):
    d = _dir(tmp_path)
    _selado(d, "2026-07-21_leituras.txt")
    EnviadorSftp(COLETOR, tmp_path / "dados", _TransporteFake()).varrer()
    estado = json.loads((d / "_enviados.json").read_text())
    assert "2026-07-21_leituras.txt" in estado
    # nova instância lê o estado e não reenvia
    env2 = EnviadorSftp(COLETOR, tmp_path / "dados", _TransporteFake())
    assert env2.varrer() == []
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_enviador_sftp.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'hub.enviador_sftp'`)

- [ ] **Step 3: Implementar a parte lógica de `hub/enviador_sftp.py`**

```python
"""Envio dos arquivos selados ao servidor via SFTP.

EnviadorSftp = lógica (varre selados não-enviados, envia, registra estado,
retry natural em falha). O transporte concreto é injetado (Protocol),
permitindo testar a lógica sem rede. TransporteParamiko é a impl real (Task 4).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from hub.arquivo_diario import _esta_selado


class Transporte(Protocol):
    def enviar(self, caminho_local: str, nome_remoto: str) -> None: ...


class EnviadorSftp:
    def __init__(self, coletor_id, caminho_dados, transporte, caminho_estado=None):
        self._dir = Path(caminho_dados).expanduser() / coletor_id
        self._transporte = transporte
        self._estado_path = Path(caminho_estado) if caminho_estado else self._dir / "_enviados.json"
        self._enviados = self._carregar_estado()

    def _carregar_estado(self):
        if self._estado_path.exists():
            return json.loads(self._estado_path.read_text())
        return {}

    def _persistir(self):
        self._estado_path.parent.mkdir(parents=True, exist_ok=True)
        self._estado_path.write_text(json.dumps(self._enviados, indent=2))

    def varrer(self):
        enviados_agora = []
        for caminho in sorted(self._dir.glob("*_leituras.txt")):
            nome = caminho.name
            if nome in self._enviados or not _esta_selado(caminho):
                continue
            try:
                self._transporte.enviar(str(caminho), nome)
            except Exception:
                continue  # falha não-fatal; retry no próximo varrer
            self._enviados[nome] = {"enviado_em": datetime.now(timezone.utc).isoformat()}
            self._persistir()
            enviados_agora.append(nome)
        return enviados_agora
```

- [ ] **Step 4: Rodar — deve passar**

Run: `python -m pytest hub/tests/test_enviador_sftp.py -q`
Expected: PASS (5 testes)

- [ ] **Step 5: Commit**

```bash
git add hub/enviador_sftp.py hub/tests/test_enviador_sftp.py
git commit -m "feat(hub): enviador_sftp — varredura de selados, estado e retry (transporte injetável)"
```

---

### Task 4: `TransporteParamiko` — impl SFTP real (teste com mock)

**Files:**
- Modify: `hub/enviador_sftp.py` (adiciona a classe)
- Modify: `hub/tests/test_enviador_sftp.py` (adiciona o teste)
- Modify: `hub/requirements.txt` (+ paramiko)

**Interfaces:**
- Produces: `TransporteParamiko(host, port, username, ssh_key_path, remote_dir)` implementando `enviar(caminho_local, nome_remoto)` via paramiko (auth por chave ed25519).

- [ ] **Step 1: Escrever o teste falho (dirige paramiko mockado)**

Append em `hub/tests/test_enviador_sftp.py`:
```python
from unittest import mock

from hub.enviador_sftp import TransporteParamiko


def test_transporte_paramiko_conecta_autentica_e_poe(tmp_path):
    from hub import identidade_ssh
    chave_path = tmp_path / "ssh_hub"
    identidade_ssh.carregar_ou_criar_chave_ssh(chave_path)

    t = TransporteParamiko("192.168.0.10", 2022, "hub-1", str(chave_path), "/uploads")
    with mock.patch("paramiko.SSHClient") as MockClient, \
         mock.patch("paramiko.Ed25519Key") as MockKey:
        cliente = MockClient.return_value
        sftp = cliente.open_sftp.return_value
        t.enviar("/local/2026-07-21_leituras.txt", "2026-07-21_leituras.txt")

    MockKey.from_private_key_file.assert_called_once_with(str(chave_path))
    _, kwargs = cliente.connect.call_args
    assert kwargs["port"] == 2022
    assert kwargs["username"] == "hub-1"
    sftp.put.assert_called_once_with("/local/2026-07-21_leituras.txt",
                                     "/uploads/2026-07-21_leituras.txt")
    cliente.close.assert_called_once()
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_enviador_sftp.py::test_transporte_paramiko_conecta_autentica_e_poe -q`
Expected: FAIL (`ImportError: cannot import name 'TransporteParamiko'`)

- [ ] **Step 3: Adicionar paramiko ao requirements e implementar a classe**

Adicionar `paramiko>=3` em `hub/requirements.txt`.

Append em `hub/enviador_sftp.py`:
```python
class TransporteParamiko:
    def __init__(self, host, port, username, ssh_key_path, remote_dir):
        self._host = host
        self._port = port
        self._username = username
        self._ssh_key_path = str(Path(ssh_key_path).expanduser())
        self._remote_dir = remote_dir.rstrip("/")

    def enviar(self, caminho_local, nome_remoto):
        import paramiko
        chave = paramiko.Ed25519Key.from_private_key_file(self._ssh_key_path)
        cliente = paramiko.SSHClient()
        cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cliente.connect(self._host, port=self._port, username=self._username,
                        pkey=chave, look_for_keys=False, allow_agent=False)
        try:
            sftp = cliente.open_sftp()
            sftp.put(caminho_local, f"{self._remote_dir}/{nome_remoto}")
            sftp.close()
        finally:
            cliente.close()
```

- [ ] **Step 4: Rodar — deve passar (arquivo inteiro)**

Run: `python -m pytest hub/tests/test_enviador_sftp.py -q`
Expected: PASS (6 testes)

- [ ] **Step 5: Commit**

```bash
git add hub/enviador_sftp.py hub/tests/test_enviador_sftp.py hub/requirements.txt
git commit -m "feat(hub): TransporteParamiko — SFTP real com auth ed25519"
```

---

### Task 5: Wiring no `hub/main.py`

Constrói o enviador quando `cfg.sftp` existe e chama `varrer()` a cada ciclo e no encerramento.

**Files:**
- Modify: `hub/main.py`
- Modify: `hub/tests/test_main.py`

**Interfaces:**
- Consumes: `hub.enviador_sftp.EnviadorSftp`, `hub.enviador_sftp.TransporteParamiko`, `hub.identidade_ssh.carregar_ou_criar_chave_ssh`.
- Produces: `executar(config, leitor, arquivo, publicador, agora_fn, parar, max_ciclos=None, enviador=None)` — chama `enviador.varrer()` por ciclo e após a selagem final, se `enviador` não-None.

- [ ] **Step 1: Escrever o teste falho**

Append em `hub/tests/test_main.py`:
```python
class _EnviadorFake:
    def __init__(self):
        self.varreduras = 0
    def varrer(self):
        self.varreduras += 1
        return []


def test_executar_chama_varrer_quando_ha_enviador(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(CFG).format(chave=tmp_path / "k.pem", dados=tmp_path / "dados"))
    cfg = config.carregar_config(p)
    arq = ArquivoDiario(cfg.coletor_id, cfg.hub_id, cfg.firmware_version,
                        cfg.timezone_offset, cfg.caminho_dados, AssinadorSoftware(cfg.caminho_chave))
    envio = _EnviadorFake()
    agora = datetime(2026, 7, 21, 0, 1, tzinfo=TZ)
    hub_main.executar(cfg, _LeitorFake(), arq, _PubFake(), agora_fn=lambda: agora,
                      parar=Event(), max_ciclos=2, enviador=envio)
    # 2 ciclos + 1 varredura final no encerramento
    assert envio.varreduras == 3
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest hub/tests/test_main.py -q`
Expected: FAIL (`TypeError: executar() got an unexpected keyword argument 'enviador'`)

- [ ] **Step 3: Modificar `hub/main.py`**

Trocar a assinatura e o corpo de `executar` para incluir o `enviador`:
```python
def executar(config, leitor, arquivo, publicador, agora_fn, parar, max_ciclos=None, enviador=None):
    arquivo.recuperar_pendentes(agora_fn().date())
    publicador.conectar()
    ciclos = 0
    data_corrente = None
    while not parar.is_set():
        agora = agora_fn()
        data_corrente = agora.date().isoformat()
        for leitura in leitor.ler_todos(agora):
            arquivo.registrar(leitura)
            publicador.publicar(config.hub_id, config.coletor_id, leitura)
        if enviador is not None:
            enviador.varrer()
        ciclos += 1
        if max_ciclos is not None and ciclos >= max_ciclos:
            break
        parar.wait(config.intervalo_leitura_s)
    arquivo.selar(data_corrente)
    if enviador is not None:
        enviador.varrer()
    leitor.fechar()
    publicador.fechar()
```

Em `main()`, após construir `publicador`, construir o enviador condicionalmente e passá-lo:
```python
    enviador = None
    if cfg.sftp is not None:
        from hub.enviador_sftp import EnviadorSftp, TransporteParamiko
        from hub import identidade_ssh
        identidade_ssh.carregar_ou_criar_chave_ssh(cfg.sftp.ssh_key_path)
        transporte = TransporteParamiko(
            cfg.sftp.host, cfg.sftp.port, cfg.sftp.username,
            cfg.sftp.ssh_key_path, cfg.sftp.remote_dir,
        )
        enviador = EnviadorSftp(cfg.coletor_id, cfg.caminho_dados, transporte)
    parar = Event()
    signal.signal(signal.SIGTERM, lambda *_: parar.set())
    signal.signal(signal.SIGINT, lambda *_: parar.set())
    executar(cfg, leitor, arquivo, publicador,
             agora_fn=lambda: datetime.now(tz), parar=parar, enviador=enviador)
```

- [ ] **Step 4: Rodar — deve passar (novo + antigo)**

Run: `python -m pytest hub/tests/test_main.py -q`
Expected: PASS (o antigo `test_executar_grava_e_publica_e_sela_no_fim` + o novo = 2)

- [ ] **Step 5: Commit**

```bash
git add hub/main.py hub/tests/test_main.py
git commit -m "feat(hub): main — wiring do enviador SFTP (varrer por ciclo + no encerramento)"
```

---

### Task 6: Lado-servidor — `ingestao/receber_upload.py` + serviço SFTPGo

Entrypoint que o Event Manager do SFTPGo chama pós-upload, e o serviço no compose. O entrypoint tem teste (mock de `ingerir_arquivo`); o compose é verificado no runbook (não há docker no Pi).

**Files:**
- Create: `ingestao/receber_upload.py`, `ingestao/tests/test_receber_upload.py`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: `ingestao.ingestor.ingerir_arquivo(caminho, registro_path, dsn, cliente_odoo)`; `ingestao.odoo_cliente.conectar(url, db, usuario, senha)`.
- Produces: `ingestao.receber_upload.main(argv=None) -> ResultadoIngestao`.

- [ ] **Step 1: Escrever o teste falho**

Create `ingestao/tests/test_receber_upload.py`:
```python
from unittest import mock

from ingestao import receber_upload


def test_main_chama_ingerir_com_caminho_e_env(monkeypatch):
    monkeypatch.setenv("SENTINELA_REGISTRO", "/reg.json")
    monkeypatch.setenv("SENTINELA_DSN", "postgresql://x")
    with mock.patch("ingestao.receber_upload.odoo_cliente.conectar") as conectar, \
         mock.patch("ingestao.receber_upload.ingestor.ingerir_arquivo") as ingerir:
        cliente = conectar.return_value
        receber_upload.main(["/uploads/2026-07-21_leituras.txt"])
    ingerir.assert_called_once_with("/uploads/2026-07-21_leituras.txt", "/reg.json",
                                    "postgresql://x", cliente)
```

- [ ] **Step 2: Rodar — deve falhar**

Run: `python -m pytest ingestao/tests/test_receber_upload.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'ingestao.receber_upload'`)

- [ ] **Step 3: Implementar `ingestao/receber_upload.py`**

```python
"""Entrypoint chamado pelo Event Manager do SFTPGo após um upload.

Uso: python -m ingestao.receber_upload <caminho_do_arquivo>
Config via ambiente: SENTINELA_REGISTRO, SENTINELA_DSN, SENTINELA_ODOO_URL,
SENTINELA_ODOO_DB, SENTINELA_ODOO_USER, SENTINELA_ODOO_SENHA.
"""
import os
import sys

from . import ingestor, odoo_cliente


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    caminho = argv[0]
    registro = os.environ.get("SENTINELA_REGISTRO", "ingestao/coletores_conhecidos.json")
    dsn = os.environ.get("SENTINELA_DSN", "postgresql://sentinela:sentinela@localhost:5433/sentinela")
    cliente = odoo_cliente.conectar(
        os.environ.get("SENTINELA_ODOO_URL", "http://localhost:8189"),
        os.environ.get("SENTINELA_ODOO_DB", "sentinela"),
        os.environ.get("SENTINELA_ODOO_USER", "admin"),
        os.environ.get("SENTINELA_ODOO_SENHA", "admin"),
    )
    resultado = ingestor.ingerir_arquivo(caminho, registro, dsn, cliente)
    print(f"status={resultado.status_validacao} gravado={resultado.total_gravado} "
          f"motivo={resultado.motivo_rejeicao}")
    return resultado


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Rodar — deve passar**

Run: `python -m pytest ingestao/tests/test_receber_upload.py -q`
Expected: PASS (1 teste)

- [ ] **Step 5: Adicionar o serviço `sftpgo` ao `docker-compose.yml`**

Adicionar em `services:` (antes de `volumes:`):
```yaml
  sftpgo:
    image: drakkan/sftpgo:v2
    depends_on:
      - timescaledb
    ports:
      - "2022:2022"          # SFTP (LAN no dev; restringir à VPN no T3)
      - "8190:8080"          # WebAdmin do SFTPGo
    environment:
      SFTPGO_SFTPD__BINDINGS__0__PORT: 2022
      SFTPGO_COMMON__UPLOAD_MODE: 2
    volumes:
      - sftpgo-data:/srv/sftpgo
      - sftpgo-config:/var/lib/sftpgo
      - ./ingestao:/opt/ingestao:ro     # receber_upload disponível ao Event Manager
    restart: unless-stopped
```
E adicionar em `volumes:`:
```yaml
  sftpgo-data:
  sftpgo-config:
```

- [ ] **Step 6: Verificar que o compose continua YAML válido**

Run: `python -c "import yaml; yaml.safe_load(open('docker-compose.yml')); print('compose OK')"`
Expected: `compose OK`

- [ ] **Step 7: Commit**

```bash
git add ingestao/receber_upload.py ingestao/tests/test_receber_upload.py docker-compose.yml
git commit -m "feat(ingestao): receber_upload (Event Manager pós-upload) + serviço sftpgo no compose"
```

---

### Task 7: Runbook do lado-servidor + verificação cross-machine

**Files:**
- Create: `docs/runbooks/transporte-sftp-servidor.md`

**Interfaces:** nenhuma (documentação).

- [ ] **Step 1: Escrever o runbook**

Create `docs/runbooks/transporte-sftp-servidor.md`:
````markdown
# Runbook — Transporte SFTP (lado-servidor) e teste cross-machine

Passos executados **no servidor (LAN)**, onde roda o `docker-compose`. O Hub
(Raspberry Pi) só precisa do IP do servidor e da sua chave SSH registrada.

## 1. Subir o SFTPGo
```bash
docker compose up -d sftpgo
# WebAdmin em http://<servidor>:8190 (criar admin no primeiro acesso)
```

## 2. Provisionar o Hub no servidor
No Pi, obter as duas chaves públicas do Hub:
```bash
# pubkey SSH (para o SFTPGo autenticar o upload)
cat ~/sentinela-hub/chaves/ssh_hub.pub
# pubkey EC de assinatura (para a ingestão validar o arquivo)
python - <<'PY'
from cryptography.hazmat.primitives import serialization
from contrato import identidade
k = identidade.carregar_ou_criar_chave("~/sentinela-hub/chaves/coletor.pem".replace("~","/home/fitadigital"))
print(k.public_key().public_bytes(serialization.Encoding.PEM,
      serialization.PublicFormat.SubjectPublicKeyInfo).decode())
PY
```
No servidor:
- **SFTPGo**: criar um usuário (ex. `hub-0001A2F3`), home isolado, método de login **Public key**, colando a `ssh_hub.pub`. Diretório `/uploads` com permissão de escrita.
- **Registro de coletores**: registrar a pubkey EC de assinatura:
  ```bash
  python -m ingestao.registro_coletores --registrar COL-RS485-BUS0 \
    --a-partir-de <caminho_da_privada>   # ou usar registrar_coletor com a pubkey PEM
  ```
  (No servidor pode-se registrar direto pela pubkey PEM via `registro_coletores.registrar_coletor(caminho, "COL-RS485-BUS0", pem)`.)

## 3. Ligar o Event Manager (pós-upload → ingestão)
No WebAdmin do SFTPGo → **Event Manager** → nova regra:
- **Trigger:** Filesystem event `upload`.
- **Action:** Run command → `python3 -m ingestao.receber_upload {{VirtualPath}}`
  (working dir `/opt/ingestao/..` conforme o volume montado; ajustar PYTHONPATH).
- **Env:** `SENTINELA_DSN`, `SENTINELA_ODOO_URL`, `SENTINELA_ODOO_DB`,
  `SENTINELA_ODOO_USER`, `SENTINELA_ODOO_SENHA`, `SENTINELA_REGISTRO`.

## 4. Teste cross-machine
No Pi, editar `~/sentinela-hub/config.yaml` com o bloco `sftp` apontando pro IP
do servidor e rodar:
```bash
python -m hub.main --config ~/sentinela-hub/config.yaml   # Ctrl+C sela + envia
```
Verificar no servidor:
- arquivo em `/uploads` no home do hub;
- linha nova no TimescaleDB (`SELECT count(*) FROM leituras WHERE ...`);
- entrada no `file.ledger` do Odoo (`sensor_monitor.file_ledger`), status `valido`.

## Pendências para fatias seguintes
- **T2:** ack de validação de volta ao Hub via MQTT; bridge MQTT local→central.
- **T3:** OpenVPN — restringir o binding do SFTPGo à interface da VPN (remover a
  exposição `2022` no LAN).
````

- [ ] **Step 2: Commit**

```bash
git add docs/runbooks/transporte-sftp-servidor.md
git commit -m "docs(runbook): deploy do transporte SFTP no servidor + teste cross-machine"
```

---

## Validação final (no Pi)

- [ ] **Suíte completa do lado-Hub + ingestão (sem DB):**

Run: `python -m pytest hub/tests contrato/tests coletor_simulado/tests ingestao/tests/test_validador.py ingestao/tests/test_receber_upload.py -q`
Expected: PASS (todos)

---

## Self-Review (preenchido)

**Cobertura do spec:**
- §1.2 cliente SFTP com auth ed25519 → Tasks 1, 4. ✓
- §1.2 rastreio por índice de estado (`_enviados.json`), retry, não-reenvio, não-fatal → Task 3. ✓
- §1.2 provisionamento da identidade SSH → Task 1 (+ registro no runbook Task 7). ✓
- §1.2 SFTPGo no compose + fiação pós-upload → Task 6. ✓
- §1.2 runbook → Task 7. ✓
- §3.1 config bloco sftp opcional, ausência → desligado → Task 2 (+ guarda em Task 5). ✓
- §3.1 wiring no main (varrer por ciclo + no fim) → Task 5. ✓
- §5 testes Pi (identidade, lógica com fake, paramiko com mock, config, receber_upload) → Tasks 1–6. ✓

**Placeholder scan:** sem TBD/TODO; todo step de código traz o código. O runbook tem parâmetros de deploy (`<servidor>`, env) que são valores de ambiente do servidor, não placeholders de código. ✓
**Consistência de tipos:** `Transporte.enviar(caminho_local, nome_remoto)` idêntico no Protocol, no fake e no `TransporteParamiko`; `EnviadorSftp.varrer()` retorna `list[str]` usado no teste do main; `executar(..., enviador=None)` consistente entre assinatura, chamada em `main()` e teste. `ingerir_arquivo(caminho, registro_path, dsn, cliente_odoo)` bate com a assinatura real verificada. ✓

**Limitações conscientes (registradas):**
- `TransporteParamiko` validado por mock no Pi; SFTP real só no runbook cross-machine (paramiko não traz servidor pronto).
- Lado-servidor (compose sftpgo, Event Manager) não roda no Pi; verificação pelo runbook.
- Sem retomada de upload parcial nem rotação do `_enviados.json` (arquivos pequenos; fora do T1).
