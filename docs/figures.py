"""Two ink risograph style figures for the README, cards and article. Usage: python figures.py FONTDIR OUTDIR LANG"""
import sys, os, math, random
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import fonts as rlfonts

FD = sys.argv[1]; OUTDIR = sys.argv[2]; LANG = sys.argv[3]
os.makedirs(OUTDIR, exist_ok=True)
FONTS = ["BigShoulders-Black", "BigShoulders-Bold", "SpaceMono-Regular", "SpaceMono-Bold",
         "InstrumentSans-Regular", "InstrumentSans-SemiBold", "InstrumentSans-Italic"]
for n in FONTS:
    pdfmetrics.registerFont(TTFont(n, os.path.join(FD, n + ".ttf")))
pdfmetrics.registerFontFamily("InstrumentSans", normal="InstrumentSans-Regular", bold="InstrumentSans-SemiBold",
                              italic="InstrumentSans-Italic", boldItalic="InstrumentSans-SemiBold")
for f, b, i in [("InstrumentSans-Regular", 0, 0), ("InstrumentSans-SemiBold", 1, 0), ("InstrumentSans-Italic", 0, 1), ("InstrumentSans-SemiBold", 1, 1)]:
    rlfonts._tt2ps_map[("instrumentsans", b, i)] = f
    rlfonts._ps2tt_map[f.lower()] = ("instrumentsans", b, i)
from reportlab import rl_config
rl_config.canvas_basefontname = "InstrumentSans-Regular"
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph

W, H = 1080, 1350
PAPER = HexColor("#F1F2EE"); BLUE = HexColor("#0078BF"); PINK = HexColor("#FF48B0")
M = 80
rnd = random.Random(26)


def st(size, font="InstrumentSans-Regular", color=BLUE, lead=1.34):
    return ParagraphStyle("p%s%s%s" % (size, font, color), fontName=font, fontSize=size, leading=size * lead,
                          textColor=color, bulletFontName=font)


def para(c, text, x, ytop, w, style):
    p = Paragraph(text, style); _, h = p.wrapOn(c, w, 3000); p.drawOn(c, x, ytop - h); return ytop - h


def ink(c, color, alpha=1.0):
    c.setBlendMode("Multiply"); c.setFillColor(color); c.setStrokeColor(color); c.setFillAlpha(alpha); c.setStrokeAlpha(alpha)


def text(c, s, x, y, font, size, color, anchor="l", alpha=1.0):
    ink(c, color, alpha); c.setFont(font, size)
    {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[anchor](x, y, s)


def misreg(c, s, x, y, font, size, anchor="l", dx=7, dy=-5):
    text(c, s, x + dx, y + dy, font, size, PINK, anchor)
    text(c, s, x, y, font, size, BLUE, anchor)


def halftone(c, x, y, w, h, color, step=14, rmin=1.2, rmax=6.0, angle=0, grad="none"):
    ink(c, color); c.saveState()
    p = c.beginPath(); p.rect(x, y, w, h); c.clipPath(p, stroke=0, fill=0)
    cx, cy = x + w / 2, y + h / 2; a = math.radians(angle)
    span = int(max(w, h) / step) + 4
    for i in range(-span, span):
        for j in range(-span, span):
            px = cx + (i * math.cos(a) - j * math.sin(a)) * step
            py = cy + (i * math.sin(a) + j * math.cos(a)) * step
            if not (x - step < px < x + w + step and y - step < py < y + h + step):
                continue
            t = {"none": 1.0, "up": (py - y) / h, "down": 1 - (py - y) / h, "right": (px - x) / w}[grad]
            r = rmin + (rmax - rmin) * max(0, min(1, t))
            c.circle(px, py, r, fill=1, stroke=0)
    c.restoreState()


def paper(c):
    c.setBlendMode("Normal"); c.setFillAlpha(1); c.setFillColor(PAPER); c.rect(0, 0, W, H, fill=1, stroke=0)
    ink(c, BLUE, 0.10)
    for _ in range(420):
        c.circle(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(0.4, 1.3), fill=1, stroke=0)
    ink(c, BLUE)
    c.setLineWidth(1.2)
    for (x, y, sx, sy) in [(34, 34, 1, 1), (W - 34, 34, -1, 1), (34, H - 34, 1, -1), (W - 34, H - 34, -1, -1)]:
        c.line(x, y, x + 26 * sx, y); c.line(x, y, x, y + 26 * sy)


def regmark(c, x, y):
    ink(c, BLUE); c.setLineWidth(1.4); c.circle(x, y, 11, fill=0, stroke=1); c.line(x - 18, y, x + 18, y); c.line(x, y - 18, x, y + 18)
    ink(c, PINK); c.circle(x + 2, y - 1.5, 11, fill=0, stroke=1)


def tape(c, x, y, w, h, rot, color, label, body):
    c.saveState(); c.translate(x, y); c.rotate(rot)
    ink(c, color, 0.92); c.rect(0, 0, w, h, fill=1, stroke=0)
    tc = PAPER if color == BLUE else BLUE
    c.setBlendMode("Normal"); c.setFillAlpha(1)
    c.setFillColor(tc); c.setFont("BigShoulders-Black", 64); c.drawString(28, h - 78, label)
    p = Paragraph(body, st(27, color=tc, lead=1.25)); _, hh = p.wrapOn(c, w - 56, 400); p.drawOn(c, 28, h - 100 - hh)
    c.restoreState()



import subprocess
PT = LANG == "pt"
T = lambda a, b: a if PT else b
num = lambda v: ("%.3f" % v).replace(".", ",") if PT else "%.3f" % v


def paper_wh(c, w, h):
    global W, H
    W, H = w, h
    paper(c)


def render(name, w, h, fn):
    pdf = os.path.join(OUTDIR, name + ".pdf")
    c = canvas.Canvas(pdf, pagesize=(w, h), initialFontName="InstrumentSans-Regular")
    for k in ("setAuthor", "setCreator", "setProducer"):
        getattr(c, k)("Juliano Dutra de Almeida")
    paper_wh(c, w, h); fn(c, w, h); c.showPage(); c.save()
    subprocess.run(["pdftoppm", "-r", "72", "-png", "-singlefile", pdf, os.path.join(OUTDIR, name)], check=True)
    os.remove(pdf)


def cover(c, w, h):
    halftone(c, 900, 0, 1020, 1080, PINK, step=18, rmin=0.6, rmax=8, angle=15, grad="right")
    ink(c, PINK); c.circle(w - 330, h - 300, 230, fill=1, stroke=0)
    lines = T(["O SLA ESTOURA", "ANTES DO JOB"], ["YOUR SLA BREAKS", "BEFORE THE JOB"])
    for i, s in enumerate(lines):
        misreg(c, s, 90, h - 300 - i * 230, "BigShoulders-Black", 250, dx=9, dy=-7)
    text(c, T("COMEÇAR.", "EVEN STARTS."), 94, h - 300 - 2 * 230 + 10, "BigShoulders-Black", 200, PINK)
    text(c, T("alerta precoce de SLA para pipelines batch  ·  modelo e dataset abertos",
              "early warning for batch pipeline SLAs  ·  open model and dataset"), 100, 80, "SpaceMono-Bold", 26, BLUE)
    regmark(c, w - 90, 80)


def budget(c, w, h):
    misreg(c, T("388 ALERTAS PARA CADA MÉTODO", "388 ALERTS FOR EACH METHOD"), 80, h - 150, "BigShoulders-Black", 110)
    text(c, T("ponto cheio = estouro antecipado  ·  ponto vazio = alarme falso  ·  27 dias de teste",
              "filled dot = breach caught early  ·  empty dot = false alarm  ·  27 test days"), 84, h - 200, "SpaceMono-Regular", 22, BLUE)
    colw = (w - 160 - 80) / 2
    for j, (lab, n, col, p) in enumerate([(T("MODELO", "MODEL"), 337, PINK, 87), (T("REGRA DO P95", "P95 RULE"), 161, BLUE, 41)]):
        x = 80 + j * (colw + 80)
        text(c, str(n), x - 4, h - 400, "BigShoulders-Black", 190, col)
        text(c, lab, x + 300, h - 300, "SpaceMono-Bold", 26, BLUE)
        text(c, "%d%% %s" % (p, T("de precisão", "precision")), x + 300, h - 340, "SpaceMono-Regular", 24, BLUE)
        r, gap, cols = 10.5, 4.0, 26
        for i in range(388):
            row, cc = divmod(i, cols)
            cx = x + cc * (2 * r + gap) + r; cy = h - 450 - row * (2 * r + gap) - r
            if i < n:
                ink(c, col); c.circle(cx, cy, r, fill=1, stroke=0)
            else:
                ink(c, BLUE); c.setLineWidth(1.5); c.circle(cx, cy, r - 1.6, fill=0, stroke=1)


def results(c, w, h):
    misreg(c, T("PR AUC NO TESTE", "TEST PR AUC"), 80, h - 150, "BigShoulders-Black", 120)
    text(c, T("barra = valor  ·  traço = intervalo de 95% por bootstrap de dias  ·  594 estouros",
              "bar = value  ·  whisker = 95% whole day bootstrap interval  ·  594 breaches"), 84, h - 200, "SpaceMono-Regular", 22, BLUE)
    data = [(T("REGRA DO P95", "P95 RULE"), .384, .355, .416), (T("REGRESSÃO LOGÍSTICA", "LOGISTIC REGRESSION"), .804, .768, .835),
            ("GRADIENT BOOSTING", .819, .781, .850)]
    x0, x1 = 80, w - 80; sc = lambda v: x0 + v * (x1 - x0)
    for i, (lab, v, lo, hi) in enumerate(data):
        yy = h - 300 - i * 200
        text(c, lab, x0, yy, "BigShoulders-Black", 46, BLUE)
        text(c, num(v), x1, yy, "BigShoulders-Black", 60, PINK if i == 2 else BLUE, "r")
        if i < 2:
            halftone(c, x0, yy - 130, sc(v) - x0, 95, BLUE, step=11, rmin=3.2 if i else 1.8, rmax=3.2 if i else 1.8)
        else:
            ink(c, PINK); c.rect(x0, yy - 130, sc(v) - x0, 95, fill=1, stroke=0)
            ink(c, BLUE); c.setLineWidth(1.4); c.rect(x0 + 8, yy - 138, sc(v) - x0, 95, fill=0, stroke=1)
        ink(c, BLUE); c.setLineWidth(4); c.line(sc(lo), yy - 82, sc(hi), yy - 82)
        for e in (lo, hi): c.line(sc(e), yy - 100, sc(e), yy - 64)


def causes(c, w, h):
    misreg(c, T("O QUE ELE NÃO ENXERGA", "WHAT IT CANNOT SEE"), 80, h - 150, "BigShoulders-Black", 120)
    text(c, T("recall por causa do estouro no limiar de 80% de precisão", "recall by breach root cause at the 80% precision threshold"), 84, h - 200, "SpaceMono-Regular", 22, BLUE)
    rows = [(T("atraso upstream", "upstream delay"), 89), (T("pico de volume", "volume spike"), 65), (T("contenção", "contention"), 41),
            (T("skew de dados", "data skew"), 15), (T("preempção spot", "spot preemption"), 15)]
    y = h - 290; bx = 80 + 420; bw = w - 80 - bx - 140
    for lab, v in rows:
        text(c, lab, 80, y - 36, "InstrumentSans-SemiBold", 36, BLUE)
        ink(c, BLUE); c.setLineWidth(2); c.rect(bx, y - 56, bw, 52, fill=0, stroke=1)
        ink(c, BLUE if v >= 40 else PINK); c.rect(bx, y - 56, bw * v / 100, 52, fill=1, stroke=0)
        text(c, "%d%%" % v, w - 80, y - 50, "BigShoulders-Black", 60, PINK if v < 40 else BLUE, "r")
        y -= 104


render("cover" if PT else "cover-en", 1920, 1080, cover)
render("fig-orcamento" if PT else "fig-budget", 1600, 900, budget)
render("fig-resultados" if PT else "fig-results", 1600, 900, results)
render("fig-causas" if PT else "fig-causes", 1600, 900, causes)
print(sorted(os.listdir(OUTDIR)))
