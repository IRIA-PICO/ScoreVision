"""
ScoreVision · NÚCLEO DE VISIÓN POR COMPUTADOR
=============================================
Aquí solo hay OpenCV y numpy: nada de ventanas ni de sonido.

    from scorevision_core import analizar_partitura
    resultado = analizar_partitura(imagen_gris)
    resultado["notas"]      -> lista de notas y silencios, ordenados en el tiempo
    resultado["imagenes"]   -> imágenes de cada paso (para el Inspector)

Pipeline:
  1. Binarizar
  2. Detectar las líneas del pentagrama (proyección horizontal)
  3. Borrar las líneas sin romper las notas (máscara selectiva + cierre)
  4. Separar símbolos (componentes conexas)
  5. Silencios  -> reglas geométricas
  6. Grupos con barra (corcheas / semicorcheas unidas)
  7. Notas sueltas y acordes (+ corchetes)
  8. Puntillos
  9. Altura de cada nota (DO4, SOL4...) y orden temporal
"""
import cv2 as cv
import numpy as np

NOMBRES_NOTAS = ["DO", "RE", "MI", "FA", "SOL", "LA", "SI"]

DURACIONES = {
    "negra": 1,
    "blanca": 2,
    "corchea": 0.5,
    "semicorchea": 0.25,
    "silencio_redonda": 4,
    "silencio_blanca": 2,
    "silencio_negra": 1,
    "silencio_corchea": 0.5,
}


# 2. PENTAGRAMAS
def detectar_pentagramas(binaria):
    """Devuelve las Y de las líneas, agrupadas en pentagramas de 5,
    la separación entre líneas (dist_media) y su grosor."""
    alto, ancho = binaria.shape

    #Solo nos quedamos con trazos horizontales largos
    ancho_kernel = max(30, int(ancho * 0.05))
    kernel_h = cv.getStructuringElement(cv.MORPH_RECT, (ancho_kernel, 1))
    lineas_h = cv.morphologyEx(binaria, cv.MORPH_OPEN, kernel_h)

    #Proyección horizontal en la zona central
    x_ini, x_fin = int(ancho * 0.25), int(ancho * 0.75)
    proyeccion = np.count_nonzero(lineas_h[:, x_ini:x_fin], axis=1)
    filas_activas = np.where(proyeccion > (x_fin - x_ini) * 0.50)[0]

    #Filas seguidas = la misma línea (una línea puede medir 2-3 px)
    grupos = []
    for y in filas_activas:
        if not grupos or y - grupos[-1][-1] > 2:
            grupos.append([int(y)])
        else:
            grupos[-1].append(int(y))

    lineas_y = sorted(max(g, key=lambda y: proyeccion[y]) for g in grupos)
    distancias = np.diff(lineas_y)
    dist_media = float(np.median(distancias)) if len(distancias) > 0 else 10.0
    grosor_linea = max(1, int(np.median([len(g) for g in grupos]))) if grupos else 1

    #Agrupar en pentagramas: un salto grande separa sistemas
    pentagramas = []
    if lineas_y:
        actual = [lineas_y[0]]
        for y in lineas_y[1:]:
            if y - actual[-1] > dist_media * 2.2:
                pentagramas.append(actual)
                actual = [y]
            else:
                actual.append(y)
        pentagramas.append(actual)

    return pentagramas, dist_media, grosor_linea

#3. BORRAR LÍNEA
def eliminar_lineas(binaria, dist_media, grosor_linea):
    """Borra solo los píxeles que son línea: horizontales Y con una racha
    vertical del grosor de una línea. Así no se cortan cabezas ni plicas."""
    alto, ancho = binaria.shape
    b = (binaria > 0).astype(np.uint8)

    #Para cada píxel: cuánto mide la racha vertical de tinta a la que pertenece
    mapa_alturas = np.zeros_like(b, dtype=np.int32)
    for x in range(ancho):
        col = b[:, x]
        cambios = np.flatnonzero(np.diff(col)) + 1
        limites = np.concatenate(([0], cambios, [alto]))
        for ini, fin, val in zip(limites[:-1], limites[1:], col[limites[:-1]]):
            if val == 1:
                mapa_alturas[ini:fin, x] = fin - ini

    k_lineas = cv.getStructuringElement(cv.MORPH_RECT, (int(dist_media * 1.5), 1))
    mascara_h = cv.morphologyEx(binaria, cv.MORPH_OPEN, k_lineas)

    quitar = (mascara_h > 0) & (mapa_alturas <= grosor_linea + 2)
    sin_lineas = binaria.copy()
    sin_lineas[quitar] = 0

    #Cerrar los micro-cortes que hayan quedado
    k_restaurar = cv.getStructuringElement(cv.MORPH_RECT, (1, grosor_linea + 2))
    restaurada = cv.morphologyEx(sin_lineas, cv.MORPH_CLOSE, k_restaurar)

    return quitar.astype(np.uint8) * 255, sin_lineas, restaurada

# Utilidades
def pentagrama_mas_cercano(cy, pentagramas):
    return min(range(len(pentagramas)),
               key=lambda j: max(pentagramas[j][0] - cy, 0, cy - pentagramas[j][-1]))


def calcular_altura(cy, lineas):
    """Posición vertical -> nombre de nota. La línea de abajo es MI4 y
    cada medio espacio (línea o hueco) sube una nota"""
    separacion = np.median(np.diff(lineas))
    pasos = round((lineas[-1] - cy) / (separacion / 2))
    indice = 4 * 7 + 2 + pasos
    return f"{NOMBRES_NOTAS[indice % 7]}{indice // 7}"


def rellenar_huecos(recorte, dist_media):
    """Cierre + relleno de agujeros (para que una blanca parezca maciza)"""
    k = max(3, int(round(dist_media * 0.35)))
    k += (k % 2 == 0)
    cerrado = cv.morphologyEx(recorte, cv.MORPH_CLOSE,
                              cv.getStructuringElement(cv.MORPH_ELLIPSE, (k, k)))
    h, w = cerrado.shape
    relleno = cv.copyMakeBorder(cerrado, 1, 1, 1, 1, cv.BORDER_CONSTANT, value=0)
    mascara = np.zeros((h + 4, w + 4), dtype=np.uint8)
    cv.floodFill(relleno, mascara, (0, 0), 255)
    huecos = cv.bitwise_not(relleno)[1:-1, 1:-1]
    return cv.bitwise_or(cerrado, huecos)


def tapar_agujeros(recorte):
    """Rellena agujeros cerrados SIN cierre morfológico (no pega cabezas de al lado)"""
    borde = cv.copyMakeBorder(recorte, 1, 1, 1, 1, cv.BORDER_CONSTANT, value=0)
    mascara = np.zeros((borde.shape[0] + 2, borde.shape[1] + 2), np.uint8)
    cv.floodFill(borde, mascara, (0, 0), 255)
    agujeros = cv.bitwise_not(borde)[1:-1, 1:-1]
    return cv.bitwise_or(recorte, agujeros)


def tipo_por_densidad(recorte, local_cx, local_cy, dist_media):
    """Cabeza hueca (blanca) o llena (negra) según la tinta del centro"""
    h, w = recorte.shape
    r = max(2, int(dist_media * 0.35))
    ventana = recorte[max(0, local_cy - r):min(h, local_cy + r),
                      max(0, local_cx - r):min(w, local_cx + r)]
    densidad = (np.mean(ventana) / 255.0) if ventana.size > 0 else 1.0
    return "blanca" if densidad < 0.45 else "negra"


def _rachas(columna, minimo, maximo):
    """Cuántas franjas de tinta de grosor [minimo, maximo] cruzan una columna"""
    tinta = (columna > 0).astype(np.int8)
    cambios = np.diff(np.pad(tinta, (1, 1)))
    grosores = np.where(cambios == -1)[0] - np.where(cambios == 1)[0]
    return int(np.count_nonzero((grosores >= minimo) & (grosores <= maximo)))

#5. SILENCIOS
def clasificar_silencio(recorte, x, y, w, h, lineas, d):
    """Reglas geométricas en unidades de d (separación entre líneas)"""
    relleno = np.count_nonzero(recorte) / float(w * h)
    cy = y + h / 2
    if not (lineas[0] - 0.5 * d <= cy <= lineas[4] + 0.5 * d):
        return None

    #Rectángulo macizo: la blanca se APOYA en la línea central,
    #la redonda CUELGA de la 2ª línea empezando por arriba
    if 0.8 * d <= w <= 1.7 * d and 0.25 * d <= h <= 0.8 * d and relleno >= 0.8:
        if abs((y + h) - lineas[2]) <= 0.35 * d:
            return "silencio_blanca"
        if abs(y - lineas[1]) <= 0.35 * d:
            return "silencio_redonda"
        return None

    #Zigzag alto y estrecho
    if (2.7 * d <= h <= 3.8 * d and 0.5 * d <= w <= 1.3 * d
            and 0.2 <= relleno <= 0.65 and abs(cy - lineas[2]) <= 0.8 * d):
        return "silencio_negra"

    #Bolita arriba + palito
    if 1.4 * d < h < 2.7 * d and 0.5 * d <= w <= 1.4 * d and relleno <= 0.6:
        mitad = h // 2
        if np.count_nonzero(recorte[:mitad]) > 1.3 * np.count_nonzero(recorte[mitad:]):
            return "silencio_corchea"
    return None


#6. GRUPOS CON BARRA
def contar_barras(recorte, cabezas, x, y, dist_media):
    """Entre cada par de cabezas, cuántas barras cruzan una columna vertical"""
    h, w = recorte.shape
    cy_min = min(cy for _, cy in cabezas) - y
    cy_max = max(cy for _, cy in cabezas) - y
    limite_arriba = max(0, int(cy_min - 0.65 * dist_media))
    limite_abajo = min(h, int(cy_max + 0.65 * dist_media))

    conteos = []
    for (cx1, _), (cx2, _) in zip(cabezas[:-1], cabezas[1:]):
        muestras = []
        for fraccion in (0.4, 0.5, 0.6):
            col = int(round(cx1 + fraccion * (cx2 - cx1))) - x
            if not 0 <= col < w:
                continue
            arriba = _rachas(recorte[:limite_arriba, col], 0.16 * dist_media, 0.85 * dist_media)
            abajo = _rachas(recorte[limite_abajo:, col], 0.16 * dist_media, 0.85 * dist_media)
            muestras.append(max(arriba, abajo))
        if muestras:
            conteos.append(int(round(np.median(muestras))))
    return conteos


def detectar_grupos(num, etiquetas, stats, pentagramas, dist_media):
    d = dist_media
    kw = max(3, int(round(d * 0.46)));  kw += (kw % 2 == 0)
    kh = max(3, int(round(d * 0.32)));  kh += (kh % 2 == 0)
    kernel_cabezas = cv.getStructuringElement(cv.MORPH_ELLIPSE, (kw, kh))
    tipos_por_barras = {1: "corchea", 2: "semicorchea"}

    grupos = []
    for etiqueta in range(1, num):
        x, y, w, h, area = map(int, stats[etiqueta])
        if not (1.6 * d < w < 12 * d and 1.8 * d < h < 7 * d):
            continue
        recorte = (etiquetas[y:y+h, x:x+w] == etiqueta).astype(np.uint8) * 255

        #Las cabezas sobreviven a una apertura elíptica; plicas y barras no
        cabezas_mask = cv.morphologyEx(recorte, cv.MORPH_OPEN, kernel_cabezas)
        n, _, st, centros = cv.connectedComponentsWithStats(cabezas_mask, connectivity=8)
        cabezas = []
        for j in range(1, n):
            _, _, wc, hc, area_c = st[j]
            if not (0.45 * d <= wc <= 2.2 * d and 0.4 * d <= hc <= 2.2 * d
                    and 0.1 * d**2 <= area_c <= 1.8 * d**2):
                continue
            if not 0.55 <= wc / hc <= 2.2:
                continue
            cx, cy = int(round(x + centros[j][0])), int(round(y + centros[j][1]))
            if any(p[0] - 2 * d <= cy <= p[-1] + 2 * d for p in pentagramas):
                cabezas.append((cx, cy))

        cabezas.sort()
        if len(cabezas) < 2:
            continue
        if any(b[0] - a[0] < 0.65 * d for a, b in zip(cabezas[:-1], cabezas[1:])):
            continue

        conteos = contar_barras(recorte, cabezas, x, y, d)
        if not conteos or len(set(conteos)) != 1:
            continue
        tipo = tipos_por_barras.get(conteos[0])
        if tipo is None:
            continue

        grupos.append({"etiqueta": etiqueta, "x": x, "y": y, "w": w, "h": h,
                       "cabezas": cabezas, "barras": conteos[0], "tipo": tipo,
                       "recorte": recorte})
    return grupos

#7. NOTAS SUELTAS, ACORDES Y CORCHETES
def buscar_cabezas_apiladas(recorte, dist_media):
    """Todas las cabezas de un componente, aunque estén pegadas (acorde).
    Perfil horizontal: cada cabeza deja un pico de anchura."""
    d = dist_media
    recorte_relleno = tapar_agujeros(recorte)

    #Quitar la plica (más estrecha que media separación)
    k = max(3, int(round(d * 0.5)))
    solo_cabezas = cv.morphologyEx(recorte_relleno, cv.MORPH_OPEN,
                                   cv.getStructuringElement(cv.MORPH_RECT, (k, 1)))

    perfil = np.count_nonzero(solo_cabezas, axis=1).astype(float)
    v = max(3, int(round(d * 0.15)))
    perfil = np.convolve(perfil, np.ones(v) / v, mode="same")

    radio = max(2, int(round(d * 0.4)))
    mesetas = []
    for fila in range(len(perfil)):
        a, b = max(0, fila - radio), min(len(perfil), fila + radio + 1)
        if perfil[fila] >= 0.8 * d and perfil[fila] >= perfil[a:b].max():
            if mesetas and fila - mesetas[-1][-1] <= 1:
                mesetas[-1].append(fila)
            else:
                mesetas.append([fila])

    rx, ry = int(round(0.55 * d)), int(round(0.25 * d))
    r = max(2, int(d * 0.35))
    cabezas = []
    for meseta in mesetas:
        cy = int(round(np.mean(meseta)))
        columnas = np.nonzero(solo_cabezas[max(0, cy - ry):cy + ry + 1])[1]
        if columnas.size == 0:
            continue
        cx = int(round(columnas.mean()))
        caja = (slice(max(0, cy - ry), cy + ry + 1), slice(max(0, cx - rx), cx + rx + 1))
        lleno_original = np.mean(recorte[caja] > 0)
        lleno_relleno = np.mean(recorte_relleno[caja] > 0)
        centro = recorte[max(0, cy - r):cy + r, max(0, cx - r):cx + r]
        densidad_centro = np.mean(centro > 0) if centro.size else 1.0
        if lleno_original >= 0.75:
            clase = "llena"
        elif lleno_relleno >= 0.75 and densidad_centro < 0.45:
            clase = "hueca"
        else:
            continue
        cabezas.append((cx, cy, clase))

    if len(cabezas) < 2:
        return [(cx, cy) for cx, cy, _ in cabezas]

    #Reglas musicales de un acorde
    cx_med = np.median([c[0] for c in cabezas])
    if any(abs(c[0] - cx_med) > 0.6 * d for c in cabezas):        #misma columna
        return []
    if len({c[2] for c in cabezas}) != 1:                          #misma figura
        return []
    ys = sorted(c[1] for c in cabezas)
    if any(not (0.85 * d <= b - a <= 4 * d) for a, b in zip(ys[:-1], ys[1:])):
        return []                                                  #>= una tercera
    if cabezas[0][2] == "llena":                                   #necesita plica
        racha_max = 0
        for col in (recorte > 0).T:
            cambios = np.diff(np.concatenate(([0], col.astype(np.int8), [0])))
            ini, fin = np.where(cambios == 1)[0], np.where(cambios == -1)[0]
            if ini.size:
                racha_max = max(racha_max, int((fin - ini).max()))
        if racha_max < (ys[-1] - ys[0]) + 2 * d:
            return []
    return [(cx, cy) for cx, cy, _ in cabezas]


def contar_corchetes(recorte, local_cx, local_cy, dist_media):
    """0 negra, 1 corchea, 2 semicorchea: franjas a la derecha de la plica,
    en el extremo contrario a la cabeza"""
    d = dist_media
    h, w = recorte.shape
    col_plica = int(np.argmax(np.count_nonzero(recorte, axis=0)))
    if local_cy > h / 2:
        zona = recorte[:max(0, int(local_cy - 0.8 * d)), :]
    else:
        zona = recorte[int(local_cy + 0.8 * d):, :]
    if zona.size == 0:
        return 0
    conteos = []
    for desplazamiento in (0.3, 0.45, 0.6):
        col = col_plica + int(round(desplazamiento * d))
        if col < w:
            conteos.append(_rachas(zona[:, col], 0.1 * d, 0.7 * d))
    return int(np.median(conteos)) if conteos else 0


def detectar_notas(candidatas, etiquetas, dist_media):
    kernel_cabeza = cv.getStructuringElement(cv.MORPH_ELLIPSE, (13, 9))
    notas = []
    for cand in candidatas:
        x, y, w, h, etiqueta = cand["x"], cand["y"], cand["w"], cand["h"], cand["etiqueta"]
        recorte = (etiquetas[y:y+h, x:x+w] == etiqueta).astype(np.uint8) * 255
        base = {"etiqueta": etiqueta, "x": x, "y": y, "w": w, "h": h,
                "grupo_id": None, "acorde_id": None, "recorte": recorte}

        # ¿Acorde? (varias cabezas en la misma plica)
        cabezas_acorde = buscar_cabezas_apiladas(recorte, dist_media)
        if len(cabezas_acorde) >= 2:
            for lcx, lcy in cabezas_acorde:
                notas.append({**base, "cx": x + lcx, "cy": y + lcy, "acorde_id": etiqueta,
                              "tipo": tipo_por_densidad(recorte, lcx, lcy, dist_media)})
            continue
        if not cand["normal"]:
            continue

        #Nota suelta: la cabeza sobrevive a una apertura elíptica
        relleno = rellenar_huecos(recorte, dist_media)
        cabeza = cv.morphologyEx(relleno, cv.MORPH_OPEN, kernel_cabeza)
        n, _, st, centros = cv.connectedComponentsWithStats(cabeza, connectivity=8)
        if n < 2:
            continue
        idx = 1 + np.argmax(st[1:, cv.CC_STAT_AREA])
        cx, cy = int(round(x + centros[idx][0])), int(round(y + centros[idx][1]))
        if len(cabezas_acorde) == 1:          # sin cierre: no confunde corchetes con cabeza
            cx, cy = x + cabezas_acorde[0][0], y + cabezas_acorde[0][1]

        lcx, lcy = cx - x, cy - y
        tipo = tipo_por_densidad(recorte, lcx, lcy, dist_media)
        if tipo == "negra":
            tipo = {0: "negra", 1: "corchea"}.get(
                contar_corchetes(recorte, lcx, lcy, dist_media), "semicorchea")
        notas.append({**base, "cx": cx, "cy": cy, "tipo": tipo})
    return notas

#8. PUNTILLOS
def detectar_puntillos(num, etiquetas, stats, notas, usadas, dist_media):
    """Un puntillo es una mancha pequeña, redonda y maciza justo a la derecha
    de una cabeza (a la misma altura o medio espacio por encima).
    Marca nota["puntillo"] = True y devuelve las manchas encontradas."""
    d = dist_media
    puntos = []
    for i in range(1, num):
        if i in usadas:
            continue
        x, y, w, h, area = map(int, stats[i])
        if not (0.2 * d <= w <= 0.65 * d and 0.2 * d <= h <= 0.65 * d):
            continue
        if area / float(w * h) < 0.55 or not 0.6 <= w / h <= 1.6:
            continue
        px, py = x + w / 2, y + h / 2

        #La nota a la que pertenece: a su izquierda y cerca
        candidatas = [n for n in notas
                      if not n["tipo"].startswith("silencio")
                      and 0.5 * d <= px - n["cx"] <= 2.0 * d
                      and -0.9 * d <= py - n["cy"] <= 0.4 * d]
        if not candidatas:
            continue
        nota = min(candidatas, key=lambda n: (px - n["cx"]) ** 2 + (py - n["cy"]) ** 2)
        if nota["acorde_id"] is not None:       # en un acorde, todas llevan puntillo
            for n in notas:
                if n["acorde_id"] == nota["acorde_id"]:
                    n["puntillo"] = True
        else:
            nota["puntillo"] = True
        puntos.append((int(px), int(py)))
    return puntos


#FUNCIÓN PRINCIPAL
def analizar_partitura(imagen):
    """imagen: escala de grises (o BGR). Devuelve un diccionario con
    notas, pentagramas, dist_media e imágenes de cada paso"""
    if imagen.ndim == 3:
        imagen = cv.cvtColor(imagen, cv.COLOR_BGR2GRAY)

    #1-3
    _, binaria = cv.threshold(imagen, 127, 255, cv.THRESH_BINARY_INV)
    pentagramas, dist_media, grosor_linea = detectar_pentagramas(binaria)
    pentagramas = [p for p in pentagramas if len(p) == 5]
    if not pentagramas:
        raise ValueError("No se ha encontrado ningún pentagrama de 5 líneas")
    d = dist_media
    mascara_borrado, sin_lineas, restaurada = eliminar_lineas(binaria, d, grosor_linea)

    #4. Componentes conexas
    num, etiquetas, stats, _ = cv.connectedComponentsWithStats(restaurada, connectivity=8)

    #5. Silencios (antes que las notas: si no, un zigzag parece una negra)
    silencios, etiquetas_silencio = [], set()
    for i in range(1, num):
        x, y, w, h, _ = map(int, stats[i])
        if w < 0.3 * d or h < 0.2 * d:
            continue
        recorte = (etiquetas[y:y+h, x:x+w] == i).astype(np.uint8) * 255
        lineas = pentagramas[pentagrama_mas_cercano(y + h / 2, pentagramas)]
        tipo = clasificar_silencio(recorte, x, y, w, h, lineas, d)
        if tipo:
            silencios.append({"etiqueta": i, "x": x, "y": y, "w": w, "h": h,
                              "cx": x + w // 2, "cy": y + h // 2, "tipo": tipo,
                              "grupo_id": None, "acorde_id": None, "recorte": recorte})
            etiquetas_silencio.add(i)

    #Candidatas a nota (por tamaño)
    candidatas = []
    for i in range(1, num):
        if i in etiquetas_silencio:
            continue
        x, y, w, h, area = map(int, stats[i])
        normal = (0.65 * d <= w <= 2.3 * d and 1.8 * d <= h <= 4.8 * d
                  and 0.1 * d**2 <= area <= 3.0 * d**2)
        posible_acorde = (0.65 * d <= w <= 2.2 * d and 1.8 * d <= h <= 9.0 * d
                          and 0.1 * d**2 <= area <= 7.0 * d**2)
        if normal or posible_acorde:
            candidatas.append({"etiqueta": i, "x": x, "y": y, "w": w, "h": h, "normal": normal})

    #6-7
    grupos = detectar_grupos(num, etiquetas, stats, pentagramas, d)
    notas = detectar_notas(candidatas, etiquetas, d)
    for g in grupos:
        for cx, cy in g["cabezas"]:
            notas.append({"etiqueta": g["etiqueta"], "x": g["x"], "y": g["y"],
                          "w": g["w"], "h": g["h"], "cx": cx, "cy": cy, "tipo": g["tipo"],
                          "grupo_id": g["etiqueta"], "acorde_id": None, "recorte": g["recorte"]})
    notas.extend(silencios)

    #8. Puntillos
    for n in notas:
        n["puntillo"] = False
    usadas = {n["etiqueta"] for n in notas}
    puntos = detectar_puntillos(num, etiquetas, stats, notas, usadas, d)

    #9. Pentagrama, orden y altura
    for n in notas:
        n["pentagrama"] = pentagrama_mas_cercano(n["cy"], pentagramas) + 1
    notas.sort(key=lambda n: (n["pentagrama"], n["cx"]))
    for n in notas:
        n["altura"] = "-" if n["tipo"].startswith("silencio") else \
            calcular_altura(n["cy"], pentagramas[n["pentagrama"] - 1])

    #Imágenes para el Inspector
    img_lineas = cv.cvtColor(imagen, cv.COLOR_GRAY2BGR)
    colores = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 200, 255)]
    for k, p in enumerate(pentagramas):
        for yl in p:
            cv.line(img_lineas, (0, yl), (imagen.shape[1] - 1, yl), colores[k % 4], 2)

    return {
        "notas": notas,
        "pentagramas": pentagramas,
        "dist_media": d,
        "grosor_linea": grosor_linea,
        "puntillos": puntos,
        "imagenes": {
            "original": imagen,
            "binaria": binaria,
            "lineas": img_lineas,
            "mascara_borrado": mascara_borrado,
            "sin_lineas": sin_lineas,
            "restaurada": restaurada,
        },
    }


def dibujar_resultado(imagen, notas, dist_media):
    """Cajas verdes, centros rojos y etiqueta de cada nota."""
    if imagen.ndim == 2:
        imagen = cv.cvtColor(imagen, cv.COLOR_GRAY2BGR)
    out = imagen.copy()
    dibujadas = set()
    for i, n in enumerate(notas, 1):
        x, y, w, h = n["x"], n["y"], n["w"], n["h"]
        if n["etiqueta"] not in dibujadas:
            cv.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)
            dibujadas.add(n["etiqueta"])
        cv.circle(out, (n["cx"], n["cy"]), 5, (0, 0, 255), -1)
        texto = f"{i}. {n['altura']} ({n['tipo'][0].upper()}{'.' if n.get('puntillo') else ''})"
        if n["acorde_id"] is not None:
            pos = (n["cx"] + int(dist_media), n["cy"] + 5)
        elif n["grupo_id"]:
            pos = (n["cx"] - 22, y - 12)
        else:
            pos = (x - 10, y - 12)
        cv.putText(out, texto, pos, cv.FONT_HERSHEY_SIMPLEX, 0.46, (255, 0, 0), 2)
    return out