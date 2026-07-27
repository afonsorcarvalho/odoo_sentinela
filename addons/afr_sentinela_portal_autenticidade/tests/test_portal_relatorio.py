from unittest.mock import patch

from odoo.tests import HttpCase, tagged

LOTE = {
    'total': 2, 'validos': 1, 'invalidos': 1, 'incompletos': 0, 'indeterminados': 0,
    'todos_ok': False,
    'itens': [
        {'nome': 'a.txt', 'estado': 'valido', 'motivo': None, 'coletor_id': 'COL-1',
         'data_referencia': '2026-07-16', 'total_linhas': 2, 'hash_final': 'abc',
         'fingerprint_conferido': None},
        {'nome': 'b.txt', 'estado': 'invalido', 'motivo': 'cadeia quebrada',
         'coletor_id': 'COL-1', 'data_referencia': '2026-07-16', 'total_linhas': 0,
         'hash_final': None, 'fingerprint_conferido': None},
    ],
}


@tagged('post_install', '-at_install')
class TestPortalRelatorio(HttpCase):
    def _patch(self, estado='pronto'):
        return patch(
            'odoo.addons.afr_sentinela_portal_autenticidade.models.verificacao_client'
            '.VerificacaoClient.status',
            return_value={'estado': estado, 'lote': LOTE})

    def test_relatorio_na_tela(self):
        with self._patch():
            r = self.url_open('/verificar-autenticidade/JID')
            self.assertEqual(r.status_code, 200)
            self.assertIn('a.txt', r.text)
            self.assertIn('b.txt', r.text)

    def test_download_json(self):
        with self._patch():
            r = self.url_open('/verificar-autenticidade/JID/relatorio.json')
            self.assertEqual(r.status_code, 200)
            self.assertIn('application/json', r.headers.get('Content-Type', ''))
            self.assertIn('"total": 2', r.text)

    def test_estado_expirado_mostra_erro_sem_polling(self):
        with patch('odoo.addons.afr_sentinela_portal_autenticidade.models.verificacao_client'
                   '.VerificacaoClient.status', return_value={'estado': 'expirado'}):
            r = self.url_open('/verificar-autenticidade/JID')  # full page (Accept text/html)
            self.assertEqual(r.status_code, 200)
            self.assertIn('expirou', r.text.lower())
            self.assertNotIn('data-job-id', r.text)  # sem widget de polling -> nao faz loop

    def test_laudo_pdf_nao_vazio(self):
        # Mocka o renderer de PDF: wkhtmltopdf real, dentro de --test-enable,
        # faz um callback HTTP de volta ao mesmo servidor Odoo single-thread
        # para header/footer, e isso trava (deadlock) contra a transacao de
        # teste aberta. Renderizacao real de PDF funciona no servidor ao
        # vivo (multi-request); aqui so verificamos a fiacao do controller.
        with patch(
            'odoo.addons.base.models.ir_actions_report.IrActionsReport'
            '._render_qweb_pdf',
            return_value=(b'%PDF-1.4 laudo-fake', 'pdf'),
        ):
            with self._patch():
                r = self.url_open('/verificar-autenticidade/JID/laudo.pdf')
        self.assertEqual(r.status_code, 200)
        self.assertIn('application/pdf', r.headers.get('Content-Type', ''))
        self.assertTrue(r.content.startswith(b'%PDF'))
