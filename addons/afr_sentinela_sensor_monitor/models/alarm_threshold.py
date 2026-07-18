from odoo import api, fields, models
from odoo.exceptions import ValidationError

RDC15_DEFAULTS = {
    ('EXPURGO', 'temperatura'): (18.0, 22.0),
    ('EXPURGO', 'pressao_diferencial'): (None, -2.5),
    ('PREPARO_ESTERILIZACAO', 'temperatura'): (20.0, 24.0),
    ('PREPARO_ESTERILIZACAO', 'pressao_diferencial'): (2.5, None),
}


class AlarmThreshold(models.Model):
    _name = 'sensor_monitor.alarm.threshold'
    _inherit = ['mail.thread']
    _description = 'Limiar de Alarme'

    sensor_id = fields.Many2one('sensor_monitor.sensor', required=True)
    limite_min = fields.Float(tracking=True)
    limite_max = fields.Float(tracking=True)
    is_valor_padrao_regulatorio = fields.Boolean(default=False)
    origem_ultima_alteracao = fields.Selection([
        ('hub', 'Hub'),
        ('nuvem', 'Nuvem'),
    ], default='nuvem')
    justificativa_desvio = fields.Text()

    _sql_constraints = [
        ('sensor_id_unique', 'unique(sensor_id)', 'Já existe um limiar cadastrado para este sensor.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'limite_min' not in vals and 'limite_max' not in vals:
                sensor = self.env['sensor_monitor.sensor'].browse(vals['sensor_id'])
                key = (sensor.area_id.area_category_id.code, sensor.measurement_type_id.code)
                default = RDC15_DEFAULTS.get(key)
                if default:
                    vals['limite_min'], vals['limite_max'] = default
                    vals['is_valor_padrao_regulatorio'] = True
        return super().create(vals_list)

    @api.constrains('is_valor_padrao_regulatorio', 'justificativa_desvio', 'sensor_id')
    def _check_justificativa_desvio(self):
        for threshold in self:
            vertical = threshold.sensor_id.area_id.site_id.vertical
            if not threshold.is_valor_padrao_regulatorio and vertical == 'cme_hospitalar':
                if not threshold.justificativa_desvio:
                    raise ValidationError(
                        'Desvio do padrão regulatório exige justificativa preenchida.'
                    )
