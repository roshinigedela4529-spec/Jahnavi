"""Synthesises the soundtrack for the Kaveri birthday video (original score, no samples).

96 BPM (beat 0.625 s, bar 2.5 s) so every scene cut lands on a bar line.
The finale plays the traditional "Happy Birthday" melody (public domain) on a music box.
usage: python3 music.py out.wav
"""
import sys
import numpy as np

SR = 44100
DUR = 63.0
BEAT = 60 / 96
BAR = BEAT * 4
N = int(SR * DUR)
L = np.zeros(N); R = np.zeros(N)
rs = np.random.default_rng(5)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def add(sig, t0, gain=1.0, pan=0.0):
    i = int(t0 * SR)
    if i >= N:
        return
    sig = sig[: N - i]
    lg, rg = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    L[i:i + len(sig)] += sig * gain * lg * 1.414
    R[i:i + len(sig)] += sig * gain * rg * 1.414


def env(n, a, d_tau=None, rel=0.05, sustain_len=None):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4))
    if d_tau:
        e *= np.exp(-t / d_tau)
    if sustain_len is not None:
        e *= np.clip((sustain_len + rel - t) / rel, 0, 1)
    return e


# ---------------- instruments ----------------
def bell(m, dur=2.2, bright=1.0):
    f = mtof(m); n = int(dur * SR); t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * f * t) * np.exp(-t / 1.1)
         + 0.45 * bright * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.6)
         + 0.18 * bright * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t / 0.35)
         + 0.10 * bright * np.sin(2 * np.pi * 4.2 * f * t) * np.exp(-t / 0.18))
    return s * np.minimum(1, t / 0.004)


def musicbox(m, dur=1.8):
    f = mtof(m); n = int(dur * SR); t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * f * t) * np.exp(-t / 0.9)
         + 0.3 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / 0.4)
         + 0.25 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t / 0.08))
    return s * np.minimum(1, t / 0.002)


def pluck(m, dur=0.8):
    f = mtof(m); n = int(dur * SR); t = np.arange(n) / SR
    s = sum((0.6 ** (k - 1)) * np.sin(2 * np.pi * k * f * t) * np.exp(-t * (3 + 4 * k)) for k in range(1, 6))
    return s * np.minimum(1, t / 0.003)


def pad(notes, dur, attack=0.8, release=1.2):
    n = int((dur + release) * SR); t = np.arange(n) / SR
    s = np.zeros(n)
    for m in notes:
        f = mtof(m)
        for det in (-0.12, 0.0, 0.11):
            ff = f * 2 ** (det / 12)
            ph = rs.random() * 6.28
            for k in range(1, 7):
                s += (0.55 ** k) * np.sin(2 * np.pi * k * ff * t + ph * k)
    lfo = 1 + 0.08 * np.sin(2 * np.pi * 0.25 * t)
    e = np.minimum(1, t / attack) * np.clip((dur + release - t) / release, 0, 1)
    return s * e * lfo / (len(notes) * 3)


def bass(m, dur):
    f = mtof(m); n = int((dur + 0.1) * SR); t = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)
    return s * np.minimum(1, t / 0.01) * np.exp(-t / 0.9) * np.clip((dur + 0.1 - t) / 0.1, 0, 1)


def kick():
    n = int(0.45 * SR); t = np.arange(n) / SR
    f = 45 + 90 * np.exp(-t / 0.03)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / 0.16)


def hp_noise(n, k=1):
    x = rs.standard_normal(n)
    for _ in range(k):
        x = np.diff(x, prepend=0)
    return x / (2 ** k)


def clap():
    n = int(0.3 * SR); t = np.arange(n) / SR
    x = hp_noise(n, 1)
    e = np.exp(-t / 0.07)
    for d in (0.0, 0.012, 0.024):
        e += np.exp(-np.maximum(t - d, 0) / 0.008) * (t >= d) * 0.6
    return x * e * 0.6


def shaker():
    n = int(0.12 * SR); t = np.arange(n) / SR
    return hp_noise(n, 2) * np.minimum(1, t / 0.01) * np.exp(-t / 0.035)


def riser(dur):
    n = int(dur * SR); t = np.arange(n) / SR
    k = t / dur
    f = 200 + 1800 * k ** 2
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = sum(np.sin(ph * h) / h for h in (1, 2, 3))
    noise = hp_noise(n, 1)
    return (0.25 * tone + 0.8 * noise) * k ** 2.2


def impact():
    n = int(3.0 * SR); t = np.arange(n) / SR
    f = 38 + 60 * np.exp(-t / 0.08)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.9)
    shimmer = hp_noise(n, 2) * np.exp(-t / 1.2) * 0.5
    return boom + shimmer


def chime_sweep(start_m=84, count=10, step=0.05):
    out = np.zeros(int((count * step + 2.5) * SR))
    scale = [0, 2, 4, 7, 9]
    for i in range(count):
        m = start_m + scale[i % 5] + 12 * (i // 5)
        b = bell(m, 2.0, 0.6) * 0.35
        j = int(i * step * SR); out[j:j + len(b)] += b
    return out


def firework(seed):
    r = np.random.default_rng(seed)
    n = int(1.8 * SR); t = np.arange(n) / SR
    thump = np.sin(2 * np.pi * (60 + 80 * np.exp(-t / 0.02)) * t) * np.exp(-t / 0.12)
    crack = np.zeros(n)
    for _ in range(70):
        c = int(r.uniform(0.15, 1.5) * SR); ln = int(0.006 * SR)
        if c + ln < n:
            crack[c:c + ln] += r.standard_normal(ln) * r.uniform(0.2, 1) * np.exp(-(c / SR - 0.15) / 0.8)
    crack = np.diff(crack, prepend=0)
    return thump * 0.7 + crack * 0.5


# ---------------- arrangement ----------------
PROG = [[53, 57, 60, 65], [48, 55, 60, 64], [50, 57, 62, 65], [46, 53, 58, 62]]   # F  C  Dm  Bb
ROOT = [41, 36, 38, 34]
ARP_PAT = [0, 2, 3, 1, 2, 3, 1, 2]
MEL = [(0, 69, 1), (1, 72, 1), (2, 77, 2), (4, 76, 1), (5, 74, 1), (6, 72, 2),
       (8, 74, 1), (9, 77, 1), (10, 81, 1), (11, 79, 1), (12, 77, 3), (15, 72, 1)]
MEL_B = [(0, 81, 1), (1, 79, 1), (2, 77, 2), (4, 79, 1), (5, 76, 1), (6, 72, 2),
         (8, 74, 1), (9, 77, 1), (10, 81, 1.5), (11.5, 84, .5), (12, 81, 2), (14, 77, 2)]

FINALE = 50.0
nbars = int(FINALE / BAR)
for b in range(nbars):
    t0 = b * BAR
    ch = PROG[b % 4]
    breakdown = 40 <= t0 < 45
    full = (10 <= t0 < 40) or (45 <= t0 < 50)
    add(pad([m + 12 for m in ch], BAR, attack=1.2 if t0 < 5 else 0.4), t0, 0.22 if t0 >= 5 else 0.16 * min(1, t0 / 2.5 + .4), 0)
    # music-box intro sparkle
    if t0 < 5:
        for i, s in enumerate([0, 2, 3, 1]):
            add(bell(ch[s] + 24, 2.5, 0.5), t0 + i * BEAT, 0.10, (-0.5, 0.5)[i % 2])
    # arpeggio
    if t0 >= 5:
        for i in range(8):
            m = ch[ARP_PAT[i]] + 12 + (12 if i >= 4 and b % 2 else 0)
            add(pluck(m), t0 + i * BEAT / 2, 0.14 if not breakdown else 0.10, 0.45 * np.sin(i * 1.3))
    # bass + drums
    if full:
        add(bass(ROOT[b % 4], BEAT * 1.9), t0, 0.40)
        add(bass(ROOT[b % 4] + (7 if b % 2 else 12), BEAT * 1.9), t0 + 2 * BEAT, 0.30)
        for q in range(4):
            if q in (0, 2):
                add(kick(), t0 + q * BEAT, 0.55)
            else:
                add(clap(), t0 + q * BEAT, 0.16, 0.1)
        for e8 in range(8):
            add(shaker(), t0 + e8 * BEAT / 2 + 0.01, 0.07 if e8 % 2 else 0.04, 0.35)
    if breakdown:
        add(bass(ROOT[b % 4], BAR), t0, 0.25)

# lead melody (bells) — two phrases, played over the photo scenes and the collage
for start in (10.0, 20.0, 30.0, 45.0):
    phrase = MEL if start in (10.0, 30.0) else MEL_B
    for (bt, m, ln) in phrase:
        if start + bt * BEAT < (40 if start < 40 else 50):
            add(bell(m, 1.5 + ln * BEAT), start + bt * BEAT, 0.20, -0.15)
# breakdown melody (date scene) — softer, an octave up
for (bt, m, ln) in MEL[:8]:
    add(bell(m + 12, 2.0, 0.5), 40 + bt * BEAT, 0.12, 0.2)

# risers & impacts on key cuts
add(riser(3.5), 5 - 3.5, 0.18)
add(impact(), 5.0, 0.55)
add(chime_sweep(84, 12, 0.045), 5.0, 0.5, 0.2)
for c in (10, 17.5, 25, 32.5, 40, 45):
    add(chime_sweep(84 + (2 if c % 5 else 0), 6, 0.04), c - 0.12, 0.35, 0.4 * (1 if c % 5 else -1))
add(riser(BAR * 0.9), 45 - BAR * 0.9, 0.14)
add(riser(BAR * 1.0), FINALE - BAR, 0.18)
add(impact(), FINALE, 0.5)
add(chime_sweep(84, 14, 0.04), FINALE, 0.5)

# ---------------- finale: Happy Birthday (traditional, public domain) on music box ----------------
HB_BEAT = 0.45
HB_START = 50.6
# (beat, midi, length) in F major, 3/4, pickup on beat 0
HB = [(0, 72, .75), (.75, 72, .25), (1, 74, 1), (2, 72, 1), (3, 77, 1), (4, 76, 2),
      (6, 72, .75), (6.75, 72, .25), (7, 74, 1), (8, 72, 1), (9, 79, 1), (10, 77, 2),
      (12, 72, .75), (12.75, 72, .25), (13, 84, 1), (14, 81, 1), (15, 77, 1), (16, 76, 1), (17, 74, 1),
      (18, 82, .75), (18.75, 82, .25), (19, 81, 1), (20, 77, 1), (21, 79, 1), (22, 77, 3)]
for (bt, m, ln) in HB:
    add(musicbox(m, 2.2), HB_START + bt * HB_BEAT, 0.34, -0.1)
    add(bell(m + 12, 1.4, 0.3), HB_START + bt * HB_BEAT, 0.06, 0.3)
# accompaniment: one chord per 3/4 bar (bar starts at beat 1, 4, 7, ...)
HB_CH = [[53, 57, 60], [48, 52, 55, 58], [48, 52, 55, 58], [53, 57, 60], [53, 57, 60, 63], [46, 50, 53], [53, 57, 60], [48, 52, 55], [53, 57, 60, 65]]
HB_ROOT = [41, 36, 36, 41, 41, 34, 41, 36, 41]
for i, (ch, rt) in enumerate(zip(HB_CH, HB_ROOT)):
    t0 = HB_START + (1 + 3 * i) * HB_BEAT
    last = i == len(HB_CH) - 1
    add(pad([m + 12 for m in ch], 3 * HB_BEAT * (3 if last else 1), attack=0.15, release=2.5 if last else 0.6), t0, 0.22)
    add(bass(rt, 3 * HB_BEAT * (3 if last else 1)), t0, 0.32)
    for k in (1, 2):
        if not last:
            add(pluck(ch[k % len(ch)] + 12, 0.6), t0 + k * HB_BEAT, 0.10, 0.4 * (-1) ** k)
    if not last:
        add(kick(), t0, 0.30)
add(chime_sweep(91, 15, 0.05), HB_START + 22 * HB_BEAT, 0.45)


# fireworks (times mirror scene.html: mulberry32(99), 5 draws per firework, first one is the time)
def mulberry32(seed):
    st = [seed & 0xFFFFFFFF]

    def r():
        st[0] = (st[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = st[0]
        t = ((t ^ (t >> 15)) * (1 | t)) & 0xFFFFFFFF
        t = (t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF) ^ t) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return r


r = mulberry32(99)
for i in range(16):
    ft = 51.4 + i * BEAT * 1.4 + r() * 0.2
    fx = r(); r(); r(); r()
    add(firework(i), ft, 0.22, (fx - 0.5) * 1.4)

# ---------------- reverb + master ----------------
def reverb(x, seed, secs=2.6):
    n = int(secs * SR); t = np.arange(n) / SR
    ir = np.random.default_rng(seed).standard_normal(n) * np.exp(-t / 0.55)
    ir = np.convolve(ir, np.ones(8) / 8, mode='same')   # darken the tail
    ir[0] = 0
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    return y / np.sqrt(np.sum(ir ** 2))


wetL, wetR = reverb(L, 1), reverb(R, 2)
outL = L + 0.28 * wetL
outR = R + 0.28 * wetR
t = np.arange(N) / SR
fade = np.minimum(1, t / 0.6) * np.clip((DUR - t) / 1.8, 0, 1)
outL *= fade; outR *= fade
peak = max(np.abs(outL).max(), np.abs(outR).max())
outL = np.tanh(outL / peak * 1.25) * 0.89
outR = np.tanh(outR / peak * 1.25) * 0.89
pcm = (np.stack([outL, outR], 1) * 32767).astype('<i2')

import wave
with wave.open(sys.argv[1] if len(sys.argv) > 1 else 'music.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print('wrote', DUR, 's')
