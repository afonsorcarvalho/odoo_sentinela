from odoo import api, fields, models

# Campos da linha do laudo espelhados a partir de VerificacaoItem (dict do
# lote devolvido pelo api). Whitelist explicita: o dict do lote pode conter
# chaves extras (ex.: 'hash_final') que não existem no modelo transient —
# um **item cru quebraria o create() com "Invalid field".
_CAMPOS_LINHA = (
    'nome', 'estado', 'motivo', 'coletor_id', 'data_referencia',
    'total_linhas', 'fingerprint_conferido',
)


class VerificacaoLaudo(models.TransientModel):
    _name = 'sensor_monitor.verificacao.laudo'
    _description = 'Laudo de verificação de autenticidade (efêmero)'

    total = fields.Integer(string='Total')
    validos = fields.Integer(string='Válidos')
    invalidos = fields.Integer(string='Inválidos')
    incompletos = fields.Integer(string='Incompletos')
    indeterminados = fields.Integer(string='Indeterminados')
    todos_ok = fields.Boolean(string='Todos OK')
    gerado_em = fields.Datetime(string='Gerado em', default=fields.Datetime.now)
    linha_ids = fields.One2many(
        'sensor_monitor.verificacao.laudo.linha', 'laudo_id', string='Itens')

    @api.model
    def criar_de_lote(self, lote):
        """Cria um laudo (+ linhas) efêmero a partir do dict `lote` devolvido
        pelo api quando o job atinge estado 'pronto'. Devolve o record.
        """
        linhas = [
            (0, 0, {campo: item.get(campo) for campo in _CAMPOS_LINHA})
            for item in lote.get('itens', [])
        ]
        return self.create({
            'total': lote.get('total', 0),
            'validos': lote.get('validos', 0),
            'invalidos': lote.get('invalidos', 0),
            'incompletos': lote.get('incompletos', 0),
            'indeterminados': lote.get('indeterminados', 0),
            'todos_ok': bool(lote.get('todos_ok')),
            'linha_ids': linhas,
        })


class VerificacaoLaudoLinha(models.TransientModel):
    _name = 'sensor_monitor.verificacao.laudo.linha'
    _description = 'Linha (arquivo) do laudo de verificação'

    laudo_id = fields.Many2one(
        'sensor_monitor.verificacao.laudo', string='Laudo',
        required=True, ondelete='cascade')
    nome = fields.Char(string='Arquivo')
    estado = fields.Selection([
        ('valido', 'Válido'),
        ('invalido', 'Inválido'),
        ('incompleto', 'Incompleto'),
        ('indeterminado', 'Indeterminado'),
    ], string='Estado')
    motivo = fields.Char(string='Motivo')
    coletor_id = fields.Char(string='Coletor')
    data_referencia = fields.Char(string='Data de referência')
    total_linhas = fields.Integer(string='Total de linhas')
    fingerprint_conferido = fields.Char(string='Fingerprint conferido')
