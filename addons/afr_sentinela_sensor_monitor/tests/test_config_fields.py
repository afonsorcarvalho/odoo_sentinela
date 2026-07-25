from odoo.tests.common import TransactionCase


class TestConfigFields(TransactionCase):
    def test_campos_de_config_do_canal_existem_e_gravam(self):
        Sensor = self.env['sensor_monitor.sensor']
        campos = Sensor.fields_get(
            ['modbus_channel', 'ma_in_min', 'ma_in_max', 'eng_out_min',
             'eng_out_max', 'filtro_tipo', 'filtro_alpha'])
        assert set(campos) == {
            'modbus_channel', 'ma_in_min', 'ma_in_max', 'eng_out_min',
            'eng_out_max', 'filtro_tipo', 'filtro_alpha'}

    def test_driver_no_perfil(self):
        campos = self.env['sensor_monitor.modbus.profile'].fields_get(['driver'])
        assert campos['driver']['type'] == 'selection'

    def test_usa_map_existe_default_false(self):
        campos = self.env['sensor_monitor.sensor'].fields_get(['usa_map'])
        assert campos['usa_map']['type'] == 'boolean'
        s = self.env['sensor_monitor.sensor'].new({})
        assert s.usa_map is False

    def test_driver_aceita_rs_ws_n01_2d(self):
        campos = self.env['sensor_monitor.modbus.profile'].fields_get(['driver'])
        valores = dict(campos['driver']['selection'])
        assert 'rs_ws_n01_2d' in valores
