"""
Match Three - a Bejeweled-style gem game with power gems.

Gem artwork is used exactly as drawn - whatever is in gems/ is the gem, with
its own silhouette and transparency. Name them 1.png .. 6.png (any count from
3 upwards works; they are discovered at startup).

Modes:
    ENDLESS  matches fill the level bar; fill it and the next board rains in
             and the target goes up. No clock, no losing.
    TIMED    90 seconds to score as much as possible. Some gems carry a +3s
             badge - matching those puts time back on the clock.
    Switch in the menu, or press T.

Specials:
    match 4  -> FLAME GEM. When cleared, blows up the 8 cells around it.
                Chains: a blast that catches another flame sets that one off too.
    match 5  -> POWER GEM (gems/7.png). Colorless, never matches normally. Swap it with any
                gem to vaporise every gem of that color. Two hypercubes swapped
                together clear the whole board.

Controls:
    click a gem, then click an adjacent gem   -> swap
    or click and drag onto a neighbor         -> swap
    H   -> hint (same as the HINT button)
    N   -> jump to a random song
    Esc -> open/close the menu (volumes, quit)
    R   -> restart
    T   -> switch between endless and timed
    M   -> mute music
    - / =  -> music volume down / up
    F1 (or \\) -> secret reshuffle, keeps your score
    close window -> quit

Audio (all optional - the game runs fine silent):
    soundeffects/   SelectGem, NoMatch, Match3, Match4-5, Cascade2..Cascade6,
                    GemFalling, Explode, LevelUp, Go, MenuClick   (.ogg)
    music/               .ogg or .mp3, shuffled, for endless mode
    music/Timed Music/   played instead while timed mode is running

Backgrounds (optional):
    backgrounds/    1.png, 2.png ... one is shown per level, cycling round.
                    Scaled to cover the window and dimmed so gems stay readable.

Effects (optional):
    effects/        match, explode, hyper, levelup, go - as a folder of
                    frames, a sprite strip (name@8.png), or a .gif (Pillow).
                    fire.png   drawn behind a flame gem, drifting
                    smoke.png  puffs out when a flame gem detonates

Run:  python3 match3.py
"""

import math
import os
import random
import sys

import pygame

try:
    import numpy as np           # optional: only used to pitch-shift cascades
except ImportError:
    np = None

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

COLS, ROWS = 9, 9
TILE = 74
MARGIN = 24
GEM_PAD = 3                 # breathing room inside each tile

# 4:3 window, with the score panel running down the left-hand side.
#   24 margin | 220 panel | 26 gap | 666 board | 24 margin  = 960
#   27 margin | 666 board | 27 margin                       = 720
WIDTH, HEIGHT = 960, 720
PANEL_W = 220
PANEL_X = MARGIN
PANEL_Y = 27
PANEL_H = HEIGHT - PANEL_Y * 2
BOARD_X = PANEL_X + PANEL_W + 26
BOARD_Y = PANEL_Y
BOARD_W = COLS * TILE
BOARD_H = ROWS * TILE

HINT_SECONDS = 4.0          # how long a hint stays lit

FPS = 60

# progression
LEVEL_BASE_TARGET = 1200   # points needed to clear level 1
LEVEL_GROWTH = 1.35        # each level needs this much more than the last

# timed mode
ENDLESS, TIMED = "endless", "timed"
TIMED_SECONDS = 90.0        # 1:30 on the clock
TIMED_MAX = 120.0           # you can bank up to this much, never more
BONUS_SECONDS = 3.0         # what one +3 gem is worth
# Tuned by simulation: a bot playing flawlessly earns back roughly half the
# clock it burns, so good play stretches a run without making it endless.
BONUS_CHANCE = 0.028        # odds any refilled gem carries a bonus
BONUS_MIN = 2               # keep at least this many on the board
LOW_TIME = 12.0             # clock turns red and pulses below this

# animation durations, in seconds
SWAP_TIME = 0.14
CLEAR_TIME = 0.26
FALL_TIME = 0.32
POP_TIME = 0.35          # the little "pop" when a special is born
INTRO_TIME = 1.20        # whole board raining in at the start of a level
INTRO_FALL = 0.55        # how long any single gem takes to land
INTRO_STAGGER = 0.06     # each column starts this much later than the last
INTRO_SOUND_EVERY = 2    # play GemFalling on every Nth column landing
LEVELUP_MIN = 0.9        # floor for the level-up pause, even with no sound
LEVELUP_MAX = 3.0        # ceiling, so a long track cannot stall the game
GO_TIME = 0.85           # how long the GO! flash sits on screen

# scoring
POINTS_PER_GEM = 10
FLAME_BONUS = 60
HYPER_BONUS = 200

def clamp01(t):
    return max(0.0, min(1.0, t))


# palette
# Grey chrome, drawn semi-transparently so a background photo reads through.
# Alpha is part of the colour here, so these are drawn onto SRCALPHA surfaces
# rather than straight to the display - pygame.draw ignores alpha otherwise.
BG = (22, 23, 26)                      # only seen if backgrounds/ is empty

# How much of the background photo shows through the grey chrome.
#   0.0 = solid grey panels (background only visible around them)
#   1.0 = barely-there glass
# Everything below scales off this, so it is the one number worth tuning.
GLASS = 0.55

BG_DIM = 78                            # black scrim over the photo, 0-255


def _glass(rgb, base_alpha):
    """Fade an alpha toward transparent as GLASS rises."""
    return rgb + (int(base_alpha * (1.0 - 0.62 * clamp01(GLASS))),)


PANEL_FILL = _glass((58, 61, 66), 232)
PANEL_EDGE = (168, 173, 182, 130)
BOARD_FILL = _glass((40, 43, 48), 214)
CELL_HI = (255, 255, 255, 15)          # the lighter checker squares
BTN = _glass((78, 82, 89), 236)
BTN_HOVER = _glass((110, 115, 124, ), 246)
BTN_DOWN = _glass((58, 61, 67), 246)
TEXT = (238, 239, 243)
DIM = (156, 160, 168)
GOLD = (224, 198, 132)                 # level bar accent
HINT_COLOR = (128, 226, 210)


def app_dir():
    """The folder the *user* sees.

    Running as a script that is the folder holding this file. Frozen, it is
    the folder holding the .exe - or the folder holding the .app, since macOS
    buries the real executable in Contents/MacOS.
    """
    if getattr(sys, "frozen", False):
        here = os.path.dirname(os.path.abspath(sys.executable))
        if here.replace(os.sep, "/").endswith(".app/Contents/MacOS"):
            return os.path.dirname(os.path.dirname(os.path.dirname(here)))
        return here
    return os.path.dirname(os.path.abspath(__file__))


def bundle_dir():
    """Where PyInstaller unpacked the baked-in copies."""
    return getattr(sys, "_MEIPASS", app_dir())


def asset_folder(name):
    """Prefer a folder sitting next to the app, fall back to the baked-in copy,
    so artwork can be swapped without rebuilding."""
    external = os.path.join(app_dir(), name)
    if os.path.isdir(external):
        return external
    return os.path.join(bundle_dir(), name)


BASE_DIR = app_dir()
ASSET_DIR = asset_folder("gems")
SFX_DIR = asset_folder("soundeffects")
MUSIC_DIR = asset_folder("music")
EFFECT_DIR = asset_folder("effects")
BACKGROUND_DIR = asset_folder("backgrounds")

AUDIO_EXTS = (".ogg", ".wav", ".mp3", ".flac")

# Music is shuffled. The order is reshuffled each time the playlist wraps,
# and never repeats the track you just heard back-to-back.
# music/            the endless-mode playlist, shuffled
# music/Timed Music/ played instead while timed mode is running
TIMED_MUSIC_SUBDIR = "Timed Music"

MUSIC_VOLUME = 0.35        # starting music level, 0.0 - 1.0
SFX_START_VOLUME = 0.8     # starting sound-effect level, 0.0 - 1.0
VOLUME_STEP = 0.05         # how much the - and = keys move the slider
VOL_WIDTH = 150
VOL_HEIGHT = 6
CASCADE_SEMITONES = 2      # only used to fake a missing CascadeN.ogg

# Game event -> the filenames it will accept, best first.
# Matching ignores case, spaces and punctuation, so "Match4/5.ogg",
# "Match4:5.ogg" and "match45.ogg" all resolve to the same sound. Add your own
# alternative names to any of these tuples; nothing else needs to change.
SFX_ALIASES = {
    "select":  ("SelectGem", "Select", "Swap"),
    "nomatch": ("NoMatch", "Invalid", "BadSwap"),
    "match3":  ("Match3", "Match"),
    "match45": ("Match4/5", "Match45", "Match4", "Match5", "PowerGem"),
    "falling": ("GemFalling", "Falling", "Fall", "Drop"),
    "explode": ("Explode", "Explosion", "Flame", "Boom"),
    "hyper":   ("Hypercube", "Hyper", "Supernova", "Explode"),
    "shuffle": ("Shuffle", "Reshuffle", "NoMoves"),
    "levelup": ("LevelUp", "Level", "NextLevel"),
    "menuclick": ("MenuClick", "Click", "Button", "UIClick"),
    "go": ("Go", "Start", "Begin"),
    "gameover": ("GameOver", "Lose", "TimeUp"),
    # Excellent is the +3 pickup AND the 3-deep cascade. Note there is no "Go"
    # fallback here - that made every bonus gem shout GO.
    "bonus": ("Excellent", "Bonus", "TimeBonus"),
}
for _n in range(2, 7):
    SFX_ALIASES[f"cascade{_n}"] = (f"Cascade{_n}",)
SFX_ALIASES["cascade3"] = ("Cascade3", "Excellent")

MUSIC_END = pygame.USEREVENT + 1

# ---- animated effects ----------------------------------------------------
# Drop animations in effects/ under any of three names. Checked in this order:
#
#   effects/match/            a folder of frames: 000.png, 001.png, ...
#   effects/match@8.png       one strip, 8 frames side by side
#   effects/match.png         one strip, square frames (count inferred)
#   effects/match.gif         an animated gif (needs Pillow installed)
#
# Sprite strips and frame folders are strongly preferred. GIF caps out at 256
# colours with 1-bit alpha, so edges come out jagged and glows cannot fade -
# fine for chunky pixel art, poor for explosions.
EFFECT_FPS = 24
EFFECT_SCALE = 1.9         # effects are drawn bigger than one tile
MAX_EFFECTS = 36           # hard cap, so a big cascade cannot tank the frame rate
EFFECT_NAMES = ("match", "explode", "hyper", "levelup", "go", "smoke")

# Single stills that are decorated rather than played as animations.
FIRE_ASSET = "fire"        # sits behind a flame gem, drifting and breathing
SMOKE_ASSET = "smoke"      # puffs outward when a flame gem detonates
# Effects listed here are drawn additively, which is what makes fire and
# sparks read as light rather than as stickers.
# "go" is deliberately NOT additive - it is a readable overlay, not a light.
EFFECT_ADDITIVE = {"match", "explode", "hyper", "levelup"}

# Hidden reshuffle. F1 is the intended one, but macOS eats F1 unless you tick
# "Use F1, F2, etc. as standard function keys" (or hold Fn), so backslash is
# wired up as a fallback that always reaches the game.
SECRET_SHUFFLE_KEYS = (pygame.K_F1, pygame.K_BACKSLASH)

# gems/7.png is reserved for the hypercube, so it is kept out of the matchable
# set. Rename or clear this if you ever want a seventh colour instead.
HYPERCUBE_ASSET = "7"

# Fallback silhouettes, used only when a gem PNG is missing so the game still
# runs. With real artwork present, none of this is touched.
GEM_SHAPES = ("circle", "square", "triangle", "diamond",
              "hexagon", "star", "octagon", "pentagon")
GEM_COLORS = ((232,  72,  85), ( 86, 194, 112), ( 72, 142, 236), (246, 190,  62),
              (172, 112, 232), ( 56, 208, 212), (244, 124,  60), (150, 206,  80))

# Filled in by discover_gems() at startup; these are just a working default so
# the module can be imported and tested without any image files present.
GEM_DEFS = [(str(i + 1), GEM_SHAPES[i], GEM_COLORS[i]) for i in range(6)]
N_TYPES = len(GEM_DEFS)


def discover_gems():
    """Whatever images sit in gems/ become the gem set, in filename order.

    Numeric names sort numerically, so 10.png lands after 9.png instead of
    between 1.png and 2.png. Drop in another file and it joins the game.
    """
    global GEM_DEFS, N_TYPES
    names = []
    if os.path.isdir(ASSET_DIR):
        for filename in os.listdir(ASSET_DIR):
            stem, ext = os.path.splitext(filename)
            if ext.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                names.append(stem)
    names = [n for n in names if _norm(n) != _norm(HYPERCUBE_ASSET)]
    names.sort(key=lambda s: (0, int(s)) if s.isdigit() else (1, s.lower()))

    if len(names) < 3:
        print(f"Found {len(names)} gem image(s) in {ASSET_DIR}; need at least 3.")
        print("Using plain colored shapes instead.\n")
        names = [str(i + 1) for i in range(6)]

    GEM_DEFS = [(name,
                 GEM_SHAPES[i % len(GEM_SHAPES)],
                 GEM_COLORS[i % len(GEM_COLORS)]) for i, name in enumerate(names)]
    N_TYPES = len(GEM_DEFS)
    return names


SS = 4  # supersample factor when baking sprites (gives free antialiasing)

# power levels
NORMAL, FLAME, HYPER = 0, 1, 2
HYPER_KIND = -1          # a hypercube has no color


class Gem:
    """One cell's contents: a color (kind), an optional power, and in timed
    mode possibly a +3 second bonus."""

    __slots__ = ("kind", "power", "bonus")

    def __init__(self, kind, power=NORMAL, bonus=False):
        self.kind = kind
        self.power = power
        self.bonus = bonus

    def __repr__(self):
        tag = ", +3s" if self.bonus else ""
        return f"Gem({self.kind}, {self.power}{tag})"


# --------------------------------------------------------------------------
# asset loading / sprite baking
# --------------------------------------------------------------------------

def _norm(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def find_asset(name):
    """Locate gems/<name>.png, tolerating case and spacing differences."""
    if not os.path.isdir(ASSET_DIR):
        return None
    exact = os.path.join(ASSET_DIR, name + ".png")
    if os.path.isfile(exact):
        return exact
    target = _norm(name)
    for fn in os.listdir(ASSET_DIR):
        stem, ext = os.path.splitext(fn)
        if ext.lower() in (".png", ".jpg", ".jpeg", ".webp") and _norm(stem) == target:
            return os.path.join(ASSET_DIR, fn)
    return None


def shade(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def scale_points(pts, cx, cy, f):
    return [(cx + (x - cx) * f, cy + (y - cy) * f) for x, y in pts]


def shape_points(shape, size):
    """Polygon points for a shape inscribed in a size x size box."""
    c = size / 2
    r = size / 2
    if shape == "triangle":
        return [(c, r * 0.12), (size * 0.06, size * 0.94), (size * 0.94, size * 0.94)]
    if shape == "diamond":
        return [(c, 0), (size, c), (c, size), (0, size)]
    if shape == "hexagon":
        return [(c + r * math.cos(math.radians(60 * i - 90)),
                 c + r * math.sin(math.radians(60 * i - 90))) for i in range(6)]
    if shape == "star":
        pts = []
        for i in range(10):
            rad = r if i % 2 == 0 else r * 0.46
            a = math.radians(36 * i - 90)
            pts.append((c + rad * math.cos(a), c + rad * math.sin(a)))
        return pts
    if shape == "pentagon":
        return [(c + r * math.cos(math.radians(72 * i - 90)),
                 c + r * math.sin(math.radians(72 * i - 90))) for i in range(5)]
    if shape == "octagon":
        return [(c + r * math.cos(math.radians(45 * i - 22.5)),
                 c + r * math.sin(math.radians(45 * i - 22.5))) for i in range(8)]
    return None  # circle and square are drawn directly


def draw_shape(surf, shape, color, size, inset):
    """Draw one shape, inset by `inset` pixels from the surface edge."""
    c = size / 2
    if shape == "circle":
        pygame.draw.circle(surf, color, (int(c), int(c)), int(c - inset))
        return
    if shape == "square":
        r = pygame.Rect(inset, inset, size - inset * 2, size - inset * 2)
        pygame.draw.rect(surf, color, r, border_radius=int(size * 0.18))
        return
    pts = shape_points(shape, size)
    f = (size - inset * 2) / size
    pygame.draw.polygon(surf, color, scale_points(pts, c, c, f))


def fit_in(surface, box):
    """Scale to fit a box, keeping aspect ratio. Gems are rarely square."""
    w, h = surface.get_size()
    scale = min(box / w, box / h)
    return pygame.transform.smoothscale(
        surface, (max(1, int(w * scale)), max(1, int(h * scale))))


def centred(sprite):
    """Drop a sprite into the middle of a transparent TILE x TILE surface."""
    out = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    out.blit(sprite, ((TILE - sprite.get_width()) // 2,
                      (TILE - sprite.get_height()) // 2))
    return out


def silhouette(sprite, color, thickness=3):
    """Trace the outline of whatever shape the artwork actually is.

    pygame.mask reads the alpha channel, so this follows a real gem's edge
    rather than assuming a circle or a square.
    """
    out = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
    points = pygame.mask.from_surface(sprite).outline()
    if len(points) > 2:
        pygame.draw.lines(out, color, True, points, thickness)
    return out


def fallback_gem(shape, color):
    """Only used when a gem PNG is missing, so the game still runs."""
    big = TILE * SS
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    draw_shape(surf, shape, shade(color, 0.55), big, 4 * SS)
    draw_shape(surf, shape, color, big, 8 * SS)
    return pygame.transform.smoothscale(surf, (TILE, TILE))


def bake_gem(face, shape, color, hot=False):
    """Normal gem is the artwork, untouched.

    A flame gem is the SAME artwork - the fire is a separate sprite drawn
    behind it each frame so it can move. Without a fire.png we fall back to
    warming the gem itself, so the state is still readable.
    """
    art = fallback_gem(shape, color) if face is None \
        else fit_in(face, TILE - GEM_PAD * 2)

    if not hot:
        return centred(art)

    warmed = art.copy()
    tint = pygame.Surface(art.get_size(), pygame.SRCALPHA)
    tint.fill((48, 16, 0))
    warmed.blit(tint, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    return centred(warmed)


def load_still(name, size):
    """One decorative PNG from effects/, scaled to a square box."""
    if not os.path.isdir(EFFECT_DIR):
        return None
    for filename in sorted(os.listdir(EFFECT_DIR)):
        stem, ext = os.path.splitext(filename)
        if _norm(stem) == _norm(name) and ext.lower() in (".png", ".webp"):
            try:
                image = pygame.image.load(
                    os.path.join(EFFECT_DIR, filename)).convert_alpha()
            except pygame.error:
                return None
            return pygame.transform.smoothscale(image, (size, size))
    return None


def bake_hypercube():
    """The 5-match power gem.

    Uses gems/7.png if it exists; otherwise falls back to a generated
    prismatic octagon so the game still runs without the artwork.
    """
    path = find_asset(HYPERCUBE_ASSET)
    if path is not None:
        try:
            art = pygame.image.load(path).convert_alpha()
            return centred(fit_in(art, TILE - GEM_PAD * 2))
        except pygame.error:
            pass
    return bake_hypercube_fallback()


def bake_hypercube_fallback():
    """A colorless prismatic gem: rings of every gem color around a white core."""
    big = TILE * SS
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    draw_shape(surf, "octagon", (250, 250, 255), big, 3 * SS)
    inset = 6 * SS
    step = (big * 0.30) / N_TYPES
    for _, _, color in GEM_DEFS:
        draw_shape(surf, "octagon", color, big, int(inset))
        inset += step
    draw_shape(surf, "octagon", (255, 255, 255), big, int(inset))
    return pygame.transform.smoothscale(surf, (TILE, TILE))


def bake_glow(sprite, color, spread=1.34, layers=3):
    """A soft halo shaped like the sprite, for the power gem.

    Built from scaled copies of the artwork itself rather than a filled box -
    a filled rectangle is what made the old GO! look like a white slab.
    """
    size = int(TILE * spread)
    glow = pygame.Surface((size, size), pygame.SRCALPHA)
    for i in range(layers):
        factor = 1.0 + (spread - 1.0) * (i + 1) / layers
        blob = pygame.transform.smoothscale(
            sprite, (int(TILE * factor), int(TILE * factor)))
        blob = blob.copy()
        wash = pygame.Surface(blob.get_size(), pygame.SRCALPHA)
        wash.fill(color)
        blob.blit(wash, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        blob.set_alpha(70 - i * 18)
        glow.blit(blob, blob.get_rect(center=(size // 2, size // 2)),
                  special_flags=pygame.BLEND_RGBA_ADD)
    return glow


def build_sprites():
    """Returns (normal, flame, hypercube, missing_names)."""
    normal, flame, missing = [], [], []
    for name, shape, color in GEM_DEFS:
        face = None
        path = find_asset(name)
        if path is None:
            missing.append(name)
        else:
            try:
                face = pygame.image.load(path).convert_alpha()
            except pygame.error:
                missing.append(name)
        normal.append(bake_gem(face, shape, color, hot=False))
        flame.append(bake_gem(face, shape, color, hot=True))
    return normal, flame, bake_hypercube(), missing


# --------------------------------------------------------------------------
# board logic (pure data - no pygame in here, so it can be tested alone)
# --------------------------------------------------------------------------

def in_bounds(r, c):
    return 0 <= r < ROWS and 0 <= c < COLS


def matchable(cell):
    """Hypercubes are colorless and never take part in normal matching."""
    return cell is not None and cell.power != HYPER


def new_grid(bonuses=False):
    """Random board with no pre-existing matches, guaranteed to have a move."""
    while True:
        g = [[None] * COLS for _ in range(ROWS)]
        for r in range(ROWS):
            for c in range(COLS):
                banned = set()
                if c >= 2 and g[r][c - 1].kind == g[r][c - 2].kind:
                    banned.add(g[r][c - 1].kind)
                if r >= 2 and g[r - 1][c].kind == g[r - 2][c].kind:
                    banned.add(g[r - 1][c].kind)
                choices = [t for t in range(N_TYPES) if t not in banned]
                g[r][c] = Gem(random.choice(choices),
                              bonus=bonuses and random.random() < BONUS_CHANCE)
        if not has_move(g):
            continue
        if bonuses:
            cells = [(r, c) for r in range(ROWS) for c in range(COLS)]
            random.shuffle(cells)
            while count_bonus(g) < BONUS_MIN and cells:
                r, c = cells.pop()
                g[r][c].bonus = True
        return g


def find_runs(g):
    """Every straight run of 3 or more same-colored gems, as lists of cells."""
    runs = []
    for r in range(ROWS):
        c = 0
        while c < COLS:
            if not matchable(g[r][c]):
                c += 1
                continue
            k = g[r][c].kind
            end = c
            while end + 1 < COLS and matchable(g[r][end + 1]) and g[r][end + 1].kind == k:
                end += 1
            if end - c + 1 >= 3:
                runs.append([(r, x) for x in range(c, end + 1)])
            c = end + 1
    for c in range(COLS):
        r = 0
        while r < ROWS:
            if not matchable(g[r][c]):
                r += 1
                continue
            k = g[r][c].kind
            end = r
            while end + 1 < ROWS and matchable(g[end + 1][c]) and g[end + 1][c].kind == k:
                end += 1
            if end - r + 1 >= 3:
                runs.append([(x, c) for x in range(r, end + 1)])
            r = end + 1
    return runs


def find_matches(g):
    """Flat set of every cell involved in any match."""
    cells = set()
    for run in find_runs(g):
        cells.update(run)
    return cells


def has_move(g):
    """True if some adjacent swap would do something."""
    for r in range(ROWS):
        for c in range(COLS):
            # a hypercube can always be swapped with a neighbor
            if g[r][c] is not None and g[r][c].power == HYPER:
                return True
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if not in_bounds(r2, c2):
                    continue
                g[r][c], g[r2][c2] = g[r2][c2], g[r][c]
                ok = bool(find_runs(g))
                g[r][c], g[r2][c2] = g[r2][c2], g[r][c]
                if ok:
                    return True
    return False


def detonate(g, cells):
    """Expand a clear set to include chained flame gem explosions."""
    cleared = set(cells)
    queue = [rc for rc in cells
             if g[rc[0]][rc[1]] is not None and g[rc[0]][rc[1]].power == FLAME]
    fired = set(queue)
    while queue:
        r, c = queue.pop()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = r + dr, c + dc
                if not in_bounds(rr, cc) or g[rr][cc] is None:
                    continue
                cleared.add((rr, cc))
                if g[rr][cc].power == FLAME and (rr, cc) not in fired:
                    fired.add((rr, cc))
                    queue.append((rr, cc))
    return cleared


def plan_clear(g, runs, origin=()):
    """Work out what a set of runs destroys and what it leaves behind.

    origin is the cells the player just moved; a special prefers to appear
    under the player's own gem, which is what makes placement feel deliberate
    rather than random.

    Returns (cells_to_clear, {cell: power}).
    """
    base = set()
    spawns = {}

    for run in runs:
        base.update(run)
        if len(run) < 4:
            continue
        power = HYPER if len(run) >= 5 else FLAME
        at = next((rc for rc in origin if rc in run), run[len(run) // 2])
        if spawns.get(at, NORMAL) < power:
            spawns[at] = power

    clear = base - set(spawns)
    clear = detonate(g, clear)
    clear -= set(spawns)          # a new special survives its own blast
    return clear, spawns


def hyper_targets(g, hyper_cell, other_cell):
    """What a hypercube destroys when swapped into `other_cell`."""
    other = g[other_cell[0]][other_cell[1]]
    if other.power == HYPER:
        return {(r, c) for r in range(ROWS) for c in range(COLS) if g[r][c] is not None}
    kind = other.kind
    cells = {hyper_cell, other_cell}
    cells |= {(r, c) for r in range(ROWS) for c in range(COLS)
              if matchable(g[r][c]) and g[r][c].kind == kind}
    return detonate(g, cells)


def find_hint(g):
    """Pick a swap that would actually score. Random among all of them, so
    asking twice in a row suggests somewhere different."""
    for r in range(ROWS):
        for c in range(COLS):
            if g[r][c] is not None and g[r][c].power == HYPER:
                for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    if in_bounds(r + dr, c + dc):
                        return (r, c), (r + dr, c + dc)
    moves = []
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if not in_bounds(r2, c2):
                    continue
                g[r][c], g[r2][c2] = g[r2][c2], g[r][c]
                scores = bool(find_runs(g))
                g[r][c], g[r2][c2] = g[r2][c2], g[r][c]
                if scores:
                    moves.append(((r, c), (r2, c2)))
    return random.choice(moves) if moves else None


def count_bonus(g):
    return sum(1 for row in g for gem in row
               if gem is not None and gem.bonus)


def collapse(g, bonuses=False):
    """Drop gems into holes and refill the top.

    With bonuses=True (timed mode) some new gems arrive carrying +3 seconds.
    A floor of BONUS_MIN is topped up so the board never runs dry of them.

    Returns {(row, col): rows_fallen} so the drop can be animated.
    """
    falls = {}
    for c in range(COLS):
        write = ROWS - 1
        for r in range(ROWS - 1, -1, -1):
            if g[r][c] is not None:
                if write != r:
                    g[write][c] = g[r][c]
                    g[r][c] = None
                    falls[(write, c)] = write - r
                write -= 1
        n_new = write + 1
        for r in range(write, -1, -1):
            g[r][c] = Gem(random.randrange(N_TYPES),
                          bonus=bonuses and random.random() < BONUS_CHANCE)
            falls[(r, c)] = n_new  # falls in from above the board

    if bonuses:
        fresh = [rc for rc in falls if not g[rc[0]][rc[1]].bonus]
        random.shuffle(fresh)
        while count_bonus(g) < BONUS_MIN and fresh:
            r, c = fresh.pop()
            g[r][c].bonus = True
    return falls


def adjacent(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


# --------------------------------------------------------------------------
# easing
# --------------------------------------------------------------------------

def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return t * t * (3 - 2 * t)


class Animation:
    """Decoded, pre-scaled frames plus how fast to run them."""

    __slots__ = ("frames", "fps", "blend", "source")

    def __init__(self, frames, fps=EFFECT_FPS, blend=0, source=""):
        self.frames = frames
        self.fps = fps
        self.blend = blend
        self.source = source

    @property
    def duration(self):
        return len(self.frames) / self.fps


class Effect:
    """One playing instance, pinned to a screen position."""

    __slots__ = ("anim", "x", "y", "t")

    def __init__(self, anim, x, y):
        self.anim = anim
        self.x = x
        self.y = y
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        return self.t < self.anim.duration

    def draw(self, screen):
        index = min(int(self.t * self.anim.fps), len(self.anim.frames) - 1)
        frame = self.anim.frames[index]
        screen.blit(frame, (self.x - frame.get_width() // 2,
                            self.y - frame.get_height() // 2),
                    special_flags=self.anim.blend)


def _scaled(surface, size):
    return pygame.transform.smoothscale(surface.convert_alpha(), (size, size))


def _frames_from_folder(folder, size):
    files = sorted(f for f in os.listdir(folder)
                   if os.path.splitext(f)[1].lower() in (".png", ".webp"))
    return [_scaled(pygame.image.load(os.path.join(folder, f)), size)
            for f in files]


def _frames_from_strip(path, size, count=None):
    """Slice a horizontal strip. Square frames are assumed unless @N says."""
    sheet = pygame.image.load(path).convert_alpha()
    w, h = sheet.get_size()
    if count is None:
        count = max(1, w // h)
    fw = w // count
    return [_scaled(sheet.subsurface((i * fw, 0, fw, h)), size)
            for i in range(count)]


def _frames_from_gif(path, size):
    """Needs Pillow. Each frame is composited then handed to pygame."""
    from PIL import Image, ImageSequence
    image = Image.open(path)
    frames, durations = [], []
    for frame in ImageSequence.Iterator(image):
        rgba = frame.convert("RGBA")
        surface = pygame.image.fromstring(rgba.tobytes(), rgba.size, "RGBA")
        frames.append(_scaled(surface, size))
        durations.append(frame.info.get("duration", 1000 / EFFECT_FPS))
    average = sum(durations) / len(durations) if durations else 0
    fps = 1000.0 / average if average > 0 else EFFECT_FPS
    return frames, fps


def load_animation(name, size):
    """Find and decode one effect. Returns (Animation, note) or (None, note)."""
    folder = os.path.join(EFFECT_DIR, name)
    if os.path.isdir(folder):
        frames = _frames_from_folder(folder, size)
        if frames:
            return frames, EFFECT_FPS, f"{name}/ ({len(frames)} frames)"

    if os.path.isdir(EFFECT_DIR):
        for filename in sorted(os.listdir(EFFECT_DIR)):
            stem, ext = os.path.splitext(filename)
            base, _, count = stem.partition("@")
            if _norm(base) != _norm(name):
                continue
            path = os.path.join(EFFECT_DIR, filename)
            if ext.lower() in (".png", ".webp"):
                frames = _frames_from_strip(
                    path, size, int(count) if count.isdigit() else None)
                return frames, EFFECT_FPS, f"{filename} ({len(frames)} frames)"
            if ext.lower() == ".gif":
                try:
                    frames, fps = _frames_from_gif(path, size)
                    return frames, fps, f"{filename} ({len(frames)} gif frames)"
                except ImportError:
                    return None, None, f"{filename} needs Pillow (pip install pillow)"
    return None, None, None


def load_backgrounds():
    """Photos from backgrounds/, scaled to cover the window.

    Cover rather than stretch: the image keeps its aspect ratio and the
    overflow is cropped, so nothing ends up squashed.
    """
    shots = []
    if not os.path.isdir(BACKGROUND_DIR):
        return shots
    names = []
    for filename in os.listdir(BACKGROUND_DIR):
        stem, ext = os.path.splitext(filename)
        if ext.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            names.append((0, int(stem)) if stem.isdigit() else (1, stem.lower()))
    for _, key in sorted(names):
        stem = str(key)
        for filename in os.listdir(BACKGROUND_DIR):
            if os.path.splitext(filename)[0] == stem:
                try:
                    photo = pygame.image.load(
                        os.path.join(BACKGROUND_DIR, filename)).convert()
                except pygame.error:
                    break
                pw, ph = photo.get_size()
                scale = max(WIDTH / pw, HEIGHT / ph)
                photo = pygame.transform.smoothscale(
                    photo, (int(pw * scale + 0.5), int(ph * scale + 0.5)))
                canvas = pygame.Surface((WIDTH, HEIGHT))
                canvas.blit(photo, ((WIDTH - photo.get_width()) // 2,
                                    (HEIGHT - photo.get_height()) // 2))
                scrim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                scrim.fill((0, 0, 0, BG_DIM))   # keeps the gems readable
                canvas.blit(scrim, (0, 0))
                shots.append(canvas)
                break
    return shots


def translucent(size, fill, edge=None, radius=14):
    """Rounded rect with real alpha. pygame.draw cannot blend alpha straight
    onto the display, so anything see-through has to be built here first."""
    surf = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(surf, fill, surf.get_rect(), border_radius=radius)
    if edge:
        pygame.draw.rect(surf, edge, surf.get_rect(), 1, border_radius=radius)
    return surf


def build_effects():
    """Load every effect we know about. Missing ones simply do not play."""
    size = int(TILE * EFFECT_SCALE)
    animations, report = {}, []
    for name in EFFECT_NAMES:
        frames, fps, note = load_animation(name, size)
        if frames:
            blend = pygame.BLEND_RGBA_ADD if name in EFFECT_ADDITIVE else 0
            animations[name] = Animation(frames, fps, blend, note)
            report.append(f"   {name:<9} <- {note}")
        elif note:
            report.append(f"   {name:<9} !! {note}")
    return animations, report


class Audio:
    """Loads every sound from soundeffects/ and every track from music/.

    Files are matched by normalised name (case, spaces and punctuation are
    ignored), so you can drop your files in as-named. Every method is a safe
    no-op when the mixer failed to start or a file is missing, so the game
    still runs on a machine with no sound at all.
    """

    def __init__(self):
        self.ok = False
        self.muted = False
        self.music_volume = MUSIC_VOLUME
        self.sfx_volume = SFX_START_VOLUME
        self.snd = {}
        self.playlist = []
        self.timed_playlist = []
        self.mode = ENDLESS
        self.playlist_started = False
        self.track = 0
        self.found = []
        self.missing = []

        try:
            pygame.mixer.init()
            pygame.mixer.set_num_channels(24)   # cascades stack up fast
            self.ok = True
        except pygame.error as exc:
            print(f"No audio device ({exc}); running silent.")
            return

        index = self.index_folder(SFX_DIR)
        for key, names in SFX_ALIASES.items():
            path = next((index[_norm(n)] for n in names if _norm(n) in index), None)
            if path is None:
                self.missing.append(f"{key} ({names[0]}.ogg)")
                self.snd[key] = None
                continue
            try:
                sound = pygame.mixer.Sound(path)
                sound.set_volume(self.sfx_volume)
                self.snd[key] = sound
                self.found.append(f"{key} <- {os.path.basename(path)}")
            except pygame.error as exc:
                print(f"Could not load {os.path.basename(path)}: {exc}")
                self.snd[key] = None

        self.fake_missing_cascades()
        self.load_music()

    @staticmethod
    def index_folder(folder):
        """{normalised filename stem: full path} for every audio file inside.

        Only the folder itself - subfolders are left alone, which is what
        keeps "Timed Music" out of the endless playlist.
        """
        found = {}
        if not os.path.isdir(folder):
            return found
        for filename in sorted(os.listdir(folder)):
            path = os.path.join(folder, filename)
            if os.path.isdir(path):
                continue
            stem, ext = os.path.splitext(filename)
            if ext.lower() in AUDIO_EXTS:
                found.setdefault(_norm(stem), path)
        return found

    def fake_missing_cascades(self):
        """If a CascadeN.ogg is absent, pitch the match sound up instead.

        Resampling shorter = higher and faster, which is roughly what the
        original games do. Needs numpy; without it the slot just stays silent.
        """
        base = self.snd.get("match3")
        if base is None or np is None:
            return
        try:
            arr = pygame.sndarray.array(base)
        except (pygame.error, AttributeError):
            return

        n = arr.shape[0]
        for level in range(2, 7):
            key = f"cascade{level}"
            if self.snd.get(key) is not None:
                continue
            ratio = 2 ** ((level - 1) * CASCADE_SEMITONES / 12)
            idx = np.linspace(0, n - 1, max(1, int(n / ratio)))
            lo = np.floor(idx).astype(int)
            hi = np.minimum(lo + 1, n - 1)
            frac = idx - lo
            if arr.ndim == 2:
                frac = frac[:, None]
            mixed = np.ascontiguousarray(
                (arr[lo] * (1 - frac) + arr[hi] * frac).astype(arr.dtype))
            try:
                sound = pygame.sndarray.make_sound(mixed)
                sound.set_volume(self.sfx_volume)
                self.snd[key] = sound
                self.missing = [m for m in self.missing if not m.startswith(key)]
                self.found.append(f"{key} <- pitched up from match3")
            except (pygame.error, ValueError):
                return

    def load_music(self):
        """Two playlists: the shuffled main one, and the timed-mode set."""
        index = self.index_folder(MUSIC_DIR)
        self.playlist = [index[key] for key in sorted(index)]
        random.shuffle(self.playlist)

        timed_dir = os.path.join(MUSIC_DIR, TIMED_MUSIC_SUBDIR)
        timed_index = self.index_folder(timed_dir)
        self.timed_playlist = [timed_index[key] for key in sorted(timed_index)]
        random.shuffle(self.timed_playlist)

        if not self.playlist:
            self.missing.append("music (nothing in music/)")
        if not self.timed_playlist:
            self.missing.append(f"timed music (nothing in {TIMED_MUSIC_SUBDIR}/)")
        if not self.playlist and not self.timed_playlist:
            return

        pygame.mixer.music.set_volume(self.music_volume)
        pygame.mixer.music.set_endevent(MUSIC_END)
        self.use_playlist(ENDLESS)

    def active_list(self):
        """Timed mode falls back to the main playlist if the subfolder is
        empty, so the game never goes silent."""
        if self.mode == TIMED and self.timed_playlist:
            return self.timed_playlist
        return self.playlist

    def use_playlist(self, mode):
        """Switch which set of tracks is playing, starting somewhere random.

        Picking a random index rather than 0 matters: without it, every
        switch back to a mode restarts that mode's first song, so a session
        spent toggling modes hears the same two tracks forever.
        """
        if mode == self.mode and self.playlist_started:
            return
        playing = self.now_playing()
        self.mode = mode
        self.playlist_started = True
        songs = self.active_list()
        if not songs:
            return
        choices = [i for i in range(len(songs))
                   if os.path.splitext(os.path.basename(songs[i]))[0] != playing]
        self.play_track(random.choice(choices or range(len(songs))))

    def reshuffle(self):
        """Shuffle again, but never let the same track play twice in a row."""
        songs = self.active_list()
        if len(songs) < 2:
            return
        last = songs[self.track]
        for _ in range(8):
            random.shuffle(songs)
            if songs[0] is not last:
                return
        songs.append(songs.pop(0))

    def play_track(self, i):
        songs = self.active_list()
        if not self.ok or not songs:
            return
        self.track = i % len(songs)
        try:
            pygame.mixer.music.load(songs[self.track])
            pygame.mixer.music.play()
        except pygame.error as exc:
            print(f"Could not play {os.path.basename(songs[self.track])}: {exc}")

    def next_track(self):
        """Called from the main loop when a track ends."""
        songs = self.active_list()
        if not songs:
            return
        if self.track + 1 >= len(songs):
            self.reshuffle()                 # new order every time round
            self.play_track(0)
        else:
            self.play_track(self.track + 1)

    def random_track(self):
        """Jump straight to some other song. Returns its display name."""
        songs = self.active_list()
        if not self.ok or not songs:
            return None
        if len(songs) > 1:
            choices = [i for i in range(len(songs)) if i != self.track]
            self.play_track(random.choice(choices))
        else:
            self.play_track(0)
        return self.now_playing()

    def now_playing(self):
        songs = self.active_list()
        if not songs:
            return None
        return os.path.splitext(os.path.basename(songs[self.track]))[0]

    def play(self, key):
        if not self.ok or self.muted:
            return
        sound = self.snd.get(key)
        if sound is not None:
            sound.play()

    @classmethod
    def silent(cls):
        """A do-nothing Audio, for tests or when the caller wants no sound."""
        a = cls.__new__(cls)
        a.ok = False
        a.muted = True
        a.music_volume = MUSIC_VOLUME
        a.sfx_volume = SFX_START_VOLUME
        a.snd = {}
        a.playlist = []
        a.timed_playlist = []
        a.mode = ENDLESS
        a.playlist_started = False
        a.track = 0
        a.found = []
        a.missing = []
        return a

    def play_match(self, cascade, special=False):
        """One voice per clear: cascade tone if chaining, else match3/match4-5."""
        if not self.ok or self.muted:
            return
        if cascade >= 2 and self.snd.get(f"cascade{min(cascade, 6)}") is not None:
            self.play(f"cascade{min(cascade, 6)}")
        elif special:
            self.play("match45")
        else:
            self.play("match3")

    def apply_volume(self):
        if self.ok:
            pygame.mixer.music.set_volume(0.0 if self.muted else self.music_volume)

    def set_music_volume(self, value):
        """Set music level. Touching the slider also lifts a mute, which is
        what people expect when they drag a volume control."""
        self.music_volume = clamp01(value)
        if self.music_volume > 0:
            self.muted = False
        self.apply_volume()
        return self.music_volume

    def nudge_volume(self, delta):
        return self.set_music_volume(self.music_volume + delta)

    def set_sfx_volume(self, value):
        """Sound effects have their own level, independent of the music."""
        self.sfx_volume = clamp01(value)
        for sound in self.snd.values():
            if sound is not None:
                sound.set_volume(self.sfx_volume)
        return self.sfx_volume

    def toggle_mute(self):
        self.muted = not self.muted
        self.apply_volume()
        return self.muted

    def report(self):
        if not self.ok:
            return
        if self.found:
            print("Sound loaded:")
            for line in self.found:
                print("   " + line)
        if self.playlist:
            print("Music: "
                  + ", ".join(os.path.splitext(os.path.basename(p))[0]
                              for p in self.playlist))
        if self.timed_playlist:
            print("Timed music: "
                  + ", ".join(os.path.splitext(os.path.basename(p))[0]
                              for p in self.timed_playlist))
        if self.missing:
            print("Not found (these stay silent): " + ", ".join(self.missing))
            print(f"   effects go in: {SFX_DIR}")
            print(f"   music goes in: {MUSIC_DIR}")
        print()


# --------------------------------------------------------------------------
# game
# --------------------------------------------------------------------------

class Puff:
    """One smoke sprite: drifts outward, swells and fades."""

    LIFE = 0.85
    __slots__ = ("image", "x", "y", "dx", "dy", "spin", "t")

    def __init__(self, image, x, y):
        self.image = image
        self.x, self.y = x, y
        angle = random.uniform(0, math.tau)
        speed = random.uniform(16, 46)
        self.dx = math.cos(angle) * speed
        self.dy = math.sin(angle) * speed - 14      # drifts up a little
        self.spin = random.uniform(-70, 70)
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        return self.t < self.LIFE

    def draw(self, screen):
        progress = self.t / self.LIFE
        scale = 0.55 + 0.85 * ease_out(progress)
        image = pygame.transform.rotozoom(self.image, self.spin * progress, scale)
        image.set_alpha(int(210 * (1.0 - progress) ** 1.5))
        screen.blit(image, image.get_rect(center=(
            int(self.x + self.dx * progress),
            int(self.y + self.dy * progress))))


class TimePop:
    """A floating "+3s" that drifts up and fades where a bonus gem cleared."""

    LIFE = 1.0
    __slots__ = ("x", "y", "t")

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        return self.t < self.LIFE

    def draw(self, screen, font):
        progress = self.t / self.LIFE
        label = font.render(f"+{int(BONUS_SECONDS)}s", True, (126, 240, 168))
        label.set_alpha(int(255 * (1.0 - progress ** 2)))
        screen.blit(label, label.get_rect(
            center=(self.x, self.y - int(38 * ease_out(progress)))))


class Button:
    """Flat rounded button. Knows how it looks, not what it does."""

    def __init__(self, rect, label, action, accent=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.accent = accent
        self.hover = False
        self.down = False

    def hit(self, pos):
        return self.rect.collidepoint(pos)

    def draw(self, screen, font):
        if self.down and self.hover:
            fill = BTN_DOWN
        elif self.hover:
            fill = BTN_HOVER
        else:
            fill = BTN
        screen.blit(translucent(self.rect.size, fill, PANEL_EDGE, 10),
                    self.rect.topleft)
        if self.accent:
            pygame.draw.rect(screen, self.accent,
                             (self.rect.x, self.rect.y + 8, 3, self.rect.height - 16),
                             border_radius=2)
        text = font.render(self.label, True, TEXT if self.hover else (206, 212, 228))
        screen.blit(text, text.get_rect(center=self.rect.center))


class Slider:
    """Labelled horizontal slider wired to a getter/setter pair."""

    def __init__(self, rect, label, get, set):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.get = get
        self.set = set

    def hit(self, pos):
        return self.rect.inflate(20, 28).collidepoint(pos)

    def set_from(self, pos):
        self.set((pos[0] - self.rect.x) / self.rect.width)

    def draw(self, screen, font, small, dragging=False):
        value = clamp01(self.get())
        label = small.render(self.label, True, DIM)
        screen.blit(label, (self.rect.x, self.rect.y - 24))
        pct = small.render(f"{int(round(value * 100))}%", True, DIM)
        screen.blit(pct, (self.rect.right - pct.get_width(), self.rect.y - 24))

        screen.blit(translucent(self.rect.size, (255, 255, 255, 38), None,
                                self.rect.height // 2), self.rect.topleft)
        if value > 0:
            width = int(self.rect.width * value)
            if width >= self.rect.height:
                screen.blit(translucent((width, self.rect.height),
                                        (206, 210, 218, 235), None,
                                        self.rect.height // 2),
                            self.rect.topleft)
        knob = self.rect.x + int(self.rect.width * value)
        pygame.draw.circle(screen, TEXT, (knob, self.rect.centery),
                           9 if dragging else 8)


class Game:
    """State machine: idle -> swap -> (clear -> fall -> clear ...) -> idle."""

    def __init__(self, sprites, audio=None, effects=None, backgrounds=None):
        self.normal, self.flame, self.hyper, _ = sprites
        self.anims = effects or {}
        self.backgrounds = backgrounds or []
        self.fire = load_still(FIRE_ASSET, int(TILE * 1.30))
        self.smoke = load_still(SMOKE_ASSET, int(TILE * 1.55))
        self.hyper_glow = bake_glow(self.hyper, (255, 255, 255, 255))
        self.puffs = []
        self.effects = []
        self.panel_bg = translucent((PANEL_W, PANEL_H), PANEL_FILL, PANEL_EDGE, 14)
        self.board_bg = self.build_board_backdrop()
        self.menu_bg = translucent(self.menu_rect().size, PANEL_FILL,
                                   PANEL_EDGE, 16)
        self.mode = ENDLESS
        self.audio = audio if audio is not None else Audio.silent()
        face = "Helvetica,Arial,DejaVu Sans"
        self.font_huge = pygame.font.SysFont(face, 48, bold=True)
        self.font_score = pygame.font.SysFont(face, 36, bold=True)
        self.font_big = pygame.font.SysFont(face, 21, bold=True)
        self.font = pygame.font.SysFont(face, 16)
        self.font_small = pygame.font.SysFont(face, 13)
        self.build_widgets()
        self.reset()

    def reset(self, mode=None):
        if mode is not None:
            self.mode = mode
        self.time = 0.0
        self.score = 0
        self.level = 1
        self.level_floor = 0          # score at which the current level began
        self.menu_open = False
        self.dragging = None
        self.wants_quit = False
        self.hint = None
        self.hint_left = 0.0
        self.effects = []
        self.go_left = 0.0
        self.flash = 0.0
        self.note = ""
        self.time_left = TIMED_SECONDS
        self.over = False
        self.time_pops = []          # floating "+3s" labels
        self.puffs = []              # smoke left by flame gems
        self.audio.use_playlist(self.mode)
        self.new_board()

    def new_board(self):
        """Fresh grid for the current level, rained in from above."""
        self.grid = new_grid(bonuses=self.timed)
        self.begin_intro()

    @property
    def timed(self):
        return self.mode == TIMED

    def set_mode(self, mode):
        """Switch game mode. Always starts a fresh run, and swaps the music."""
        self.menu_open = False
        self.reset(mode)

    def begin_intro(self):
        self.state = "intro"
        self.t = 0.0
        self.sel = None
        self.press = None
        self.pair = None
        self.matched = set()
        self.spawns = {}
        self.falls = {}
        self.pops = {}
        self.cascade = 0
        # one GemFalling per Nth column, fired as that column lands
        self.intro_cues = [c * INTRO_STAGGER
                           for c in range(0, COLS, INTRO_SOUND_EVERY)]

    @staticmethod
    def build_board_backdrop():
        """Translucent board with its checker pattern clipped to the rounded
        corners, baked once instead of redrawn every frame."""
        base = translucent((BOARD_W, BOARD_H), BOARD_FILL, None, 14)
        checker = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
        for r in range(ROWS):
            for c in range(COLS):
                if (r + c) % 2:
                    pygame.draw.rect(checker, CELL_HI,
                                     (c * TILE, r * TILE, TILE, TILE))
        mask = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(),
                         border_radius=14)
        checker.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        base.blit(checker, (0, 0))
        pygame.draw.rect(base, PANEL_EDGE, base.get_rect(), 1, border_radius=14)
        return base

    def background_for_level(self):
        if not self.backgrounds:
            return None
        return self.backgrounds[(self.level - 1) % len(self.backgrounds)]

    # -- effects ----------------------------------------------------------

    def spawn_effect(self, name, r, c):
        """Play an animation centred on a board cell, if that effect exists."""
        anim = self.anims.get(name)
        if anim is None or len(self.effects) >= MAX_EFFECTS:
            return
        self.effects.append(Effect(anim,
                                   BOARD_X + int((c + 0.5) * TILE),
                                   BOARD_Y + int((r + 0.5) * TILE)))

    def spawn_smoke(self, r, c, count=5):
        """A little cloud where a flame gem went off."""
        if self.smoke is None:
            return
        if len(self.puffs) > MAX_EFFECTS:
            return
        x = BOARD_X + int((c + 0.5) * TILE)
        y = BOARD_Y + int((r + 0.5) * TILE)
        for _ in range(count):
            self.puffs.append(Puff(self.smoke, x, y))

    def spawn_effect_at(self, name, x, y):
        anim = self.anims.get(name)
        if anim is not None and len(self.effects) < MAX_EFFECTS:
            self.effects.append(Effect(anim, x, y))

    # -- progression ------------------------------------------------------

    def end_game(self):
        self.over = True
        self.sel = None
        self.hint = None
        self.menu_open = False
        self.note = ""
        self.flash = 0.5
        self.audio.play("gameover")

    def levelup_pause(self):
        """Hold the level-up banner for as long as LevelUp.ogg actually runs,
        so the gems do not start dropping over the top of it."""
        sound = self.audio.snd.get("levelup") if self.audio.ok else None
        length = sound.get_length() if sound is not None else 0.0
        return max(LEVELUP_MIN, min(LEVELUP_MAX, length))

    def level_target(self):
        """Points needed to clear the current level."""
        return int(LEVEL_BASE_TARGET * LEVEL_GROWTH ** (self.level - 1))

    def level_progress(self):
        earned = self.score - self.level_floor
        return max(0.0, min(1.0, earned / self.level_target()))

    def begin_levelup(self):
        self.level_floor += self.level_target()   # overflow carries forward
        self.level += 1
        self.state = "levelup"
        self.t = 0.0
        self.sel = None
        self.pair = None
        self.flash = 0.9
        self.note = f"LEVEL {self.level}"
        self.spawn_effect_at("levelup",
                             BOARD_X + BOARD_W // 2, BOARD_Y + BOARD_H // 2)
        self.audio.play("levelup")

    def secret_shuffle(self):
        """Hidden reshuffle. New board, score and level untouched.

        Only fires when the board is settled, so it can't interrupt a cascade
        that is still paying out points.
        """
        if self.over or self.state != "idle":
            return False
        self.grid = new_grid(bonuses=self.timed)
        self.flash = 0.35
        self.audio.play("shuffle")
        self.begin_intro()          # rains the new board in like any other
        return True

    # -- widgets ----------------------------------------------------------

    def build_widgets(self):
        inner_x = PANEL_X + 16
        inner_w = PANEL_W - 32
        bottom = PANEL_Y + PANEL_H - 16
        self.buttons = [
            Button((inner_x, bottom - 46 * 3 - 20, inner_w, 46),
                   "HINT", self.show_hint, accent=HINT_COLOR),
            Button((inner_x, bottom - 46 * 2 - 10, inner_w, 46),
                   "SHUFFLE SONG", self.shuffle_song, accent=(150, 160, 190)),
            Button((inner_x, bottom - 46, inner_w, 46),
                   "MENU", self.open_menu),
        ]

        box = self.menu_rect()
        sx, sw = box.x + 30, box.width - 60
        self.sliders = [
            Slider((sx, box.y + 104, sw, 8), "MUSIC",
                   lambda: self.audio.music_volume, self.audio.set_music_volume),
            Slider((sx, box.y + 168, sw, 8), "SOUND EFFECTS",
                   lambda: self.audio.sfx_volume, self.audio.set_sfx_volume),
        ]
        half = (sw - 20) // 2
        self.menu_buttons = [
            Button((sx, box.y + 210, half, 42), "ENDLESS",
                   lambda: self.set_mode(ENDLESS), accent=GOLD),
            Button((sx + half + 20, box.y + 210, half, 42), "TIMED",
                   lambda: self.set_mode(TIMED), accent=(126, 216, 150)),
            Button((sx, box.y + 262, half, 42), "RESUME", self.close_menu),
            Button((sx + half + 20, box.y + 262, half, 42), "QUIT", self.quit,
                   accent=(232, 92, 92)),
        ]

        over = self.over_rect()
        ox, ow = over.x + 34, over.width - 68
        third = (ow - 20) // 2
        self.over_buttons = [
            Button((ox, over.bottom - 74, third, 46), "PLAY AGAIN",
                   lambda: self.reset(self.mode), accent=(126, 216, 150)),
            Button((ox + third + 20, over.bottom - 74, third, 46), "ENDLESS",
                   lambda: self.set_mode(ENDLESS), accent=GOLD),
        ]

    @staticmethod
    def over_rect():
        return pygame.Rect(WIDTH // 2 - 210, HEIGHT // 2 - 150, 420, 300)

    @staticmethod
    def menu_rect():
        return pygame.Rect(WIDTH // 2 - 220, HEIGHT // 2 - 180, 440, 350)

    # -- button actions ---------------------------------------------------

    def show_hint(self):
        if self.over or self.state != "idle":
            return
        self.hint = find_hint(self.grid)
        self.hint_left = HINT_SECONDS if self.hint else 0.0
        self.note = "" if self.hint else "no moves - reshuffling"
        if self.hint is None:
            self.secret_shuffle()

    def shuffle_song(self):
        name = self.audio.random_track()
        self.note = f"now playing: {name}" if name else "no music loaded"

    def open_menu(self):
        self.menu_open = True
        self.sel = None
        self.dragging = None

    def close_menu(self):
        self.menu_open = False
        self.dragging = None

    def quit(self):
        self.wants_quit = True

    # -- input ------------------------------------------------------------

    def cell_at(self, pos):
        x, y = pos
        c = (x - BOARD_X) // TILE
        r = (y - BOARD_Y) // TILE
        if in_bounds(r, c):
            return int(r), int(c)
        return None

    def widgets_at(self, pos):
        """Whatever interactive thing is under the cursor, overlays first."""
        if self.over:
            for button in self.over_buttons:
                if button.hit(pos):
                    return button
            return None
        if self.menu_open:
            for slider in self.sliders:
                if slider.hit(pos):
                    return slider
            for button in self.menu_buttons:
                if button.hit(pos):
                    return button
            return None
        for button in self.buttons:
            if button.hit(pos):
                return button
        return None

    def on_down(self, pos):
        hit = self.widgets_at(pos)
        if isinstance(hit, Slider):
            self.dragging = hit
            hit.set_from(pos)
            self.audio.play("menuclick")
            return
        if isinstance(hit, Button):
            hit.down = True
            self.audio.play("menuclick")
            return
        if self.over:
            return                     # nothing but those two buttons is live
        if self.menu_open:
            if not self.menu_rect().collidepoint(pos):
                self.audio.play("menuclick")
                self.close_menu()      # click outside the box dismisses it
            return

        if self.state != "idle":
            return
        cell = self.cell_at(pos)
        self.press = cell
        if cell is None:
            self.sel = None
        elif self.sel is not None and adjacent(self.sel, cell):
            self.begin_swap(self.sel, cell)
        else:
            self.sel = cell
            self.audio.play("select")

    def on_motion(self, pos):
        if self.dragging is not None:
            self.dragging.set_from(pos)
            return
        if self.over:
            active = self.over_buttons
        elif self.menu_open:
            active = self.menu_buttons
        else:
            active = self.buttons
        for button in self.buttons + self.menu_buttons + self.over_buttons:
            button.hover = button in active and button.hit(pos)

    def on_up(self, pos):
        if self.dragging is not None:
            self.dragging = None
            return

        fired = None
        for button in self.buttons + self.menu_buttons + self.over_buttons:
            if button.down and button.hit(pos):
                fired = button
            button.down = False
        if fired is not None:
            fired.action()
            return

        if self.over or self.menu_open or self.state != "idle" or self.press is None:
            return
        cell = self.cell_at(pos)
        if cell is not None and cell != self.press and adjacent(self.press, cell):
            self.begin_swap(self.press, cell)
        self.press = None

    def begin_swap(self, a, b):
        self.hint = None
        self.hint_left = 0.0
        self.pair = (a, b)
        self.sel = None
        self.press = None
        self.state = "swap"
        self.t = 0.0

    # -- update -----------------------------------------------------------

    def apply_swap(self):
        (r1, c1), (r2, c2) = self.pair
        self.grid[r1][c1], self.grid[r2][c2] = self.grid[r2][c2], self.grid[r1][c1]

    def update(self, dt):
        self.time += dt
        if self.effects:
            self.effects = [e for e in self.effects if e.update(dt)]
        if self.go_left > 0:
            self.go_left = max(0.0, self.go_left - dt)
        if self.time_pops:
            self.time_pops = [p for p in self.time_pops if p.update(dt)]
        if self.puffs:
            self.puffs = [p for p in self.puffs if p.update(dt)]

        # the clock only runs while the board is actually playable
        if (self.timed and not self.over
                and self.state not in ("intro", "levelup")):
            self.time_left -= dt
            if self.time_left <= 0:
                self.time_left = 0.0
                self.end_game()
        if self.hint_left > 0:
            self.hint_left = max(0.0, self.hint_left - dt)
            if self.hint_left == 0:
                self.hint = None
        self.flash = max(0.0, self.flash - dt)
        for cell in list(self.pops):
            self.pops[cell] -= dt
            if self.pops[cell] <= 0:
                del self.pops[cell]

        if self.state == "idle":
            return

        dur = {"swap": SWAP_TIME, "swapback": SWAP_TIME,
               "clear": CLEAR_TIME, "fall": FALL_TIME,
               "intro": INTRO_TIME, "levelup": self.levelup_pause()}[self.state]
        self.t += dt / dur

        # patter of landing gems while the board rains in
        if self.state == "intro":
            elapsed = self.t * INTRO_TIME
            while self.intro_cues and self.intro_cues[0] <= elapsed:
                self.intro_cues.pop(0)
                self.audio.play("falling")

        if self.t < 1.0:
            return
        self.t = 0.0

        if self.state == "intro":
            self.note = ""
            self.go_left = GO_TIME
            self.audio.play("go")
            self.state = "idle"
        elif self.state == "levelup":
            self.new_board()
        elif self.state == "swap":
            self.resolve_swap()
        elif self.state == "swapback":
            self.state = "idle"
            self.pair = None
        elif self.state == "clear":
            self.finish_clear()
        elif self.state == "fall":
            self.falls = {}
            runs = find_runs(self.grid)
            if runs:
                self.cascade += 1
                self.begin_clear(*plan_clear(self.grid, runs))
            else:
                self.settle()

    def resolve_swap(self):
        a, b = self.pair
        ga = self.grid[a[0]][a[1]]
        gb = self.grid[b[0]][b[1]]

        # hypercube path: always legal, never needs a match
        if ga.power == HYPER or gb.power == HYPER:
            hyper, other = (a, b) if ga.power == HYPER else (b, a)
            both = ga.power == HYPER and gb.power == HYPER
            self.cascade = 1
            self.begin_clear(hyper_targets(self.grid, hyper, other), {})
            self.note = "BOARD WIPE!" if both else "HYPERCUBE!"
            self.flash = 0.5 if both else 0.25
            self.spawn_effect("hyper", *hyper)
            self.audio.play("hyper")
            return

        self.apply_swap()
        runs = find_runs(self.grid)
        if runs:
            self.cascade = 1
            self.begin_clear(*plan_clear(self.grid, runs, origin=(a, b)))
        else:
            self.apply_swap()          # undo the data change
            self.state = "swapback"    # then animate the undo
            self.note = ""
            self.audio.play("nomatch")

    def award_time(self, cells):
        """+3 seconds for each bonus gem in this clear, with a floating label."""
        if not self.timed:
            return
        gained = 0
        # Spawn cells count too: if a bonus gem is the one that turns into a
        # flame or hypercube, the player still matched it and still earns the
        # time. The flag is cleared in finish_clear so it cannot pay twice.
        for r, c in set(cells) | set(self.spawns):
            gem = self.grid[r][c]
            if gem is not None and gem.bonus:
                gained += 1
                self.time_pops.append(TimePop(
                    BOARD_X + int((c + 0.5) * TILE),
                    BOARD_Y + int((r + 0.5) * TILE)))
        if gained:
            self.time_left = min(TIMED_MAX,
                                 self.time_left + BONUS_SECONDS * gained)
            self.audio.play("bonus")

    def begin_clear(self, cells, spawns):
        self.matched = cells
        self.spawns = spawns
        self.award_time(cells)
        for r, c in cells:
            gem = self.grid[r][c]
            if gem is not None and gem.power == FLAME:
                self.spawn_effect("explode", r, c)
                self.spawn_smoke(r, c)
            else:
                self.spawn_effect("match", r, c)
        gained = len(cells) * POINTS_PER_GEM * self.cascade
        for power in spawns.values():
            gained += HYPER_BONUS if power == HYPER else FLAME_BONUS
        self.score += gained

        self.audio.play_match(self.cascade, bool(spawns))
        if any(self.grid[r][c] is not None and self.grid[r][c].power == FLAME
               for r, c in cells):
            self.audio.play("explode")
        if HYPER in spawns.values():
            self.note = "HYPERCUBE!"
        elif FLAME in spawns.values():
            self.note = "FLAME GEM!"
        elif self.cascade > 1:
            self.note = f"CASCADE x{self.cascade}"
        self.state = "clear"

    def finish_clear(self):
        for r, c in self.matched:
            self.grid[r][c] = None
        for (r, c), power in self.spawns.items():
            gem = self.grid[r][c]
            gem.power = power
            gem.bonus = False          # already paid out in award_time
            if power == HYPER:
                gem.kind = HYPER_KIND
            self.pops[(r, c)] = POP_TIME
        self.matched = set()
        self.spawns = {}
        self.falls = collapse(self.grid, bonuses=self.timed)
        self.audio.play("falling")
        self.state = "fall"

    def settle(self):
        self.pair = None
        self.cascade = 0
        if self.level_progress() >= 1.0:
            self.begin_levelup()
            return
        if not has_move(self.grid):
            self.grid = new_grid()
            self.note = "no moves - reshuffled"
            self.flash = 0.6
            self.audio.play("shuffle")
        self.state = "idle"

    # -- drawing ----------------------------------------------------------

    def sprite_for(self, gem):
        if gem.power == HYPER:
            return self.hyper
        if gem.power == FLAME:
            return self.flame[gem.kind]
        return self.normal[gem.kind]

    def draw_behind(self, screen, gem, x, y):
        """Whatever sits *under* a special gem: fire, or the power-gem halo."""
        cx, cy = int(x + TILE / 2), int(y + TILE / 2)

        if gem.power == FLAME and self.fire is not None:
            # two copies at different speeds, so the flame breathes and sways
            # instead of just pulsing on the spot
            for phase, base, sway in ((0.0, 1.00, 4.0), (1.9, 0.86, -2.6)):
                t = self.time * 2.3 + phase + (cx + cy) * 0.01
                scale = base + 0.10 * math.sin(t) + 0.045 * math.sin(t * 2.7)
                image = pygame.transform.rotozoom(
                    self.fire, 3.5 * math.sin(t * 0.8), scale)
                image.set_alpha(150 + int(70 * (0.5 + 0.5 * math.sin(t * 1.3))))
                screen.blit(image, image.get_rect(
                    center=(cx + int(sway * math.sin(t * 0.9)),
                            cy - int(3 + 3 * math.sin(t)))),
                    special_flags=pygame.BLEND_RGBA_ADD)

        elif gem.power == HYPER:
            pulse = 0.5 + 0.5 * math.sin(self.time * 3.2)
            image = pygame.transform.rotozoom(
                self.hyper_glow, (self.time * 26) % 360, 0.94 + 0.10 * pulse)
            image.set_alpha(150 + int(90 * pulse))
            screen.blit(image, image.get_rect(center=(cx, cy)),
                        special_flags=pygame.BLEND_RGBA_ADD)

    def gem_draw_info(self, r, c):
        """Returns (x, y, scale) for the gem at r,c."""
        x = BOARD_X + c * TILE
        y = BOARD_Y + r * TILE
        scale = 1.0

        if self.state in ("swap", "swapback") and self.pair and (r, c) in self.pair:
            a, b = self.pair
            other = b if (r, c) == a else a
            p = ease_in_out(self.t)
            if self.state == "swapback":
                p = 1 - p
            x += (other[1] - c) * TILE * p
            y += (other[0] - r) * TILE * p

        elif self.state == "clear" and (r, c) in self.matched:
            scale = max(0.0, 1.0 - ease_in_out(self.t))

        elif self.state == "fall" and (r, c) in self.falls:
            d = self.falls[(r, c)]
            y -= d * TILE * (1 - ease_out(self.t))

        elif self.state == "intro":
            # each column starts a little later, so the board lands left to right
            p = clamp01((self.t * INTRO_TIME - c * INTRO_STAGGER) / INTRO_FALL)
            y -= (ROWS + 2) * TILE * (1 - ease_out(p))

        elif self.state == "levelup":
            # old board peels away diagonally before the next one drops
            delay = (r + c) / (ROWS + COLS) * 0.30
            p = clamp01((self.t * self.levelup_pause() - delay) / 0.40)
            scale = 1.0 - ease_in_out(p)
            y -= 30 * p

        if (r, c) in self.pops:
            p = self.pops[(r, c)] / POP_TIME
            scale *= 1.0 + 0.45 * math.sin(p * math.pi)

        return x, y, scale

    def draw_bonus_tag(self, screen, x, y):
        """Green +3s badge, pinned to the bottom of a bonus gem."""
        pulse = 0.5 + 0.5 * math.sin(self.time * 4.5)
        label = self.font_small.render(f"+{int(BONUS_SECONDS)}s", True,
                                       (18, 32, 24))
        pad = 5
        w = label.get_width() + pad * 2
        h = label.get_height() + 2
        chip = translucent((w, h), (126, 240, 168, 200 + int(55 * pulse)),
                           None, h // 2)
        chip.blit(label, (pad, 1))
        screen.blit(chip, (int(x + (TILE - w) / 2), int(y + TILE - h - 3)))

        ring = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.rect(ring, (126, 240, 168, int(70 + 60 * pulse)),
                         (2, 2, TILE - 4, TILE - 4), 2, border_radius=10)
        screen.blit(ring, (int(x), int(y)))

    def gem_draw_info(self, r, c):
        """Returns (x, y, scale) for the gem at r,c."""
        x = BOARD_X + c * TILE
        y = BOARD_Y + r * TILE
        scale = 1.0

        if self.state in ("swap", "swapback") and self.pair and (r, c) in self.pair:
            a, b = self.pair
            other = b if (r, c) == a else a
            p = ease_in_out(self.t)
            if self.state == "swapback":
                p = 1 - p
            x += (other[1] - c) * TILE * p
            y += (other[0] - r) * TILE * p

        elif self.state == "clear" and (r, c) in self.matched:
            scale = max(0.0, 1.0 - ease_in_out(self.t))

        elif self.state == "fall" and (r, c) in self.falls:
            d = self.falls[(r, c)]
            y -= d * TILE * (1 - ease_out(self.t))

        elif self.state == "intro":
            # each column starts a little later, so the board lands left to right
            p = clamp01((self.t * INTRO_TIME - c * INTRO_STAGGER) / INTRO_FALL)
            y -= (ROWS + 2) * TILE * (1 - ease_out(p))

        elif self.state == "levelup":
            # old board peels away diagonally before the next one drops
            delay = (r + c) / (ROWS + COLS) * 0.30
            p = clamp01((self.t * self.levelup_pause() - delay) / 0.40)
            scale = 1.0 - ease_in_out(p)
            y -= 30 * p

        if (r, c) in self.pops:
            p = self.pops[(r, c)] / POP_TIME
            scale *= 1.0 + 0.45 * math.sin(p * math.pi)

        return x, y, scale

    def draw_bonus_tag(self, screen, x, y):
        """Green +3s badge, pinned to the bottom of a bonus gem."""
        pulse = 0.5 + 0.5 * math.sin(self.time * 4.5)
        label = self.font_small.render(f"+{int(BONUS_SECONDS)}s", True,
                                       (18, 32, 24))
        pad = 5
        w = label.get_width() + pad * 2
        h = label.get_height() + 2
        chip = translucent((w, h), (126, 240, 168, 200 + int(55 * pulse)),
                           None, h // 2)
        chip.blit(label, (pad, 1))
        screen.blit(chip, (int(x + (TILE - w) / 2), int(y + TILE - h - 3)))

        ring = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.rect(ring, (126, 240, 168, int(70 + 60 * pulse)),
                         (2, 2, TILE - 4, TILE - 4), 2, border_radius=10)
        screen.blit(ring, (int(x), int(y)))

    def gem_draw_info(self, r, c):
        """Returns (x, y, scale) for the gem at r,c."""
        x = BOARD_X + c * TILE
        y = BOARD_Y + r * TILE
        scale = 1.0

        if self.state in ("swap", "swapback") and self.pair and (r, c) in self.pair:
            a, b = self.pair
            other = b if (r, c) == a else a
            p = ease_in_out(self.t)
            if self.state == "swapback":
                p = 1 - p
            x += (other[1] - c) * TILE * p
            y += (other[0] - r) * TILE * p

        elif self.state == "clear" and (r, c) in self.matched:
            scale = max(0.0, 1.0 - ease_in_out(self.t))

        elif self.state == "fall" and (r, c) in self.falls:
            d = self.falls[(r, c)]
            y -= d * TILE * (1 - ease_out(self.t))

        elif self.state == "intro":
            # each column starts a little later, so the board lands left to right
            p = clamp01((self.t * INTRO_TIME - c * INTRO_STAGGER) / INTRO_FALL)
            y -= (ROWS + 2) * TILE * (1 - ease_out(p))

        elif self.state == "levelup":
            # old board peels away diagonally before the next one drops
            delay = (r + c) / (ROWS + COLS) * 0.30
            p = clamp01((self.t * self.levelup_pause() - delay) / 0.40)
            scale = 1.0 - ease_in_out(p)
            y -= 30 * p

        if (r, c) in self.pops:
            p = self.pops[(r, c)] / POP_TIME
            scale *= 1.0 + 0.45 * math.sin(p * math.pi)

        return x, y, scale

    def draw_bonus_tag(self, screen, x, y):
        """Green +3s badge, pinned to the bottom of a bonus gem."""
        pulse = 0.5 + 0.5 * math.sin(self.time * 4.5)
        label = self.font_small.render(f"+{int(BONUS_SECONDS)}s", True,
                                       (18, 32, 24))
        pad = 5
        w = label.get_width() + pad * 2
        h = label.get_height() + 2
        chip = translucent((w, h), (126, 240, 168, 200 + int(55 * pulse)),
                           None, h // 2)
        chip.blit(label, (pad, 1))
        screen.blit(chip, (int(x + (TILE - w) / 2), int(y + TILE - h - 3)))

        ring = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.rect(ring, (126, 240, 168, int(70 + 60 * pulse)),
                         (2, 2, TILE - 4, TILE - 4), 2, border_radius=10)
        screen.blit(ring, (int(x), int(y)))

    def gem_draw_info(self, r, c):
        """Returns (x, y, scale) for the gem at r,c."""
        x = BOARD_X + c * TILE
        y = BOARD_Y + r * TILE
        scale = 1.0

        if self.state in ("swap", "swapback") and self.pair and (r, c) in self.pair:
            a, b = self.pair
            other = b if (r, c) == a else a
            p = ease_in_out(self.t)
            if self.state == "swapback":
                p = 1 - p
            x += (other[1] - c) * TILE * p
            y += (other[0] - r) * TILE * p

        elif self.state == "clear" and (r, c) in self.matched:
            scale = max(0.0, 1.0 - ease_in_out(self.t))

        elif self.state == "fall" and (r, c) in self.falls:
            d = self.falls[(r, c)]
            y -= d * TILE * (1 - ease_out(self.t))

        elif self.state == "intro":
            # each column starts a little later, so the board lands left to right
            p = clamp01((self.t * INTRO_TIME - c * INTRO_STAGGER) / INTRO_FALL)
            y -= (ROWS + 2) * TILE * (1 - ease_out(p))

        elif self.state == "levelup":
            # old board peels away diagonally before the next one drops
            delay = (r + c) / (ROWS + COLS) * 0.30
            p = clamp01((self.t * self.levelup_pause() - delay) / 0.40)
            scale = 1.0 - ease_in_out(p)
            y -= 30 * p

        if (r, c) in self.pops:
            p = self.pops[(r, c)] / POP_TIME
            scale *= 1.0 + 0.45 * math.sin(p * math.pi)

        return x, y, scale

    def draw_bonus_tag(self, screen, x, y):
        """Green +3s badge, pinned to the bottom of a bonus gem."""
        pulse = 0.5 + 0.5 * math.sin(self.time * 4.5)
        label = self.font_small.render(f"+{int(BONUS_SECONDS)}s", True,
                                       (18, 32, 24))
        pad = 5
        w = label.get_width() + pad * 2
        h = label.get_height() + 2
        chip = translucent((w, h), (126, 240, 168, 200 + int(55 * pulse)),
                           None, h // 2)
        chip.blit(label, (pad, 1))
        screen.blit(chip, (int(x + (TILE - w) / 2), int(y + TILE - h - 3)))

        ring = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.rect(ring, (126, 240, 168, int(70 + 60 * pulse)),
                         (2, 2, TILE - 4, TILE - 4), 2, border_radius=10)
        screen.blit(ring, (int(x), int(y)))

    @staticmethod
    def bar(screen, x, y, w, h, frac, color):
        screen.blit(translucent((w, h), (255, 255, 255, 34), None, h // 2), (x, y))
        filled = int(w * clamp01(frac))
        if filled >= h:
            screen.blit(translucent((filled, h), color + (240,), None, h // 2),
                        (x, y))

    def draw_panel(self, screen):
        screen.blit(self.panel_bg, (PANEL_X, PANEL_Y))

        x = PANEL_X + 16
        width = PANEL_W - 32

        screen.blit(self.font_small.render("SCORE", True, DIM), (x, PANEL_Y + 26))
        screen.blit(self.font_score.render(f"{self.score:,}", True, TEXT),
                    (x, PANEL_Y + 46))

        if self.timed:
            low = self.time_left <= LOW_TIME
            pulse = 0.5 + 0.5 * math.sin(self.time * 6.0)
            color = ((255, int(90 + 60 * pulse), int(90 + 40 * pulse)) if low
                     else TEXT)
            secs = int(math.ceil(self.time_left))
            screen.blit(self.font_small.render("TIME", True, DIM),
                        (x, PANEL_Y + 112))
            screen.blit(self.font_score.render(f"{secs // 60}:{secs % 60:02d}",
                                               True, color), (x, PANEL_Y + 130))
            bar_color = (232, 96, 96) if low else (126, 216, 150)
            self.bar(screen, x, PANEL_Y + 176, width, 10,
                     self.time_left / TIMED_MAX, bar_color)
        else:
            screen.blit(self.font_big.render(f"LEVEL {self.level}", True, TEXT),
                        (x, PANEL_Y + 116))
            self.bar(screen, x, PANEL_Y + 150, width, 10,
                     self.level_progress(), GOLD)
            earned = max(0, self.score - self.level_floor)
            goal = self.font_small.render(
                f"{earned:,} / {self.level_target():,}", True, DIM)
            screen.blit(goal, (x, PANEL_Y + 166))

        mode = self.font_small.render(
            "TIMED" if self.timed else "ENDLESS", True, DIM)
        screen.blit(mode, (PANEL_X + PANEL_W - 16 - mode.get_width(),
                           PANEL_Y + 30))

        if self.note:
            self.wrapped(screen, self.note, x, PANEL_Y + 208, width, GOLD)

        track = self.audio.now_playing()
        if track:
            screen.blit(self.font_small.render("NOW PLAYING", True, DIM),
                        (x, PANEL_Y + PANEL_H - 250))
            self.wrapped(screen, track, x, PANEL_Y + PANEL_H - 232, width, DIM)

        for button in self.buttons:
            button.draw(screen, self.font)

    def wrapped(self, screen, text, x, y, width, color):
        """Panel is narrow, so long notes need to wrap rather than overflow."""
        words = text.split()
        line = ""
        for word in words:
            trial = f"{line} {word}".strip()
            if self.font_small.size(trial)[0] > width and line:
                screen.blit(self.font_small.render(line, True, color), (x, y))
                y += 17
                line = word
            else:
                line = trial
        if line:
            screen.blit(self.font_small.render(line, True, color), (x, y))

    def draw_hint(self, screen):
        if not self.hint or self.hint_left <= 0:
            return
        pulse = 0.5 + 0.5 * math.sin(self.time * 7.0)
        alpha = int(200 * min(1.0, self.hint_left / 0.6))
        for r, c in self.hint:
            ring = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            pygame.draw.rect(ring, HINT_COLOR + (alpha,),
                             (2, 2, TILE - 4, TILE - 4),
                             int(2 + 2 * pulse), border_radius=10)
            screen.blit(ring, (BOARD_X + c * TILE, BOARD_Y + r * TILE))

    def draw_go(self, screen):
        """Short GO! over the board as the gems finish landing.

        Optional: drop a go.png (or go/ frame folder, or go@N.png strip) into
        effects/ and that artwork is used instead of the text.
        """
        if self.go_left <= 0:
            return
        progress = 1.0 - self.go_left / GO_TIME
        scale = 1.0 + 0.55 * ease_out(min(1.0, progress * 3))
        alpha = int(255 * min(1.0, self.go_left / (GO_TIME * 0.45)))
        center = (BOARD_X + BOARD_W // 2, BOARD_Y + BOARD_H // 2)

        art = self.anims.get("go")
        if art is not None:
            index = min(int(progress * len(art.frames)), len(art.frames) - 1)
            image = art.frames[index]
        else:
            image = self.font_huge.render("GO!", True, (255, 255, 255))

        size = (max(1, int(image.get_width() * scale)),
                max(1, int(image.get_height() * scale)))
        image = pygame.transform.smoothscale(image, size)

        # The halo is the image's own shape blown up slightly, NOT a filled
        # rectangle - filling the bounding box is what produced a white block.
        halo = pygame.transform.smoothscale(
            image, (int(size[0] * 1.16), int(size[1] * 1.16)))
        halo.fill((90, 96, 110, 0), special_flags=pygame.BLEND_RGBA_ADD)
        halo.set_alpha(alpha // 3)
        screen.blit(halo, halo.get_rect(center=center))

        image.set_alpha(alpha)
        screen.blit(image, image.get_rect(center=center))

    def draw_over(self, screen):
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((8, 9, 13, 200))
        screen.blit(veil, (0, 0))

        box = self.over_rect()
        screen.blit(translucent(box.size, PANEL_FILL, PANEL_EDGE, 16),
                    box.topleft)

        lines = [(self.font_huge, "TIME UP", TEXT, 30),
                 (self.font_score, f"{self.score:,}", GOLD, 14),
                 (self.font_small, "POINTS", DIM, 22),
                 (self.font, f"reached level {self.level}", DIM, 0)]
        y = box.y + 34
        for font, text, color, gap in lines:
            image = font.render(text, True, color)
            screen.blit(image, (box.centerx - image.get_width() // 2, y))
            y += image.get_height() + gap

        for button in self.over_buttons:
            button.draw(screen, self.font)

    def draw_menu(self, screen):
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((8, 9, 13, 190))
        screen.blit(veil, (0, 0))

        box = self.menu_rect()
        screen.blit(self.menu_bg, box.topleft)

        title = self.font_big.render("MENU", True, TEXT)
        current = self.font_small.render(
            "MODE", True, DIM)
        screen.blit(current, (box.x + 30, box.y + 190))
        screen.blit(title, (box.x + 30, box.y + 26))
        hint = self.font_small.render("Esc or click outside to close", True, DIM)
        screen.blit(hint, (box.right - 30 - hint.get_width(), box.y + 31))

        for slider in self.sliders:
            slider.draw(screen, self.font, self.font_small,
                        dragging=self.dragging is slider)
        for button in self.menu_buttons:
            button.draw(screen, self.font)

    def draw_levelup(self, screen):
        """Shockwave and banner when the level bar fills."""
        p = ease_out(self.t)
        ring = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        center = (BOARD_X + BOARD_W // 2, BOARD_Y + BOARD_H // 2)
        pygame.draw.circle(ring, (255, 255, 255, int(170 * (1 - p))),
                           center, int(p * WIDTH * 0.85), 10)
        screen.blit(ring, (0, 0))
        banner = self.font_huge.render(f"LEVEL {self.level}", True, (255, 255, 255))
        banner.set_alpha(int(255 * (1 - abs(self.t * 2 - 1))))
        screen.blit(banner, (WIDTH // 2 - banner.get_width() // 2,
                             center[1] - banner.get_height() // 2))

    def draw(self, screen):
        photo = self.background_for_level()
        if photo is None:
            screen.fill(BG)
        else:
            screen.blit(photo, (0, 0))
        self.draw_panel(screen)

        screen.blit(self.board_bg, (BOARD_X, BOARD_Y))

        if self.sel is not None:
            r, c = self.sel
            pygame.draw.rect(screen, (255, 255, 255),
                             (BOARD_X + c * TILE, BOARD_Y + r * TILE, TILE, TILE), 3,
                             border_radius=6)

        clip = screen.get_clip()
        screen.set_clip(pygame.Rect(BOARD_X, BOARD_Y, COLS * TILE, ROWS * TILE))
        for r in range(ROWS):
            for c in range(COLS):
                gem = self.grid[r][c]
                if gem is None:
                    continue
                x, y, scale = self.gem_draw_info(r, c)
                sprite = self.sprite_for(gem)
                if gem.power != NORMAL and scale > 0.05:
                    self.draw_behind(screen, gem, x, y)
                if abs(scale - 1.0) > 0.001:
                    if scale <= 0.02:
                        continue
                    s = max(1, int(TILE * scale))
                    sprite = pygame.transform.smoothscale(sprite, (s, s))
                    x += (TILE - s) / 2
                    y += (TILE - s) / 2
                screen.blit(sprite, (int(x), int(y)))
                if gem.bonus:
                    self.draw_bonus_tag(screen, x, y)
        for puff in self.puffs:
            puff.draw(screen)
        for effect in self.effects:
            effect.draw(screen)
        for pop in self.time_pops:
            pop.draw(screen, self.font_big)
        screen.set_clip(clip)
        self.draw_hint(screen)

        if self.flash > 0:
            veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            veil.fill((255, 255, 255, int(90 * self.flash)))
            screen.blit(veil, (0, 0))

        if self.go_left > 0:
            self.draw_go(screen)
        if self.state == "levelup":
            self.draw_levelup(screen)
        if self.menu_open:
            self.draw_menu(screen)
        if self.over:
            self.draw_over(screen)


# --------------------------------------------------------------------------

def main():
    # This line has to come BEFORE pygame.init(). The default mixer buffer is
    # 4096 samples, which puts a very audible delay between clicking a gem and
    # hearing it pop. 512 makes the feedback feel instant.
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
    pygame.init()
    pygame.display.set_caption("Prismac")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    names = discover_gems()
    print(f"{len(names)} gems: " + ", ".join(names))
    sprites = build_sprites()
    missing = sprites[3]
    if missing:
        print("Could not load a face for: " + ", ".join(missing))
        print(f"Expected the PNGs in: {ASSET_DIR}")
        print("Playing with plain shapes for those in the meantime.\n")

    audio = Audio()
    audio.report()

    effects, effect_report = build_effects()
    for label, name in (("fire", FIRE_ASSET), ("smoke", SMOKE_ASSET)):
        found = load_still(name, TILE) is not None
        effect_report.append(
            f"   {label:<9} {'<-' if found else '!!'} "
            f"{name}.png" + ("" if found else " not found"))
    if effect_report:
        print("Effects loaded:")
        print("\n".join(effect_report))
        print()
    elif os.path.isdir(EFFECT_DIR):
        print(f"No animations found in {EFFECT_DIR}\n")

    backgrounds = load_backgrounds()
    if backgrounds:
        print(f"{len(backgrounds)} backgrounds loaded, one per level\n")
    elif os.path.isdir(BACKGROUND_DIR):
        print(f"No images found in {BACKGROUND_DIR}\n")

    game = Game(sprites, audio, effects, backgrounds)

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if game.menu_open:
                        game.close_menu()
                    else:
                        game.open_menu()
                elif e.key == pygame.K_r:
                    game.reset()
                elif e.key == pygame.K_m:
                    game.note = "muted" if audio.toggle_mute() else ""
                elif e.key in SECRET_SHUFFLE_KEYS:
                    game.secret_shuffle()
                elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    audio.nudge_volume(-VOLUME_STEP)
                elif e.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                    audio.nudge_volume(VOLUME_STEP)
                elif e.key == pygame.K_h:
                    game.show_hint()
                elif e.key == pygame.K_n:
                    game.shuffle_song()
                elif e.key == pygame.K_t:
                    game.set_mode(TIMED if game.mode == ENDLESS else ENDLESS)
            elif e.type == MUSIC_END:
                audio.next_track()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                game.on_down(e.pos)
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                game.on_up(e.pos)
            elif e.type == pygame.MOUSEMOTION:
                game.on_motion(e.pos)

        if game.wants_quit:
            pygame.quit()
            sys.exit()

        game.update(dt)
        game.draw(screen)
        pygame.display.flip()


if __name__ == "__main__":
    main()
