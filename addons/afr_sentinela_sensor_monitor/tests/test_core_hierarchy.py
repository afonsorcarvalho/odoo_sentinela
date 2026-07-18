from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestCoreHierarchy(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        self.area_category = self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo')
        self.measurement_type = self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura')

    def _create_site(self, **overrides):
        vals = {
            'name': 'CME Central',
            'partner_id': self.partner.id,
            'site_code': 'SITE-001',
            'vertical': 'cme_hospitalar',
        }
        vals.update(overrides)
        return self.env['sensor_monitor.site'].create(vals)

    def test_site_retention_years_floor(self):
        with self.assertRaises(ValidationError):
            self._create_site(retention_mode='expurgar_apos', retention_years=3)

    def test_site_retention_years_default_ok(self):
        site = self._create_site()
        self.assertEqual(site.retention_years, 5)

    def test_site_code_forbids_pipe(self):
        with self.assertRaises(ValidationError):
            self._create_site(site_code='SITE|001')

    def test_area_code_forbids_pipe(self):
        site = self._create_site()
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.area'].create({
                'name': 'Expurgo',
                'site_id': site.id,
                'area_category_id': self.area_category.id,
                'area_code': 'AREA|001',
            })

    def test_sensor_requires_coletor_and_area(self):
        site = self._create_site()
        area = self.env['sensor_monitor.area'].create({
            'name': 'Expurgo',
            'site_id': site.id,
            'area_category_id': self.area_category.id,
            'area_code': 'AREA-001',
        })
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub 1',
            'site_id': site.id,
            'hub_code': 'HUB-001',
        })
        coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor 1',
            'hub_id': hub.id,
            'coletor_code': 'COL-001',
            'tipo': 'esp32_wifi',
        })
        sensor = self.env['sensor_monitor.sensor'].create({
            'name': 'Sensor Temp Expurgo',
            'sensor_code': 'SNR-001',
            'coletor_id': coletor.id,
            'area_id': area.id,
            'measurement_type_id': self.measurement_type.id,
            'protocolo_origem': '4-20ma',
        })
        self.assertTrue(sensor.coletor_id)
        self.assertTrue(sensor.area_id)
        with self.assertRaises(Exception):
            self.env['sensor_monitor.sensor'].create({
                'name': 'Sensor órfão',
                'sensor_code': 'SNR-002',
                'measurement_type_id': self.measurement_type.id,
                'protocolo_origem': '4-20ma',
            })

    def test_coletor_is_hub_embutido_computed(self):
        site = self._create_site(site_code='SITE-002')
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub 2', 'site_id': site.id, 'hub_code': 'HUB-002',
        })
        coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor RS485', 'hub_id': hub.id,
            'coletor_code': 'COL-002', 'tipo': 'hub_rs485_embutido',
        })
        self.assertTrue(coletor.is_hub_embutido)
