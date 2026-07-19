import json

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DashboardConfig(models.Model):
    _name = 'sensor_monitor.dashboard.config'
    _description = 'Configuração do Dashboard'

    site_id = fields.Many2one('sensor_monitor.site', required=True, ondelete='cascade')
    carousel_interval_ms = fields.Integer(
        default=3000, required=True, string='Intervalo do carrossel (ms)',
    )
    layout_json = fields.Text(string='Layout do dashboard (JSON)')
    layout_version = fields.Integer(string='Versão do schema de layout', default=1)

    _sql_constraints = [
        ('site_id_unique', 'unique(site_id)', 'Já existe uma configuração de dashboard para este site.'),
    ]

    @api.constrains('carousel_interval_ms')
    def _check_carousel_interval_floor(self):
        for config in self:
            if config.carousel_interval_ms < 1000:
                raise ValidationError(
                    'carousel_interval_ms não pode ser menor que 1000 (piso de legibilidade).'
                )

    @api.constrains('layout_json')
    def _check_layout_json_parseavel(self):
        for config in self:
            if not config.layout_json:
                continue
            try:
                json.loads(config.layout_json)
            except (ValueError, TypeError):
                raise ValidationError('layout_json deve ser um JSON válido.')
