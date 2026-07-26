"""Carrega e valida a config local do Hub (YAML) em dataclasses tipadas."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from contrato.formato import validar_identificador, validar_segmento_path


@dataclass
class CanalConfig:
    ch: int
    sensor_id: str
    area_id: str
    tipo_medida: str
    unidade: str
    protocolo_origem: str
    map_in: tuple = None
    map_out: tuple = None
    filtro: dict = None
    calibracao: dict = None
    registro: dict = None
    faixa_min: float = None
    faixa_max: float = None
    limite_min: float = None
    limite_max: float = None


@dataclass
class DispositivoConfig:
    endereco: int
    driver: str
    canais: list = field(default_factory=list)
    reconexao_n: int = 3
    reconexao_m: int = 5
    reconexao_k: int = 10


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
    cliente_id: str = ''
    site_id: str = ''
    alarme_n: int = 3
    alarme_margem: float = 0.0


def _par(lista, nome):
    if not isinstance(lista, list) or len(lista) != 2:
        raise ValueError(f"'{nome}' deve ter exatamente 2 elementos, veio {lista!r}")
    return (float(lista[0]), float(lista[1]))


def _canal(bruto):
    for campo in ("sensor_id", "area_id"):
        validar_identificador(str(bruto[campo]))
    mapa = bruto.get("map")
    if mapa is not None:
        map_in = _par(mapa["in"], "map.in")
        map_out = _par(mapa["out"], "map.out")
    else:
        map_in = map_out = None
    cal = bruto.get("calibracao") or {}
    calibracao = {
        'cert_ver': int(cal.get('cert_ver', 0)),
        'ganho': float(cal.get('ganho', 1.0)),
        'offset': float(cal.get('offset', 0.0)),
    }
    return CanalConfig(
        ch=int(bruto["ch"]),
        sensor_id=bruto["sensor_id"],
        area_id=bruto["area_id"],
        tipo_medida=bruto["tipo_medida"],
        unidade=bruto["unidade"],
        protocolo_origem=bruto.get("protocolo_origem", "4-20ma"),
        map_in=map_in,
        map_out=map_out,
        filtro=bruto.get("filtro"),
        calibracao=calibracao,
        registro=bruto.get("registro"),
        faixa_min=(float(bruto["faixa_min"]) if bruto.get("faixa_min") is not None else None),
        faixa_max=(float(bruto["faixa_max"]) if bruto.get("faixa_max") is not None else None),
        limite_min=(float(bruto["limite_min"]) if bruto.get("limite_min") is not None else None),
        limite_max=(float(bruto["limite_max"]) if bruto.get("limite_max") is not None else None),
    )


def _validar_segmento(nome_campo, valor, motivo_extra=''):
    """Valida na ENTRADA um campo que vira segmento de path (local e/ou remoto).

    Falhar aqui é falhar no boot, alto e claro. Sem isso, o ValueError cru nascia
    lá no EnviadorSftp._caminho_remoto — fora do try/except do varrer — e derrubava
    o processo do Hub horas depois, no primeiro arquivo selado, parando a leitura
    dos sensores. A mensagem tem que dizer QUAL campo e por quê.
    """
    if not isinstance(valor, str):
        raise ValueError(
            f"'{nome_campo}' inválido: {valor!r} (tipo {type(valor).__name__}) — "
            f"precisa ser string; valor em branco ou booleano no YAML vira "
            f"None/True/False, que não é um segmento de path válido.{motivo_extra}")
    try:
        validar_segmento_path(valor)
    except ValueError:
        raise ValueError(
            f"'{nome_campo}' inválido: {valor!r} — precisa ser um segmento de path "
            f"simples (não pode ser vazio, '.', '..' nem conter '/' ou '\\'); "
            f"ele vira um diretório no caminho do arquivo.{motivo_extra}")


_DATA_TYPES_SUPORTADOS = {"int16", "uint16"}


def _validar_canais_generico(endereco, canais):
    """Driver 'generico' é data-driven: cada canal PRECISA de 'registro' válido,
    senão o driver não sabe o que ler — falhar aqui é falhar no boot, não em
    tempo de varredura."""
    for canal in canais:
        if not canal.registro:
            raise ValueError(
                f"dispositivo endereco={endereco} driver=generico: canal ch={canal.ch} "
                f"sem 'registro' — obrigatório para o driver genérico.")
        data_type = canal.registro.get("data_type")
        if data_type not in _DATA_TYPES_SUPORTADOS:
            raise ValueError(
                f"dispositivo endereco={endereco} driver=generico: canal ch={canal.ch} "
                f"registro.data_type={data_type!r} inválido — suportados: "
                f"{sorted(_DATA_TYPES_SUPORTADOS)}.")
        count = canal.registro.get("count")
        if count != 1:
            raise ValueError(
                f"dispositivo endereco={endereco} driver=generico: canal ch={canal.ch} "
                f"registro.count={count!r} inválido — só 1 é suportado na v1.")


def carregar_config(caminho):
    dados = yaml.safe_load(Path(caminho).read_text())
    for campo in ("hub_id", "coletor_id"):
        validar_identificador(str(dados[campo]))
        # hub_id e coletor_id compõem o nome do arquivo e o caminho remoto, e
        # coletor_id é também o diretório LOCAL de dados: validar na entrada
        # cobre os dois lados de uma vez.
        _validar_segmento(campo, dados[campo])
    barramentos = []
    for bus in dados["barramentos"]:
        dispositivos = []
        for d in bus["dispositivos"]:
            endereco = int(d["endereco"])
            driver = d["driver"]
            canais = [_canal(c) for c in d["canais"]]
            if driver == "generico":
                _validar_canais_generico(endereco, canais)
            dispositivos.append(DispositivoConfig(
                endereco=endereco, driver=driver, canais=canais,
                reconexao_n=int(d.get("reconexao_n", 3)),
                reconexao_m=int(d.get("reconexao_m", 5)),
                reconexao_k=int(d.get("reconexao_k", 10)),
            ))
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
        # cliente_id/site_id só são exigidos quando há envio: o EnviadorSftp monta
        # {cliente}/AAAA/MM/DD/{site}/{hub}/{coletor}/ e não tem como sem eles.
        # Sem o bloco 'sftp' (bancada, simulação, hub sem transporte) ninguém monta
        # caminho remoto, e exigir tenant só quebraria esses cenários.
        for campo in ("cliente_id", "site_id"):
            _validar_segmento(
                campo, dados.get(campo, ''),
                motivo_extra=" É obrigatório quando o bloco 'sftp' está presente, "
                             "porque compõe o caminho remoto do envio.")
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
        cliente_id=dados.get("cliente_id", ""), site_id=dados.get("site_id", ""),
        alarme_n=int(dados.get("alarme_n", 3)),
        alarme_margem=float(dados.get("alarme_margem", 0.0)),
    )
