"""Carrega e valida a config local do Hub (YAML) em dataclasses tipadas."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from contrato.formato import validar_identificador


@dataclass
class CanalConfig:
    ch: int
    sensor_id: str
    area_id: str
    tipo_medida: str
    unidade: str
    protocolo_origem: str
    map_in: tuple
    map_out: tuple
    filtro: dict = None


@dataclass
class DispositivoConfig:
    endereco: int
    driver: str
    canais: list = field(default_factory=list)


@dataclass
class BarramentoConfig:
    porta: str
    baud: int
    paridade: str
    stop_bits: int
    dispositivos: list = field(default_factory=list)


@dataclass
class SftpConfig:
    host: str
    port: int
    username: str
    ssh_key_path: str
    remote_dir: str


@dataclass
class HubConfig:
    hub_id: str
    coletor_id: str
    firmware_version: str
    timezone_offset: str
    intervalo_leitura_s: int
    caminho_chave: str
    caminho_dados: str
    mqtt_host: str
    mqtt_port: int
    barramentos: list = field(default_factory=list)
    sftp: object = None


def _par(lista, nome):
    if not isinstance(lista, list) or len(lista) != 2:
        raise ValueError(f"'{nome}' deve ter exatamente 2 elementos, veio {lista!r}")
    return (float(lista[0]), float(lista[1]))


def _canal(bruto):
    for campo in ("sensor_id", "area_id"):
        validar_identificador(str(bruto[campo]))
    mapa = bruto["map"]
    return CanalConfig(
        ch=int(bruto["ch"]),
        sensor_id=bruto["sensor_id"],
        area_id=bruto["area_id"],
        tipo_medida=bruto["tipo_medida"],
        unidade=bruto["unidade"],
        protocolo_origem=bruto.get("protocolo_origem", "4-20ma"),
        map_in=_par(mapa["in"], "map.in"),
        map_out=_par(mapa["out"], "map.out"),
        filtro=bruto.get("filtro"),
    )


def carregar_config(caminho):
    dados = yaml.safe_load(Path(caminho).read_text())
    for campo in ("hub_id", "coletor_id"):
        validar_identificador(str(dados[campo]))
    barramentos = []
    for bus in dados["barramentos"]:
        dispositivos = [
            DispositivoConfig(
                endereco=int(d["endereco"]),
                driver=d["driver"],
                canais=[_canal(c) for c in d["canais"]],
            )
            for d in bus["dispositivos"]
        ]
        barramentos.append(BarramentoConfig(
            porta=bus["porta"], baud=int(bus["baud"]),
            paridade=bus.get("paridade", "N"), stop_bits=int(bus.get("stop_bits", 1)),
            dispositivos=dispositivos,
        ))
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
    mqtt = dados.get("mqtt", {})
    return HubConfig(
        hub_id=dados["hub_id"], coletor_id=dados["coletor_id"],
        firmware_version=dados["firmware_version"], timezone_offset=dados["timezone_offset"],
        intervalo_leitura_s=int(dados["intervalo_leitura_s"]),
        caminho_chave=dados["caminho_chave"], caminho_dados=dados["caminho_dados"],
        mqtt_host=mqtt.get("host", "localhost"), mqtt_port=int(mqtt.get("port", 1883)),
        barramentos=barramentos, sftp=sftp,
    )
