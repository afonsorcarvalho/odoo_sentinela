"""Testes do watcher de ingestão host-side (scripts/watcher_ingestao.py).

O watcher é o ÚNICO gatilho de ingestão real neste deployment: o SFTPGo roda em
container sem Python e não tem nenhuma regra de Event Manager configurada
(events_rules/events_actions vazias). Se ele não enxerga um arquivo, esse arquivo
nunca vira leitura no Timescale nem linha no file.ledger.

`scripts/` não é pacote — o módulo é carregado por caminho.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_RAIZ = Path(__file__).resolve().parents[2]


def _carregar_watcher():
    spec = importlib.util.spec_from_file_location(
        'watcher_ingestao', str(_RAIZ / 'scripts' / 'watcher_ingestao.py'))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def watcher():
    return _carregar_watcher()


class _EntradaFake:
    """Equivalente ao SFTPAttributes do paramiko: nome + st_mode (S_ISDIR)."""

    def __init__(self, filename, diretorio=False):
        self.filename = filename
        self.st_mode = 0o040755 if diretorio else 0o100644


class _SftpFake:
    def __init__(self, arvore):
        # arvore: {caminho_do_dir: [(nome, é_dir), ...]}
        self._arvore = arvore
        self.baixados = []

    def listdir_attr(self, caminho):
        return [_EntradaFake(n, d) for (n, d) in self._arvore[caminho]]

    def get(self, remoto, local):
        self.baixados.append(remoto)
        Path(local).write_text('conteudo irrelevante para o teste')


ARVORE_NOVA = {
    '/uploads': [('CLI-1', True)],
    '/uploads/CLI-1': [('2026', True)],
    '/uploads/CLI-1/2026': [('07', True)],
    '/uploads/CLI-1/2026/07': [('23', True)],
    '/uploads/CLI-1/2026/07/23': [('SITE-1', True)],
    '/uploads/CLI-1/2026/07/23/SITE-1': [('HUB-1', True)],
    '/uploads/CLI-1/2026/07/23/SITE-1/HUB-1': [('COL-1', True)],
    '/uploads/CLI-1/2026/07/23/SITE-1/HUB-1/COL-1': [
        ('2026-07-23_HUB-1-COL-1_leituras.txt', False)],
}


def test_descobre_arquivo_na_arvore_nova(watcher):
    """FIX C3: listdir plano só via os diretórios de topo (ex. 'CLI-1'), que não
    casam _e_arquivo_ingerivel — TODO arquivo da árvore nova ficava invisível."""
    sftp = _SftpFake(ARVORE_NOVA)
    achados = watcher._descobrir(sftp, '/uploads')
    assert achados == [
        '/uploads/CLI-1/2026/07/23/SITE-1/HUB-1/COL-1/2026-07-23_HUB-1-COL-1_leituras.txt']


def test_descobre_arquivo_legado_plano_na_raiz(watcher):
    """O acervo é misto por decisão explícita (legados não migram): arquivo plano
    na raiz de /uploads tem que continuar sendo ingerido."""
    arvore = dict(ARVORE_NOVA)
    arvore['/uploads'] = [('CLI-1', True), ('2026-07-20_leituras.txt', False),
                          ('README.md', False)]
    achados = watcher._descobrir(_SftpFake(arvore), '/uploads')
    assert '/uploads/2026-07-20_leituras.txt' in achados
    assert '/uploads/README.md' not in achados       # filtro de ingeríveis mantido
    assert len(achados) == 2


def test_descobre_alarmes_tambem(watcher):
    arvore = {'/uploads': [('2026-07-20_HUB-1-COL-1_alarmes.txt', False)]}
    assert watcher._descobrir(_SftpFake(arvore), '/uploads') == [
        '/uploads/2026-07-20_HUB-1-COL-1_alarmes.txt']


def test_descobre_ignora_ponto_e_pontoponto(watcher):
    """Se o servidor devolver '.'/'..' o walk não pode recursar neles (laço)."""
    arvore = {'/uploads': [('.', True), ('..', True), ('x_leituras.txt', False)]}
    assert watcher._descobrir(_SftpFake(arvore), '/uploads') == ['/uploads/x_leituras.txt']


def _arvore_com_colisao():
    nome = '2026-07-23_HUB-1-COL-1_leituras.txt'
    return {
        '/uploads': [('CLI-1', True), ('CLI-2', True)],
        '/uploads/CLI-1': [('2026', True)],
        '/uploads/CLI-1/2026': [('07', True)],
        '/uploads/CLI-1/2026/07': [('23', True)],
        '/uploads/CLI-1/2026/07/23': [('SITE-1', True)],
        '/uploads/CLI-1/2026/07/23/SITE-1': [('HUB-1', True)],
        '/uploads/CLI-1/2026/07/23/SITE-1/HUB-1': [('COL-1', True)],
        '/uploads/CLI-1/2026/07/23/SITE-1/HUB-1/COL-1': [(nome, False)],
        '/uploads/CLI-2': [('2026', True)],
        '/uploads/CLI-2/2026': [('07', True)],
        '/uploads/CLI-2/2026/07': [('23', True)],
        '/uploads/CLI-2/2026/07/23': [('SITE-9', True)],
        '/uploads/CLI-2/2026/07/23/SITE-9': [('HUB-1', True)],
        '/uploads/CLI-2/2026/07/23/SITE-9/HUB-1': [('COL-1', True)],
        '/uploads/CLI-2/2026/07/23/SITE-9/HUB-1/COL-1': [(nome, False)],
    }


def test_processa_ambos_os_ramos_com_mesmo_basename(watcher, tmp_path, monkeypatch):
    """FIX C3: a chave de `processados` tem que ser o caminho completo. Com o
    basename, o segundo coletor com arquivo de mesmo nome seria marcado como já
    processado e NUNCA ingerido — a colisão que a árvore veio eliminar voltaria
    pela porta dos fundos do watcher."""
    monkeypatch.setattr(watcher, 'ESTADO', tmp_path / 'estado.json')
    sftp = _SftpFake(_arvore_com_colisao())
    ingeridos = []

    def _ingerir(local):
        ingeridos.append(local)
        return 'ok'

    processados = set()
    watcher._processar_novos(sftp, processados, _ingerir)

    assert len(ingeridos) == 2                        # os dois foram ingeridos
    assert sorted(sftp.baixados) == [
        '/uploads/CLI-1/2026/07/23/SITE-1/HUB-1/COL-1/2026-07-23_HUB-1-COL-1_leituras.txt',
        '/uploads/CLI-2/2026/07/23/SITE-9/HUB-1/COL-1/2026-07-23_HUB-1-COL-1_leituras.txt']
    assert processados == set(sftp.baixados)
    assert set(json.loads((tmp_path / 'estado.json').read_text())) == processados


def test_nao_reprocessa_o_que_ja_esta_no_estado(watcher, tmp_path, monkeypatch):
    monkeypatch.setattr(watcher, 'ESTADO', tmp_path / 'estado.json')
    sftp = _SftpFake(ARVORE_NOVA)
    caminho = ('/uploads/CLI-1/2026/07/23/SITE-1/HUB-1/COL-1/'
               '2026-07-23_HUB-1-COL-1_leituras.txt')
    processados = {caminho}
    watcher._processar_novos(sftp, processados, lambda local: 'ok')
    assert sftp.baixados == []


def test_estado_legado_por_basename_migra_para_caminho_completo(watcher, tmp_path, monkeypatch):
    """A chave mudou de basename para caminho completo. Sem migrar, todo arquivo
    já ingerido seria re-ingerido — e ingerir_arquivo escreve no file.ledger a
    cada chamada, duplicando linhas do acervo de auditoria no Odoo."""
    estado = tmp_path / 'estado.json'
    estado.write_text(json.dumps(['2026-07-20_leituras.txt',
                                  '/uploads/CLI-1/2026/07/23/x_leituras.txt']))
    monkeypatch.setattr(watcher, 'ESTADO', estado)
    monkeypatch.setattr(watcher, 'SFTP_UPLOADS', '/uploads')
    assert watcher._carregar_processados() == {
        '/uploads/2026-07-20_leituras.txt',                  # migrado
        '/uploads/CLI-1/2026/07/23/x_leituras.txt',          # já no formato novo
    }
