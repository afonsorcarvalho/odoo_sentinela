from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestRs485Modbus(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Hospital Teste'})
        site = self.env['sensor_monitor.site'].create({
            'name': 'CME Central', 'partner_id': partner.id,
            'site_code': 'SITE-040', 'vertical': 'cme_hospitalar',
        })
        self.area = self.env['sensor_monitor.area'].create({
            'name': 'Expurgo', 'site_id': site.id,
            'area_category_id': self.env.ref('afr_sentinela_sensor_monitor.area_category_expurgo').id,
            'area_code': 'AREA-040',
        })
        self.hub = self.env['sensor_monitor.hub'].create({
            'name': 'Hub', 'site_id': site.id, 'hub_code': 'HUB-040',
        })
        self.coletor = self.env['sensor_monitor.coletor'].create({
            'name': 'Coletor RS485', 'hub_id': self.hub.id,
            'coletor_code': 'COL-040', 'tipo': 'hub_rs485_embutido',
        })
        self.bus = self.env['sensor_monitor.rs485.bus'].create({
            'hub_id': self.hub.id, 'name': 'Barramento 1', 'bus_code': 'BUS-001',
            'serial_port': '/dev/ttyAMA0', 'baud_rate': 9600,
        })
        self.profile = self.env['sensor_monitor.modbus.profile'].create({
            'name': 'Transmissor Temp/Umidade TX-100', 'fabricante': 'Fabricante X', 'modelo': 'TX-100',
        })
        self.register = self.env['sensor_monitor.modbus.profile.register'].create({
            'profile_id': self.profile.id, 'name': 'Temperatura',
            'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
            'function_code': '04_input', 'register_address': 0, 'register_count': 1,
            'data_type': 'int16', 'byte_order': 'big', 'scale': 0.1, 'offset': 0.0,
        })

    def test_modbus_device_unique_slave_per_bus(self):
        self.env['sensor_monitor.modbus.device'].create({
            'name': 'Transdutor 1', 'rs485_bus_id': self.bus.id,
            'slave_address': 1, 'profile_id': self.profile.id,
        })
        with self.assertRaises(Exception):
            self.env['sensor_monitor.modbus.device'].create({
                'name': 'Transdutor 2', 'rs485_bus_id': self.bus.id,
                'slave_address': 1, 'profile_id': self.profile.id,
            })

    def test_sensor_modbus_register_requires_rs485(self):
        with self.assertRaises(ValidationError):
            self.env['sensor_monitor.sensor'].create({
                'name': 'Sensor Modbus', 'sensor_code': 'SNR-040',
                'coletor_id': self.coletor.id, 'area_id': self.area.id,
                'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
                'protocolo_origem': '4-20ma',
                'modbus_register_id': self.register.id,
            })

    def test_sensor_modbus_register_ok_with_rs485(self):
        sensor = self.env['sensor_monitor.sensor'].create({
            'name': 'Sensor Modbus', 'sensor_code': 'SNR-041',
            'coletor_id': self.coletor.id, 'area_id': self.area.id,
            'measurement_type_id': self.env.ref('afr_sentinela_sensor_monitor.measurement_type_temperatura').id,
            'protocolo_origem': 'rs485',
            'modbus_register_id': self.register.id,
        })
        self.assertEqual(sensor.modbus_register_id, self.register)
