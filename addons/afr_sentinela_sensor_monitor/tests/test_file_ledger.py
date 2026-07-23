from odoo.tests.common import TransactionCase


class TestFileLedger(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central', 'partner_id': partner.id,
            'site_code': 'SITE-030', 'vertical': 'cme_hospitalar',
        })
        self.hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub', 'site_id': site.id, 'hub_code': 'HUB-030',
        })
        self.coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor', 'hub_id': self.hub.id, 'coletor_code': 'COL-030', 'tipo': 'esp32_wifi',
        })

    def test_unique_ledger_per_coletor_dia_tipo(self):
        self.env['sensor_monitor.file.ledger'].create({
            'coletor_id': self.coletor.id, 'tipo_arquivo': 'leituras',
            'data_referencia': '2026-07-16', 'status_validacao': 'valido',
        })
        with self.assertRaises(Exception):
            self.env['sensor_monitor.file.ledger'].create({
                'coletor_id': self.coletor.id, 'tipo_arquivo': 'leituras',
                'data_referencia': '2026-07-16', 'status_validacao': 'valido',
            })

    def test_hub_id_denormalizado(self):
        ledger = self.env['sensor_monitor.file.ledger'].create({
            'coletor_id': self.coletor.id, 'tipo_arquivo': 'alarmes',
            'data_referencia': '2026-07-16', 'status_validacao': 'valido',
        })
        self.assertEqual(ledger.hub_id, self.hub)

    def test_status_incompleto_e_aceito(self):
        campos = self.env['sensor_monitor.file.ledger'].fields_get(['status_validacao'])
        valores = dict(campos['status_validacao']['selection'])
        assert 'incompleto' in valores

    def test_cron_detect_gaps_creates_missing_entry(self):
        self.env['sensor_monitor.file.ledger'].create({
            'coletor_id': self.coletor.id, 'tipo_arquivo': 'leituras',
            'data_referencia': '2026-07-14', 'status_validacao': 'valido',
        })
        self.env['sensor_monitor.file.ledger'].create({
            'coletor_id': self.coletor.id, 'tipo_arquivo': 'leituras',
            'data_referencia': '2026-07-16', 'status_validacao': 'valido',
        })
        self.env['sensor_monitor.file.ledger']._cron_detect_gaps()
        gap = self.env['sensor_monitor.file.ledger'].search([
            ('coletor_id', '=', self.coletor.id),
            ('tipo_arquivo', '=', 'leituras'),
            ('data_referencia', '=', '2026-07-15'),
        ])
        self.assertEqual(len(gap), 1)
        self.assertEqual(gap.status_validacao, 'faltante')
