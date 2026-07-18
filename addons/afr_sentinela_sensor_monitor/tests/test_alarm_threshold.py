from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestAlarmThreshold(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central', 'partner_id': partner.id,
            'site_code': 'SITE-010', 'vertical': 'cme_hospitalar',
        })
        area = self.env['sensor_monitor.area'].create({
            'name': 'Expurgo', 'site_id': site.id,
            'area_category_id': self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo').id,
            'area_code': 'AREA-010',
        })
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub', 'site_id': site.id, 'hub_code': 'HUB-010',
        })
        coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor', 'hub_id': hub.id, 'coletor_code': 'COL-010', 'tipo': 'esp32_wifi',
        })
        self.sensor = self.env['sensor_monitor.sensor'].create({
            'name': 'Sensor Temp', 'sensor_code': 'SNR-010',
            'coletor_id': coletor.id, 'area_id': area.id,
            'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
            'protocolo_origem': '4-20ma',
        })

    def test_rdc15_default_prefill_expurgo_temperatura(self):
        threshold = self.env['sensor_monitor.alarm.threshold'].create({'sensor_id': self.sensor.id})
        self.assertEqual(threshold.limite_min, 18.0)
        self.assertEqual(threshold.limite_max, 22.0)
        self.assertTrue(threshold.is_valor_padrao_regulatorio)

    def test_desvio_requires_justificativa(self):
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.alarm.threshold'].create({
                'sensor_id': self.sensor.id,
                'limite_min': 10.0,
                'limite_max': 30.0,
                'is_valor_padrao_regulatorio': False,
            })

    def test_desvio_with_justificativa_ok(self):
        threshold = self.env['sensor_monitor.alarm.threshold'].create({
            'sensor_id': self.sensor.id,
            'limite_min': 10.0,
            'limite_max': 30.0,
            'is_valor_padrao_regulatorio': False,
            'justificativa_desvio': 'Ajuste solicitado pela engenharia clínica.',
        })
        self.assertEqual(threshold.limite_min, 10.0)

    def test_unique_threshold_per_sensor(self):
        self.env['sensor_monitor.alarm.threshold'].create({'sensor_id': self.sensor.id})
        with self.assertRaises(Exception):
            self.env['sensor_monitor.alarm.threshold'].create({'sensor_id': self.sensor.id})
