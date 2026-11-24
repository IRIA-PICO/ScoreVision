"""
Generador de partituras sintéticas para ScoreVision.
Crea imágenes PNG + ground truth (CSV) con distintos tipos de notas.

Formato de las melodías (tokens separados por espacios):
  SOL4:n   -> nota SOL4 negra        (r=redonda, b=blanca, n=negra, c=corchea, s=semicorchea)
  SOL4:c.  -> corchea con puntillo
  FA#4:n   -> con sostenido
  S:n      -> silencio de negra       (S:r, S:b, S:n, S:c)
  [ ... ]  -> notas unidas por barra (corcheas / semicorcheas)
  |        -> barra de compás          ||  -> doble barra final
"""
import csv
import json
import math
import random
import re
from pathlib import Path

import cv2 as cv
import numpy as np

NOMBRES = ["DO", "RE", "MI", "FA", "SOL", "LA", "SI"]
DUR = {"r": 4, "b": 2, "n": 1, "c": 0.5, "s": 0.25}
TIPO = {"r": "redonda", "b": "blanca", "n": "negra", "c": "corchea", "s": "semicorchea"}
AVANCE = {"r": 5.0, "b": 3.8, "n": 3.0, "c": 2.5, "s": 2.1}
BARRAS = {"c": 1, "s": 2}

RE_NOTA = re.compile(r"^(DO|RE|MI|FA|SOL|LA|SI)(#|b)?(-?\d):([rbncs])(\.?)$")
RE_SILENCIO = re.compile(r"^S:([rbncs])$")

TINTA = 0


#utilidades
def pos_a_altura(p):
    g = 30 + p                       # MI4 (línea inferior) = 4*7+2
    return f"{NOMBRES[g % 7]}{g // 7}"


def altura_a_pos(nombre, octava):
    return int(octava) * 7 + NOMBRES.index(nombre) - 30


def bezier(p0, p1, p2, p3, n=20):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = map(np.array, (p0, p1, p2, p3))
    pts = (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3
    return pts.round().astype(np.int32)


#parsing
def parsear(texto):
    eventos, grupo, gid = [], None, 0
    for tok in texto.split():
        if tok == "[":
            gid += 1
            grupo = gid
        elif tok == "]":
            grupo = None
        elif tok in ("|", "||"):
            eventos.append({"clase": "barra", "doble": tok == "||"})
        elif m := RE_SILENCIO.match(tok):
            eventos.append({"clase": "silencio", "fig": m.group(1)})
        elif "+" in tok:
            alturas, fig = tok.rsplit(":", 1)
            notas = []
            for a in alturas.split("+"):
                m = re.fullmatch(r"(DO|RE|MI|FA|SOL|LA|SI)(#|b)?(-?\d)", a)
                nombre, alt, octv = m.groups()
                notas.append({"nombre": nombre, "alteracion": alt or "", "octava": int(octv),
                              "p": altura_a_pos(nombre, octv)})
            eventos.append({"clase": "acorde", "notas": notas, "fig": fig.rstrip("."),
                            "puntillo": fig.endswith("."), "grupo": None})
        elif m := RE_NOTA.match(tok):
            nombre, alt, octv, fig, punto = m.groups()
            eventos.append({
                "clase": "nota", "nombre": nombre, "alteracion": alt or "",
                "octava": int(octv), "p": altura_a_pos(nombre, octv),
                "fig": fig, "puntillo": punto == ".", "grupo": grupo,
            })
        else:
            raise ValueError(f"Token no válido: {tok}")
    return eventos


#dibujo
class Pentagrama:
    def __init__(self, y_top, d, grosor):
        self.d, self.g = d, grosor
        self.lineas = [int(round(y_top + i * d)) for i in range(5)]

    def y(self, p):
        return int(round(self.lineas[4] - p * self.d / 2))


def dibujar_clave(img, x, pg, t):
    d = pg.d
    yG = pg.lineas[3]
    top, bot = pg.lineas[0], pg.lineas[4]
    #espiral alrededor de la línea de SOL
    pts = []
    for th in np.linspace(0, 2.3 * np.pi, 70):
        r = 0.2 * d + th / (2.3 * np.pi) * 1.25 * d
        pts.append((x + r * math.cos(th + math.pi), yG + r * math.sin(th + math.pi) * 1.05))
    pts = np.array(pts).round().astype(np.int32)
    cv.polylines(img, [pts], False, TINTA, t, cv.LINE_AA)
    #trazo hacia arriba, bucle y bajada
    sube = bezier(tuple(pts[-1]), (x + 1.6 * d, yG - 1.5 * d), (x + 1.1 * d, top - 1.2 * d), (x + 0.3 * d, top - 2.0 * d))
    cv.polylines(img, [sube], False, TINTA, t, cv.LINE_AA)
    bucle = bezier((x + 0.3 * d, top - 2.0 * d), (x - 0.5 * d, top - 1.0 * d), (x - 0.1 * d, top + 0.2 * d), (x + 0.2 * d, top + 0.8 * d))
    cv.polylines(img, [bucle], False, TINTA, t, cv.LINE_AA)
    cv.line(img, (int(x + 0.2 * d), int(top + 0.8 * d)), (int(x + 0.45 * d), int(bot + 1.4 * d)), TINTA, t, cv.LINE_AA)
    gancho = bezier((x + 0.45 * d, bot + 1.4 * d), (x + 0.5 * d, bot + 2.1 * d), (x - 0.4 * d, bot + 2.2 * d), (x - 0.5 * d, bot + 1.5 * d))
    cv.polylines(img, [gancho], False, TINTA, t, cv.LINE_AA)
    cv.circle(img, (int(x - 0.3 * d), int(bot + 1.5 * d)), max(2, int(0.3 * d)), TINTA, -1, cv.LINE_AA)


def dibujar_compas(img, x, pg, num, den):
    d = pg.d
    font = cv.FONT_HERSHEY_DUPLEX
    escala = d * 1.7 / 22
    grosor = max(2, int(d * 0.16))
    for txt, yc in ((str(num), pg.lineas[1]), (str(den), pg.lineas[3])):
        (tw, th), _ = cv.getTextSize(txt, font, escala, grosor)
        cv.putText(img, txt, (int(x - tw / 2), int(yc + th / 2)), font, escala, TINTA, grosor, cv.LINE_AA)


def dibujar_cabeza(img, cx, cy, d, hueca):
    ejes = (int(round(0.66 * d)), int(round(0.46 * d)))
    if hueca:
        cv.ellipse(img, (cx, cy), ejes, -20, 0, 360, TINTA, max(2, int(round(d * 0.14))), cv.LINE_AA)
    else:
        cv.ellipse(img, (cx, cy), ejes, -20, 0, 360, TINTA, -1, cv.LINE_AA)


def dibujar_adicionales(img, cx, p, pg):
    d = pg.d
    rango = []
    if p <= -2:
        rango = range(-2, p - 1, -2)
    elif p >= 10:
        rango = range(10, p + 1, 2)
    for q in rango:
        y = pg.y(q)
        cv.line(img, (int(cx - 1.05 * d), y), (int(cx + 1.05 * d), y), TINTA, pg.g)


def dibujar_corchetes(img, sx, ty, d, arriba, n, t):
    s = 1 if arriba else -1
    for k in range(n):
        y0 = ty + s * k * 0.8 * d
        pts = bezier((sx, y0), (sx + 0.55 * d, y0 + s * 0.45 * d), (sx + 1.1 * d, y0 + s * 1.0 * d), (sx + 0.8 * d, y0 + s * 2.1 * d))
        cv.polylines(img, [pts], False, TINTA, t, cv.LINE_AA)


def dibujar_barra(img, x1, y1, x2, y2, grosor, s):
    pts = np.array([(x1, y1), (x2, y2), (x2, y2 + s * grosor), (x1, y1 + s * grosor)], np.float32).round().astype(np.int32)
    cv.fillPoly(img, [pts], TINTA, cv.LINE_AA)


def dibujar_sostenido(img, x, y, d):
    t = max(1, int(d * 0.09))
    for dx in (-0.22, 0.22):
        cv.line(img, (int(x + dx * d), int(y - 1.2 * d)), (int(x + dx * d), int(y + 1.2 * d)), TINTA, t, cv.LINE_AA)
    for dy in (-0.4, 0.4):
        dibujar_barra(img, x - 0.5 * d, y + dy * d + 0.12 * d, x + 0.5 * d, y + dy * d - 0.12 * d, 0.24 * d, 1)


def dibujar_puntillo(img, x, y, d):
    cv.circle(img, (int(x), int(y)), max(2, int(0.17 * d)), TINTA, -1, cv.LINE_AA)


def dibujar_silencio(img, x, fig, pg):
    d = pg.d
    ym = pg.lineas[2]
    t = max(2, int(0.22 * d))
    if fig == "r":
        cv.rectangle(img, (int(x - 0.6 * d), pg.lineas[1]), (int(x + 0.6 * d), int(pg.lineas[1] + 0.5 * d)), TINTA, -1)
    elif fig == "b":
        cv.rectangle(img, (int(x - 0.6 * d), int(ym - 0.5 * d)), (int(x + 0.6 * d), ym), TINTA, -1)
    elif fig == "n":
        pts = np.array([(x - 0.2 * d, ym - 1.5 * d), (x + 0.45 * d, ym - 0.6 * d), (x - 0.25 * d, ym + 0.1 * d),
                        (x + 0.45 * d, ym + 0.9 * d)]).round().astype(np.int32)
        cv.polylines(img, [pts], False, TINTA, t + 1, cv.LINE_AA)
        cola = bezier((x + 0.45 * d, ym + 0.9 * d), (x - 0.4 * d, ym + 0.4 * d), (x - 0.6 * d, ym + 1.1 * d), (x + 0.1 * d, ym + 1.6 * d))
        cv.polylines(img, [cola], False, TINTA, t, cv.LINE_AA)
    elif fig in ("c", "s"):
        for k in range(BARRAS[fig]):
            yy = ym - 0.6 * d + k * 0.9 * d
            cv.circle(img, (int(x - 0.35 * d), int(yy)), max(2, int(0.25 * d)), TINTA, -1, cv.LINE_AA)
            cur = bezier((x - 0.35 * d, yy + 0.2 * d), (x - 0.1 * d, yy + 0.35 * d), (x + 0.3 * d, yy + 0.2 * d), (x + 0.45 * d, yy - 0.15 * d))
            cv.polylines(img, [cur], False, TINTA, max(1, t // 2), cv.LINE_AA)
        cv.line(img, (int(x + 0.45 * d), int(ym - 0.75 * d)), (int(x - 0.15 * d), int(ym + 1.4 * d)), TINTA, max(2, t // 2 + 1), cv.LINE_AA)


#render
def renderizar(pieza, carpeta):
    d = pieza.get("d", 20)
    grosor = pieza.get("grosor_linea", 2)
    t_plica = max(2, int(round(d * 0.1)))
    t_corchete = max(2, int(round(d * 0.2)))
    t_barra = 0.5 * d
    inclinadas = pieza.get("barras_inclinadas", False)
    sistemas = [parsear(s) for s in pieza["pentagramas"]]

    margen_sup = 6 * d
    sep = pieza.get("separacion", 10) * d
    alto = int(margen_sup + len(sistemas) * 4 * d + (len(sistemas) - 1) * sep + 6 * d)

    #layout horizontal
    x_ini_notas = []
    for i, eventos in enumerate(sistemas):
        cur = 1.5 * d + 3.5 * d + (2.5 * d if i == 0 and pieza.get("compas") else 0) + 1.5 * d
        x_ini_notas.append(cur)
        ultimo_dcha = cur
        for ev in eventos:
            if ev["clase"] == "barra":
                bx = max(cur - 1.0 * d, ultimo_dcha + 0.7 * d)
                ev["x"] = bx
                cur = bx + 1.8 * d
                continue
            if (ev["clase"] == "nota" and ev["alteracion"]) or (
                    ev["clase"] == "acorde" and any(n["alteracion"] for n in ev["notas"])):
                cur += 1.4 * d
            ev["x"] = cur
            fig = ev["fig"]
            dcha = cur + 0.7 * d
            if ev["clase"] in ("nota", "acorde") and fig in BARRAS and ev["grupo"] is None:
                dcha += 1.1 * d
            if ev.get("puntillo"):
                dcha += 0.7 * d
            ultimo_dcha = dcha
            cur += AVANCE[fig] * d + (0.6 * d if ev.get("puntillo") else 0)
            if ev["clase"] in ("nota", "acorde") and fig in BARRAS and ev["grupo"] is None:
                cur += 0.9 * d                      # hueco para el corchete
        x_ini_notas[-1] = (x_ini_notas[-1], ultimo_dcha)
    ancho = int(max(fin for _, fin in x_ini_notas) + 2.5 * d)
    ancho = max(ancho, pieza.get("ancho_min", 0))

    img = np.full((alto, ancho), 255, np.uint8)
    registros = []
    num_nota = 0

    for i, eventos in enumerate(sistemas):
        pg = Pentagrama(margen_sup + i * (4 * d + sep), d, grosor)
        for y in pg.lineas:
            cv.line(img, (int(1.5 * d), y), (ancho - int(1.5 * d), y), TINTA, grosor)
        cv.line(img, (int(1.5 * d), pg.lineas[0]), (int(1.5 * d), pg.lineas[4]), TINTA, grosor)
        dibujar_clave(img, 3.2 * d, pg, max(2, int(0.17 * d)))
        if i == 0 and pieza.get("compas"):
            dibujar_compas(img, 6.3 * d, pg, *pieza["compas"])

        # notas: cabezas, puntillos, alteraciones, adicionales
        fin_lineas = ancho - int(1.5 * d)
        if eventos and eventos[-1]["clase"] == "barra":
            ult = eventos[-1]
            ult["x"] = fin_lineas - (int(0.4 * d) + max(3, int(0.3 * d)) if ult["doble"] else 0)
        for ev in eventos:
            x = int(round(ev["x"]))
            if ev["clase"] == "barra":
                cv.line(img, (x, pg.lineas[0]), (x, pg.lineas[4]), TINTA, max(2, grosor))
                if ev["doble"]:
                    cv.rectangle(img, (x + int(0.4 * d), pg.lineas[0]), (x + int(0.4 * d) + max(3, int(0.3 * d)), pg.lineas[4]), TINTA, -1)
                continue
            if ev["clase"] == "acorde":
                fig = ev["fig"]
                ps = sorted(n["p"] for n in ev["notas"])
                arriba = np.mean(ps) < 4
                acorde_n = sum(1 for e in eventos[:eventos.index(ev) + 1] if e["clase"] == "acorde")
                for n in ev["notas"]:
                    cy = pg.y(n["p"])
                    dibujar_adicionales(img, x, n["p"], pg)
                    dibujar_cabeza(img, x, cy, d, hueca=fig in ("r", "b"))
                    if n["alteracion"] == "#":
                        dibujar_sostenido(img, x - 1.5 * d, cy, d)
                    if ev["puntillo"]:
                        dibujar_puntillo(img, x + 1.2 * d, pg.y(n["p"] + 1) if n["p"] % 2 == 0 else cy, d)
                    num_nota += 1
                    registros.append({
                        "numero": num_nota, "pentagrama": i + 1, "clase": "nota", "tipo": TIPO[fig],
                        "altura": f"{n['nombre']}{n['alteracion']}{n['octava']}", "puntillo": int(ev["puntillo"]),
                        "duracion_pulsos": DUR[fig] * (1.5 if ev["puntillo"] else 1),
                        "x_cabeza": x, "y_cabeza": cy, "grupo_id": "", "acorde_id": f"{i + 1}-{acorde_n}",
                    })
                if fig != "r":
                    y_bajo, y_alto = pg.y(ps[0]), pg.y(ps[-1])
                    if arriba:
                        sx, y1, y2 = int(round(x + 0.62 * d)), y_bajo, int(round(y_alto - 3.5 * d))
                    else:
                        sx, y1, y2 = int(round(x - 0.62 * d)), y_alto, int(round(y_bajo + 3.5 * d))
                    cv.line(img, (sx, y1), (sx, y2), TINTA, t_plica)
                    if fig in BARRAS:
                        dibujar_corchetes(img, sx, y2, d, arriba, BARRAS[fig], t_corchete)
                continue
            if ev["clase"] == "silencio":
                dibujar_silencio(img, x, ev["fig"], pg)
                num_nota += 1
                registros.append({
                    "numero": num_nota, "pentagrama": i + 1, "clase": "silencio",
                    "tipo": "silencio_" + TIPO[ev["fig"]], "altura": "", "puntillo": 0,
                    "duracion_pulsos": DUR[ev["fig"]], "x_cabeza": x, "y_cabeza": pg.lineas[2], "grupo_id": "", "acorde_id": "",
                })
                continue
            p, fig = ev["p"], ev["fig"]
            cy = pg.y(p)
            ev["cx"], ev["cy"] = x, cy
            dibujar_adicionales(img, x, p, pg)
            dibujar_cabeza(img, x, cy, d, hueca=fig in ("r", "b"))
            if ev["alteracion"] == "#":
                dibujar_sostenido(img, x - 1.5 * d, cy, d)
            if ev["puntillo"]:
                yp = pg.y(p + 1) if p % 2 == 0 else cy
                dibujar_puntillo(img, x + 1.2 * d, yp, d)
            ev["arriba"] = p < 4
            num_nota += 1
            dur = DUR[fig] * (1.5 if ev["puntillo"] else 1)
            altura = f"{ev['nombre']}{ev['alteracion']}{ev['octava']}"
            registros.append({
                "numero": num_nota, "pentagrama": i + 1, "clase": "nota", "tipo": TIPO[fig],
                "altura": altura, "puntillo": int(ev["puntillo"]), "duracion_pulsos": dur,
                "x_cabeza": x, "y_cabeza": cy, "grupo_id": f"{i + 1}-{ev['grupo']}" if ev["grupo"] else "", "acorde_id": "",
            })

        # plicas sueltas + corchetes
        for ev in eventos:
            if ev["clase"] != "nota" or ev["fig"] == "r" or ev["grupo"]:
                continue
            x, cy, arriba = ev["cx"], ev["cy"], ev["arriba"]
            sx = int(round(x + 0.62 * d)) if arriba else int(round(x - 0.62 * d))
            ty = int(round(cy - 3.5 * d)) if arriba else int(round(cy + 3.5 * d))
            cv.line(img, (sx, cy), (sx, ty), TINTA, t_plica)
            if ev["fig"] in BARRAS:
                dibujar_corchetes(img, sx, ty, d, arriba, BARRAS[ev["fig"]], t_corchete)

        # grupos con barras
        grupos = {}
        for ev in eventos:
            if ev["clase"] == "nota" and ev["grupo"]:
                grupos.setdefault(ev["grupo"], []).append(ev)
        for notas in grupos.values():
            arriba = np.mean([n["p"] for n in notas]) < 4
            s = 1 if arriba else -1
            xs = [int(round(n["cx"] + 0.62 * d)) if arriba else int(round(n["cx"] - 0.62 * d)) for n in notas]
            cys = [n["cy"] for n in notas]
            pend = 0.0
            if inclinadas and len(notas) > 1 and xs[-1] != xs[0]:
                pend = float(np.clip((cys[-1] - cys[0]) / (xs[-1] - xs[0]) * 0.5, -0.18, 0.18))
            if arriba:
                y0 = min(c - 3.3 * d - pend * (xx - xs[0]) for c, xx in zip(cys, xs))
            else:
                y0 = max(c + 3.3 * d - pend * (xx - xs[0]) for c, xx in zip(cys, xs))
            yb = lambda xx: y0 + pend * (xx - xs[0])
            for xx, c in zip(xs, cys):
                cv.line(img, (xx, c), (xx, int(round(yb(xx)))), TINTA, t_plica)
            ext = t_plica / 2
            dibujar_barra(img, xs[0] - ext, yb(xs[0] - ext), xs[-1] + ext, yb(xs[-1] + ext), t_barra, s)
            niveles = [BARRAS[n["fig"]] for n in notas]
            off = s * 0.8 * d
            for k in range(len(notas)):
                if niveles[k] < 2:
                    continue
                if k + 1 < len(notas) and niveles[k + 1] >= 2:
                    x1, x2 = xs[k] - ext, xs[k + 1] + ext
                elif (k == 0 or niveles[k - 1] < 2):
                    if k > 0:
                        x1, x2 = xs[k] - 1.0 * d, xs[k] + ext
                    else:
                        x1, x2 = xs[k] - ext, xs[k] + 1.0 * d
                else:
                    continue
                dibujar_barra(img, x1, yb(x1) + off, x2, yb(x2) + off, t_barra, s)

    #degradación opcional (rotación + ruido)
    if pieza.get("rotacion") or pieza.get("ruido"):
        ang = pieza.get("rotacion", 0)
        M = cv.getRotationMatrix2D((ancho / 2, alto / 2), ang, 1.0)
        img = cv.warpAffine(img, M, (ancho, alto), flags=cv.INTER_LINEAR, borderValue=255)
        for r in registros:
            x, y = r["x_cabeza"], r["y_cabeza"]
            r["x_cabeza"] = int(round(M[0, 0] * x + M[0, 1] * y + M[0, 2]))
            r["y_cabeza"] = int(round(M[1, 0] * x + M[1, 1] * y + M[1, 2]))
        rng = np.random.default_rng(7)
        ruido = rng.normal(0, pieza.get("ruido", 0), img.shape)
        img = cv.GaussianBlur(np.clip(img + ruido, 0, 255).astype(np.uint8), (3, 3), 0)

    nombre = pieza["nombre"]
    cv.imwrite(str(carpeta / f"{nombre}.png"), img)
    with open(carpeta / f"{nombre}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(registros[0].keys()))
        w.writeheader()
        w.writerows(registros)
    return registros


#piezas aleatorias
def compas_aleatorio(rng, dificil):
    patrones = [(["n"], 4), (["c", "c"], 3), (["s", "s", "s", "s"], 2), (["c", "s", "s"], 1 + dificil),
                (["s", "s", "c"], 1 + dificil), (["c.", "s"], dificil * 2), (["S:n"], dificil)]
    pesos = [w for _, w in patrones]
    pulsos, toks = 0, []
    while pulsos < 4:
        if pulsos <= 2 and rng.random() < 0.18:
            toks.append(("b",))
            pulsos += 2
            continue
        pat = rng.choices([p for p, _ in patrones], weights=pesos)[0]
        toks.append(tuple(pat))
        pulsos += 1
    return toks


def melodia_aleatoria(seed, n_pent, compases, dificil=0, p_min=-1, p_max=9):
    rng = random.Random(seed)
    p = 4
    pentas = []
    for _ in range(n_pent):
        partes = []
        for c in range(compases):
            for bloque in compas_aleatorio(rng, dificil):
                notas = []
                for fig in bloque:
                    if fig.startswith("S:"):
                        notas.append(fig)
                        continue
                    p = max(p_min, min(p_max, p + rng.choice([-2, -1, -1, 0, 1, 1, 2, 3, -3])))
                    notas.append(f"{pos_a_altura(p)}:{fig}")
                if len(notas) > 1:
                    partes.append("[ " + " ".join(notas) + " ]")
                else:
                    partes.extend(notas)
            partes.append("|")
        pentas.append(" ".join(partes))
    pentas[-1] = pentas[-1][:-1] + "||"
    return pentas


#catálogo
CUMPLE_SIMPLE = [
    "[ SOL4:c SOL4:c ] | LA4:n SOL4:n DO5:n | SI4:b [ SOL4:c SOL4:c ] | LA4:n SOL4:n RE5:n | DO5:b [ SOL4:c SOL4:c ] |",
    "SOL5:n MI5:n DO5:n | SI4:n LA4:n [ FA5:c FA5:c ] | MI5:n DO5:n RE5:n | DO5:b ||",
]
CUMPLE_PUNTILLO = [
    "[ SOL4:c. SOL4:s ] | LA4:n SOL4:n DO5:n | SI4:b |",
    "[ SOL4:c. SOL4:s ] | LA4:n SOL4:n RE5:n | DO5:b |",
    "[ SOL4:c. SOL4:s ] | SOL5:n MI5:n DO5:n | SI4:n LA4:n |",
    "[ FA5:c. FA5:s ] | MI5:n DO5:n RE5:n | DO5:b. ||",
]

PIEZAS = [
    {"nombre": "01-Negras basicas", "nivel": "basico", "compas": (4, 4),
     "pentagramas": ["MI4:n FA4:n SOL4:n LA4:n | SI4:n DO5:n RE5:n MI5:n | FA5:n MI5:n RE5:n DO5:n | SI4:n LA4:n SOL4:n FA4:n ||"]},
    {"nombre": "02-Negras blancas y redonda", "nivel": "basico", "compas": (4, 4),
     "pentagramas": ["DO5:b SOL4:b | LA4:n SI4:n DO5:b | MI4:b FA4:n SOL4:n | DO5:r ||"]},
    {"nombre": "03-Corcheas unidas", "nivel": "basico", "compas": (4, 4),
     "pentagramas": ["[ SOL4:c LA4:c ] [ SI4:c DO5:c ] RE5:n RE5:n | [ MI5:c RE5:c ] [ DO5:c SI4:c ] LA4:b | "
                     "[ SOL4:c SOL4:c SOL4:c SOL4:c ] [ LA4:c SI4:c DO5:c RE5:c ] ||"]},
    {"nombre": "04-Corcheas sueltas", "nivel": "basico", "compas": (4, 4),
     "pentagramas": ["SOL4:c S:c LA4:c SI4:c DO5:n RE5:n | MI5:c FA5:c SOL4:n LA4:b ||"]},
    {"nombre": "05-Semicorcheas unidas", "nivel": "medio", "compas": (4, 4),
     "pentagramas": ["[ DO5:s SI4:s LA4:s SOL4:s ] [ FA4:s SOL4:s LA4:s SI4:s ] DO5:b | "
                     "[ MI5:s RE5:s DO5:s SI4:s ] [ LA4:c SOL4:c ] [ SOL4:s LA4:s SI4:s DO5:s ] RE5:n ||"]},
    {"nombre": "06-Semicorcheas sueltas y mixtas", "nivel": "medio", "compas": (4, 4),
     "pentagramas": ["SOL4:s LA4:s SI4:s DO5:s RE5:n MI5:b | [ SOL4:c LA4:s SI4:s ] [ DO5:s RE5:s MI5:c ] FA5:b ||"]},
    {"nombre": "07-Dos pentagramas mezcla", "nivel": "medio", "compas": (4, 4),
     "pentagramas": ["DO5:n [ SI4:c LA4:c ] SOL4:n [ FA4:s MI4:s FA4:s SOL4:s ] | LA4:b SOL4:b |",
                     "[ MI5:c RE5:c ] [ DO5:s SI4:s LA4:s SOL4:s ] FA4:n MI4:n | MI4:r ||"]},
    {"nombre": "08-Lineas adicionales", "nivel": "medio", "compas": (4, 4),
     "pentagramas": ["DO4:n RE4:n MI4:n FA4:n | SOL5:n LA5:n SI5:n DO6:n |",
                     "LA3:b SI3:b | [ DO4:c RE4:c ] [ LA5:c SI5:c ] DO6:b ||"]},
    {"nombre": "09-Cumpleanos feliz", "nivel": "basico", "compas": (3, 4), "pentagramas": CUMPLE_SIMPLE},
    {"nombre": "10-Cumpleanos feliz con puntillo", "nivel": "dificil", "compas": (3, 4), "d": 18,
     "pentagramas": CUMPLE_PUNTILLO},
    {"nombre": "11-Tres pentagramas mezcla", "nivel": "medio", "compas": (4, 4), "d": 16,
     "pentagramas": melodia_aleatoria(11, 3, 3, dificil=0)},
    {"nombre": "12-Cuatro pentagramas largo", "nivel": "medio", "compas": (4, 4), "d": 22,
     "pentagramas": melodia_aleatoria(12, 4, 4, dificil=1, p_min=-2, p_max=10)},
    {"nombre": "13-Dificil silencios puntillos sostenidos", "nivel": "dificil", "compas": (4, 4),
     "barras_inclinadas": True,
     "pentagramas": ["DO5:n S:n [ SI4:c. LA4:s ] SOL4:n | FA#4:n S:c SOL4:c LA4:b | DO#5:n. RE5:c S:b |",
                     "[ SOL4:s LA4:s SI4:s DO5:s ] RE5:b. | [ MI5:c DO5:c ] [ LA4:s SI4:s DO5:c ] S:b | MI4:r ||"]},
    {"nombre": "15-Acordes", "nivel": "medio", "compas": (4, 4),
     "pentagramas": ["DO4+MI4+SOL4:n FA4+LA4+DO5:n SOL4+SI4+RE5:n DO4+MI4+SOL4:n | SOL4+SI4+RE5+FA5:b DO5+MI5+SOL5:b |",
                     "LA4+DO5+MI5:n FA4+LA4+DO5:n SOL4+SI4+RE5:n SOL4+SI4+RE5+FA5:n | DO4+MI4+SOL4+DO5:r ||"]},
    {"nombre": "16-Acordes y melodia", "nivel": "dificil", "compas": (3, 4),
     "pentagramas": ["[ SOL4:c SOL4:c ] | DO4+MI4+LA4:n SOL4:n DO5:n | SOL4+SI4+RE5+FA5:b [ SOL4:c SOL4:c ] |",
                     "LA4:n SOL4:n RE5:n | DO4+MI4+SOL4+DO5:b. ||"]},
    {"nombre": "17-Bella ciao", "nivel": "medio", "compas": (4, 4),
     "pentagramas": ["[ MI4:c LA4:c SI4:c ] | DO5:c LA4:b [ MI4:c LA4:c SI4:c ] | DO5:c LA4:b [ MI4:c LA4:c SI4:c ] |",
                     "DO5:n [ SI4:c LA4:c ] DO5:n [ SI4:c LA4:c ] | MI5:n MI5:n [ MI5:c MI5:c RE5:c MI5:c ] |",
                     "FA5:c FA5:b [ FA5:c MI5:c RE5:c ] | FA5:c MI5:b [ MI5:c RE5:c DO5:c ] |",
                     "SI4:n MI5:n DO5:n SI4:n | LA4:b S:b ||"]},
    {"nombre": "18-Twinkle twinkle little star", "nivel": "basico", "compas": (4, 4),
     "pentagramas": ["DO4:n DO4:n SOL4:n SOL4:n | LA4:n LA4:n SOL4:b | FA4:n FA4:n MI4:n MI4:n | RE4:n RE4:n DO4:b |",
                     "SOL4:n SOL4:n FA4:n FA4:n | MI4:n MI4:n RE4:b | SOL4:n SOL4:n FA4:n FA4:n | MI4:n MI4:n RE4:b |",
                     "DO4:n DO4:n SOL4:n SOL4:n | LA4:n LA4:n SOL4:b | FA4:n FA4:n MI4:n MI4:n | RE4:n RE4:n DO4:b ||"]},
    {"nombre": "19-Jingle bells", "nivel": "medio", "compas": (4, 4),
     "pentagramas": ["MI4:n MI4:n MI4:b | MI4:n MI4:n MI4:b | MI4:n SOL4:n DO4:n. RE4:c | MI4:b S:b |",
                     "FA4:n FA4:n FA4:n. FA4:c | FA4:n MI4:n MI4:n [ MI4:c MI4:c ] | MI4:n RE4:n RE4:n MI4:n | RE4:b SOL4:b |",
                     "MI4:n MI4:n MI4:b | MI4:n MI4:n MI4:b | MI4:n SOL4:n DO4:n. RE4:c | MI4:b S:b |",
                     "FA4:n FA4:n FA4:n. FA4:c | FA4:n MI4:n MI4:n [ MI4:c MI4:c ] | SOL4:n SOL4:n FA4:n RE4:n | DO4:b S:b ||"]},
    {"nombre": "20-Himno de la alegria", "nivel": "medio", "compas": (4, 4),
     "pentagramas": ["MI4:n MI4:n FA4:n SOL4:n | SOL4:n FA4:n MI4:n RE4:n | DO4:n DO4:n RE4:n MI4:n | MI4:n. RE4:c RE4:b |",
                     "MI4:n MI4:n FA4:n SOL4:n | SOL4:n FA4:n MI4:n RE4:n | DO4:n DO4:n RE4:n MI4:n | RE4:n. DO4:c DO4:b ||"]},
    {"nombre": "21-We wish you a merry christmas", "nivel": "medio", "compas": (3, 4),
     "pentagramas": ["SOL4:n | DO5:n [ DO5:c RE5:c DO5:c SI4:c ] | LA4:n LA4:n LA4:n | RE5:n [ RE5:c MI5:c RE5:c DO5:c ] |",
                     "SI4:n SOL4:n SOL4:n | MI5:n [ MI5:c FA5:c MI5:c RE5:c ] | DO5:n LA4:n [ SOL4:c SOL4:c ] |",
                     "LA4:n RE5:n SI4:n | DO5:b ||"]},
    {"nombre": "22-Frere Jacques", "nivel": "medio", "compas": (4, 4),
     "pentagramas": ["DO4:n RE4:n MI4:n DO4:n | DO4:n RE4:n MI4:n DO4:n | MI4:n FA4:n SOL4:b | MI4:n FA4:n SOL4:b |",
                     "[ SOL4:c LA4:c SOL4:c FA4:c ] MI4:n DO4:n | [ SOL4:c LA4:c SOL4:c FA4:c ] MI4:n DO4:n | DO4:n SOL3:n DO4:b | DO4:n SOL3:n DO4:b ||"]},
    {"nombre": "14-Dificil cumpleanos escaneado", "nivel": "dificil", "compas": (3, 4), "d": 20,
     "barras_inclinadas": True, "rotacion": 0.7, "ruido": 14, "grosor_linea": 3,
     "pentagramas": [" ".join(CUMPLE_PUNTILLO[:2]), " ".join(CUMPLE_PUNTILLO[2:])]},
]


def main():
    salida = Path(__file__).resolve().parent.parent / "datasets" / "MiniDataset_7"
    salida.mkdir(exist_ok=True)
    todos, resumen = [], []
    for pieza in PIEZAS:
        regs = renderizar(pieza, salida)
        for r in regs:
            todos.append({"imagen": pieza["nombre"] + ".png", **r})
        tipos = {}
        for r in regs:
            tipos[r["tipo"]] = tipos.get(r["tipo"], 0) + 1
        resumen.append({"imagen": pieza["nombre"] + ".png", "nivel": pieza["nivel"],
                        "pentagramas": len(pieza["pentagramas"]), "figuras": tipos,
                        "melodia": pieza["pentagramas"]})
        print(f"{pieza['nombre']:45s} {len(regs):3d} figuras  {tipos}")

    with open(salida / "ground_truth_completo.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(todos[0].keys()))
        w.writeheader()
        w.writerows(todos)
    with open(salida / "resumen.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
