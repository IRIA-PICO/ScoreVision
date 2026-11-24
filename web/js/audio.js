/* ScoreVision — sintetizador con Web Audio
   Cada nota es una suma de parciales (senos) que se apagan solos.
   Tres instrumentos: cambian qué parciales hay, cuánto pesan y cuánto duran.
   Todo se programa con el reloj del audio (ctx.currentTime), así el karaoke
   va exactamente a tempo aunque la pantalla vaya a tirones. */
"use strict";

const Sinte = (() => {
  let ctx = null;
  let salida = null;

  // relacion: múltiplo de la frecuencia; amp: volumen; caida: cuánto tarda en apagarse
  // (más alto = se apaga antes). Más parciales agudos y que duren = sonido más brillante.
  const INSTRUMENTOS = {
    piano: {
      nombre: "Piano",
      octava: 0,
      volumen: 0.13,
      articulacion: 0.88,         // la nota suena el 88 % de su duración: más "picado", más vivo
      parciales: [
        { relacion: 1, amp: 1.0, caida: 1.1 },
        { relacion: 2, amp: 0.62, caida: 1.4 },
        { relacion: 3, amp: 0.42, caida: 1.8 },
        { relacion: 4, amp: 0.26, caida: 2.3 },
        { relacion: 5, amp: 0.17, caida: 2.9 },
        { relacion: 6, amp: 0.10, caida: 3.6 },
        { relacion: 8, amp: 0.05, caida: 5.0 },
      ],
    },
    caja: {
      nombre: "Caja de música",
      octava: 1,                  // una octava más aguda: suena a juguete y a alegría
      volumen: 0.15,
      articulacion: 0.7,
      parciales: [                // ligeramente inarmónicos: sonido de campanita
        { relacion: 1, amp: 1.0, caida: 2.2 },
        { relacion: 2.0, amp: 0.35, caida: 3.2 },
        { relacion: 3.01, amp: 0.22, caida: 4.5 },
        { relacion: 4.17, amp: 0.12, caida: 6 },
        { relacion: 5.43, amp: 0.07, caida: 8 },
      ],
    },
    marimba: {
      nombre: "Marimba",
      octava: 0,
      volumen: 0.2,
      articulacion: 0.6,
      parciales: [                // madera: fundamental + un parcial ~4 veces más agudo
        { relacion: 1, amp: 1.0, caida: 3.2 },
        { relacion: 3.93, amp: 0.32, caida: 9 },
        { relacion: 9.2, amp: 0.08, caida: 16 },
      ],
    },
  };

  let instrumento = "piano";
  const sonando = new Set();

  function crearReverb() {
    // Respuesta al impulso inventada: ruido que se apaga en ~1.4 s
    const dur = 1.4;
    const buf = ctx.createBuffer(2, Math.floor(ctx.sampleRate * dur), ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const datos = buf.getChannelData(c);
      for (let i = 0; i < datos.length; i++) {
        datos[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / datos.length, 3.5);
      }
    }
    const conv = ctx.createConvolver();
    conv.buffer = buf;
    return conv;
  }

  function iniciar() {
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      const compresor = ctx.createDynamicsCompressor();
      compresor.threshold.value = -14;
      compresor.ratio.value = 4;
      salida = ctx.createGain();
      salida.gain.value = 0.8;
      const reverb = crearReverb();
      const mojado = ctx.createGain();
      mojado.gain.value = 0.12;   // poca sala: más claro y más alegre
      salida.connect(compresor);
      salida.connect(reverb);
      reverb.connect(mojado);
      mojado.connect(compresor);
      compresor.connect(ctx.destination);
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  const midiAFrecuencia = (m) => 440 * Math.pow(2, (m - 69) / 12);

  /** Programa una nota. cuando: segundos del reloj de audio. */
  function tocar(midi, cuando, duracion, fuerza = 1) {
    iniciar();
    const ins = INSTRUMENTOS[instrumento];
    const t0 = Math.max(cuando ?? ctx.currentTime, ctx.currentTime);
    const f = midiAFrecuencia(midi + 12 * ins.octava);
    const suena = Math.max(0.08, duracion * ins.articulacion);
    const nota = ctx.createGain();
    nota.connect(salida);

    const osciladores = ins.parciales
      .filter((p) => f * p.relacion < 16000)
      .map((p) => {
        const osc = ctx.createOscillator();
        osc.frequency.value = f * p.relacion;
        const g = ctx.createGain();
        g.gain.setValueAtTime(0, t0);
        g.gain.linearRampToValueAtTime(p.amp * ins.volumen * fuerza, t0 + 0.004);
        g.gain.setTargetAtTime(0, t0 + 0.004, 1 / p.caida);
        osc.connect(g);
        g.connect(nota);
        osc.start(t0);
        osc.stop(t0 + suena + 0.5);
        return osc;
      });

    // al acabar, la nota se suelta
    nota.gain.setValueAtTime(1, t0 + suena);
    nota.gain.setTargetAtTime(0, t0 + suena, 0.06);

    const registro = { nota, osciladores };
    sonando.add(registro);
    osciladores[0].onended = () => sonando.delete(registro);
    return registro;
  }

  /** Silencia todo lo que suena o está programado. */
  function callar() {
    if (!ctx) return;
    const ahora = ctx.currentTime;
    sonando.forEach(({ nota, osciladores }) => {
      try {
        nota.gain.cancelScheduledValues(ahora);
        nota.gain.setTargetAtTime(0, ahora, 0.03);
        osciladores.forEach((o) => o.stop(ahora + 0.2));
      } catch (e) { /* ya parado */ }
    });
    sonando.clear();
  }

  return {
    iniciar,
    tocar,
    callar,
    instrumentos: Object.fromEntries(Object.entries(INSTRUMENTOS).map(([k, v]) => [k, v.nombre])),
    get instrumento() { return instrumento; },
    set instrumento(nombre) { if (INSTRUMENTOS[nombre]) instrumento = nombre; },
    get reloj() { return ctx ? ctx.currentTime : 0; },
  };
})();
