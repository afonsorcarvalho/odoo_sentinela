from datetime import datetime, date
from unittest.mock import patch

import pytz

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestArquivoClient(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('sentinela.api_url', 'http://api:8000')
        self.env['ir.config_parameter'].sudo().set_param(
            'sentinela.config_publish_secret', 's3cr3t')
        self.partner_a = self.env['res.partner'].create({'name': 'Hospital A', 'ref': 'CLI-A'})
        self.partner_b = self.env['res.partner'].create({'name': 'Hospital B', 'ref': 'CLI-B'})
        self.site_a = self.env['sensor_monitor.site'].create({
            'name': 'CME A', 'partner_id': self.partner_a.id,
            'site_code': 'SITE-ARQ-A', 'vertical': 'cme_hospitalar'})
        self.site_b = self.env['sensor_monitor.site'].create({
            'name': 'CME B', 'partner_id': self.partner_b.id,
            'site_code': 'SITE-ARQ-B', 'vertical': 'cme_hospitalar'})
        view_group = self.env.ref('afr_sentinela_sensor_monitor.group_sensor_monitor_view')
        self.user_a = self.env['res.users'].create({
            'name': 'Usuário A', 'login': 'usuario_arq_a@teste.com',
            'partner_id': self.partner_a.id,
            'groups_id': [(6, 0, [view_group.id, self.env.ref('base.group_user').id])]})

    def _client(self, user=None):
        modelo = self.env['sensor_monitor.arquivo.client']
        return modelo.with_user(user) if user else modelo

    def _resposta(self, status_code, blocos=(b'PK\x03\x04',), corpo_json=None, corpo_invalido=False):
        class Resp:
            def __init__(self):
                self.status_code = status_code

            def iter_content(self, chunk_size=None):
                return iter(blocos)

            def json(self):
                if corpo_invalido:
                    raise ValueError('corpo não é JSON')
                return corpo_json if corpo_json is not None else {}
        return Resp()

    def test_resolver_site_de_outro_cliente_levanta_access_error(self):
        # O isolamento vem do ir.rule rule_site_tenant; o client não usa sudo.
        with self.assertRaises(AccessError):
            self._client(self.user_a).resolver_site(self.site_b.id)

    def test_resolver_site_inexistente_levanta_access_error(self):
        # Mesma resposta de site alheio: não vazar existência de registro.
        with self.assertRaises(AccessError):
            self._client(self.user_a).resolver_site(0)

    def test_resolver_site_proprio_devolve_registro(self):
        assert self._client(self.user_a).resolver_site(self.site_a.id) == self.site_a

    def test_baixar_zip_monta_url_e_header(self):
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(200)
            nome, blocos = self._client(self.user_a).baixar_zip(
                self.site_a.id, date(2026, 7, 29))
            args, kwargs = mock_get.call_args
            assert args[0] == 'http://api:8000/internal/arquivos/zip'
            assert kwargs['params'] == {
                'cliente': 'CLI-A', 'site': 'SITE-ARQ-A', 'data': '2026-07-29'}
            assert kwargs['headers']['X-Config-Secret'] == 's3cr3t'
            assert kwargs['stream'] is True
            assert kwargs['timeout'] == 300
            assert nome == 'sentinela_SITE-ARQ-A_2026-07-29.zip'
            assert b''.join(blocos) == b'PK\x03\x04'

    def test_cliente_id_cai_para_partner_id_quando_ref_vazio(self):
        # Mesma regra de ingestao/odoo_cliente.py::resolver_coletor, que é
        # quem escreve a árvore do acervo. Divergir aqui gera 404 silencioso.
        self.partner_a.ref = False
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(200)
            self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            _args, kwargs = mock_get.call_args
            assert kwargs['params']['cliente'] == f'CLI-{self.partner_a.id}'

    def test_400_vira_mensagem_de_dados_invalidos(self):
        # site_code/partner.ref não têm a mesma validação de caracteres que a
        # api aplica ([A-Za-z0-9_-]); um 400 não é "serviço fora do ar".
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(400)
            with self.assertRaises(UserError) as ctx:
                self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            assert 'não aceito' in str(ctx.exception)

    def test_404_com_detail_de_dia_vazio_vira_mensagem_legivel(self):
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(
                404, corpo_json={'detail': 'nenhum arquivo para este dia/site'})
            with self.assertRaises(UserError) as ctx:
                self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            assert 'Nenhum arquivo' in str(ctx.exception)

    def test_404_com_detail_diferente_vira_servico_indisponivel(self):
        # Mesmo status code, corpo diferente: rota inexistente na api (ex.:
        # container não reiniciado após deploy) também devolve 404, e o
        # FastAPI gera {"detail": "Not Found"} pra isso — não é "dia sem
        # arquivo", é a api quebrada. Isso já aconteceu de verdade durante a
        # verificação desta branch.
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(404, corpo_json={'detail': 'Not Found'})
            with self.assertRaises(UserError) as ctx:
                self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            assert 'indisponível' in str(ctx.exception)

    def test_404_com_corpo_nao_json_vira_servico_indisponivel(self):
        # Guard contra resp.json() explodir (ex.: um proxy/reverse-proxy no
        # meio do caminho devolvendo HTML de erro em vez de JSON).
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(404, corpo_invalido=True)
            with self.assertRaises(UserError) as ctx:
                self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            assert 'indisponível' in str(ctx.exception)

    def test_413_vira_mensagem_de_volume(self):
        with patch('requests.get') as mock_get:
            mock_get.return_value = self._resposta(413)
            with self.assertRaises(UserError) as ctx:
                self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            assert 'limite' in str(ctx.exception)

    def test_erro_de_conexao_vira_servico_indisponivel(self):
        with patch('requests.get', side_effect=OSError('sem rota')):
            with self.assertRaises(UserError) as ctx:
                self._client(self.user_a).baixar_zip(self.site_a.id, date(2026, 7, 29))
            assert 'indisponível' in str(ctx.exception)


class TestArquivoDownloadWizard(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital W', 'ref': 'CLI-W'})
        self.site = self.env['sensor_monitor.site'].create({
            'name': 'CME W', 'partner_id': partner.id,
            'site_code': 'SITE-ARQ-W', 'vertical': 'cme_hospitalar'})

    def test_action_baixar_devolve_act_url_com_site_e_data(self):
        wizard = self.env['sensor_monitor.arquivo.download.wizard'].create({
            'site_id': self.site.id, 'data_referencia': '2026-07-29'})
        acao = wizard.action_baixar()
        assert acao['type'] == 'ir.actions.act_url'
        assert acao['target'] == 'self'
        assert f'site_id={self.site.id}' in acao['url']
        assert 'data=2026-07-29' in acao['url']
        assert acao['url'].startswith('/sentinela/arquivos/zip?')

    def test_data_referencia_default_e_hoje_no_fuso_do_usuario(self):
        # Fixa o fuso do contexto (em vez de deixar no fuso do usuário de
        # teste, que pode ser UTC) e calcula o "hoje" esperado de forma
        # INDEPENDENTE de fields.Date.context_today — chamar a mesma função
        # que o default usa pra construir a expectativa é tautológico, passa
        # em qualquer comportamento de fuso, e some com o teste virando
        # documentação morta de uma preocupação real (o campo tem que
        # refletir o fuso de quem está vendo o wizard, não o do servidor).
        tz = pytz.timezone('America/Sao_Paulo')
        esperado = pytz.UTC.localize(datetime.now()).astimezone(tz).date()
        wizard = self.env['sensor_monitor.arquivo.download.wizard'].with_context(
            tz='America/Sao_Paulo').create({'site_id': self.site.id})
        assert wizard.data_referencia == esperado
