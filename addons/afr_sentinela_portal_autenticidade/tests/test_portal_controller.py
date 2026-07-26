from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestPortalController(HttpCase):
    def test_pagina_publica_200(self):
        r = self.url_open('/verificar-autenticidade')
        self.assertEqual(r.status_code, 200)
        self.assertIn('verifica', r.text.lower())

    def test_post_repassa_e_retorna_job(self):
        with patch(
            'odoo.addons.afr_sentinela_portal_autenticidade.models.verificacao_client'
            '.VerificacaoClient.enviar',
            return_value={'job_id': 'JID', 'posicao': 1},
        ):
            r = self.url_open('/verificar-autenticidade',
                              files={'arquivo': ('a.txt', b'x')})
            self.assertEqual(r.status_code, 200)
            self.assertIn('JID', r.text)

    def test_upload_grande_rejeitado(self):
        big = b'x' * (26 * 1024 * 1024)
        r = self.url_open('/verificar-autenticidade', files={'arquivo': ('big.bin', big)})
        self.assertEqual(r.status_code, 200)
        self.assertIn('muito grande', r.text.lower())

    def test_status_proxy(self):
        with patch(
            'odoo.addons.afr_sentinela_portal_autenticidade.models.verificacao_client'
            '.VerificacaoClient.status',
            return_value={'estado': 'processando', 'posicao': 2},
        ):
            r = self.url_open('/verificar-autenticidade/JID')
            self.assertEqual(r.status_code, 200)
            self.assertIn('processando', r.text)
