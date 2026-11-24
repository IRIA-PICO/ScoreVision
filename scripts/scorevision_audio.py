"""
ScoreVision · TIEMPOS Y SONIDO (sin depender de Windows)
========================================================
- calcular_tiempos(): en qué pulso empieza cada nota (los acordes, a la vez)
- renderizar(): genera el audio (numpy) con timbre tipo piano
- guardar_wav(): lo guarda en un .wav
La web usa los mismos tiempos (van en el JSON), así el ritmo se programa una vez.
"""
import re
import wave

import numpy as np

from scorevision_core import DURACIONES

FS = 44100      #muestras por segundo
COLA = 0.4      #segundos que la nota sigue resonando al soltarla

SEMITONOS = {"DO": 0, "RE": 2, "MI": 4, "FA": 5, "SOL": 7, "LA": 9, "SI": 11}


def altura_a_midi(altura):
    """'SOL4' -> 67, 'FA#4' -> 66. Devuelve None para un silencio."""
    m = re.fullmatch(r"(DO|RE|MI|FA|SOL|LA|SI)(#|b)?(-?\d+)", altura)
    if m is None:
        return None
    nombre, alteracion, octava = m.groups()
    return 12 * (int(octava) + 1) + SEMITONOS[nombre] + {"#": 1, "b": -1}.get(alteracion, 0)


def calcular_frecuencia(altura):
    midi = altura_a_midi(altura)
    if midi is None:
        raise ValueError(f"Nota no reconocida: {altura}")
    return 440 * 2 ** ((midi - 69) / 12)


def pulsos(nota):
    return DURACIONES[nota["tipo"]] * (1.5 if nota.get("puntillo") else 1)


def calcular_tiempos(notas):
    """Añade nota['inicio'] y nota['pulsos'] (en pulsos, no en segundos,
    para poder cambiar el tempo sin recalcular). Las notas de un mismo
    acorde empiezan a la vez. Devuelve la duración total en pulsos."""
    t = 0.0
    acorde_anterior = None
    inicio_acorde = 0.0
    for n in notas:
        n["pulsos"] = pulsos(n)
        acorde = n.get("acorde_id")
        if acorde is not None and acorde == acorde_anterior:
            n["inicio"] = inicio_acorde          # suena con la anterior
            continue
        n["inicio"] = t
        inicio_acorde = t
        acorde_anterior = acorde
        t += n["pulsos"]
    return t


def sintetizar_nota(freq, dur):
    """Varios armónicos que se apagan solos -> timbre tipo piano."""
    n = int(FS * (dur + COLA))
    t = np.arange(n) / FS
    onda = np.zeros(n)
    for k, amp in enumerate([1.0, 0.45, 0.25, 0.12, 0.06, 0.03], start=1):
        onda += amp * np.sin(2 * np.pi * freq * k * t) * np.exp(-t * (0.9 + 0.9 * k))
    a = int(0.006 * FS)
    onda[:a] *= np.linspace(0, 1, a)                       # ataque suave
    fin = int(FS * dur)
    onda[fin:] *= np.exp(-(t[fin:] - dur) * 10)            # se suelta
    return onda


def renderizar(notas, bpm=100):
    """Todas las notas en un único audio (int16). Usa nota['inicio']."""
    total_pulsos = calcular_tiempos(notas)
    seg = 60 / bpm
    audio = np.zeros(int(FS * (total_pulsos * seg + COLA + 0.2)))
    for n in notas:
        if n["tipo"].startswith("silencio"):
            continue                                     # hueco sin sonido
        i = int(n["inicio"] * seg * FS)
        s = sintetizar_nota(calcular_frecuencia(n["altura"]), n["pulsos"] * seg)
        audio[i:i + len(s)] += s[:len(audio) - i]
    audio /= np.max(np.abs(audio)) + 1e-9
    return (audio * 0.8 * 32767).astype(np.int16)


def guardar_wav(audio, ruta):
    with wave.open(str(ruta), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(FS)
        f.writeframes(audio.tobytes())
