"""Exportacao em PDF do relatorio de periodo (mesmo conteudo do JSON de /relatorio)."""
import io
import re
import unicodedata
import calendar
from datetime import date, datetime, timezone
from typing import Optional
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
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
_COR_CAB = colors.HexColor('#1b2a3a')
_COR_GRADE = colors.HexColor('#b8c0ca')
_COR_ZEBRA = colors.HexColor('#f3f5f8')
_COR_ROTULO = colors.HexColor('#e9edf2')
_TITULO_DOC = 'RELATÓRIO DE REGISTRO DE MONITORAMENTO'

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


def _estilo_tabela(n_linhas):
    cmds = [
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), _COR_CAB),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 0.8, _COR_CAB),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, _COR_GRADE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]
    cmds += [('BACKGROUND', (0, r), (-1, r), _COR_ZEBRA) for r in range(2, n_linhas, 2)]
    return cmds


def _tabela(s, gran, estilos):
    cab = ['Período', f"Média ({s['unidade']})", 'Mín', 'Máx', 'Leituras', 'Falhas']
    linhas = [cab]
    cmds = _estilo_tabela(len(s['buckets']) + 1) + [('ALIGN', (1, 0), (-1, -1), 'RIGHT')]
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
    linhas = [[Paragraph(f'<font color="white"><b>{t}</b></font>', estilos['cel']) for t in
               ('Detectado em', 'Tipo', 'Valor lido', 'Status', 'Saiu do alarme em', 'Resolvido em')]]
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
    return [Table(linhas, repeatRows=1, style=TableStyle(_estilo_tabela(len(linhas))), colWidths=[3 * cm, 3 * cm, 2 * cm, 2.4 * cm, 3.3 * cm, 3.3 * cm])]


def _estilos():
    base = getSampleStyleSheet()
    return {
        'titulo': ParagraphStyle('titulo', parent=base['Title'], fontName='Helvetica-Bold', fontSize=13,
                                 alignment=1, spaceAfter=2, textColor=_COR_CAB),
        'subtitulo': ParagraphStyle('subtitulo', parent=base['Normal'], fontSize=8.5, alignment=1,
                                    textColor=colors.HexColor('#4a5968'), spaceAfter=10),
        'secao': ParagraphStyle('secao', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=10.5,
                                textColor=colors.white, backColor=_COR_CAB, borderPadding=(4, 5, 4, 5),
                                spaceBefore=10, spaceAfter=8, keepWithNext=1),
        'h2': ParagraphStyle('h2', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=10,
                             textColor=_COR_CAB, backColor=_COR_ROTULO, borderColor=_COR_CAB,
                             borderWidth=0.6, borderPadding=(4, 5, 4, 5),
                             spaceBefore=4, spaceAfter=8, keepWithNext=1),
        'h3': ParagraphStyle('h3', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=9.5,
                             textColor=_COR_CAB, spaceBefore=10, spaceAfter=4, keepWithNext=1),
        'corpo': ParagraphStyle('corpo', parent=base['Normal'], fontSize=9, leading=12, alignment=4),
        'aviso': ParagraphStyle('aviso', parent=base['Normal'], fontSize=8.5, leading=11,
                                textColor=colors.HexColor('#7a4b00'), backColor=colors.HexColor('#fff3cd'),
                                borderColor=colors.HexColor('#e0b84f'), borderWidth=0.5,
                                borderPadding=3, spaceAfter=5),
        'cel': ParagraphStyle('cel', parent=base['Normal'], fontSize=8, leading=9.5),
        'rotulo': ParagraphStyle('rotulo', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=8,
                                 leading=10, textColor=_COR_CAB),
        'peq': ParagraphStyle('peq', parent=base['Normal'], fontSize=7.5, leading=9.5,
                              textColor=colors.HexColor('#4a5968'), spaceBefore=2),
        'assin': ParagraphStyle('assin', parent=base['Normal'], fontSize=8.5, leading=11, alignment=1),
    }


def _quadro(pares, estilos, larguras=None):
    """Quadro rotulo/valor em 2 pares por linha (estilo ficha de registro)."""
    cel = lambda t: Paragraph(t, estilos['cel'])
    linhas = []
    for i in range(0, len(pares), 2):
        linha = []
        for rot, val in pares[i:i + 2]:
            linha += [Paragraph(rot.upper(), estilos['rotulo']), cel(val)]
        while len(linha) < 4:
            linha += ['', '']
        linhas.append(linha)
    larguras = larguras or [3.3 * cm, 5.2 * cm, 3.3 * cm, 5.2 * cm]
    return Table(linhas, colWidths=larguras, style=TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.8, _COR_CAB),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, _COR_GRADE),
        ('BACKGROUND', (0, 0), (0, -1), _COR_ROTULO),
        ('BACKGROUND', (2, 0), (2, -1), _COR_ROTULO),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))


def numero_documento(relatorio: dict) -> str:
    emitido = datetime.fromisoformat(relatorio['emitido_em']).astimezone(ZoneInfo(relatorio['fuso']))
    return f'REL-{emitido:%Y%m%d-%H%M%S}'


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
    """Canvas com cabecalho institucional e rodape 'Página X de Y' em todas as paginas."""

    def __init__(self, *args, rodape='', numero='', logo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []
        self._rodape = rodape
        self._numero = numero
        self._logo = logo

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def _cabecalho(self):
        topo = A4[1] - 1.2 * cm
        if self._logo:
            leitor, larg, alt = self._logo
            esc = min(4.2 * cm / larg, 1.4 * cm / alt)
            self.drawImage(leitor, 2 * cm, topo - alt * esc, larg * esc, alt * esc, mask='auto')
        self.setFillColor(_COR_CAB)
        self.setFont('Helvetica-Bold', 9)
        self.drawRightString(A4[0] - 2 * cm, topo - 0.45 * cm, _TITULO_DOC)
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#4a5968'))
        self.drawRightString(A4[0] - 2 * cm, topo - 0.9 * cm, f'Documento nº {self._numero}')
        self.setStrokeColor(_COR_CAB)
        self.setLineWidth(1.2)
        self.line(2 * cm, topo - 1.65 * cm, A4[0] - 2 * cm, topo - 1.65 * cm)

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._cabecalho()
            self.setStrokeColor(_COR_GRADE)
            self.setLineWidth(0.5)
            self.line(2 * cm, 1.55 * cm, A4[0] - 2 * cm, 1.55 * cm)
            self.setFont('Helvetica', 7.5)
            self.setFillColor(colors.HexColor('#4a5968'))
            self.drawString(2 * cm, 1.1 * cm, self._rodape)
            self.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f'Página {self._pageNumber} de {total}')
            super().showPage()
        super().save()


def _logo_leitor(logo: Optional[bytes]):
    """(ImageReader, largura, altura) do logo PNG/JPEG; None se ausente ou ilegível."""
    if not logo:
        return None
    try:
        leitor = ImageReader(io.BytesIO(logo))
        larg, alt = leitor.getSize()
    except Exception:
        return None
    return leitor, larg, alt


def gerar_pdf(relatorio: dict, cliente_nome: str, compress: bool = True, logo: Optional[bytes] = None) -> bytes:
    tz = ZoneInfo(relatorio['fuso'])
    est = _estilos()
    gran = relatorio['granularidade']
    emitido = datetime.fromisoformat(relatorio['emitido_em']).astimezone(tz)
    numero = numero_documento(relatorio)
    periodo = f"{_data_iso(relatorio['inicio'])} – {_data_iso(relatorio['fim'])}"
    rodape = (f"Documento gerado eletronicamente pelo sistema Sentinela em {_data_hora(emitido)} · "
              f"{cliente_nome}")

    story = [
        Paragraph(_TITULO_DOC, est['titulo']),
        Paragraph('Registro de condições ambientais monitoradas por sensores', est['subtitulo']),
        Paragraph('1. IDENTIFICAÇÃO', est['secao']),
        _quadro([
            ('Cliente', escape(cliente_nome)),
            ('Documento', numero),
            ('Período', periodo),
            ('Granularidade', _GRAN[gran]),
            ('Fuso horário', escape(relatorio['fuso'])),
            ('Sensores', str(len(relatorio['sensores']))),
            ('Emitido em', _data_hora(emitido)),
            ('Emissor', escape(relatorio['emissor'])),
        ], est),
        Spacer(1, 0.25 * cm),
        Paragraph('Valores consolidados a partir das leituras válidas de cada sensor. Leituras com falha de '
                  'instrumento não entram na média, no mínimo nem no máximo e são contadas à parte. '
                  'Períodos sem nenhuma leitura são identificados como "Sem dados".', est['peq']),
    ]
    for idx, s in enumerate(relatorio['sensores'], start=1):
        if idx > 1:
            story.append(PageBreak())
        else:
            story.append(Paragraph('2. SENSORES MONITORADOS', est['secao']))
        story.append(Paragraph(
            f"2.{idx} {escape(s['nome'])} ({escape(s['sensor_code'])})", est['h2']))
        story.append(_quadro([
            ('Site', escape(s['site'] or '—')),
            ('Código', escape(s['sensor_code'])),
            ('Unidade', escape(s['unidade'] or '—')),
            ('Limites', escape(_limites_texto(s))),
        ], est))
        story.append(Spacer(1, 0.2 * cm))
        for a in s['alteracoes_limite']:
            story.append(Paragraph(escape(_aviso_limite(a, tz, relatorio['fim'])), est['aviso']))
        story.append(KeepTogether([
            Paragraph(f'2.{idx}.1 Registro gráfico', est['h3']),
            _grafico(s, gran),
            Paragraph('Linha: média. Faixa clara: mínimo–máximo. Tracejado: limites atuais. '
                      'Ponto vermelho: período com valor fora do limite.', est['peq']),
        ]))
        story.append(Paragraph(f'2.{idx}.2 Registros consolidados', est['h3']))
        story.append(_tabela(s, gran, est))
        story.append(Paragraph('Linhas destacadas: mínimo ou máximo fora do limite atual.', est['peq']))
        for nota in _notas_mes(relatorio):
            story.append(Paragraph(nota, est['peq']))
        story.append(Paragraph(f'2.{idx}.3 Ocorrências — alarmes no período', est['h3']))
        story.extend(_alarmes(s, tz, est))

    linha_assin = '_' * 38
    assinaturas = Table([
        [Paragraph(linha_assin, est['assin']), Paragraph(linha_assin, est['assin'])],
        [Paragraph('<b>Responsável técnico</b><br/>Nome / registro profissional', est['assin']),
         Paragraph('<b>Responsável pela unidade</b><br/>Nome / cargo', est['assin'])],
        [Paragraph('Data: ____/____/________', est['assin']), Paragraph('Data: ____/____/________', est['assin'])],
    ], colWidths=[_LARGURA / 2] * 2, style=TableStyle([('TOPPADDING', (0, 0), (-1, -1), 3)]))
    story.append(KeepTogether([
        Paragraph('3. TERMO DE RESPONSABILIDADE', est['secao']),
        Paragraph(f'Declaramos que os dados apresentados neste relatório correspondem aos registros '
                  f'armazenados pelo sistema de monitoramento Sentinela para o período de {periodo}, '
                  f'obtidos automaticamente pelos sensores identificados acima, sem edição manual dos valores.',
                  est['corpo']),
        Spacer(1, 1.6 * cm),
        assinaturas,
    ]))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=3.3 * cm, bottomMargin=2.2 * cm,
        title=f'Relatório {numero} ({periodo})',
        author=relatorio['emissor'], pageCompression=1 if compress else 0,
    )
    leitor = _logo_leitor(logo)
    doc.build(story, canvasmaker=lambda *a, **k: _CanvasNumerado(
        *a, rodape=rodape, numero=numero, logo=leitor, **k))
    return buf.getvalue()
