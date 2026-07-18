from odoo import fields, models


class ModbusProfile(models.Model):
    _name = 'sensor_monitor.modbus.profile'
    _description = 'Perfil Modbus (catálogo)'

    name = fields.Char(required=True)
    fabricante = fields.Char()
    modelo = fields.Char()
    register_ids = fields.One2many('sensor_monitor.modbus.profile.register', 'profile_id')


class ModbusProfileRegister(models.Model):
    _name = 'sensor_monitor.modbus.profile.register'
    _description = 'Registrador do Perfil Modbus'

    profile_id = fields.Many2one('sensor_monitor.modbus.profile', required=True)
    name = fields.Char(required=True)
    measurement_type_id = fields.Many2one('sensor_monitor.measurement.type', required=True)
    function_code = fields.Selection([
        ('03_holding', '03 - Holding'), ('04_input', '04 - Input'),
    ], required=True)
    register_address = fields.Integer(required=True)
    register_count = fields.Integer(default=1, required=True)
    data_type = fields.Selection([
        ('int16', 'int16'), ('uint16', 'uint16'),
        ('int32', 'int32'), ('uint32', 'uint32'), ('float32', 'float32'),
    ], required=True)
    byte_order = fields.Selection([
        ('big', 'Big'), ('little', 'Little'),
        ('big_swap', 'Big Swap'), ('little_swap', 'Little Swap'),
    ], default='big', required=True)
    scale = fields.Float(default=1.0)
    offset = fields.Float(default=0.0)
    unidade = fields.Char()
