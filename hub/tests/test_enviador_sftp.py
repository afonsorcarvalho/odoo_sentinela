import json
from unittest import mock

from hub.enviador_sftp import EnviadorSftp, TransporteParamiko

COLETOR = "COL-RS485-BUS0"

CABECALHO = "# schema_version: 1\n# coletor_id: COL-RS485-BUS0\n"
CORPO = "1|2026-07-21T00:01:00-03:00|SNR|AREA|temperatura|19.8|C|4-20ma|ok|abc\n"
RODAPE_SELADO = "# total_linhas: 1\n# hash_final: abc\n# assinatura: ZZ==\n"


def _dir(tmp_path):
    d = tmp_path / "dados" / COLETOR
    d.mkdir(parents=True)
    return d


def _selado(d, nome):
    (d / nome).write_text(CABECALHO + CORPO + RODAPE_SELADO)


def _aberto(d, nome):
    (d / nome).write_text(CABECALHO + CORPO)  # sem rodapé/assinatura


class _TransporteFake:
    def __init__(self, falhar=False):
        self.enviados = []
        self.falhar = falhar
    def enviar(self, caminho_local, nome_remoto):
        if self.falhar:
            raise OSError("sem rede")
        self.enviados.append(nome_remoto)


def test_envia_selado_nao_enviado(tmp_path):
    d = _dir(tmp_path)
    _selado(d, "2026-07-21_leituras.txt")
    t = _TransporteFake()
    env = EnviadorSftp(COLETOR, tmp_path / "dados", t,
                       cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001")
    enviados = env.varrer()
    assert enviados == ["2026-07-21_leituras.txt"]
    assert t.enviados == [
        f"CLI-1/2026/07/21/SITE-1/HUB-0001/{COLETOR}/2026-07-21_leituras.txt"
    ]


def test_ignora_aberto_nao_selado(tmp_path):
    d = _dir(tmp_path)
    _aberto(d, "2026-07-22_leituras.txt")
    t = _TransporteFake()
    env = EnviadorSftp(COLETOR, tmp_path / "dados", t,
                       cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001")
    assert env.varrer() == []
    assert t.enviados == []


def test_nao_reenvia(tmp_path):
    d = _dir(tmp_path)
    _selado(d, "2026-07-21_leituras.txt")
    t = _TransporteFake()
    env = EnviadorSftp(COLETOR, tmp_path / "dados", t,
                       cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001")
    env.varrer()
    assert env.varrer() == []          # segunda varredura não reenvia
    assert t.enviados == [
        f"CLI-1/2026/07/21/SITE-1/HUB-0001/{COLETOR}/2026-07-21_leituras.txt"
    ]


def test_falha_deixa_pendente_para_retry(tmp_path):
    d = _dir(tmp_path)
    _selado(d, "2026-07-21_leituras.txt")
    falho = _TransporteFake(falhar=True)
    env = EnviadorSftp(COLETOR, tmp_path / "dados", falho,
                       cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001")
    assert env.varrer() == []          # falhou, nada registrado
    ok = _TransporteFake()
    env2 = EnviadorSftp(COLETOR, tmp_path / "dados", ok,
                        cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001")
    assert env2.varrer() == ["2026-07-21_leituras.txt"]   # retry envia


def test_estado_persiste_entre_instancias(tmp_path):
    d = _dir(tmp_path)
    _selado(d, "2026-07-21_leituras.txt")
    EnviadorSftp(COLETOR, tmp_path / "dados", _TransporteFake(),
                cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001").varrer()
    estado = json.loads((d / "_enviados.json").read_text())
    assert "2026-07-21_leituras.txt" in estado
    # nova instância lê o estado e não reenvia
    env2 = EnviadorSftp(COLETOR, tmp_path / "dados", _TransporteFake(),
                        cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001")
    assert env2.varrer() == []


def test_envia_com_subcaminho_da_arvore(tmp_path):
    d = _dir(tmp_path)
    nome = "2026-07-21_HUB-0001-COL-RS485-BUS0_leituras.txt"
    _selado(d, nome)
    t = _TransporteFake()
    env = EnviadorSftp(COLETOR, tmp_path / "dados", t,
                       cliente_id="CLI-1", site_id="SITE-1", hub_id="HUB-0001")
    env.varrer()
    assert t.enviados == [
        f"CLI-1/2026/07/21/SITE-1/HUB-0001/{COLETOR}/{nome}"
    ]


def test_transporte_paramiko_conecta_autentica_e_poe(tmp_path):
    from hub import identidade_ssh
    chave_path = tmp_path / "ssh_hub"
    identidade_ssh.carregar_ou_criar_chave_ssh(chave_path)

    t = TransporteParamiko("192.168.0.10", 2022, "hub-1", str(chave_path), "/uploads")
    with mock.patch("paramiko.SSHClient") as MockClient, \
         mock.patch("paramiko.Ed25519Key") as MockKey:
        cliente = MockClient.return_value
        sftp = cliente.open_sftp.return_value
        t.enviar("/local/2026-07-21_leituras.txt", "2026-07-21_leituras.txt")

    MockKey.from_private_key_file.assert_called_once_with(str(chave_path))
    _, kwargs = cliente.connect.call_args
    assert kwargs["port"] == 2022
    assert kwargs["username"] == "hub-1"
    sftp.put.assert_called_once_with("/local/2026-07-21_leituras.txt",
                                     "/uploads/2026-07-21_leituras.txt")
    cliente.close.assert_called_once()


def test_transporte_cria_diretorios_antes_do_put():
    sftp = mock.Mock()
    existentes = set()
    def mkdir(p):
        if p in existentes:
            raise IOError("existe")
        existentes.add(p)
    sftp.mkdir.side_effect = mkdir
    cliente = mock.Mock()
    cliente.open_sftp.return_value = sftp
    with mock.patch("paramiko.SSHClient", return_value=cliente), \
         mock.patch("paramiko.Ed25519Key.from_private_key_file"):
        t = TransporteParamiko("h", 22, "u", "/dev/null", "/uploads")

        # --- 1ª chamada: árvore nova, nenhum nível existe ainda ---
        t.enviar("/local/x.txt", "CLI-1/2026/07/21/SITE-1/HUB-0001/COL/x.txt")

        # criou cada nível do pai sob /uploads, em ordem
        criados_1 = [c.args[0] for c in sftp.mkdir.call_args_list]
        assert criados_1 == [
            "/uploads/CLI-1", "/uploads/CLI-1/2026", "/uploads/CLI-1/2026/07",
            "/uploads/CLI-1/2026/07/21", "/uploads/CLI-1/2026/07/21/SITE-1",
            "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001",
            "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001/COL",
        ]
        sftp.put.assert_called_once_with(
            "/local/x.txt", "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001/COL/x.txt")

        # (b) ordem: os 7 mkdir da 1ª chamada aparecem como bloco contíguo
        # em sftp.mock_calls e o put vem logo depois — se _mkdir_p fosse
        # chamado depois do put, este bloco não existiria na sequência real.
        sftp.assert_has_calls(
            [mock.call.mkdir(p) for p in criados_1] +
            [mock.call.put("/local/x.txt",
                            "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001/COL/x.txt")]
        )

        sftp.reset_mock()

        # --- 2ª chamada: outro coletor sob a mesma árvore cliente/dia ---
        # (a) os níveis CLI-1 .. HUB-0001 já foram criados na 1ª chamada;
        # _mkdir_p deve engolir o IOError desses níveis (ramo "já existe")
        # e a chamada não deve propagar exceção. Só o nível novo (COL2) é
        # de fato criado sem levantar.
        t.enviar("/local/y.txt", "CLI-1/2026/07/21/SITE-1/HUB-0001/COL2/y.txt")

    criados_2 = [c.args[0] for c in sftp.mkdir.call_args_list]
    assert criados_2 == [
        "/uploads/CLI-1", "/uploads/CLI-1/2026", "/uploads/CLI-1/2026/07",
        "/uploads/CLI-1/2026/07/21", "/uploads/CLI-1/2026/07/21/SITE-1",
        "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001",
        "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001/COL2",
    ]
    sftp.put.assert_called_once_with(
        "/local/y.txt", "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001/COL2/y.txt")

    # (b) idem para a 2ª chamada: mesmo com mkdir levantando IOError
    # internamente para os níveis repetidos, todos os mkdir precedem o put.
    sftp.assert_has_calls(
        [mock.call.mkdir(p) for p in criados_2] +
        [mock.call.put("/local/y.txt",
                        "/uploads/CLI-1/2026/07/21/SITE-1/HUB-0001/COL2/y.txt")]
    )
