/* ScoreVision — la web
   Lee window.SCOREVISION (generado por exportar_web.py) y dibuja encima
   de cada partitura una capa viva: notas de color, cursor, ondas y notas
   que salen volando. Modos: Escuchar (karaoke), Tocar (arpa con el dedo),
   Flow (tú marcas el ritmo) e Inspector (cómo la ha leído OpenCV). */
"use strict";

(() => {
  // ------------------------------------------------------------ constantes
  const COLORES = {
    DO: "#ff3d6e", RE: "#ff8a2b", MI: "#ffd23f", FA: "#3ddc84",
    SOL: "#22d3ee", LA: "#5b7cfa", SI: "#b45cf5",
  };
  const FIGURAS = {
    negra: "negra", blanca: "blanca", corchea: "corchea", semicorchea: "semicorchea",
    silencio_negra: "silencio de negra", silencio_blanca: "silencio de blanca",
    silencio_corchea: "silencio de corchea", silencio_redonda: "silencio de redonda",
  };
  const AYUDAS = {
    escuchar: "Pulsa play y sigue la luz. Toca una nota para empezar desde ahí.",
    tocar: "Pasa el dedo por las notas: cada una suena al tocarla.",
    flow: "Toca el papel al ritmo que quieras y la canción avanza contigo. También vale la barra espaciadora.",
    inspector: "Así ha leído la partitura OpenCV, paso a paso. Toca una nota para ver su ficha.",
    camara: "Imprime la partitura o ábrela en otra pantalla. Enciende la cámara, marca las 4 esquinas de los pentagramas y señala las notas con el índice.",
  };
  const SIMBOLOS = ["♪", "♫", "♬", "♩"];
  const MIDI_MIN = 55;   // SOL3
  const MIDI_MAX = 86;   // RE6
  const REDUCIR_MOVIMIENTO = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const $ = (s) => document.querySelector(s);
  const el = {
    canciones: $("#canciones"), img: $("#partitura"), capa: $("#capa"), lienzo: $("#lienzo"),
    scroll: $("#scroll"), ayuda: $("#ayuda"), play: $("#play"), stop: $("#stop"),
    progreso: $("#progreso"), relleno: $("#progreso-relleno"), tempo: $("#tempo"),
    tempoValor: $("#tempo-valor"), nombre: $("#ahora-nombre"), octava: $("#ahora-octava"),
    detalle: $("#ahora-detalle"), notaGrande: document.querySelector(".ahora-nota"),
    contador: $("#contador"), inspector: $("#inspector"), pasos: $("#pasos"),
    pasoExplicacion: $("#paso-explicacion"), ficha: $("#ficha"), capaPaso: $("#capa-paso"),
    corte: $("#corte"), comparador: $("#comparador"), deslizador: $("#deslizador-paso"),
    piano: $("#piano"), aviso: $("#aviso"), fondo: $("#fondo"),
    instrumento: $("#instrumento"), camara: $("#camara"), video: $("#video"),
    capaCamara: $("#capa-camara"), camaraInicio: $("#camara-inicio"),
    encenderCamara: $("#encender-camara"), camaraEstado: $("#camara-estado"),
    recalibrar: $("#recalibrar"),
  };
  const ctx2d = el.capa.getContext("2d");

  // ------------------------------------------------------------ estado
  const estado = {
    cancion: null,
    notas: [],
    eventos: [],          // notas agrupadas por instante (un acorde = un evento)
    modo: "escuchar",
    bpm: 100,
    escala: 1,            // píxeles en pantalla / píxeles de la imagen
    reproduccion: null,   // { inicioReloj, desdePulso, indice }
    posicion: 0,          // pulso donde está el cursor cuando no suena
    eventoActual: -1,
    flowIndice: 0,
    brillo: new Map(),    // id de nota -> 0..1
    ondas: [],
    particulas: [],
    seleccion: null,
    ultimaTocada: null,
    pasoActivo: 0,
    usuarioScroll: 0,
  };

  // ------------------------------------------------------------ utilidades
  const nombreDe = (altura) => (/^(DO|RE|MI|FA|SOL|LA|SI)/.exec(altura) || [])[1] || null;
  const colorDe = (nota) => COLORES[nombreDe(nota.altura)] || "#a9a3d6";
  const segPorPulso = () => 60 / estado.bpm;
  const pulsoActual = () => {
    const r = estado.reproduccion;
    return r ? r.desdePulso + (Sinte.reloj - r.inicioReloj) / segPorPulso() : estado.posicion;
  };

  function avisar(texto, ms = 2400) {
    el.aviso.textContent = texto;
    el.aviso.hidden = false;
    clearTimeout(avisar.t);
    avisar.t = setTimeout(() => { el.aviso.hidden = true; }, ms);
  }

  function agruparEventos(notas) {
    const eventos = [];
    for (const n of notas) {
      const ultimo = eventos[eventos.length - 1];
      if (ultimo && Math.abs(ultimo.inicio - n.inicio) < 1e-6) {
        ultimo.notas.push(n);
        ultimo.pulsos = Math.max(ultimo.pulsos, n.pulsos);
      } else {
        eventos.push({ inicio: n.inicio, pulsos: n.pulsos, notas: [n] });
      }
    }
    eventos.forEach((e, i) => {
      e.indice = i;
      e.silencio = e.notas.every((n) => n.silencio);
      e.cx = Math.max(...e.notas.map((n) => n.cx));
      e.pentagrama = e.notas[0].pentagrama;
    });
    return eventos;
  }

  // ------------------------------------------------------------ canciones
  function dibujarContorno(cancion) {
    // un punto por nota: altura = tono, color = nombre de la nota
    const notas = cancion.notas.filter((n) => !n.silencio);
    const muestra = notas.slice(0, 22);
    const midis = muestra.map((n) => n.midi);
    const min = Math.min(...midis), max = Math.max(...midis);
    const ancho = 172, alto = 38, r = 3.2;
    const paso = (ancho - 2 * r) / Math.max(1, muestra.length - 1);
    const puntos = muestra.map((n, i) => {
      const y = max === min ? alto / 2 : alto - r - ((n.midi - min) / (max - min)) * (alto - 2 * r);
      return `<circle cx="${(r + i * paso).toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" fill="${colorDe(n)}"/>`;
    }).join("");
    return `<svg class="contorno" viewBox="0 0 ${ancho} ${alto}" preserveAspectRatio="none" aria-hidden="true">${puntos}</svg>`;
  }

  function construirTarjetas() {
    el.canciones.innerHTML = "";
    window.SCOREVISION.canciones.forEach((c, i) => {
      const b = document.createElement("button");
      b.className = "tarjeta";
      b.dataset.indice = i;
      const notas = c.notas.filter((n) => !n.silencio).length;
      b.innerHTML = `${dibujarContorno(c)}
        <span class="tarjeta-titulo">${c.titulo}</span>
        <span class="tarjeta-autor">${c.autor}, ${notas} notas</span>`;
      const primera = c.notas.find((n) => !n.silencio);
      if (primera) b.style.setProperty("--color-tarjeta", colorDe(primera));
      b.addEventListener("click", () => cargarCancion(i));
      el.canciones.appendChild(b);
    });
  }

  function cargarCancion(i) {
    detener();
    const c = window.SCOREVISION.canciones[i];
    estado.cancion = c;
    estado.notas = c.notas;
    estado.eventos = agruparEventos(c.notas);
    estado.bpm = c.bpm;
    estado.posicion = 0;
    estado.eventoActual = -1;
    estado.flowIndice = 0;
    estado.brillo.clear();
    estado.seleccion = null;
    el.tempo.value = c.bpm;
    el.tempoValor.textContent = c.bpm;
    document.querySelectorAll(".tarjeta").forEach((t) =>
      t.classList.toggle("activa", Number(t.dataset.indice) === i));
    el.img.src = c.carpeta + c.imagen;
    el.scroll.scrollTop = 0;
    mostrarAhora(null, c.titulo);
    construirPasos();
    mostrarFicha(null);
    actualizarContador();
    try { history.replaceState(null, "", "#" + c.id); } catch (e) { /* file:// */ }
    if (cam.flujo) empezarCalibracion();     // otra hoja: hay que marcar sus esquinas
  }

  // ------------------------------------------------------------ tamaño del lienzo
  function ajustarLienzo() {
    if (!estado.cancion || !el.img.clientWidth) return;
    const dpr = window.devicePixelRatio || 1;
    const w = el.img.clientWidth, h = el.img.clientHeight;
    el.capa.width = Math.round(w * dpr);
    el.capa.height = Math.round(h * dpr);
    ctx2d.setTransform(dpr, 0, 0, dpr, 0, 0);
    estado.escala = w / estado.cancion.ancho;
  }
  el.img.addEventListener("load", ajustarLienzo);
  new ResizeObserver(ajustarLienzo).observe(el.img);

  // ------------------------------------------------------------ panel "ahora suena"
  function mostrarAhora(nota, texto) {
    el.notaGrande.classList.toggle("vacia", !nota);
    if (!nota) {
      el.nombre.textContent = "♪";
      el.octava.textContent = "";
      el.detalle.textContent = texto || "";
      el.notaGrande.style.removeProperty("--color-ahora");
      return;
    }
    const nombre = nombreDe(nota.altura);
    el.nombre.textContent = nombre;
    el.octava.textContent = nota.altura.slice(nombre.length);
    el.notaGrande.style.setProperty("--color-ahora", colorDe(nota));
    el.detalle.textContent = texto || (FIGURAS[nota.tipo] + (nota.puntillo ? " con puntillo" : ""));
    el.notaGrande.classList.remove("golpe");
    void el.notaGrande.offsetWidth;          // reinicia la animación
    el.notaGrande.classList.add("golpe");
  }

  function teñirSala(color) {
    document.documentElement.style.setProperty("--aura", color);
  }

  // ------------------------------------------------------------ efectos
  function encenderEvento(evento, duracionSeg) {
    const suenan = evento.notas.filter((n) => !n.silencio);
    if (!suenan.length) return;
    suenan.forEach((n) => {
      estado.brillo.set(n.id, 1);
      estado.ondas.push({ x: n.cx, y: n.cy, color: colorDe(n), t: performance.now() });
      if (!REDUCIR_MOVIMIENTO) {
        for (let k = 0; k < 3; k++) {
          estado.particulas.push({
            x: n.cx, y: n.cy - 6,
            vx: (Math.random() - 0.5) * 1.6, vy: -1.2 - Math.random() * 1.4,
            giro: (Math.random() - 0.5) * 0.06, angulo: (Math.random() - 0.5) * 0.6,
            simbolo: SIMBOLOS[(Math.random() * SIMBOLOS.length) | 0],
            color: colorDe(n), vida: 1, tam: 16 + Math.random() * 12,
          });
        }
      }
      encenderTecla(n.midi, colorDe(n), duracionSeg);
    });
    const principal = suenan.reduce((a, b) => (b.midi > a.midi ? b : a));   // la más aguda = melodía
    mostrarAhora(principal, suenan.length > 1
      ? "acorde: " + suenan.map((n) => n.altura).join(", ")
      : null);
    teñirSala(colorDe(principal));
  }

  function sonarEvento(evento, cuando, duracionSeg, fuerza = 1) {
    evento.notas.forEach((n) => {
      if (!n.silencio) Sinte.tocar(n.midi, cuando, duracionSeg, fuerza);
    });
  }

  function celebrar() {
    if (REDUCIR_MOVIMIENTO || !estado.cancion) return;
    const c = estado.cancion;
    const colores = Object.values(COLORES);
    for (let k = 0; k < 46; k++) {
      const ang = Math.random() * Math.PI * 2, v = 2 + Math.random() * 4;
      estado.particulas.push({
        x: c.ancho / 2, y: Math.min(c.alto / 2, el.scroll.scrollTop / estado.escala + 200),
        vx: Math.cos(ang) * v, vy: Math.sin(ang) * v - 2, giro: (Math.random() - 0.5) * 0.1,
        angulo: 0, simbolo: SIMBOLOS[k % 4], color: colores[k % 7], vida: 1.4, tam: 18 + Math.random() * 16,
      });
    }
  }

  // ------------------------------------------------------------ modo Escuchar
  function reproducir() {
    if (!estado.cancion) return;
    Sinte.iniciar();
    const spp = segPorPulso();
    if (estado.posicion >= estado.cancion.duracion_pulsos - 0.01) estado.posicion = 0;
    const desde = estado.posicion;
    const inicioReloj = Sinte.reloj + 0.08;
    let indice = estado.eventos.findIndex((e) => e.inicio >= desde - 1e-6);
    if (indice < 0) indice = estado.eventos.length;
    for (const e of estado.eventos.slice(indice)) {
      sonarEvento(e, inicioReloj + (e.inicio - desde) * spp, e.pulsos * spp);
    }
    estado.reproduccion = { inicioReloj, desdePulso: desde, indice };
    document.body.classList.add("sonando");
    el.play.setAttribute("aria-label", "Pausa");
  }

  function pausar() {
    if (!estado.reproduccion) return;
    estado.posicion = Math.min(pulsoActual(), estado.cancion.duracion_pulsos);
    estado.reproduccion = null;
    Sinte.callar();
    document.body.classList.remove("sonando");
    el.play.setAttribute("aria-label", "Reproducir");
  }

  function detener() {
    pausar();
    estado.posicion = 0;
    estado.eventoActual = -1;
  }

  function irAPulso(pulso) {
    const sonaba = !!estado.reproduccion;
    pausar();
    estado.posicion = Math.max(0, pulso);
    estado.eventoActual = -1;
    if (sonaba) reproducir();
  }

  function avanzarKaraoke() {
    const r = estado.reproduccion;
    if (!r) return;
    const p = pulsoActual();
    while (r.indice < estado.eventos.length && estado.eventos[r.indice].inicio <= p) {
      const e = estado.eventos[r.indice];
      estado.eventoActual = r.indice;
      encenderEvento(e, e.pulsos * segPorPulso());
      r.indice++;
    }
    if (p >= estado.cancion.duracion_pulsos + 0.35) {
      estado.reproduccion = null;
      document.body.classList.remove("sonando");
      estado.posicion = 0;
      estado.eventoActual = -1;
      mostrarAhora(null, "Fin. Pulsa play para volver a escucharla.");
      celebrar();
    }
  }

  // ------------------------------------------------------------ modo Tocar
  function notaEn(x, y, holgura = 1) {
    // x, y en píxeles de la imagen original. holgura > 1 = más fácil de acertar
    const d = estado.cancion.dist_media;
    let mejor = null, distMejor = Infinity;
    for (const n of estado.notas) {
      if (n.silencio && holgura > 1) continue;
      const dx = (x - n.cx) / (1.2 * d * holgura), dy = (y - n.cy) / (0.9 * d * holgura);
      const dist = dx * dx + dy * dy;
      if (dist < 1 && dist < distMejor) { mejor = n; distMejor = dist; }
    }
    if (!mejor) {   // ¿dentro de la caja de un silencio o de la figura?
      for (const n of estado.notas) {
        const [bx, by, bw, bh] = n.caja;
        if (x >= bx && x <= bx + bw && y >= by && y <= by + bh && n.grupo === null) return n;
      }
    }
    return mejor;
  }

  function eventoDe(nota) {
    return estado.eventos.find((e) => e.notas.includes(nota));
  }

  function tocarNota(nota) {
    if (!nota) return;
    const e = eventoDe(nota);
    const conjunto = nota.acorde !== null ? e : { notas: [nota] };
    if (nota.silencio) {
      mostrarAhora(null, FIGURAS[nota.tipo]);
      return;
    }
    Sinte.iniciar();
    sonarEvento(conjunto, null, 0.9);
    encenderEvento(conjunto, 0.9);
  }

  // ------------------------------------------------------------ modo Flow
  function flowSiguiente() {
    if (!estado.cancion) return;
    Sinte.iniciar();
    // los silencios se saltan solos: el ritmo lo pones tú
    while (estado.flowIndice < estado.eventos.length && estado.eventos[estado.flowIndice].silencio) {
      estado.flowIndice++;
    }
    if (estado.flowIndice >= estado.eventos.length) {
      celebrar();
      avisar("¡Canción completa! Toca otra vez para repetirla.");
      estado.flowIndice = 0;
      actualizarContador();
      return;
    }
    const e = estado.eventos[estado.flowIndice];
    Sinte.callar();
    const dur = Math.min(e.pulsos * segPorPulso(), 1.8);
    sonarEvento(e, null, dur);
    encenderEvento(e, dur);
    estado.eventoActual = estado.flowIndice;
    estado.flowIndice++;
    actualizarContador();
  }

  function actualizarContador() {
    const total = estado.eventos.filter((e) => !e.silencio).length;
    const hechos = estado.eventos.slice(0, estado.flowIndice).filter((e) => !e.silencio).length;
    el.contador.innerHTML = `<strong>${hechos}</strong> de ${total} notas tocadas`;
  }

  // ------------------------------------------------------------ modo Inspector
  function construirPasos() {
    const c = estado.cancion;
    const pasos = [{ archivo: null, nombre: "Original", explicacion: "La imagen tal cual entra en el programa." }]
      .concat(c.pasos);
    el.pasos.innerHTML = "";
    pasos.forEach((p, i) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.textContent = p.nombre;
      b.addEventListener("click", () => elegirPaso(i));
      li.appendChild(b);
      el.pasos.appendChild(li);
    });
    estado.pasosLista = pasos;
    elegirPaso(estado.modo === "inspector" ? Math.min(estado.pasoActivo, pasos.length - 1) : 0);
  }

  function elegirPaso(i) {
    estado.pasoActivo = i;
    const p = estado.pasosLista[i];
    [...el.pasos.querySelectorAll("button")].forEach((b, k) => b.classList.toggle("activo", k === i));
    el.pasoExplicacion.textContent = p.explicacion;
    const conCapa = estado.modo === "inspector" && p.archivo;
    el.capaPaso.hidden = !conCapa;
    el.corte.hidden = !conCapa;
    el.comparador.hidden = !conCapa;
    if (conCapa) el.capaPaso.src = estado.cancion.carpeta + p.archivo;
    aplicarCorte();
  }

  function aplicarCorte() {
    const v = Number(el.deslizador.value);
    el.capaPaso.style.clipPath = `inset(0 ${100 - v}% 0 0)`;
    el.corte.style.left = v + "%";
  }
  el.deslizador.addEventListener("input", aplicarCorte);

  function comoSeDetecto(n) {
    if (n.silencio) return "Componente dentro del pentagrama cuya forma (alto, ancho, relleno y posición) encaja con un silencio.";
    if (n.acorde !== null) return "Varias cabezas en una misma plica: cada una deja un pico en el perfil horizontal de tinta.";
    if (n.grupo !== null) return "Grupo unido por barras: las cabezas salen con una apertura elíptica y se cuentan las barras entre ellas.";
    if (n.tipo === "corchea" || n.tipo === "semicorchea") return "Nota suelta: se contaron los corchetes a la derecha de la plica.";
    if (n.tipo === "blanca") return "Cabeza hueca: poca tinta en el centro de la cabeza.";
    return "Cabeza llena con plica y sin corchetes.";
  }

  function mostrarFicha(n) {
    estado.seleccion = n;
    if (!n) {
      el.ficha.innerHTML = '<p class="ficha-vacia">Toca una nota de la partitura para ver su ficha.</p>';
      return;
    }
    const color = n.silencio ? "var(--texto)" : colorDe(n);
    const filas = [
      ["Figura", FIGURAS[n.tipo] + (n.puntillo ? " con puntillo" : "")],
      ["Empieza", `pulso ${n.inicio}`],
      ["Dura", `${n.pulsos} ${n.pulsos === 1 ? "pulso" : "pulsos"}`],
      ["Pentagrama", n.pentagrama],
      ["Cabeza", `x ${n.cx}, y ${n.cy} px`],
    ];
    if (n.acorde !== null) filas.push(["Acorde", eventoDe(n).notas.map((m) => m.altura).join(", ")]);
    el.ficha.innerHTML = `
      <h3 style="color:${color}">${n.silencio ? "Silencio" : n.altura}</h3>
      <dl>${filas.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join("")}</dl>
      <p class="como">${comoSeDetecto(n)}</p>`;
  }

  // ------------------------------------------------------------ cambio de modo
  function elegirModo(modo) {
    if (modo === estado.modo) return;
    pausar();
    Sinte.callar();
    estado.modo = modo;
    document.body.dataset.modo = modo;
    document.querySelectorAll(".modo").forEach((b) => {
      const activo = b.dataset.modo === modo;
      b.classList.toggle("activo", activo);
      b.setAttribute("aria-pressed", activo);
    });
    el.ayuda.textContent = AYUDAS[modo];
    el.inspector.hidden = modo !== "inspector";
    el.contador.hidden = modo !== "flow";
    el.camara.hidden = modo !== "camara";
    if (modo !== "camara") apagarCamara();
    if (modo === "flow") { estado.flowIndice = 0; actualizarContador(); }
    if (estado.cancion) elegirPaso(modo === "inspector" ? Math.max(1, estado.pasoActivo) : 0);
    if (modo !== "inspector") mostrarFicha(null);
  }
  document.querySelectorAll(".modo").forEach((b) =>
    b.addEventListener("click", () => elegirModo(b.dataset.modo)));

  // ------------------------------------------------------------ dedo / ratón sobre el papel
  function aImagen(evento) {
    const r = el.capa.getBoundingClientRect();
    return [(evento.clientX - r.left) / estado.escala, (evento.clientY - r.top) / estado.escala];
  }

  el.capa.addEventListener("pointerdown", (ev) => {
    if (!estado.cancion) return;
    const [x, y] = aImagen(ev);
    const n = notaEn(x, y);
    switch (estado.modo) {
      case "escuchar":
        if (n) {
          irAPulso(n.inicio);
          if (!estado.reproduccion) tocarNota(n);
          estado.eventoActual = eventoDe(n).indice;
        }
        break;
      case "tocar":
        el.capa.setPointerCapture(ev.pointerId);
        estado.ultimaTocada = n;
        tocarNota(n);
        break;
      case "flow":
        ev.preventDefault();
        flowSiguiente();
        break;
      case "inspector":
        mostrarFicha(n);
        break;
    }
  });

  el.capa.addEventListener("pointermove", (ev) => {
    if (estado.modo !== "tocar" || !estado.cancion || !ev.buttons && ev.pointerType === "mouse") return;
    if (!el.capa.hasPointerCapture(ev.pointerId) && ev.pointerType !== "mouse") return;
    const [x, y] = aImagen(ev);
    const n = notaEn(x, y);
    if (n && n !== estado.ultimaTocada && !(estado.ultimaTocada && n.acorde !== null && n.acorde === estado.ultimaTocada.acorde)) {
      tocarNota(n);
    }
    estado.ultimaTocada = n;
  });

  const soltar = () => { estado.ultimaTocada = null; };
  el.capa.addEventListener("pointerup", soltar);
  el.capa.addEventListener("pointercancel", soltar);

  // ------------------------------------------------------------ controles
  el.play.addEventListener("click", () => (estado.reproduccion ? pausar() : reproducir()));
  el.stop.addEventListener("click", () => {
    detener();
    el.scroll.scrollTo({ top: 0, behavior: "smooth" });
    if (estado.cancion) mostrarAhora(null, estado.cancion.titulo);
  });

  el.tempo.addEventListener("input", () => {
    const sonaba = !!estado.reproduccion;
    if (sonaba) pausar();
    estado.bpm = Number(el.tempo.value);
    el.tempoValor.textContent = estado.bpm;
    if (sonaba) reproducir();
  });

  el.progreso.addEventListener("pointerdown", (ev) => {
    if (!estado.cancion) return;
    const r = el.progreso.getBoundingClientRect();
    irAPulso(((ev.clientX - r.left) / r.width) * estado.cancion.duracion_pulsos);
  });

  el.progreso.addEventListener("keydown", (ev) => {
    if (!estado.cancion) return;
    if (ev.key === "ArrowRight") irAPulso(pulsoActual() + 2);
    if (ev.key === "ArrowLeft") irAPulso(pulsoActual() - 2);
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.code !== "Space" || ev.repeat) return;
    if (ev.target.closest("button, input, [role=slider]")) return;
    ev.preventDefault();
    if (estado.modo === "flow") flowSiguiente();
    else if (estado.modo === "escuchar") (estado.reproduccion ? pausar() : reproducir());
  });

  el.scroll.addEventListener("wheel", () => { estado.usuarioScroll = performance.now(); }, { passive: true });
  el.scroll.addEventListener("touchmove", () => { estado.usuarioScroll = performance.now(); }, { passive: true });

  // ------------------------------------------------------------ piano
  const NEGRAS = new Set([1, 3, 6, 8, 10]);
  const teclas = new Map();

  function construirPiano() {
    el.piano.innerHTML = "";
    const blancas = [];
    for (let m = MIDI_MIN; m <= MIDI_MAX; m++) if (!NEGRAS.has(m % 12)) blancas.push(m);
    const anchoBlanca = 100 / blancas.length;
    const nombres = ["DO", "", "RE", "", "MI", "FA", "", "SOL", "", "LA", "", "SI"];
    for (let m = MIDI_MIN; m <= MIDI_MAX; m++) {
      const negra = NEGRAS.has(m % 12);
      const t = document.createElement("button");
      t.className = "tecla " + (negra ? "negra" : "blanca");
      const nombre = nombres[m % 12];
      const octava = Math.floor(m / 12) - 1;
      t.setAttribute("aria-label", negra ? `${nombres[(m - 1) % 12]}${octava} sostenido` : `${nombre}${octava}`);
      if (negra) {
        const izquierda = blancas.indexOf(m - 1) + 1;
        t.style.left = `calc(${izquierda * anchoBlanca}% - ${anchoBlanca * 0.31}%)`;
        t.style.width = `${anchoBlanca * 0.62}%`;
      } else if (m % 12 === 0) {
        t.innerHTML = `<span class="nombre-tecla">DO${octava}</span>`;
      }
      t.addEventListener("pointerdown", (ev) => {
        ev.preventDefault();
        Sinte.iniciar();
        const color = negra ? COLORES[nombres[(m - 1) % 12]] : COLORES[nombre];
        Sinte.tocar(m, null, 0.8);
        encenderTecla(m, color, 0.5);
        teñirSala(color);
      });
      el.piano.appendChild(t);
      teclas.set(m, t);
    }
  }

  function encenderTecla(midi, color, duracionSeg) {
    const t = teclas.get(midi);
    if (!t) return;
    t.style.setProperty("--c", color);
    t.classList.add("encendida");
    t._fin = performance.now() + Math.max(0.18, duracionSeg * 0.92) * 1000;
    clearTimeout(t._t);
    t._t = setTimeout(() => t.classList.remove("encendida"), Math.max(0.18, duracionSeg * 0.92) * 1000);
  }

  // ------------------------------------------------------------ dibujo de la capa
  function dibujar(ahora) {
    const c = estado.cancion;
    const W = el.img.clientWidth, H = el.img.clientHeight;
    ctx2d.clearRect(0, 0, W, H);
    if (!c) return;
    const s = estado.escala, d = c.dist_media * s;
    const r = 0.62 * d;

    // 1) notas de color: un anillo suave en cada cabeza
    //    (en el Inspector no: ahí se ven las imágenes técnicas tal cual)
    for (const n of estado.notas) {
      if (n.silencio || estado.modo === "inspector") continue;
      const x = n.cx * s, y = n.cy * s, color = colorDe(n);
      ctx2d.globalAlpha = 0.9;
      ctx2d.lineWidth = Math.max(1.5, d * 0.1);
      ctx2d.strokeStyle = color;
      ctx2d.beginPath();
      ctx2d.ellipse(x, y, r * 1.18, r * 0.88, -0.35, 0, Math.PI * 2);
      ctx2d.stroke();
    }

    // 2) cursor del karaoke
    if (estado.modo === "escuchar" && (estado.reproduccion || estado.eventoActual >= 0)) {
      dibujarCursor(s, d);
    }

    // 3) siguiente nota en Flow: late suavemente
    if (estado.modo === "flow") {
      let i = estado.flowIndice;
      while (i < estado.eventos.length && estado.eventos[i].silencio) i++;
      const e = estado.eventos[i];
      if (e) {
        const latido = REDUCIR_MOVIMIENTO ? 0.5 : 0.5 + 0.5 * Math.sin(ahora / 220);
        for (const n of e.notas) {
          if (n.silencio) continue;
          ctx2d.globalAlpha = 0.35 + 0.4 * latido;
          ctx2d.strokeStyle = colorDe(n);
          ctx2d.lineWidth = 3;
          ctx2d.beginPath();
          ctx2d.ellipse(n.cx * s, n.cy * s, r * (1.6 + 0.3 * latido), r * (1.25 + 0.25 * latido), -0.35, 0, Math.PI * 2);
          ctx2d.stroke();
        }
      }
    }

    // 4) notas encendidas
    for (const [id, b] of estado.brillo) {
      const n = estado.notas[id];
      const sonandoAun = estado.reproduccion && n.inicio <= pulsoActual() && pulsoActual() < n.inicio + n.pulsos;
      const nivel = sonandoAun ? Math.max(b, 0.75) : b;
      const color = colorDe(n);
      ctx2d.globalAlpha = nivel;
      ctx2d.shadowColor = color;
      ctx2d.shadowBlur = 26 * nivel;
      ctx2d.fillStyle = color;
      ctx2d.beginPath();
      ctx2d.ellipse(n.cx * s, n.cy * s, r * 1.28, r * 0.98, -0.35, 0, Math.PI * 2);
      ctx2d.fill();
      ctx2d.shadowBlur = 0;
      const siguiente = sonandoAun ? b : b * 0.93;
      if (siguiente < 0.02) estado.brillo.delete(id); else estado.brillo.set(id, siguiente);
    }

    // 5) ondas
    estado.ondas = estado.ondas.filter((o) => {
      const t = (ahora - o.t) / 700;
      if (t >= 1) return false;
      ctx2d.globalAlpha = (1 - t) * 0.8;
      ctx2d.strokeStyle = o.color;
      ctx2d.lineWidth = 2.5 * (1 - t) + 0.5;
      ctx2d.beginPath();
      ctx2d.arc(o.x * s, o.y * s, r * (1.2 + t * 3.2), 0, Math.PI * 2);
      ctx2d.stroke();
      return true;
    });

    // 6) notitas que salen volando
    ctx2d.textAlign = "center";
    ctx2d.textBaseline = "middle";
    estado.particulas = estado.particulas.filter((p) => {
      p.x += p.vx; p.y += p.vy; p.vy += 0.02; p.angulo += p.giro; p.vida -= 0.012;
      if (p.vida <= 0) return false;
      ctx2d.save();
      ctx2d.globalAlpha = Math.min(1, p.vida);
      ctx2d.translate(p.x * s, p.y * s);
      ctx2d.rotate(p.angulo);
      ctx2d.fillStyle = p.color;
      ctx2d.font = `700 ${p.tam}px ${getComputedStyle(document.body).fontFamily}`;
      ctx2d.fillText(p.simbolo, 0, 0);
      ctx2d.restore();
      return true;
    });

    // 7) nota elegida en el Inspector
    if (estado.modo === "inspector" && estado.seleccion) {
      const [bx, by, bw, bh] = estado.seleccion.caja;
      ctx2d.globalAlpha = 1;
      ctx2d.strokeStyle = estado.seleccion.silencio ? "#1a1540" : colorDe(estado.seleccion);
      ctx2d.lineWidth = 3;
      ctx2d.setLineDash([6, 4]);
      ctx2d.strokeRect(bx * s - 4, by * s - 4, bw * s + 8, bh * s + 8);
      ctx2d.setLineDash([]);
    }
    ctx2d.globalAlpha = 1;
  }

  function dibujarCursor(s, d) {
    const c = estado.cancion;
    const p = pulsoActual();
    let i = estado.eventoActual;
    if (i < 0) i = Math.max(0, estado.eventos.findIndex((e) => e.inicio >= p - 1e-6));
    const e = estado.eventos[i];
    if (!e) return;
    const sig = estado.eventos[i + 1];
    const avance = estado.reproduccion ? Math.min(1, Math.max(0, (p - e.inicio) / e.pulsos)) : 0;
    let x = e.cx;
    if (sig && sig.pentagrama === e.pentagrama) x = e.cx + (sig.cx - e.cx) * avance;
    else x = e.cx + c.dist_media * 1.5 * avance;
    const lineas = c.pentagramas[e.pentagrama - 1];
    const y0 = (lineas[0] - c.dist_media * 1.6) * s, y1 = (lineas[4] + c.dist_media * 1.6) * s;
    const color = getComputedStyle(document.documentElement).getPropertyValue("--aura").trim() || "#5b7cfa";
    const g = ctx2d.createLinearGradient(0, y0, 0, y1);
    g.addColorStop(0, "transparent");
    g.addColorStop(0.5, color);
    g.addColorStop(1, "transparent");
    ctx2d.globalAlpha = 0.9;
    ctx2d.fillStyle = g;
    ctx2d.shadowColor = color;
    ctx2d.shadowBlur = 14;
    ctx2d.fillRect(x * s - 2, y0, 4, y1 - y0);
    ctx2d.shadowBlur = 0;

    // que el pentagrama que suena se vea (si no estás haciendo scroll tú)
    if (estado.reproduccion && performance.now() - estado.usuarioScroll > 2500) {
      const objetivo = Math.max(0, y0 - 30);
      const sc = el.scroll;
      if (objetivo < sc.scrollTop || y1 > sc.scrollTop + sc.clientHeight) {
        sc.scrollTop += (objetivo - sc.scrollTop) * 0.12;
      }
    }
  }

  // ------------------------------------------------------------ instrumento
  function construirInstrumentos() {
    try {
      const guardado = localStorage.getItem("scorevision-instrumento");
      if (guardado) Sinte.instrumento = guardado;
    } catch (e) { /* sin almacenamiento */ }
    el.instrumento.innerHTML = Object.entries(Sinte.instrumentos).map(([clave, nombre]) =>
      `<button role="radio" data-instrumento="${clave}" aria-checked="${clave === Sinte.instrumento}">${nombre}</button>`
    ).join("");
    el.instrumento.addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      Sinte.instrumento = b.dataset.instrumento;
      try { localStorage.setItem("scorevision-instrumento", b.dataset.instrumento); } catch (e) { /* nada */ }
      el.instrumento.querySelectorAll("button").forEach((x) => x.setAttribute("aria-checked", x === b));
      if (estado.reproduccion) { pausar(); reproducir(); }      // sigue sonando con el nuevo
      else { Sinte.iniciar(); Sinte.tocar(67, null, 0.6); }    // un SOL de muestra
    });
  }

  // ------------------------------------------------------------ modo Cámara: el dedo mágico
  // 1. La cámara ve la partitura (impresa o en otra pantalla).
  // 2. Tocas en el vídeo las 4 esquinas de los pentagramas -> homografía vídeo <-> partitura.
  // 3. MediaPipe encuentra la punta del índice; la homografía la lleva a la partitura
  //    y suena la nota que hay debajo. Además se pintan las notas sobre el vídeo (realidad aumentada).
  const MEDIAPIPE = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
  const MODELO_MANO = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
  const ESQUINAS = [
    "arriba a la izquierda (donde empieza la primera línea)",
    "arriba a la derecha (donde acaba la primera línea)",
    "abajo a la derecha (donde acaba la última línea)",
    "abajo a la izquierda (donde empieza la última línea)",
  ];
  const UNIONES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10],
    [10, 11], [11, 12], [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];
  const LECTURA = 0.4;        // se lee un poco por encima de la punta del dedo (no tapa la nota)
  const ESPERA_MS = 90;       // el dedo tiene que estar quieto un instante sobre la nota

  const cam = {
    flujo: null, esquinas: [], H: null, Hinv: null,
    detector: null, estadoDetector: "nada",
    mano: null, dedo: null, candidata: null, desde: 0, ultima: null, sinNotaDesde: 0,
    ultimoTiempoVideo: -1,
  };
  const ctxCam = el.capaCamara.getContext("2d");

  // --- homografía con 4 puntos (sistema de 8 ecuaciones, eliminación de Gauss)
  function resolverSistema(A, b) {
    const n = b.length;
    const M = A.map((fila, i) => [...fila, b[i]]);
    for (let c = 0; c < n; c++) {
      let p = c;
      for (let f = c + 1; f < n; f++) if (Math.abs(M[f][c]) > Math.abs(M[p][c])) p = f;
      [M[c], M[p]] = [M[p], M[c]];
      for (let f = 0; f < n; f++) {
        if (f === c) continue;
        const k = M[f][c] / M[c][c];
        for (let j = c; j <= n; j++) M[f][j] -= k * M[c][j];
      }
    }
    return M.map((fila, i) => fila[n] / fila[i]);
  }

  function homografia(origen, destino) {
    const A = [], b = [];
    for (let i = 0; i < 4; i++) {
      const [x, y] = origen[i], [u, v] = destino[i];
      A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
      A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
    }
    return [...resolverSistema(A, b), 1];
  }

  function aplicarH(H, [x, y]) {
    const w = H[6] * x + H[7] * y + H[8];
    return [(H[0] * x + H[1] * y + H[2]) / w, (H[3] * x + H[4] * y + H[5]) / w];
  }

  function camEstado(texto) { el.camaraEstado.textContent = texto; }

  async function encenderCamara() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      camEstado("Aquí no se puede usar la cámara. Abre la web desde una dirección https, por ejemplo GitHub Pages.");
      return;
    }
    Sinte.iniciar();                         // aprovecha este toque para activar el sonido
    camEstado("Abriendo la cámara…");
    try {
      cam.flujo = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
    } catch (e) {
      camEstado(e.name === "NotAllowedError"
        ? "La cámara está bloqueada. Dale permiso en el navegador y vuelve a pulsar el botón."
        : "No se ha podido abrir la cámara (" + e.name + ").");
      return;
    }
    el.video.srcObject = cam.flujo;
    await el.video.play();
    el.camaraInicio.hidden = true;
    document.querySelector("#camara-marco").classList.add("encendida");
    empezarCalibracion();
    cargarDetector();
  }

  function apagarCamara() {
    if (cam.flujo) cam.flujo.getTracks().forEach((t) => t.stop());
    cam.flujo = null;
    cam.mano = null;
    cam.dedo = null;
    el.video.srcObject = null;
    el.camaraInicio.hidden = false;
    document.querySelector("#camara-marco").classList.remove("encendida");
    el.recalibrar.hidden = true;
    camEstado("");
  }

  function empezarCalibracion() {
    cam.esquinas = [];
    cam.H = cam.Hinv = null;
    cam.ultima = null;
    el.recalibrar.hidden = true;
    camEstado("Toca en el vídeo la esquina 1 de 4: " + ESQUINAS[0] + ".");
  }

  function calibrar() {
    const marco = estado.cancion.marco;
    cam.H = homografia(cam.esquinas, marco);      // vídeo -> partitura
    cam.Hinv = homografia(marco, cam.esquinas);   // partitura -> vídeo
    el.recalibrar.hidden = false;
    mensajeListo();
  }

  function mensajeListo() {
    if (!cam.H) return;
    camEstado({
      listo: "¡Listo! Señala una nota con el índice.",
      error: "No se ha podido cargar el detector de manos: toca las notas directamente en el vídeo.",
    }[cam.estadoDetector] || "Cargando el detector de manos…");
  }

  async function cargarDetector() {
    if (cam.estadoDetector !== "nada") return;
    cam.estadoDetector = "cargando";
    try {
      const { FilesetResolver, HandLandmarker } = await import(`${MEDIAPIPE}/vision_bundle.mjs`);
      const archivos = await FilesetResolver.forVisionTasks(`${MEDIAPIPE}/wasm`);
      const crear = (delegate) => HandLandmarker.createFromOptions(archivos, {
        baseOptions: { modelAssetPath: MODELO_MANO, delegate },
        runningMode: "VIDEO",
        numHands: 1,
      });
      try { cam.detector = await crear("GPU"); } catch (e) { cam.detector = await crear("CPU"); }
      cam.estadoDetector = "listo";
    } catch (e) {
      console.warn("Detector de manos no disponible:", e);
      cam.estadoDetector = "error";
    }
    mensajeListo();
  }

  function aVideo(ev) {
    const r = el.video.getBoundingClientRect();      // el propio vídeo, no el recuadro
    return [(ev.clientX - r.left) / r.width * el.video.videoWidth,
            (ev.clientY - r.top) / r.height * el.video.videoHeight];
  }

  function notaDesdeVideo(p, desplazar) {
    const [x, y] = aplicarH(cam.H, p);
    const d = estado.cancion.dist_media;
    return notaEn(x, y - (desplazar ? LECTURA * d : 0), 1.3);
  }

  el.capaCamara.addEventListener("pointerdown", (ev) => {
    if (!cam.flujo || !estado.cancion) return;
    const p = aVideo(ev);
    if (!cam.H) {
      cam.esquinas.push(p);
      if (cam.esquinas.length < 4) {
        camEstado(`Esquina ${cam.esquinas.length + 1} de 4: ${ESQUINAS[cam.esquinas.length]}.`);
      } else {
        calibrar();
      }
      return;
    }
    const n = notaDesdeVideo(p, false);      // tocar el vídeo también vale
    if (n) tocarNota(n);
  });

  el.encenderCamara.addEventListener("click", encenderCamara);
  el.recalibrar.addEventListener("click", empezarCalibracion);

  function sinNota(ahora) {
    cam.candidata = null;
    if (!cam.sinNotaDesde) cam.sinNotaDesde = ahora;
    if (ahora - cam.sinNotaDesde > 300) cam.ultima = null;   // al apartar el dedo, se puede repetir
  }

  /** punta: [x, y] en píxeles del vídeo, o null si no hay mano. */
  function procesarDedo(punta, ahora) {
    if (!punta) { cam.dedo = null; sinNota(ahora); return; }
    // suavizado: media entre la posición anterior y la nueva (quita el temblor)
    cam.dedo = cam.dedo ? [cam.dedo[0] * 0.45 + punta[0] * 0.55, cam.dedo[1] * 0.45 + punta[1] * 0.55] : punta;
    if (!cam.H) return;
    const n = notaDesdeVideo(cam.dedo, true);
    if (!n) { sinNota(ahora); return; }
    cam.sinNotaDesde = 0;
    if (n !== cam.candidata) { cam.candidata = n; cam.desde = ahora; return; }
    const mismoAcorde = cam.ultima && n.acorde !== null && n.acorde === cam.ultima.acorde;
    if (ahora - cam.desde >= ESPERA_MS && n !== cam.ultima && !mismoAcorde) {
      tocarNota(n);
      cam.ultima = n;
    }
  }

  function actualizarCamara(ahora) {
    if (!cam.flujo || el.video.readyState < 2 || !el.video.videoWidth) return;
    if (cam.detector && el.video.currentTime !== cam.ultimoTiempoVideo) {
      cam.ultimoTiempoVideo = el.video.currentTime;
      const r = cam.detector.detectForVideo(el.video, ahora);
      const w = el.video.videoWidth, h = el.video.videoHeight;
      cam.mano = r.landmarks && r.landmarks[0] ? r.landmarks[0].map((p) => [p.x * w, p.y * h]) : null;
      procesarDedo(cam.mano ? cam.mano[8] : null, ahora);
    }
    dibujarCamara();
  }

  function dibujarCamara() {
    const lienzo = el.capaCamara;
    const dpr = window.devicePixelRatio || 1;
    const W = lienzo.clientWidth, Hh = lienzo.clientHeight;
    if (lienzo.width !== Math.round(W * dpr) || lienzo.height !== Math.round(Hh * dpr)) {
      lienzo.width = Math.round(W * dpr);
      lienzo.height = Math.round(Hh * dpr);
    }
    ctxCam.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctxCam.clearRect(0, 0, W, Hh);
    if (!el.video.videoWidth) return;
    const s = el.video.clientWidth / el.video.videoWidth;
    const P = ([x, y]) => [x * s, y * s];

    // esquinas marcadas
    ctxCam.lineWidth = 2;
    cam.esquinas.forEach((e, i) => {
      const [x, y] = P(e);
      ctxCam.fillStyle = "#ffffff";
      ctxCam.beginPath(); ctxCam.arc(x, y, 7, 0, Math.PI * 2); ctxCam.fill();
      ctxCam.fillStyle = "#1a1540";
      ctxCam.font = "700 11px sans-serif";
      ctxCam.textAlign = "center"; ctxCam.textBaseline = "middle";
      ctxCam.fillText(String(i + 1), x, y + 0.5);
    });

    if (cam.Hinv) {
      // contorno de los pentagramas sobre el vídeo
      const marco = estado.cancion.marco.map((p) => P(aplicarH(cam.Hinv, p)));
      ctxCam.strokeStyle = "rgba(255,255,255,0.75)";
      ctxCam.setLineDash([6, 6]);
      ctxCam.beginPath();
      marco.forEach(([x, y], i) => (i ? ctxCam.lineTo(x, y) : ctxCam.moveTo(x, y)));
      ctxCam.closePath(); ctxCam.stroke();
      ctxCam.setLineDash([]);

      // las notas, pintadas encima del papel real
      const d = estado.cancion.dist_media;
      for (const n of estado.notas) {
        if (n.silencio) continue;
        const c = P(aplicarH(cam.Hinv, [n.cx, n.cy]));
        const borde = P(aplicarH(cam.Hinv, [n.cx + 0.7 * d, n.cy]));
        const r = Math.max(4, Math.hypot(borde[0] - c[0], borde[1] - c[1]));
        const b = estado.brillo.get(n.id) || 0;
        const color = colorDe(n);
        ctxCam.globalAlpha = 0.85;
        ctxCam.strokeStyle = color;
        ctxCam.lineWidth = Math.max(2, r * 0.22);
        ctxCam.beginPath(); ctxCam.arc(c[0], c[1], r, 0, Math.PI * 2); ctxCam.stroke();
        if (b > 0.02) {
          ctxCam.globalAlpha = b;
          ctxCam.fillStyle = color;
          ctxCam.shadowColor = color; ctxCam.shadowBlur = 24 * b;
          ctxCam.beginPath(); ctxCam.arc(c[0], c[1], r * (1.3 + 0.6 * (1 - b)), 0, Math.PI * 2); ctxCam.fill();
          ctxCam.shadowBlur = 0;
        }
      }
      ctxCam.globalAlpha = 1;
    }

    // la mano
    if (cam.mano) {
      ctxCam.strokeStyle = "rgba(255,255,255,0.55)";
      ctxCam.lineWidth = 2;
      for (const [a, b] of UNIONES) {
        const [x1, y1] = P(cam.mano[a]), [x2, y2] = P(cam.mano[b]);
        ctxCam.beginPath(); ctxCam.moveTo(x1, y1); ctxCam.lineTo(x2, y2); ctxCam.stroke();
      }
    }
    if (cam.dedo) {
      const [x, y] = P(cam.dedo);
      const color = cam.candidata ? colorDe(cam.candidata) : "#ffffff";
      ctxCam.strokeStyle = color;
      ctxCam.lineWidth = 3;
      ctxCam.beginPath(); ctxCam.arc(x, y, 14, 0, Math.PI * 2); ctxCam.stroke();
      if (cam.H) {   // dónde está leyendo (un poco por encima de la uña)
        const d = estado.cancion.dist_media;
        const lect = aplicarH(cam.H, cam.dedo);
        const [lx, ly] = P(aplicarH(cam.Hinv, [lect[0], lect[1] - LECTURA * d]));
        ctxCam.fillStyle = color;
        ctxCam.beginPath(); ctxCam.arc(lx, ly, 4, 0, Math.PI * 2); ctxCam.fill();
      }
    }
  }

  // ------------------------------------------------------------ fondo: notas flotando
  const fondo = el.fondo.getContext("2d");
  let flotantes = [];
  function prepararFondo() {
    const dpr = window.devicePixelRatio || 1;
    el.fondo.width = innerWidth * dpr;
    el.fondo.height = innerHeight * dpr;
    fondo.setTransform(dpr, 0, 0, dpr, 0, 0);
    const cuantas = Math.round(Math.min(26, innerWidth / 55));
    const colores = Object.values(COLORES);
    flotantes = Array.from({ length: cuantas }, (_, k) => ({
      x: Math.random() * innerWidth, y: Math.random() * innerHeight,
      v: 0.12 + Math.random() * 0.25, fase: Math.random() * 6.28,
      tam: 18 + Math.random() * 34, simbolo: SIMBOLOS[k % 4], color: colores[k % 7],
      alfa: 0.06 + Math.random() * 0.1,
    }));
  }
  function dibujarFondo(ahora) {
    fondo.clearRect(0, 0, innerWidth, innerHeight);
    fondo.textAlign = "center";
    for (const f of flotantes) {
      if (!REDUCIR_MOVIMIENTO) {
        f.y -= f.v;
        if (f.y < -40) { f.y = innerHeight + 40; f.x = Math.random() * innerWidth; }
      }
      fondo.globalAlpha = f.alfa;
      fondo.fillStyle = f.color;
      fondo.font = `${f.tam}px serif`;
      fondo.fillText(f.simbolo, f.x + Math.sin(ahora / 1800 + f.fase) * 14, f.y);
    }
  }
  addEventListener("resize", prepararFondo);

  // ------------------------------------------------------------ bucle
  function bucle(ahora) {
    avanzarKaraoke();
    if (estado.modo === "camara") actualizarCamara(ahora);
    if (estado.cancion) {
      const total = estado.cancion.duracion_pulsos;
      el.relleno.style.width = `${Math.min(100, (pulsoActual() / total) * 100)}%`;
    }
    dibujar(ahora);
    dibujarFondo(ahora);
    requestAnimationFrame(bucle);
  }

  // ------------------------------------------------------------ arranque
  function arrancar() {
    if (!window.SCOREVISION || !window.SCOREVISION.canciones?.length) {
      el.ayuda.textContent = "No hay partituras. Ejecuta exportar_web.py para generar partituras/datos.js.";
      return;
    }
    document.body.dataset.modo = estado.modo;
    el.ayuda.textContent = AYUDAS[estado.modo];
    construirTarjetas();
    construirPiano();
    construirInstrumentos();
    prepararFondo();
    const porHash = window.SCOREVISION.canciones.findIndex((c) => "#" + c.id === location.hash);
    cargarCancion(porHash >= 0 ? porHash : 0);
    requestAnimationFrame(bucle);
  }

  // para las pruebas automáticas
  window.ScoreVisionApp = { estado, cargarCancion, reproducir, pausar, elegirModo, flowSiguiente,
    cam, procesarDedo, homografia, aplicarH, calibrar };

  arrancar();
})();
