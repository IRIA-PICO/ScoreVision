"""
ScoreVision · EXPORTAR PARA LA WEB
==================================
Analiza cada partitura con scorevision_core y deja en web/partituras/:

    canciones.json              <- índice para el selector de canciones
    <id>/partitura.json         <- notas, tiempos y cajas (lo que usa la web)
    <id>/original.png           <- la partitura
    <id>/paso_*.png             <- cada paso del pipeline (para el Inspector)

Uso:
    python exportar_web.py                 (usa ../datasets/MiniDataset_7 y ../web junto al script)
    python exportar_web.py "ruta/al/dataset" "ruta/a/web"
"""
import json
import sys
from pathlib import Path

import cv2 as cv
import numpy as np

from scorevision_core import analizar_partitura, dibujar_resultado
from scorevision_audio import altura_a_midi, calcular_tiempos

# Qué imágenes del dataset van a la web, con su ficha
CANCIONES = [
    ("17-Bella ciao", "bella-ciao", "Bella Ciao", "Popular italiana", 120),
    ("18-Twinkle twinkle little star", "twinkle", "Twinkle Twinkle Little Star", "Popular", 100),
    ("19-Jingle bells", "jingle-bells", "Jingle Bells", "J. Pierpont, 1857", 140),
    ("20-Himno de la alegria", "himno-alegria", "Himno de la alegría", "L. van Beethoven", 110),
    ("21-We wish you a merry christmas", "merry-christmas", "We Wish You a Merry Christmas", "Popular inglesa", 130),
    ("22-Frere Jacques", "frere-jacques", "Frère Jacques", "Popular francesa", 110),
    ("09-Cumpleanos feliz", "cumpleanos", "Cumpleaños feliz", "M. y P. Hill", 100),
    ("16-Acordes y melodia", "cumpleanos-acordes", "Cumpleaños con acordes", "Versión con acordes", 100),
]

PASOS = [
    ("lineas", "Pentagramas detectados", "Proyección horizontal: las filas con mucha tinta son líneas."),
    ("mascara_borrado", "Qué se borra", "Solo píxeles horizontales con la altura de una línea."),
    ("restaurada", "Sin pentagrama", "Quedan los símbolos sueltos, listos para separarlos."),
    ("resultado", "Notas reconocidas", "Cabezas, figuras, acordes, silencios y puntillos."),
]


def a_png_blanco(img):
    """Las imágenes binarias van en negro sobre blanco (se ven mejor en la web)."""
    if img.ndim == 2 and img.max() <= 255 and (img == 0).mean() > 0.5:
        return 255 - img
    return img


def exportar(png, carpeta, id_, titulo, autor, bpm):
    imagen = cv.imread(str(png), cv.IMREAD_GRAYSCALE)
    res = analizar_partitura(imagen)
    notas, d = res["notas"], res["dist_media"]
    total = calcular_tiempos(notas)

    carpeta.mkdir(parents=True, exist_ok=True)
    cv.imwrite(str(carpeta / "original.png"), imagen)
    imagenes = dict(res["imagenes"])
    imagenes["resultado"] = dibujar_resultado(imagen, notas, d)
    pasos = []
    for clave, nombre, explicacion in PASOS:
        archivo = f"paso_{clave}.png"
        cv.imwrite(str(carpeta / archivo), a_png_blanco(imagenes[clave]))
        pasos.append({"archivo": archivo, "nombre": nombre, "explicacion": explicacion})

    # Marco para calibrar la cámara: los extremos de los pentagramas
    # (arriba-izq, arriba-dcha, abajo-dcha, abajo-izq). Son fáciles de ver en papel.
    binaria = res["imagenes"]["binaria"]
    def extremos(y):
        cols = np.nonzero(binaria[y])[0]
        return int(cols.min()), int(cols.max())
    y_arriba = res["pentagramas"][0][0]
    y_abajo = res["pentagramas"][-1][-1]
    xa0, xa1 = extremos(y_arriba)
    xb0, xb1 = extremos(y_abajo)
    marco = [[xa0, y_arriba], [xa1, y_arriba], [xb1, y_abajo], [xb0, y_abajo]]

    datos = {
        "id": id_, "titulo": titulo, "autor": autor, "bpm": bpm,
        "marco": marco,
        "imagen": "original.png",
        "ancho": int(imagen.shape[1]), "alto": int(imagen.shape[0]),
        "dist_media": float(d),
        "pentagramas": [[int(y) for y in p] for p in res["pentagramas"]],
        "duracion_pulsos": float(total),
        "pasos": pasos,
        "notas": [{
            "id": i,
            "tipo": n["tipo"],
            "silencio": n["tipo"].startswith("silencio"),
            "altura": n["altura"],
            "midi": altura_a_midi(n["altura"]),
            "puntillo": bool(n.get("puntillo")),
            "inicio": float(n["inicio"]),          # en pulsos
            "pulsos": float(n["pulsos"]),
            "cx": int(n["cx"]), "cy": int(n["cy"]),
            "caja": [int(n["x"]), int(n["y"]), int(n["w"]), int(n["h"])],
            "pentagrama": int(n["pentagrama"]),
            "acorde": None if n["acorde_id"] is None else int(n["acorde_id"]),
            "grupo": None if n["grupo_id"] is None else int(n["grupo_id"]),
        } for i, n in enumerate(notas)],
    }
    (carpeta / "partitura.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return datos


def main():
    raiz = Path(__file__).resolve().parent.parent          # carpeta ScoreVision/
    dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else raiz / "datasets" / "MiniDataset_7"
    web = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else raiz / "web"
    if not any(dataset.glob("*.png")):
        print(f"No encuentro imágenes PNG en:\n  {dataset}")
        sys.exit(1)
    salida = web / "partituras"
    indice = []
    for nombre, id_, titulo, autor, bpm in CANCIONES:
        png = dataset / f"{nombre}.png"
        if not png.exists():
            print("No encuentro", png)
            continue
        datos = exportar(png, salida / id_, id_, titulo, autor, bpm)
        n_notas = sum(not n["silencio"] for n in datos["notas"])
        indice.append({"id": id_, "titulo": titulo, "autor": autor, "bpm": bpm,
                       "notas": n_notas, "pentagramas": len(datos["pentagramas"]),
                       "carpeta": f"partituras/{id_}/"})
        print(f"{titulo:32s} {n_notas:3d} notas  {datos['duracion_pulsos']:5.1f} pulsos")
    (salida / "canciones.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")

    # datos.js: lo mismo pero como JavaScript. Así la web funciona también
    # abriendo index.html con doble clic (file://), donde fetch() de JSON está bloqueado.
    todas = []
    for c in indice:
        datos = json.loads((salida / c["id"] / "partitura.json").read_text(encoding="utf-8"))
        todas.append({**datos, "carpeta": c["carpeta"]})
    (salida / "datos.js").write_text(
        "// Generado por exportar_web.py — no editar a mano\n"
        "window.SCOREVISION = " + json.dumps({"canciones": todas}, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    print("Listo:", salida.resolve())


if __name__ == "__main__":
    main()
