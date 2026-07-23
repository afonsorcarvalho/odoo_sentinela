# Organização de pastas dos arquivos de leitura — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enviar cada arquivo diário de leitura para uma árvore remota
`{cliente}/AAAA/MM/DD/{site}/{hub}/{coletor}/` com nome auto-descritivo,
eliminando a colisão da pasta SFTP plana e fechando path traversal nos segmentos.

**Architecture:** A árvore é uma preocupação de **transporte**. O nome do arquivo
passa a carregar hub+coletor; o `EnviadorSftp` monta o sub-caminho da árvore a
partir do nome (data) + config (cliente/site/hub); o `TransporteParamiko` cria os
diretórios remotos antes do `put`. A cadeia de hash / selagem não é tocada — o
nome do arquivo não entra no lastro.

**Tech Stack:** Python 3, pytest, paramiko (SFTP).

## Global Constraints

- Identificadores usados como segmento de diretório (cliente, site, hub, coletor)
  devem ser validados contra path traversal: rejeitar `/`, `\`, `..`, `.`, vazio.
- Cadeia de hash, selagem e reconstrução de estado permanecem **idênticas** ao
  comportamento atual — só o nome do arquivo muda, o conteúdo/lastro não.
- Local do Hub permanece `dados/{coletor}/{nome}.txt`. A árvore existe só no
  remoto (SFTP).
- Ingestão não é tocada (é push; lê identidade do cabeçalho).
- Data extraída do nome sempre pelos 10 primeiros caracteres (`AAAA-MM-DD`), nunca
  por `split("_")` — hub/coletor podem conter `_`.
- Rodar testes do hub com: `python -m pytest hub/tests/ -q`

---

### Task 1: `validar_segmento_path` no contrato

**Files:**
- Modify: `contrato/formato.py` (adicionar função após `validar_identificador`, linha 8)
- Test: `contrato/tests/test_formato.py` (criar se não existir; senão adicionar)

**Interfaces:**
- Produces: `validar_segmento_path(valor: str) -> None` — levanta `ValueError`
  se `valor` for vazio, `.`, `..`, ou contiver `/` ou `\`.

- [ ] **Step 1: Verificar onde ficam os testes de formato**

Run: `ls contrato/tests/ 2>/dev/null; grep -rl "from contrato import formato\|import formato" contrato/tests/ 2>/dev/null`
Se existir arquivo de teste de formato, adicionar os testes nele. Senão, criar
`contrato/tests/test_formato.py` com `from contrato import formato` no topo.

- [ ] **Step 2: Escrever o teste que falha**

```python
import pytest

from contrato import formato


def test_validar_segmento_path_aceita_codigo_normal():
    formato.validar_segmento_path("COL-RS485-BUS0")
    formato.validar_segmento_path("HUB-0001")
    formato.validar_segmento_path("CLI-1")


@pytest.mark.parametrize("ruim", ["", ".", "..", "a/b", "a\\b", "../../etc"])
def test_validar_segmento_path_rejeita_traversal(ruim):
    with pytest.raises(ValueError):
        formato.validar_segmento_path(ruim)
```

- [ ] **Step 3: Rodar o teste e confirmar que falha**

Run: `python -m pytest contrato/tests/test_formato.py -q`
Expected: FAIL — `AttributeError: module 'contrato.formato' has no attribute 'validar_segmento_path'`

- [ ] **Step 4: Implementar `validar_segmento_path`**

Em `contrato/formato.py`, após `validar_identificador` (linha 8):

```python
def validar_segmento_path(valor):
    if valor in ('', '.', '..') or '/' in valor or '\\' in valor:
        raise ValueError(f"segmento de path inválido: '{valor}'")
```

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `python -m pytest contrato/tests/test_formato.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add contrato/formato.py contrato/tests/test_formato.py
git commit -m "feat(contrato): validar_segmento_path contra path traversal"
```

---

### Task 2: Nome auto-descritivo no `ArquivoDiario`

**Files:**
- Modify: `hub/arquivo_diario.py:49-50` (`caminho`) e `hub/arquivo_diario.py:101-105` (`recuperar_pendentes`)
- Test: `hub/tests/test_arquivo_diario.py`

**Interfaces:**
- Consumes: `formato.validar_segmento_path` (Task 1).
- Produces: `ArquivoDiario.caminho(data)` retorna
  `.../{coletor}/{data}_{hub}-{coletor}_leituras.txt`. O nome é a única fonte do
  caminho — testes e o enviador derivam tudo dele.

- [ ] **Step 1: Escrever o teste que falha (nome novo)**

Adicionar em `hub/tests/test_arquivo_diario.py`:

```python
def test_caminho_tem_nome_auto_descritivo(tmp_path):
    arq, _ = _fazer(tmp_path)
    caminho = arq.caminho("2026-07-21")
    assert caminho.name == "2026-07-21_HUB-0001-COL-RS485-BUS0_leituras.txt"
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest hub/tests/test_arquivo_diario.py::test_caminho_tem_nome_auto_descritivo -q`
Expected: FAIL — nome ainda é `2026-07-21_leituras.txt`.

- [ ] **Step 3: Implementar o nome novo**

Em `hub/arquivo_diario.py`, substituir `caminho` (linhas 49-50):

```python
    def caminho(self, data_referencia):
        nome = f"{data_referencia}_{self._hub_id}-{self._coletor_id}_leituras.txt"
        return self._dir / nome
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `python -m pytest hub/tests/test_arquivo_diario.py::test_caminho_tem_nome_auto_descritivo -q`
Expected: PASS

- [ ] **Step 5: Escrever o teste de regressão do `recuperar_pendentes`**

O parse de data em `recuperar_pendentes` usava `replace("_leituras.txt", "")`,
que quebra com o sufixo `_{hub}-{coletor}`. Adicionar:

```python
def test_recuperar_pendentes_sela_dia_passado_com_nome_novo(tmp_path):
    arq, _ = _fazer(tmp_path)
    ontem = datetime(2026, 7, 20, 8, 0, tzinfo=TZ)
    arq.registrar(_leitura(ontem))
    # simula crash antes de selar: fecha sem selar, reabre em novo dia
    arq_novo, _ = _fazer(tmp_path, ass=arq._assinador)
    arq_novo.recuperar_pendentes(date(2026, 7, 21))
    texto = arq_novo.caminho("2026-07-20").read_text()
    assert "# assinatura: " in texto
```

- [ ] **Step 6: Rodar e confirmar que falha**

Run: `python -m pytest hub/tests/test_arquivo_diario.py::test_recuperar_pendentes_sela_dia_passado_com_nome_novo -q`
Expected: FAIL — `date.fromisoformat` recebe `2026-07-20_HUB-0001-COL-RS485-BUS0` e levanta `ValueError`.

- [ ] **Step 7: Corrigir o parse de data no `recuperar_pendentes`**

Em `hub/arquivo_diario.py`, substituir `recuperar_pendentes` (linhas 101-105):

```python
    def recuperar_pendentes(self, hoje: date):
        for nome in glob.glob(str(self._dir / "*_leituras.txt")):
            data_str = os.path.basename(nome)[:10]
            if date.fromisoformat(data_str) < hoje and not _esta_selado(Path(nome)):
                self.selar(data_str)
```

- [ ] **Step 8: Rodar toda a suite do arquivo_diario (regressão da cadeia)**

Run: `python -m pytest hub/tests/test_arquivo_diario.py -q`
Expected: PASS — todos, incluindo selagem/reconstrução (cadeia intacta).

- [ ] **Step 9: Commit**

```bash
git add hub/arquivo_diario.py hub/tests/test_arquivo_diario.py
git commit -m "feat(hub): nome auto-descritivo AAAA-MM-DD_hub-coletor_leituras"
```

---

### Task 3: `EnviadorSftp` monta o sub-caminho da árvore

**Files:**
- Modify: `hub/enviador_sftp.py:20-49` (`EnviadorSftp`)
- Test: `hub/tests/test_enviador_sftp.py`

**Interfaces:**
- Consumes: `formato.validar_segmento_path` (Task 1); nome de arquivo do formato
  `AAAA-MM-DD_..._leituras.txt` (Task 2).
- Produces: `EnviadorSftp(coletor_id, caminho_dados, transporte, cliente_id,
  site_id, hub_id, caminho_estado=None)`. Em `varrer()`, o `nome_remoto` passado
  ao transporte é o sub-caminho completo da árvore
  `{cliente}/AAAA/MM/DD/{site}/{hub}/{coletor}/{nome_arquivo}`.

- [ ] **Step 1: Escrever o teste que falha (sub-caminho da árvore)**

Substituir/atualizar os testes existentes que chamam `EnviadorSftp(COLETOR, tmp_path / "dados", t)`
(a assinatura muda). Adicionar, e ajustar `_TransporteFake` já existe. Novo teste:

```python
def test_envia_com_subcaminho_da_arvore(tmp_path):
    d = _dir(tmp_path)
    nome = "2026-07-21_HUB-0001-COL-RS485-BUS0_leituras.txt"
    _selado(d, nome)
    t = _TransporteFake()
    env = EnviadorSftp(COLETOR, tmp_path / "dados", t,
                       cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001")
    env.varrer()
    assert t.enviados == [
        f"CLI-1/2026/07/21/SITE-1/HUB-0001/{COLETOR}/{nome}"
    ]
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest hub/tests/test_enviador_sftp.py::test_envia_com_subcaminho_da_arvore -q`
Expected: FAIL — `TypeError` (assinatura antiga) ou `nome_remoto` = só o nome.

- [ ] **Step 3: Implementar a montagem do sub-caminho**

Em `hub/enviador_sftp.py`, atualizar imports e a classe `EnviadorSftp`
(linhas 12, 20-49):

```python
from hub.arquivo_diario import _esta_selado
from contrato.formato import validar_segmento_path


class EnviadorSftp:
    def __init__(self, coletor_id, caminho_dados, transporte,
                 cliente_id, site_id, hub_id, caminho_estado=None):
        self._coletor_id = coletor_id
        self._cliente_id = cliente_id
        self._site_id = site_id
        self._hub_id = hub_id
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

    def _caminho_remoto(self, nome):
        data = nome[:10]              # AAAA-MM-DD
        ano, mes, dia = data[:4], data[5:7], data[8:10]
        for seg in (self._cliente_id, self._site_id, self._hub_id, self._coletor_id):
            validar_segmento_path(seg)
        return "/".join([self._cliente_id, ano, mes, dia,
                         self._site_id, self._hub_id, self._coletor_id, nome])

    def varrer(self):
        enviados_agora = []
        for caminho in sorted(self._dir.glob("*_leituras.txt")):
            nome = caminho.name
            if nome in self._enviados or not _esta_selado(caminho):
                continue
            remoto = self._caminho_remoto(nome)
            try:
                self._transporte.enviar(str(caminho), remoto)
            except Exception:
                continue  # falha não-fatal; retry no próximo varrer
            self._enviados[nome] = {"enviado_em": datetime.now(timezone.utc).isoformat()}
            self._persistir()
            enviados_agora.append(nome)
        return enviados_agora
```

Nota: o estado `_enviados` continua chaveado pelo **nome** local (não muda o
formato do `_enviados.json`).

- [ ] **Step 4: Atualizar os testes existentes para a nova assinatura**

Em `hub/tests/test_enviador_sftp.py`, todo `EnviadorSftp(COLETOR, tmp_path / "dados", t)`
vira `EnviadorSftp(COLETOR, tmp_path / "dados", t, cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001")`.
Os asserts que comparavam `t.enviados == ["2026-07-21_leituras.txt"]` passam a
comparar com o sub-caminho completo `"CLI-1/2026/07/21/SITE-1/HUB-0001/COL-RS485-BUS0/2026-07-21_leituras.txt"`
(mantendo o nome de arquivo que cada teste usa). Os asserts sobre `enviados`
(retorno de `varrer`, chaveado por nome local) permanecem com o nome do arquivo.

- [ ] **Step 5: Rodar toda a suite do enviador**

Run: `python -m pytest hub/tests/test_enviador_sftp.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add hub/enviador_sftp.py hub/tests/test_enviador_sftp.py
git commit -m "feat(hub): enviador monta sub-caminho da arvore remota por cliente/data"
```

---

### Task 4: `TransporteParamiko` cria diretórios remotos (`mkdir -p`)

**Files:**
- Modify: `hub/enviador_sftp.py:60-72` (`TransporteParamiko.enviar`)
- Test: `hub/tests/test_enviador_sftp.py`

**Interfaces:**
- Consumes: `nome_remoto` = sub-caminho da árvore (Task 3), com `/` separando os
  níveis, cujo diretório-pai pode não existir no servidor.
- Produces: `TransporteParamiko.enviar` cria cada nível do diretório-pai de
  `nome_remoto` (relativo a `remote_dir`) antes do `put`, ignorando níveis que já
  existem.

- [ ] **Step 1: Escrever o teste que falha (mkdir -p antes do put)**

O `sftp` do paramiko é mockado. Testar que os diretórios são criados na ordem
e o `put` ocorre com o caminho completo. Adicionar:

```python
def test_transporte_cria_diretorios_antes_do_put():
    sftp = mock.Mock()
    existentes = set()
    def mkdir(p):
        if p in existentes:
            raise IOError("existe")
        existentes.add(p)
    sftp.mkdir.side_effect = mkdir
    cliente = mock.Mock()
    cliente.open_sftp.return_value = sftp
    with mock.patch("paramiko.SSHClient", return_value=cliente), \
         mock.patch("paramiko.Ed25519Key.from_private_key_file"):
        t = TransporteParamiko("h", 22, "u", "/dev/null", "/uploads")
        t.enviar("/local/x.txt", "CLI-1/2026/07/21/SITE-1/HUB-0001/COL/x.txt")
    # criou cada nível do pai sob /uploads, em ordem, antes do put
    criados = [c.args[0] for c in sftp.mkdir.call_args_list]
    assert criados == [
        "/uploads/CLI-1", "/uploads/CLI-1/2026", "/uploads/CLI-1/2026/07",
        "/uploads/CLI-1/2026/07/21", "/uploads/CLI-1/2026/07/21/SITE-1",
        "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001",
        "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001/COL",
    ]
    sftp.put.assert_called_once_with(
        "/local/x.txt", "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001/COL/x.txt")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `python -m pytest hub/tests/test_enviador_sftp.py::test_transporte_cria_diretorios_antes_do_put -q`
Expected: FAIL — hoje `enviar` só faz `put`, sem `mkdir`.

- [ ] **Step 3: Implementar o `mkdir -p` remoto**

Em `hub/enviador_sftp.py`, substituir `TransporteParamiko.enviar` (linhas 60-72):

```python
    def enviar(self, caminho_local, nome_remoto):
        import paramiko
        chave = paramiko.Ed25519Key.from_private_key_file(self._ssh_key_path)
        cliente = paramiko.SSHClient()
        cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cliente.connect(self._host, port=self._port, username=self._username,
                        pkey=chave, look_for_keys=False, allow_agent=False)
        try:
            sftp = cliente.open_sftp()
            destino = f"{self._remote_dir}/{nome_remoto}"
            self._mkdir_p(sftp, destino.rsplit("/", 1)[0])
            sftp.put(caminho_local, destino)
            sftp.close()
        finally:
            cliente.close()

    @staticmethod
    def _mkdir_p(sftp, diretorio):
        partes = diretorio.strip("/").split("/")
        atual = ""
        for parte in partes:
            atual = f"{atual}/{parte}" if atual else f"/{parte}"
            try:
                sftp.mkdir(atual)
            except IOError:
                pass  # já existe
```

- [ ] **Step 4: Rodar o teste e confirmar que passa**

Run: `python -m pytest hub/tests/test_enviador_sftp.py::test_transporte_cria_diretorios_antes_do_put -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub/enviador_sftp.py hub/tests/test_enviador_sftp.py
git commit -m "feat(hub): TransporteParamiko cria diretorios remotos antes do put"
```

---

### Task 5: Cabear os ids no `hub/main.py`

**Files:**
- Modify: `hub/main.py:117`
- Test: `hub/tests/test_main.py` (só rodar; se houver mock de `EnviadorSftp`, ajustar)

**Interfaces:**
- Consumes: `EnviadorSftp(...)` com a nova assinatura (Task 3). `cfg` já expõe
  `cliente_id`, `site_id`, `hub_id`, `coletor_id`, `caminho_dados`.

- [ ] **Step 1: Atualizar a construção do `EnviadorSftp`**

Em `hub/main.py`, linha 117, substituir:

```python
        enviador = EnviadorSftp(cfg.coletor_id, cfg.caminho_dados, transporte)
```

por:

```python
        enviador = EnviadorSftp(cfg.coletor_id, cfg.caminho_dados, transporte,
                                cliente_id=cfg.cliente_id, site_id=cfg.site_id,
                                hub_id=cfg.hub_id)
```

- [ ] **Step 2: Rodar os testes do main (regressão de wiring)**

Run: `python -m pytest hub/tests/test_main.py -q`
Expected: PASS. Se algum teste construir/mockar `EnviadorSftp` com a assinatura
antiga, ajustar para passar `cliente_id`/`site_id`/`hub_id` (ou o mock
correspondente).

- [ ] **Step 3: Rodar toda a suite do hub + contrato**

Run: `python -m pytest hub/tests/ contrato/tests/ -q`
Expected: PASS — verde ponta-a-ponta.

- [ ] **Step 4: Commit**

```bash
git add hub/main.py hub/tests/test_main.py
git commit -m "feat(hub): cabeia cliente/site/hub no EnviadorSftp"
```

---

## Self-Review

**Cobertura do spec:**
- Estrutura remota `{cliente}/AAAA/MM/DD/{site}/{hub}/{coletor}/{nome}` → Task 3.
- Nome auto-descritivo → Task 2.
- `validar_segmento_path` / path traversal → Task 1 (usada em Task 3).
- `mkdir -p` remoto antes do `put` → Task 4.
- Wiring dos ids no main → Task 5.
- Cadeia de hash / selagem intactas → regressão em Task 2 (Step 8).
- Ingestão zero mudança → nenhum task a toca (correto).
- Sem migração → nenhum task de migração (correto, conforme decidido).

**Consistência de tipos:** `EnviadorSftp(coletor_id, caminho_dados, transporte,
cliente_id, site_id, hub_id, caminho_estado=None)` — mesma assinatura em Task 3
(def), Task 3 Step 4 (testes), Task 5 (chamada no main). `_caminho_remoto(nome)`
e `_mkdir_p(sftp, diretorio)` consistentes. Data sempre por `nome[:10]`.

**Placeholders:** nenhum — todo passo tem código/comando/saída esperada.
