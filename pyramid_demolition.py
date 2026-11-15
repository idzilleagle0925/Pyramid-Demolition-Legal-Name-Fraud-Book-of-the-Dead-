#!/usr/bin/env python3
"""
BOOK OF THE DEAD: PYRAMID DEMOLITION
Legal Name Fraud Truth Channel ~ https://legalnamefraud.carrd.co ~ Read the BCCRSS ~
Babylon Is Fallen ~ BCCRSS ~ Judge Bows

A top-down pygame action game. You are a demolition explorer in the Egyptian desert.
Find the hidden machines (BULLDOZER, WRECKING-BALL TRUCK), grab dynamite and fuel,
and bring down all three PYRAMIDS before the sun sets - while the guardians of the
Book of the Dead (scarabs, mummies, Anubis guards) try to stop you.

Everything (art, music, sound effects) is generated in code - no asset files.

    pip install pygame-ce        (or pygame)
    python pyramid_demolition.py

CONTROLS  (keyboard)
    WASD / ARROWS   walk.  In a machine: W/S = forward / reverse, A/D = steer
    SHIFT           sprint / bulldozer boost       E   get in / out of a machine
    SPACE           throw dynamite / swing the wrecking ball - always in the direction you FACE
    F  or  LEFT CLICK   swing your khopesh (melee)          R   EYE OF HORUS radar
    BULLDOZER: strike the pyramid, BACK UP, strike again (holding against it does nothing!)
    TAB             switch AIM MODE:  FACING (default)  <->  MOUSE (mouse aims / steers,
                    right click = dynamite, hold right click to drive forward)
    P / ESC pause   M / N music / sound effects on-off      F11 fullscreen

CONTROLLER  (plug in any USB / Xbox-style pad - it is detected automatically)
    Left stick move / drive (up = forward, down = reverse, left-right = steer)
    Right stick aim      A fire (dynamite / wrecking ball)    X melee    Y get in/out
    B Eye of Horus      RB boost      RT / LT accelerate / reverse     Start pause   Back switch aim

Levels get harder and change layout every time you bring the pyramids down.
"""

import array
import json
import math
import random
import sys
import threading
import webbrowser
from pathlib import Path

import pygame

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
W, H = 1280, 720
FPS = 60
WORLD_W, WORLD_H = 3200, 2400
TITLE = "BOOK OF THE DEAD: PYRAMID DEMOLITION"
LINK_URL = "https://legalnamefraud.carrd.co"
TAGLINE = ("Legal Name Fraud Truth Channel ~ https://legalnamefraud.carrd.co ~ Read the BCCRSS ~ "
           "Babylon Is Fallen ~ BCCRSS ~ Judge Bows")
LAYOUTS = ["OPEN DESERT", "RUINED COURTYARDS", "STONE CORRIDORS", "SCATTERED RUINS"]
try:
    SAVE_PATH = Path(__file__).with_name("pyramid_demolition_save.json")
except NameError:
    SAVE_PATH = Path("pyramid_demolition_save.json")

GOLD = (255, 208, 64)
GOLD_D = (176, 128, 24)
SAND = (226, 196, 128)
RED = (225, 50, 55)
GREEN = (80, 215, 110)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
LAPIS = (30, 70, 150)
STONES = [(205, 172, 112), (190, 158, 100), (170, 140, 90), (222, 190, 130), (150, 124, 84)]
FONT_HEAD = "papyrus,impact,arialblack,arial"
FONT_BODY = "arial,helvetica,dejavusans"


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def angle_diff(a, b):
    return (b - a + math.pi) % (2 * math.pi) - math.pi


def push_out_circle_rect(cx, cy, r, x0, y0, x1, y1):
    """Push a circle out of an axis-aligned box. Returns (x, y, nx, ny) or None."""
    nx, ny = clamp(cx, x0, x1), clamp(cy, y0, y1)
    dx, dy = cx - nx, cy - ny
    d = math.hypot(dx, dy)
    if d >= r:
        return None
    if d < 1e-6:                                   # centre inside the box: leave by the nearest side
        opts = [(cx - x0, -1, 0), (x1 - cx, 1, 0), (cy - y0, 0, -1), (y1 - cy, 0, 1)]
        pen, ux, uy = min(opts, key=lambda o: o[0])
        return cx + ux * (pen + r), cy + uy * (pen + r), ux, uy
    ux, uy = dx / d, dy / d
    return nx + ux * r, ny + uy * r, ux, uy


def push_out_circle_circle(cx, cy, r, ox, oy, orad):
    dx, dy = cx - ox, cy - oy
    d = math.hypot(dx, dy)
    if d >= r + orad:
        return None
    if d < 1e-6:
        dx, dy, d = 1.0, 0.0, 1.0
    ux, uy = dx / d, dy / d
    return ox + ux * (r + orad), oy + uy * (r + orad), ux, uy


# ---------------------------------------------------------------------------
# SOUND (synthesised) + MUSIC (built in a background thread)
# ---------------------------------------------------------------------------
RATE = 22050


def _wave(kind, phase):
    if kind == "sine":
        return math.sin(phase)
    if kind == "tri":
        return 2 / math.pi * math.asin(math.sin(phase))
    if kind == "square":
        return 0.6 if math.sin(phase) >= 0 else -0.6
    if kind == "saw":
        return 2 * ((phase / (2 * math.pi)) % 1.0) - 1
    return 0.0


def synth(freq, dur, vol=0.4, kind="sine", f_end=None, attack=0.004, decay=6.0, noise=0.0):
    n = int(RATE * dur)
    out, phase = [], 0.0
    for i in range(n):
        t = i / RATE
        u = i / max(1, n - 1)
        f = freq if f_end is None else freq + (f_end - freq) * u
        phase += 2 * math.pi * f / RATE
        env = min(1.0, t / attack) * math.exp(-decay * u)
        s = _wave(kind, phase) * (1 - noise) + random.uniform(-1, 1) * noise
        out.append(s * env * vol)
    return out


def mix(parts):
    length = max(int(RATE * st) + len(buf) for st, buf in parts)
    out = [0.0] * length
    for st, buf in parts:
        off = int(RATE * st)
        for i, v in enumerate(buf):
            out[off + i] += v
    return out


NOTE_SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note_freq(name):
    semi = NOTE_SEMI[name[0]]
    rest = name[1:]
    if rest.startswith("#"):
        semi += 1
        rest = rest[1:]
    elif rest.startswith("b"):
        semi -= 1
        rest = rest[1:]
    midi = 12 * (int(rest) + 1) + semi
    return 440.0 * 2 ** ((midi - 69) / 12)


class Sfx:
    BPM = 126
    # D phrygian-dominant ("Egyptian") melody, lengths in eighth notes (8 per bar)
    LEAD = ["D5:2 C5:1 Bb4:1 A4:2 F#4:2", "Eb4:2 F#4:2 A4:4", "D5:1 Eb5:1 D5:1 C5:1 Bb4:2 A4:2",
            "G4:2 F#4:2 Eb4:2 D4:2", "A4:2 Bb4:2 C5:2 D5:2", "Eb5:2 D5:2 C5:2 Bb4:2",
            "A4:1 Bb4:1 A4:1 G4:1 F#4:2 Eb4:2", "D4:4 A3:2 -:2"]
    BASS = ["D2", "D2", "Bb1", "G2", "D2", "Eb2", "Bb1", "A2"]

    def __init__(self):
        global RATE
        self.ok = False
        self.enabled = True
        self.music_on = True
        self.snd = {}
        self.music = None
        self.music_data = None
        self.music_channel = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(RATE, -16, 1, 512)
            RATE, _fmt, self.channels = pygame.mixer.get_init()
            self.ok = True
        except pygame.error:
            return
        self._build()
        threading.Thread(target=self._build_music, daemon=True).start()

    def _make(self, samples, volume=1.0):
        buf = array.array("h")
        for v in samples:
            s = int(max(-1.0, min(1.0, v)) * 32000)
            for _ in range(self.channels):
                buf.append(s)
        snd = pygame.mixer.Sound(buffer=buf.tobytes())
        snd.set_volume(volume)
        return snd

    def _build(self):
        S = self.snd
        S["click"] = self._make(synth(900, 0.05, 0.25, "square", decay=8), 0.6)
        S["pickup"] = self._make(mix([(0, synth(880, 0.1, 0.3, "square", decay=5)),
                                      (0.08, synth(1320, 0.18, 0.3, "square", decay=4))]), 0.7)
        S["scroll"] = self._make(mix([(i * 0.07, synth(f, 0.25, 0.25, "tri", decay=4))
                                      for i, f in enumerate([587, 740, 880, 1175, 1480])]), 0.8)
        S["throw"] = self._make(synth(300, 0.18, 0.3, "sine", f_end=700, decay=5, noise=0.5), 0.6)
        S["tick"] = self._make(synth(1800, 0.03, 0.25, "square", decay=6), 0.45)
        S["boom"] = self._make(mix([(0, synth(100, 0.7, 0.8, "sine", f_end=28, decay=4)),
                                    (0, synth(0, 0.8, 0.6, "sine", noise=1.0, decay=4.5))]), 1.0)
        S["crumble"] = self._make(mix([(0, synth(0, 1.2, 0.45, "sine", noise=1.0, decay=2.5)),
                                       (0, synth(70, 1.2, 0.5, "sine", f_end=24, decay=2.5))]), 1.0)
        S["hit"] = self._make(mix([(0, synth(160, 0.12, 0.6, "sine", f_end=55, decay=8)),
                                   (0, synth(0, 0.06, 0.3, "sine", noise=1.0, decay=9))]), 0.8)
        S["hurt"] = self._make(synth(320, 0.28, 0.4, "saw", f_end=110, decay=4), 0.8)
        S["swing"] = self._make(synth(380, 0.16, 0.3, "sine", f_end=1000, decay=6, noise=0.45), 0.6)
        S["radar"] = self._make(synth(260, 0.9, 0.3, "sine", f_end=1500, decay=2.5), 0.7)
        S["enter"] = self._make(mix([(0, synth(220, 0.12, 0.35, "square", decay=5)),
                                     (0.1, synth(330, 0.18, 0.35, "square", decay=4))]), 0.7)
        S["engine"] = self._make(synth(62, 0.3, 0.3, "saw", decay=2.0, noise=0.25), 0.55)
        S["kill"] = self._make(synth(700, 0.1, 0.3, "square", f_end=180, decay=6), 0.6)
        S["shield"] = self._make(synth(500, 0.3, 0.3, "tri", f_end=1100, decay=3), 0.7)
        S["win"] = self._make(mix([(i * 0.13, synth(f, 0.55, 0.3, "tri", decay=3))
                                   for i, f in enumerate([587, 740, 880, 1175, 880, 1175, 1480])]), 0.9)
        S["lose"] = self._make(mix([(i * 0.22, synth(f, 0.5, 0.3, "saw", decay=3))
                                    for i, f in enumerate([440, 392, 349, 294])]), 0.8)

    def _build_music(self):
        try:
            step = 60.0 / self.BPM / 2
            total = int(RATE * step * 64)
            out = [0.0] * total
            cache = {}

            def add(start_step, buf):
                off = int(RATE * step * start_step)
                for i, v in enumerate(buf):
                    j = off + i
                    if j >= total:
                        break
                    out[j] += v

            pos = 0
            for bar in self.LEAD:
                for tok in bar.split():
                    name, ln = tok.split(":")
                    ln = int(ln)
                    if name != "-":
                        key = ("L", name, ln)
                        if key not in cache:
                            cache[key] = synth(note_freq(name), step * ln * 0.9, 0.16, "square", decay=2.0)
                        add(pos, cache[key])
                    pos += ln
            for b, root in enumerate(self.BASS):
                for k in range(4):
                    name = root if k % 2 == 0 else root[0] + str(int(root[-1]) + 1)
                    key = ("B", name)
                    if key not in cache:
                        cache[key] = synth(note_freq(name), step * 2 * 0.9, 0.34, "tri", decay=1.2)
                    add(b * 8 + k * 2, cache[key])
            kick = synth(140, 0.12, 0.5, "sine", f_end=45, decay=6)
            snare = synth(210, 0.1, 0.24, "sine", noise=0.85, decay=7)
            hat = synth(0, 0.03, 0.06, "sine", noise=1.0, decay=8)
            for st in range(64):
                if st % 4 == 0:
                    add(st, kick)
                if st % 4 == 2:
                    add(st, snare)
                if st % 2 == 1:
                    add(st, hat)
            peak = max(0.01, max(abs(v) for v in out))
            gain = min(1.0, 0.9 / peak)
            buf = array.array("h")
            for v in out:
                s16 = int(max(-1.0, min(1.0, v * gain)) * 32000)
                for _ in range(self.channels):
                    buf.append(s16)
            self.music_data = buf.tobytes()
        except Exception:
            self.music_data = None

    def poll(self):
        if self.ok and self.music is None and self.music_data is not None:
            self.music = pygame.mixer.Sound(buffer=self.music_data)
            self.music.set_volume(0.22)
            self.music_channel = self.music.play(loops=-1)
            if not self.music_on and self.music_channel:
                self.music_channel.pause()

    def play(self, name):
        if self.ok and self.enabled and name in self.snd:
            self.snd[name].play()

    def toggle_music(self):
        self.music_on = not self.music_on
        if self.music_channel:
            if self.music_on:
                self.music_channel.unpause()
            else:
                self.music_channel.pause()

    def toggle_sound(self):
        self.enabled = not self.enabled


# ---------------------------------------------------------------------------
# ART  (everything drawn with pygame primitives)
# ---------------------------------------------------------------------------
def vgrad(w, h, top, bottom):
    s = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        pygame.draw.line(s, (int(lerp(top[0], bottom[0], t)), int(lerp(top[1], bottom[1], t)),
                             int(lerp(top[2], bottom[2], t))), (0, y), (w, y))
    return s


def blit_rot(dst, img, x, y, angle):
    rot = pygame.transform.rotate(img, -math.degrees(angle))
    dst.blit(rot, rot.get_rect(center=(int(x), int(y))))


def outlined(font, text, fill, outline, thick=2):
    base = font.render(text, True, fill)
    w, h = base.get_size()
    surf = pygame.Surface((w + 2 * thick, h + 2 * thick), pygame.SRCALPHA)
    o = font.render(text, True, outline)
    for a in range(0, 360, 30):
        surf.blit(o, (thick + int(round(math.cos(math.radians(a)) * thick)),
                      thick + int(round(math.sin(math.radians(a)) * thick))))
    surf.blit(base, (thick, thick))
    return surf


class Art:
    def __init__(self):
        sf = pygame.font.SysFont
        self.f_huge = sf(FONT_HEAD, 96)
        self.f_title = sf(FONT_HEAD, 64)
        self.f_big = sf(FONT_HEAD, 40)
        self.f_med = sf(FONT_BODY, 26, bold=True)
        self.f_small = sf(FONT_BODY, 19, bold=True)
        self.f_tiny = sf(FONT_BODY, 15, bold=True)
        self._text = {}
        self.sand = self.make_sand()
        self.player = self.make_player()
        self.dozer = self.make_dozer()
        self.wrecker = self.make_wrecker()
        self.rocks = {r: self.make_rock(r) for r in (14, 18, 22, 26, 30)}
        self.column = self.make_column()
        self.palm = self.make_palm()
        self.tent = self.make_tent()
        self.items = {"fuel": self.make_fuel(), "dyn": self.make_crate(), "ankh": self.make_ankh(),
                      "scroll": self.make_scroll()}
        self.enemy = {"scarab": self.make_scarab(), "mummy": self.make_mummy(), "anubis": self.make_anubis()}
        self.dust = {}
        for r in range(6, 46, 4):
            for lv in range(5):
                s = pygame.Surface((2 * r, 2 * r), pygame.SRCALPHA)
                for i in range(r, 0, -2):
                    a = int((150 - lv * 28) * (1 - i / r) ** 0.6)
                    pygame.draw.circle(s, (232, 210, 160, max(0, a)), (r, r), i)
                self.dust[(r, lv)] = s
        self.scissor_free = None

    # ----- text cache -----
    def text(self, font, txt, color):
        key = (id(font), txt, color)
        if key not in self._text:
            if len(self._text) > 600:
                self._text.clear()
            self._text[key] = font.render(txt, True, color)
        return self._text[key]

    # ----- terrain -----
    def make_sand(self, size=512):
        s = pygame.Surface((size, size))
        s.fill(SAND)
        rng = random.Random(3)
        for _ in range(7000):
            s.set_at((rng.randrange(size), rng.randrange(size)),
                     rng.choice([(218, 186, 118), (233, 205, 140), (212, 180, 110), (238, 212, 150)]))
        for _ in range(16):
            y0 = rng.randrange(size)
            amp = rng.uniform(4, 11)
            k = rng.choice([1, 2, 2, 3])
            ph = rng.uniform(0, 6.28)
            for dy in (-size, 0, size):
                pts = [(x, y0 + dy + math.sin(x / size * 2 * math.pi * k + ph) * amp) for x in range(0, size + 8, 8)]
                pygame.draw.lines(s, (214, 182, 112), False, pts, 2)
                pts2 = [(x, y + 3) for x, y in pts]
                pygame.draw.lines(s, (238, 212, 150), False, pts2, 1)
        return s

    def make_rock(self, r):
        s = pygame.Surface((2 * r + 8, 2 * r + 8), pygame.SRCALPHA)
        c = r + 4
        rng = random.Random(r * 7)
        pts = [(c + math.cos(a) * r * rng.uniform(0.8, 1.05), c + math.sin(a) * r * rng.uniform(0.8, 1.05))
               for a in [i * math.pi / 5 for i in range(10)]]
        pygame.draw.polygon(s, (120, 100, 70), [(x + 3, y + 4) for x, y in pts])
        pygame.draw.polygon(s, (150, 128, 92), pts)
        pygame.draw.polygon(s, (180, 156, 116), [(c + (x - c) * 0.62 - 2, c + (y - c) * 0.62 - 3) for x, y in pts])
        pygame.draw.polygon(s, (96, 78, 54), pts, 2)
        return s

    def make_column(self):
        r = 24
        s = pygame.Surface((2 * r + 10, 2 * r + 10), pygame.SRCALPHA)
        c = r + 5
        pygame.draw.circle(s, (130, 108, 76), (c + 4, c + 5), r)
        pygame.draw.circle(s, (205, 180, 130), (c, c), r)
        pygame.draw.circle(s, (170, 146, 100), (c, c), r, 4)
        pygame.draw.circle(s, (225, 200, 150), (c - 2, c - 2), r - 9)
        for a in range(0, 360, 45):
            pygame.draw.line(s, (170, 146, 100), (c, c),
                             (c + math.cos(math.radians(a)) * (r - 9), c + math.sin(math.radians(a)) * (r - 9)), 1)
        return s

    def make_palm(self):
        s = pygame.Surface((120, 120), pygame.SRCALPHA)
        c = 60
        for a in range(0, 360, 36):
            r = math.radians(a)
            tip = (c + math.cos(r) * 52, c + math.sin(r) * 52)
            side = (c + math.cos(r + 0.28) * 28, c + math.sin(r + 0.28) * 28)
            side2 = (c + math.cos(r - 0.28) * 28, c + math.sin(r - 0.28) * 28)
            pygame.draw.polygon(s, (36, 112, 56), [(c, c), side, tip, side2])
            pygame.draw.line(s, (24, 80, 40), (c, c), tip, 2)
        pygame.draw.circle(s, (110, 80, 40), (c, c), 8)
        pygame.draw.circle(s, (150, 112, 60), (c - 2, c - 2), 5)
        return s

    def make_tent(self):
        s = pygame.Surface((170, 130), pygame.SRCALPHA)
        pygame.draw.polygon(s, (120, 100, 70), [(12, 20), (150, 14), (160, 100), (22, 112)])
        pygame.draw.polygon(s, (236, 226, 196), [(8, 14), (146, 8), (156, 94), (18, 106)])
        pygame.draw.line(s, (200, 60, 50), (80, 11), (87, 100), 4)
        pygame.draw.polygon(s, (60, 40, 30), [(56, 100), (112, 96), (96, 60), (70, 62)])
        return s

    # ----- characters / machines (all drawn facing RIGHT) -----
    def make_player(self):
        s = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 70), (16, 22, 34, 30))
        pygame.draw.rect(s, (120, 80, 40), (14, 22, 12, 20), border_radius=4)
        pygame.draw.ellipse(s, (190, 170, 110), (22, 17, 24, 30))
        pygame.draw.circle(s, (222, 176, 130), (46, 22), 5)
        pygame.draw.circle(s, (222, 176, 130), (46, 42), 5)
        pygame.draw.line(s, (170, 150, 90), (36, 22), (46, 22), 5)
        pygame.draw.line(s, (170, 150, 90), (36, 42), (46, 42), 5)
        pygame.draw.circle(s, (222, 176, 130), (34, 32), 9)
        pygame.draw.circle(s, (226, 206, 150), (33, 32), 13)
        pygame.draw.circle(s, (180, 150, 90), (33, 32), 13, 2)
        pygame.draw.circle(s, (206, 186, 130), (35, 32), 6)
        return s

    def make_dozer(self):
        s = pygame.Surface((160, 110), pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 0, 0, 60), (22, 18, 100, 80), border_radius=10)
        for y in (8, 78):
            pygame.draw.rect(s, (30, 30, 30), (14, y, 106, 24), border_radius=10)
            for x in range(20, 112, 9):
                pygame.draw.line(s, (80, 80, 80), (x, y + 3), (x, y + 21), 2)
        pygame.draw.rect(s, (244, 190, 20), (24, 22, 94, 66), border_radius=8)
        pygame.draw.rect(s, (200, 150, 10), (24, 22, 94, 66), 3, border_radius=8)
        pygame.draw.rect(s, (214, 160, 14), (74, 30, 40, 50), border_radius=6)
        for y in (36, 48, 60, 70):
            pygame.draw.line(s, (150, 110, 10), (80, y), (108, y), 2)
        pygame.draw.rect(s, (60, 80, 100), (36, 32, 34, 46), border_radius=5)
        pygame.draw.rect(s, (150, 190, 210), (40, 36, 26, 38), border_radius=4)
        pygame.draw.circle(s, (60, 60, 60), (92, 24), 5)
        for y in (24, 76):
            pygame.draw.rect(s, (120, 120, 126), (116, y, 18, 8))
        pygame.draw.rect(s, (130, 130, 138), (128, 6, 22, 98), border_radius=6)
        pygame.draw.rect(s, (80, 80, 88), (128, 6, 22, 98), 3, border_radius=6)
        for y in range(10, 98, 18):
            pygame.draw.polygon(s, (240, 190, 20), [(130, y), (148, y), (148, y + 8), (136, y + 8)])
        return s

    def make_wrecker(self):
        s = pygame.Surface((150, 100), pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 0, 0, 60), (14, 18, 124, 70), border_radius=10)
        for x in (22, 96):
            pygame.draw.rect(s, (30, 30, 30), (x, 6, 30, 14), border_radius=5)
            pygame.draw.rect(s, (30, 30, 30), (x, 80, 30, 14), border_radius=5)
        pygame.draw.rect(s, (200, 100, 30), (14, 20, 84, 60), border_radius=8)
        pygame.draw.rect(s, (150, 70, 20), (14, 20, 84, 60), 3, border_radius=8)
        pygame.draw.rect(s, (236, 130, 40), (98, 24, 40, 52), border_radius=8)
        pygame.draw.rect(s, (150, 190, 210), (116, 30, 18, 40), border_radius=4)
        pygame.draw.circle(s, (90, 90, 96), (52, 50), 16)
        pygame.draw.circle(s, (160, 160, 168), (52, 50), 11)
        pygame.draw.circle(s, (70, 70, 76), (52, 50), 4)
        return s

    def make_scarab(self):
        s = pygame.Surface((36, 36), pygame.SRCALPHA)
        for dy in (-9, 0, 9):
            pygame.draw.line(s, (20, 30, 50), (18, 18 + dy), (8, 18 + dy * 1.7), 2)
            pygame.draw.line(s, (20, 30, 50), (18, 18 + dy), (28, 18 + dy * 1.7), 2)
        pygame.draw.ellipse(s, (30, 90, 120), (6, 9, 22, 18))
        pygame.draw.ellipse(s, (70, 170, 190), (9, 11, 14, 8))
        pygame.draw.line(s, (20, 40, 60), (6, 18), (28, 18), 1)
        pygame.draw.circle(s, (16, 40, 60), (28, 18), 6)
        pygame.draw.circle(s, (255, 80, 60), (30, 16), 2)
        pygame.draw.circle(s, (255, 80, 60), (30, 20), 2)
        return s

    def make_mummy(self):
        s = pygame.Surface((52, 52), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 60), (9, 12, 34, 32))
        pygame.draw.ellipse(s, (224, 214, 180), (10, 10, 28, 32))
        for x in range(14, 36, 6):
            pygame.draw.line(s, (170, 156, 120), (x, 12), (x - 4, 40), 2)
        pygame.draw.circle(s, (224, 214, 180), (40, 14), 5)
        pygame.draw.circle(s, (224, 214, 180), (40, 38), 5)
        pygame.draw.circle(s, (232, 222, 190), (34, 26), 10)
        pygame.draw.line(s, (170, 156, 120), (27, 24), (41, 28), 2)
        pygame.draw.circle(s, (255, 60, 40), (38, 23), 2)
        pygame.draw.circle(s, (255, 60, 40), (38, 30), 2)
        return s

    def make_anubis(self):
        s = pygame.Surface((64, 64), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 60), (12, 14, 36, 36))
        pygame.draw.ellipse(s, (24, 24, 34), (12, 14, 30, 36))
        pygame.draw.ellipse(s, (230, 180, 40), (28, 16, 12, 32))
        pygame.draw.line(s, (170, 120, 40), (20, 44), (60, 44), 4)
        pygame.draw.polygon(s, (230, 220, 200), [(60, 40), (64, 44), (60, 48)])
        pygame.draw.circle(s, (16, 16, 24), (42, 32), 9)
        pygame.draw.polygon(s, (16, 16, 24), [(46, 28), (60, 32), (46, 36)])
        pygame.draw.polygon(s, (16, 16, 24), [(38, 24), (34, 14), (44, 22)])
        pygame.draw.polygon(s, (16, 16, 24), [(38, 40), (34, 50), (44, 42)])
        pygame.draw.circle(s, (255, 200, 40), (44, 29), 2)
        return s

    # ----- pickups -----
    def make_fuel(self):
        s = pygame.Surface((44, 44), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 70), (7, 30, 32, 10))
        pygame.draw.rect(s, (200, 40, 40), (9, 10, 26, 28), border_radius=5)
        pygame.draw.rect(s, (130, 20, 20), (9, 10, 26, 28), 2, border_radius=5)
        pygame.draw.rect(s, (200, 40, 40), (26, 4, 9, 8), border_radius=2)
        pygame.draw.rect(s, (60, 60, 60), (15, 4, 8, 7))
        pygame.draw.line(s, (255, 235, 200), (16, 18), (28, 30), 3)
        pygame.draw.line(s, (255, 235, 200), (28, 18), (16, 30), 3)
        return s

    def make_crate(self):
        s = pygame.Surface((46, 46), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (0, 0, 0, 70), (6, 33, 36, 10))
        pygame.draw.rect(s, (160, 110, 56), (6, 8, 34, 30), border_radius=3)
        pygame.draw.rect(s, (96, 60, 30), (6, 8, 34, 30), 2, border_radius=3)
        for x in (14, 23, 32):
            pygame.draw.line(s, (110, 70, 36), (x, 9), (x, 37), 1)
        f = pygame.font.SysFont(FONT_BODY, 13, bold=True).render("TNT", True, (200, 30, 30))
        s.blit(f, f.get_rect(center=(23, 23)))
        return s

    def make_ankh(self):
        s = pygame.Surface((44, 44), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 230, 120, 80), (22, 22), 20)
        pygame.draw.circle(s, GOLD, (22, 14), 8, 4)
        pygame.draw.rect(s, GOLD, (19, 20, 6, 20))
        pygame.draw.rect(s, GOLD, (10, 26, 24, 6))
        pygame.draw.circle(s, (255, 244, 190), (20, 11), 2)
        return s

    def make_scroll(self):
        s = pygame.Surface((46, 46), pygame.SRCALPHA)
        pygame.draw.circle(s, (160, 120, 255, 70), (23, 23), 21)
        pygame.draw.rect(s, (236, 222, 172), (8, 14, 30, 18), border_radius=3)
        pygame.draw.ellipse(s, (210, 190, 130), (4, 12, 8, 22))
        pygame.draw.ellipse(s, (210, 190, 130), (34, 12, 8, 22))
        for y in (19, 24, 29):
            pygame.draw.line(s, (130, 90, 50), (13, y), (33, y), 1)
        pygame.draw.rect(s, (190, 40, 50), (21, 12, 4, 22))
        return s


# ---------------------------------------------------------------------------
# GAME OBJECTS
# ---------------------------------------------------------------------------
class Pyramid:
    def __init__(self, x, y, half, hp, name, seed):
        self.x, self.y, self.half = x, y, half
        self.max_hp = self.hp = hp
        self.name = name
        self.alive = True
        self.flash = 0.0
        self.collapse = 0.0
        self.last_size = half
        rng = random.Random(seed)
        self.cracks = []
        for _ in range(16):
            a = rng.uniform(0, math.tau)
            r0 = rng.uniform(0.85, 1.0)
            pts = [(math.cos(a) * r0, math.sin(a) * r0)]
            for _k in range(4):
                a += rng.uniform(-0.4, 0.4)
                r0 = max(0.05, r0 - rng.uniform(0.12, 0.26))
                pts.append((math.cos(a) * r0, math.sin(a) * r0))
            self.cracks.append(pts)
        self.rubble = [(rng.uniform(0, math.tau), rng.uniform(0.72, 1.3), rng.uniform(5, 15),
                        rng.choice(STONES), rng.uniform(0, 6.28)) for _ in range(80)]

    @property
    def frac(self):
        return max(0.0, self.hp / self.max_hp)

    @property
    def size(self):
        return self.half * (0.30 + 0.70 * self.frac) if self.alive else self.half * 0.3

    @property
    def box(self):
        s = self.size
        return (self.x - s, self.y - s, self.x + s, self.y + s)

    def _chunk(self, surf, cx, cy, size, color, rot):
        pts = [(cx + math.cos(rot + a) * size * k, cy + math.sin(rot + a) * size * k)
               for a, k in ((0, 1.0), (1.5, 0.8), (3.0, 1.0), (4.6, 0.7))]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, (110, 88, 58), pts, 1)

    def draw_rubble(self, surf, cam):
        sx, sy = self.x - cam[0], self.y - cam[1]
        n = len(self.rubble) if not self.alive else int(len(self.rubble) * (1 - self.frac) * 1.05)
        for a, d, sz, col, rot in self.rubble[:n]:
            self._chunk(surf, sx + math.cos(a) * self.half * d, sy + math.sin(a) * self.half * d, sz, col, rot)

    def draw(self, surf, cam, art):
        if not self.alive and self.collapse >= 2.0:
            return
        sx, sy = self.x - cam[0], self.y - cam[1]
        s = self.size
        if not self.alive:
            u = min(1.0, self.collapse / 2.0)
            s = self.last_size * (1 - u) ** 1.5
            sx += random.uniform(-4, 4) * (1 - u)
            sy += random.uniform(-4, 4) * (1 - u)
        if s < 3:
            return
        A, B, C, D, O = (sx - s, sy - s), (sx + s, sy - s), (sx + s, sy + s), (sx - s, sy + s), (sx, sy)
        sh = s * 0.12 + 6
        pygame.draw.polygon(surf, (165, 134, 84), [(A[0] + sh, A[1] + sh), (B[0] + sh, B[1] + sh),
                                                   (C[0] + sh, C[1] + sh), (D[0] + sh, D[1] + sh)])
        faces = [((A, B, O), (240, 212, 150)), ((B, C, O), (214, 180, 116)),
                 ((C, D, O), (176, 144, 92)), ((D, A, O), (222, 190, 130))]
        for pts, col in faces:
            pygame.draw.polygon(surf, col, pts)
        for t in (0.2, 0.38, 0.56, 0.74, 0.9):
            pygame.draw.rect(surf, (150, 122, 80), (sx - s * t, sy - s * t, 2 * s * t, 2 * s * t), 1)
        pygame.draw.line(surf, (130, 104, 66), A, O, 2)
        pygame.draw.line(surf, (130, 104, 66), B, O, 2)
        pygame.draw.line(surf, (130, 104, 66), C, O, 2)
        pygame.draw.line(surf, (130, 104, 66), D, O, 2)
        pygame.draw.rect(surf, (110, 88, 58), (A[0], A[1], 2 * s, 2 * s), 3)
        n = int(len(self.cracks) * (1 - self.frac) * 1.15)
        for pts in self.cracks[:n]:
            pygame.draw.lines(surf, (60, 44, 30), False, [(sx + px * s, sy + py * s) for px, py in pts], 2)
        if self.frac > 0.45 or not self.alive:
            c = max(4, s * 0.12)
            pygame.draw.polygon(surf, GOLD, [(sx, sy - c), (sx + c, sy), (sx, sy + c), (sx - c, sy)])
            pygame.draw.polygon(surf, (255, 240, 170), [(sx, sy - c), (sx + c, sy), (sx, sy)])
        if self.flash > 0:
            ov = pygame.Surface((int(2 * s) + 2, int(2 * s) + 2), pygame.SRCALPHA)
            ov.fill((255, 255, 255, int(140 * self.flash / 0.12)))
            surf.blit(ov, (sx - s, sy - s))


class Vehicle:
    def __init__(self, kind, x, y):
        self.kind = kind
        self.x, self.y = x, y
        self.angle = random.uniform(0, math.tau)
        self.speed = 0.0
        self.found = False
        self.driver = False
        if kind == "dozer":
            self.name, self.max_hp, self.max_speed, self.radius, self.accel = "BULLDOZER", 240, 215, 40, 260
        else:
            self.name, self.max_hp, self.max_speed, self.radius, self.accel = "WRECKING TRUCK", 200, 170, 44, 220
        self.hp = self.max_hp
        self.fuel = 60.0
        self.ram_cd = 0.0
        self.swing_t = 0.0           # seconds left of the wrecking-ball swing
        self.swing_cd = 0.0
        self.swing_a = 0.0
        self.pyr_cd = {}
        self.eng_t = 0.0
        self.armed = True            # bulldozer: must BACK UP before the next strike counts

    def ball_pos(self):
        return (self.x + math.cos(self.swing_a) * 135, self.y + math.sin(self.swing_a) * 135)


class Enemy:
    SPEC = {"scarab": dict(hp=8, speed=160, r=11, dmg=5, cd=0.7, pts=15),
            "mummy": dict(hp=45, speed=88, r=18, dmg=14, cd=1.0, pts=40),
            "anubis": dict(hp=70, speed=74, r=20, dmg=0, cd=2.4, pts=75)}

    def __init__(self, kind, x, y):
        sp = self.SPEC[kind]
        self.kind = kind
        self.x, self.y = x, y
        self.hp = self.max_hp = sp["hp"]
        self.speed, self.r, self.dmg, self.cd, self.pts = sp["speed"], sp["r"], sp["dmg"], sp["cd"], sp["pts"]
        self.angle = 0.0
        self.atk_cd = random.uniform(0.2, self.cd)
        self.wob = random.uniform(0, 6.28)
        self.hurt = 0.0
        self.kx = self.ky = 0.0


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max", "size", "color", "kind")

    def __init__(self, x, y, vx, vy, life, size, color, kind):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max = life
        self.size, self.color, self.kind = size, color, kind


class Pad:
    """USB / Xbox-style game controller (SDL game-controller API, joystick API as a fallback)."""
    DEAD = 0.22

    def __init__(self):
        self.dev = None
        self.kind = None
        self.name = ""
        self.sc = None
        self.cur, self.prev = {}, {}
        self.lx = self.ly = self.rx = self.ry = self.lt = self.rt = 0.0
        self.recheck = 0.0
        self.fake = False
        self.connect()

    @property
    def active(self):
        return self.dev is not None

    def connect(self):
        self.dev, self.kind, self.name = None, None, ""
        try:
            from pygame._sdl2 import controller as sc
            sc.init()
            for i in range(sc.get_count()):
                if sc.is_controller(i):
                    self.dev = sc.Controller(i)
                    self.sc, self.kind = sc, "sdl"
                    try:
                        self.name = str(sc.name_forindex(i))
                    except Exception:
                        self.name = "Game controller"
                    return
        except Exception:
            pass
        try:
            pygame.joystick.init()
            if pygame.joystick.get_count() > 0:
                j = pygame.joystick.Joystick(0)
                j.init()
                self.dev, self.kind, self.name = j, "joy", j.get_name()
        except Exception:
            pass

    def _dz(self, v):
        if abs(v) < self.DEAD:
            return 0.0
        return (abs(v) - self.DEAD) / (1 - self.DEAD) * (1 if v > 0 else -1)

    def update(self, dt):
        if self.fake:
            return
        self.prev = self.cur
        if self.dev is None:
            self.cur = {}
            self.lx = self.ly = self.rx = self.ry = self.lt = self.rt = 0.0
            self.recheck -= dt
            if self.recheck <= 0:
                self.recheck = 2.0
                self.connect()
            return
        try:
            if self.kind == "sdl":
                sc, d = self.sc, self.dev
                if not getattr(d, "attached", lambda: True)():
                    raise RuntimeError("unplugged")

                def ax(a):
                    return d.get_axis(a) / 32768.0

                def bt(b):
                    return bool(d.get_button(b))
                self.lx, self.ly = self._dz(ax(sc.CONTROLLER_AXIS_LEFTX)), self._dz(ax(sc.CONTROLLER_AXIS_LEFTY))
                self.rx, self.ry = self._dz(ax(sc.CONTROLLER_AXIS_RIGHTX)), self._dz(ax(sc.CONTROLLER_AXIS_RIGHTY))
                self.lt = max(0.0, ax(sc.CONTROLLER_AXIS_TRIGGERLEFT))
                self.rt = max(0.0, ax(sc.CONTROLLER_AXIS_TRIGGERRIGHT))
                self.cur = dict(a=bt(sc.CONTROLLER_BUTTON_A), b=bt(sc.CONTROLLER_BUTTON_B),
                                x=bt(sc.CONTROLLER_BUTTON_X), y=bt(sc.CONTROLLER_BUTTON_Y),
                                lb=bt(sc.CONTROLLER_BUTTON_LEFTSHOULDER), rb=bt(sc.CONTROLLER_BUTTON_RIGHTSHOULDER),
                                back=bt(sc.CONTROLLER_BUTTON_BACK), start=bt(sc.CONTROLLER_BUTTON_START))
            else:
                j = self.dev
                n = j.get_numaxes()
                nb = j.get_numbuttons()

                def g(i):
                    return j.get_axis(i) if i < n else 0.0

                def b(i):
                    return bool(j.get_button(i)) if i < nb else False
                self.lx, self.ly = self._dz(g(0)), self._dz(g(1))
                self.rx, self.ry = self._dz(g(2)), self._dz(g(3))
                self.lt = self.rt = 0.0
                self.cur = dict(a=b(0), b=b(1), x=b(2), y=b(3), lb=b(4), rb=b(5), back=b(6), start=b(7))
        except Exception:
            self.dev = None
            self.cur = {}

    def just(self, name):
        return bool(self.cur.get(name)) and not self.prev.get(name)


# ---------------------------------------------------------------------------
# THE GAME
# ---------------------------------------------------------------------------
class Game:
    def __init__(self, screen):
        self.screen = screen
        self.canvas = pygame.Surface((W, H)).convert()
        self.clock = pygame.time.Clock()
        self.art = Art()
        self.sfx = Sfx()
        self.best_level = 1
        self.high = self.load_high()
        self.pad = Pad()
        self.aim_mode = "FACING"
        self.mouse_world = None
        self.level = 1
        self.level_time = 0.0
        self.run_seed = random.randrange(10 ** 6)
        self.level_bonus = 0
        self.cfg = None
        self.walls = []
        self.layout = 0
        self.state = "TITLE"            # TITLE PLAY PAUSE WIN LOSE
        self.time = 0.0
        self.link_rect = pygame.Rect(0, 0, 1, 1)
        self.title_dust = [[random.uniform(0, W), random.uniform(300, H), random.uniform(10, 40)] for _ in range(40)]
        self.end_t = 0.0
        self.cam = [0.0, 0.0]
        self.shake = 0.0
        self.new_game()
        self.state = "TITLE"

    # ------------------------------------------------------------------ setup
    def load_high(self):
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.best_level = int(data.get("best_level", 1))
            return int(data.get("high", 0))
        except (OSError, ValueError, AttributeError):
            return 0
    def save_high(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump({"high": self.high, "best_level": self.best_level}, f)
        except OSError:
            pass
    def level_cfg(self, level):
        """Difficulty for a level. Level 1 is gentle; everything ramps with the level AND with time inside it."""
        d = level - 1
        n_pyr = [1, 2, 3, 3, 4, 4, 5][min(d, 6)]
        i0 = max(3.8, 11.5 - 0.85 * d)
        i1 = max(2.0, i0 * 0.55)
        return dict(level=level, n_pyr=n_pyr, hp_mult=1.0 + 0.09 * d,
                    grace=38.0 if level == 1 else (22.0 if level == 2 else 14.0),
                    int0=i0, int1=i1,
                    cap0=1 + d // 3, cap1=min(18, 3 + d + d // 2),
                    speed=min(1.25, 0.72 + 0.035 * d), ramp=180.0 + 25.0 * d,
                    scarab=min(0.32, 0.12 + 0.018 * d),
                    anubis=0.0 if level <= 2 else min(0.25, 0.06 + 0.018 * d),
                    group=1 if level < 5 else (2 if level < 9 else 3),
                    time=max(220.0, 380.0 - 11.0 * d), hp_en=1.0 + 0.035 * d)

    def new_game(self):
        self.level = 1
        self.run_seed = random.randrange(10 ** 6)
        self.score = 0
        self.kills = 0
        self.vehicles_lost = 0
        self.hp = 100.0
        self.dyn_count = 4
        self.shield = 0
        self.build_level(1)

    def next_level(self):
        self.level += 1
        self.hp = min(100.0, self.hp + 40.0)
        self.dyn_count = max(self.dyn_count, 4)
        self.build_level(self.level)
        self.state = "PLAY"
        self.sfx.play("enter")

    def near_wall(self, x, y, m):
        for x0, y0, x1, y1 in self.walls:
            if math.hypot(x - clamp(x, x0, x1), y - clamp(y, y0, y1)) < m:
                return True
        return False

    def build_level(self, level):
        cfg = self.level_cfg(level)
        self.cfg = cfg
        rng = random.Random(self.run_seed * 1009 + level * 7919)
        starts = [(380.0, 2000.0), (2820.0, 2000.0), (380.0, 400.0), (2820.0, 400.0), (1600.0, 2080.0), (1600.0, 320.0)]
        self.start = rng.choice(starts)
        sx, sy = self.start
        ox, oy = 1600.0, 1200.0
        for _ in range(200):
            ox, oy = rng.uniform(300, WORLD_W - 300), rng.uniform(300, WORLD_H - 300)
            if math.hypot(ox - sx, oy - sy) > 750:
                break
        orad = rng.uniform(110, 155)
        self.oasis = (ox, oy, orad)
        self.camp = (clamp(sx - 130, 100, WORLD_W - 100), clamp(sy + 40, 100, WORLD_H - 100))
        # pyramids
        names = ["GREAT PYRAMID", "SECOND PYRAMID", "THIRD PYRAMID", "FOURTH PYRAMID", "FIFTH PYRAMID"]
        halves = [rng.uniform(190, 235)] + [rng.uniform(120, 180) for _ in range(cfg["n_pyr"] - 1)]
        pyr = []
        for i, half in enumerate(halves):
            x, y = WORLD_W / 2, WORLD_H / 2
            for attempt in range(300):
                x, y = rng.uniform(450, WORLD_W - 450), rng.uniform(450, WORLD_H - 450)
                if math.hypot(x - sx, y - sy) < 950:
                    continue
                if math.hypot(x - ox, y - oy) < orad + half + 120:
                    continue
                sep = 260 if attempt < 200 else 120
                if all(math.hypot(x - q.x, y - q.y) > q.half + half + sep for q in pyr):
                    break
            pyr.append(Pyramid(x, y, half, int(half * 7.2 * cfg["hp_mult"]), names[i], level * 10 + i))
        self.pyramids = pyr

        def place(lo, hi):
            for _ in range(300):
                a, r = rng.uniform(0, math.tau), rng.uniform(lo, hi)
                x, y = sx + math.cos(a) * r, sy + math.sin(a) * r
                if not (180 < x < WORLD_W - 180 and 180 < y < WORLD_H - 180):
                    continue
                if any(math.hypot(x - q.x, y - q.y) < q.half + 170 for q in pyr):
                    continue
                if math.hypot(x - ox, y - oy) < orad + 120:
                    continue
                return x, y
            return clamp(sx + 600, 200, WORLD_W - 200), clamp(sy + 300, 200, WORLD_H - 200)
        dx, dy = place(650, 1000) if level == 1 else place(850, 1500)
        wx, wy = place(1300, 2300)
        self.vehicles = [Vehicle("dozer", dx, dy), Vehicle("wrecker", wx, wy)]
        # walls
        walls = []
        zones = [(sx, sy, 230)] + [(v.x, v.y, 130) for v in self.vehicles] + [(ox, oy, orad + 50)]

        def near(rect, zx, zy, zr):
            x0, y0, x1, y1 = rect
            return math.hypot(zx - clamp(zx, x0, x1), zy - clamp(zy, y0, y1)) < zr

        def add_wall(x0, y0, x1, y1, allow_pyr=False):
            rect = (x0, y0, x1, y1)
            if x0 < 60 or y0 < 60 or x1 > WORLD_W - 60 or y1 > WORLD_H - 60:
                return
            if any(near(rect, *z) for z in zones):
                return
            if not allow_pyr and any(near(rect, q.x, q.y, q.half + 50) for q in pyr):
                return
            for w in walls:
                if not (x1 < w[0] - 20 or x0 > w[2] + 20 or y1 < w[1] - 20 or y0 > w[3] + 20):
                    return
            walls.append(rect)
        last = getattr(self, "layout", 0)
        self.layout = 0 if level == 1 else rng.choice([i for i in (1, 2, 3) if i != last] or [1, 2, 3])
        if self.layout == 1:                                   # courtyards around each pyramid
            for q in pyr:
                R, gap, th = q.half + 150, 110, 18
                for sgn in (-1, 1):
                    add_wall(q.x - R, q.y + sgn * R - th, q.x - gap, q.y + sgn * R + th, True)
                    add_wall(q.x + gap, q.y + sgn * R - th, q.x + R, q.y + sgn * R + th, True)
                    add_wall(q.x + sgn * R - th, q.y - R, q.x + sgn * R + th, q.y - gap, True)
                    add_wall(q.x + sgn * R - th, q.y + gap, q.x + sgn * R + th, q.y + R, True)
        elif self.layout == 2:                                 # long corridors
            for _ in range(60):
                if len(walls) >= 8:
                    break
                ln = rng.uniform(500, 900)
                x, y = rng.uniform(150, WORLD_W - 150), rng.uniform(150, WORLD_H - 150)
                if rng.random() < 0.5:
                    add_wall(x, y, x + ln, y + 36)
                else:
                    add_wall(x, y, x + 36, y + ln)
        elif self.layout == 3:                                 # scattered ruins
            for _ in range(120):
                if len(walls) >= 20:
                    break
                ln = rng.uniform(110, 250)
                x, y = rng.uniform(150, WORLD_W - 150), rng.uniform(150, WORLD_H - 150)
                if rng.random() < 0.5:
                    add_wall(x, y, x + ln, y + 36)
                else:
                    add_wall(x, y, x + 36, y + ln)
        self.walls = walls
        # rocks, columns, palms
        keep_out = [(sx, sy, 260)] + [(q.x, q.y, q.half + 120) for q in pyr] + [(v.x, v.y, 150) for v in self.vehicles] \
            + [(ox, oy, orad + 40)]

        def free(x, y, extra=0):
            return all(math.hypot(x - kx, y - ky) > kr + extra for kx, ky, kr in keep_out) and not self.near_wall(x, y, 50)
        self.obstacles, self.palms = [], []
        for _ in range(40 + 8 * (level - 1)):
            x, y = rng.uniform(80, WORLD_W - 80), rng.uniform(80, WORLD_H - 80)
            if free(x, y):
                self.obstacles.append({"x": x, "y": y, "r": rng.choice([14, 18, 22, 26, 30]), "kind": "rock"})
        for _ in range(10 + 4 * (level - 1)):
            x, y = rng.uniform(80, WORLD_W - 80), rng.uniform(80, WORLD_H - 80)
            if free(x, y, 30):
                self.obstacles.append({"x": x, "y": y, "r": 22, "kind": "column"})
        for _ in range(110):
            x, y = rng.uniform(40, WORLD_W - 40), rng.uniform(40, WORLD_H - 40)
            if free(x, y, 10) and math.hypot(x - ox, y - oy) > orad - 30:
                self.palms.append((x, y, rng.choice([0, 90, 180, 270]), rng.uniform(0.8, 1.2)))
        for a in range(0, 360, 40):
            r = math.radians(a)
            self.palms.append((ox + math.cos(r) * (orad + 26), oy + math.sin(r) * (orad + 26), a, 1.1))
        # items
        self.items = []
        for kind, n in (("dyn", 7), ("fuel", 5), ("ankh", 3), ("scroll", 3)):
            for _ in range(n):
                self.spawn_item(kind)
        self.items.append({"kind": "dyn", "x": sx + 110, "y": clamp(sy - 70, 80, WORLD_H - 80), "ph": 0.0})
        self.items.append({"kind": "dyn", "x": sx + 50, "y": clamp(sy - 150, 80, WORLD_H - 80), "ph": 1.0})
        # per-level state (hp / dynamite / amulets carry over from the last level)
        self.enemies, self.bolts, self.dyns, self.parts, self.texts = [], [], [], [], []
        self.px, self.py = self.start
        self.pangle = 0.0
        self.fuel_cans = 0
        self.vehicle = None
        self.buff_speed = 0.0
        self.melee_cd = 0.0
        self.melee_vis = 0.0
        self.melee_ang = 0.0
        self.time_left = cfg["time"]
        self.level_time = 0.0
        self.destroyed = 0
        self.radar_t = 0.0
        self.radar_cd = 0.0
        self.spawn_t = cfg["grace"]
        self.item_t = {"dyn": 16.0, "fuel": 22.0, "ankh": 30.0, "scroll": 34.0}
        self.respawns = []
        n = len(self.pyramids)
        self.msg = [f"LEVEL {level}: {LAYOUTS[self.layout]} - bring down {n} pyramid{'s' if n > 1 else ''}!", 6.0]
        self.hit_snd_cd = 0.0
        self.win_delay = 0.0
        self.won = False
        self.cam = [self.px - W / 2, self.py - H / 2]
        self.shake = 0.0
        if level > 1:
            self.spawn_wave(1)
    def spawn_item(self, kind):
        for _ in range(60):
            x, y = random.uniform(100, WORLD_W - 100), random.uniform(100, WORLD_H - 100)
            if all(math.hypot(x - p.x, y - p.y) > p.half + 70 for p in self.pyramids) \
                    and math.hypot(x - self.oasis[0], y - self.oasis[1]) > self.oasis[2] + 30 \
                    and not self.near_wall(x, y, 50):
                self.items.append({"kind": kind, "x": x, "y": y, "ph": random.uniform(0, 6.28)})
                return
    def say(self, text, secs=3.5):
        self.msg = [text, secs]

    def float_text(self, text, x, y, color=WHITE):
        self.texts.append([text, x, y, 1.2, color])

    # --------------------------------------------------------------- helpers
    @property
    def ex(self):
        return (self.vehicle.x, self.vehicle.y) if self.vehicle else (self.px, self.py)

    def solid_move(self, x, y, r, crush=False):
        """Resolve an entity (circle) against the world. Returns x, y."""
        for p in self.pyramids:
            if p.alive:
                res = push_out_circle_rect(x, y, r, *p.box)
                if res:
                    x, y = res[0], res[1]
        for w in self.walls:
            res = push_out_circle_rect(x, y, r, *w)
            if res:
                x, y = res[0], res[1]
        for o in self.obstacles[:]:
            res = push_out_circle_circle(x, y, r, o["x"], o["y"], o["r"])
            if res:
                if crush and o["kind"] == "rock" and o["r"] <= 30:
                    self.obstacles.remove(o)
                    self.spawn_chips(o["x"], o["y"], 6)
                    self.sfx.play("hit")
                else:
                    x, y = res[0], res[1]
        res = push_out_circle_circle(x, y, r, self.oasis[0], self.oasis[1], self.oasis[2] - 20)
        if res:
            x, y = res[0], res[1]
        return clamp(x, r, WORLD_W - r), clamp(y, r, WORLD_H - r)

    def spawn_chips(self, x, y, n, color=None):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(80, 320)
            self.parts.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp, random.uniform(0.35, 0.8),
                                       random.uniform(3, 7), color or random.choice(STONES), "chip"))
        del self.parts[:-600]

    def spawn_dust(self, x, y, n, spread=60, big=False):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            d = random.uniform(0, spread)
            self.parts.append(Particle(x + math.cos(a) * d, y + math.sin(a) * d, random.uniform(-30, 30),
                                       random.uniform(-40, 10), random.uniform(0.8, 1.7),
                                       random.choice([14, 18, 22, 26, 30] if big else [8, 10, 14, 18]), None, "dust"))
        del self.parts[:-600]

    def explosion(self, x, y, radius=170, dmg=210, by_player=True):
        self.sfx.play("boom")
        self.shake = max(self.shake, 0.6)
        self.parts.append(Particle(x, y, 0, 0, 0.45, radius, (255, 190, 60), "ring"))
        self.parts.append(Particle(x, y, 0, 0, 0.25, radius * 0.55, (255, 255, 230), "flash"))
        self.spawn_chips(x, y, 22, (90, 70, 50))
        for _ in range(16):
            a = random.uniform(0, math.tau)
            sp = random.uniform(100, 380)
            self.parts.append(Particle(x, y, math.cos(a) * sp, math.sin(a) * sp, random.uniform(0.3, 0.7),
                                       random.uniform(3, 6), random.choice([(255, 220, 90), (255, 140, 40)]), "spark"))
        self.spawn_dust(x, y, 10, radius * 0.5, True)
        for p in self.pyramids:
            if not p.alive:
                continue
            x0, y0, x1, y1 = p.box
            d = math.hypot(x - clamp(x, x0, x1), y - clamp(y, y0, y1))
            if d <= radius:
                amount = dmg * (1.0 - 0.45 * d / radius)
                self.damage_pyramid(p, amount, x, y)
        for e in self.enemies[:]:
            d = math.hypot(e.x - x, e.y - y)
            if d <= radius + e.r:
                self.hurt_enemy(e, 120 * (1 - d / (radius + e.r)) + 40)
        if by_player:
            d = math.hypot(self.ex[0] - x, self.ex[1] - y)
            if d < radius * 0.55:
                if self.vehicle:
                    self.hurt_vehicle(self.vehicle, 30)
                else:
                    self.hurt_player(25)

    def damage_pyramid(self, p, amount, x, y):
        if not p.alive:
            return
        p.hp -= amount
        p.flash = 0.12
        self.spawn_chips(x, y, 3)
        if self.hit_snd_cd <= 0:
            self.sfx.play("hit")
            self.hit_snd_cd = 0.12
        if p.hp <= 0:
            p.hp = 0
            p.alive = False
            p.last_size = p.half * 0.3
            p.collapse = 0.0
            p.last_size = p.half * 0.3 + 0.0
            self.destroyed += 1
            self.score += 1000
            self.sfx.play("crumble")
            self.shake = 1.0
            self.say(f"{p.name} DESTROYED!  Babylon Is Fallen", 4.0)
            self.float_text("+1000", p.x, p.y - 40, GOLD)
            self.spawn_dust(p.x, p.y, 30, p.half, True)
            self.spawn_chips(p.x, p.y, 40)
            if all(not q.alive for q in self.pyramids):
                self.won = True
                self.win_delay = 3.2

    def hurt_enemy(self, e, amount):
        e.hp -= amount
        e.hurt = 0.15
        if e.hp <= 0 and e in self.enemies:
            self.enemies.remove(e)
            self.kills += 1
            self.score += e.pts
            self.sfx.play("kill")
            self.spawn_dust(e.x, e.y, 3, 10)
            self.spawn_chips(e.x, e.y, 5, (60, 160, 200) if e.kind == "scarab" else (230, 220, 180))
            self.float_text(f"+{e.pts}", e.x, e.y - 20, (255, 235, 140))

    def hurt_player(self, amount):
        if self.shield > 0:
            self.shield -= 1
            self.sfx.play("shield")
            self.float_text("BLOCKED", self.px, self.py - 40, (150, 220, 255))
            return
        self.hp -= amount
        self.sfx.play("hurt")
        self.shake = max(self.shake, 0.25)
        if self.hp <= 0:
            self.hp = 0
            self.end_game(False)

    def hurt_vehicle(self, v, amount):
        if self.shield > 0 and v.driver:
            self.shield -= 1
            self.sfx.play("shield")
            return
        v.hp -= amount
        self.sfx.play("hurt")
        if v.hp <= 0:
            self.explosion(v.x, v.y, 150, 60, by_player=False)
            self.vehicles.remove(v)
            self.vehicles_lost += 1
            if v.driver:
                self.vehicle = None
                self.px, self.py = v.x, v.y
                self.hurt_player(20)
            self.respawns.append([40.0, v.kind])
            self.say(f"YOUR {v.name} WAS DESTROYED! Another will turn up in the sand...", 4.5)

    # -------------------------------------------------------------- spawning
    def spawn_wave(self, n):
        cfg = self.cfg
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            dist = random.uniform(750, 1050)
            x = clamp(self.ex[0] + math.cos(ang) * dist, 50, WORLD_W - 50)
            y = clamp(self.ex[1] + math.sin(ang) * dist, 50, WORLD_H - 50)
            roll = random.random()
            new = []
            if roll < cfg["scarab"]:
                for _k in range(cfg["group"]):
                    new.append(Enemy("scarab", x + random.uniform(-40, 40), y + random.uniform(-40, 40)))
            elif roll < cfg["scarab"] + cfg["anubis"]:
                new.append(Enemy("anubis", x, y))
            else:
                new.append(Enemy("mummy", x, y))
            for e in new:
                e.speed *= cfg["speed"]
                e.hp = e.max_hp = e.max_hp * cfg["hp_en"]
            self.enemies.extend(new)
    def on_enter_exit(self):
        if self.vehicle:
            v = self.vehicle
            v.driver = False
            v.speed = 0
            self.vehicle = None
            a = v.angle + math.pi / 2
            self.px, self.py = self.solid_move(v.x + math.cos(a) * (v.radius + 26),
                                               v.y + math.sin(a) * (v.radius + 26), 16)
            self.sfx.play("enter")
            return
        best, bd = None, 110
        for v in self.vehicles:
            d = math.hypot(v.x - self.px, v.y - self.py)
            if d < bd:
                best, bd = v, d
        if best:
            self.vehicle = best
            best.driver = True
            if self.fuel_cans > 0:
                best.fuel = min(100.0, best.fuel + 45 * self.fuel_cans)
                self.fuel_cans = 0
            self.sfx.play("enter")
            if best.kind == "dozer":
                self.say("BULLDOZER: W/S drive, A/D steer.  STRIKE the pyramid, BACK UP, strike again!", 5.0)
            else:
                self.say("WRECKING TRUCK: press SPACE to swing the ball!", 4.0)
        else:
            self.say("Nothing to drive nearby - explore the desert!  (R = Eye of Horus)", 3.0)

    def read_input(self):
        K = pygame
        keys = K.key.get_pressed()
        kx = (1 if (keys[K.K_d] or keys[K.K_RIGHT]) else 0) - (1 if (keys[K.K_a] or keys[K.K_LEFT]) else 0)
        ky = (1 if (keys[K.K_s] or keys[K.K_DOWN]) else 0) - (1 if (keys[K.K_w] or keys[K.K_UP]) else 0)
        p = self.pad
        mx, my = float(kx), float(ky)
        throttle, steer = float(-ky), float(kx)
        aim = None
        boost = bool(K.key.get_mods() & K.KMOD_SHIFT)
        mouse_fwd = False
        if p.active:
            if math.hypot(p.lx, p.ly) > math.hypot(mx, my):
                mx, my = p.lx, p.ly
            throttle = clamp(throttle - p.ly + p.rt - p.lt, -1.0, 1.0)
            steer = clamp(steer + p.lx, -1.0, 1.0)
            if p.cur.get("rb"):
                boost = True
            if math.hypot(p.rx, p.ry) > 0.35:
                aim = math.atan2(p.ry, p.rx)
        if self.aim_mode == "MOUSE":
            mxp, myp = K.mouse.get_pos()
            self.mouse_world = (mxp + self.cam[0], myp + self.cam[1])
            mouse_fwd = bool(K.mouse.get_pressed()[2])
        return dict(mx=mx, my=my, throttle=throttle, steer=steer, aim=aim, boost=boost, mouse_fwd=mouse_fwd)

    def aim_point(self):
        """Where dynamite lands: straight ahead of you (FACING mode) or at the cursor (MOUSE mode)."""
        if self.aim_mode == "MOUSE":
            mx, my = pygame.mouse.get_pos()
            tx, ty = mx + self.cam[0], my + self.cam[1]
            d = math.hypot(tx - self.px, ty - self.py)
            if d > 380:
                tx = self.px + (tx - self.px) / d * 380
                ty = self.py + (ty - self.py) / d * 380
            return tx, ty
        return self.px + math.cos(self.pangle) * 320, self.py + math.sin(self.pangle) * 320

    def throw_dynamite(self):
        if self.vehicle or self.dyn_count <= 0:
            return
        tx, ty = self.aim_point()
        self.dyn_count -= 1
        self.dyns.append({"sx": self.px, "sy": self.py, "tx": tx, "ty": ty, "x": self.px, "y": self.py,
                          "t": 0.0, "fuse": 2.1, "tick": 0.0})
        self.sfx.play("throw")

    def fire(self):
        if self.vehicle and self.vehicle.kind == "wrecker":
            self.swing_wrecker()
        else:
            self.throw_dynamite()

    def toggle_aim(self):
        self.aim_mode = "MOUSE" if self.aim_mode == "FACING" else "FACING"
        self.sfx.play("click")
        if self.state == "PLAY":
            self.say("AIM MODE: MOUSE (mouse aims / steers, left click melee, right click dynamite)"
                     if self.aim_mode == "MOUSE" else "AIM MODE: FACING (you fire the way you face)", 3.5)
    def swing_wrecker(self):
        v = self.vehicle
        if v and v.kind == "wrecker" and v.swing_t <= 0 and v.swing_cd <= 0:
            v.swing_t = 1.4
            v.swing_a = v.angle - math.pi / 2
            self.sfx.play("swing")

    def melee(self):
        if self.vehicle or self.melee_cd > 0:
            return
        self.melee_ang = self.pangle
        self.melee_cd = 0.38
        self.melee_vis = 0.16
        self.sfx.play("swing")
        for e in self.enemies[:]:
            d = math.hypot(e.x - self.px, e.y - self.py)
            if d < 84 + e.r and abs(angle_diff(self.melee_ang, math.atan2(e.y - self.py, e.x - self.px))) < 1.1:
                self.hurt_enemy(e, 24)
                e.kx, e.ky = math.cos(self.melee_ang) * 260, math.sin(self.melee_ang) * 260
        for p in self.pyramids:
            if p.alive:
                x0, y0, x1, y1 = p.box
                if math.hypot(self.px - clamp(self.px, x0, x1), self.py - clamp(self.py, y0, y1)) < 54:
                    self.damage_pyramid(p, 5, self.px + math.cos(self.melee_ang) * 40, self.py + math.sin(self.melee_ang) * 40)
    def use_radar(self):
        if self.radar_cd > 0:
            self.say(f"EYE OF HORUS is recharging ({int(self.radar_cd)}s)", 1.5)
            return
        self.radar_t = 4.5
        self.radar_cd = 18.0
        self.sfx.play("radar")

    def read_scroll(self):
        spell = random.choice(["speed", "amulet", "thunder", "barque"])
        self.sfx.play("scroll")
        if spell == "speed":
            self.buff_speed = 12.0
            self.say("BOOK OF THE DEAD - SPELL 17: BCCRSS SEED OF TRUTH!", 3.5)
        elif spell == "amulet":
            self.shield = min(5, self.shield + 3)
            self.say("BOOK OF THE DEAD - SPELL 30B: HEART AMULET ~ You Are Not A Legal Name (blocks 3 hits)", 3.5)
        elif spell == "thunder":
            self.say("BOOK OF THE DEAD - SPELL 125: IT'S ILLEGAL TO USE A LEGAL NAME!", 3.5)
            self.shake = 0.6
            for e in self.enemies[:]:
                if abs(e.x - self.ex[0]) < W * 0.75 and abs(e.y - self.ex[1]) < H * 0.75:
                    self.hurt_enemy(e, 120)
                    self.parts.append(Particle(e.x, e.y, 0, 0, 0.3, 34, (200, 230, 255), "flash"))
        else:
            self.time_left += 30
            self.say("BOOK OF THE DEAD - SPELL 64: Legal Name Beast Mark Stripped (+30 s)", 3.5)

    # --------------------------------------------------------------- updates
    def update_player(self, dt, inp):
        speed = 235 * (1.4 if self.buff_speed > 0 else 1.0) * (1.3 if inp["boost"] else 1.0)
        mx, my = inp["mx"], inp["my"]
        mag = math.hypot(mx, my)
        if mag > 0.05:
            n = max(1.0, mag)
            self.px += mx / n * speed * dt
            self.py += my / n * speed * dt
            if self.aim_mode != "MOUSE":
                self.pangle = math.atan2(my, mx)
        if inp["aim"] is not None:
            self.pangle = inp["aim"]
        elif self.aim_mode == "MOUSE" and self.mouse_world:
            self.pangle = math.atan2(self.mouse_world[1] - self.py, self.mouse_world[0] - self.px)
        self.px, self.py = self.solid_move(self.px, self.py, 16)
    def update_vehicle(self, v, dt, inp):
        if v.fuel <= 0 and self.fuel_cans > 0:
            v.fuel = min(100.0, 45.0)
            self.fuel_cans -= 1
            self.say("Refuelled from a jerry can.", 2)
        throttle, steer = inp["throttle"], inp["steer"]
        boost = inp["boost"] and v.kind == "dozer" and throttle > 0.3
        if self.aim_mode == "MOUSE" and self.mouse_world:
            ta = math.atan2(self.mouse_world[1] - v.y, self.mouse_world[0] - v.x)
            steer = clamp(angle_diff(v.angle, ta) / 0.35, -1.0, 1.0)
            if inp["mouse_fwd"]:
                throttle = max(throttle, 1.0)
        if abs(throttle) > 0.05 and v.fuel <= 0:
            throttle = 0.0
            self.say("OUT OF FUEL - find a jerry can!  (press E and look for one)", 1.5)
        turn_rate = 2.4 if v.kind == "dozer" else 1.9
        v.angle += steer * turn_rate * dt * (0.45 + 0.55 * min(1.0, abs(v.speed) / 90.0))
        slow = 0.45 if v.swing_t > 0 else 1.0
        fwd = v.max_speed * (1.45 if boost else 1.0) * slow
        target = throttle * fwd if throttle > 0 else throttle * v.max_speed * 0.4
        v.speed += clamp(target - v.speed, -430 * dt, v.accel * dt)
        if abs(throttle) > 0.05:
            v.fuel = max(0.0, v.fuel - (4.6 if boost else 2.2) * abs(throttle) * dt)
        v.eng_t -= dt
        if abs(v.speed) > 25 and v.eng_t <= 0:
            self.sfx.play("engine")
            v.eng_t = 0.34
        nx = v.x + math.cos(v.angle) * v.speed * dt
        ny = v.y + math.sin(v.angle) * v.speed * dt
        # pyramids: the bulldozer only does damage on a fresh STRIKE - back up and strike again
        for p in self.pyramids:
            if not p.alive:
                continue
            res = push_out_circle_rect(nx, ny, v.radius, *p.box)
            if res:
                nx, ny = res[0], res[1]
                if v.kind == "dozer" and v.armed and v.speed >= 70:
                    hit = v.speed
                    dmg = 40 + (hit - 40) * 0.7
                    cxp, cyp = nx + math.cos(v.angle) * v.radius, ny + math.sin(v.angle) * v.radius
                    self.damage_pyramid(p, dmg, cxp, cyp)
                    self.spawn_dust(cxp, cyp, 4, 24)
                    self.shake = max(self.shake, 0.3)
                    v.armed = False
                    v.speed = -min(150.0, hit * 0.55)
                    self.float_text("STRIKE!  BACK UP!", v.x, v.y - 64, (255, 220, 120))
                else:
                    v.speed = min(v.speed, 0.0)
        v.x, v.y = self.solid_move(nx, ny, v.radius, crush=(v.kind == "dozer" and v.speed > 80))
        self.px, self.py = v.x, v.y
        self.pangle = v.angle
        if v.kind == "dozer" and not v.armed:
            clear = 9999.0
            for p in self.pyramids:
                if p.alive:
                    x0, y0, x1, y1 = p.box
                    clear = min(clear, math.hypot(v.x - clamp(v.x, x0, x1), v.y - clamp(v.y, y0, y1)) - v.radius)
            if clear > 55:
                v.armed = True
        # dozer crushes enemies
        if v.kind == "dozer" and v.speed > 55:
            bx, by = v.x + math.cos(v.angle) * 30, v.y + math.sin(v.angle) * 30
            for e in self.enemies[:]:
                if math.hypot(e.x - bx, e.y - by) < v.radius + e.r:
                    self.hurt_enemy(e, 90)
        # wrecking ball
        if v.kind == "wrecker" and v.swing_t > 0:
            v.swing_a += (2 * math.pi * 1.6 / 1.4) * dt
            bx, by = v.ball_pos()
            for p in self.pyramids:
                if p.alive and v.pyr_cd.get(id(p), 0) <= 0:
                    x0, y0, x1, y1 = p.box
                    if math.hypot(bx - clamp(bx, x0, x1), by - clamp(by, y0, y1)) < 34:
                        self.damage_pyramid(p, 62, bx, by)
                        self.spawn_dust(bx, by, 3, 20)
                        self.shake = max(self.shake, 0.3)
                        v.pyr_cd[id(p)] = 0.3
            for e in self.enemies[:]:
                if math.hypot(e.x - bx, e.y - by) < 34 + e.r:
                    self.hurt_enemy(e, 80)
            for o in self.obstacles[:]:
                if o["kind"] == "rock" and math.hypot(o["x"] - bx, o["y"] - by) < 34 + o["r"]:
                    self.obstacles.remove(o)
                    self.spawn_chips(o["x"], o["y"], 6)
            v.swing_t -= dt
            if v.swing_t <= 0:
                v.swing_cd = 1.0
        v.swing_cd = max(0.0, v.swing_cd - dt)
        v.ram_cd = max(0.0, v.ram_cd - dt)
        for k in list(v.pyr_cd):
            v.pyr_cd[k] -= dt
    def update_enemy(self, e, dt):
        tx, ty = self.ex
        dx, dy = tx - e.x, ty - e.y
        d = math.hypot(dx, dy) or 1.0
        e.angle = math.atan2(dy, dx)
        e.hurt = max(0.0, e.hurt - dt)
        e.x += e.kx * dt
        e.y += e.ky * dt
        e.kx *= max(0.0, 1 - 8 * dt)
        e.ky *= max(0.0, 1 - 8 * dt)
        e.atk_cd -= dt
        tr = self.vehicle.radius if self.vehicle else 16
        if e.kind == "anubis":
            if d > 430:
                mv = 1.0
            elif d < 300:
                mv = -0.6
            else:
                mv = 0.0
            e.x += dx / d * e.speed * mv * dt
            e.y += dy / d * e.speed * mv * dt
            e.x += -dy / d * e.speed * 0.45 * math.sin(self.time + e.wob) * dt
            e.y += dx / d * e.speed * 0.45 * math.sin(self.time + e.wob) * dt
            if d < 720 and e.atk_cd <= 0:
                e.atk_cd = e.cd
                self.bolts.append({"x": e.x, "y": e.y, "vx": dx / d * 340, "vy": dy / d * 340, "life": 3.0})
                self.sfx.play("tick")
        else:
            ang = e.angle + (math.sin(self.time * 7 + e.wob) * 0.45 if e.kind == "scarab" else 0)
            e.x += math.cos(ang) * e.speed * dt
            e.y += math.sin(ang) * e.speed * dt
            if d < e.r + tr + 4 and e.atk_cd <= 0:
                e.atk_cd = e.cd
                if self.vehicle:
                    self.hurt_vehicle(self.vehicle, e.dmg * 0.7)
                else:
                    self.hurt_player(e.dmg)
        e.x = clamp(e.x, 10, WORLD_W - 10)
        e.y = clamp(e.y, 10, WORLD_H - 10)
        # spirits cannot enter pyramids
        for p in self.pyramids:
            if p.alive:
                res = push_out_circle_rect(e.x, e.y, e.r, *p.box)
                if res:
                    e.x, e.y = res[0], res[1]

    def update_play(self, dt):
        self.time += dt
        self.level_time += dt
        self.time_left -= dt
        if self.time_left <= 0:
            self.time_left = 0
            self.end_game(False)
            return
        inp = self.read_input()
        if self.vehicle:
            self.update_vehicle(self.vehicle, dt, inp)
        else:
            self.update_player(dt, inp)
        self.hit_snd_cd = max(0.0, self.hit_snd_cd - dt)
        self.melee_cd = max(0.0, self.melee_cd - dt)
        self.melee_vis = max(0.0, self.melee_vis - dt)
        self.buff_speed = max(0.0, self.buff_speed - dt)
        self.radar_t = max(0.0, self.radar_t - dt)
        self.radar_cd = max(0.0, self.radar_cd - dt)
        for v in self.vehicles:
            if not v.found and math.hypot(v.x - self.px, v.y - self.py) < 420:
                v.found = True
                self.say(f"YOU FOUND A {v.name}!  Walk up and press E", 4.0)
                self.sfx.play("scroll")
            if not v.driver:
                v.speed = 0
                v.swing_t = 0.0
        # dynamite
        for d in self.dyns[:]:
            d["t"] += dt
            d["fuse"] -= dt
            u = min(1.0, d["t"] / 0.45)
            d["x"] = lerp(d["sx"], d["tx"], u)
            d["y"] = lerp(d["sy"], d["ty"], u)
            d["tick"] -= dt
            if d["tick"] <= 0:
                d["tick"] = 0.3 if d["fuse"] > 0.8 else 0.12
                self.sfx.play("tick")
            if d["fuse"] <= 0:
                self.dyns.remove(d)
                self.explosion(d["x"], d["y"])
        # enemies / bolts
        for e in self.enemies[:]:
            self.update_enemy(e, dt)
        tr = self.vehicle.radius if self.vehicle else 16
        for b in self.bolts[:]:
            b["x"] += b["vx"] * dt
            b["y"] += b["vy"] * dt
            b["life"] -= dt
            if math.hypot(b["x"] - self.ex[0], b["y"] - self.ex[1]) < tr + 8:
                self.bolts.remove(b)
                if self.vehicle:
                    self.hurt_vehicle(self.vehicle, 10)
                else:
                    self.hurt_player(12)
            elif b["life"] <= 0:
                self.bolts.remove(b)
        # spawning
        # guardians arrive gradually: a calm start, then more and faster the longer you take - and every level
        cfg = self.cfg
        ramp = clamp(self.level_time / cfg["ramp"], 0.0, 1.0)
        self.spawn_t -= dt
        if self.spawn_t <= 0:
            self.spawn_t = lerp(cfg["int0"], cfg["int1"], ramp)
            if len(self.enemies) < int(round(lerp(cfg["cap0"], cfg["cap1"], ramp))):
                self.spawn_wave(1)
        for kind in self.item_t:
            self.item_t[kind] -= dt
            if self.item_t[kind] <= 0:
                self.item_t[kind] = {"dyn": 15, "fuel": 22, "ankh": 30, "scroll": 36}[kind]
                if sum(1 for i in self.items if i["kind"] == kind) < {"dyn": 8, "fuel": 5, "ankh": 3, "scroll": 3}[kind]:
                    self.spawn_item(kind)
        for r in self.respawns[:]:
            r[0] -= dt
            if r[0] <= 0:
                self.respawns.remove(r)
                for _ in range(30):
                    x, y = random.uniform(200, WORLD_W - 200), random.uniform(200, WORLD_H - 200)
                    if all(math.hypot(x - p.x, y - p.y) > p.half + 150 for p in self.pyramids) \
                            and math.hypot(x - self.ex[0], y - self.ex[1]) > 500:
                        nv = Vehicle(r[1], x, y)
                        self.vehicles.append(nv)
                        self.say(f"A new {nv.name} has appeared in the desert!  Use the Eye of Horus (R)", 4.0)
                        break
        # pickups
        pr = (self.vehicle.radius + 8) if self.vehicle else 30
        for it in self.items[:]:
            it["ph"] += dt * 3
            if math.hypot(it["x"] - self.ex[0], it["y"] - self.ex[1]) < pr + 14:
                self.items.remove(it)
                k = it["kind"]
                self.sfx.play("pickup")
                if k == "dyn":
                    self.dyn_count = min(12, self.dyn_count + 3)
                    self.float_text("+3 DYNAMITE", it["x"], it["y"] - 20, (255, 160, 120))
                elif k == "fuel":
                    if self.vehicle:
                        self.vehicle.fuel = min(100.0, self.vehicle.fuel + 45)
                        self.float_text("+FUEL", it["x"], it["y"] - 20, (255, 200, 90))
                    else:
                        self.fuel_cans = min(3, self.fuel_cans + 1)
                        self.float_text("JERRY CAN (used when you drive)", it["x"], it["y"] - 20, (255, 200, 90))
                elif k == "ankh":
                    self.hp = min(100.0, self.hp + 40)
                    self.float_text("+40 HEART", it["x"], it["y"] - 20, (255, 120, 140))
                else:
                    self.read_scroll()
        # world
        for p in self.pyramids:
            p.flash = max(0.0, p.flash - dt)
            if not p.alive and p.collapse < 2.0:
                p.collapse += dt
                if random.random() < 0.7:
                    self.spawn_dust(p.x, p.y, 2, p.half * 0.9, True)
                self.shake = max(self.shake, 0.3)
        for pt in self.parts[:]:
            pt.life -= dt
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            if pt.kind in ("dust", "chip"):
                pt.vx *= max(0.0, 1 - 1.5 * dt)
                pt.vy *= max(0.0, 1 - 1.5 * dt)
            if pt.life <= 0:
                self.parts.remove(pt)
        for t in self.texts[:]:
            t[3] -= dt
            t[2] -= 30 * dt
            if t[3] <= 0:
                self.texts.remove(t)
        if self.msg[1] > 0:
            self.msg[1] -= dt
        self.shake = max(0.0, self.shake - dt * 1.4)
        # camera
        tx, ty = self.px - W / 2, self.py - H / 2
        self.cam[0] += (clamp(tx, 0, WORLD_W - W) - self.cam[0]) * min(1.0, 7 * dt)
        self.cam[1] += (clamp(ty, 0, WORLD_H - H) - self.cam[1]) * min(1.0, 7 * dt)
        if self.won:
            self.win_delay -= dt
            if self.win_delay <= 0:
                self.end_game(True)

    def end_game(self, win):
        if self.state in ("LEVELDONE", "LOSE"):
            return
        self.end_t = 0.0
        if win:
            self.state = "LEVELDONE"
            self.level_bonus = int(self.time_left) * 15
            self.score += self.level_bonus
            self.sfx.play("win")
        else:
            self.state = "LOSE"
            self.sfx.play("lose")
        self.best_level = max(self.best_level, self.level)
        if self.score > self.high:
            self.high = self.score
        self.save_high()
    def handle(self, e):
        if e.type == pygame.QUIT:
            self.quit()
        elif e.type == pygame.KEYDOWN:
            self.on_key(e.key)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            self.on_mouse_down(e.button)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.on_click(e.pos)

    def process_pad(self, dt):
        p = self.pad
        p.update(dt)
        if not p.active:
            return
        for name in ("a", "b", "x", "y", "start", "back"):
            if p.just(name):
                self.on_pad_button(name)

    def on_pad_button(self, name):
        st = self.state
        if st == "TITLE":
            if name in ("a", "start"):
                self.start_play()
        elif st in ("LEVELDONE", "LOSE"):
            if name in ("a", "start") and self.end_t > 1.0:
                self.advance()
        elif st == "PAUSE":
            if name in ("a", "start", "b"):
                self.state = "PLAY"
        elif st == "PLAY":
            if name == "start":
                self.state = "PAUSE"
            elif name == "y":
                self.on_enter_exit()
            elif name == "b":
                self.use_radar()
            elif name == "a":
                self.fire()
            elif name == "x":
                self.melee()
            elif name == "back":
                self.toggle_aim()

    def on_mouse_down(self, button):
        if self.state != "PLAY":
            return
        if button == 1:
            if self.vehicle and self.vehicle.kind == "wrecker":
                self.swing_wrecker()
            else:
                self.melee()
        elif button == 3 and not self.vehicle:
            self.throw_dynamite()
    def start_play(self):
        self.new_game()
        self.state = "PLAY"
        self.sfx.play("enter")

    def advance(self):
        if self.state == "LEVELDONE":
            self.next_level()
        else:
            self.start_play()
    def on_click(self, pos):
        if self.state in ("TITLE", "LEVELDONE", "LOSE", "PAUSE") and self.link_rect.collidepoint(pos):
            try:
                webbrowser.open(LINK_URL)
            except Exception:
                pass
            return
        if self.state == "TITLE":
            self.start_play()
        elif self.state in ("LEVELDONE", "LOSE") and self.end_t > 1.0:
            self.advance()
        elif self.state == "PAUSE":
            self.state = "PLAY"
    def on_key(self, key):
        K = pygame
        if key == K.K_F11:
            pygame.display.toggle_fullscreen()
        elif key == K.K_m:
            self.sfx.toggle_music()
        elif key == K.K_n:
            self.sfx.toggle_sound()
        elif key == K.K_TAB and self.state in ("PLAY", "PAUSE", "TITLE"):
            self.toggle_aim()
        if self.state == "TITLE":
            if key in (K.K_SPACE, K.K_RETURN):
                self.start_play()
            elif key == K.K_ESCAPE:
                self.quit()
        elif self.state == "PLAY":
            if key in (K.K_ESCAPE, K.K_p):
                self.state = "PAUSE"
            elif key == K.K_e:
                self.on_enter_exit()
            elif key == K.K_r:
                self.use_radar()
            elif key == K.K_SPACE:
                self.fire()
            elif key == K.K_f:
                self.melee()
        elif self.state == "PAUSE":
            if key in (K.K_ESCAPE, K.K_p, K.K_RETURN, K.K_SPACE):
                self.state = "PLAY"
            elif key == K.K_q:
                self.quit()
        elif self.state in ("LEVELDONE", "LOSE"):
            if key in (K.K_RETURN, K.K_SPACE) and self.end_t > 1.0:
                self.advance()
            elif key == K.K_ESCAPE:
                self.quit()
    def quit(self):
        pygame.quit()
        sys.exit()

    # ------------------------------------------------------------------ draw
    def world_to_screen(self, x, y):
        return x - self.cam[0], y - self.cam[1]

    def draw_world(self, s):
        A = self.art
        cx, cy = self.cam
        if self.shake > 0:
            cx += random.uniform(-1, 1) * self.shake * 14
            cy += random.uniform(-1, 1) * self.shake * 14
        cam = (cx, cy)
        ts = 512
        for ty in range(int(cy // ts), int((cy + H) // ts) + 1):
            for tx in range(int(cx // ts), int((cx + W) // ts) + 1):
                s.blit(A.sand, (tx * ts - cx, ty * ts - cy))
        # world edge
        pygame.draw.rect(s, (140, 110, 70), (-cx - 20, -cy - 20, WORLD_W + 40, WORLD_H + 40), 20)

        def vis(x, y, m=120):
            return -m < x - cx < W + m and -m < y - cy < H + m
        # oasis
        ox, oy, orad = self.oasis
        if vis(ox, oy, orad + 80):
            pygame.draw.circle(s, (180, 160, 100), (int(ox - cx), int(oy - cy)), int(orad + 14))
            pygame.draw.circle(s, (46, 120, 160), (int(ox - cx), int(oy - cy)), int(orad))
            pygame.draw.circle(s, (80, 170, 200), (int(ox - cx - 20), int(oy - cy - 16)), int(orad * 0.6))
            pygame.draw.circle(s, (130, 205, 225), (int(ox - cx - 40), int(oy - cy - 30)), int(orad * 0.22))
        # camp
        if vis(self.camp[0], self.camp[1], 140):
            s.blit(A.tent, (self.camp[0] - 85 - cx, self.camp[1] - 65 - cy))
        # stone walls
        for (x0, y0, x1, y1) in self.walls:
            if x1 - cx > -60 and x0 - cx < W + 60 and y1 - cy > -60 and y0 - cy < H + 60:
                r = pygame.Rect(int(x0 - cx), int(y0 - cy), int(x1 - x0), int(y1 - y0))
                pygame.draw.rect(s, (140, 112, 76), r.move(6, 8))
                pygame.draw.rect(s, (198, 168, 118), r)
                pygame.draw.rect(s, (120, 96, 64), r, 3)
                if r.w >= r.h:
                    for bx in range(r.x + 30, r.right, 30):
                        pygame.draw.line(s, (150, 122, 84), (bx, r.y + 2), (bx, r.bottom - 2), 2)
                else:
                    for by in range(r.y + 30, r.bottom, 30):
                        pygame.draw.line(s, (150, 122, 84), (r.x + 2, by), (r.right - 2, by), 2)
        # rubble of destroyed / damaged pyramids
        for p in self.pyramids:
            if vis(p.x, p.y, p.half + 140):
                p.draw_rubble(s, cam)
        # items
        for it in self.items:
            if vis(it["x"], it["y"], 60):
                img = A.items[it["kind"]]
                bob = math.sin(it["ph"]) * 4
                s.blit(img, img.get_rect(center=(it["x"] - cx, it["y"] - cy + bob)))
        # obstacles
        for o in self.obstacles:
            if vis(o["x"], o["y"], 60):
                img = A.column if o["kind"] == "column" else A.rocks[o["r"]]
                s.blit(img, img.get_rect(center=(o["x"] - cx, o["y"] - cy)))
        # pyramids
        for p in sorted(self.pyramids, key=lambda q: q.y):
            if vis(p.x, p.y, p.half + 140):
                p.draw(s, cam, A)
        # vehicles
        for v in self.vehicles:
            if vis(v.x, v.y, 120):
                img = A.dozer if v.kind == "dozer" else A.wrecker
                blit_rot(s, img, v.x - cx, v.y - cy, v.angle)
                if v.kind == "wrecker" and v.swing_t > 0:
                    bx, by = v.ball_pos()
                    pygame.draw.line(s, (60, 60, 66), (v.x - cx, v.y - cy), (bx - cx, by - cy), 5)
                    pygame.draw.circle(s, (30, 30, 36), (int(bx - cx), int(by - cy)), 30)
                    pygame.draw.circle(s, (90, 90, 100), (int(bx - cx - 8), int(by - cy - 8)), 12)
                elif v.kind == "wrecker":
                    ba = v.angle - math.pi / 2
                    pygame.draw.line(s, (60, 60, 66), (v.x - cx, v.y - cy),
                                     (v.x + math.cos(ba) * 60 - cx, v.y + math.sin(ba) * 60 - cy), 4)
                    pygame.draw.circle(s, (30, 30, 36), (int(v.x + math.cos(ba) * 66 - cx), int(v.y + math.sin(ba) * 66 - cy)), 14)
                if not v.driver:
                    bar = pygame.Rect(0, 0, 60, 8)
                    bar.center = (int(v.x - cx), int(v.y - cy - 70))
                    pygame.draw.rect(s, (20, 20, 20), bar)
                    pygame.draw.rect(s, GREEN, (bar.x, bar.y, int(bar.w * v.hp / v.max_hp), bar.h))
                    if v.found:
                        t = A.text(A.f_tiny, f"{v.name}  [E]", GOLD)
                        s.blit(t, t.get_rect(center=(int(v.x - cx), int(v.y - cy - 86))))
        # enemies
        for e in self.enemies:
            if vis(e.x, e.y, 60):
                img = A.enemy[e.kind]
                blit_rot(s, img, e.x - cx, e.y - cy, e.angle)
                if e.hurt > 0:
                    pygame.draw.circle(s, (255, 255, 255), (int(e.x - cx), int(e.y - cy)), int(e.r), 3)
                if e.kind != "scarab" and e.hp < e.max_hp:
                    pygame.draw.rect(s, (20, 20, 20), (e.x - cx - 16, e.y - cy - e.r - 10, 32, 5))
                    pygame.draw.rect(s, RED, (e.x - cx - 16, e.y - cy - e.r - 10, 32 * e.hp / e.max_hp, 5))
        # player (on foot)
        if not self.vehicle:
            blit_rot(s, A.player, self.px - cx, self.py - cy, self.pangle)
            if self.melee_vis > 0:
                u = 1 - self.melee_vis / 0.16
                pts = [(self.px - cx + math.cos(self.melee_ang - 1.0 + u * 2.0 + k * 0.06) * (64 - k),
                        self.py - cy + math.sin(self.melee_ang - 1.0 + u * 2.0 + k * 0.06) * (64 - k)) for k in range(0, 14, 2)]
                pygame.draw.lines(s, (255, 250, 220), False, pts, 5)
            if self.shield > 0:
                pygame.draw.circle(s, (150, 220, 255), (int(self.px - cx), int(self.py - cy)), 28, 2)
        elif self.shield > 0:
            pygame.draw.circle(s, (150, 220, 255), (int(self.px - cx), int(self.py - cy)), int(self.vehicle.radius + 10), 3)
        # aim reticle (where dynamite will land)
        if not self.vehicle and self.state == "PLAY":
            ax, ay = self.aim_point()
            spx, spy = self.px - cx, self.py - cy
            ex_, ey_ = ax - cx, ay - cy
            dist = math.hypot(ex_ - spx, ey_ - spy)
            n = int(dist // 26)
            for i in range(2, n):
                u = i / max(1, n)
                pygame.draw.circle(s, (255, 244, 210), (int(lerp(spx, ex_, u)), int(lerp(spy, ey_, u))), 2)
            pygame.draw.circle(s, (255, 244, 210), (int(ex_), int(ey_)), 14, 2)
            pygame.draw.line(s, (255, 244, 210), (ex_ - 8, ey_), (ex_ + 8, ey_), 2)
            pygame.draw.line(s, (255, 244, 210), (ex_, ey_ - 8), (ex_, ey_ + 8), 2)
        # dynamite
        for d in self.dyns:
            u = min(1.0, d["t"] / 0.45)
            lift = math.sin(u * math.pi) * 40 if u < 1 else 0
            x, y = d["x"] - cx, d["y"] - cy
            pygame.draw.ellipse(s, (120, 100, 70), (x - 10, y - 4, 20, 8))
            pygame.draw.rect(s, (200, 30, 30), (x - 8, y - lift - 10, 16, 20), border_radius=3)
            pygame.draw.line(s, (255, 230, 120), (x, y - lift - 10), (x + 5, y - lift - 18), 2)
            if int(d["fuse"] * 8) % 2 == 0:
                pygame.draw.circle(s, (255, 190, 60), (int(x + 5), int(y - lift - 19)), 4)
        # bolts
        for b in self.bolts:
            pygame.draw.circle(s, (80, 240, 150), (int(b["x"] - cx), int(b["y"] - cy)), 8)
            pygame.draw.circle(s, (220, 255, 230), (int(b["x"] - cx), int(b["y"] - cy)), 4)
        # particles
        for pt in self.parts:
            x, y = pt.x - cx, pt.y - cy
            if not (-60 < x < W + 60 and -60 < y < H + 60):
                continue
            u = pt.life / pt.max
            if pt.kind == "dust":
                r = int(pt.size)
                r = max(6, min(42, (r // 4) * 4 + 2))
                img = A.dust.get((r, min(4, int((1 - u) * 5))))
                if img:
                    s.blit(img, img.get_rect(center=(int(x), int(y))))
            elif pt.kind == "chip":
                pygame.draw.rect(s, pt.color, (x, y, pt.size, pt.size))
            elif pt.kind == "spark":
                pygame.draw.circle(s, pt.color, (int(x), int(y)), max(1, int(pt.size * u)))
            elif pt.kind == "ring":
                r = int(pt.size * (1 - u) + 10)
                pygame.draw.circle(s, pt.color, (int(x), int(y)), r, max(2, int(10 * u)))
            elif pt.kind == "flash":
                r = int(pt.size * (0.6 + 0.4 * (1 - u)))
                pygame.draw.circle(s, pt.color, (int(x), int(y)), r)
        # palms drawn over everything (tall)
        for (px, py, rot, sc) in self.palms:
            if vis(px, py, 90):
                img = A.palm if sc == 1.0 else pygame.transform.rotozoom(A.palm, rot, sc)
                s.blit(img, img.get_rect(center=(px - cx, py - cy)))
        for t in self.texts:
            img = outlined(A.f_small, t[0], t[4], BLACK, 2)
            img.set_alpha(int(255 * min(1.0, t[3] / 0.5)))
            s.blit(img, img.get_rect(center=(int(t[1] - cx), int(t[2] - cy))))
        # radar markers
        if self.radar_t > 0:
            for v in self.vehicles:
                self.draw_marker(s, v.x, v.y, GOLD, v.name)
            for it in self.items:
                if it["kind"] == "dyn":
                    self.draw_marker(s, it["x"], it["y"], (255, 150, 110), "TNT", small=True)
        # objective arrows
        for v in self.vehicles:
            if v.found and not v.driver and not self.vehicle and False:
                pass

    def draw_marker(self, s, x, y, color, label, small=False):
        sx, sy = x - self.cam[0], y - self.cam[1]
        pulse = 0.5 + 0.5 * math.sin(self.time * 8)
        if 20 < sx < W - 20 and 20 < sy < H - 40:
            pygame.draw.circle(s, color, (int(sx), int(sy)), int((24 if small else 40) + pulse * 10), 3)
            if not small:
                t = self.art.text(self.art.f_tiny, label, color)
                s.blit(t, t.get_rect(center=(int(sx), int(sy - 58))))
        else:
            ex, ey = clamp(sx, 40, W - 40), clamp(sy, 90, H - 60)
            ang = math.atan2(sy - H / 2, sx - W / 2)
            if not small:
                pts = [(ex + math.cos(ang) * 22, ey + math.sin(ang) * 22),
                       (ex + math.cos(ang + 2.5) * 16, ey + math.sin(ang + 2.5) * 16),
                       (ex + math.cos(ang - 2.5) * 16, ey + math.sin(ang - 2.5) * 16)]
                pygame.draw.polygon(s, color, pts)
                t = self.art.text(self.art.f_tiny, label, color)
                s.blit(t, t.get_rect(center=(int(ex - math.cos(ang) * 30), int(ey - math.sin(ang) * 30))))

    # ----- HUD -----
    def draw_bar(self, s, x, y, w, h, frac, color, label):
        pygame.draw.rect(s, (14, 10, 8), (x, y, w, h), border_radius=6)
        if frac > 0:
            pygame.draw.rect(s, color, (x + 2, y + 2, int((w - 4) * clamp(frac, 0, 1)), h - 4), border_radius=5)
        pygame.draw.rect(s, GOLD_D, (x, y, w, h), 2, border_radius=6)
        t = self.art.text(self.art.f_tiny, label, WHITE)
        s.blit(t, t.get_rect(midleft=(x + 8, y + h // 2)))

    def draw_hud(self, s):
        A = self.art
        n = len(self.pyramids)
        panel = pygame.Surface((300, 196), pygame.SRCALPHA)
        panel.fill((20, 12, 6, 170))
        s.blit(panel, (10, 10))
        pygame.draw.rect(s, GOLD_D, (10, 10, 300, 196), 2, border_radius=4)
        self.draw_bar(s, 22, 20, 276, 20, self.hp / 100.0, (210, 50, 60), f"HEART  {int(self.hp)}")
        y = 48
        if self.vehicle:
            v = self.vehicle
            self.draw_bar(s, 22, y, 276, 20, v.fuel / 100.0, (240, 170, 40), f"FUEL  {int(v.fuel)}")
            self.draw_bar(s, 22, y + 28, 276, 20, v.hp / v.max_hp, (90, 190, 90), f"{v.name}  {int(v.hp)}")
            y += 56
            if v.kind == "dozer":
                if v.armed:
                    t = A.text(A.f_small, "BLADE READY - STRIKE!", GREEN)
                else:
                    t = A.text(A.f_small, "BACK UP, THEN STRIKE AGAIN", (255, 150, 90) if int(self.time * 4) % 2 else (255, 210, 120))
                s.blit(t, (24, y + 2))
                y += 24
        else:
            t = A.text(A.f_small, f"JERRY CANS: {self.fuel_cans}", (255, 210, 120))
            s.blit(t, (24, y + 2))
            y += 28
        t = A.text(A.f_small, f"DYNAMITE: {self.dyn_count}   [SPACE]", (255, 160, 120))
        s.blit(t, (24, y + 2))
        y += 26
        extra = []
        if self.shield:
            extra.append(f"AMULET x{self.shield}")
        if self.buff_speed > 0:
            extra.append(f"SPEED OF RA {int(self.buff_speed)}s")
        if extra:
            t = A.text(A.f_tiny, "  ".join(extra), (160, 220, 255))
            s.blit(t, (24, y + 2))
        rc = "EYE OF HORUS [R]: READY" if self.radar_cd <= 0 else f"EYE OF HORUS [R]: {int(self.radar_cd)}s"
        t = A.text(A.f_tiny, rc, (120, 220, 255) if self.radar_cd <= 0 else (140, 140, 150))
        s.blit(t, (24, 186))
        # time + pyramids
        mm, ss = divmod(int(self.time_left), 60)
        low = self.time_left < 45
        t = outlined(A.f_big, f"{mm}:{ss:02d}", RED if low and int(self.time * 3) % 2 else GOLD, BLACK, 2)
        s.blit(t, t.get_rect(center=(W // 2, 34)))
        sunset = A.text(A.f_tiny, "SUNSET", (220, 180, 120))
        s.blit(sunset, sunset.get_rect(center=(W // 2, 62)))
        x0 = W // 2 - n * 86 // 2 + 25
        for i, p in enumerate(self.pyramids):
            x = x0 + i * 86
            pygame.draw.polygon(s, (90, 90, 90) if not p.alive else (240, 200, 130), [(x, 100), (x + 36, 100), (x + 18, 74)])
            pygame.draw.polygon(s, BLACK, [(x, 100), (x + 36, 100), (x + 18, 74)], 2)
            pygame.draw.rect(s, (14, 10, 8), (x - 4, 104, 44, 8))
            pygame.draw.rect(s, GREEN if p.alive else (90, 90, 90), (x - 3, 105, int(42 * p.frac), 6))
            if not p.alive:
                t = A.text(A.f_tiny, "X", RED)
                s.blit(t, t.get_rect(center=(x + 18, 90)))
        obj = A.text(A.f_small, f"PYRAMIDS DESTROYED: {self.destroyed} / {n}", WHITE)
        s.blit(obj, obj.get_rect(center=(W // 2, 130)))
        tools = []
        for kind, name in (("dozer", "BULLDOZER"), ("wrecker", "WRECKING TRUCK")):
            v = next((q for q in self.vehicles if q.kind == kind), None)
            tools.append(f"{name}: " + ("DRIVING" if v and v.driver else "FOUND" if v and v.found else "NOT FOUND"
                                        if v else "LOST"))
        t = A.text(A.f_tiny, "   |   ".join(tools), (230, 215, 170))
        s.blit(t, t.get_rect(center=(W // 2, 152)))
        # minimap
        mw, mh = 210, 158
        mx, my = W - mw - 10, 10
        mini = pygame.Surface((mw, mh), pygame.SRCALPHA)
        mini.fill((200, 170, 110, 190))
        sc_x, sc_y = mw / WORLD_W, mh / WORLD_H
        for (a0, b0, a1, b1) in self.walls:
            pygame.draw.rect(mini, (120, 96, 64), (a0 * sc_x, b0 * sc_y, max(2, (a1 - a0) * sc_x), max(2, (b1 - b0) * sc_y)))
        pygame.draw.circle(mini, (60, 130, 170), (int(self.oasis[0] * sc_x), int(self.oasis[1] * sc_y)), 8)
        for p in self.pyramids:
            c = (150, 40, 40) if p.alive else (110, 110, 110)
            x, y = p.x * sc_x, p.y * sc_y
            pygame.draw.polygon(mini, c, [(x - 8, y + 6), (x + 8, y + 6), (x, y - 8)])
        for v in self.vehicles:
            if v.found or self.radar_t > 0:
                pygame.draw.circle(mini, GOLD, (int(v.x * sc_x), int(v.y * sc_y)), 4)
                pygame.draw.circle(mini, BLACK, (int(v.x * sc_x), int(v.y * sc_y)), 4, 1)
        for e in self.enemies:
            if math.hypot(e.x - self.px, e.y - self.py) < 900:
                pygame.draw.circle(mini, (200, 30, 30), (int(e.x * sc_x), int(e.y * sc_y)), 2)
        pygame.draw.circle(mini, (30, 90, 230), (int(self.px * sc_x), int(self.py * sc_y)), 4)
        s.blit(mini, (mx, my))
        pygame.draw.rect(s, GOLD_D, (mx, my, mw, mh), 3)
        for i, (txt, col) in enumerate(((f"LEVEL {self.level}  -  {LAYOUTS[self.layout]}", GOLD),
                                        (f"AIM: {self.aim_mode}  [TAB]", (230, 220, 190)),
                                        (("CONTROLLER: " + self.pad.name[:18]) if self.pad.active else "CONTROLLER: none", (130, 230, 150) if self.pad.active else (150, 150, 150)),
                                        (f"SCORE {self.score:,}", WHITE))):
            img = A.text(A.f_tiny, txt, col)
            s.blit(img, img.get_rect(midright=(W - 12, 180 + i * 18)))
        # level intro
        if self.level_time < 4.0:
            a = int(255 * min(1.0, (4.0 - self.level_time)))
            t1 = outlined(A.f_huge, f"LEVEL {self.level}", GOLD, (90, 40, 0), 4)
            t1.set_alpha(a)
            s.blit(t1, t1.get_rect(center=(W // 2, 290)))
            t2 = outlined(A.f_big, f"{LAYOUTS[self.layout]}  -  {n} PYRAMID{'S' if n > 1 else ''}", WHITE, BLACK, 2)
            t2.set_alpha(a)
            s.blit(t2, t2.get_rect(center=(W // 2, 360)))
        # message
        if self.msg[1] > 0 and self.msg[0]:
            img = outlined(A.f_med, self.msg[0], WHITE, BLACK, 2)
            img.set_alpha(int(255 * min(1.0, self.msg[1] / 0.6)))
            s.blit(img, img.get_rect(center=(W // 2, H - 90)))
        self.draw_ticker(s)
    def draw_ticker(self, s, y=H - 30, h=30):
        A = self.art
        pygame.draw.rect(s, (24, 14, 8), (0, y, W, h))
        pygame.draw.line(s, GOLD, (0, y), (W, y), 2)
        img = A.text(A.f_small, TAGLINE + "   ~~~   ", GOLD)
        w = img.get_width()
        off = -(self.time * 70) % w
        x = -off
        while x < W:
            s.blit(img, (x, y + (h - img.get_height()) // 2))
            x += w

    def draw_link(self, s, cx, y, font=None):
        A = self.art
        font = font or A.f_med
        hover = self.link_rect.collidepoint(pygame.mouse.get_pos())
        t = font.render(LINK_URL, True, (255, 255, 255) if hover else (130, 210, 255))
        r = t.get_rect(center=(cx, y))
        s.blit(t, r)
        pygame.draw.line(s, (130, 210, 255), (r.left, r.bottom), (r.right, r.bottom), 2)
        self.link_rect = r.inflate(16, 10)

    # ----- decorative Egyptian border -----
    def draw_hiero_band(self, s, y, h=40, scroll=0.0):
        pygame.draw.rect(s, (20, 40, 80), (0, y, W, h))
        pygame.draw.line(s, GOLD, (0, y), (W, y), 3)
        pygame.draw.line(s, GOLD, (0, y + h), (W, y + h), 3)
        step = 70
        off = (scroll * 20) % step
        for i in range(-1, W // step + 2):
            x = i * step - off + step // 2
            m = i % 5
            cy = y + h // 2
            if m == 0:                                      # ankh
                pygame.draw.circle(s, GOLD, (int(x), cy - 8), 7, 3)
                pygame.draw.line(s, GOLD, (x, cy - 1), (x, cy + 15), 3)
                pygame.draw.line(s, GOLD, (x - 8, cy + 5), (x + 8, cy + 5), 3)
            elif m == 1:                                    # eye of horus
                pygame.draw.ellipse(s, GOLD, (x - 15, cy - 7, 30, 14), 3)
                pygame.draw.circle(s, GOLD, (int(x), cy), 4)
                pygame.draw.line(s, GOLD, (x - 4, cy + 7), (x - 8, cy + 15), 3)
            elif m == 2:                                    # water
                for k in range(3):
                    pts = [(x - 16 + j * 4, cy - 8 + k * 8 + (3 if j % 2 else -3)) for j in range(9)]
                    pygame.draw.lines(s, GOLD, False, pts, 2)
            elif m == 3:                                    # scarab
                pygame.draw.ellipse(s, GOLD, (x - 11, cy - 7, 22, 16))
                pygame.draw.circle(s, GOLD, (int(x), cy - 10), 5)
                pygame.draw.line(s, (20, 40, 80), (x, cy - 7), (x, cy + 9), 2)
                for dy in (-4, 2, 8):
                    pygame.draw.line(s, GOLD, (x - 11, cy + dy), (x - 17, cy + dy + 3), 2)
                    pygame.draw.line(s, GOLD, (x + 11, cy + dy), (x + 17, cy + dy + 3), 2)
            else:                                           # feather of Ma'at
                pygame.draw.ellipse(s, GOLD, (x - 5, cy - 15, 10, 26))
                pygame.draw.line(s, (20, 40, 80), (x, cy - 13), (x, cy + 9), 2)
                pygame.draw.line(s, GOLD, (x, cy + 9), (x, cy + 17), 3)

    def draw_title(self, s):
        A = self.art
        t = self.time
        s.blit(vgrad(W, H, (22, 14, 62), (246, 150, 70)), (0, 0))
        rng = random.Random(8)
        for _ in range(60):
            x, y = rng.randrange(W), rng.randrange(0, 340)
            if (int(t * 2) + x) % 5:
                pygame.draw.circle(s, (255, 250, 230), (x, y), 1)
        sun_y = 470 + math.sin(t * 0.4) * 6
        pygame.draw.circle(s, (255, 190, 90), (W // 2, int(sun_y)), 150)
        pygame.draw.circle(s, (255, 230, 150), (W // 2, int(sun_y)), 110)
        for (x, y, sz) in ((250, 590, 230), (560, 610, 300), (1000, 600, 260), (1170, 620, 160)):
            pygame.draw.polygon(s, (74, 40, 50), [(x - sz, y), (x + sz, y), (x, y - sz * 0.95)])
            pygame.draw.polygon(s, (110, 58, 56), [(x, y), (x + sz, y), (x, y - sz * 0.95)])
        pygame.draw.polygon(s, (60, 32, 40), [(0, H), (0, 640)] + [(x, 640 + math.sin(x / 140.0) * 22) for x in range(0, W + 40, 40)] + [(W, H)])
        for d in self.title_dust:
            pygame.draw.circle(s, (255, 214, 150), (int(d[0]), int(d[1])), 2)
        self.draw_hiero_band(s, 0, 44, t)
        self.draw_hiero_band(s, H - 74, 44, -t)
        title = outlined(A.f_huge, "BOOK OF THE DEAD", GOLD, (90, 40, 0), 4)
        s.blit(title, title.get_rect(center=(W // 2, 118)))
        sub = outlined(A.f_title, "PYRAMID DEMOLITION", (255, 244, 214), (110, 30, 20), 4)
        s.blit(sub, sub.get_rect(center=(W // 2, 196)))
        line = A.text(A.f_med, "Find a bulldozer.  Bring down the pyramids.  Babylon Is Fallen.", (255, 236, 190))
        s.blit(line, line.get_rect(center=(W // 2, 250)))
        pulse = 0.5 + 0.5 * math.sin(t * 4)
        bt = outlined(A.f_big, "CLICK / SPACE / START", WHITE, BLACK, 2)
        r = pygame.Rect(0, 0, bt.get_width() + 80, 62)   # wider so the text fits comfortably
        r.center = (W // 2, 312)
        pygame.draw.rect(s, (0, 0, 0), r.move(0, 5), border_radius=14)
        pygame.draw.rect(s, (int(150 + 60 * pulse), 40, 40), r, border_radius=14)
        pygame.draw.rect(s, GOLD, r, 4, border_radius=14)
        s.blit(bt, bt.get_rect(center=r.center))
        hp = pygame.Surface((1140, 206), pygame.SRCALPHA)
        hp.fill((16, 10, 8, 195))
        s.blit(hp, (W // 2 - 570, 356))
        pygame.draw.rect(s, GOLD_D, (W // 2 - 570, 356, 1140, 206), 2)
        rows = [("WASD / ARROWS  walk (in a machine: W/S forward-reverse, A/D steer)      SHIFT  sprint / boost      E  get in / out      R  EYE OF HORUS radar", (240, 230, 205)),
                ("SPACE  throw dynamite / swing the wrecking ball - the way you FACE      F / LEFT CLICK  swing khopesh      P  pause      M / N  music / sound", (240, 230, 205)),
                ("BULLDOZER:  STRIKE the pyramid, BACK UP, strike again - holding against it does nothing!", (255, 220, 140)),
                ("TAB = MOUSE AIM mode (mouse aims and steers, right click = dynamite, hold right click to drive forward)", (240, 230, 205)),
                ("GAME CONTROLLER:  left stick move / drive      right stick aim      A fire      X melee      Y get in-out      B radar      RB boost      Start pause", (160, 220, 255)),
                (("CONTROLLER DETECTED: " + self.pad.name) if self.pad.active else "No controller detected - plug in a USB / Xbox-style pad any time and it will be picked up.",
                 (130, 235, 150) if self.pad.active else (190, 190, 190)),
                (f"Destroy every pyramid before sunset.  Every level is harder and laid out differently.   BEST: {self.high:,}  (LEVEL {self.best_level})", (255, 220, 140))]
        for i, (txt, col) in enumerate(rows):
            img = A.text(A.f_tiny, txt, col)
            s.blit(img, img.get_rect(center=(W // 2, 376 + i * 27)))
        head = outlined(A.f_med, "Legal Name Fraud Truth Channel", GOLD, (60, 30, 0), 2)
        s.blit(head, head.get_rect(center=(W // 2, 584)))
        self.draw_link(s, W // 2, 610)
        sub2 = A.text(A.f_small, "Read the BCCRSS ~ Babylon Is Fallen ~ BCCRSS ~ Judge Bows", (255, 236, 190))
        s.blit(sub2, sub2.get_rect(center=(W // 2, 636)))
        self.draw_ticker(s)
    def draw_scales(self, s, cx, cy, tilt, win):
        """Weighing of the Heart. tilt > 0: heart side (left) is lower."""
        A = self.art
        pygame.draw.polygon(s, GOLD_D, [(cx - 50, cy + 170), (cx + 50, cy + 170), (cx + 14, cy), (cx - 14, cy)])
        pygame.draw.rect(s, GOLD, (cx - 70, cy + 164, 140, 14), border_radius=4)
        ang = math.radians(tilt * 14)
        L = 190
        lx, ly = cx - math.cos(ang) * L, cy + math.sin(ang) * L
        rx, ry = cx + math.cos(ang) * L, cy - math.sin(ang) * L
        pygame.draw.line(s, GOLD, (lx, ly), (rx, ry), 10)
        pygame.draw.circle(s, GOLD, (cx, cy), 14)
        for (x, y) in ((lx, ly), (rx, ry)):
            pygame.draw.line(s, GOLD_D, (x, y), (x - 50, y + 90), 3)
            pygame.draw.line(s, GOLD_D, (x, y), (x + 50, y + 90), 3)
            pygame.draw.ellipse(s, GOLD, (x - 62, y + 84, 124, 26))
        # heart (left) and feather (right)
        hx, hy = lx, ly + 76
        pygame.draw.circle(s, (190, 30, 50), (int(hx - 10), int(hy - 8)), 15)
        pygame.draw.circle(s, (190, 30, 50), (int(hx + 10), int(hy - 8)), 15)
        pygame.draw.polygon(s, (190, 30, 50), [(hx - 24, hy - 2), (hx + 24, hy - 2), (hx, hy + 28)])
        fx, fy = rx, ry + 70
        pygame.draw.ellipse(s, (245, 245, 235), (fx - 10, fy - 36, 20, 62))
        pygame.draw.line(s, (170, 170, 160), (fx, fy - 32), (fx, fy + 30), 2)

    def draw_end(self, s):
        A = self.art
        win = self.state == "LEVELDONE"
        self.end_t += 1 / FPS
        s.blit(vgrad(W, H, (16, 12, 40), (90, 40, 30) if not win else (220, 150, 70)), (0, 0))
        self.draw_hiero_band(s, 0, 44, self.time)
        self.draw_hiero_band(s, H - 74, 44, -self.time)
        tilt = (-1 if win else 1) * min(1.0, self.end_t / 1.5)
        self.draw_scales(s, 300, 250, tilt, win)
        n = len(self.pyramids)
        if win:
            h1 = outlined(A.f_huge, "JUDGE BOWS", GOLD, (90, 40, 0), 4)
            h2 = outlined(A.f_title, "BABYLON IS FALLEN", (255, 244, 214), (110, 30, 20), 4)
            sub = f"LEVEL {self.level} COMPLETE.  The sands shift... new pyramids rise, and the guardians are stronger."
            stats = [(f"LEVEL {self.level} COMPLETE", GOLD), (f"PYRAMIDS DESTROYED   {self.destroyed} / {n}", (240, 230, 205)),
                     (f"GUARDIANS DEFEATED    {self.kills}", (240, 230, 205)),
                     (f"TIME BONUS   +{self.level_bonus:,}", (240, 230, 205)),
                     (f"SCORE   {self.score:,}", GOLD), (f"BEST   {self.high:,}  (LEVEL {self.best_level})", GOLD)]
            prompt = f"PRESS ENTER / CLICK / PAD A  FOR LEVEL {self.level + 1}"
        else:
            h1 = outlined(A.f_huge, "THE HEART IS HEAVY", (255, 120, 110), (60, 0, 0), 4)
            h2 = outlined(A.f_title, "READ THE BCCRSS", (255, 244, 214), (110, 30, 20), 4)
            sub = ("The sun has set on your demolition." if self.time_left <= 0
                   else "The guardians of the Book of the Dead have claimed you.")
            stats = [(f"YOU REACHED LEVEL {self.level}", GOLD), (f"PYRAMIDS THIS LEVEL   {self.destroyed} / {n}", (240, 230, 205)),
                     (f"GUARDIANS DEFEATED    {self.kills}", (240, 230, 205)),
                     (f"MACHINES LOST   {self.vehicles_lost}", (240, 230, 205)),
                     (f"SCORE   {self.score:,}", GOLD), (f"BEST   {self.high:,}  (LEVEL {self.best_level})", GOLD)]
            prompt = "PRESS ENTER / CLICK / PAD A  TO PLAY AGAIN      ESC = QUIT"
        s.blit(h1, h1.get_rect(center=(W // 2 + 170, 110)))
        s.blit(h2, h2.get_rect(center=(W // 2 + 170, 190)))
        t = A.text(A.f_small, sub, (255, 236, 190))
        s.blit(t, t.get_rect(center=(W // 2 + 170, 240)))
        for i, (txt, col) in enumerate(stats):
            img = A.text(A.f_med, txt, col)
            s.blit(img, img.get_rect(midleft=(W // 2 - 20, 300 + i * 40)))
        head = outlined(A.f_med, "Legal Name Fraud Truth Channel", GOLD, (60, 30, 0), 2)
        s.blit(head, head.get_rect(center=(W // 2, 566)))
        self.draw_link(s, W // 2, 598)
        sub2 = A.text(A.f_small, "Read the BCCRSS ~ Babylon Is Fallen ~ BCCRSS ~ Judge Bows", (255, 236, 190))
        s.blit(sub2, sub2.get_rect(center=(W // 2, 628)))
        if self.end_t > 1.0 and int(self.time * 2) % 2 == 0:
            blink = A.text(A.f_med, prompt, WHITE)
            s.blit(blink, blink.get_rect(center=(W // 2, 524)))
        self.draw_ticker(s)
    def draw(self):
        s = self.canvas
        if self.state == "TITLE":
            self.draw_title(s)
        elif self.state in ("LEVELDONE", "LOSE"):
            self.draw_end(s)
        else:
            self.draw_world(s)
            self.draw_hud(s)
            if self.state == "PAUSE":
                dim = pygame.Surface((W, H), pygame.SRCALPHA)
                dim.fill((0, 0, 0, 170))
                s.blit(dim, (0, 0))
                t = outlined(self.art.f_huge, "PAUSED", GOLD, (90, 40, 0), 4)
                s.blit(t, t.get_rect(center=(W // 2, 250)))
                for i, txt in enumerate(["P / ESC / SPACE  resume", "Q  quit"]):
                    img = self.art.text(self.art.f_med, txt, WHITE)
                    s.blit(img, img.get_rect(center=(W // 2, 340 + i * 40)))
                head = self.art.text(self.art.f_med, "Legal Name Fraud Truth Channel", GOLD)
                s.blit(head, head.get_rect(center=(W // 2, 470)))
                self.draw_link(s, W // 2, 506)
        self.screen.blit(s, (0, 0))
        pygame.display.flip()

    # ------------------------------------------------------------------- run
    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            for e in pygame.event.get():
                self.handle(e)
            self.process_pad(dt)
            self.sfx.poll()
            self.time += dt if self.state != "PLAY" else 0.0
            if self.state == "TITLE":
                for d in self.title_dust:
                    d[1] -= d[2] * dt
                    d[0] += 12 * dt
                    if d[1] < 0 or d[0] > W:
                        d[0], d[1] = random.uniform(0, W), H
            if self.state == "PLAY":
                self.update_play(dt)
            self.draw()


def main():
    pygame.mixer.pre_init(RATE, -16, 1, 512)
    pygame.init()
    pygame.display.set_caption(TITLE)
    try:
        screen = pygame.display.set_mode((W, H), pygame.SCALED | pygame.RESIZABLE)
    except pygame.error:
        screen = pygame.display.set_mode((W, H))
    Game(screen).run()


if __name__ == "__main__":
    main()
