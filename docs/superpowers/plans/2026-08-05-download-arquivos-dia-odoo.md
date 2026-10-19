# Download dos Arquivos do Dia pelo Odoo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um wizard no Odoo que recebe data + site e devolve um ZIP com todos os arquivos diários assinados daquele dia naquele site, com os bytes originais intactos.

**Architecture:** O container `odoo` não tem acesso ao acervo; o container `api` tem (chave SFTP + `paramiko`). O Odoo expõe wizard + controller que resolvem o site pelo ORM do usuário (o `ir.rule` isola por cliente), derivam `cliente_id` e chamam uma rota `/internal/` na api usando o segredo compartilhado que `hub.action_publicar_config` já usa. A api lista a pasta `{cliente}/{AAAA}/{MM}/{DD}/{site}/`, monta o ZIP num temporário e devolve; o Odoo repassa em blocos de 64 KB.

**Tech Stack:** Odoo 18 (`afr_sentinela_sensor_monitor`), FastAPI + paramiko (`api/`), pytest, `odoo.tests.common.TransactionCase`.

**Spec:** `docs/superpowers/specs/2026-08-05-download-arquivos-dia-odoo-design.md`

## Global Constraints

- **Bytes intactos.** O ZIP deve conter cópia byte-a-byte dos arquivos do acervo. Nenhuma normalização de newline, nenhum BOM, nenhum re-encode. O rodapé assinado é a razão de existir da feature.
- **O endpoint da api nunca aceita caminho.** Recebe `cliente`, `site`, `data` e compõe o caminho internamente. `cliente` e `site` validados contra `^[A-Za-z0-9_-]{1,64}$`.
- **O controller do Odoo nunca usa `sudo` para resolver o site.** O isolamento multi-tenant vem do `ir.rule` `rule_site_tenant` já existente.
- **Nenhuma mudança em `docker-compose.yml`.** Toda variável de ambiente nova tem default no código (`SFTP_UPLOADS` = `/uploads`, `ARQUIVOS_ZIP_MAX_BYTES` = `524288000`).
- **Nenhum campo novo no `sensor_monitor.file.ledger`** e nenhum backfill. A árvore do acervo é o índice.
- Comentários e mensagens de usuário em português; identificadores em português seguindo o código existente (`baixar_zip`, `caminho_do_dia`).
- Teto de ZIP: `ARQUIVOS_ZIP_MAX_BYTES`, default 500 MB (`500 * 1024 * 1024 = 524288000`).
- Timeout do Odoo ao chamar a api: 300 s.

## File Structure

**Criar:**

| Arquivo | Responsabilidade |
|---|---|
| `api/arquivos.py` | Lógica pura: validação de token, composição de caminho, varredura da árvore, montagem do ZIP. Sem FastAPI, sem HTTP. |
| `api/arquivos_router.py` | Rota `/internal/arquivos/zip`: segredo, tradução de erro em código HTTP, `FileResponse` + limpeza do temporário. |
| `api/tests/test_arquivos.py` | Testes de `api/arquivos.py` com um duplo de SFTP. |
| `api/tests/test_arquivos_router.py` | Testes da rota com `TestClient`. |
| `addons/afr_sentinela_sensor_monitor/models/arquivo_client.py` | `sensor_monitor.arquivo.client`: resolve site com ACL do usuário, chama a api, traduz erro em `UserError`. |
| `addons/afr_sentinela_sensor_monitor/models/arquivo_download_wizard.py` | `sensor_monitor.arquivo.download.wizard`: data + site → `ir.actions.act_url`. |
| `addons/afr_sentinela_sensor_monitor/controllers/__init__.py` | Import do controller. |
| `addons/afr_sentinela_sensor_monitor/controllers/arquivos.py` | Rota HTTP `/sentinela/arquivos/zip`, fina: parse, delega, repassa stream. |
| `addons/afr_sentinela_sensor_monitor/views/arquivo_download_views.xml` | Form do wizard + action. |
| `addons/afr_sentinela_sensor_monitor/tests/test_arquivo_download.py` | Testes do client e do wizard. |

**Modificar:**

| Arquivo | Mudança |
|---|---|
| `api/main.py:6-8` | Importar `arquivos_router` |
| `api/main.py:24-31` | `app.include_router(arquivos_router.router)` |
| `addons/afr_sentinela_sensor_monitor/__init__.py` | `from . import controllers` |
| `addons/afr_sentinela_sensor_monitor/models/__init__.py` | Importar os dois models novos |
| `addons/afr_sentinela_sensor_monitor/tests/__init__.py` | Importar o teste novo |
| `addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv` | Acesso ao wizard |
| `addons/afr_sentinela_sensor_monitor/views/menu.xml` | Item "Arquivos do Dia" |
| `addons/afr_sentinela_sensor_monitor/__manifest__.py` | `views/arquivo_download_views.xml` no `data` |

## Como rodar os testes

**Testes da api** (da raiz do repositório, com o venv ativo):

```bash
source .venv/bin/activate
python -m pytest api/tests/test_arquivos.py api/tests/test_arquivos_router.py -q
```

**Testes do Odoo** (o addon precisa ser atualizado para o teste enxergar código novo):

```bash
docker compose exec -T odoo odoo -d sentinela \
  -u afr_sentinela_sensor_monitor --test-enable \
  --test-tags /afr_sentinela_sensor_monitor \
  --db_host=db --db_user=odoo --db_password=odoo \
  --stop-after-init --http-port=8169
```

`--test-tags /afr_sentinela_sensor_monitor` é obrigatório: sem ele a suíte inteira do `base` roda (1500+ testes). `--http-port=8169` evita conflito com o Odoo que já está de pé na 8069 do container.

---

### Task 1: Validação de parâmetros e composição de caminho (api)

Nenhum fragmento de caminho pode vir do chamador. Esta task cria as duas funções puras que garantem isso.

**Files:**
- Create: `api/arquivos.py`
- Create: `api/tests/test_arquivos.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `class ParametroInvalido(ValueError)`
  - `validar_token(valor: str) -> str`
  - `caminho_do_dia(base: str, cliente: str, site: str, data: datetime.date) -> str`

- [ ] **Step 1: Write the failing test**

Criar `api/tests/test_arquivos.py`:

```python
from datetime import date

import pytest

from api.arquivos import ParametroInvalido, caminho_do_dia, validar_token


def test_validar_token_aceita_codigos_reais():
    assert validar_token('CLI-43') == 'CLI-43'
    assert validar_token('SITE-DEMO-01') == 'SITE-DEMO-01'
    assert validar_token('HUB_0001A2F3') == 'HUB_0001A2F3'


@pytest.mark.parametrize('valor', [
    '..',
    '../..',
    'a/b',
    'CLI-43/../../etc',
    '%2e%2e',
    'cli 43',
    '',
    'x' * 65,
    # Em Python, `$` casa também logo antes de um \n final — com .match() estes
    # três passariam. Por isso validar_token usa .fullmatch().
    'CLI-43\n',
    '\nCLI-43',
    'CLI-43\r\n',
])
def test_validar_token_recusa_travessia_e_lixo(valor):
    # A defesa contra path traversal mora aqui: se um destes passar, o caminho
    # montado em caminho_do_dia escapa da raiz do acervo.
    with pytest.raises(ParametroInvalido):
        validar_token(valor)


def test_caminho_do_dia_monta_arvore_do_acervo():
    assert caminho_do_dia('/uploads', 'CLI-43', 'SITE-DEMO-01', date(2026, 7, 29)) == \
        '/uploads/CLI-43/2026/07/29/SITE-DEMO-01'


def test_caminho_do_dia_zero_pad_mes_e_dia():
    assert caminho_do_dia('/uploads', 'CLI-1', 'S-1', date(2026, 1, 5)) == \
        '/uploads/CLI-1/2026/01/05/S-1'


def test_caminho_do_dia_valida_os_tokens():
    with pytest.raises(ParametroInvalido):
        caminho_do_dia('/uploads', '../etc', 'S-1', date(2026, 1, 5))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_arquivos.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'api.arquivos'`

- [ ] **Step 3: Write minimal implementation**

Criar `api/arquivos.py`:

```python
"""Acervo de arquivos diários: varredura da árvore SFTP e montagem de ZIP.

Módulo puro — sem FastAPI e sem HTTP. Quem fala HTTP é arquivos_router.py.
"""
import re
from datetime import date

# Códigos do cadastro (CLI-43, SITE-DEMO-01, HUB_0001A2F3). O que este regex
# recusa é exatamente o que tornaria o caminho montado abaixo perigoso: '/',
# '.' e qualquer forma de travessia.
_RE_TOKEN = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


class ParametroInvalido(ValueError):
    """Token ou data fora do formato aceito."""


def validar_token(valor: str) -> str:
    # fullmatch, não match: `$` casa também imediatamente antes de um \n final,
    # então .match() aceitaria 'CLI-43\n'. O token não viraria travessia por si
    # só, mas um newline sobrevivente vira injeção em header ou log adiante.
    if not isinstance(valor, str) or not _RE_TOKEN.fullmatch(valor):
        raise ParametroInvalido(f'valor inválido: {valor!r}')
    return valor


def caminho_do_dia(base: str, cliente: str, site: str, data: date) -> str:
    """Caminho remoto da pasta de um dia/site, montado só com valores validados."""
    cliente = validar_token(cliente)
    site = validar_token(site)
    return f'{base}/{cliente}/{data.year:04d}/{data.month:02d}/{data.day:02d}/{site}'
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_arquivos.py -q`
Expected: PASS (15 testes — 11 do parametrize mais 4 avulsos)

- [ ] **Step 5: Commit**

```bash
git add api/arquivos.py api/tests/test_arquivos.py
git commit -m "feat(api): validacao de token e caminho do dia do acervo"
```

---

### Task 2: Varredura da árvore do dia (api)

**Files:**
- Modify: `api/arquivos.py`
- Modify: `api/tests/test_arquivos.py`

**Interfaces:**
- Consumes: `validar_token`, `caminho_do_dia` da Task 1.
- Produces: `listar_arquivos_do_dia(sftp, raiz: str, profundidade_max: int = 3) -> list[tuple[str, int]]` — lista de `(caminho_relativo_a_raiz, tamanho_bytes)`, ordenada por caminho. Lista vazia quando a pasta não existe.

O duplo de SFTP definido aqui é reusado pelas Tasks 3 e 4.

- [ ] **Step 1: Write the failing test**

Acrescentar a `api/tests/test_arquivos.py` (mantendo o que já existe):

```python
import io
import stat as stat_mod

from api.arquivos import listar_arquivos_do_dia


class FakeAttr:
    """Imita paramiko.SFTPAttributes no que listar_arquivos_do_dia usa."""

    def __init__(self, filename, tamanho=0, tipo='arquivo'):
        self.filename = filename
        self.st_size = tamanho
        modos = {
            'arquivo': stat_mod.S_IFREG | 0o644,
            'dir': stat_mod.S_IFDIR | 0o755,
            'link': stat_mod.S_IFLNK | 0o777,
        }
        self.st_mode = modos[tipo]


class FakeSFTP:
    """SFTP falso: um dict de caminho absoluto -> bytes.

    Diretórios são inferidos dos caminhos. Levanta IOError em pasta
    inexistente, igual ao paramiko.
    """

    def __init__(self, arquivos):
        self.arquivos = dict(arquivos)
        self.links = set()

    def listdir_attr(self, caminho):
        caminho = caminho.rstrip('/')
        filhos = {}
        for full in self.arquivos:
            if not full.startswith(caminho + '/'):
                continue
            resto = full[len(caminho) + 1:]
            nome = resto.split('/')[0]
            if '/' in resto:
                filhos[nome] = FakeAttr(nome, 0, 'dir')
            else:
                tipo = 'link' if full in self.links else 'arquivo'
                filhos[nome] = FakeAttr(nome, len(self.arquivos[full]), tipo)
        if not filhos:
            raise IOError(f'No such file: {caminho}')
        return list(filhos.values())

    def open(self, caminho, modo='r'):
        if caminho not in self.arquivos:
            raise IOError(f'No such file: {caminho}')
        return io.BytesIO(self.arquivos[caminho])


RAIZ = '/uploads/CLI-43/2026/07/29/SITE-DEMO-01'


def _acervo_de_um_dia():
    return FakeSFTP({
        f'{RAIZ}/HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_leituras.txt': b'linha1\nlinha2\n',
        f'{RAIZ}/HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_alarmes.txt': b'alarme\n',
        f'{RAIZ}/HUB-0001/COL-BUS1/2026-07-29_HUB-0001-COL-BUS1_leituras.txt': b'x' * 100,
    })


def test_listar_traz_caminho_relativo_e_tamanho():
    encontrados = listar_arquivos_do_dia(_acervo_de_um_dia(), RAIZ)
    assert encontrados == [
        ('HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_alarmes.txt', 7),
        ('HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_leituras.txt', 14),
        ('HUB-0001/COL-BUS1/2026-07-29_HUB-0001-COL-BUS1_leituras.txt', 100),
    ]


def test_listar_pasta_inexistente_devolve_vazio():
    assert listar_arquivos_do_dia(FakeSFTP({}), RAIZ) == []


def test_listar_ignora_arquivo_fundo_demais():
    # HUB/COLETOR/arquivo = 3 níveis. Qualquer coisa mais funda não faz parte
    # da convenção do acervo e não entra no ZIP.
    sftp = FakeSFTP({
        f'{RAIZ}/HUB-0001/COL-BUS0/subpasta/inesperado.txt': b'nao',
        f'{RAIZ}/HUB-0001/COL-BUS0/ok.txt': b'sim',
    })
    assert listar_arquivos_do_dia(sftp, RAIZ) == [('HUB-0001/COL-BUS0/ok.txt', 3)]


def test_listar_ignora_symlink():
    sftp = FakeSFTP({
        f'{RAIZ}/HUB-0001/COL-BUS0/real.txt': b'sim',
        f'{RAIZ}/HUB-0001/COL-BUS0/atalho.txt': b'nao',
    })
    sftp.links.add(f'{RAIZ}/HUB-0001/COL-BUS0/atalho.txt')
    assert listar_arquivos_do_dia(sftp, RAIZ) == [('HUB-0001/COL-BUS0/real.txt', 3)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_arquivos.py -q`
Expected: FAIL com `ImportError: cannot import name 'listar_arquivos_do_dia'`

- [ ] **Step 3: Write minimal implementation**

Acrescentar a `api/arquivos.py`:

```python
import stat


def listar_arquivos_do_dia(sftp, raiz: str, profundidade_max: int = 3):
    """Arquivos regulares sob `raiz`, como (caminho_relativo, tamanho).

    `profundidade_max=3` é a convenção do acervo: HUB/COLETOR/arquivo.txt.
    Só entra o que for arquivo regular — symlink e diretório fundo demais
    ficam de fora. Pasta inexistente devolve lista vazia (o chamador traduz
    em 404), não exceção.
    """
    encontrados = []

    def varrer(caminho_abs, prefixo, profundidade):
        try:
            entradas = sftp.listdir_attr(caminho_abs)
        except IOError:
            return
        for attr in entradas:
            rel = f'{prefixo}{attr.filename}'
            if stat.S_ISREG(attr.st_mode):
                encontrados.append((rel, attr.st_size))
            elif stat.S_ISDIR(attr.st_mode) and profundidade < profundidade_max:
                varrer(f'{caminho_abs}/{attr.filename}', f'{rel}/', profundidade + 1)

    varrer(raiz.rstrip('/'), '', 1)
    return sorted(encontrados)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_arquivos.py -q`
Expected: PASS (15 testes)

- [ ] **Step 5: Commit**

```bash
git add api/arquivos.py api/tests/test_arquivos.py
git commit -m "feat(api): varredura da arvore do dia no acervo SFTP"
```

---

### Task 3: Montagem do ZIP com bytes intactos (api)

Esta é a task que sustenta a feature: se o ZIP alterar um byte, o arquivo baixado não passa mais no portal de autenticidade.

**Files:**
- Modify: `api/arquivos.py`
- Modify: `api/tests/test_arquivos.py`

**Interfaces:**
- Consumes: `listar_arquivos_do_dia` da Task 2; `FakeSFTP` do arquivo de teste.
- Produces: `montar_zip(sftp, raiz: str, arquivos: list[tuple[str, int]], destino: str) -> None` — escreve o ZIP em `destino` (caminho local).

- [ ] **Step 1: Write the failing test**

Acrescentar a `api/tests/test_arquivos.py`:

```python
import hashlib
import zipfile

from api.arquivos import montar_zip


def test_montar_zip_preserva_bytes_e_arvore(tmp_path):
    sftp = _acervo_de_um_dia()
    arquivos = listar_arquivos_do_dia(sftp, RAIZ)
    destino = tmp_path / 'dia.zip'

    montar_zip(sftp, RAIZ, arquivos, str(destino))

    with zipfile.ZipFile(destino) as zf:
        assert sorted(zf.namelist()) == [
            'HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_alarmes.txt',
            'HUB-0001/COL-BUS0/2026-07-29_HUB-0001-COL-BUS0_leituras.txt',
            'HUB-0001/COL-BUS1/2026-07-29_HUB-0001-COL-BUS1_leituras.txt',
        ]
        for arcname in zf.namelist():
            original = sftp.arquivos[f'{RAIZ}/{arcname}']
            extraido = zf.read(arcname)
            # SHA-256 e não igualdade de string: é o mesmo confronto que o
            # portal de autenticidade faz. Newline normalizado ou BOM
            # inserido quebram aqui, que é onde tem que quebrar.
            assert hashlib.sha256(extraido).hexdigest() == hashlib.sha256(original).hexdigest()


def test_montar_zip_de_arquivo_com_bytes_nao_utf8(tmp_path):
    # O acervo é texto, mas o ZIP não pode presumir isso: qualquer
    # transcodificação silenciosa invalidaria a assinatura.
    cru = b'\x00\xff\xfe raw \r\n sem newline normalizado \r'
    sftp = FakeSFTP({f'{RAIZ}/HUB-X/COL-Y/cru.txt': cru})
    destino = tmp_path / 'cru.zip'

    montar_zip(sftp, RAIZ, listar_arquivos_do_dia(sftp, RAIZ), str(destino))

    with zipfile.ZipFile(destino) as zf:
        assert zf.read('HUB-X/COL-Y/cru.txt') == cru


def test_montar_zip_vazio_gera_zip_valido_sem_membros(tmp_path):
    destino = tmp_path / 'vazio.zip'
    montar_zip(FakeSFTP({}), RAIZ, [], str(destino))
    with zipfile.ZipFile(destino) as zf:
        assert zf.namelist() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_arquivos.py -q`
Expected: FAIL com `ImportError: cannot import name 'montar_zip'`

- [ ] **Step 3: Write minimal implementation**

Acrescentar a `api/arquivos.py`:

```python
import shutil
import zipfile

_BLOCO = 1024 * 1024


def montar_zip(sftp, raiz: str, arquivos, destino: str) -> None:
    """Escreve em `destino` um ZIP com os arquivos, preservando HUB/COLETOR/.

    Cópia byte-a-byte via copyfileobj em modo binário: nada de ler como texto,
    nada de decodificar. O rodapé assinado tem que sobreviver intacto.
    """
    raiz = raiz.rstrip('/')
    with zipfile.ZipFile(destino, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, _tamanho in arquivos:
            origem = sftp.open(f'{raiz}/{rel}', 'rb')
            try:
                # prefetch multiplica a taxa de leitura do paramiko; o duplo
                # de teste não tem o método, daí o hasattr.
                if hasattr(origem, 'prefetch'):
                    origem.prefetch()
                with zf.open(rel, 'w') as destino_membro:
                    shutil.copyfileobj(origem, destino_membro, _BLOCO)
            finally:
                origem.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_arquivos.py -q`
Expected: PASS (18 testes)

- [ ] **Step 5: Commit**

```bash
git add api/arquivos.py api/tests/test_arquivos.py
git commit -m "feat(api): montagem de ZIP do dia com bytes intactos"
```

---

### Task 4: Rota `/internal/arquivos/zip` (api)

**Files:**
- Create: `api/arquivos_router.py`
- Create: `api/tests/test_arquivos_router.py`
- Modify: `api/main.py:6-8` (import) e `api/main.py:24-31` (include_router)

**Interfaces:**
- Consumes: `ParametroInvalido`, `caminho_do_dia`, `listar_arquivos_do_dia`, `montar_zip` das Tasks 1-3.
- Produces: `router` (APIRouter) e `_sftp_conectar` — atributo de módulo trocado por monkeypatch nos testes.

- [ ] **Step 1: Write the failing test**

Criar `api/tests/test_arquivos_router.py`:

```python
import hashlib
import io
import stat as stat_mod
import zipfile

import pytest
from fastapi.testclient import TestClient

from api import arquivos_router
from api.main import app

SECRET = 'segredo-de-teste'
RAIZ = '/uploads/CLI-43/2026/07/29/SITE-DEMO-01'
LEITURAS = b'ts;sensor;valor\n2026-07-29T00:00:00;SNR-1;21.5\n#assinatura=abc\n'


class FakeAttr:
    def __init__(self, filename, tamanho=0, tipo='arquivo'):
        self.filename = filename
        self.st_size = tamanho
        self.st_mode = {'arquivo': stat_mod.S_IFREG | 0o644,
                        'dir': stat_mod.S_IFDIR | 0o755}[tipo]


class FakeSFTP:
    def __init__(self, arquivos):
        self.arquivos = dict(arquivos)

    def listdir_attr(self, caminho):
        caminho = caminho.rstrip('/')
        filhos = {}
        for full in self.arquivos:
            if not full.startswith(caminho + '/'):
                continue
            resto = full[len(caminho) + 1:]
            nome = resto.split('/')[0]
            filhos[nome] = (FakeAttr(nome, 0, 'dir') if '/' in resto
                            else FakeAttr(nome, len(self.arquivos[full])))
        if not filhos:
            raise IOError('No such file')
        return list(filhos.values())

    def open(self, caminho, modo='r'):
        return io.BytesIO(self.arquivos[caminho])

    def close(self):
        pass


class FakeTransport:
    def close(self):
        pass


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(arquivos_router, '_SECRET', SECRET)
    monkeypatch.setattr(arquivos_router, 'SFTP_UPLOADS', '/uploads')
    monkeypatch.setattr(arquivos_router, 'MAX_BYTES', 500 * 1024 * 1024)
    sftp = FakeSFTP({f'{RAIZ}/HUB-0001/COL-BUS0/leituras.txt': LEITURAS})
    monkeypatch.setattr(arquivos_router, '_sftp_conectar', lambda: (FakeTransport(), sftp))
    return TestClient(app)


def _url(cliente_id='CLI-43', site='SITE-DEMO-01', data='2026-07-29'):
    return f'/internal/arquivos/zip?cliente={cliente_id}&site={site}&data={data}'


def test_sem_secret_401(cliente):
    assert cliente.get(_url()).status_code == 401


def test_secret_errado_401(cliente):
    r = cliente.get(_url(), headers={'X-Config-Secret': 'outro'})
    assert r.status_code == 401


def test_cliente_com_travessia_400(cliente):
    r = cliente.get(_url(cliente_id='../../etc'), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 400


def test_data_nao_iso_400(cliente):
    r = cliente.get(_url(data='29-07-2026'), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 400


def test_dia_sem_arquivo_404(cliente):
    r = cliente.get(_url(data='2026-07-01'), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 404


def test_acima_do_teto_413(cliente, monkeypatch):
    monkeypatch.setattr(arquivos_router, 'MAX_BYTES', 10)
    r = cliente.get(_url(), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 413


def test_zip_do_dia_com_bytes_intactos(cliente):
    r = cliente.get(_url(), headers={'X-Config-Secret': SECRET})
    assert r.status_code == 200
    assert r.headers['content-type'] == 'application/zip'
    assert 'sentinela_SITE-DEMO-01_2026-07-29.zip' in r.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert zf.namelist() == ['HUB-0001/COL-BUS0/leituras.txt']
        assert hashlib.sha256(zf.read('HUB-0001/COL-BUS0/leituras.txt')).hexdigest() == \
            hashlib.sha256(LEITURAS).hexdigest()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest api/tests/test_arquivos_router.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'api.arquivos_router'`

- [ ] **Step 3: Write minimal implementation**

Criar `api/arquivos_router.py`:

```python
import os
import tempfile
from datetime import date

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .arquivos import ParametroInvalido, caminho_do_dia, listar_arquivos_do_dia, montar_zip
from .config_publisher import _sftp_conectar

router = APIRouter()

_SECRET = os.environ.get('CONFIG_PUBLISH_SECRET', '')
# Defaults no código de propósito: o docker-compose de produção não muda.
SFTP_UPLOADS = os.environ.get('SFTP_UPLOADS', '/uploads')
MAX_BYTES = int(os.environ.get('ARQUIVOS_ZIP_MAX_BYTES', str(500 * 1024 * 1024)))


def _remover(caminho):
    def _limpar():
        try:
            os.unlink(caminho)
        except OSError:
            pass
    return _limpar


@router.get('/internal/arquivos/zip')
def zip_do_dia(cliente: str, site: str, data: str, x_config_secret: str = Header(default='')):
    """ZIP com todos os arquivos de um dia/site do acervo.

    Rota interna: só o Odoo chama, com o mesmo segredo do publicar-config.
    Nenhum fragmento de caminho vem do chamador — cliente/site/data são
    validados e o caminho é montado aqui.
    """
    if not _SECRET or x_config_secret != _SECRET:
        raise HTTPException(status_code=401, detail='secret inválido')
    try:
        dia = date.fromisoformat(data)
        raiz = caminho_do_dia(SFTP_UPLOADS, cliente, site, dia)
    except (ValueError, ParametroInvalido) as e:
        raise HTTPException(status_code=400, detail=str(e))

    transport, sftp = _sftp_conectar()
    try:
        encontrados = listar_arquivos_do_dia(sftp, raiz)
        if not encontrados:
            raise HTTPException(status_code=404, detail='nenhum arquivo para este dia/site')
        total = sum(tamanho for _rel, tamanho in encontrados)
        if total > MAX_BYTES:
            raise HTTPException(status_code=413, detail=f'{total} bytes acima do teto {MAX_BYTES}')
        tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
        tmp.close()
        montar_zip(sftp, raiz, encontrados, tmp.name)
    except HTTPException:
        raise
    finally:
        sftp.close()
        transport.close()

    return FileResponse(
        tmp.name,
        media_type='application/zip',
        filename=f'sentinela_{site}_{data}.zip',
        background=BackgroundTask(_remover(tmp.name)),
    )
```

Modificar `api/main.py`, linha 6-8 — acrescentar `arquivos_router` à lista de imports em ordem alfabética:

```python
from . import (alarmes, arquivos_router, auth, config, config_publish_router, config_report,
               historico, live, live_listener, meta, presenca, verificacao_router)
```

E logo após `app.include_router(alarmes.router)` (linha 24):

```python
app.include_router(arquivos_router.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest api/tests/test_arquivos_router.py api/tests/test_arquivos.py -q`
Expected: PASS (25 testes)

Rodar também a suíte da api inteira, para garantir que o `include_router` novo não quebrou nada:

Run: `python -m pytest api -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/arquivos_router.py api/tests/test_arquivos_router.py api/main.py
git commit -m "feat(api): rota interna de download do ZIP do dia"
```

---

### Task 5: Client Odoo → api com ACL do usuário

Toda a lógica fica aqui, não no controller: assim os testes rodam em `TransactionCase` com `with_user`, sem precisar de sessão HTTP.

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/arquivo_client.py`
- Create: `addons/afr_sentinela_sensor_monitor/tests/test_arquivo_download.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/__init__.py`

**Interfaces:**
- Consumes: a rota da Task 4 (`GET /internal/arquivos/zip`, header `X-Config-Secret`).
- Produces: AbstractModel `sensor_monitor.arquivo.client` com
  - `resolver_site(self, site_id: int)` → recordset `sensor_monitor.site` de um registro; levanta `AccessError` se o usuário não enxerga.
  - `baixar_zip(self, site_id: int, data: datetime.date)` → `(nome_zip: str, blocos: Iterator[bytes])`.

- [ ] **Step 1: Write the failing test**

Criar `addons/afr_sentinela_sensor_monitor/tests/test_arquivo_download.py`:

```python
from datetime import date
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestArquivoClient(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('sentinela.api_url', 'http://api:8000')
        self.env['ir.config_parameter'].sudo().set_param(
            'sentinela.config_publish_secret', 's3cr3t')
        self.partner_a = self.env['res.partner'].create({'name': 'Hospital A', 'ref': 'CLI-A'})
        self.partner_b = self.env['res.partner'].create({'name': 'Hospital B', 'ref': 'CLI-B'})
        self.site_a = self.env['sensor_monitor.site'].create({
            'name': 'CME A', 'partner_id': self.partner_a.id,
            'site_code': 'SITE-ARQ-A', 'vertical': 'cme_hospitalar'})
        self.site_b = self.env['sensor_monitor.site'].create({
            'name': 'CME B', 'partner_id': self.partner_b.id,
            'site_code': 'SITE-ARQ-B', 'vertical': 'cme_hospitalar'})
        view_group = self.env.ref('afr_sentinela_sensor_monitor.group_sensor_monitor_view')
        self.user_a = self.env['res.users'].create({
            'name': 'Usuário A', 'login': 'usuario_arq_a@teste.com',
            'partner_id': self.partner_a.id,
            'groups_id': [(6, 0, [view_group.id, self.env.ref('base.group_user').id])]})

    def _client(self, user=None):
        modelo = self.env['sensor_monitor.arquivo.client']
        return modelo.with_user(user) if user else modelo

    def _resposta(self, status_code, blocos=(b'PK\x03\x04',)):
        class Resp:
            def __init__(self):
                self.status_code = status_code

            def iter_content(self, chunk_size=None):
                return iter(blocos)
        return Resp()

    def test_resolver_site_de_outro_cliente_levanta_access_error(self):
        # O isolamento vem do ir.rule rule_site_tenant; o client não usa sudo.
        with self.assertRaises(AccessError):
            self._client(self.user_a).resolver_site(self.site_b.id)

    def test_resolver_site_inexistente_levanta_access_error(self):
        # Mesma resposta de site alheio: não vazar existência de registro.
        with self.assertRaises(AccessError):
            self._client(self.user_a).resolver_site(0)

    def test_resolver_site_proprio_devolve_registro(self):
        assert self._client(self.user_a).resolver_site(self.site_a.id) == self.site_a

    def test_baixar_zip_monta_url_e_header(self):
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(200)
            nome, blocos = self._client(self.user_a).baixar_zip(
                self.site_a.id, date(2026, 7, 29))
            args, kwargs = mock_get.call_args
            assert args[0] == 'http://api:8000/internal/arquivos/zip'
            assert kwargs['params'] == {
                'cliente': 'CLI-A', 'site': 'SITE-ARQ-A', 'data': '2026-07-29'}
            assert kwargs['headers']['X-Config-Secret'] == 's3cr3t'
            assert kwargs['stream'] is True
            assert kwargs['timeout'] == 300
            assert nome == 'sentinela_SITE-ARQ-A_2026-07-29.zip'
            assert b''.join(blocos) == b'PK\x03\x04'

    def test_cliente_id_cai_para_partner_id_quando_ref_vazio(self):
        # Mesma regra de ingestao/odoo_cliente.py::resolver_coletor, que é quem
        # escreve a árvore do acervo. Divergir aqui gera 404 silencioso.
        self.partner_a.ref = False
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(200)
            self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            _args, kwargs = mock_get.call_args
            assert kwargs['params']['cliente'] == f'CLI-{self.partner_a.id}'

    def test_404_vira_mensagem_legivel(self):
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(404)
            with self.assertRaises(UserError) as ctx:
                self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            assert 'Nenhum arquivo' in str(ctx.exception)

    def test_413_vira_mensagem_de_volume(self):
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(413)
            with self.assertRaises(UserError) as ctx:
                self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            assert 'limite' in str(ctx.exception)

    def test_erro_de_conexao_vira_servico_indisponivel(self):
        with patch('requests.get', side_effect=OSError('sem rota')):
            with self.assertRaises(UserError) as ctx:
                self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            assert 'indisponível' in str(ctx.exception)
```

Acrescentar em `addons/afr_sentinela_sensor_monitor/tests/__init__.py`:

```python
from . import test_arquivo_download
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose exec -T odoo odoo -d sentinela -u afr_sentinela_sensor_monitor \
  --test-enable --test-tags /afr_sentinela_sensor_monitor \
  --db_host=db --db_user=odoo --db_password=odoo --stop-after-init --http-port=8169
```
Expected: FAIL com `KeyError: 'sensor_monitor.arquivo.client'`

- [ ] **Step 3: Write minimal implementation**

Criar `addons/afr_sentinela_sensor_monitor/models/arquivo_client.py`:

```python
import requests

from odoo import models
from odoo.exceptions import AccessError, UserError

# SFTP lento com 60 MB de acervo não pode estourar num timeout de 15 s como o
# do publicar-config; o ZIP costuma levar segundos, mas a margem é barata.
_TIMEOUT = 300


class ArquivoClient(models.AbstractModel):
    _name = 'sensor_monitor.arquivo.client'
    _description = 'Cliente HTTP do acervo de arquivos diários'

    def _base_url(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sentinela.api_url', 'http://api:8000')

    def _secret(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'sentinela.config_publish_secret', '')

    def resolver_site(self, site_id):
        """Site que o usuário corrente pode ler — sem sudo, de propósito.

        `search` é o que aplica o ir.rule rule_site_tenant: site de outro
        partner simplesmente não aparece no resultado. Usar
        `browse(...).exists()` aqui seria um furo — `exists()` só confere a
        existência da linha no banco e ignora record rule.

        Site inexistente e site alheio dão a mesma resposta, para não vazar
        existência de registro.
        """
        site = self.env['sensor_monitor.site'].search([('id', '=', int(site_id))], limit=1)
        if not site:
            raise AccessError('Site não encontrado ou fora do seu acesso.')
        return site

    def baixar_zip(self, site_id, data):
        """(nome_do_zip, iterador de blocos) para o dia/site pedido."""
        site = self.resolver_site(site_id)
        partner = site.partner_id
        cliente_id = partner.ref or f'CLI-{partner.id}'
        iso = data.isoformat()
        try:
            resp = requests.get(
                f'{self._base_url()}/internal/arquivos/zip',
                params={'cliente': cliente_id, 'site': site.site_code, 'data': iso},
                headers={'X-Config-Secret': self._secret()},
                stream=True, timeout=_TIMEOUT)
        except Exception:
            raise UserError('Serviço de arquivos indisponível. Tente novamente.')
        if resp.status_code == 404:
            raise UserError(
                f'Nenhum arquivo encontrado para {site.site_code} em '
                f'{data.strftime("%d/%m/%Y")}.')
        if resp.status_code == 413:
            raise UserError('Volume acima do limite; escolha um dia com menos coletores.')
        if resp.status_code != 200:
            raise UserError('Serviço de arquivos indisponível. Tente novamente.')
        nome = f'sentinela_{site.site_code}_{iso}.zip'
        return nome, resp.iter_content(64 * 1024)
```

Acrescentar em `addons/afr_sentinela_sensor_monitor/models/__init__.py`:

```python
from . import arquivo_client
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose exec -T odoo odoo -d sentinela -u afr_sentinela_sensor_monitor \
  --test-enable --test-tags /afr_sentinela_sensor_monitor \
  --db_host=db --db_user=odoo --db_password=odoo --stop-after-init --http-port=8169
```
Expected: PASS — nenhuma linha `FAIL` ou `ERROR` no log; `test_arquivo_download` aparece entre os testes rodados.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/arquivo_client.py \
        addons/afr_sentinela_sensor_monitor/models/__init__.py \
        addons/afr_sentinela_sensor_monitor/tests/test_arquivo_download.py \
        addons/afr_sentinela_sensor_monitor/tests/__init__.py
git commit -m "feat(odoo): client do acervo com ACL por site e erro legivel"
```

---

### Task 6: Controller HTTP do Odoo

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/controllers/__init__.py`
- Create: `addons/afr_sentinela_sensor_monitor/controllers/arquivos.py`
- Modify: `addons/afr_sentinela_sensor_monitor/__init__.py`

**Interfaces:**
- Consumes: `sensor_monitor.arquivo.client.baixar_zip(site_id, data)` da Task 5.
- Produces: rota `GET /sentinela/arquivos/zip?site_id=<int>&data=<YYYY-MM-DD>`.

O controller é fino de propósito: parse, delega, repassa. Toda regra testável já está no client (Task 5), então esta task não acrescenta teste automatizado — a verificação dela é a Task 8, ponta-a-ponta com a stack real.

- [ ] **Step 1: Escrever o controller**

Criar `addons/afr_sentinela_sensor_monitor/controllers/__init__.py`:

```python
from . import arquivos
```

Criar `addons/afr_sentinela_sensor_monitor/controllers/arquivos.py`:

```python
from datetime import date

from werkzeug.wrappers import Response

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class SentinelaArquivos(http.Controller):

    @http.route('/sentinela/arquivos/zip', type='http', auth='user', methods=['GET'])
    def zip_do_dia(self, site_id=None, data=None, **kw):
        try:
            dia = date.fromisoformat(data or '')
            site_id = int(site_id)
        except (TypeError, ValueError):
            return Response('Parâmetros inválidos.', status=400, content_type='text/plain')
        try:
            nome, blocos = request.env['sensor_monitor.arquivo.client'].baixar_zip(site_id, dia)
        except AccessError:
            return Response('Sem acesso a este site.', status=403, content_type='text/plain')
        except UserError as e:
            # Mensagem já é legível (vem do client); 409 evita que o browser
            # trate como erro genérico de servidor.
            return Response(str(e), status=409, content_type='text/plain; charset=utf-8')
        # Streaming: o ZIP inteiro nunca fica em memória neste processo.
        return Response(
            blocos, status=200, content_type='application/zip',
            headers=[('Content-Disposition', f'attachment; filename="{nome}"')])
```

Acrescentar em `addons/afr_sentinela_sensor_monitor/__init__.py`:

```python
from . import controllers
```

- [ ] **Step 2: Reiniciar o Odoo e verificar que a rota subiu**

Um controller novo só é registrado no boot; `-u` sozinho não basta.

```bash
docker compose restart odoo
sleep 15
docker compose logs --tail 40 odoo | grep -i "error\|traceback" || echo "boot limpo"
```
Expected: `boot limpo` (nenhum traceback de import).

- [ ] **Step 3: Verificar que a rota exige login**

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  'http://localhost:8189/sentinela/arquivos/zip?site_id=1&data=2026-07-29'
```
Expected: `303` ou `302` — redirect para `/web/login`, isto é, `auth='user'` funcionando. Um `404` significa que o controller não foi registrado; revisar o `from . import controllers` em `__init__.py`.

- [ ] **Step 4: Rodar a suíte do addon para confirmar que nada regrediu**

```bash
docker compose exec -T odoo odoo -d sentinela -u afr_sentinela_sensor_monitor \
  --test-enable --test-tags /afr_sentinela_sensor_monitor \
  --db_host=db --db_user=odoo --db_password=odoo --stop-after-init --http-port=8169
```
Expected: PASS, sem `FAIL`/`ERROR`.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/controllers/ \
        addons/afr_sentinela_sensor_monitor/__init__.py
git commit -m "feat(odoo): controller de download do ZIP do dia"
```

---

### Task 7: Wizard, view e menu

**Files:**
- Create: `addons/afr_sentinela_sensor_monitor/models/arquivo_download_wizard.py`
- Create: `addons/afr_sentinela_sensor_monitor/views/arquivo_download_views.xml`
- Modify: `addons/afr_sentinela_sensor_monitor/models/__init__.py`
- Modify: `addons/afr_sentinela_sensor_monitor/tests/test_arquivo_download.py`
- Modify: `addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv`
- Modify: `addons/afr_sentinela_sensor_monitor/views/menu.xml`
- Modify: `addons/afr_sentinela_sensor_monitor/__manifest__.py`

**Interfaces:**
- Consumes: a rota `/sentinela/arquivos/zip` da Task 6.
- Produces: TransientModel `sensor_monitor.arquivo.download.wizard` com campos `data_referencia` (Date) e `site_id` (Many2one), e método `action_baixar()` → dict de `ir.actions.act_url`.

O campo se chama `data_referencia` para casar com o nome já usado em `sensor_monitor.file.ledger`.

- [ ] **Step 1: Write the failing test**

Acrescentar ao final de `addons/afr_sentinela_sensor_monitor/tests/test_arquivo_download.py` (a classe nova reusa o mesmo arquivo):

```python
class TestArquivoDownloadWizard(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital W', 'ref': 'CLI-W'})
        self.site = self.env['sensor_monitor.site'].create({
            'name': 'CME W', 'partner_id': partner.id,
            'site_code': 'SITE-ARQ-W', 'vertical': 'cme_hospitalar'})

    def test_action_baixar_devolve_act_url_com_site_e_data(self):
        wizard = self.env['sensor_monitor.arquivo.download.wizard'].create({
            'site_id': self.site.id, 'data_referencia': '2026-07-29'})
        acao = wizard.action_baixar()
        assert acao['type'] == 'ir.actions.act_url'
        assert acao['target'] == 'self'
        assert f'site_id={self.site.id}' in acao['url']
        assert 'data=2026-07-29' in acao['url']
        assert acao['url'].startswith('/sentinela/arquivos/zip?')

    def test_data_referencia_default_e_hoje(self):
        wizard = self.env['sensor_monitor.arquivo.download.wizard'].create({
            'site_id': self.site.id})
        assert wizard.data_referencia == fields.Date.context_today(wizard)
```

Acrescentar `fields` ao import no topo do arquivo de teste:

```python
from odoo import fields
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose exec -T odoo odoo -d sentinela -u afr_sentinela_sensor_monitor \
  --test-enable --test-tags /afr_sentinela_sensor_monitor \
  --db_host=db --db_user=odoo --db_password=odoo --stop-after-init --http-port=8169
```
Expected: FAIL com `KeyError: 'sensor_monitor.arquivo.download.wizard'`

- [ ] **Step 3: Write minimal implementation**

Criar `addons/afr_sentinela_sensor_monitor/models/arquivo_download_wizard.py`:

```python
from odoo import fields, models


class ArquivoDownloadWizard(models.TransientModel):
    _name = 'sensor_monitor.arquivo.download.wizard'
    _description = 'Baixar arquivos do dia'

    data_referencia = fields.Date(
        string='Data', required=True, default=fields.Date.context_today)
    site_id = fields.Many2one('sensor_monitor.site', string='Site', required=True)

    def action_baixar(self):
        """Redireciona para o controller, que faz o streaming do ZIP.

        act_url em vez de baixar aqui: o wizard não pode segurar dezenas de MB
        na resposta JSON-RPC.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': (f'/sentinela/arquivos/zip?site_id={self.site_id.id}'
                    f'&data={self.data_referencia.isoformat()}'),
            'target': 'self',
        }
```

Acrescentar em `addons/afr_sentinela_sensor_monitor/models/__init__.py`:

```python
from . import arquivo_download_wizard
```

Criar `addons/afr_sentinela_sensor_monitor/views/arquivo_download_views.xml`:

```xml
<odoo>
    <record id="view_arquivo_download_wizard_form" model="ir.ui.view">
        <field name="name">sensor_monitor.arquivo.download.wizard.form</field>
        <field name="model">sensor_monitor.arquivo.download.wizard</field>
        <field name="arch" type="xml">
            <form string="Baixar arquivos do dia">
                <group>
                    <field name="site_id"/>
                    <field name="data_referencia"/>
                </group>
                <p class="text-muted">
                    O ZIP traz todos os arquivos daquele dia no site — leituras e alarmes,
                    de todos os hubs e coletores — com os bytes originais preservados.
                </p>
                <footer>
                    <button name="action_baixar" string="Baixar ZIP" type="object"
                            class="btn-primary"/>
                    <button string="Cancelar" class="btn-secondary" special="cancel"/>
                </footer>
            </form>
        </field>
    </record>

    <record id="action_arquivo_download" model="ir.actions.act_window">
        <field name="name">Arquivos do Dia</field>
        <field name="res_model">sensor_monitor.arquivo.download.wizard</field>
        <field name="view_mode">form</field>
        <field name="target">new</field>
    </record>
</odoo>
```

Acrescentar em `addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv` (última linha; TransientModel precisa de create/write para o usuário preencher o form):

```csv
access_arquivo_download_wizard,arquivo.download.wizard,model_sensor_monitor_arquivo_download_wizard,group_sensor_monitor_view,1,1,1,0
```

Acrescentar em `addons/afr_sentinela_sensor_monitor/views/menu.xml`, dentro do bloco de Operação, logo após o item `menu_file_ledger`:

```xml
    <menuitem id="menu_arquivo_download" name="Arquivos do Dia" parent="menu_sensor_monitor_operacao" action="action_arquivo_download" sequence="20"/>
```

Acrescentar em `addons/afr_sentinela_sensor_monitor/__manifest__.py`, na lista `data`, **antes** de `'views/menu.xml'` (o menu referencia a action):

```python
        'views/arquivo_download_views.xml',
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose exec -T odoo odoo -d sentinela -u afr_sentinela_sensor_monitor \
  --test-enable --test-tags /afr_sentinela_sensor_monitor \
  --db_host=db --db_user=odoo --db_password=odoo --stop-after-init --http-port=8169
docker compose restart odoo
```
Expected: PASS, sem `FAIL`/`ERROR`. O `restart` é o que faz o menu novo aparecer na sessão.

- [ ] **Step 5: Commit**

```bash
git add addons/afr_sentinela_sensor_monitor/models/arquivo_download_wizard.py \
        addons/afr_sentinela_sensor_monitor/models/__init__.py \
        addons/afr_sentinela_sensor_monitor/views/arquivo_download_views.xml \
        addons/afr_sentinela_sensor_monitor/views/menu.xml \
        addons/afr_sentinela_sensor_monitor/security/ir.model.access.csv \
        addons/afr_sentinela_sensor_monitor/__manifest__.py \
        addons/afr_sentinela_sensor_monitor/tests/test_arquivo_download.py
git commit -m "feat(odoo): wizard Arquivos do Dia com download em ZIP"
```

---

### Task 8: Verificação ponta-a-ponta contra a stack real

Os testes das tasks anteriores usam duplos de SFTP. Esta task prova o caminho completo com o acervo de verdade — e prova a única coisa que os duplos não podem provar: que o arquivo baixado ainda passa na verificação de autenticidade.

**Files:**
- Nenhum arquivo de código. Produz um registro do resultado no commit final.

**Interfaces:**
- Consumes: tudo das Tasks 1-7, mais a stack em `docker compose`.
- Produces: confirmação de que o ZIP baixado contém arquivo válido segundo o portal.

- [ ] **Step 1: Descobrir um dia que existe no acervo**

```bash
docker exec odoo_sentinela-sftpgo-1 sh -c \
  'find /srv/sftpgo -name "*_leituras.txt" -type f | head -3'
```
Anotar cliente, data, site e coletor de um dos caminhos — a árvore é
`.../uploads/{CLIENTE}/{AAAA}/{MM}/{DD}/{SITE}/{HUB}/{COLETOR}/arquivo.txt`.

- [ ] **Step 2: Chamar a rota da api diretamente**

Substituir `CLI-43`, `SITE-DEMO-01` e a data pelos valores do passo anterior. O segredo é o `CONFIG_PUBLISH_SECRET` do `docker-compose.yml` (`e2e-cfg-secret` em dev).

```bash
curl -s -o /tmp/sentinela-dia.zip -w '%{http_code} %{size_download}\n' \
  -H 'X-Config-Secret: e2e-cfg-secret' \
  'http://localhost:8000/internal/arquivos/zip?cliente=CLI-43&site=SITE-DEMO-01&data=2026-07-29'
unzip -l /tmp/sentinela-dia.zip
```
Expected: `200` com tamanho de vários MB; o `unzip -l` lista caminhos no formato `HUB-xxxx/COL-yyyy/*.txt`.

- [ ] **Step 3: Provar byte-identidade contra o acervo**

```bash
ARC=$(unzip -Z1 /tmp/sentinela-dia.zip | head -1)
unzip -p /tmp/sentinela-dia.zip "$ARC" | sha256sum
docker exec odoo_sentinela-sftpgo-1 sh -c \
  "sha256sum /srv/sftpgo/data/sentinela-config-svc/uploads/CLI-43/2026/07/29/SITE-DEMO-01/$ARC"
```
Expected: os dois SHA-256 idênticos. Diferentes = a feature está quebrada, mesmo que o download "funcione".

- [ ] **Step 4: Baixar pelo Odoo e verificar no portal de autenticidade**

1. Abrir `http://localhost:8189`, logar, ir em **Sensor Monitor → Operação → Arquivos do Dia**.
2. Escolher o site e a data do passo 1, clicar **Baixar ZIP**. O browser baixa `sentinela_<SITE>_<DATA>.zip`.
3. Extrair um `_leituras.txt` do ZIP.
4. Abrir `http://localhost:8189/verificar-autenticidade`, enviar esse `.txt`.

Expected: relatório com veredito **válido**. Esse é o critério de aceite real da feature — o arquivo baixado continua sendo prova.

- [ ] **Step 5: Verificar o isolamento multi-tenant no ar**

Com o usuário logado, chamar a rota com um `site_id` de outro cliente (pegar um id pela lista de Sites com o admin, depois logar como usuário de outro partner):

```bash
# Substituir <ID_DE_OUTRO_CLIENTE> e usar a sessão do browser (DevTools → Network).
curl -s -o /dev/null -w '%{http_code}\n' -b 'session_id=<SESSAO>' \
  'http://localhost:8189/sentinela/arquivos/zip?site_id=<ID_DE_OUTRO_CLIENTE>&data=2026-07-29'
```
Expected: `403`.

- [ ] **Step 6: Registrar o resultado**

```bash
git commit --allow-empty -m "test: verificacao ponta-a-ponta do download do ZIP do dia

ZIP baixado pelo Odoo, byte-identico ao acervo (SHA-256 conferido) e
aprovado no portal de autenticidade. Site de outro cliente devolve 403."
```

---

## Self-Review

**Cobertura da spec:**

| Requisito da spec | Task |
|---|---|
| Wizard data + site | 7 |
| Controller com ACL sem sudo | 5 (regra), 6 (rota) |
| `sensor_monitor.arquivo.client` | 5 |
| Rota `/internal/arquivos/zip` | 4 |
| Regex anti-traversal | 1 |
| Caminho montado internamente | 1, 4 |
| Profundidade máx 3, só arquivo regular | 2 |
| 404 dia vazio | 2 (lista vazia), 4 (código HTTP), 5 (mensagem) |
| Teto 413 | 4 (código), 5 (mensagem) |
| ZIP em tempfile + limpeza | 4 |
| Streaming 64 KB no Odoo | 5 (`iter_content`), 6 (Response) |
| `arcname` = HUB/COLETOR/arquivo | 2, 3 |
| Byte-identidade | 3 (unidade), 4 (rota), 8 (acervo real + portal) |
| Menu, view, ACL, manifest | 7 |
| Nenhuma mudança em docker-compose | Global Constraints, Task 4 (defaults no código) |
| Timeout 300 s | 5 |
| Sem campo novo no ledger | nenhuma task toca `file_ledger.py` |

**Consistência de nomes entre tasks:** `validar_token`, `caminho_do_dia`, `listar_arquivos_do_dia`, `montar_zip` (Tasks 1-3) são consumidos com a mesma assinatura na Task 4. `baixar_zip(site_id, data)` devolve `(nome, blocos)` na Task 5 e é desempacotado assim na Task 6. `data_referencia` é o nome do campo do wizard (Task 7) e `data` é o nome do parâmetro de URL (Tasks 6 e 7) — divergência proposital, documentada na Task 7.

**Sem placeholders:** todo passo de código traz o código; todo passo de teste traz o comando e o resultado esperado.
