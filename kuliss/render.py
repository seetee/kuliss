"""The overlay: a backdrop panel with one avatar per player.

- whose view we watch: that avatar is enlarged and gets a name label under it
  in the player's colour; on a cut the label slides over, blending colour, and the
  avatars re-size;
- who is talking: a ring in the player's colour plus a small badge with sound
  bars (so it never relies on colour alone), faded in and out; the ring's glow
  and the bars move with the voice level;
- when no player's view is on screen (intro, outro, full-screen assets) the
  whole overlay fades out.

The canvas has the profile's aspect ratio, so MLT maps it 1:1 onto a
qtblend rect of the same size; no scaling maths in Kdenlive.
"""

import logging
import math
import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import skia

from .config import Theme
from .errors import die

log = logging.getLogger(__name__)

FADE = 0.30       # s; overlay in/out and the cut transition
TALK_FADE = 0.08  # s; talking marker in/out
LEVEL_FALL = 0.25  # s for the voice level to fall from full to nothing (it rises at once)
LEVEL_STEPS = 8    # voice levels drawn; few enough that the frame cache keeps hitting
DIM = 0.6         # opacity of avatars that are neither viewed nor talking
BLACK, WHITE = (0, 0, 0), (255, 255, 255)

# theme `codec` -> (file extension, container, pixel format, encoder options).
# Both are lossless with alpha and decode in Kdenlive; never add a codec
# without checking that its alpha survives there (VP8/VP9 WebM alpha does not).
CODECS = {
    "ffv1": (".mkv", "matroska", "bgra",
             # encoding is ~90% of the run; 16 slices instead of 4 is 40% faster for 5% more bytes
             {"level": "3", "slices": "16", "slicecrc": "1", "context": "1"}),
    "qtrle": (".mov", "mov", "argb", {}),
}


def luminance(rgb) -> float:
    c = [v / 255 for v in rgb]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)))
    return (lb + 0.05) / (la + 0.05)


def on_colour(rgb):
    """Black or white, whichever reads better on rgb. The better of the two is
    always >= 4.58:1, so WCAG AA text contrast holds for any player colour."""
    return max((BLACK, WHITE), key=lambda t: contrast(rgb, t))


def sk(rgb, alpha=1.0):
    return skia.Color(*rgb, round(255 * alpha))


@dataclass(frozen=True)
class Layout:
    W: int                 # canvas size
    H: int
    panel: skia.Rect
    S: int                 # avatar size, idle
    V: int                 # avatar size, viewed
    slots: tuple[tuple[float, float], ...]    # avatar centre per player
    labels: tuple[tuple[float, float], ...]   # name label anchor per player: (x, top)
    label_h: float
    font_size: int
    inset: int             # transparent border around the panel, room for its shadow


def load_font(theme: Theme, size: int) -> skia.Font:
    if theme.font:
        face = skia.Typeface.MakeFromFile(str(theme.font))
        if face is None:
            die(f"font {theme.font} is not a font file skia can read (use .ttf or .otf)")
    else:
        face = skia.Typeface("sans-serif", skia.FontStyle.Bold())
    return skia.Font(face, size)


def load_image(path: Path, what: str) -> skia.Image:
    try:
        return skia.Image.open(str(path))
    except RuntimeError:
        die(f"{what} {path} is not an image skia can read (use .png, .jpg or .webp)")


def layout(theme: Theme, frame_w: int, frame_h: int) -> Layout:
    """A row of avatars ("horizontal") or a column along the frame edge
    ("vertical"), with the name label under the viewed avatar either way."""
    n, S = len(theme.players), theme.avatar_size
    V = round(S * 1.25)
    gap, pad = max(4, S // 4), max(6, S // 4)
    font_size = max(11, round(S / 3))
    label_h = round(font_size * 1.7)
    h, v = anchor(theme.position)
    font = load_font(theme, font_size)
    label_w = max(font.measureText(p.name) for p in theme.players) + label_h
    vertical = theme.orientation == "vertical"
    cell = V + gap // 2 + label_h if vertical else V   # a column leaves label room per avatar
    run = [pad + V / 2 + i * (cell + gap) for i in range(n)]   # avatar centres along the bar
    bar = 2 * pad + n * cell + (n - 1) * gap
    if vertical:
        pw, ph = max(2 * pad + V, label_w + 8), bar
    else:
        pw = max(bar, label_w + 8)       # the label is kept 4 px inside the panel
        ph = pad + V + gap // 2 + label_h + pad
        run = [x + (pw - bar) / 2 for x in run]   # centre the avatars in a wider panel
    inset = max(4, S // 8)
    g = math.gcd(frame_w, frame_h)
    aw, ah = frame_w // g, frame_h // g
    k = math.ceil(max((pw + 2 * inset) / aw, (ph + 2 * inset) / ah))
    W, H = aw * k, ah * k
    if frame_w < W or frame_h < H:
        log.warning("the overlay needs %dx%d px, more than the %dx%d frame; "
                    "lower avatar_size or use fewer players", W, H, frame_w, frame_h)
    px = {"left": inset, "center": (W - pw) / 2, "right": W - pw - inset}[h]
    py = {"top": inset, "middle": (H - ph) / 2, "bottom": H - ph - inset}[v]
    if vertical:
        slots = tuple((px + pw / 2, py + y) for y in run)
        labels = tuple((x, y + V / 2 + gap // 2) for x, y in slots)
    else:
        slots = tuple((px + x, py + pad + V / 2) for x in run)
        labels = tuple((x, py + pad + V + gap // 2) for x, _ in slots)
    return Layout(W, H, skia.Rect.MakeXYWH(px, py, pw, ph), S, V, slots, labels,
                  label_h, font_size, inset)


def anchor(position: str) -> tuple[str, str]:
    """"top-left" -> ("left", "top"); "bottom" -> ("center", "bottom"); "left" -> ("left", "middle")."""
    if "-" in position:
        v, h = position.split("-")
    elif position in ("top", "bottom"):
        v, h = position, "center"
    else:
        v, h = "middle", position
    return h, v


def placement(theme: Theme, lay: Layout, frame_w: int, frame_h: int) -> tuple[int, int, int, int]:
    """Where the canvas goes in the frame: (x, y, w, h) for the qtblend rect.
    The margin applies to the edges the bar sits against (the panel's edge, not its
    shadow's); offset nudges the result."""
    m, (h, v), (dx, dy) = theme.margin - lay.inset, anchor(theme.position), theme.offset
    x = {"left": m, "center": (frame_w - lay.W) // 2, "right": frame_w - m - lay.W}[h]
    y = {"top": m, "middle": (frame_h - lay.H) // 2, "bottom": frame_h - m - lay.H}[v]
    return x + dx, y + dy, lay.W, lay.H


def follow(target: np.ndarray, up: float, down: float) -> np.ndarray:
    """Values that chase `target`, moving at most `up` / `down` per frame, from 0."""
    out = np.empty(len(target), np.float32)
    v = 0.0
    for i, t in enumerate(target.tolist()):
        v = min(v + up, t) if t > v else max(v - down, t)
        out[i] = v
    return out


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)   # in and out: no jerk at either end of a cut


def soft(c: skia.Canvas, rr: skia.RRect, rgb, alpha: float, sigma: float, dy: float = 0,
         stroke: float = 0) -> None:
    """A blurred copy of rr, drawn only outside it: a drop shadow (filled, moved down
    by dy) or a glow (stroked)."""
    paint = skia.Paint(Color=sk(rgb, alpha), AntiAlias=True,
                       MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, sigma))
    if stroke:
        paint.setStyle(skia.Paint.kStroke_Style)
        paint.setStrokeWidth(stroke)
    c.save()
    c.clipRRect(rr, skia.ClipOp.kDifference, True)   # never darken what sits on top
    c.translate(0, dy)
    c.drawRRect(rr, paint)
    c.restore()


class Painter:
    def __init__(self, theme: Theme, lay: Layout):
        self.theme, self.lay = theme, lay
        self.surface = skia.Surface(lay.W, lay.H)
        self.avatars = [load_image(p.avatar, f"{p.name}'s avatar") for p in theme.players]
        self.backdrop = load_image(theme.backdrop, "backdrop") if theme.backdrop else None
        self.font = load_font(theme, lay.font_size)

    def _image(self, c: skia.Canvas, img: skia.Image, dst: skia.Rect, cover=False, paint=None):
        if cover:   # crop to fill dst without distortion
            s = max(dst.width() / img.width(), dst.height() / img.height())
            w, h = dst.width() / s, dst.height() / s
            src = skia.Rect.MakeXYWH((img.width() - w) / 2, (img.height() - h) / 2, w, h)
        else:
            src = skia.Rect.MakeWH(img.width(), img.height())
        # pixel art (Minecraft heads) stays crisp when enlarged
        sampling = (skia.SamplingOptions(skia.FilterMode.kNearest)
                    if img.width() < dst.width() else
                    skia.SamplingOptions(skia.FilterMode.kLinear, skia.MipmapMode.kLinear))
        c.drawImageRect(img, src, dst, sampling, paint)

    def draw(self, vis: float, a: int, b: int, t: float, talk: tuple[float, ...],
             level: tuple[float, ...] | None = None) -> np.ndarray:
        """a -> b: previous and current viewed player, t: 0..1 through the cut.
        talk: each player's talking marker opacity; level: their voice level, 0..1."""
        lay, c = self.lay, self.surface.getCanvas()
        level = level or talk
        c.clear(skia.ColorTRANSPARENT)
        if vis > 0 and b >= 0:
            c.saveLayerAlpha(None, round(255 * vis))
            self._panel(c)
            e = ease(t) if a >= 0 else 1.0
            for i in range(len(self.theme.players)):
                w = e if i == b else (1 - e) if i == a else 0.0
                self._avatar(c, i, lay.S + (lay.V - lay.S) * w,
                             DIM + (1 - DIM) * max(w, talk[i]), talk[i], level[i])
            self._label(c, a if a >= 0 else b, b, e)
            c.restore()
        return self.surface.makeImageSnapshot().toarray(
            colorType=skia.kBGRA_8888_ColorType, alphaType=skia.kUnpremul_AlphaType)

    def _panel(self, c):
        rr = skia.RRect.MakeRectXY(self.lay.panel, self.lay.S / 4, self.lay.S / 4)
        soft(c, rr, BLACK, 0.45, self.lay.inset / 2.5, dy=self.lay.inset / 4)
        c.save()
        c.clipRRect(rr, doAntiAlias=True)
        if self.backdrop:
            self._image(c, self.backdrop, self.lay.panel, cover=True)
        c.drawPaint(skia.Paint(Color=sk(BLACK, 0.35 if self.backdrop else 0.6)))  # scrim
        c.restore()

    def _avatar(self, c, i, size, alpha, talk, level):
        lay, colour = self.lay, self.theme.players[i].colour
        cx, cy = lay.slots[i]
        box = skia.Rect.MakeXYWH(cx - size / 2, cy - size / 2, size, size)
        r = size * 0.18
        rr = skia.RRect.MakeRectXY(box, r, r)
        c.saveLayerAlpha(None, round(255 * alpha))
        # the shadow follows the picture's own shape (avatars often have a clear border);
        # drawn first and unclipped, then covered by the picture itself
        self._image(c, self.avatars[i], box, cover=True, paint=skia.Paint(
            ImageFilter=skia.ImageFilters.DropShadowOnly(0, lay.S / 24, lay.S / 16, lay.S / 16,
                                                         sk(BLACK, 0.6))))
        c.save()
        c.clipRRect(rr, doAntiAlias=True)
        self._image(c, self.avatars[i], box, cover=True)   # non-square avatars are cropped
        c.restore()
        if talk > 0:
            ring = skia.RRect.MakeRectXY(box.makeOutset(4, 4), r + 4, r + 4)
            # the glow breathes with the voice; the crisp ring below is the steady cue
            soft(c, ring, colour, talk * (0.4 + 0.5 * level), lay.S / 24 * (1 + 2 * level),
                 stroke=4 + 4 * level)
            for rgb, width in ((on_colour(colour), 5), (colour, 3)):   # edge: visible on any backdrop
                c.drawRRect(ring, skia.Paint(Color=sk(rgb, talk), AntiAlias=True,
                                             Style=skia.Paint.kStroke_Style, StrokeWidth=width))
            self._badge(c, box.right() - 2, box.top() + 2, colour, talk, level)
        c.restore()

    def _badge(self, c, x, y, colour, alpha, level):
        rad = max(6, self.lay.S / 6)
        c.drawCircle(x, y, rad + 1, skia.Paint(Color=sk(on_colour(colour), alpha), AntiAlias=True))
        c.drawCircle(x, y, rad, skia.Paint(Color=sk(colour, alpha), AntiAlias=True))
        bar = skia.Paint(Color=sk(on_colour(colour), alpha), AntiAlias=True)
        bw = rad / 3.5
        for k, gain in enumerate((0.45, 0.8, 0.6)):   # three sound bars, the middle one liveliest
            bx = x + (k - 1) * bw * 1.6 - bw / 2
            bh = rad * 1.1 * (0.3 + gain * level)
            c.drawRoundRect(skia.Rect.MakeXYWH(bx, y - bh / 2, bw, bh), bw / 2, bw / 2, bar)

    def _label(self, c, a, b, e):
        """One name pill sliding from player a's slot to b's, blending colour;
        the text flips half-way and is re-contrasted for every blended colour."""
        lay, pa, pb = self.lay, self.theme.players[a], self.theme.players[b]
        colour = tuple(round(x + (y - x) * e) for x, y in zip(pa.colour, pb.colour, strict=True))
        name = pb.name if e >= 0.5 else pa.name
        wa, wb = (self.font.measureText(p.name) + lay.label_h for p in (pa, pb))
        w = wa + (wb - wa) * e
        (ax, ay), (bx, by) = lay.labels[a], lay.labels[b]
        cx, top = ax + (bx - ax) * e, ay + (by - ay) * e
        x = cx - w / 2
        x = min(max(x, lay.panel.left() + 4), lay.panel.right() - 4 - w)
        box = skia.Rect.MakeXYWH(x, top, w, lay.label_h)
        c.drawRRect(skia.RRect.MakeRectXY(box, lay.label_h / 2, lay.label_h / 2),
                    skia.Paint(Color=sk(colour), AntiAlias=True))
        m = self.font.getMetrics()
        base = top + (lay.label_h - (m.fDescent - m.fAscent)) / 2 - m.fAscent
        ink = skia.Paint(Color=sk(on_colour(colour)), AntiAlias=True)
        c.drawString(name, x + (w - self.font.measureText(name)) / 2, base, self.font, ink)
        # a camera on the pill's corner: this is whose view we watch
        r, bx, by = max(6, lay.S / 6), x + 4, top + 1   # stays inside the panel
        fill = skia.Paint(Color=sk(colour), AntiAlias=True)
        c.drawCircle(bx, by, r + 1, fill)
        c.drawCircle(bx, by, r, ink)
        c.drawRoundRect(skia.Rect.MakeXYWH(bx - r * 0.62, by - r * 0.4, r * 0.8, r * 0.8), 1, 1, fill)
        lens = skia.Path()
        lens.addPoly([(bx + r * 0.1, by), (bx + r * 0.62, by - r * 0.4), (bx + r * 0.62, by + r * 0.4)],
                     True)
        c.drawPath(lens, fill)


def frame_states(spans, talking: list[np.ndarray], fps: float, n: int):
    """Per frame: (visibility, previous viewer, viewer, transition 0..1, talking marker
    opacity per player, voice level per player)."""
    shown = np.full(n, -1, np.int16)
    before = np.full(n, -1, np.int16)
    since = np.zeros(n, np.int64)
    visible = np.zeros(n, bool)
    last, prev, switch = -1, -1, 0
    for s, e, who in spans:
        if s >= n:
            break
        e = min(e, n)
        if who >= 0 and who != last:
            prev, last, switch = last, who, s
        shown[s:e], before[s:e] = last, prev
        since[s:e] = np.arange(s, e) - switch
        visible[s:e] = who >= 0
    step = 1 / max(FADE * fps, 1)
    vis = np.round(follow(visible.astype(np.float32), step, step), 3).tolist()
    cut = np.round(np.minimum(since / (FADE * fps), 1.0), 3).tolist()
    step = 1 / max(TALK_FADE * fps, 1)
    voices = [np.asarray(t[:n], np.float32) for t in talking]
    marks = [np.round(follow((v > 0).astype(np.float32), step, step), 2).tolist() for v in voices]
    fall = 1 / max(LEVEL_FALL * fps, 1)
    levels = [(np.round(follow(v, 1.0, fall) * LEVEL_STEPS) / LEVEL_STEPS).tolist()
              for v in voices]
    shown, before = shown.tolist(), before.tolist()
    for f in range(n):
        yield (vis[f], before[f], shown[f], cut[f],
               tuple(m[f] for m in marks), tuple(lv[f] for lv in levels))


def render(painter: Painter, codec: str, spans, talking, rate: Fraction, n: int, out: Path,
           progress=lambda done, total: None) -> None:
    """Encode n frames at `rate` fps to `out` (its extension must match the codec's)."""
    _, container, pix_fmt, options = CODECS[codec]
    fps = float(rate)
    tmp = out.with_name(out.name + ".partial")
    cache: dict = {}
    # steady states repeat, ramps are short-lived: keep ~64 MB of them, whatever the canvas size
    cap = max(16, 64_000_000 // (painter.lay.W * painter.lay.H * 4))
    try:
        with av.open(str(tmp), "w", format=container) as box:
            st = box.add_stream(codec, rate=rate)
            st.width, st.height, st.pix_fmt = painter.lay.W, painter.lay.H, pix_fmt
            st.options = options
            for f, state in enumerate(frame_states(spans, talking, fps, n)):
                img = cache.get(state)
                if img is None:
                    if len(cache) > cap:
                        cache.clear()
                    img = cache[state] = painter.draw(*state)
                frame = av.VideoFrame.from_ndarray(img, format="bgra")
                if pix_fmt != "bgra":
                    frame = frame.reformat(format=pix_fmt)
                frame.pts, frame.time_base = f, 1 / rate
                box.mux(st.encode(frame))
                if f % 600 == 0:
                    progress(f, n)
            box.mux(st.encode(None))
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)    # no half-written overlay left behind
        raise
    progress(n, n)
