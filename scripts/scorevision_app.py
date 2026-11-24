"""
ScoreVision -> APP DE ESCRITORIO
=========================================
Lo de siempre: muestra los pasos, guarda resultados y abre la partitura
interactiva (clic = suena la nota, P = toda la canción, S = parar, ESC = salir).

"""
import csv
import sys
import tempfile
from pathlib import Path

import cv2 as cv
import numpy as np
import winsound

from scorevision_core import analizar_partitura, dibujar_resultado
from scorevision_audio import calcular_frecuencia, calcular_tiempos, guardar_wav, renderizar

BPM = 100
MOSTRAR_PASOS = True

directorio = Path(__file__).resolve().parent
ruta_imagen = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    directorio.parent / "datasets" / "MiniDataset_7" / "21-We wish you a merry christmas.png"
carpeta_resultados = directorio / "resultados"
carpeta_resultados.mkdir(exist_ok=True)


def escala_para(img):
    return min(1.0, 1100 / img.shape[1], 650 / img.shape[0])


def mostrar_paso(titulo, img):
    e = escala_para(img)
    cv.imshow(titulo, cv.resize(img, None, fx=e, fy=e, interpolation=cv.INTER_AREA))
    cv.waitKey(0)
    cv.destroyAllWindows()


#análisis
imagen = cv.imread(str(ruta_imagen), cv.IMREAD_GRAYSCALE)
if imagen is None:
    raise FileNotFoundError(f"No se encuentra la imagen en: {ruta_imagen}")

res = analizar_partitura(imagen)
notas, d = res["notas"], res["dist_media"]
calcular_tiempos(notas)
resultado = dibujar_resultado(imagen, notas, d)

print(f"Pentagramas: {len(res['pentagramas'])}  |  separación entre líneas: {d:.1f} px")
for i, n in enumerate(notas, 1):
    extra = " ·" if n["puntillo"] else ""
    extra += f" (acorde {n['acorde_id']})" if n["acorde_id"] is not None else ""
    print(f"{i:3d}. P{n['pentagrama']} {n['altura']:>5s} {n['tipo']}{extra}")

pasos = [("1. Original", imagen), ("2. Pentagramas", res["imagenes"]["lineas"]),
         ("3. Mascara de borrado", res["imagenes"]["mascara_borrado"]),
         ("4. Sin lineas", res["imagenes"]["restaurada"]), ("5. Notas", resultado)]
for k, (titulo, img) in enumerate(pasos):
    cv.imwrite(str(carpeta_resultados / f"{k:02d}_{titulo[3:].replace(' ', '_')}.png"), img)
    if MOSTRAR_PASOS:
        mostrar_paso(titulo, img)

with open(carpeta_resultados / "posiciones.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["numero", "pentagrama", "tipo", "altura", "puntillo", "inicio_pulsos",
                "duracion_pulsos", "x_cabeza", "y_cabeza", "grupo_id", "acorde_id"])
    for i, n in enumerate(notas, 1):
        w.writerow([i, n["pentagrama"], n["tipo"], n["altura"], int(n["puntillo"]), n["inicio"],
                    n["pulsos"], n["cx"], n["cy"], n["grupo_id"] or "",
                    "" if n["acorde_id"] is None else n["acorde_id"]])

audio_cancion = renderizar(notas, BPM)
guardar_wav(audio_cancion, carpeta_resultados / "cancion.wav")
print("Resultados en:", carpeta_resultados)

#sonido
_turno = [0]


def reproducir(audio):
    winsound.PlaySound(None, 0)
    _turno[0] ^= 1
    ruta = Path(tempfile.gettempdir()) / f"scorevision_{_turno[0]}.wav"
    guardar_wav(audio, ruta)
    winsound.PlaySound(str(ruta), winsound.SND_FILENAME | winsound.SND_ASYNC)


def tocar_nota(nota):
    if nota["tipo"].startswith("silencio"):
        print("Silencio:", nota["tipo"])
        return
    grupo = [nota]
    if nota["acorde_id"] is not None:
        grupo = [n for n in notas if n["acorde_id"] == nota["acorde_id"]]
    print("Tocando:", ", ".join(f"{n['altura']} ({calcular_frecuencia(n['altura']):.0f} Hz)" for n in grupo))
    copia = [dict(n) for n in grupo]
    reproducir(renderizar(copia, BPM))


#ventana
escala = escala_para(resultado)
vista = cv.resize(resultado, None, fx=escala, fy=escala, interpolation=cv.INTER_AREA)


def al_hacer_click(evento, x, y, flags, param):
    if evento != cv.EVENT_LBUTTONDOWN:
        return
    xo, yo = x / escala, y / escala
    candidatas = [n for n in notas
                  if n["x"] <= xo <= n["x"] + n["w"] and n["y"] <= yo <= n["y"] + n["h"]]
    if candidatas:
        tocar_nota(min(candidatas, key=lambda n: (n["cx"] - xo) ** 2 + (n["cy"] - yo) ** 2))


ventana = "ScoreVision - Partitura interactiva"
cv.namedWindow(ventana, cv.WINDOW_AUTOSIZE)
cv.setMouseCallback(ventana, al_hacer_click)
print("Clic = nota  |  P = toda la partitura  |  S = parar  |  ESC = salir")

while True:
    cv.imshow(ventana, vista)
    tecla = cv.waitKey(25) & 0xFF
    if tecla == ord("p"):
        reproducir(audio_cancion)
    elif tecla == ord("s"):
        winsound.PlaySound(None, 0)
    elif tecla == 27:
        break

winsound.PlaySound(None, 0)
cv.destroyAllWindows()
