from odoo import api, fields, models

CONVERSOR_TIPOS = [
    ('nenhum', 'Nenhum (sensor entrega direto)'),
    ('485_pt100', 'RS-485 PT100'),
    ('485_4_20ma', 'RS-485 4-20mA'),
    ('485_0_30v', 'RS-485 0-30V'),
]


class Calibracao(models.Model):
    _name = 'sensor_monitor.calibracao'
    _description = 'Certificado de Calibração da Malha'
    _order = 'sensor_id, versao desc'
    _rec_name = 'cert_numero'

    _sql_constraints = [
        ('versao_por_malha_unica', 'unique(sensor_id, versao)',
         'Já existe um certificado com esta versão para esta malha.'),
    ]

    sensor_id = fields.Many2one(
        'sensor_monitor.sensor', required=True, ondelete='cascade',
        help='A malha certificada (sensor + conversor).')
    cert_numero = fields.Char(help='Número do certificado emitido pela empresa de calibração.')
    versao = fields.Integer(
        required=True, default=1,
        help='Incremental por malha (v1, v2, …). Entra no snapshot de cada leitura.')
    cal_ganho = fields.Float(
        required=True, default=1.0, digits=(16, 6),
        help='Ganho multiplicativo CERTIFICADO, aplicado DEPOIS do map. '
             'Não confundir com o ganho do map nem com o scale do registrador Modbus.')
    cal_offset = fields.Float(
        required=True, default=0.0, digits=(16, 6),
        help='Offset aditivo CERTIFICADO da calibração. Distinto do offset do registrador Modbus.')
    validade_de = fields.Date(required=True)
    validade_ate = fields.Date(required=True)
    conversor_tipo_snapshot = fields.Selection(
        CONVERSOR_TIPOS, required=True, default='nenhum',
        help='Conversor da malha no momento da calibração (a calibração é do par sensor+conversor). '
             'Se o conversor atual do sensor divergir deste snapshot, este certificado deixa de valer.')
    empresa_calibracao_id = fields.Many2one('res.partner', string='Empresa de Calibração')
    documento = fields.Binary(string='Certificado (PDF)')
    documento_nome = fields.Char()
    estado = fields.Selection(
        [('vigente', 'Vigente'), ('expirado', 'Expirado'), ('futuro', 'Futuro')],
        compute='_compute_estado', store=False)

    @api.depends('validade_de', 'validade_ate')
    def _compute_estado(self):
        hoje = fields.Date.context_today(self)
        for cert in self:
            if cert.validade_de and hoje < cert.validade_de:
                cert.estado = 'futuro'
            elif cert.validade_ate and hoje > cert.validade_ate:
                cert.estado = 'expirado'
            else:
                cert.estado = 'vigente'
