from datetime import timedelta

from odoo import fields, models


class FileLedger(models.Model):
    _name = 'sensor_monitor.file.ledger'
    _description = 'Ledger de Recebimento de Arquivo'

    coletor_id = fields.Many2one('sensor_monitor.coletor', required=True)
    hub_id = fields.Many2one('sensor_monitor.hub', related='coletor_id.hub_id', store=True)
    tipo_arquivo = fields.Selection([
        ('leituras', 'Leituras'),
        ('alarmes', 'Alarmes'),
    ], required=True)
    data_referencia = fields.Date(required=True)
    hash_final = fields.Char()
    assinatura = fields.Char()
    horario_recebimento = fields.Datetime()
    status_validacao = fields.Selection([
        ('valido', 'Válido'),
        ('invalido', 'Inválido'),
        ('pendente', 'Pendente'),
        ('faltante', 'Faltante'),
    ], default='pendente', required=True)
    motivo_rejeicao = fields.Text()
    total_linhas = fields.Integer(default=0)

    _sql_constraints = [
        ('unique_coletor_dia_tipo', 'unique(coletor_id, data_referencia, tipo_arquivo)',
         'Já existe um registro de ledger para este coletor/dia/tipo de arquivo.'),
    ]

    def _cron_detect_gaps(self):
        for coletor in self.env['sensor_monitor.coletor'].search([]):
            for tipo in ('leituras', 'alarmes'):
                entries = self.search([
                    ('coletor_id', '=', coletor.id), ('tipo_arquivo', '=', tipo),
                ], order='data_referencia asc')
                if len(entries) < 2:
                    continue
                known_dates = set(entries.mapped('data_referencia'))
                current = entries[0].data_referencia
                last = entries[-1].data_referencia
                while current <= last:
                    if current not in known_dates:
                        self.create({
                            'coletor_id': coletor.id, 'tipo_arquivo': tipo,
                            'data_referencia': current, 'status_validacao': 'faltante',
                        })
                    current += timedelta(days=1)
