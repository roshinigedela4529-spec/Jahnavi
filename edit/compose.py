"""Frame-by-frame compositor for the DMart Facts edit.

Timeline (EDL) + kinetic typography + 2D motion graphics + keyed presenter.
Usage: python3 compose.py <worker_idx> <n_workers> <outdir>   (renders a contiguous chunk to mp4)
       python3 compose.py still <t> <out.png>                  (debug single frame)
"""
import math
import os
import subprocess
import sys
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FPS = 30000 / 1001
SRC = os.environ.get("SRC", "/root/.claude/uploads/a9449ec5-5d9b-5035-a2b7-72e9b08c4c2d/8a9e45e7-DMART_Facts_video_Green_Screen.mp4")
WORK = os.environ.get("WORK", "/tmp/claude-0/-home-user-Jahnavi/a9449ec5-5d9b-5035-a2b7-72e9b08c4c2d/scratchpad")
RENDERS = os.path.join(WORK, "renders")
DUR = 225.5253
NFRAMES = int(round(DUR * FPS))

F_BLACK = "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"
F_XBOLD = "/usr/share/fonts/opentype/inter/InterDisplay-ExtraBold.otf"
F_BOLD = "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf"
F_SEMI = "/usr/share/fonts/opentype/inter/InterDisplay-SemiBold.otf"
F_RUPEE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

GREEN = (14, 140, 64)
DGREEN = (6, 48, 26)
YELLOW = (255, 199, 44)
WHITE = (255, 255, 255)
RED = (226, 54, 54)
INK = (8, 18, 13)


# ------------------------------------------------------------------ easing / utils
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return 3 * x * x - 2 * x * x * x


def ease_back(x, s=1.7):
    x = clamp(x)
    x -= 1
    return x * x * ((s + 1) * x + s) + 1


def lerp(a, b, t):
    return a + (b - a) * t


@lru_cache(None)
def font(path, size):
    return ImageFont.truetype(path, size)


def fnt(size, w="black"):
    return font({"black": F_BLACK, "xbold": F_XBOLD, "bold": F_BOLD, "semi": F_SEMI, "rupee": F_RUPEE}[w], int(size))


def text_size(txt, f, spacing=0):
    b = f.getbbox(txt)
    return b[2] - b[0] + spacing * max(0, len(txt) - 1), b[3] - b[1], b


@lru_cache(512)
def text_sprite(txt, size, color=WHITE, weight="black", shadow=True, stroke=0, stroke_color=INK, track=0):
    f = fnt(size, weight)
    if "₹" in txt and weight != "rupee":
        # draw rupee with DejaVu, rest with Inter
        parts = txt.split("₹")
        sprites = []
        for i, p in enumerate(parts):
            if i:
                sprites.append(text_sprite("₹", int(size * 0.92), color, "rupee", False, stroke, stroke_color))
            if p:
                sprites.append(text_sprite(p, size, color, weight, False, stroke, stroke_color, track))
        wsum = sum(s.width for s in sprites)
        hmax = max(s.height for s in sprites)
        im = Image.new("RGBA", (wsum, hmax))
        x = 0
        for s in sprites:
            im.alpha_composite(s, (x, (hmax - s.height) // 2))
            x += s.width
        return _shadow(im, size) if shadow else im
    tw, th, bb = text_size(txt, f)
    pad = int(size * 0.25) + stroke
    im = Image.new("RGBA", (tw + track * len(txt) + 2 * pad, int(size * 1.25) + 2 * pad))
    d = ImageDraw.Draw(im)
    if track:
        x = pad
        for ch in txt:
            d.text((x - bb[0], pad - f.getbbox("H")[1] + int(size * 0.05)), ch, font=f, fill=color,
                   stroke_width=stroke, stroke_fill=stroke_color)
            x += f.getlength(ch) + track
    else:
        d.text((pad - bb[0], pad - f.getbbox("H")[1] + int(size * 0.05)), txt, font=f, fill=color,
               stroke_width=stroke, stroke_fill=stroke_color)
    im = im.crop(im.getbbox() or (0, 0, 1, 1))
    im = _padded(im, int(size * 0.12))
    return _shadow(im, size) if shadow else im


def _padded(im, p):
    o = Image.new("RGBA", (im.width + 2 * p, im.height + 2 * p))
    o.alpha_composite(im, (p, p))
    return o


def _shadow(im, size):
    p = max(6, int(size * 0.18))
    o = Image.new("RGBA", (im.width + 2 * p, im.height + 2 * p))
    a = im.split()[3].point(lambda v: v * 0.55)
    sh = Image.new("RGBA", im.size, (0, 0, 0, 255))
    sh.putalpha(a)
    o.alpha_composite(sh, (p, p + max(2, size // 22)))
    o = o.filter(ImageFilter.GaussianBlur(max(2, size // 14)))
    o.alpha_composite(im, (p, p))
    return o


def put(base, sprite, cx, cy, alpha=1.0, scale=1.0, anchor="c"):
    if alpha <= 0.003 or sprite is None:
        return
    s = sprite
    if abs(scale - 1) > 0.002:
        s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.BILINEAR)
    if alpha < 0.997:
        a = s.split()[3].point(lambda v: int(v * alpha))
        s = s.copy()
        s.putalpha(a)
    if anchor == "c":
        x, y = int(cx - s.width / 2), int(cy - s.height / 2)
    elif anchor == "l":
        x, y = int(cx), int(cy - s.height / 2)
    else:
        x, y = int(cx - s.width), int(cy - s.height / 2)
    base.alpha_composite(s, (x, y)) if (x >= 0 and y >= 0 and x + s.width <= base.width and y + s.height <= base.height) \
        else _safe_paste(base, s, x, y)


def _safe_paste(base, s, x, y):
    l, t = max(0, x), max(0, y)
    r, b = min(base.width, x + s.width), min(base.height, y + s.height)
    if r <= l or b <= t:
        return
    base.alpha_composite(s.crop((l - x, t - y, r - x, b - y)), (l, t))


@lru_cache(256)
def pill(w, h, color, radius=None, outline=None, ow=0):
    im = Image.new("RGBA", (int(w), int(h)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, int(w) - 1, int(h) - 1), radius=radius if radius is not None else int(h) // 2,
                        fill=color, outline=outline, width=ow)
    return im


def label_pill(txt, size, fg=WHITE, bg=GREEN, weight="black", padx=None, pady=None):
    t = text_sprite(txt, size, fg, weight, shadow=False)
    padx = padx if padx is not None else int(size * 0.45)
    pady = pady if pady is not None else int(size * 0.12)
    p = pill(t.width + 2 * padx, t.height + 2 * pady, bg, radius=int(size * 0.28))
    p = p.copy()
    p.alpha_composite(t, (padx, pady))
    return _shadow(p, size)


# ------------------------------------------------------------------ backgrounds
@lru_cache(4)
def mg_bg(variant=0):
    """Dark green studio gradient with perspective floor grid (static base)."""
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(-1, 1, W)[None, :]
    r = np.sqrt(x ** 2 * 0.6 + (y - 0.42) ** 2 * 1.6)
    c0 = np.array([18, 92, 52]) if variant == 0 else np.array([20, 60, 95])
    c1 = np.array([3, 14, 9])
    k = np.clip(r, 0, 1)[..., None]
    img = c0 * (1 - k) ** 1.4 + c1 * (1 - (1 - k) ** 1.4)
    im = Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert("RGBA")
    # perspective grid
    g = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(g)
    hz = 640
    for i in range(-30, 31):
        x0 = W / 2 + i * 60
        x1 = W / 2 + i * 600
        d.line((x0, hz, x1, H + 400), fill=(80, 255, 160, 34), width=2)
    for j in range(1, 16):
        yy = hz + (H - hz) * (j / 15) ** 2.2
        d.line((0, yy, W, yy), fill=(80, 255, 160, int(10 + 30 * j / 15)), width=2)
    fade = Image.linear_gradient("L").resize((W, H))
    a = np.asarray(g.split()[3]).astype(np.float32) * np.clip((np.arange(H)[:, None] - hz) / 300, 0, 1)
    g.putalpha(Image.fromarray(a.astype(np.uint8)))
    im.alpha_composite(g)
    return im


_PART = np.random.default_rng(4).uniform(0, 1, (40, 4))


def mg_frame(t, variant=0):
    im = mg_bg(variant).copy()
    d = ImageDraw.Draw(im, "RGBA")
    for px, py, ps, sp in _PART:  # drifting bokeh
        x = (px * W + t * 25 * (sp - 0.5)) % W
        y = (py * H - t * 18 * (0.3 + sp)) % H
        r = 2 + ps * 7
        d.ellipse((x - r, y - r, x + r, y + r), fill=(170, 255, 200, int(25 + 40 * ps)))
    return im


@lru_cache(1)
def studio_bg():
    p = os.path.join(RENDERS, "studiobg", "studiobg.png")
    if os.path.exists(p):
        im = Image.open(p).convert("RGB").resize((int(W * 1.12), int(H * 1.12)), Image.LANCZOS)
        im = im.filter(ImageFilter.GaussianBlur(9))
        arr = np.asarray(im).astype(np.float32) * 0.72
        return Image.fromarray(arr.clip(0, 255).astype(np.uint8)).convert("RGBA")
    return mg_bg(0).resize((int(W * 1.12), int(H * 1.12)))


# ------------------------------------------------------------------ presenter (chroma key)
class Source:
    def __init__(self, start_frame):
        self.proc = subprocess.Popen(
            ["ffmpeg", "-v", "error", "-ss", f"{start_frame / FPS:.4f}", "-i", SRC, "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, bufsize=W * H * 3 * 2)
        self.idx = start_frame - 1
        self.cur = None

    def get(self, frame):
        while self.idx < frame:
            buf = self.proc.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            self.cur = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
            self.idx += 1
        return self.cur


_YY = np.arange(H)[:, None]
_LUT = None


def grade_lut():
    global _LUT
    if _LUT is None:
        x = np.arange(256) / 255.0
        s = x + 0.12 * np.sin(2 * np.pi * x) * x * (1 - x) * 2  # gentle S-curve
        s = np.clip((s - 0.02) / 0.97, 0, 1)
        r = np.clip(s * 1.02 + 0.005, 0, 1)
        g = s
        b = np.clip(s * 0.96 + 0.01, 0, 1)
        _LUT = [(c * 255).astype(np.uint8) for c in (r, g, b)]
    return _LUT


def key_presenter(rgb):
    a = rgb.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = np.maximum(r, b)
    gs = g - mx
    alpha = 1 - np.clip((gs - 8) / 18.0, 0, 1)
    lum = (r + g + b) // 3
    sat = a.max(2) - a.min(2)
    desk = (_YY > 930) & (lum > 170) & (sat < 50)
    alpha[desk] = 0
    al = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5)).filter(
        ImageFilter.GaussianBlur(1.4))
    g2 = np.where(g > mx, mx + (g - mx) // 8, g)
    lut = grade_lut()
    out = np.stack([lut[0][r.clip(0, 255)], lut[1][g2.clip(0, 255)], lut[2][b.clip(0, 255)]], 2)
    im = Image.fromarray(out.astype(np.uint8)).convert("RGBA")
    # soft fade at bottom so the cut-off desk line never shows
    al_arr = np.asarray(al).astype(np.float32)
    al_arr *= np.clip((1060 - _YY) / 70.0, 0, 1)
    im.putalpha(Image.fromarray(al_arr.astype(np.uint8)))
    return im


def presenter_frame(src_rgb, t_local, dur, shift=0.0, zoom_dir=1):
    bgs = studio_bg()
    # slow drift on background
    k = t_local / max(dur, 0.1)
    ox = int((bgs.width - W) * (0.5 + 0.3 * math.sin(k * 1.4 + zoom_dir)))
    oy = int((bgs.height - H) * 0.5)
    base = bgs.crop((ox, oy, ox + W, oy + H)).copy()
    fg = key_presenter(src_rgb)
    # gentle push-in for dynamism
    sc = 1.0 + 0.045 * ease_io(k) if zoom_dir > 0 else 1.045 - 0.045 * ease_io(k)
    fgs = fg.resize((int(W * sc), int(H * sc)), Image.BILINEAR)
    x = int((W - fgs.width) / 2 + shift)
    y = int(H - fgs.height + 10)
    # ground shadow / rim glow
    glow = Image.new("RGBA", (W, H))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((W / 2 - 520 + shift, 860, W / 2 + 520 + shift, 1220), fill=(0, 0, 0, 120))
    base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)))
    _safe_paste(base, fgs, x, y)
    return base


# ------------------------------------------------------------------ 3D clips
@lru_cache(None)
def clip_count(name):
    d = os.path.join(RENDERS, name)
    return len([f for f in os.listdir(d) if f.startswith("f_")]) if os.path.isdir(d) else 0


def clip_frame(name, t_local, dur, nframes):
    n = clip_count(name) or nframes
    f = 1 + int(clamp(t_local / dur) * (n - 1) + 0.5)
    p = os.path.join(RENDERS, name, f"f_{f:04d}.png")
    if not os.path.exists(p):
        return mg_frame(t_local)
    im = Image.open(p).convert("RGB")
    im = im.resize((W, H), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 2))
    return im.convert("RGBA")


# ------------------------------------------------------------------ overlay elements
def anim_in_out(t, t0, t1, din=0.45, dout=0.3):
    if t < t0 or t > t1:
        return 0.0, 0.0
    a_in = clamp((t - t0) / din)
    a_out = clamp((t1 - t) / dout)
    return a_in, a_out


def ov_headline(base, t, t0, t1, lines, y=540, x=W / 2, size=110, stagger=0.14, hl=None, anchor="c"):
    """lines: list of (text, size_mult, color, style) style in {'plain','pill','yellowpill'}."""
    n = len(lines)
    total_h = sum(int(size * m * 1.18) for _, m, _, _ in lines)
    yy = y - total_h / 2
    for i, (txt, m, col, style) in enumerate(lines):
        s = int(size * m)
        lh = int(s * 1.18)
        a_in, a_out = anim_in_out(t, t0 + i * stagger, t1)
        if a_in > 0:
            e = ease_back(a_in)
            alpha = clamp(a_in * 2.5) * ease_out(a_out)
            if style == "pill":
                spr = label_pill(txt, s, WHITE, GREEN)
            elif style == "yellowpill":
                spr = label_pill(txt, s, INK, YELLOW)
            elif style == "redpill":
                spr = label_pill(txt, s, WHITE, RED)
            else:
                spr = text_sprite(txt, s, col)
            put(base, spr, x + (0 if anchor == "c" else 0), yy + lh / 2 + (1 - e) * 60, alpha, 0.85 + 0.15 * e,
                anchor=anchor)
        yy += lh


def ov_chips(base, t, items, y, t1, size=54, gap=28, x=W / 2):
    sprites = [label_pill(txt, size, INK if bg == YELLOW else WHITE, bg) for txt, _, bg in items]
    total = sum(s.width for s in sprites) + gap * (len(sprites) - 1)
    cx = x - total / 2
    for (txt, ts, bg), s in zip(items, sprites):
        a_in, a_out = anim_in_out(t, ts, t1, 0.35, 0.3)
        if a_in > 0:
            e = ease_back(a_in, 2.5)
            put(base, s, cx + s.width / 2, y, clamp(a_in * 3) * a_out, 0.5 + 0.5 * e)
        cx += s.width + gap


def ov_card(base, t, t0, t1, kicker, value, sub, value_color=YELLOW, x=1500):
    """Glass info card on the right side of presenter shots."""
    a_in, a_out = anim_in_out(t, t0, t1, 0.55, 0.35)
    if a_in <= 0:
        return
    e = ease_out(a_in)
    cw, ch = 640, 470
    card = Image.new("RGBA", (cw, ch))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), 36, fill=(6, 30, 18, 205), outline=(120, 255, 170, 120), width=3)
    d.rounded_rectangle((0, 0, 14, ch - 1), 7, fill=GREEN + (255,))
    k = text_sprite(kicker, 40, YELLOW, "xbold", shadow=False, track=3)
    card.alpha_composite(k, (56, 52))
    vt = value
    vs = 150
    v = text_sprite(vt, vs, value_color, "black", shadow=False)
    while v.width > cw - 80:
        vs -= 8
        v = text_sprite(vt, vs, value_color, "black", shadow=False)
    card.alpha_composite(v, (48, 150 + (150 - vs) // 2))
    yy = 330
    for line in sub.split("\n"):
        s = text_sprite(line, 46, WHITE, "bold", shadow=False)
        card.alpha_composite(s, (56, yy))
        yy += 62
    card = _shadow(card, 60)
    put(base, card, x + (1 - e) * 500, 520, ease_out(a_out) * clamp(a_in * 2))


def ov_counter(base, t, t0, t1, v0, v1, fmt, label, y=520, size=170, dur=1.6, color=YELLOW):
    a_in, a_out = anim_in_out(t, t0, t1, 0.35, 0.35)
    if a_in <= 0:
        return
    k = ease_out((t - t0) / dur)
    v = v0 + (v1 - v0) * k
    s = text_sprite(fmt(v), size, color)
    put(base, s, W / 2, y + (1 - ease_out(a_in)) * 40, a_out * clamp(a_in * 2))
    l = label_pill(label, 52, WHITE, GREEN)
    a2, _ = anim_in_out(t, t0 + 0.4, t1)
    if a2 > 0:
        put(base, l, W / 2, y + size * 0.82, a_out * clamp(a2 * 2), 0.6 + 0.4 * ease_back(a2))


def ov_brand(base, t):
    """Small persistent channel bug top-left."""
    s = label_pill("DMART FACTS", 30, WHITE, (14, 140, 64, 220))
    put(base, s, 60, 70, 0.92, anchor="l")


def ov_lower(base, t, t0, t1, title, sub):
    a_in, a_out = anim_in_out(t, t0, t1, 0.5, 0.3)
    if a_in <= 0:
        return
    e = ease_out(a_in)
    ts = text_sprite(title, 64, WHITE, "black", shadow=False)
    ss = text_sprite(sub, 36, INK, "bold", shadow=False)
    w = max(ts.width, ss.width) + 80
    bar = Image.new("RGBA", (w, 190))
    d = ImageDraw.Draw(bar)
    d.rectangle((0, 0, int(w * e), 104), fill=GREEN + (240,))
    d.rectangle((0, 104, int(w * ease_out(a_in * 1.3 - 0.3)), 160), fill=YELLOW + (255,))
    bar.alpha_composite(ts, (40, 16))
    bar.alpha_composite(ss, (40, 110))
    put(base, _shadow(bar, 40), 90, 860, ease_out(a_out), anchor="l")


# ------------------------------------------------------------------ motion-graphic scenes
def bar3d(d, x, y_base, w, h, col, depth=40):
    """Pseudo-3D extruded bar (front, top, side faces)."""
    c = np.array(col)
    top = tuple((c * 1.25).clip(0, 255).astype(int))
    side = tuple((c * 0.6).astype(int))
    d.polygon([(x, y_base - h), (x + depth, y_base - h - depth * 0.6), (x + w + depth, y_base - h - depth * 0.6),
               (x + w, y_base - h)], fill=top)
    d.polygon([(x + w, y_base), (x + w, y_base - h), (x + w + depth, y_base - h - depth * 0.6),
               (x + w + depth, y_base - depth * 0.6)], fill=side)
    d.rectangle((x, y_base - h, x + w, y_base), fill=tuple(col))


def mg_price_compare(t, dur):
    im = mg_frame(t)
    d = ImageDraw.Draw(im)
    ov_headline(im, t, 0.1, dur, [("LOWER PRICES", 1.0, WHITE, "plain"),
                                  ("THAN OTHER SUPERMARKETS", 0.5, WHITE, "pill")], y=170, size=96)
    base_y = 900
    g1 = ease_out((t - 0.6) / 1.2)
    g2 = ease_out((t - 1.1) / 1.2)
    bar3d(d, 520, base_y, 300, int(480 * g1), (200, 60, 55), 60)
    bar3d(d, 1100, base_y, 300, int(300 * g2), (20, 170, 80), 60)
    put(im, text_sprite("OTHER STORES", 46, WHITE, "xbold"), 670, base_y + 50, clamp(g1 * 2))
    put(im, text_sprite("DMART", 50, YELLOW, "black"), 1250, base_y + 50, clamp(g2 * 2))
    put(im, label_pill("₹₹₹", 54, WHITE, RED), 700, base_y - 480 * g1 - 90, clamp(g1 * 2 - 1))
    put(im, label_pill("₹", 54, INK, YELLOW), 1280, base_y - 300 * g2 - 90, clamp(g2 * 2 - 1))
    a = clamp((t - 2.6) / 0.4)
    if a > 0:
        bob = math.sin(t * 5) * 10
        put(im, label_pill("SAVE MORE", 60, INK, YELLOW), 1560, 520 + bob, a, 0.6 + 0.4 * ease_back(a))
    return im


def mg_profit(t, dur):
    im = mg_frame(t)
    d = ImageDraw.Draw(im, "RGBA")
    ov_headline(im, t, 0.1, 4.2, [("LOW PRICES", 1.0, WHITE, "plain"), ("= LOW PROFITS?", 0.62, WHITE, "redpill")],
                y=190, size=100)
    ov_headline(im, t, 4.5, dur, [("DMART: LOW PRICES", 0.8, WHITE, "plain"), ("+ STRONG PROFITS", 0.62, INK, "yellowpill")],
                y=190, size=100)
    # axes
    x0, y0, x1, y1 = 360, 940, 1560, 420
    d.line((x0, y0, x1 + 40, y0), fill=(200, 255, 220, 160), width=4)
    d.line((x0, y0, x0, y1 - 40), fill=(200, 255, 220, 160), width=4)
    for i in range(1, 5):
        yy = y0 - i * (y0 - y1) / 4
        d.line((x0, yy, x1, yy), fill=(200, 255, 220, 30), width=2)
    pts = []
    k = ease_io((t - 1.0) / 6.0)
    N = 60
    for i in range(int(N * k) + 1):
        u = i / N
        val = 0.12 + 0.75 * u ** 1.6 + 0.04 * math.sin(u * 18)
        pts.append((x0 + u * (x1 - x0), y0 - val * (y0 - y1)))
    if len(pts) > 1:
        d.polygon(pts + [(pts[-1][0], y0), (x0, y0)], fill=(30, 220, 110, 60))
        d.line(pts, fill=(60, 255, 140, 255), width=10, joint="curve")
        px, py = pts[-1]
        d.ellipse((px - 16, py - 16, px + 16, py + 16), fill=YELLOW)
        put(im, label_pill("PROFIT ▲", 44, INK, YELLOW), px + 10, py - 70, clamp(k * 3))
    put(im, text_sprite("YEARS", 34, (200, 255, 220), "bold"), x1, y0 + 40, 0.8)
    return im


def silhouette(size=360):
    im = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 0, size - 1, size - 1), fill=(20, 70, 40, 255))
    d.ellipse((size * 0.32, size * 0.16, size * 0.68, size * 0.55), fill=(190, 220, 200, 255))
    d.ellipse((size * 0.12, size * 0.58, size * 0.88, size * 1.25), fill=(190, 220, 200, 255))
    m = Image.new("L", (size, size))
    ImageDraw.Draw(m).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(im, (0, 0), m)
    ImageDraw.Draw(out).ellipse((2, 2, size - 3, size - 3), outline=YELLOW, width=10)
    return out


_SIL = None


def mg_founder(t, dur):
    global _SIL
    im = mg_frame(t, 0)
    if _SIL is None:
        _SIL = _shadow(silhouette(380), 80)
    a = clamp(t / 0.6)
    put(im, _SIL, 560, 470, a, 0.7 + 0.3 * ease_back(a))
    # rotating ring
    d = ImageDraw.Draw(im, "RGBA")
    ang = t * 40
    d.arc((560 - 245, 470 - 245, 560 + 245, 470 + 245), ang, ang + 250, fill=(60, 255, 140, 200), width=6)
    ov_headline(im, t, 0.5, dur, [("THE FOUNDER", 0.42, INK, "yellowpill"), ("RADHAKISHAN", 1.0, WHITE, "plain"),
                                  ("DAMANI", 1.0, WHITE, "plain")], y=400, x=880, size=118, anchor="l")
    ov_chips(im, t, [("FIRST STORE: 2002", 1.6, GREEN), ("POWAI, MUMBAI", 2.0, GREEN)], 690, dur, size=44, x=1250)
    ov_chips(im, t, [("RETAIL RESEARCH", 5.5, (20, 60, 95)), ("3 SMART STRATEGIES", 8.0, YELLOW)], 820, dur,
             size=50, x=1060)
    return im


def icon_card(kind, size=300):
    im = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size - 1, size - 1), 40, fill=(10, 40, 25, 230), outline=(120, 255, 170, 140), width=4)
    c = (230, 240, 235)
    s = size
    if kind == "tv":
        d.rounded_rectangle((s * .18, s * .25, s * .82, s * .65), 12, outline=c, width=12)
        d.rectangle((s * .45, s * .65, s * .55, s * .75), fill=c)
        d.rectangle((s * .33, s * .75, s * .67, s * .79), fill=c)
        d.rounded_rectangle((s * .62, s * .40, s * .72, s * .78), 8, fill=(10, 40, 25), outline=c, width=7)
    elif kind == "ring":
        d.ellipse((s * .28, s * .38, s * .72, s * .82), outline=(255, 205, 80), width=16)
        d.polygon([(s * .5, s * .38), (s * .38, s * .26), (s * .44, s * .18), (s * .56, s * .18), (s * .62, s * .26)],
                  fill=(170, 230, 255))
    elif kind == "crown":
        d.polygon([(s * .2, s * .7), (s * .2, s * .32), (s * .35, s * .5), (s * .5, s * .26), (s * .65, s * .5),
                   (s * .8, s * .32), (s * .8, s * .7)], fill=(255, 205, 80))
        d.rectangle((s * .2, s * .72, s * .8, s * .8), fill=(255, 205, 80))
    return im


_ICONS = {}


def mg_no_luxury(t, dur):
    im = mg_frame(t, 1)
    ov_headline(im, t, 0.05, dur, [("NO EXPENSIVE ITEMS", 0.9, WHITE, "plain")], y=150, size=100)
    labels = [("tv", "ELECTRONICS"), ("ring", "JEWELLERY"), ("crown", "LUXURY")]
    for i, (k, lab) in enumerate(labels):
        if k not in _ICONS:
            _ICONS[k] = _shadow(icon_card(k, 300), 60)
        cx = 560 + i * 400
        a = clamp((t - 0.3 - i * 0.35) / 0.4)
        put(im, _ICONS[k], cx, 470, a, 0.6 + 0.4 * ease_back(a))
        put(im, text_sprite(lab, 44, WHITE, "xbold"), cx, 665, a)
        ax = clamp((t - 1.6 - i * 0.45) / 0.25)
        if ax > 0:
            xs = Image.new("RGBA", (300, 300))
            dd = ImageDraw.Draw(xs)
            dd.line((40, 40, 260, 260), fill=RED, width=34)
            dd.line((260, 40, 40, 260), fill=RED, width=34)
            put(im, _shadow(xs, 50), cx, 470, ax, 1.6 - 0.6 * ease_out(ax))
    ov_chips(im, t, [("FOOD ✓", 4.4, GREEN), ("CLOTHES ✓", 4.7, GREEN), ("HOUSEHOLD ✓", 5.0, GREEN)], 860, dur,
             size=56)
    return im


def mg_flow(t, dur, nodes, title, times, sub_title=None):
    im = mg_frame(t)
    d = ImageDraw.Draw(im, "RGBA")
    ov_headline(im, t, 0.05, dur, title, y=170, size=96)
    n = len(nodes)
    xs = [W / 2 + (i - (n - 1) / 2) * 560 for i in range(n)]
    y = 560
    for i in range(n - 1):
        k = ease_io((t - times[i] - 0.3) / 0.7)
        if k > 0:
            xa, xb = xs[i] + 190, xs[i + 1] - 190
            xe = lerp(xa, xb, k)
            d.line((xa, y, xe, y), fill=(255, 199, 44, 255), width=12)
            d.polygon([(xe + 26, y), (xe - 8, y - 24), (xe - 8, y + 24)], fill=YELLOW)
            # coin travelling along
            if k >= 1:
                u = ((t - times[i]) * 0.7) % 1
                cxp = lerp(xa, xb, u)
                d.ellipse((cxp - 18, y - 60, cxp + 18, y - 24), fill=(255, 205, 80), outline=(180, 120, 20), width=4)
    for i, (txt, col) in enumerate(nodes):
        a = clamp((t - times[i]) / 0.45)
        if a <= 0:
            continue
        circ = Image.new("RGBA", (340, 340))
        cd = ImageDraw.Draw(circ)
        cd.ellipse((0, 0, 339, 339), fill=col + (240,), outline=(255, 255, 255, 200), width=6)
        yy = 170 - (len(txt) - 1) * 32
        for line in txt:
            s = text_sprite(line, 52, WHITE if col != YELLOW else INK, "black", shadow=False)
            circ.alpha_composite(s, (170 - s.width // 2, int(yy - s.height / 2)))
            yy += 64
        put(im, _shadow(circ, 60), xs[i], y, a, 0.5 + 0.5 * ease_back(a))
    if sub_title:
        ov_headline(im, t, sub_title[1], dur, [(sub_title[0], 0.6, INK, "yellowpill")], y=900, size=100)
    return im


def mg_savings(t, dur):
    return mg_flow(t, dur, [(["LOW", "COSTS"], GREEN), (["MORE", "SAVINGS"], (20, 90, 160)),
                            (["DISCOUNTS", "FOR YOU"], YELLOW)],
                   [("WHERE THE SAVINGS GO", 0.85, WHITE, "plain")], [0.3, 1.6, 2.9],
                   ("CHEAPER PRICES EVERY DAY", 4.2))


def mg_payment(t, dur):
    im = mg_flow(t, dur, [(["PAYS IN", "15–20 DAYS"], GREEN), (["SUPPLIER", "DISCOUNTS"], (20, 90, 160)),
                          (["LOWER", "PRICES"], YELLOW)],
                 [("FAST PAYMENTS = BETTER DEALS", 0.8, WHITE, "plain")], [0.3, 2.6, 5.2],
                 ("SAVINGS PASSED TO CUSTOMERS", 7.5))
    return im


def mg_strategy(t, dur, num, title, sub):
    im = mg_frame(t)
    a = clamp(t / 0.5)
    big = text_sprite(f"0{num}", 520, (40, 190, 100), "black", shadow=False)
    put(im, big, W / 2 + (1 - ease_out(a)) * 300, 520, 0.35 * a, 1.0 + 0.04 * t)
    ov_headline(im, t, 0.15, dur, [(f"STRATEGY 0{num}", 0.42, INK, "yellowpill"), (title, 1.0, WHITE, "plain"),
                                   (sub, 0.45, WHITE, "pill")], y=540, size=120, stagger=0.2)
    return im


def mg_donut(t, dur):
    im = mg_frame(t)
    ov_headline(im, t, 0.05, dur, [("DMART OWNS ITS STORES", 0.85, WHITE, "plain")], y=150, size=100)
    k = ease_io((t - 0.4) / 2.0)
    cx, cy, R = 700, 590, 290
    ring = Image.new("RGBA", (2 * R + 40, 2 * R + 40))
    d = ImageDraw.Draw(ring)
    box = (20, 20, 2 * R + 20, 2 * R + 20)
    d.ellipse(box, outline=(255, 255, 255, 40), width=70)
    if k > 0:
        d.arc(box, -90, -90 + 324 * k, fill=(40, 200, 100), width=70)
    k2 = ease_io((t - 2.2) / 0.8)
    if k2 > 0:
        d.arc(box, 234, 234 + 36 * k2, fill=(150, 160, 155), width=70)
    put(im, _shadow(ring, 60), cx, cy, clamp(t / 0.3))
    put(im, text_sprite(f"{int(round(90 * k))}%", 150, YELLOW), cx, cy - 10, clamp(t / 0.3))
    for i, (pct, lab, col, t0) in enumerate([("90%", "OWNED", GREEN, 1.4), ("10%", "RENTED", (120, 130, 125), 2.6)]):
        a = clamp((t - t0) / 0.4)
        if a > 0:
            put(im, label_pill(pct, 80, WHITE, col), 1150, 470 + i * 200, a, 0.6 + 0.4 * ease_back(a), anchor="l")
            put(im, text_sprite(lab, 64, WHITE, "black"), 1420, 470 + i * 200, a, anchor="l")
    return im


MG = {
    "price_compare": mg_price_compare, "profit": mg_profit, "founder": mg_founder, "no_luxury": mg_no_luxury,
    "savings": mg_savings, "payment": mg_payment, "donut": mg_donut,
    "strat2": lambda t, d: mg_strategy(t, d, 2, "OWN, DON'T RENT", "NO MONTHLY RENT"),
    "strat3": lambda t, d: mg_strategy(t, d, 3, "PAY SUPPLIERS FAST", "BETTER BUYING PRICES"),
}


# ------------------------------------------------------------------ the timeline
# (start, end, kind, arg)   kind: pres | clip | mg
SHOTS = [
    (0.0, 7.0, "clip", ("exterior", 210)),
    (7.0, 14.8, "pres", {}),
    (14.8, 22.4, "mg", "price_compare"),
    (22.4, 28.0, "pres", {"shift": -330}),
    (28.0, 37.6, "clip", ("aisleA", 285)),
    (37.6, 41.6, "clip", ("twin", 120)),
    (41.6, 50.6, "clip", ("growth", 270)),
    (50.6, 58.4, "pres", {"shift": -330, "zoom": -1}),
    (58.4, 64.4, "clip", ("money", 180)),
    (64.4, 73.4, "mg", "profit"),
    (73.4, 80.0, "pres", {}),
    (80.0, 91.5, "mg", "founder"),
    (91.5, 100.0, "clip", ("three", 255)),
    (100.0, 109.5, "clip", ("aisleB", 285)),
    (109.5, 117.0, "mg", "no_luxury"),
    (117.0, 127.0, "clip", ("cart", 300)),
    (127.0, 133.2, "pres", {"shift": -330}),
    (133.2, 141.2, "mg", "savings"),
    (141.2, 145.8, "mg", "strat2"),
    (145.8, 153.0, "mg", "donut"),
    (153.0, 163.0, "clip", ("owned", 300)),
    (163.0, 173.4, "pres", {"shift": -330, "zoom": -1}),
    (173.4, 177.4, "mg", "strat3"),
    (177.4, 187.4, "clip", ("warehouse", 300)),
    (187.4, 202.0, "mg", "payment"),
    (202.0, 211.5, "clip", ("podium", 285)),
    (211.5, DUR + 0.1, "pres", {"cta": True}),
]

TRANS = 0.4  # crossfade/push length at cuts


def overlays(base, t, shot):
    s0 = shot[0]
    # -------- typography synced to narration
    ov_headline(base, t, 0.5, 6.7, [("WHY IS", 0.55, WHITE, "plain"), ("DMART", 1.5, WHITE, "plain"),
                                    ("SO CHEAP?", 0.8, INK, "yellowpill")], y=520, size=120, stagger=0.25)
    ov_headline(base, t, 7.3, 14.6, [("EVERYONE SHOPS HERE", 0.7, WHITE, "plain")], y=805, size=100)
    ov_chips(base, t, [("POOR", 10.1, GREEN), ("MIDDLE CLASS", 11.2, GREEN), ("RICH", 12.4, YELLOW)], 920, 14.6, 60)
    ov_card(base, t, 22.7, 27.8, "THE BIG QUESTION", "TOP STORE?", "How did DMart become\na top retailer?",
            WHITE)
    ov_headline(base, t, 28.3, 31.1, [("HOW IS IT", 0.7, WHITE, "plain"), ("SO CHEAP?", 1.0, INK, "yellowpill")],
                y=520, size=120)
    ov_headline(base, t, 31.3, 33.6, [("WHAT'S THE", 0.7, WHITE, "plain"), ("STRATEGY?", 1.0, INK, "yellowpill")],
                y=520, size=120)
    ov_headline(base, t, 33.8, 37.4, [("LET'S FIND OUT", 0.9, WHITE, "plain")], y=540, size=120)
    ov_headline(base, t, 38.0, 41.5, [("STARTED WITH", 0.6, WHITE, "plain"), ("2 STORES", 1.2, YELLOW, "plain"),
                                      ("MAHARASHTRA", 0.5, WHITE, "pill")], y=480, size=120)
    ov_headline(base, t, 42.3, 50.4, [("EXPANDED", 0.9, WHITE, "plain"), ("ACROSS INDIA", 0.6, INK, "yellowpill")],
                y=160, size=110)
    ov_card(base, t, 52.0, 58.2, "STORE NETWORK", "400+", "stores across\nIndian states")
    ov_counter(base, t, 58.9, 64.2, 0, 2, lambda v: f"₹{v:.1f} LAKH CRORE" if v < 1.995 else "₹2 LAKH CRORE",
               "COMPANY VALUE", y=200, size=130)
    ov_headline(base, t, 73.6, 79.8, [("HOW DID", 0.6, WHITE, "plain"), ("THIS HAPPEN?", 1.0, INK, "yellowpill")],
                y=830, size=110)
    ov_headline(base, t, 92.0, 99.8, [("3 SECRET", 0.6, WHITE, "plain"), ("STRATEGIES", 1.0, YELLOW, "plain")],
                y=170, size=120)
    ov_headline(base, t, 100.2, 104.5, [("STRATEGY 01", 0.45, INK, "yellowpill"), ("LOW-COST STORES", 1.0, WHITE, "plain")],
                y=170, size=110)
    ov_chips(base, t, [("CLOTHES", 103.6, GREEN), ("FOOD", 104.6, GREEN), ("DAILY ITEMS", 105.6, YELLOW)], 940, 109.3,
             60)
    ov_headline(base, t, 117.4, 121.4, [("ESSENTIALS ONLY", 0.9, WHITE, "plain")], y=150, size=110)
    ov_headline(base, t, 121.7, 126.8, [("SIMPLE STORES", 0.9, WHITE, "plain"), ("LOW RUNNING COST", 0.5, INK, "yellowpill")],
                y=180, size=110)
    ov_card(base, t, 127.4, 133.0, "LEAN OPERATIONS", "FEWER", "staff needed\nper store")
    ov_headline(base, t, 153.3, 157.3, [("NO RENT", 1.0, WHITE, "plain"), ("TO PAY", 0.6, INK, "yellowpill")],
                y=180, size=120)
    ov_headline(base, t, 157.6, 162.8, [("MONEY SAVED", 0.9, WHITE, "plain"), ("EVERY MONTH", 0.5, WHITE, "pill")],
                y=180, size=120)
    ov_card(base, t, 164.4, 173.0, "LOW RISK", "NO RENT", "even if a store\nunderperforms", WHITE)
    ov_headline(base, t, 177.7, 184.2, [("REGULAR BULK", 0.8, WHITE, "plain"), ("PURCHASES", 0.8, INK, "yellowpill")],
                y=170, size=110)
    ov_headline(base, t, 184.6, 187.2, [("PAYS IN", 0.6, WHITE, "plain"), ("15–20 DAYS", 1.1, YELLOW, "plain")],
                y=200, size=120)
    ov_headline(base, t, 205.4, 209.0, [("3 STRATEGIES", 0.8, WHITE, "plain"), ("= SUCCESS", 0.6, INK, "yellowpill")],
                y=170, size=110)
    ov_headline(base, t, 209.2, 211.4, [("STILL NUMBER ONE", 0.9, YELLOW, "plain")], y=170, size=120)
    # -------- CTA
    ov_headline(base, t, 211.9, 216.3, [("WHAT DO YOU THINK?", 0.75, WHITE, "plain"), ("COMMENT BELOW", 0.55, INK, "yellowpill")],
                y=820, size=110)
    ov_chips(base, t, [("👍 LIKE".replace("👍 ", ""), 216.6, GREEN), ("SHARE", 217.6, (20, 90, 160))], 930, 220.0, 64)
    ov_chips(base, t, [("SUBSCRIBE", 220.2, RED), ("🔔".replace("🔔", "TURN ON NOTIFICATIONS"), 223.3, YELLOW)], 930,
             DUR, 64)
    ov_brand(base, t)


def render_shot(shot, t, src):
    s0, s1, kind, arg = shot
    tl = t - s0
    dur = s1 - s0
    if kind == "clip":
        return clip_frame(arg[0], tl, dur, arg[1])
    if kind == "mg":
        return MG[arg](tl, dur)
    # presenter
    fr = int(round(t * FPS))
    rgb = src.get(min(fr, NFRAMES - 1))
    shift = arg.get("shift", 0)
    # card-driven slide: ease the presenter aside only while the card is visible
    if shift:
        k = ease_io(clamp((tl - 0.1) / 0.6)) * ease_io(clamp((dur - tl - 0.2) / 0.6))
        shift *= k
    return presenter_frame(rgb, tl, dur, shift, arg.get("zoom", 1))


def shot_index(t):
    for i, s in enumerate(SHOTS):
        if s[0] <= t < s[1]:
            return i
    return len(SHOTS) - 1


@lru_cache(1)
def vignette():
    y = np.linspace(-1, 1, H)[:, None]
    x = np.linspace(-1, 1, W)[None, :]
    v = 1 - 0.28 * np.clip((x ** 2 * 0.7 + y ** 2) - 0.25, 0, 1.5)
    return v[..., None].astype(np.float32)


def frame_at(fi, src):
    t = fi / FPS
    i = shot_index(t)
    shot = SHOTS[i]
    img = render_shot(shot, t, src)
    tl = t - shot[0]
    if i > 0 and tl < TRANS:
        # push-in crossfade from the previous shot
        prev = render_shot(SHOTS[i - 1], t, src)
        k = ease_io(tl / TRANS)
        sc = 1.08 - 0.08 * k
        cur = img.resize((int(W * sc), int(H * sc)), Image.BILINEAR)
        cur = cur.crop(((cur.width - W) // 2, (cur.height - H) // 2, (cur.width - W) // 2 + W, (cur.height - H) // 2 + H))
        prev_s = prev.resize((int(W * (1 + 0.06 * k)), int(H * (1 + 0.06 * k))), Image.BILINEAR)
        prev_s = prev_s.crop(((prev_s.width - W) // 2, (prev_s.height - H) // 2,
                              (prev_s.width - W) // 2 + W, (prev_s.height - H) // 2 + H))
        img = Image.blend(prev_s, cur, k)
    overlays(img, t, shot)
    arr = np.asarray(img.convert("RGB")).astype(np.float32) * vignette()
    return arr.clip(0, 255).astype(np.uint8)


def main_chunk(idx, n, outdir):
    a = NFRAMES * idx // n
    b = NFRAMES * (idx + 1) // n
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"chunk_{idx:02d}.mp4")
    enc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "30000/1001",
         "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", out],
        stdin=subprocess.PIPE)
    src = Source(a)
    for fi in range(a, b):
        enc.stdin.write(frame_at(fi, src).tobytes())
        if (fi - a) % 150 == 0:
            print(f"[{idx}] {fi - a}/{b - a}", flush=True)
    enc.stdin.close()
    enc.wait()


def sfx_events():
    ev = []
    for s0, s1, kind, arg in SHOTS[1:]:
        ev.append({"t": s0, "type": "whoosh" if kind != "pres" else "whoosh_down"})
    for t in (0.5, 92.0, 100.2, 141.35, 173.55, 209.2):
        ev.append({"t": t, "type": "impact"})
    for t in (92.0, 202.0, 141.35, 173.55):
        ev.append({"t": t, "type": "riser"})
    for t in (10.1, 11.2, 12.4, 22.7, 52.0, 103.6, 104.6, 105.6, 127.4, 164.4, 216.6, 217.6, 220.2, 223.3,
              81.6, 82.0, 85.5, 88.0, 113.9, 114.2, 114.5, 133.5, 134.8, 136.1, 146.2, 147.2, 148.4,
              187.7, 190.0, 192.6, 15.4, 15.9):
        ev.append({"t": t, "type": "pop"})
    for t in (111.1, 111.55, 112.0):
        ev.append({"t": t, "type": "click", "gain": 1.4})
    for t in (58.9, 60.5, 62.0, 137.4):
        ev.append({"t": t, "type": "coins"})
    for t in (38.2, 52.3, 60.6, 147.3, 184.7, 209.4):
        ev.append({"t": t, "type": "ding"})
    return sorted(ev, key=lambda e: e["t"])


if __name__ == "__main__":
    if sys.argv[1] == "sfx":
        import json
        json.dump(sfx_events(), open(sys.argv[2], "w"), indent=0)
    elif sys.argv[1] == "still":
        ts = [float(x) for x in sys.argv[2].split(",")]
        for t in ts:
            fi = int(round(t * FPS))
            src = Source(fi)
            Image.fromarray(frame_at(fi, src)).save(sys.argv[3].replace("%", f"{t:07.2f}"))
    else:
        main_chunk(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
