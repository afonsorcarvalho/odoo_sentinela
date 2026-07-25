import json
from datetime import datetime

from hub.arquivo_diario import ArquivoDiario
from hub.assinador import AssinadorSoftware
from ingestao import registro_coletores
from scripts import verificar_autenticidade as cli


def _leitura(ts):
    return {'timestamp': ts, 'sensor_id': 'SNR-1', 'area_id': 'EXPURGO',
            'tipo_medida': 'temperatura', 'valor': 96.83, 'unidade': 'C',
            'protocolo_origem': '4-20ma', 'status_leitura': 'ok',
            'cert_ver': 3, 'cal_ganho': 0.965, 'cal_offset': 0.33}


def _dia(tmp_path, subdir, coletor='COL-1', selar=True, registro=None):
    assinador = AssinadorSoftware(str(tmp_path / f"{subdir}.pem"))
    arq = ArquivoDiario(coletor, 'HUB-1', '2.3.1', '-03:00', str(tmp_path / subdir),
                        assinador, cliente_id='CLI-1', site_id='SITE-1')
    arq.registrar(_leitura(datetime(2026, 7, 16, 0, 1, 0)))
    if selar:
        arq.selar('2026-07-16')
    if registro:
        registro_coletores.registrar_coletor(registro, coletor, assinador.chave_publica_pem())
    return arq.caminho('2026-07-16')


def test_arquivo_unico_valido_exit_0(tmp_path, capsys):
    registro = str(tmp_path / "reg.json")
    caminho = _dia(tmp_path, "d", registro=registro)
    rc = cli.main([str(caminho), '--registro', registro])
    assert rc == 0
    assert 'valido' in capsys.readouterr().out.lower()


def test_diretorio_com_invalido_exit_1(tmp_path, capsys):
    registro = str(tmp_path / "reg.json")
    raiz = tmp_path / "arvore"
    bom = _dia(tmp_path, "arvore/ok", coletor='COL-OK', registro=registro)  # noqa: F841
    ruim = _dia(tmp_path, "arvore/ruim", coletor='COL-RUIM', registro=registro)
    linhas = ruim.read_text().split('\n')
    i = next(i for i, l in enumerate(linhas) if l and not l.startswith('#'))
    campos = linhas[i].split('|'); campos[5] = '1.23'; linhas[i] = '|'.join(campos)
    ruim.write_text('\n'.join(linhas))
    rc = cli.main([str(raiz), '--registro', registro, '--json'])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload['validos'] == 1 and payload['invalidos'] == 1


def test_json_output(tmp_path, capsys):
    registro = str(tmp_path / "reg.json")
    caminho = _dia(tmp_path, "d", registro=registro)
    rc = cli.main([str(caminho), '--registro', registro, '--json'])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['total'] == 1 and payload['validos'] == 1
    assert payload['itens'][0]['estado'] == 'valido'


def test_caminho_inexistente_exit_4(tmp_path):
    rc = cli.main([str(tmp_path / "nao-existe"), '--registro', str(tmp_path / "r.json")])
    assert rc == 4


def test_pem_ilegivel_exit_4(tmp_path):
    caminho = _dia(tmp_path, "d")
    pem = tmp_path / "ruim.pem"; pem.write_text("nao eh pem")
    rc = cli.main([str(caminho), '--pem', str(pem)])
    assert rc == 4


def test_diretorio_sem_txt_exit_4(tmp_path):
    vazio = tmp_path / "vazio"; vazio.mkdir()
    rc = cli.main([str(vazio), '--registro', str(tmp_path / "r.json")])
    assert rc == 4
