from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DashboardConfig(models.Model):
    _name = 'sensor_monitor.dashboard.config'
    _description = 'Configuração do Dashboard'

    site_id = fields.Many2one('sensor_monitor.site', required=True, ondelete='cascade')
    carousel_interval_ms = fields.Integer(
        default=3000, required=True, string='Intervalo do carrossel (ms)',
    )

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
