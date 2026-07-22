from threading import Event
from unittest.mock import MagicMock

from hub import main as hub_main


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
