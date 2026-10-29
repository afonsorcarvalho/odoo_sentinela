"""Exportacao em PDF do relatorio de periodo (mesmo conteudo do JSON de /relatorio)."""
import io
import re
import unicodedata
import calendar
from datetime import date, datetime, timezone
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus.flowables import KeepTogether

_MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']
_GRAN = {'hora': 'Por hora', 'dia': 'Por dia', 'mes': 'Por mês'}
_TIPO = {
    'acima_limite': 'Acima do limite', 'abaixo_limite': 'Abaixo do limite',
    'sensor_offline': 'Sensor offline', 'erro_leitura': 'Erro de leitura',
    'falha_sensor': 'Falha do sensor',
}
_STATUS = {'aberto': 'Aberto', 'reconhecido': 'Reconhecido', 'resolvido': 'Resolvido'}

_COR_LINHA = colors.HexColor('#1f4e79')
_COR_FAIXA = colors.HexColor('#cfe0f1')
_COR_LIMITE = colors.HexColor('#b3261e')
_COR_FORA = colors.HexColor('#f8d7da')
_COR_CAB = colors.HexColor('#e6e9ee')
_COR_GRADE = colors.HexColor('#d0d4da')

_LARGURA = A4[0] - 4 * cm


def slug(texto: str) -> str:
    """ASCII, minusculo, hifens (para nome de arquivo)."""
    ascii_ = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', ascii_.lower()).strip('-') or 'cliente'


def _num(valor, casas=2):
    if valor is None:
        return '—'
    return f'{valor:.{casas}f}'.replace('.', ',')


def _data(d) -> str:
    return d.strftime('%d/%m/%Y')


def _data_hora(d) -> str:
    return d.strftime('%d/%m/%Y %H:%M')


def _data_iso(texto: str) -> str:
    return _data(datetime.fromisoformat(texto))


def _local(epoch_ms, tz):
    if epoch_ms is None:
        return None
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).astimezone(tz)


def rotulo_bucket(iso: str, gran: str) -> str:
    dt = datetime.fromisoformat(iso)
    if gran == 'hora':
        return f'{dt:%H}:00'
    if gran == 'dia':
        return _data(dt)
    return f'{_MESES[dt.month - 1]}/{dt.year}'


def _limites_texto(s) -> str:
    lim = s['limites']
    if lim is None or (lim['limite_min'] is None and lim['limite_max'] is None):
        return 'sem limite cadastrado'
    return f"mín {_num(lim['limite_min'])} / máx {_num(lim['limite_max'])} {s['unidade']}"


def _grafico(s, gran) -> Drawing:
    altura = 6.2 * cm
    d = Drawing(_LARGURA, altura)
    esq, dir_, base, topo = 1.6 * cm, 0.3 * cm, 1.1 * cm, altura - 0.3 * cm
    larg = _LARGURA - esq - dir_
    buckets = s['buckets']
    n = len(buckets)
    lim = s['limites'] or {}
    lmin, lmax = lim.get('limite_min'), lim.get('limite_max')

    vals = [v for b in buckets for v in (b['avg'], b['min'], b['max']) if v is not None]
    if not vals:
        d.add(Rect(esq, base, larg, topo - base, strokeColor=_COR_GRADE, fillColor=None))
        d.add(String(esq + larg / 2, (base + topo) / 2, 'Sem dados no período',
                     textAnchor='middle', fontSize=10, fontName='Helvetica', fillColor=colors.grey))
        return d
    pontos_y = vals + [v for v in (lmin, lmax) if v is not None]
    lo, hi = min(pontos_y), max(pontos_y)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    margem = (hi - lo) * 0.08
    lo, hi = lo - margem, hi + margem

    def px(i):
        return esq + (larg / 2 if n == 1 else larg * i / (n - 1))

    def py(v):
        return base + (v - lo) / (hi - lo) * (topo - base)

    # grade e eixo Y
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        d.add(Line(esq, py(v), esq + larg, py(v), strokeColor=_COR_GRADE, strokeWidth=0.4))
        d.add(String(esq - 0.15 * cm, py(v) - 3, _num(v), textAnchor='end', fontSize=7, fontName='Helvetica'))
    d.add(Line(esq, base, esq, topo, strokeColor=colors.black, strokeWidth=0.6))
    d.add(Line(esq, base, esq + larg, base, strokeColor=colors.black, strokeWidth=0.6))

    # eixo X
    indices = list(range(0, n, -(-n // 8)))
    for i in indices:
        d.add(Line(px(i), base, px(i), base - 0.12 * cm, strokeColor=colors.black, strokeWidth=0.5))
        d.add(String(px(i), base - 0.5 * cm, rotulo_bucket(buckets[i]['bucket'], gran),
                     textAnchor='middle', fontSize=7, fontName='Helvetica'))

    # segmentos contiguos (bucket sem avg quebra a linha)
    segmentos, atual = [], []
    for i, b in enumerate(buckets):
        if b['avg'] is None:
            if atual:
                segmentos.append(atual)
            atual = []
        else:
            atual.append(i)
    if atual:
        segmentos.append(atual)

    for seg in segmentos:
        if len(seg) > 1:
            topo_pts = [(px(i), py(buckets[i]['max'])) for i in seg]
            base_pts = [(px(i), py(buckets[i]['min'])) for i in reversed(seg)]
            flat = [c for p in topo_pts + base_pts for c in p]
            d.add(Polygon(flat, fillColor=_COR_FAIXA, strokeColor=None))
        else:
            i = seg[0]
            d.add(Line(px(i), py(buckets[i]['min']), px(i), py(buckets[i]['max']),
                       strokeColor=_COR_FAIXA, strokeWidth=3))
    for v, rotulo in ((lmax, 'limite máx'), (lmin, 'limite mín')):
        if v is not None:
            d.add(Line(esq, py(v), esq + larg, py(v), strokeColor=_COR_LIMITE,
                       strokeWidth=0.9, strokeDashArray=[4, 3]))
            d.add(String(esq + larg, py(v) + 2, rotulo, textAnchor='end', fontSize=6.5, fontName='Helvetica',
                         fillColor=_COR_LIMITE))
    for seg in segmentos:
        if len(seg) > 1:
            d.add(PolyLine([c for i in seg for c in (px(i), py(buckets[i]['avg']))],
                           strokeColor=_COR_LINHA, strokeWidth=1.2))
    for i, b in enumerate(buckets):
        if b['avg'] is None:
            continue
        isolado = (i == 0 or buckets[i - 1]['avg'] is None) and (i == n - 1 or buckets[i + 1]['avg'] is None)
        if b['fora_limite']:
            d.add(Circle(px(i), py(b['avg']), 2.4, fillColor=_COR_LIMITE, strokeColor=None))
        elif isolado or n <= 31:
            d.add(Circle(px(i), py(b['avg']), 1.5, fillColor=_COR_LINHA, strokeColor=None))
    return d


def _tabela(s, gran, estilos):
    cab = ['Período', f"Média ({s['unidade']})", 'Mín', 'Máx', 'Leituras', 'Falhas']
    linhas = [cab]
    cmds = [
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), _COR_CAB),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.3, _COR_GRADE),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]
    for r, b in enumerate(s['buckets'], start=1):
        rot = rotulo_bucket(b['bucket'], gran)
        if b['estado'] == 'sem_dados':
            linhas.append([rot, 'Sem dados', '', '', '0', '0'])
            cmds += [('SPAN', (1, r), (3, r)), ('ALIGN', (1, r), (3, r), 'CENTER'),
                     ('TEXTCOLOR', (1, r), (3, r), colors.grey)]
        elif b['estado'] == 'falha_instrumento':
            linhas.append([rot, 'Falha de instrumento', '', '', '0', str(b['n_falha'])])
            cmds += [('SPAN', (1, r), (3, r)), ('ALIGN', (1, r), (3, r), 'CENTER'),
                     ('TEXTCOLOR', (1, r), (3, r), _COR_LIMITE)]
        else:
            linhas.append([rot, _num(b['avg']), _num(b['min']), _num(b['max']),
                           str(b['n_ok']), str(b['n_falha'])])
            if b['fora_limite']:
                cmds += [('BACKGROUND', (0, r), (-1, r), _COR_FORA),
                         ('FONTNAME', (0, r), (-1, r), 'Helvetica-Bold')]
    return Table(linhas, repeatRows=1, style=TableStyle(cmds),
                 colWidths=[3.4 * cm, 3.4 * cm, 2.6 * cm, 2.6 * cm, 2.5 * cm, 2.5 * cm])


def _alarmes(s, tz, estilos):
    if not s['alarmes']:
        return [Paragraph('Nenhum alarme no período.', estilos['corpo'])]
    linhas = [['Detectado em', 'Tipo', 'Valor lido', 'Status', 'Saiu do alarme em', 'Resolvido em']]
    for a in s['alarmes']:
        sensor = _local(a['timestamp_resolucao_sensor'], tz)
        resol = _local(a['data_resolucao'], tz)
        deteccao = _local(a['timestamp_deteccao'], tz)
        linhas.append([
            _data_hora(deteccao) if deteccao else '—',
            Paragraph(_TIPO.get(a['tipo_violacao'], a['tipo_violacao']), estilos['cel']),
            _num(a['valor_lido']),
            _STATUS.get(a['status'], a['status']),
            _data_hora(sensor) if sensor else '—',
            _data_hora(resol) if resol else '—',
        ])
    return [Table(linhas, repeatRows=1, style=TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), _COR_CAB),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.3, _COR_GRADE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]), colWidths=[3 * cm, 3 * cm, 2 * cm, 2.4 * cm, 3.3 * cm, 3.3 * cm])]


def _estilos():
    base = getSampleStyleSheet()
    return {
        'titulo': ParagraphStyle('titulo', parent=base['Title'], fontSize=17, alignment=0, spaceAfter=6),
        'h2': ParagraphStyle('h2', parent=base['Heading2'], fontSize=13, spaceAfter=2),
        'h3': ParagraphStyle('h3', parent=base['Heading3'], fontSize=10, spaceBefore=8, spaceAfter=3,
                             keepWithNext=1),
        'corpo': ParagraphStyle('corpo', parent=base['Normal'], fontSize=9, leading=12),
        'aviso': ParagraphStyle('aviso', parent=base['Normal'], fontSize=8.5, leading=11,
                                textColor=colors.HexColor('#7a4b00'), backColor=colors.HexColor('#fff3cd'),
                                borderPadding=3, spaceAfter=4),
        'cel': ParagraphStyle('cel', parent=base['Normal'], fontSize=8, leading=9),
        'peq': ParagraphStyle('peq', parent=base['Normal'], fontSize=7.5, textColor=colors.grey),
    }


def _aviso_limite(a, tz, fim: str) -> str:
    dt = datetime.fromisoformat(a['quando']).astimezone(tz)
    campo = 'limite máximo' if a['campo'] == 'limite_max' else 'limite mínimo'
    texto = f"Limite alterado em {_data_hora(dt)} (de {_num(a['de'])} para {_num(a['para'])}) — {campo}"
    if dt.date().isoformat() > fim:
        texto += ' — após o período'
    return texto


def _notas_mes(relatorio: dict) -> list:
    """Avisos de mes parcial (primeiro/ultimo) quando a granularidade e mensal."""
    if relatorio['granularidade'] != 'mes':
        return []
    ini = date.fromisoformat(relatorio['inicio'])
    fim = date.fromisoformat(relatorio['fim'])
    fim_ini = date(ini.year, ini.month, calendar.monthrange(ini.year, ini.month)[1])
    ini_fim = date(fim.year, fim.month, 1)
    parcial_ini = ini.day != 1
    parcial_fim = fim.day != calendar.monthrange(fim.year, fim.month)[1]
    if (ini.year, ini.month) == (fim.year, fim.month):
        return [f'Mês parcial: dados de {_data(ini)} a {_data(fim)}.'] if parcial_ini or parcial_fim else []
    notas = []
    if parcial_ini:
        notas.append(f'Primeiro mês parcial: dados de {_data(ini)} a {_data(fim_ini)}.')
    if parcial_fim:
        notas.append(f'Último mês parcial: dados de {_data(ini_fim)} a {_data(fim)}.')
    return notas


class _CanvasNumerado(rl_canvas.Canvas):
    """Canvas que conhece o total de paginas, para o rodape 'Página X de Y'."""

    def __init__(self, *args, rodape='', **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []
        self._rodape = rodape

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self.setFont('Helvetica', 8)
            self.setFillColor(colors.grey)
            self.drawString(2 * cm, 1.1 * cm, self._rodape)
            self.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f'Página {self._pageNumber} de {total}')
            super().showPage()
        super().save()


def gerar_pdf(relatorio: dict, cliente_nome: str, compress: bool = True) -> bytes:
    tz = ZoneInfo(relatorio['fuso'])
    est = _estilos()
    gran = relatorio['granularidade']
    emitido = datetime.fromisoformat(relatorio['emitido_em']).astimezone(tz)
    rodape = f"{cliente_nome} — Relatório de período {_data_iso(relatorio['inicio'])} a {_data_iso(relatorio['fim'])}"

    story = [
        Paragraph('Relatório de monitoramento', est['titulo']),
        Paragraph(f"<b>Cliente:</b> {escape(cliente_nome)}", est['corpo']),
        Paragraph(f"<b>Período:</b> {_data_iso(relatorio['inicio'])} – {_data_iso(relatorio['fim'])}", est['corpo']),
        Paragraph(f"<b>Granularidade:</b> {_GRAN[gran]} &nbsp;&nbsp; <b>Fuso horário:</b> {escape(relatorio['fuso'])}",
                  est['corpo']),
        Paragraph(f"<b>Emitido em:</b> {_data_hora(emitido)} &nbsp;&nbsp; <b>Emissor:</b> {escape(relatorio['emissor'])}",
                  est['corpo']),
        Paragraph(f"<b>Sensores:</b> {len(relatorio['sensores'])}", est['corpo']),
        Spacer(1, 0.4 * cm),
    ]
    for idx, s in enumerate(relatorio['sensores']):
        if idx:
            story.append(PageBreak())
        story.append(Paragraph(f"{escape(s['nome'])} ({escape(s['sensor_code'])})", est['h2']))
        story.append(Paragraph(
            f"<b>Site:</b> {escape(s['site'] or '—')} &nbsp;&nbsp; <b>Unidade:</b> {escape(s['unidade'] or '—')}"
            f" &nbsp;&nbsp; <b>Limites:</b> {escape(_limites_texto(s))}", est['corpo']))
        story.append(Spacer(1, 0.2 * cm))
        for a in s['alteracoes_limite']:
            story.append(Paragraph(escape(_aviso_limite(a, tz, relatorio['fim'])), est['aviso']))
        story.append(KeepTogether([
            Paragraph('Evolução no período', est['h3']),
            _grafico(s, gran),
            Paragraph('Linha: média. Faixa clara: mínimo–máximo. Tracejado: limites atuais. '
                      'Ponto vermelho: período com valor fora do limite.', est['peq']),
        ]))
        story.append(Paragraph('Dados por período', est['h3']))
        story.append(_tabela(s, gran, est))
        story.append(Paragraph('Linhas destacadas: mínimo ou máximo fora do limite atual.', est['peq']))
        for nota in _notas_mes(relatorio):
            story.append(Paragraph(nota, est['peq']))
        story.append(Paragraph('Alarmes no período', est['h3']))
        story.extend(_alarmes(s, tz, est))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=2 * cm,
        title=f'Relatório {_data_iso(relatorio["inicio"])} a {_data_iso(relatorio["fim"])}',
        author=relatorio['emissor'], pageCompression=1 if compress else 0,
    )
    doc.build(story, canvasmaker=lambda *a, **k: _CanvasNumerado(*a, rodape=rodape, **k))
    return buf.getvalue()
