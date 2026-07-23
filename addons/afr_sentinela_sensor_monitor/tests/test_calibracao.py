from datetime import date, timedelta

from odoo.tests.common import TransactionCase


class TestCalibracao(TransactionCase):
    def _sensor(self):
        site = self.env['sensor_monitor.site'].create({
            'name': 'S', 'site_code': 'SITE-CAL-01', 'vertical': 'cme_hospitalar',
            'partner_id': self.env['res.partner'].create({'name': 'P'}).id})
        hub = self.env['sensor_monitor.hub'].create({
            'name': 'H', 'site_id': site.id, 'hub_code': 'HUB-CAL-01'})
        coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'C', 'hub_id': hub.id, 'coletor_code': 'COL-CAL-01',
            'tipo': 'esp32_wifi'})
        area = self.env['sensor_monitor.area'].create({
            'name': 'A', 'site_id': site.id, 'area_code': 'AREA-CAL-01',
            'area_category_id': self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo').id})
        tipo = self.env['sensor_monitor.measurement.type'].search(
            [('code', '=', 'temperatura')], limit=1)
        return self.env['sensor_monitor.sensor'].create({
            'name': 'Sn', 'sensor_code': 'SNR-CAL-01', 'coletor_id': coletor.id,
            'area_id': area.id, 'measurement_type_id': tipo.id, 'protocolo_origem': '4-20ma'})

    def test_certificado_grava_e_computa_estado_vigente(self):
        sensor = self._sensor()
        hoje = date.today()
        cert = self.env['sensor_monitor.calibracao'].create({
            'sensor_id': sensor.id, 'cert_numero': 'CERT-001', 'versao': 1,
            'cal_ganho': 0.965, 'cal_offset': 0.33,
            'validade_de': hoje - timedelta(days=10),
            'validade_ate': hoje + timedelta(days=355),
            'conversor_tipo_snapshot': 'nenhum'})
        assert cert.estado == 'vigente'

    def test_estado_futuro_e_expirado(self):
        sensor = self._sensor()
        hoje = date.today()
        futuro = self.env['sensor_monitor.calibracao'].create({
            'sensor_id': sensor.id, 'cert_numero': 'CERT-F', 'versao': 1,
            'cal_ganho': 1.0, 'cal_offset': 0.0,
            'validade_de': hoje + timedelta(days=5),
            'validade_ate': hoje + timedelta(days=365),
            'conversor_tipo_snapshot': 'nenhum'})
        expirado = self.env['sensor_monitor.calibracao'].create({
            'sensor_id': sensor.id, 'cert_numero': 'CERT-E', 'versao': 2,
            'cal_ganho': 1.0, 'cal_offset': 0.0,
            'validade_de': hoje - timedelta(days=400),
            'validade_ate': hoje - timedelta(days=35),
            'conversor_tipo_snapshot': 'nenhum'})
        assert futuro.estado == 'futuro'
        assert expirado.estado == 'expirado'
