"""Synthesised documentary score + sound effects for the DMart edit (numpy/scipy only).

python3 audio.py music <out.wav> <duration>
python3 audio.py sfx <events.json> <out.wav> <duration>
"""
import json
import sys

import numpy as np
from scipy.signal import fftconvolve, butter, sosfilt

SR = 48000
BPM = 100
BEAT = 60 / BPM
BAR = 4 * BEAT
rng = np.random.default_rng(1)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def env_adsr(n, a, d, s, r, sr=SR):
    t = np.arange(n) / sr
    e = np.ones(n) * s
    ai = int(a * sr)
    di = int(d * sr)
    ri = int(r * sr)
    if ai:
        e[:ai] = np.linspace(0, 1, ai)
    if di:
        e[ai:ai + di] = np.linspace(1, s, len(e[ai:ai + di]))
    if ri:
        e[-ri:] *= np.linspace(1, 0, ri) ** 2
    return e


def tone(freq, dur, harmonics=6, bright=1.0, detune=0.0):
    t = np.arange(int(dur * SR)) / SR
    out = np.zeros_like(t)
    for h in range(1, harmonics + 1):
        amp = (1 / h) * np.exp(-(h - 1) / (2.5 * bright))
        out += amp * np.sin(2 * np.pi * freq * h * (1 + detune) * t + rng.uniform(0, 6.28))
    return out


def lp(x, fc, order=2):
    return sosfilt(butter(order, fc, 'low', fs=SR, output='sos'), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, fc, 'high', fs=SR, output='sos'), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], 'band', fs=SR, output='sos'), x)


def reverb(x, decay=2.8, mix=0.35, seed=0):
    r = np.random.default_rng(seed)
    n = int(decay * SR)
    t = np.arange(n) / SR
    out = []
    for ch in range(2):
        ir = r.standard_normal(n) * np.exp(-6.9 * t / decay)
        ir = lp(ir, 6000)
        ir[: int(0.02 * SR)] = 0
        ir /= np.sqrt((ir ** 2).sum())
        out.append(fftconvolve(x[:, ch], ir)[: len(x)])
    wet = np.stack(out, 1)
    return x * (1 - mix) + wet * mix * 1.6


def add(buf, sig, t0, gain=1.0, pan=0.0):
    i = int(t0 * SR)
    if i >= len(buf):
        return
    sig = sig[: len(buf) - i]
    l = np.cos((pan + 1) * np.pi / 4)
    r = np.sin((pan + 1) * np.pi / 4)
    if sig.ndim == 1:
        buf[i:i + len(sig), 0] += sig * gain * l * 1.414
        buf[i:i + len(sig), 1] += sig * gain * r * 1.414
    else:
        buf[i:i + len(sig)] += sig * gain


# chord progression: Am - F - C - G (warm, hopeful documentary feel)
CHORDS = [[57, 60, 64], [53, 57, 60], [48, 52, 55, 60], [55, 59, 62]]
ROOTS = [45, 41, 48, 43]


def section_intensity(t):
    """0..1 energy curve following the story."""
    pts = [(0, 0.35), (6, 0.45), (22, 0.5), (38, 0.7), (100, 0.75), (141, 0.8), (173, 0.85),
           (196, 0.95), (200, 1.0), (209, 0.6), (222, 0.3), (226, 0.0)]
    xs, ys = zip(*pts)
    return float(np.interp(t, xs, ys))


def music(dur):
    buf = np.zeros((int(dur * SR) + SR * 4, 2))
    nbars = int(dur / BAR) + 2
    for b in range(nbars):
        t0 = b * BAR
        if t0 > dur:
            break
        I = section_intensity(t0)
        ci = b % 4
        # pad
        for k, n in enumerate(CHORDS[ci]):
            for det, pan in ((-0.0025, -0.6), (0.0025, 0.6)):
                s = tone(midi(n), BAR + 1.2, 7, 0.8, det) * env_adsr(int((BAR + 1.2) * SR), 0.6, 0.5, 0.8, 1.2)
                add(buf, s, t0, 0.055, pan)
        # bass pulses (quarter notes, soft sidechain feel)
        if I >= 0.5:
            for q in range(4):
                s = tone(midi(ROOTS[ci]), BEAT, 4, 0.6) * env_adsr(int(BEAT * SR), 0.01, 0.2, 0.6, 0.2)
                add(buf, s, t0 + q * BEAT, 0.16 * I)
        # arpeggio 8ths
        arp = CHORDS[ci] + [CHORDS[ci][0] + 12]
        for e in range(8):
            if I < 0.4 and e % 2:
                continue
            n = arp[[0, 1, 2, 3, 2, 1, 3, 2][e]] + 12
            d = 0.5
            tt = np.arange(int(d * SR)) / SR
            s = (np.sin(2 * np.pi * midi(n) * tt) + 0.25 * np.sin(4 * np.pi * midi(n) * tt)) * np.exp(-tt * 9)
            pan = -0.4 if e % 2 else 0.4
            add(buf, s, t0 + e * BEAT / 2, 0.07, pan)
            add(buf, s * 0.45, t0 + e * BEAT / 2 + BEAT * 0.75, 0.07, -pan)  # delay echo
        # drums
        if I >= 0.65:
            kicks = [0, 2] if I < 0.95 else [0, 1, 2, 3]
            for q in kicks:
                tt = np.arange(int(0.35 * SR)) / SR
                f = 45 + 80 * np.exp(-tt * 30)
                s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9)
                add(buf, s, t0 + q * BEAT, 0.32)
            for q in range(4):
                n = int(0.05 * SR)
                s = hp(rng.standard_normal(n), 7000) * np.exp(-np.arange(n) / SR * 70)
                add(buf, s, t0 + q * BEAT + BEAT / 2, 0.05, 0.3)
        if I >= 0.8:
            for q in (1, 3):  # soft clap/snare
                n = int(0.2 * SR)
                s = bp(rng.standard_normal(n), 900, 5000) * np.exp(-np.arange(n) / SR * 22)
                add(buf, s, t0 + q * BEAT, 0.08)
    buf = reverb(buf, 2.6, 0.3)
    buf = buf[: int(dur * SR)]
    # global fades
    n = len(buf)
    fade = np.ones(n)
    fade[: int(1.5 * SR)] = np.linspace(0, 1, int(1.5 * SR))
    fo = int(4 * SR)
    fade[-fo:] = np.linspace(1, 0, fo)
    buf *= fade[:, None]
    return buf / (np.abs(buf).max() + 1e-9) * 0.89


# ------------------------------------------------------------------ SFX
def sfx_whoosh(d=0.7, up=True):
    n = int(d * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    # time-varying band via chunks
    steps = 24
    for i in range(steps):
        a, b = i * n // steps, (i + 1) * n // steps
        x = i / steps
        fc = 300 + 4500 * (x if up else 1 - x) ** 1.5
        seg = bp(noise[max(0, a - 2000):b], fc * 0.6, min(fc * 1.6, 20000))[-(b - a):]
        out[a:b] = seg
    e = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2
    s = out * e
    return np.stack([s * np.linspace(1, 0.4, n), s * np.linspace(0.4, 1, n)], 1) / (np.abs(s).max() + 1e-9)


def sfx_pop():
    d = 0.12
    t = np.arange(int(d * SR)) / SR
    f = 900 * np.exp(-t * 18) + 400
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40)
    return s / np.abs(s).max()


def sfx_ding():
    d = 1.2
    t = np.arange(int(d * SR)) / SR
    s = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * k)
            for f, a, k in ((2093, 1, 4), (3136, 0.5, 6), (4186, 0.3, 8), (5274, 0.2, 10)))
    return s / np.abs(s).max()


def sfx_coins():
    out = np.zeros(int(1.0 * SR))
    for i in range(7):
        t0 = int(rng.uniform(0, 0.6) * SR)
        d = int(0.3 * SR)
        t = np.arange(d) / SR
        f = rng.uniform(3000, 6500)
        s = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.48 * t)) * np.exp(-t * 25)
        out[t0:t0 + d] += s[: len(out) - t0]
    return out / np.abs(out).max()


def sfx_impact():
    d = 1.6
    t = np.arange(int(d * SR)) / SR
    f = 30 + 70 * np.exp(-t * 6)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3)
    s += lp(rng.standard_normal(len(t)), 800) * np.exp(-t * 12) * 0.5
    return s / np.abs(s).max()


def sfx_riser(d=1.8):
    t = np.arange(int(d * SR)) / SR
    f = 200 + 1400 * (t / d) ** 2
    s = 0.4 * np.sin(2 * np.pi * np.cumsum(f) / SR)
    s += hp(rng.standard_normal(len(t)), 2000) * 0.6
    s *= (t / d) ** 2
    return s / np.abs(s).max()


def sfx_click():
    t = np.arange(int(0.05 * SR)) / SR
    s = np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120)
    return s


SFX = {
    "whoosh": (lambda: sfx_whoosh(0.7, True), 0.32),
    "whoosh_down": (lambda: sfx_whoosh(0.8, False), 0.3),
    "pop": (sfx_pop, 0.22),
    "ding": (sfx_ding, 0.12),
    "coins": (sfx_coins, 0.16),
    "impact": (sfx_impact, 0.45),
    "riser": (sfx_riser, 0.18),
    "click": (sfx_click, 0.25),
}


def sfx_track(events, dur):
    buf = np.zeros((int(dur * SR) + 3 * SR, 2))
    cache = {}
    for ev in events:
        k = ev["type"]
        if k not in cache:
            cache[k] = SFX[k][0]()
        s = cache[k]
        t = ev["t"] - (0.35 if k.startswith("whoosh") else 0) - (1.8 if k == "riser" else 0)
        add(buf, s, max(0, t), SFX[k][1] * ev.get("gain", 1.0), ev.get("pan", 0.0))
    buf = reverb(buf, 1.2, 0.18, seed=3)
    return buf[: int(dur * SR)]


def write_wav(path, x):
    import wave
    x = np.clip(x, -1, 1)
    pcm = (x * 32767).astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    if sys.argv[1] == "music":
        write_wav(sys.argv[2], music(float(sys.argv[3])))
    else:
        ev = json.load(open(sys.argv[2]))
        write_wav(sys.argv[3], sfx_track(ev, float(sys.argv[4])))
