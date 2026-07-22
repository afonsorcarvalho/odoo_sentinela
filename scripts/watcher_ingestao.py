"""Watcher de ingestão host-side (Fase 5 / transporte).

O SFTPGo (container sem Python) não roda o Event Manager `python -m ingestao.receber_upload`.
Este watcher faz o papel do gatilho no lado servidor: conecta por SFTP na conta do
hub, puxa os arquivos selados novos de `/uploads`, e roda `ingestor.ingerir_arquivo`
(valida assinatura → grava no Timescale + ledger/alarmes no Odoo). Idempotente por
nome de arquivo (estado local). Loop até Ctrl+C.

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
    if ESTADO.exists():
        try:
            return set(json.loads(ESTADO.read_text()))
        except (json.JSONDecodeError, ValueError):
            return set()
    return set()


def _persistir(processados):
    ESTADO.write_text(json.dumps(sorted(processados)))


def _sftp():
    t = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    t.connect(username=SFTP_USER,
              pkey=paramiko.Ed25519Key.from_private_key_file(str(Path(SFTP_KEY).expanduser())))
    return t, paramiko.SFTPClient.from_transport(t)


def _e_arquivo_ingerivel(nome):
    return nome.endswith('_leituras.txt') or nome.endswith('_alarmes.txt')


def main():
    cliente = odoo_cliente.conectar(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_SENHA)
    processados = _carregar_processados()
    print(f'[watcher] observando {SFTP_USER}@{SFTP_HOST}:{SFTP_PORT}{SFTP_UPLOADS} '
          f'(intervalo {INTERVALO}s, {len(processados)} já processados)')
    while True:
        try:
            t, sftp = _sftp()
            try:
                nomes = [n for n in sftp.listdir(SFTP_UPLOADS) if _e_arquivo_ingerivel(n)]
                for nome in sorted(nomes):
                    if nome in processados:
                        continue
                    with tempfile.NamedTemporaryFile(suffix=nome, delete=False) as tmp:
                        local = tmp.name
                    sftp.get(f'{SFTP_UPLOADS}/{nome}', local)
                    try:
                        res = ingestor.ingerir_arquivo(local, REGISTRO, DSN, cliente)
                        print(f'[watcher] ingerido {nome}: {res}')
                        processados.add(nome)
                        _persistir(processados)
                    except Exception as e:
                        print(f'[watcher] FALHA ao ingerir {nome}: {e}')
                    finally:
                        os.unlink(local)
            finally:
                t.close()
        except Exception as e:
            print(f'[watcher] erro no ciclo: {e}')
        time.sleep(INTERVALO)


if __name__ == '__main__':
    main()
