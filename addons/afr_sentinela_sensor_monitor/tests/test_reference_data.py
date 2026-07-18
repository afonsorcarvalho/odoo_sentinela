from odoo.tests.common import TransactionCase


class TestReferenceData(TransactionCase):

    def test_area_category_rdc15_codes_exist(self):
        codes = self.env['sensor_monitor.area.category'].search([]).mapped('code')
        self.assertIn('EXPURGO', codes)
        self.assertIn('PREPARO_ESTERILIZACAO', codes)
        self.assertIn('DESINFECCAO_QUIMICA', codes)

    def test_measurement_type_codes_exist(self):
        codes = self.env['sensor_monitor.measurement.type'].search([]).mapped('code')
        self.assertIn('temperatura', codes)
        self.assertIn('umidade_relativa', codes)
        self.assertIn('pressao_diferencial', codes)

    def test_measurement_type_unidade_padrao(self):
        temp = self.env['sensor_monitor.measurement.type'].search([('code', '=', 'temperatura')])
        self.assertEqual(temp.unidade_padrao, 'C')
