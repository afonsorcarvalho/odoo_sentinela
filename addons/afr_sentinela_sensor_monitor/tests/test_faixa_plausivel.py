from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestFaixaPlausivel(TransactionCase):
    def _sensor(self, **vals):
        site = self.env['sensor_monitor.site'].create({
            'name': 'S', 'site_code': 'SITE-FX-01', 'vertical': 'cme_hospitalar',
            'partner_id': self.env['res.partner'].create({'name': 'P'}).id})
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'H', 'site_id': site.id, 'hub_code': 'HUB-FX-01'})
        coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'C', 'hub_id': hub.id, 'coletor_code': 'COL-FX-01',
            'tipo': 'esp32_wifi'})
        area = self.env['sensor_monitor.area'].create({
            'name': 'A', 'site_id': site.id, 'area_code': 'AREA-FX-01',
            'area_category_id': self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo').id})
        tipo = self.env['sensor_monitor.measurement.type'].search(
            [('code', '=', 'temperatura')], limit=1)
        data = {
            'name': 'Sn', 'sensor_code': 'SNR-FX-01', 'coletor_id': coletor.id,
            'area_id': area.id, 'measurement_type_id': tipo.id, 'protocolo_origem': '4-20ma',
        }
        data.update(vals)
        return self.env['sensor_monitor.sensor'].create(data)

    def test_faixa_min_maior_igual_max_com_usa_faixa_levanta_erro(self):
        with self.assertRaises(ValidationError):
            self._sensor(usa_faixa=True, faixa_min=100.0, faixa_max=50.0)

    def test_faixa_valida_com_usa_faixa_persiste(self):
        sensor = self._sensor(usa_faixa=True, faixa_min=10.0, faixa_max=90.0)
        self.assertTrue(sensor.usa_faixa)
        self.assertEqual(sensor.faixa_min, 10.0)
        self.assertEqual(sensor.faixa_max, 90.0)

    def test_faixa_invalida_sem_usa_faixa_nao_levanta_erro(self):
        sensor = self._sensor(usa_faixa=False, faixa_min=100.0, faixa_max=50.0)
        self.assertFalse(sensor.usa_faixa)
