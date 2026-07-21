from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestDashboardConfig(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        self.site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central',
            'partner_id': partner.id,
            'site_code': 'SITE-020',
            'vertical': 'cme_hospitalar',
        })

    def test_cria_config_associada_ao_site(self):
        config = self.env['sensor_monitor.dashboard.config'].create({
            'site_id': self.site.id,
            'carousel_interval_ms': 5000,
        })
        self.assertEqual(config.site_id, self.site)
        self.assertEqual(config.carousel_interval_ms, 5000)

    def test_default_carousel_interval_ms_e_3000(self):
        config = self.env['sensor_monitor.dashboard.config'].create({'site_id': self.site.id})
        self.assertEqual(config.carousel_interval_ms, 3000)

    def test_default_carousel_transition_ms_e_300(self):
        config = self.env['sensor_monitor.dashboard.config'].create({'site_id': self.site.id})
        self.assertEqual(config.carousel_transition_ms, 300)

    def test_cria_config_com_carousel_transition_ms(self):
        config = self.env['sensor_monitor.dashboard.config'].create({
            'site_id': self.site.id,
            'carousel_transition_ms': 600,
        })
        self.assertEqual(config.carousel_transition_ms, 600)

    def test_carousel_transition_ms_acima_do_teto_falha(self):
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.dashboard.config'].create({
                'site_id': self.site.id,
                'carousel_transition_ms': 3000,
            })

    def test_carousel_transition_ms_negativo_falha(self):
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.dashboard.config'].create({
                'site_id': self.site.id,
                'carousel_transition_ms': -10,
            })

    def test_site_id_unico_impede_segunda_config_no_mesmo_site(self):
        self.env['sensor_monitor.dashboard.config'].create({'site_id': self.site.id})
        with self.assertRaises(Exception):
            self.env['sensor_monitor.dashboard.config'].create({'site_id': self.site.id})

    def test_carousel_interval_ms_abaixo_do_piso_falha(self):
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.dashboard.config'].create({
                'site_id': self.site.id,
                'carousel_interval_ms': 500,
            })

    def test_layout_json_persiste(self):
        config = self.env['sensor_monitor.dashboard.config'].create({
            'site_id': self.site.id,
            'layout_json': '{"version": 1, "grid": {"cols": 12, "rowHeight": 40, "margin": [8, 8]}, "widgets": []}',
            'layout_version': 1,
        })
        self.assertEqual(config.layout_version, 1)
        self.assertIn('"version": 1', config.layout_json)

    def test_layout_json_invalido_rejeitado(self):
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.dashboard.config'].create({
                'site_id': self.site.id,
                'layout_json': 'isso nao e json',
            })

    def test_layout_version_default_um(self):
        config = self.env['sensor_monitor.dashboard.config'].create({'site_id': self.site.id})
        self.assertEqual(config.layout_version, 1)
