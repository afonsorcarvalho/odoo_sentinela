from odoo import fields, models


class ArquivoDownloadWizard(models.TransientModel):
    _name = 'sensor_monitor.arquivo.download.wizard'
    _description = 'Baixar arquivos do dia'

    data_referencia = fields.Date(
        string='Data', required=True, default=fields.Date.context_today)
    site_id = fields.Many2one('sensor_monitor.site', string='Site', required=True)

    def action_baixar(self):
        """Redireciona para o controller, que faz o streaming do ZIP.

        act_url em vez de baixar aqui: o wizard não pode segurar dezenas de MB
        na resposta JSON-RPC.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': (f'/sentinela/arquivos/zip?site_id={self.site_id.id}'
                    f'&data={self.data_referencia.isoformat()}'),
            'target': 'self',
        }
