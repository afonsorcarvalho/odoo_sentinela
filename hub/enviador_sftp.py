"""Envio dos arquivos selados ao servidor via SFTP.

EnviadorSftp = lógica (varre selados não-enviados, envia, registra estado,
retry natural em falha). O transporte concreto é injetado (Protocol),
permitindo testar a lógica sem rede. TransporteParamiko é a impl real.
"""
import json
import stat as stat_mod
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from hub.arquivo_diario import _esta_selado
from contrato.formato import validar_segmento_path


def _e_diretorio(sftp, caminho):
    """True só se `caminho` existe no servidor E é um diretório."""
    try:
        return stat_mod.S_ISDIR(sftp.stat(caminho).st_mode)
    except IOError:
        return False


class Transporte(Protocol):
    def enviar(self, caminho_local: str, nome_remoto: str) -> None: ...
    def baixar(self, caminho_remoto: str, caminho_local: str) -> None: ...


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
            except Exception as erro:
                # Sem este log, uma falha permanente (ex.: permissão negada no
                # mkdir remoto) vira retry infinito MUDO: o arquivo nunca sobe e
                # nada no Hub registra por quê.
                print(f"[hub] falha ao enviar {nome} -> {remoto}: "
                      f"{type(erro).__name__}: {erro}")
                continue  # falha não-fatal; retry no próximo varrer
            self._enviados[nome] = {"enviado_em": datetime.now(timezone.utc).isoformat()}
            self._persistir()
            enviados_agora.append(nome)
        return enviados_agora


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
            destino = f"{self._remote_dir}/{nome_remoto}"
            self._mkdir_p(sftp, destino.rsplit("/", 1)[0])
            sftp.put(caminho_local, destino)
            sftp.close()
        finally:
            cliente.close()

    def _mkdir_p(self, sftp, diretorio):
        # diretorio já inclui self._remote_dir como prefixo; o remote_dir em
        # si é assumido pré-existente (mesma premissa de `baixar`), então só
        # os níveis abaixo dele são criados.
        sub = diretorio[len(self._remote_dir):].strip("/")
        if not sub:
            return
        atual = self._remote_dir
        for parte in sub.split("/"):
            atual = f"{atual}/{parte}"
            try:
                sftp.mkdir(atual)
            except IOError as erro:
                # Paramiko levanta IOError tanto para "já existe" quanto para
                # "permission denied". Engolir os dois transformava uma conta SFTP
                # sem `create_dirs` (perfeitamente plausível em produção, onde o
                # operador dá só upload/list/download) em retry infinito mudo.
                # Só seguimos se o caminho existe E é diretório.
                if not _e_diretorio(sftp, atual):
                    raise erro

    def baixar(self, caminho_remoto, caminho_local):
        import paramiko
        chave = paramiko.Ed25519Key.from_private_key_file(self._ssh_key_path)
        cliente = paramiko.SSHClient()
        cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cliente.connect(self._host, port=self._port, username=self._username,
                        pkey=chave, look_for_keys=False, allow_agent=False)
        try:
            sftp = cliente.open_sftp()
            sftp.get(caminho_remoto, caminho_local)
            sftp.close()
        finally:
            cliente.close()
