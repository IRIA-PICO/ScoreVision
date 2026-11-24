# ScoreVision

Lee partituras con visión por computador (OpenCV) y las hace sonar.

```
ScoreVision/
├── scripts/
│   ├── scorevision_core.py    ← VISIÓN: analizar_partitura(imagen) -> notas + imágenes de cada paso
│   ├── scorevision_audio.py   ← tiempos (pulsos), frecuencias, sintetizador, WAV
│   ├── scorevision_app.py     ← app de escritorio (ventanas, clic, P/S/ESC) — Windows
│   ├── exportar_web.py        ← genera web/partituras/ (JSON + imágenes) para la web
│   ├── evaluar.py             ← compara con el ground truth del dataset
│   └── generar_dataset.py     ← crea las partituras sintéticas + CSV
├── datasets/MiniDataset_7/    ← 22 partituras + ground truth
└── web/partituras/            ← lo que leerá la web (8 canciones)
```

## Comandos (desde `scripts/`)

```bash
python evaluar.py ../datasets/MiniDataset_7
python scorevision_app.py "../datasets/MiniDataset_7/17-Bella ciao.png"
python exportar_web.py ../datasets/MiniDataset_7 ../web
python generar_dataset.py          # regenera el dataset
```

## Formato de `partitura.json`

Cada nota lleva: `altura` (SOL4), `midi` (67), `tipo`, `puntillo`, `inicio` y `pulsos`
(en pulsos: la web los convierte a segundos con el BPM), `cx`/`cy` (centro de la cabeza),
`caja` [x, y, w, h], `pentagrama`, `acorde` y `grupo`. Las notas de un acorde comparten `inicio`.

## Resultados actuales (`evaluar.py`)

- Canciones (Bella Ciao, Twinkle, Jingle Bells, Himno de la alegría, Merry Christmas,
  Frère Jacques, Cumpleaños): **100 %** de notas, silencios y puntillos.
- Total del dataset: 558/662 notas, 13/13 silencios, 19/20 puntillos.
- Pendiente: grupos mixtos (corchea con puntillo + semicorchea unidas),
  semicorcheas sueltas con plica abajo, sostenidos, redondas.
