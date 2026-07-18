from odoo import api, fields, models

from .common import validate_code


class Area(models.Model):
    _name = 'sensor_monitor.area'
    _description = 'Área/Sala'

    name = fields.Char(required=True)
    site_id = fields.Many2one('sensor_monitor.site', required=True)
    area_category_id = fields.Many2one('sensor_monitor.area.category', required=True)
    area_code = fields.Char(required=True)

    _sql_constraints = [
        ('area_code_unique_per_site', 'unique(site_id, area_code)', 'Código de área já usado neste site.'),
    ]

    @api.constrains('area_code')
    def _check_area_code(self):
        for area in self:
            validate_code(area.area_code)
