from odoo.tests.common import TransactionCase


class TestAlarmEvent(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central', 'partner_id': partner.id,
            'site_code': 'SITE-020', 'vertical': 'cme_hospitalar',
        })
        self.area = self.env['sensor_monitor.area'].create({
            'name': 'Expurgo', 'site_id': site.id,
            'area_category_id': self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo').id,
            'area_code': 'AREA-020',
        })
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub', 'site_id': site.id, 'hub_code': 'HUB-020',
        })
        self.coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor', 'hub_id': hub.id, 'coletor_code': 'COL-020', 'tipo': 'esp32_wifi',
        })
        self.sensor = self.env['sensor_monitor.sensor'].create({
            'name': 'Sensor Temp', 'sensor_code': 'SNR-020',
            'coletor_id': self.coletor.id, 'area_id': self.area.id,
            'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
            'protocolo_origem': '4-20ma',
        })

    def test_create_alarm_event_defaults_status_aberto(self):
        event = self.env['sensor_monitor.alarm.event'].create({
            'sensor_id': self.sensor.id,
            'area_id': self.area.id,
            'coletor_id': self.coletor.id,
            'timestamp_deteccao': '2026-07-16 03:14:00',
            'tipo_violacao': 'abaixo_limite',
            'valor_lido': 1.8,
            'limite_configurado_snapshot': 2.5,
        })
        self.assertEqual(event.status, 'aberto')

    def test_resolver_evento(self):
        event = self.env['sensor_monitor.alarm.event'].create({
            'sensor_id': self.sensor.id,
            'area_id': self.area.id,
            'coletor_id': self.coletor.id,
            'timestamp_deteccao': '2026-07-16 03:14:00',
            'tipo_violacao': 'abaixo_limite',
            'valor_lido': 1.8,
            'limite_configurado_snapshot': 2.5,
        })
        event.write({'status': 'resolvido', 'data_resolucao': '2026-07-16 03:30:00'})
        self.assertEqual(event.status, 'resolvido')
