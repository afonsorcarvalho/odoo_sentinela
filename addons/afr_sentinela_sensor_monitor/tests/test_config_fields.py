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
