"""Ponto de entrada do software do Hub (papel de coletor RS-485).

Recupera pendentes no boot, roda o loop de varredura (grava + publica por
leitura) e sela o dia corrente ao encerrar (SIGTERM ou fim de max_ciclos).
"""
import argparse
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

from hub import config as config_mod
from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from hub.leitor import Leitor
from hub.publicador_mqtt import PublicadorMqtt


def _tz(offset):
    sinal = 1 if offset[0] == "+" else -1
    horas, minutos = int(offset[1:3]), int(offset[4:6])
    return timezone(sinal * timedelta(hours=horas, minutes=minutos))


def executar(config, leitor, arquivo, publicador, agora_fn, parar, max_ciclos=None,
             enviador=None, reconfigurar=None, caminho_config=None, arquivo_factory=None):
    intervalo = config.intervalo_leitura_s

    def _recarregar():
        nonlocal config, leitor, arquivo, intervalo
        # Constrói a config/leitor NOVOS antes de tocar no leitor antigo: se
        # carregar_config/Leitor levantar (ex. serial /dev/ttyUSB0 ocupada),
        # o leitor antigo continua aberto e funcionando (não vira brick).
        try:
            nova_config = config_mod.carregar_config(caminho_config)
            novo_leitor = Leitor(nova_config)
        except Exception as e:
            print(f"[hub] falha ao recarregar config, mantendo leitor antigo: {e}")
            reconfigurar.clear()
            return
        leitor.fechar()
        leitor = novo_leitor
        config = nova_config
        intervalo = config.intervalo_leitura_s
        if arquivo_factory is not None:
            arquivo = arquivo_factory(nova_config)
        reconfigurar.clear()

    arquivo.recuperar_pendentes(agora_fn().date())
    publicador.conectar()
    ciclos = 0
    data_corrente = None
    # do-while (checa `parar` no fim, não no topo): garante >=1 ciclo mesmo se
    # `parar` já estiver setado ao entrar, para que `data_corrente` seja definido
    # antes do `selar()` (evita deixar o arquivo do dia sem selagem num shutdown
    # que chega durante recuperar_pendentes/conectar). Custo: 1 leitura extra no
    # shutdown. O reload in-loop é checado ANTES do ler_todos.
    while True:
        if reconfigurar is not None and reconfigurar.is_set():
            _recarregar()
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
        if parar.is_set():
            break
        parar.wait(intervalo)
    arquivo.selar(data_corrente)
    if enviador is not None:
        enviador.varrer()
    leitor.fechar()
    publicador.fechar()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hub Sentinela — coletor RS-485")
    parser.add_argument("--config", required=True)
    parser.add_argument("--identity")
    args = parser.parse_args(argv)
    cfg = config_mod.carregar_config(args.config)
    tz = _tz(cfg.timezone_offset)
    assinador = AssinadorSoftware(cfg.caminho_chave)

    def _novo_arquivo(c):
        return ArquivoDiario(c.coletor_id, c.hub_id, c.firmware_version,
                             c.timezone_offset, c.caminho_dados, assinador,
                             cliente_id=c.cliente_id, site_id=c.site_id)

    arquivo = _novo_arquivo(cfg)
    leitor = Leitor(cfg)
    publicador = PublicadorMqtt(cfg.mqtt_host, cfg.mqtt_port)
    enviador = None
    reconfigurar = Event()
    agente = None
    if cfg.sftp is not None:
        if not args.identity:
            raise SystemExit("--identity é obrigatório quando 'sftp' está configurado")
        from hub.identidade_config import carregar_identidade
        identidade = carregar_identidade(args.identity)
        hub_code = identidade.get('hub_code')
        if not hub_code:
            raise SystemExit("identity.yaml precisa de 'hub_code' == hub.hub_code do Odoo")

        from hub.enviador_sftp import EnviadorSftp, TransporteParamiko
        from hub import identidade_ssh
        identidade_ssh.carregar_ou_criar_chave_ssh(cfg.sftp.ssh_key_path)
        transporte = TransporteParamiko(
            cfg.sftp.host, cfg.sftp.port, cfg.sftp.username,
            cfg.sftp.ssh_key_path, cfg.sftp.remote_dir,
        )
        enviador = EnviadorSftp(cfg.coletor_id, cfg.caminho_dados, transporte)

        from hub.agente_config import AgenteControle
        agente = AgenteControle(
            hub_code=hub_code,
            identidade=identidade, sftp_baixar=transporte.baixar,
            reconfigurar=reconfigurar, caminho_config=args.config,
            estado_path=str(Path(cfg.caminho_dados).expanduser() / 'estado_config.json'),
            fw=cfg.firmware_version, mqtt_host=cfg.mqtt_host, mqtt_port=cfg.mqtt_port)
        agente.iniciar()
    parar = Event()
    signal.signal(signal.SIGTERM, lambda *_: parar.set())
    signal.signal(signal.SIGINT, lambda *_: parar.set())
    try:
        executar(cfg, leitor, arquivo, publicador,
                 agora_fn=lambda: datetime.now(tz), parar=parar, enviador=enviador,
                 reconfigurar=reconfigurar, caminho_config=args.config,
                 arquivo_factory=_novo_arquivo)
    finally:
        if agente is not None:
            agente.parar()


if __name__ == "__main__":
    main()
