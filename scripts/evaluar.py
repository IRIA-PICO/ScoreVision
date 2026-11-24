"""
Evalúa scorevision_core contra el ground truth del dataset.

Uso:
    python evaluar.py                      (usa ../datasets/MiniDataset_7 junto al script)
    python evaluar.py "ruta/al/dataset"
"""
import csv
import sys
from pathlib import Path

import cv2 as cv

from scorevision_core import analizar_partitura

CARPETA_POR_DEFECTO = Path(__file__).resolve().parent.parent / "datasets" / "MiniDataset_7"
dataset = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else CARPETA_POR_DEFECTO
imagenes = sorted(dataset.glob("*.png"))
if not imagenes:
    print(f"No encuentro imágenes PNG en:\n  {dataset}")
    print("Pásale la carpeta del dataset, por ejemplo:")
    print('  python evaluar.py "C:/ruta/a/ScoreVision/datasets/MiniDataset_7"')
    sys.exit(1)
print(f"Evaluando {len(imagenes)} imágenes de {dataset}\n")
tot = dict(notas_ok=0, notas=0, falsas=0, sil_ok=0, sil=0, sil_falsos=0, punt_ok=0, punt=0)

for png in imagenes:
    imagen = cv.imread(str(png), cv.IMREAD_GRAYSCALE)
    try:
        res = analizar_partitura(imagen)
    except Exception as e:
        print(f"{png.stem:42s} ERROR: {e}")
        continue
    det, d = res["notas"], res["dist_media"]
    gt = list(csv.DictReader(open(png.with_suffix(".csv"), encoding="utf-8")))

    es_sil = lambda n: n["tipo"].startswith("silencio")
    gt_n = [r for r in gt if r["clase"] == "nota"]
    gt_s = [r for r in gt if r["clase"] == "silencio"]
    det_n = [n for n in det if not es_sil(n)]
    det_s = [n for n in det if es_sil(n)]
    cerca = lambda n, r, tx, ty: (abs(n["cx"] - int(r["x_cabeza"])) < tx
                                  and abs(n["cy"] - int(r["y_cabeza"])) < ty)

    def pareja(r):
        """La nota detectada que corresponde a una fila del ground truth."""
        for n in det_n:
            if cerca(n, r, 0.4 * d, 0.4 * d):
                return n
        return None

    notas_ok = sum(1 for r in gt_n if (p := pareja(r)) and p["altura"] == r["altura"] and p["tipo"] == r["tipo"])
    falsas = sum(not any(cerca(n, r, 0.4 * d, 0.4 * d) for r in gt_n) for n in det_n)
    sil_ok = sum(any(cerca(n, r, 0.8 * d, 2 * d) and n["tipo"] == r["tipo"] for n in det_s) for r in gt_s)
    sil_falsos = sum(not any(cerca(n, r, 0.8 * d, 2 * d) for r in gt_s) for n in det_s)
    # Puntillos: de las notas encontradas, ¿coincide si llevan puntillo o no?
    emparejadas = [(r, pareja(r)) for r in gt_n if pareja(r)]
    punt = sum(1 for r, _ in emparejadas if r["puntillo"] == "1")
    punt_ok = sum(1 for r, p in emparejadas if r["puntillo"] == "1" and p["puntillo"])
    punt_falsos = sum(1 for r, p in emparejadas if r["puntillo"] == "0" and p["puntillo"])

    for k, v in dict(notas_ok=notas_ok, notas=len(gt_n), falsas=falsas, sil_ok=sil_ok,
                     sil=len(gt_s), sil_falsos=sil_falsos, punt_ok=punt_ok, punt=punt).items():
        tot[k] += v
    extra = f"   puntillos {punt_ok}/{punt}" + (f" (+{punt_falsos} de más)" if punt_falsos else "") if punt or punt_falsos else ""
    print(f"{png.stem:42s} notas {notas_ok:3d}/{len(gt_n):3d} (falsas {falsas})"
          f"   silencios {sil_ok}/{len(gt_s)} (falsos {sil_falsos}){extra}")

print("-" * 100)
print(f"{'TOTAL':42s} notas {tot['notas_ok']:3d}/{tot['notas']:3d} (falsas {tot['falsas']})"
      f"   silencios {tot['sil_ok']}/{tot['sil']} (falsos {tot['sil_falsos']})"
      f"   puntillos {tot['punt_ok']}/{tot['punt']}")
print("Una nota cuenta como bien si coinciden posición, altura y figura.")
