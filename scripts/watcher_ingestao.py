"""Watcher de ingestão host-side (Fase 5 / transporte).

O SFTPGo (container sem Python) não roda o Event Manager `python -m ingestao.receber_upload`.
Este watcher faz o papel do gatilho no lado servidor: conecta por SFTP na conta do
hub, puxa os arquivos selados novos de `/uploads` — varrendo a árvore
`{cliente}/AAAA/MM/DD/{site}/{hub}/{coletor}/` recursivamente, e também os legados
planos na raiz —, e roda `ingestor.ingerir_arquivo` (valida assinatura → grava no
Timescale + ledger/alarmes no Odoo). Idempotente pelo CAMINHO REMOTO COMPLETO
(estado local). Loop até Ctrl+C.

Env (com defaults de dev):
  SFTP_HOST=localhost SFTP_PORT=2022 SFTP_USER=sentinela-config-svc
  SFTP_KEY_PATH=.sftp-config-svc/id_ed25519  SFTP_UPLOADS=/uploads
  TIMESCALE_DSN=postgresql://sentinela:sentinela@localhost:5433/sentinela
  SENTINELA_REGISTRO=ingestao/coletores_conhecidos.json
  ODOO_URL=http://localhost:8189 ODOO_DB=sentinela ODOO_USER=admin ODOO_SENHA=admin
  WATCH_INTERVALO_S=5
"""
import json
import os
import stat
import tempfile
import time
from pathlib import Path

import paramiko

from ingestao import ingestor, odoo_cliente

SFTP_HOST = os.environ.get('SFTP_HOST', 'localhost')
SFTP_PORT = int(os.environ.get('SFTP_PORT', '2022'))
SFTP_USER = os.environ.get('SFTP_USER', 'sentinela-config-svc')
SFTP_KEY = os.environ.get('SFTP_KEY_PATH', '.sftp-config-svc/id_ed25519')
SFTP_UPLOADS = os.environ.get('SFTP_UPLOADS', '/uploads')
DSN = os.environ.get('TIMESCALE_DSN', 'postgresql://sentinela:sentinela@localhost:5433/sentinela')
REGISTRO = os.environ.get('SENTINELA_REGISTRO', 'ingestao/coletores_conhecidos.json')
ODOO_URL = os.environ.get('ODOO_URL', 'http://localhost:8189')
ODOO_DB = os.environ.get('ODOO_DB', 'sentinela')
ODOO_USER = os.environ.get('ODOO_USER', 'admin')
ODOO_SENHA = os.environ.get('ODOO_SENHA', 'admin')
INTERVALO = float(os.environ.get('WATCH_INTERVALO_S', '5'))
ESTADO = Path(os.environ.get('WATCH_ESTADO', '.watcher_ingestao.json'))


def _carregar_processados():
    if not ESTADO.exists():
        return set()
    try:
        bruto = set(json.loads(ESTADO.read_text()))
    except (json.JSONDecodeError, ValueError):
        return set()
    # Migração de chave: antes da varredura recursiva tudo era plano na raiz de
    # SFTP_UPLOADS e a chave era o basename; agora é o caminho remoto completo.
    # Sem migrar, todo arquivo já ingerido seria re-ingerido — e ingerir_arquivo
    # chama escrever_ledger incondicionalmente, o que duplicaria linhas no
    # file.ledger do Odoo (o acervo de auditoria).
    return {c if '/' in c else f'{SFTP_UPLOADS}/{c}' for c in bruto}


def _persistir(processados):
    ESTADO.write_text(json.dumps(sorted(processados)))


def _sftp():
    t = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    t.connect(username=SFTP_USER,
              pkey=paramiko.Ed25519Key.from_private_key_file(str(Path(SFTP_KEY).expanduser())))
    return t, paramiko.SFTPClient.from_transport(t)


def _e_arquivo_ingerivel(nome):
    return nome.endswith('_leituras.txt') or nome.endswith('_alarmes.txt')


def _descobrir(sftp, base):
    """Caminhos remotos completos e ingeríveis sob `base`, recursivamente.

    O Hub passou a enviar para {cliente}/AAAA/MM/DD/{site}/{hub}/{coletor}/{nome}.
    Um listdir plano só enxerga os diretórios de topo (ex. 'CLI-1'), que não casam
    _e_arquivo_ingerivel — a árvore inteira ficaria invisível e nada seria ingerido.
    O acervo é misto (legados planos na raiz não migram), então a raiz também é
    varrida normalmente. listdir_attr (e não listdir) porque só o st_mode
    distingue diretório de arquivo.
    """
    achados = []
    pilha = [base]
    while pilha:
        atual = pilha.pop()
        for entrada in sftp.listdir_attr(atual):
            nome = entrada.filename
            if nome in ('.', '..'):
                continue          # servidor que devolve os links do dir → laço
            caminho = f'{atual}/{nome}'
            if stat.S_ISDIR(entrada.st_mode):
                pilha.append(caminho)
            elif _e_arquivo_ingerivel(nome):
                achados.append(caminho)
    return sorted(achados)


def _processar_novos(sftp, processados, ingerir):
    """Um ciclo: descobre, baixa e ingere o que ainda não foi processado.

    A chave de `processados` é o CAMINHO COMPLETO, não o basename: dois coletores
    em ramos diferentes podem ter arquivos de mesmo nome, e com basename o segundo
    seria dado como já processado e nunca ingerido.
    """
    for caminho in _descobrir(sftp, SFTP_UPLOADS):
        if caminho in processados:
            continue
        nome = caminho.rsplit('/', 1)[-1]
        with tempfile.NamedTemporaryFile(suffix=nome, delete=False) as tmp:
            local = tmp.name
        sftp.get(caminho, local)
        try:
            res = ingerir(local)
            print(f'[watcher] ingerido {caminho}: {res}')
            processados.add(caminho)
            _persistir(processados)
        except Exception as e:
            print(f'[watcher] FALHA ao ingerir {caminho}: {e}')
        finally:
            os.unlink(local)


def main():
    cliente = odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_SENHA)
    processados = _carregar_processados()
    print(f'[watcher] observando {SFTP_USER}@{SFTP_HOST}:{SFTP_PORT}{SFTP_UPLOADS} '
          f'(intervalo {INTERVALO}s, {len(processados)} já processados)')
    while True:
        try:
            t, sftp = _sftp()
            try:
                _processar_novos(
                    sftp, processados,
                    lambda local: ingestor.ingerir_arquivo(local, REGISTRO, DSN, cliente))
            finally:
                t.close()
        except Exception as e:
            print(f'[watcher] erro no ciclo: {e}')
        time.sleep(INTERVALO)


if __name__ == '__main__':
    main()
