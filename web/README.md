# ScoreVision · web

Web estática: no necesita servidor ni instalar nada.

## Abrirla en tu ordenador
Doble clic en `index.html`. Funciona en Chrome, Edge, Firefox y Safari.
(La primera vez que toques algo, el navegador activa el sonido.)

## Actualizar las canciones
Cada vez que cambies el código de visión o el dataset, desde `scripts/`:
```
python exportar_web.py
```
Eso regenera `web/partituras/` (JSON, imágenes y `datos.js`).

## Publicarla gratis en GitHub Pages
1. Sube la carpeta `ScoreVision` a un repositorio de GitHub.
2. En el repo: Settings > Pages > Source: "Deploy from a branch",
   rama `main`, carpeta `/ (root)`.
3. Tu web queda en `https://TU_USUARIO.github.io/NOMBRE_REPO/web/`
   (ábrela en el móvil: el modo Tocar y Flow van con el dedo).

## Archivos
- `index.html` — estructura
- `css/estilos.css` — diseño (colores por nota, halo, piano, móvil)
- `js/audio.js` — sintetizador Web Audio (mismo timbre que la versión Python)
- `js/app.js` — karaoke, modos Tocar / Flow / Inspector, piano, animaciones
- `partituras/` — generado por `exportar_web.py`
