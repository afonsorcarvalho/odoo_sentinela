from threading import Event
from unittest.mock import MagicMock

from hub import main as hub_main
from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware


def test_executar_recarrega_leitor_quando_reconfigurar_setado(monkeypatch):
    parar = Event()
    reconfig = Event()
    reconfig.set()  # já sinalizado → deve recarregar no 1º ciclo

    leitor_velho = MagicMock()
    leitor_velho.ler_todos.return_value = []
    leitor_novo = MagicMock()
    leitor_novo.ler_todos.return_value = []

    cfg = MagicMock(); cfg.intervalo_leitura_s = 0; cfg.hub_id = 'H'; cfg.coletor_id = 'C'
    cfg_novo = MagicMock(); cfg_novo.intervalo_leitura_s = 0

    monkeypatch.setattr(hub_main.config_mod, 'carregar_config', lambda p: cfg_novo)
    criados = []
    def fake_leitor(c):
        criados.append(c); return leitor_novo
    monkeypatch.setattr(hub_main, 'Leitor', fake_leitor)

    arquivo = MagicMock(); publicador = MagicMock()
    # para no 1º ciclo após recarregar
    def agora():
        parar.set()  # encerra após um ciclo
        import datetime
        return datetime.datetime(2026, 7, 22, tzinfo=datetime.timezone.utc)

    hub_main.executar(cfg, leitor_velho, arquivo, publicador, agora_fn=agora,
                      parar=parar, max_ciclos=1, reconfigurar=reconfig,
                      caminho_config='config.yaml')

    leitor_velho.fechar.assert_called_once()   # leitor antigo fechado
    assert criados == [cfg_novo]               # novo Leitor da config nova
    assert not reconfig.is_set()               # Event limpo


def test_recarregar_com_config_invalida_mantem_leitor_antigo_sem_matar_loop(monkeypatch, capsys):
    parar = Event()
    reconfig = Event()
    reconfig.set()  # já sinalizado → deve tentar recarregar no 1º ciclo

    leitor_velho = MagicMock()
    leitor_velho.ler_todos.return_value = []

    cfg = MagicMock(); cfg.intervalo_leitura_s = 0; cfg.hub_id = 'H'; cfg.coletor_id = 'C'

    def carregar_config_com_erro(p):
        raise ValueError("serial /dev/ttyUSB0 ocupada")
    monkeypatch.setattr(hub_main.config_mod, 'carregar_config', carregar_config_com_erro)
    leitor_criado = []
    def fake_leitor(c):
        leitor_criado.append(c); return MagicMock()
    monkeypatch.setattr(hub_main, 'Leitor', fake_leitor)

    arquivo = MagicMock(); publicador = MagicMock()

    def agora():
        parar.set()
        import datetime
        return datetime.datetime(2026, 7, 22, tzinfo=datetime.timezone.utc)

    # não deve levantar (loop não pode morrer por causa do reload falho)
    hub_main.executar(cfg, leitor_velho, arquivo, publicador, agora_fn=agora,
                      parar=parar, max_ciclos=1, reconfigurar=reconfig,
                      caminho_config='config.yaml')

    leitor_velho.fechar.assert_called_once()   # só o fechar do fim normal do loop
    assert leitor_criado == []                 # Leitor novo nunca foi construído (falhou antes)
    assert not reconfig.is_set()               # Event limpo mesmo em erro (não fica em retry-loop)
    assert leitor_velho.ler_todos.called       # loop seguiu usando o leitor antigo


def test_recarregar_com_leitor_falho_mantem_leitor_antigo_sem_matar_loop(monkeypatch):
    """Cenário motivador do fix: config.yaml carrega OK, mas Leitor(cfg) é que
    falha (ex. serial /dev/ttyUSB0 ocupada). O leitor antigo NÃO pode já ter
    sido fechado quando isso acontece — senão o hub vira um brick."""
    parar = Event()
    reconfig = Event()
    reconfig.set()  # já sinalizado → deve tentar recarregar no 1º ciclo

    leitor_velho = MagicMock()
    leitor_velho.ler_todos.return_value = []

    cfg = MagicMock(); cfg.intervalo_leitura_s = 0; cfg.hub_id = 'H'; cfg.coletor_id = 'C'
    cfg_novo = MagicMock(); cfg_novo.intervalo_leitura_s = 0

    monkeypatch.setattr(hub_main.config_mod, 'carregar_config', lambda p: cfg_novo)

    def leitor_que_falha(c):
        raise OSError("serial /dev/ttyUSB0 ocupada")
    monkeypatch.setattr(hub_main, 'Leitor', leitor_que_falha)

    arquivo = MagicMock(); publicador = MagicMock()

    def agora():
        parar.set()
        import datetime
        return datetime.datetime(2026, 7, 22, tzinfo=datetime.timezone.utc)

    # não deve levantar (Leitor() falhando não pode matar o loop)
    hub_main.executar(cfg, leitor_velho, arquivo, publicador, agora_fn=agora,
                      parar=parar, max_ciclos=1, reconfigurar=reconfig,
                      caminho_config='config.yaml')

    # o leitor antigo só é fechado 1x, no encerramento normal do loop —
    # NÃO durante o _recarregar (senão teria sido fechado antes do Leitor()
    # falhar, e o loop teria seguido sem nenhum leitor funcional).
    leitor_velho.fechar.assert_called_once()
    assert not reconfig.is_set()               # Event limpo mesmo em erro (não fica em retry-loop)
    assert leitor_velho.ler_todos.called       # loop seguiu usando o leitor antigo (não brickou)


def test_recarregar_reconstroi_arquivo_com_tenant_da_config_nova(monkeypatch, tmp_path):
    """Bug de hardware: Hub que boota sem tenant (provisionamento inicial,
    barramentos: [] -> ArquivoDiario construído com cliente_id/site_id vazios)
    e depois recebe via _recarregar uma config JÁ com tenant precisa que o
    ArquivoDiario em uso também seja reconstruído — senão o cabeçalho do
    arquivo diário sai com cliente_id/site_id vazios mesmo após o reload, e o
    ingestor rejeita o arquivo no cross-check de tenant."""
    parar = Event()
    reconfig = Event()
    reconfig.set()  # já sinalizado -> deve recarregar no 1º ciclo

    assinador = AssinadorSoftware(tmp_path / 'k.pem')

    # arquivo pré-reload: construído sem tenant (cenário de boot tenant-less)
    arquivo_velho = ArquivoDiario('COL', 'HUB', '0.1.0', '-03:00',
                                  tmp_path / 'dados', assinador,
                                  cliente_id='', site_id='')

    leitor_velho = MagicMock()
    leitor_velho.ler_todos.return_value = []

    cfg = MagicMock(); cfg.intervalo_leitura_s = 0; cfg.hub_id = 'HUB'; cfg.coletor_id = 'COL'

    # config nova (pós-reload) já com o tenant que veio do config-agent
    cfg_novo = MagicMock()
    cfg_novo.intervalo_leitura_s = 0
    cfg_novo.coletor_id = 'COL'; cfg_novo.hub_id = 'HUB'
    cfg_novo.firmware_version = '0.1.0'; cfg_novo.timezone_offset = '-03:00'
    cfg_novo.caminho_dados = tmp_path / 'dados'
    cfg_novo.cliente_id = 'CLI-43'; cfg_novo.site_id = 'SITE-01'

    monkeypatch.setattr(hub_main.config_mod, 'carregar_config', lambda p: cfg_novo)

    leitor_novo = MagicMock()
    leitura_pos_reload = {
        "timestamp": None, "sensor_id": "SNR-EXP-TEMP-01", "area_id": "AREA-EXPURGO",
        "tipo_medida": "temperatura", "valor": 42.0, "unidade": "C",
        "protocolo_origem": "4-20ma", "status_leitura": "ok",
        "cert_ver": 3, "cal_ganho": 0.965, "cal_offset": 0.33,
    }
    leitor_novo.ler_todos.side_effect = lambda agora: [dict(leitura_pos_reload, timestamp=agora)]
    monkeypatch.setattr(hub_main, 'Leitor', lambda c: leitor_novo)

    publicador = MagicMock()

    def _novo_arquivo(c):
        return ArquivoDiario(c.coletor_id, c.hub_id, c.firmware_version,
                             c.timezone_offset, c.caminho_dados, assinador,
                             cliente_id=c.cliente_id, site_id=c.site_id)

    def agora():
        parar.set()  # encerra após este ciclo
        import datetime
        return datetime.datetime(2026, 7, 22, tzinfo=datetime.timezone.utc)

    hub_main.executar(cfg, leitor_velho, arquivo_velho, publicador, agora_fn=agora,
                      parar=parar, max_ciclos=1, reconfigurar=reconfig,
                      caminho_config='config.yaml', arquivo_factory=_novo_arquivo)

    texto = (tmp_path / 'dados' / 'COL' / '2026-07-22_HUB-COL_leituras.txt').read_text()
    assert "# cliente_id: CLI-43" in texto
    assert "# site_id: SITE-01" in texto
