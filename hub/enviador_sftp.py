"""Envio dos arquivos selados ao servidor via SFTP.

EnviadorSftp = lógica (varre selados não-enviados, envia, registra estado,
retry natural em falha). O transporte concreto é injetado (Protocol),
permitindo testar a lógica sem rede. TransporteParamiko é a impl real.
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
