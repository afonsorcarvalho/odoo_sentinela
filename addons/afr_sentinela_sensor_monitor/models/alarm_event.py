from odoo import fields, models


class AlarmEvent(models.Model):
    _name = 'sensor_monitor.alarm.event'
    _inherit = ['mail.thread']
    _description = 'Evento de Alarme'

    sensor_id = fields.Many2one('sensor_monitor.sensor')
    area_id = fields.Many2one('sensor_monitor.area')
    coletor_id = fields.Many2one('sensor_monitor.coletor')
    timestamp_deteccao = fields.Datetime(required=True)
    timestamp_resolucao_sensor = fields.Datetime()
    valor_lido = fields.Float()
    tipo_violacao = fields.Selection([
        ('acima_limite', 'Acima do limite'),
        ('abaixo_limite', 'Abaixo do limite'),
        ('sensor_offline', 'Sensor offline'),
        ('erro_leitura', 'Erro de leitura'),
    ], required=True)
    limite_configurado_snapshot = fields.Float()
    origem_arquivo_hash = fields.Char()
    status = fields.Selection([
        ('aberto', 'Aberto'),
        ('reconhecido', 'Reconhecido'),
        ('resolvido', 'Resolvido'),
    ], default='aberto', required=True, tracking=True)
    usuario_responsavel_id = fields.Many2one('res.users')
    data_resolucao = fields.Datetime()
    observacoes = fields.Text()
