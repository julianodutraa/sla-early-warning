"""Editorial figures for the article, README and model cards. Usage: python figures.py FONTDIR OUTDIR LANG"""
import sys, os, subprocess
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

FD, OUT, LANG = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
for n in ["Fraunces-Black", "Fraunces-SemiBold", "Fraunces-Italic", "IBMPlexSans-Regular", "IBMPlexSans-Medium",
          "IBMPlexMono-Regular", "IBMPlexMono-Medium"]:
    pdfmetrics.registerFont(TTFont(n, os.path.join(FD, n + ".ttf")))

PAPER = HexColor("#F2EEE6"); INK = HexColor("#151515"); SIG = HexColor("#D9481F")
G1 = HexColor("#4A4640"); G2 = HexColor("#8C877D"); RULE = HexColor("#CFC8BB"); DARK = HexColor("#16140F")
MUTE = HexColor("#8F887A"); TRACK = HexColor("#E6DFD2")
PT = LANG == "pt"
T = lambda pt, en: pt if PT else en
num = lambda v, d=3: (("%." + str(d) + "f") % v).replace(".", ",") if PT else ("%." + str(d) + "f") % v


def render(name, w, h, draw):
    pdf = os.path.join(OUT, name + ".pdf")
    c = canvas.Canvas(pdf, pagesize=(w, h), initialFontName="IBMPlexSans-Regular")
    c.setAuthor("Juliano Dutra de Almeida"); c.setCreator("Juliano Dutra de Almeida"); c.setProducer("Juliano Dutra de Almeida")
    draw(c, w, h); c.showPage(); c.save()
    subprocess.run(["pdftoppm", "-r", "72", "-png", "-singlefile", pdf, os.path.join(OUT, name)], check=True)
    os.remove(pdf)


def txt(c, s, x, y, font, size, color, anchor="l"):
    c.setFont(font, size); c.setFillColor(color)
    {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[anchor](x, y, s)


def cover(c, W, H):
    c.setFillColor(DARK); c.rect(0, 0, W, H, fill=1, stroke=0)
    M = 120
    txt(c, T("ENGENHARIA DE DADOS  ·  DEVOPS  ·  OBSERVABILIDADE", "DATA ENGINEERING  ·  DEVOPS  ·  OBSERVABILITY"), M, H - 130, "IBMPlexMono-Regular", 24, MUTE)
    txt(c, T("O SLA estoura antes", "Your SLA breaks before"), M, H - 300, "Fraunces-Black", 130, PAPER)
    txt(c, T("de o job começar.", "the job even starts."), M, H - 440, "Fraunces-Black", 130, PAPER)
    txt(c, T("Um modelo pequeno que avisa na liberação, com a folga inteira pela frente.",
             "A small model that warns at release time, with the whole slack still ahead."), M, H - 530, "Fraunces-Italic", 44, SIG)
    ty = 250; x0, xd, xe = M + 30, W - M - 520, W - M - 40
    c.setStrokeColor(HexColor("#6E685C")); c.setLineWidth(4); c.line(M, ty, W - M, ty)
    c.setFillColor(SIG); c.rect(x0, ty - 5, xd - x0, 10, fill=1, stroke=0)
    for x, lab, col in [(x0, T("liberação", "release"), SIG), (xd, T("prazo", "deadline"), PAPER), (xe, "dashboard", MUTE)]:
        c.setFillColor(col); c.circle(x, ty, 17, fill=1, stroke=0)
        txt(c, lab, x, ty + 44, "IBMPlexMono-Medium", 27, col, "c")
    txt(c, T("o modelo avisa aqui", "the model warns here"), x0 - 17, ty - 64, "IBMPlexMono-Regular", 24, SIG)
    txt(c, T("hoje o time descobre aqui", "today the team finds out here"), xe + 17, ty - 64, "IBMPlexMono-Regular", 24, MUTE, "r")
    txt(c, "Juliano Dutra de Almeida", M, 90, "IBMPlexMono-Medium", 26, PAPER)


def budget(c, W, H):
    c.setFillColor(PAPER); c.rect(0, 0, W, H, fill=1, stroke=0)
    M = 90
    txt(c, T("Mesmo orçamento, 388 alertas para cada método", "Same budget, 388 alerts for each method"), M, H - 110, "Fraunces-SemiBold", 50, INK)
    txt(c, T("cada ponto é um alerta  ·  cheio = estouro real antecipado  ·  27 dias de teste",
             "each dot is one alert  ·  filled = real breach caught early  ·  27 test days"), M, H - 160, "IBMPlexMono-Regular", 22, G2)
    colw = (W - 2 * M - 80) / 2
    for j, (lab, n, col, p) in enumerate([(T("modelo", "model"), 337, SIG, 87), (T("regra do p95", "p95 rule"), 161, G1, 41)]):
        x = M + j * (colw + 80)
        txt(c, str(n), x, H - 330, "Fraunces-Black", 140, col)
        txt(c, lab, x + 290, H - 285, "IBMPlexMono-Medium", 26, INK)
        txt(c, "%d%% %s" % (p, T("de precisão", "precision")), x + 290, H - 322, "IBMPlexMono-Regular", 24, G1)
        r, gap, cols = 11, 4.2, 26
        for i in range(388):
            row, cc = divmod(i, cols)
            cx = x + cc * (2 * r + gap) + r; cy = H - 380 - row * (2 * r + gap) - r
            if i < n:
                c.setFillColor(col); c.circle(cx, cy, r, fill=1, stroke=0)
            else:
                c.setStrokeColor(RULE); c.setLineWidth(1.8); c.circle(cx, cy, r - 1, fill=0, stroke=1)


def results(c, W, H):
    c.setFillColor(PAPER); c.rect(0, 0, W, H, fill=1, stroke=0)
    M = 90
    txt(c, T("PR AUC no teste, com intervalo de 95%", "Test PR AUC with 95% interval"), M, H - 110, "Fraunces-SemiBold", 50, INK)
    txt(c, T("bootstrap por dia inteiro  ·  2.920 execuções  ·  594 estouros", "whole day bootstrap  ·  2,920 runs  ·  594 breaches"), M, H - 160, "IBMPlexMono-Regular", 22, G2)
    data = [(T("Regra do p95", "p95 rule"), .384, .355, .416, G2), (T("Regressão logística", "Logistic regression"), .804, .768, .835, G1),
            ("Gradient boosting", .819, .781, .850, SIG)]
    x0, x1 = M + 380, W - M; sc = lambda v: x0 + v * (x1 - x0)
    top = H - 260; step = (top - 150) / 3
    for g in [0, .25, .5, .75, 1]:
        c.setStrokeColor(RULE); c.setLineWidth(1.2); c.line(sc(g), top + 10, sc(g), 130)
        txt(c, num(g, 2), sc(g), 95, "IBMPlexMono-Regular", 20, G2, "c")
    for i, (lab, v, lo, hi, col) in enumerate(data):
        yc = top - i * step - step / 2
        txt(c, lab, M, yc - 10, "IBMPlexSans-Medium", 30, INK)
        c.setFillColor(col); c.roundRect(x0, yc - 32, sc(v) - x0, 64, 4, fill=1, stroke=0); c.rect(x0, yc - 32, 8, 64, fill=1, stroke=0)
        c.setStrokeColor(INK); c.setLineWidth(3); c.line(sc(lo), yc, sc(hi), yc)
        for e in (lo, hi): c.line(sc(e), yc - 14, sc(e), yc + 14)
        if hi < .9:
            txt(c, num(v), sc(hi) + 18, yc - 10, "IBMPlexMono-Medium", 28, INK)
        else:
            txt(c, num(v), sc(lo) - 18, yc - 10, "IBMPlexMono-Medium", 28, PAPER, "r")


def causes(c, W, H):
    c.setFillColor(PAPER); c.rect(0, 0, W, H, fill=1, stroke=0)
    M = 90
    txt(c, T("Recall por causa do estouro", "Recall by breach root cause"), M, H - 110, "Fraunces-SemiBold", 50, INK)
    txt(c, T("no limiar de 80% de precisão escolhido na validação", "at the 80% precision threshold chosen on validation"), M, H - 160, "IBMPlexMono-Regular", 22, G2)
    rows = [(T("atraso upstream", "upstream delay"), 89, 142), (T("pico de volume", "volume spike"), 65, 198), (T("contenção do cluster", "cluster contention"), 41, 169),
            (T("skew de dados", "data skew"), 15, 59), (T("preempção spot", "spot preemption"), 15, 26)]
    bx = M + 430; bw = W - M - 140 - bx; y = H - 260
    for lab, v, n in rows:
        col = INK if v >= 40 else SIG
        txt(c, lab, M, y - 12, "IBMPlexSans-Medium", 30, INK)
        txt(c, "n=%d" % n, bx - 30, y - 12, "IBMPlexMono-Regular", 20, G2, "r")
        c.setFillColor(TRACK); c.rect(bx, y - 22, bw, 40, fill=1, stroke=0)
        c.setFillColor(col); c.rect(bx, y - 22, bw * v / 100, 40, fill=1, stroke=0)
        txt(c, "%d%%" % v, W - M, y - 12, "IBMPlexMono-Medium", 30, INK, "r")
        y -= 118
    txt(c, T("vermelho: causas que não dão sinal antes de o job começar", "red: causes with no signal before the job starts"), M, 70, "IBMPlexMono-Regular", 22, SIG)


render("cover" if PT else "cover-en", 1920, 1080, cover)
render("fig-orcamento" if PT else "fig-budget", 1600, 870, budget)
render("fig-resultados" if PT else "fig-results", 1600, 900, results)
render("fig-causas" if PT else "fig-causes", 1600, 900, causes)
print(sorted(os.listdir(OUT)))
