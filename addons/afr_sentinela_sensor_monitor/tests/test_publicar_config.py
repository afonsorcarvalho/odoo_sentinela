from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestPublicarConfig(TransactionCase):
    def _hub(self):
        site = self.env['sensor_monitor.site'].create({
            'name': 'S', 'partner_id': self.env['res.partner'].create({'name': 'P'}).id,
            'site_code': 'SITE-PUB-01', 'vertical': 'cme_hospitalar'})
        return self.env['sensor_monitor.hub'].create({
            'name': 'H', 'site_id': site.id, 'hub_code': 'HUB-PUB-01'})

    def test_publicar_incrementa_versao_e_chama_api(self):
        self.env['ir.config_parameter'].sudo().set_param('sentinela.api_url', 'http://api:8000')
        self.env['ir.config_parameter'].sudo().set_param('sentinela.config_publish_secret', 's3cr3t')
        hub = self._hub()
        v0 = hub.config_version_desejada
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            hub.action_publicar_config()
            assert hub.config_version_desejada == v0 + 1
            args, kwargs = mock_post.call_args
            assert 'HUB-PUB-01/publicar-config' in args[0]
            assert kwargs['headers']['X-Config-Secret'] == 's3cr3t'

    def test_drift_computado(self):
        hub = self._hub()
        hub.config_version_desejada = 5
        hub.config_version_aplicada = 4
        assert hub.config_em_drift is True
        hub.config_version_aplicada = 5
        assert hub.config_em_drift is False
