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

    def test_laudo_pdf_nao_vazio(self):
        with self._patch():
            r = self.url_open('/verificar-autenticidade/JID/laudo.pdf')
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.content[:4] == b'%PDF')
