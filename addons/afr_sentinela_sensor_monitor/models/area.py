from odoo import fields, models


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
