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

UI skin (optional):
    ui/             board, score, buttoninfotile, menubutton,
                    menubuttonhovered  (.png). Any missing file falls back
                    to the drawn-in-code look.

Chaos (optional):
    chaos/          bomb.png, rock.png, and optionally numbered gems used
                    only while Chaos mode is running

Backgrounds (optional):
    backgrounds/    1.png, 2.png ... one is shown per level, cycling round.
                    Scaled to cover the window and dimmed so gems stay readable.

Effects (optional):
    effects/        match, explode, hyper, levelup, go - as a folder of
                    frames, a sprite strip (name@8.png), or a .gif (Pillow).
                    smoke.png  puffs out when a flame gem detonates

Run:  python3 match3.py
"""

import colorsys
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

# 4:3 window with the score panel down the left-hand side.
WIDTH, HEIGHT = 960, 720
PANEL_W = 220
PANEL_X = MARGIN
PANEL_Y = 27
PANEL_H = HEIGHT - PANEL_Y * 2
BOARD_W = BOARD_H = COLS * TILE
BOARD_X = PANEL_X + PANEL_W + 26
BOARD_Y = (HEIGHT - BOARD_H) // 2

# Pixel type: rendered small with antialiasing off, then scaled up with
# nearest-neighbour so the edges stay hard. Drop a .ttf in fonts/ to override.
FONT_SCALE = 3

HINT_SECONDS = 4.0          # how long a hint stays lit

FPS = 60

# progression
LEVEL_BASE_TARGET = 1200   # points needed to clear level 1
LEVEL_GROWTH = 1.35        # each level needs this much more than the last

# timed mode
ENDLESS, TIMED, TITLE = "endless", "timed", "title"
TIMED_MUSIC_MODE = "timedmusic"   # an Extras run that is on the clock
SHAPES, EXTRAS, CHAOS = "shapes", "extras", "chaos"

# Extras: modifiers the player can stack. Each is (key, label, blurb).
EXTRA_DEFS = (
    ("zen",     "ZEN",            "no clock, no score"),
    ("mono",    "MONO",           "every gem the same colour"),
    ("boom",    "EXPLOSIVES",     "explosives and rainbows spawn freely"),
    ("lock",    "COLOUR LOCK",    "one colour scores, swaps every 10s"),
    ("chaos",   "CHAOS",          "bombs and rocks in the mix"),
)
LOCK_SECONDS = 10.0

# graphics toggles, both on by default and switchable from the title menu
SETTING_DEFS = (
    ("shake",     "CAMERA SHAKE",        "screen kick on big events"),
    ("particles", "BACKGROUND PARTICLES", "drifting motes behind the board"),
)
PARTICLE_COUNT = 46
DEV_CLICKS = 5             # taps on the logo to open developer mode

# rainbow gem detonation: a short charge, then the targets zapped one by one
RAINBOW_CHARGE = 0.55      # hypercube shaking before anything pops
RAINBOW_STEP = 0.055       # gap between each gem being taken out
RAINBOW_TAIL = 0.30        # a beat after the last one
RAINBOW_MAX = 1.9          # hard ceiling, so a board wipe cannot drag
ZAP_EVERY = 2              # play the zap sound on every Nth gem
EXTRA_ROW = 52             # tall enough for a label and its blurb

# The clock is frozen in all of these: the board is not playable, so running
# it down would be unfair. It restarts the moment GO! appears.
PAUSED_STATES = ("intro", "flyoff", "banner", "settling")
TIMED_SECONDS = 90.0        # 1:30 on the clock
TIMED_MAX = 120.0           # you can bank up to this much, never more
BONUS_SECONDS = 3.0         # what one +3 gem is worth
# Tuned by simulation: a bot playing flawlessly earns back roughly half the
# clock it burns, so good play stretches a run without making it endless.
BONUS_CHANCE = 0.028        # odds any refilled gem carries a bonus
BONUS_MIN = 2               # keep at least this many on the board
LOW_TIME = 12.0             # clock turns red and pulses below this

# Animation durations, in seconds. These are deliberately slower than a
# snappy-feeling first guess: below about 0.18s a swap reads as a jump cut
# rather than a movement, and the eye cannot follow which gems went where.
SWAP_TIME = 0.22
CLEAR_TIME = 0.30
FALL_TIME = 0.42
POP_TIME = 0.42          # the little "pop" when a special is born
INTRO_TIME = 1.45        # whole board raining in at the start of a level
INTRO_FALL = 0.70        # how long any single gem takes to land
INTRO_STAGGER = 0.075    # each column starts this much later than the last
INTRO_SOUND_EVERY = 2    # play GemFalling on every Nth column landing
# level transition: gems fly off, banner holds, new gems drop, then GO
FLYOFF_TIME = 1.15         # gems leaving the board
BANNER_IN = 0.85           # levelup.png at the centre, before the hold
BANNER_HOLD = 2.30         # how long it sits there
BANNER_OUT = 0.55
DROP_PAUSE = 0.30          # beat between the banner and the new gems
GO_PAUSE = 0.65            # beat between the gems landing and GO!
SHAKE_FLYOFF = 1.0
SHAKE_DECAY = 1.5
SHAKE_BOMB = 1.25          # a bomb going off
SHAKE_RAINBOW = 0.75        # the rainbow gem discharging
SHAKE_FLAME = 3.0          # an explosive gem detonating
SHAKE_MAX = 4.0

LEVELUP_MIN = 0.9        # floor for the level-up pause, even with no sound
LEVELUP_MAX = 3.0        # ceiling, so a long track cannot stall the game
GO_TIME = 0.85           # how long the GO! flash sits on screen

# scoring
POINTS_PER_GEM = 10
FLAME_BONUS = 60
HYPER_BONUS = 200
BOMB_BONUS = 80          # only awarded when bomb is detonated by explosion

# Bomb mechanics
# how often a refilled cell arrives as a rock or a bomb, in Chaos only
# Explosives mode spawn rates
BOOM_FLAME_CHANCE = 0.11
BOOM_HYPER_CHANCE = 0.030

CHAOS_ROCK_CHANCE = 0.055
CHAOS_BOMB_CHANCE = 0.030

BOMB_FUSE_MIN = 4
BOMB_FUSE_MAX = 6

# Cell types
CELL_GEM, CELL_ROCK, CELL_BOMB, CELL_EMPTY = 0, 1, 2, 3

def clamp01(t):
    return max(0.0, min(1.0, t))


# palette
# Navy chrome, drawn semi-transparently so a background photo reads through.
# Alpha is part of the colour here, so these are drawn onto SRCALPHA surfaces
# rather than straight to the display - pygame.draw ignores alpha otherwise.
BG = (18, 20, 30)                      # only seen if backgrounds/ is empty

# How much of the background photo shows through the chrome.
#   0.0 = solid panels    1.0 = barely-there glass
GLASS = 0.5

BG_DIM = 88                            # black scrim over the photo, 0-255


def _glass(rgb, base_alpha):
    return rgb + (int(base_alpha * (1.0 - 0.62 * clamp01(GLASS))),)


PANEL_FILL = _glass((34, 40, 66), 236)
PANEL_EDGE = (108, 128, 196, 130)
BOARD_FILL = _glass((26, 31, 54), 218)
CELL_HI = (140, 168, 255, 20)          # the lighter checker squares
BTN = _glass((48, 58, 96), 238)
BTN_HOVER = _glass((72, 88, 140), 248)
BTN_DOWN = _glass((34, 42, 72), 248)
TEXT = (232, 238, 255)
DIM = (146, 158, 196)
GOLD = (240, 202, 120)
HINT_COLOR = (120, 232, 224)
SKIN_TEXT = TEXT
SKIN_SHADOW = (0, 0, 0, 120)

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
UI_DIR = asset_folder("ui")
CHAOS_DIR = asset_folder("chaos")
TITLE_DIR = asset_folder("title")

# title screen
TITLE_BOB = 9.0            # pixels the logo drifts up and down
FONT_DIR = asset_folder("fonts")

# Skin art. Any missing file falls back to the drawn-in-code look, so these
# can be dropped in one at a time.
UI_IMAGES = ("board", "score", "buttoninfotile", "menubutton",
             "menubuttonhovered", "title")

CREDITS = "Created by Ty Fukushima and Claude Code"

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
    "twomatch": ("TwoMatch", "Match4/5", "Match45"),
    "flyoff": ("FlyingGem", "FlyGem", "GemFly"),
    "flamemade": ("ExplodeGemCreated", "FlameGemCreated", "PowerGem"),
    "hypermade": ("RainbowGemCreated", "HyperGemCreated"),
    "rainbowcharge": ("RainbowGem", "RainbowCharge"),
    "rainbowzap": ("RainbowGemExplosion", "RainbowZap"),
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
# "levelup" and "smoke" are stills, loaded separately - listing them
# here would make the strip loader slice them into frames.
EFFECT_NAMES = ("match", "explode", "hyper", "go")

# Single stills that are decorated rather than played as animations.
# flame gem shine
GLINT_PERIOD = 2.6         # seconds between one gem's glints
GLINT_SWEEP = 0.30         # fraction of that spent actually sweeping
SMOKE_ASSET = "smoke"      # puffs outward when a flame gem detonates
BANNER_ASSET = "levelup"   # one still image, never sliced as a strip
# Effects listed here are drawn additively, which is what makes fire and
# sparks read as light rather than as stickers.
# "go" is deliberately NOT additive - it is a readable overlay, not a light.
EFFECT_ADDITIVE = {"match", "explode", "hyper"}

# Hidden reshuffle. F1 is the intended one, but macOS eats F1 unless you tick
# "Use F1, F2, etc. as standard function keys" (or hold Fn), so backslash is
# wired up as a fallback that always reaches the game.
SECRET_SHUFFLE_KEYS = (pygame.K_F1, pygame.K_BACKSLASH)

# gems/7.png is reserved for the hypercube, so it is kept out of the matchable
# set. Rename or clear this if you ever want a seventh colour instead.
HYPERCUBE_ASSET = "7"
BOMB_ASSET = "bomb"
ROCK_ASSET = "rock"
# chaos/ holds the pieces only Chaos mode uses - bomb.png, rock.png, and
# optionally its own numbered gems. Keeping them out of gems/ means they can
# never leak into the normal modes.

# Images in gems/ that are NOT playable colours. Anything listed here is
# loaded for its own purpose and kept out of the matchable set - without
# this, dropping bomb.png into gems/ silently adds an eighth gem colour to
# every mode.
RESERVED_GEMS = (HYPERCUBE_ASSET, BOMB_ASSET, ROCK_ASSET)

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
    reserved = {_norm(r) for r in RESERVED_GEMS}
    names = [n for n in names if _norm(n) not in reserved]
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
    mode possibly a +3 second bonus. Now also handles rocks, bombs, and empty cells."""

    __slots__ = ("kind", "power", "bonus", "cell_type", "fuse")

    def __init__(self, kind=0, power=NORMAL, bonus=False, cell_type=CELL_GEM, fuse=0):
        self.kind = kind
        self.power = power
        self.bonus = bonus
        self.cell_type = cell_type
        self.fuse = fuse  # bomb fuse countdown (0 = no bomb, else 4-6 moves remaining)

    def __repr__(self):
        type_str = {CELL_GEM: "Gem", CELL_ROCK: "Rock", CELL_BOMB: "Bomb", CELL_EMPTY: "Empty"}.get(self.cell_type, "?")
        if self.cell_type == CELL_BOMB:
            return f"{type_str}(fuse={self.fuse})"
        tag = ", +3s" if self.bonus else ""
        return f"{type_str}({self.kind}, {self.power}{tag})"

    @staticmethod
    def rock():
        return Gem(cell_type=CELL_ROCK)

    @staticmethod
    def bomb(fuse=None):
        if fuse is None:
            fuse = random.randint(BOMB_FUSE_MIN, BOMB_FUSE_MAX)
        return Gem(cell_type=CELL_BOMB, fuse=fuse)

    @staticmethod
    def empty():
        return Gem(cell_type=CELL_EMPTY)


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

    A flame gem is the same artwork with a warm lift, so the state reads even
    on a single frame. The glow and the travelling glint are drawn live.
    """
    art = fallback_gem(shape, color) if face is None \
        else fit_in(face, TILE - GEM_PAD * 2)

    if not hot:
        return centred(art)

    warmed = art.copy()
    tint = pygame.Surface(art.get_size(), pygame.SRCALPHA)
    tint.fill((30, 11, 0))
    warmed.blit(tint, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    return centred(warmed)


def bake_halo(sprite, color, spread=1.34, steps=5):
    """A soft glow shaped like the artwork itself.

    Built by stacking scaled, tinted copies of the sprite's own silhouette,
    so it hugs whatever outline the gem actually has rather than being a
    circle sitting behind a non-circular gem.
    """
    size = int(TILE * spread)
    halo = pygame.Surface((size, size), pygame.SRCALPHA)
    for i in range(steps, 0, -1):
        f = i / steps
        scale = 1.0 + (spread - 1.0) * f
        ring = pygame.transform.smoothscale(
            sprite, (max(1, int(TILE * scale)), max(1, int(TILE * scale))))
        wash = pygame.Surface(ring.get_size(), pygame.SRCALPHA)
        wash.fill(color + (255,))
        ring.blit(wash, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        ring.fill((255, 255, 255, int(38 * (1.0 - f) + 8)),
                  special_flags=pygame.BLEND_RGBA_MULT)
        halo.blit(ring, ring.get_rect(center=(size // 2, size // 2)),
                  special_flags=pygame.BLEND_RGBA_ADD)
    return halo


def bake_glints(sprite, count=14, color=(255, 246, 214)):
    """Pre-render a specular streak sweeping across the gem.

    Each frame is a diagonal bright band masked to the sprite's own alpha, so
    the shine only ever appears on the gem and follows its real shape.
    """
    w, h = sprite.get_size()
    mask = pygame.mask.from_surface(sprite)
    if mask.count() == 0:
        return []
    frames = []
    band = max(6, int(w * 0.24))
    travel = w + h + band * 2
    for i in range(count):
        pos = -band + (travel * i / (count - 1)) if count > 1 else 0
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        for k in range(band):
            # triangular falloff gives a soft-edged streak
            edge = 1.0 - abs(k - band / 2) / (band / 2)
            if edge <= 0:
                continue
            alpha = int(210 * edge ** 1.6)
            x = pos + k
            pygame.draw.line(layer, color + (alpha,),
                             (x, -1), (x - h, h + 1), 2)
        shaped = mask.to_surface(setcolor=(255, 255, 255, 255),
                                 unsetcolor=(0, 0, 0, 0))
        shaped.blit(layer, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        frames.append(shaped)
    return frames


def split_clusters(sheet, minimum=200):
    """Cut a sheet into its separate blobs.

    smoke.png is several puffs on one transparent sheet; slicing them apart
    gives a set of distinct sprites to draw from, which looks far better than
    scaling one image over and over.
    """
    try:
        mask = pygame.mask.from_surface(sheet)
        parts = mask.connected_components(minimum)
    except (AttributeError, pygame.error):
        return [sheet]
    pieces = []
    for part in parts:
        rect = part.get_bounding_rects()
        if not rect:
            continue
        box = rect[0]
        for extra in rect[1:]:
            box = box.union(extra)
        if box.width < 4 or box.height < 4:
            continue
        pieces.append(sheet.subsurface(box).copy())
    return pieces or [sheet]


def load_still(name, size=None):
    """One decorative PNG from effects/.

    size=None keeps the artwork at its native size, which matters for sheets
    that get sliced up afterwards - squashing them first would distort the
    pieces.
    """
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
            if size is None:
                return image
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
    """A gem that can participate in normal color-matching.
    Hypercubes are colorless and never match. Rocks, bombs, and empties never match."""
    if cell is None:
        return False
    if cell.cell_type != CELL_GEM:
        return False
    return cell.power != HYPER


def is_gem(cell):
    """A regular gem (not rock, bomb, or empty)."""
    return cell is not None and cell.cell_type == CELL_GEM


def is_clear_cell(cell):
    """Cells that can be cleared by explosions (gems, bombs, but NOT rocks)."""
    return cell is not None and cell.cell_type in (CELL_GEM, CELL_BOMB)


def new_grid(bonuses=False, chaos=False, shapes=False):
    """Random board with no pre-existing matches, guaranteed to have a move.
    
    In Chaos mode, randomly place rocks and bombs.
    In Shapes mode, create an irregular board with holes (EMPTY cells).
    """
    if shapes:
        return new_shapes_grid(bonuses)
    
    while True:
        g = [[None] * COLS for _ in range(ROWS)]
        for r in range(ROWS):
            for c in range(COLS):
                banned = set()
                if c >= 2 and is_gem(g[r][c - 1]) and is_gem(g[r][c - 2]):
                    if g[r][c - 1].kind == g[r][c - 2].kind:
                        banned.add(g[r][c - 1].kind)
                if r >= 2 and is_gem(g[r - 1][c]) and is_gem(g[r - 2][c]):
                    if g[r - 1][c].kind == g[r - 2][c].kind:
                        banned.add(g[r - 1][c].kind)
                choices = [t for t in range(N_TYPES) if t not in banned]
                g[r][c] = Gem(random.choice(choices),
                              bonus=bonuses and random.random() < BONUS_CHANCE)
        
        if chaos:
            add_chaos_elements(g)
        
        if not has_move(g):
            continue
        
        if bonuses:
            cells = [(r, c) for r in range(ROWS) for c in range(COLS) if is_gem(g[r][c])]
            random.shuffle(cells)
            while count_bonus(g) < BONUS_MIN and cells:
                r, c = cells.pop()
                g[r][c].bonus = True
        return g


def add_chaos_elements(g):
    """Randomly place rocks and bombs in an existing grid."""
    cells = [(r, c) for r in range(ROWS) for c in range(COLS)]
    random.shuffle(cells)
    
    # Place roughly 10-15% rocks and bombs combined
    num_special = random.randint(max(1, len(cells) // 10), max(2, len(cells) // 7))
    for _ in range(num_special):
        if not cells:
            break
        r, c = cells.pop()
        if random.random() < 0.6:
            g[r][c] = Gem.rock()
        else:
            g[r][c] = Gem.bomb()


SHAPE_MASKS = (
    "diamond", "cross", "hourglass", "ring", "arrow", "butterfly",
)


def shape_mask(name):
    """Which cells are playable for a given silhouette.

    Returns a set of (row, col). Everything outside it becomes a hole, which
    is what actually makes a Shapes board look like a shape.
    """
    cr, cc = (ROWS - 1) / 2, (COLS - 1) / 2
    keep = set()
    for r in range(ROWS):
        for c in range(COLS):
            dr, dc = r - cr, c - cc
            if name == "diamond":
                ok = abs(dr) + abs(dc) <= max(ROWS, COLS) / 2 + 0.5
            elif name == "cross":
                ok = abs(dr) <= 1.5 or abs(dc) <= 1.5
            elif name == "hourglass":
                ok = abs(dc) <= abs(dr) + 1.2
            elif name == "ring":
                d = math.hypot(dr, dc)
                ok = 1.6 <= d <= cr + 0.6
            elif name == "arrow":
                ok = abs(dc) <= (cr - dr) / 1.4 + 0.5
            else:                                   # butterfly
                ok = abs(dr) <= abs(dc) + 1.2
            if ok:
                keep.add((r, c))
    # never leave so little board that the game cannot be played
    return keep if len(keep) >= ROWS * COLS * 0.45 else {
        (r, c) for r in range(ROWS) for c in range(COLS)}


def new_shapes_grid(bonuses=False, mask=None):
    """An irregular board: a silhouette of playable cells, holes elsewhere."""
    if mask is None:
        mask = shape_mask(random.choice(SHAPE_MASKS))
    while True:
        g = [[None] * COLS for _ in range(ROWS)]
        for r in range(ROWS):
            for c in range(COLS):
                if (r, c) not in mask:
                    g[r][c] = Gem.empty()
                    continue
                banned = set()
                if c >= 2 and is_gem(g[r][c - 1]) and is_gem(g[r][c - 2]):
                    if g[r][c - 1].kind == g[r][c - 2].kind:
                        banned.add(g[r][c - 1].kind)
                if r >= 2 and is_gem(g[r - 1][c]) and is_gem(g[r - 2][c]):
                    if g[r - 1][c].kind == g[r - 2][c].kind:
                        banned.add(g[r - 1][c].kind)
                choices = [t for t in range(N_TYPES) if t not in banned]
                g[r][c] = Gem(random.choice(choices),
                              bonus=bonuses and random.random() < BONUS_CHANCE)
        if not find_runs(g) and has_move(g):
            return g


def find_runs(g):
    """Every straight run of 3 or more same-colored gems.
    
    Ignores rocks, bombs, and empty cells - they break the run.
    """
    runs = []
    
    # Horizontal
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
    
    # Vertical
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
    """True if some adjacent swap would do something.
    
    Hypercubes can always be swapped. For normal gems, try all adjacent swaps.
    Rocks and bombs can be involved in swaps (they're adjacent to gems) but
    they themselves don't create matches.
    """
    # Hypercubes always produce a result
    for r in range(ROWS):
        for c in range(COLS):
            if g[r][c] is not None and g[r][c].cell_type == CELL_GEM and g[r][c].power == HYPER:
                for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    r2, c2 = r + dr, c + dc
                    if in_bounds(r2, c2) and g[r2][c2] is not None:
                        return True
    
    # Try every adjacent pair
    for r in range(ROWS):
        for c in range(COLS):
            for dr, dc in ((0, 1), (1, 0)):
                r2, c2 = r + dr, c + dc
                if not in_bounds(r2, c2):
                    continue
                # Try the swap
                g[r][c], g[r2][c2] = g[r2][c2], g[r][c]
                scores = bool(find_runs(g))
                g[r][c], g[r2][c2] = g[r2][c2], g[r][c]
                if scores:
                    return True
    
    return False


def detonate(g, cells, score_dict=None):
    """Expand a clear set to include chained explosions.
    
    Flame gems and bombs explode outward, triggering other explosions.
    Bombs only contribute to score if triggered by another explosion.
    
    If score_dict is provided, marks which explosions are "triggered" (for bomb scoring).
    """
    cleared = set(cells)
    queue = []
    
    # Start with flame gems and bombs
    for rc in cells:
        if not in_bounds(rc[0], rc[1]):
            continue
        gem = g[rc[0]][rc[1]]
        if gem is None:
            continue
        if gem.cell_type == CELL_GEM and gem.power == FLAME:
            queue.append((rc, True))  # Flame gem, mark as direct
        elif gem.cell_type == CELL_BOMB:
            queue.append((rc, False))  # Bomb, mark as triggered
    
    fired = set()
    while queue:
        (r, c), is_flame = queue.pop()
        if (r, c) in fired:
            continue
        fired.add((r, c))
        
        # Explode: hit 8 surrounding cells
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                rr, cc = r + dr, c + dc
                if not in_bounds(rr, cc) or g[rr][cc] is None:
                    continue
                
                cleared.add((rr, cc))
                
                # Queue up secondary explosions if this is a flame or bomb
                gem_hit = g[rr][cc]
                if gem_hit.cell_type == CELL_GEM and gem_hit.power == FLAME:
                    queue.append(((rr, cc), True))
                elif gem_hit.cell_type == CELL_BOMB and (rr, cc) not in fired:
                    queue.append(((rr, cc), False))
                    # Bomb was triggered, mark for scoring if score_dict provided
                    if score_dict is not None:
                        score_dict[(rr, cc)] = True
    
    return cleared


def plan_clear(g, runs, origin=(), score_dict=None):
    """Work out what a set of runs destroys.

    origin is the cells the player just moved; a special prefers to appear
    under the player's own gem, which is what makes placement feel deliberate
    rather than random.

    Returns (cells_to_clear, {cell: power}).
    
    Rocks NEVER clear (even from explosions).
    Empty cells are never cleared either.
    """
    if score_dict is None:
        score_dict = {}
    
    base = set()
    spawns = {}

    for run in runs:
        base.update(run)
        if len(run) < 4:
            continue
        power = HYPER if len(run) >= 5 else FLAME

        # A spawn cell is excluded from the clear, so it must not be a gem
        # that already carries a power - otherwise matching your own flame
        # gem into a run of 4 quietly upgrades it instead of detonating it.
        def plain(rc):
            gem = g[rc[0]][rc[1]]
            return gem is not None and gem.cell_type == CELL_GEM and gem.power == NORMAL

        at = next((rc for rc in origin if rc in run and plain(rc)), None)
        if at is None:
            middle = sorted(run, key=lambda rc: abs(run.index(rc) - len(run) // 2))
            at = next((rc for rc in middle if plain(rc)), None)
        if at is None:
            at = next((rc for rc in origin if rc in run), run[len(run) // 2])
        if at is not None and spawns.get(at, NORMAL) < power:
            spawns[at] = power

    clear = base - set(spawns)
    clear = detonate(g, clear, score_dict)
    clear -= set(spawns)          # a new special survives its own blast
    
    # Remove rocks and empty cells from clear set (they never clear)
    clear = {rc for rc in clear if is_clear_cell(g[rc[0]][rc[1]])}
    
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
    """Pick a swap that would actually score.
    
    Random among all valid moves, so asking twice suggests somewhere different.
    """
    # Hypercubes always work
    for r in range(ROWS):
        for c in range(COLS):
            if g[r][c] is not None and g[r][c].cell_type == CELL_GEM and g[r][c].power == HYPER:
                for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    if in_bounds(r + dr, c + dc) and g[r + dr][c + dc] is not None:
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


def fresh_gem(bonuses=False, boom=False):
    """One newly spawned gem. In Explosives mode it may arrive already
    charged - that is the only way an explosive appears without a match."""
    gem = Gem(random.randrange(N_TYPES),
              bonus=bonuses and random.random() < BONUS_CHANCE)
    if boom:
        roll = random.random()
        if roll < BOOM_HYPER_CHANCE:
            gem.power = HYPER
            gem.kind = HYPER_KIND
            gem.bonus = False
        elif roll < BOOM_HYPER_CHANCE + BOOM_FLAME_CHANCE:
            gem.power = FLAME
    return gem


def collapse(g, bonuses=False, chaos=False, shapes=False, boom=False,
             mask=None):
    """Drop gems into holes and refill the top.
    
    In normal mode, gems fall straight down to the bottom.
    Rocks also fall. Bombs fall with their fuse ticking down.
    Empty cells stay empty (holes in the board).

    With bonuses=True (timed mode) some new gems arrive carrying +3 seconds.
    A floor of BONUS_MIN is topped up so the board never runs dry of them.

    Returns {(row, col): rows_fallen} so the drop can be animated.
    
    Also decrements bomb fuses each turn.
    """
    # An irregular board needs the hole-aware collapse, or its shape is
    # scrubbed flat the first time anything falls.
    if shapes or mask:
        return collapse_shapes(g, bonuses, boom, mask)

    falls = {}
    # NOTE: bomb fuses are NOT ticked here. settle() does it once per player
    # move, so doing it per collapse would burn several moves off a bomb for
    # a single swap that cascades.
    for c in range(COLS):
        write = ROWS - 1
        for r in range(ROWS - 1, -1, -1):
            if g[r][c] is not None and g[r][c].cell_type != CELL_EMPTY:
                if write != r:
                    g[write][c] = g[r][c]
                    g[r][c] = None
                    falls[(write, c)] = write - r
                write -= 1
        
        # Refill from top
        n_new = write + 1
        for r in range(write, -1, -1):
            # In Chaos, new rocks and bombs keep arriving with the gems -
            # otherwise the board is scrubbed clean after the first clear.
            roll = random.random() if chaos else 1.0
            if roll < CHAOS_ROCK_CHANCE:
                g[r][c] = Gem.rock()
            elif roll < CHAOS_ROCK_CHANCE + CHAOS_BOMB_CHANCE:
                g[r][c] = Gem.bomb(random.randint(BOMB_FUSE_MIN, BOMB_FUSE_MAX))
            else:
                g[r][c] = fresh_gem(bonuses, boom)
            falls[(r, c)] = n_new  # falls in from above the board

    if bonuses:
        fresh = [rc for rc in falls if g[rc[0]][rc[1]].cell_type == CELL_GEM and not g[rc[0]][rc[1]].bonus]
        random.shuffle(fresh)
        while count_bonus(g) < BONUS_MIN and fresh:
            r, c = fresh.pop()
            g[r][c].bonus = True
    
    return falls


def collapse_shapes(g, bonuses=False, boom=False, mask=None):
    """Collapse with support for irregular boards (holes/empty cells).
    
    Gems and bombs fall down, passing through empty cells.
    Rocks also fall.
    Empty cells block gems from crossing, like invisible platforms.
    """
    falls = {}
    # NOTE: bomb fuses are NOT ticked here. settle() does it once per player
    # move, so doing it per collapse would burn several moves off a bomb for
    # a single swap that cascades.
    for c in range(COLS):
        # Collect all non-empty cells in this column
        filled = []
        holes = []
        for r in range(ROWS):
            if g[r][c] is None:
                pass
            elif g[r][c].cell_type == CELL_EMPTY:
                holes.append(r)
            else:
                filled.append((r, g[r][c]))
        
        # Clear the column
        for r in range(ROWS):
            g[r][c] = None
        
        # Reposition holes
        for r in holes:
            g[r][c] = Gem.empty()
        
        # Drop filled cells, respecting hole positions
        write = ROWS - 1
        for r_src, cell in reversed(filled):
            # Find the next available spot going down
            while write >= 0 and g[write][c] is not None:
                write -= 1
            if write >= 0:
                g[write][c] = cell
                if write != r_src:
                    falls[(write, c)] = write - r_src
                write -= 1
        
        # Refill top
        for r in range(ROWS):
            if g[r][c] is None and not any(h == r for h in holes):
                g[r][c] = fresh_gem(bonuses, boom)
                falls[(r, c)] = 1

    if bonuses:
        fresh = [rc for rc in falls if g[rc[0]][rc[1]].cell_type == CELL_GEM and not g[rc[0]][rc[1]].bonus]
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
    """Quintic. Decelerates harder at the end than a cubic, which is what
    makes a falling gem look like it settles rather than stops."""
    return 1 - (1 - t) ** 5


def ease_in_out(t):
    """Smootherstep: zero velocity AND zero acceleration at both ends, so a
    swap has no visible kick when it starts or stops."""
    return t * t * t * (t * (t * 6 - 15) + 10)


def ease_back(t, overshoot=1.5):
    """Overshoots slightly then settles. Used for gems landing."""
    t -= 1.0
    return t * t * ((overshoot + 1) * t + overshoot) + 1.0


def ease_bounce(t):
    """A small secondary hop, for the end of a long drop."""
    if t < 0.72:
        return 1 - (1 - t / 0.72) ** 2 * 1.0
    p = (t - 0.72) / 0.28
    return 1.0 - 0.055 * math.sin(p * math.pi)


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


def load_ui_skin():
    """Artwork from ui/. Anything absent just falls back to drawn shapes."""
    skin = {}
    if not os.path.isdir(UI_DIR):
        return skin
    index = {}
    for filename in os.listdir(UI_DIR):
        stem, ext = os.path.splitext(filename)
        if ext.lower() in (".png", ".webp"):
            index[_norm(stem)] = os.path.join(UI_DIR, filename)
    for name in UI_IMAGES:
        path = index.get(_norm(name))
        if path is None:
            continue
        try:
            skin[name] = pygame.image.load(path).convert_alpha()
        except pygame.error as exc:
            print(f"Could not load ui/{name}: {exc}")
    return skin


GLYPH_W, GLYPH_H = 5, 7

_GLYPHS = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ",": ("00000", "00000", "00000", "00000", "01100", "01100", "01000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "'": ("00100", "00100", "00000", "00000", "00000", "00000", "00000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "01011", "10011"),
    "x": ("00000", "00000", "10001", "01010", "00100", "01010", "10001"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
}
_MISSING = ("11111", "10001", "10001", "10001", "10001", "10001", "11111")



def load_font(scale, bold=False):
    """A pixel .ttf in fonts/ wins if you drop one in; otherwise the built-in
    bitmap face at `scale` device pixels per font pixel."""
    if os.path.isdir(FONT_DIR):
        for filename in sorted(os.listdir(FONT_DIR)):
            if os.path.splitext(filename)[1].lower() in (".ttf", ".otf"):
                try:
                    return pygame.font.Font(os.path.join(FONT_DIR, filename),
                                            scale * GLYPH_H)
                except pygame.error:
                    break
    return PixelFont(scale, bold=bold)


class PixelFont:
    """A real 5x7 bitmap face - the glyphs above are literal pixel maps.

    Scaled by whole numbers only, which is the whole point: fractional
    scaling is what makes pixel type look mushy. Drop a pixel .ttf (Press
    Start 2P, m5x7, ...) into fonts/ and that is used instead.
    """

    def __init__(self, scale, tracking=1, bold=False):
        self.scale = max(1, int(scale))
        self.tracking = tracking
        self.bold = bold
        self._cache = {}

    def smaller(self):
        """Next scale down, or self if already at 1:1."""
        if self.scale <= 1:
            return self
        return PixelFont(self.scale - 1, self.tracking, self.bold)

    def get_height(self):
        return GLYPH_H * self.scale

    def _width(self, text):
        if not text:
            return 0
        step = (GLYPH_W + self.tracking) * self.scale
        return step * len(text) - self.tracking * self.scale

    def size(self, text):
        return (self._width(text), self.get_height())

    def render(self, text, _aa=False, color=(255, 255, 255)):
        key = (text, tuple(color))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        scale = self.scale
        surface = pygame.Surface((max(1, self._width(text)), self.get_height()),
                                 pygame.SRCALPHA)
        step = (GLYPH_W + self.tracking) * scale
        for index, char in enumerate(text):
            rows = _GLYPHS.get(char) or _GLYPHS.get(char.upper()) or _MISSING
            ox = index * step
            for y, row in enumerate(rows):
                run = 0
                for x, bit in enumerate(row + "0"):
                    if bit == "1":
                        run += 1
                        continue
                    if run:
                        pygame.draw.rect(surface, color,
                                         (ox + (x - run) * scale, y * scale,
                                          run * scale, scale))
                        run = 0
        if self.bold:
            thicker = surface.copy()
            thicker.blit(surface, (scale, 0))
            surface = thicker
        if len(self._cache) > 400:
            self._cache.clear()
        self._cache[key] = surface
        return surface



def engraved(font, text, color=SKIN_TEXT):
    """Text with a hard offset shadow - the classic pixel-game treatment."""
    body = font.render(text, True, color)
    drop = max(2, FONT_SCALE)
    out = pygame.Surface((body.get_width() + drop, body.get_height() + drop),
                         pygame.SRCALPHA)
    shadow = font.render(text, True, (0, 0, 0))
    shadow.set_alpha(150)
    out.blit(shadow, (drop, drop))
    out.blit(body, (0, 0))
    return out


def stretch(surface, size):
    """Plain scale to an exact box. Fine for these panels; if you ever want
    corners that do not distort, this is where 9-slicing would go."""
    return pygame.transform.smoothscale(surface, (max(1, size[0]), max(1, size[1])))


def fallback_background():
    """A generated backdrop, used when backgrounds/ is empty.

    Without this the chrome sits on a flat fill and reads as solid even though
    its alpha is unchanged - which looks exactly like "transparency is broken
    on this machine". A gradient makes the glass visible everywhere.
    """
    canvas = pygame.Surface((WIDTH, HEIGHT))
    top, bottom = (14, 18, 38), (34, 26, 58)
    for y in range(HEIGHT):
        f = y / HEIGHT
        canvas.fill(tuple(int(a + (b - a) * f) for a, b in zip(top, bottom)),
                    (0, y, WIDTH, 1))
    glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for i, radius in enumerate((420, 300, 190)):
        pygame.draw.circle(glow, (70, 90, 190, 16 + i * 6),
                           (int(WIDTH * 0.72), int(HEIGHT * 0.30)), radius)
    canvas.blit(glow, (0, 0))
    return canvas


def describe_assets():
    """Print exactly which folders were found and what is in them.

    This exists because "it looks different on my other machine" is nearly
    always a missing folder, and guessing at it wastes everyone's time.
    """
    print(f"running from : {app_dir()}")
    if getattr(sys, "frozen", False):
        print(f"bundled in   : {bundle_dir()}")
    for label, folder, exts in (
            ("gems", ASSET_DIR, (".png", ".jpg", ".jpeg", ".webp")),
            ("soundeffects", SFX_DIR, AUDIO_EXTS),
            ("music", MUSIC_DIR, AUDIO_EXTS),
            ("backgrounds", BACKGROUND_DIR, (".png", ".jpg", ".jpeg", ".webp")),
            ("effects", EFFECT_DIR, (".png", ".webp", ".gif")),
            ("chaos", CHAOS_DIR, (".png", ".jpg", ".jpeg", ".webp")),
            ("fonts", FONT_DIR, (".ttf", ".otf"))):
        if not os.path.isdir(folder):
            print(f"  {label:<13} MISSING   (looked in {folder})")
            continue
        n = sum(1 for f in os.listdir(folder)
                if os.path.splitext(f)[1].lower() in exts)
        print(f"  {label:<13} {n:3d} file(s)")
    print()


def load_title_art():
    """The logo from title/. Kept at native size and scaled to the window."""
    if not os.path.isdir(TITLE_DIR):
        return None
    for filename in sorted(os.listdir(TITLE_DIR)):
        stem, ext = os.path.splitext(filename)
        if ext.lower() not in (".png", ".webp"):
            continue
        if "background" in _norm(stem):       # that one is the backdrop
            continue
        try:
            art = pygame.image.load(
                os.path.join(TITLE_DIR, filename)).convert_alpha()
        except pygame.error:
            continue
        target = int(WIDTH * 0.74)
        w, h = art.get_size()
        return pygame.transform.smoothscale(
            art, (target, max(1, int(h * target / w))))
    return None


def load_title_background():
    """title/TitleBackground.* - the backdrop behind the logo."""
    if not os.path.isdir(TITLE_DIR):
        return None
    for filename in sorted(os.listdir(TITLE_DIR)):
        stem, ext = os.path.splitext(filename)
        if ext.lower() not in (".png", ".webp", ".jpg", ".jpeg"):
            continue
        if "background" not in _norm(stem):
            continue
        try:
            art = pygame.image.load(os.path.join(TITLE_DIR, filename)).convert()
        except pygame.error:
            return None
        w, h = art.get_size()
        scale = max(WIDTH / w, HEIGHT / h)          # cover, never squashed
        art = pygame.transform.smoothscale(
            art, (int(w * scale + 0.5), int(h * scale + 0.5)))
        canvas = pygame.Surface((WIDTH, HEIGHT))
        canvas.blit(art, ((WIDTH - art.get_width()) // 2,
                          (HEIGHT - art.get_height()) // 2))
        return canvas
    return None


def load_chaos_assets():
    """Everything in chaos/, keyed by normalised filename.

    Returns {"bomb": Surface, "rock": Surface, "gems": [Surface, ...]} where
    "gems" is any numbered artwork that should replace the normal set while
    Chaos is running. All of it is optional.
    """
    found = {"bomb": None, "rock": None, "gems": []}
    if not os.path.isdir(CHAOS_DIR):
        return found
    numbered = []
    for filename in sorted(os.listdir(CHAOS_DIR)):
        stem, ext = os.path.splitext(filename)
        if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        try:
            art = pygame.image.load(
                os.path.join(CHAOS_DIR, filename)).convert_alpha()
        except pygame.error:
            continue
        key = _norm(stem)
        if key == _norm(BOMB_ASSET):
            found["bomb"] = centred(fit_in(art, TILE - GEM_PAD * 2))
        elif key == _norm(ROCK_ASSET):
            found["rock"] = centred(fit_in(art, TILE - GEM_PAD * 2))
        elif stem.isdigit():
            numbered.append((int(stem), art))
    numbered.sort()
    found["gems"] = [centred(fit_in(art, TILE - GEM_PAD * 2))
                     for _, art in numbered]
    return found


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
        self.title_playlist = []
        self.mode = ENDLESS
        self.playlist_started = False
        self.chosen = None          # a track the player picked by hand
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
            if ext.lower() not in AUDIO_EXTS:
                continue
            key = _norm(stem)
            found.setdefault(key, path)
            # Also index the name with any trailing take/version number
            # stripped, so "Whirlpool_1.wav" still answers to "Whirlpool"
            # and "Explode 2.ogg" still answers to "Explode". Registered
            # second, so an exact match always wins.
            bare = key.rstrip("0123456789")
            if bare and bare != key:
                found.setdefault(bare, path)
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

        title_index = self.index_folder(TITLE_DIR)
        self.title_playlist = [title_index[k] for k in sorted(title_index)]

        timed_dir = os.path.join(MUSIC_DIR, TIMED_MUSIC_SUBDIR)
        timed_index = self.index_folder(timed_dir)
        self.timed_playlist = [timed_index[key] for key in sorted(timed_index)]
        random.shuffle(self.timed_playlist)

        if not self.playlist:
            self.missing.append("music (nothing in music/)")
        if not self.title_playlist:
            self.missing.append("title music (nothing in title/)")
        if not self.timed_playlist:
            self.missing.append(f"timed music (nothing in {TIMED_MUSIC_SUBDIR}/)")
        if not self.playlist and not self.timed_playlist:
            return

        pygame.mixer.music.set_volume(self.music_volume)
        pygame.mixer.music.set_endevent(MUSIC_END)
        self.use_playlist(TITLE)

    def active_list(self):
        """Falls back to the main playlist if a set is empty, so the game
        never goes silent."""
        if self.mode == TITLE and self.title_playlist:
            return self.title_playlist
        if self.mode in (TIMED, TIMED_MUSIC_MODE) and self.timed_playlist:
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

    def track_names(self):
        """Display names for the current playlist, for the picker."""
        return [os.path.splitext(os.path.basename(p))[0]
                for p in self.active_list()]

    def play_chosen(self, index):
        """Play one specific track. After it ends the shuffle resumes."""
        songs = self.active_list()
        if not self.ok or not songs or not (0 <= index < len(songs)):
            return None
        self.chosen = index
        self.play_track(index)
        return self.now_playing()

    def next_track(self):
        """Called from the main loop when a track ends."""
        if self.chosen is not None:
            # the hand-picked song has finished: go back to shuffling
            self.chosen = None
            self.reshuffle()
            self.play_track(0)
            return
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
        a.title_playlist = []
        a.mode = ENDLESS
        a.playlist_started = False
        a.chosen = None
        a.track = 0
        a.found = []
        a.missing = []
        return a

    def play_match(self, cascade, multi=False):
        """One voice per clear.

        multi means the single swap produced two or more separate runs at
        once - an L or T shape, or a move that completed two lines.
        """
        if not self.ok or self.muted:
            return
        if cascade >= 2 and self.snd.get(f"cascade{min(cascade, 6)}") is not None:
            self.play(f"cascade{min(cascade, 6)}")
        elif multi:
            self.play("twomatch")
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
    """One smoke sprite: bursts outward, slows, swells, rises and fades.

    Each puff picks its own sprite from the pieces of smoke.png, so a single
    explosion is made of visibly different shapes rather than one image
    repeated at different sizes.
    """

    __slots__ = ("image", "x", "y", "dx", "dy", "spin", "t", "life",
                 "scale0", "scale1", "delay", "tint")

    def __init__(self, image, x, y, angle=None, force=1.0):
        self.image = image
        self.x, self.y = x, y
        angle = random.uniform(0, math.tau) if angle is None else angle
        speed = random.uniform(70, 155) * force
        self.dx = math.cos(angle) * speed
        self.dy = math.sin(angle) * speed * 0.78 - random.uniform(18, 46)
        self.spin = random.uniform(-95, 95)
        self.life = random.uniform(0.75, 1.25)
        self.scale0 = random.uniform(0.16, 0.30) * force
        self.scale1 = self.scale0 * random.uniform(2.6, 4.0)
        self.delay = random.uniform(0.0, 0.14)     # staggered, not one clump
        self.tint = random.randint(196, 255)
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        return self.t < self.life + self.delay

    def draw(self, screen):
        if self.t < self.delay:
            return
        p = clamp01((self.t - self.delay) / self.life)
        # drag: fast burst that eases to a stop, rather than constant speed
        travel = 1.0 - (1.0 - p) ** 2.4
        rise = p * p * 26                       # smoke keeps lifting as it fades
        scale = self.scale0 + (self.scale1 - self.scale0) * ease_out(p)
        image = pygame.transform.rotozoom(self.image, self.spin * travel, scale)
        if self.tint < 255:
            shade = image.copy()
            shade.fill((self.tint, self.tint, self.tint, 255),
                       special_flags=pygame.BLEND_RGBA_MULT)
            image = shade
        # fade in briefly so it does not appear at full strength
        alpha = 235 * min(1.0, p * 6.0) * (1.0 - p) ** 1.7
        image.set_alpha(int(alpha))
        screen.blit(image, image.get_rect(center=(
            int(self.x + self.dx * travel),
            int(self.y + self.dy * travel - rise))))


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
        label = font.render(f"+{int(BONUS_SECONDS)}S", True, (126, 240, 168))
        label = label.copy()
        label.set_alpha(int(255 * (1.0 - ease_in_out(progress) ** 1.4)))
        screen.blit(label, label.get_rect(
            center=(self.x, self.y - int(46 * ease_out(progress)))))


class FlyingGem:
    """One gem hurled off the board when a level ends."""

    __slots__ = ("image", "x", "y", "dx", "dy", "spin", "delay", "t")

    @staticmethod
    def crop(sprite):
        """Trim to the gem's own opaque bounds.

        The sprite is a full tile with the gem sitting inside it. Throwing the
        whole tile carries whatever else is in that square - which reads as
        the board tile flying off with the gem.
        """
        try:
            rects = pygame.mask.from_surface(sprite).get_bounding_rects()
        except (AttributeError, pygame.error):
            return sprite
        if not rects:
            return sprite
        box = rects[0]
        for extra in rects[1:]:
            box = box.union(extra)
        box = box.inflate(2, 2).clip(sprite.get_rect())
        return sprite.subsurface(box).copy() if box.width and box.height else sprite

    def __init__(self, image, x, y, delay):
        self.image = self.crop(image)
        self.x, self.y = x, y
        # thrown outward from the middle of the board, so the whole board
        # scatters rather than everything drifting the same way
        cx, cy = BOARD_X + BOARD_W / 2, BOARD_Y + BOARD_H / 2
        angle = math.atan2(y - cy, x - cx) + random.uniform(-0.5, 0.5)
        speed = random.uniform(620, 1150)
        self.dx = math.cos(angle) * speed
        self.dy = math.sin(angle) * speed - random.uniform(120, 300)
        self.spin = random.uniform(-620, 620)
        self.delay = delay
        self.t = 0.0

    def update(self, dt):
        self.t += dt

    def draw(self, screen):
        p = self.t - self.delay
        if p <= 0:
            screen.blit(self.image, self.image.get_rect(
                center=(int(self.x), int(self.y))))
            return
        image = pygame.transform.rotozoom(self.image, self.spin * p, 1.0)
        fade = max(0, int(255 * (1.0 - clamp01(p / 0.75))))
        image.set_alpha(fade)
        screen.blit(image, image.get_rect(center=(
            int(self.x + self.dx * p),
            int(self.y + self.dy * p + 900 * p * p))))   # gravity


class ScrollList:
    """A scrollable list of rows. Used for the music picker."""

    ROW = 34

    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.items = []
        self.offset = 0.0
        self.hover = -1
        self.current = -1

    @property
    def visible(self):
        return max(1, self.rect.height // self.ROW)

    def max_offset(self):
        return max(0, len(self.items) - self.visible)

    def scroll(self, steps):
        self.offset = max(0, min(self.max_offset(), self.offset + steps))

    def index_at(self, pos):
        if not self.rect.collidepoint(pos):
            return -1
        row = int(self.offset) + (pos[1] - self.rect.y) // self.ROW
        return row if 0 <= row < len(self.items) else -1

    def draw(self, screen, font):
        screen.blit(translucent(self.rect.size, (255, 255, 255, 16), None, 8),
                    self.rect.topleft)
        clip = screen.get_clip()
        screen.set_clip(self.rect)
        top = int(self.offset)
        for i in range(top, min(len(self.items), top + self.visible + 1)):
            y = self.rect.y + (i - top) * self.ROW
            if i == self.current:
                screen.blit(translucent((self.rect.width, self.ROW - 2),
                                        GOLD + (70,), None, 6),
                            (self.rect.x, y))
            elif i == self.hover:
                screen.blit(translucent((self.rect.width, self.ROW - 2),
                                        (255, 255, 255, 34), None, 6),
                            (self.rect.x, y))
            colour = GOLD if i == self.current else TEXT
            label = Button.fit(font, self.items[i], self.rect.width - 20)
            image = label.render(self.items[i], True, colour)
            screen.blit(image, (self.rect.x + 10,
                                y + (self.ROW - image.get_height()) // 2))
        screen.set_clip(clip)

        # scrollbar, only when there is something to scroll to
        if self.max_offset() > 0:
            span = self.rect.height * self.visible / len(self.items)
            pos = (self.rect.height - span) * self.offset / self.max_offset()
            screen.blit(translucent((4, int(span)), (255, 255, 255, 110), None, 2),
                        (self.rect.right - 6, self.rect.y + int(pos)))


class Button:
    """Rounded button. Uses skin artwork when it was supplied, else draws."""

    def __init__(self, rect, label, action, accent=None, art=None, art_hover=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.accent = accent
        self.art = art
        self.art_hover = art_hover
        self.hover = False
        self.down = False

    def hit(self, pos):
        return self.rect.collidepoint(pos)

    @staticmethod
    def fit(font, text, width):
        """Step the font down until the label fits. Pixel glyphs are far
        wider than proportional ones, so labels overflow easily."""
        while font.size(text)[0] > width and hasattr(font, "smaller"):
            smaller = font.smaller()
            if smaller is font:
                break
            font = smaller
        return font

    def draw(self, screen, font):
        font = self.fit(font, self.label, self.rect.width - 14)
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

    def __init__(self, sprites, audio=None, effects=None, backgrounds=None,
                 skin=None):
        self.normal, self.flame, self.hyper, _ = sprites
        self.anims = effects or {}
        self.backgrounds = backgrounds or []
        # flame gems: a glow shaped like the gem, and a travelling glint
        self._blocks = {}
        self.blank_tile = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        self.chaos_art = load_chaos_assets()
        self.mono_normal = [self.greyscale(spr) for spr in self.normal]
        self.mono_flame = [self.greyscale(spr) for spr in self.flame]
        self.flame_halo = [bake_halo(spr, (255, 150, 46)) for spr in self.flame]
        self.flame_glint = [bake_glints(spr) for spr in self.flame]
        self.banner = self.build_banner()
        sheet = load_still(SMOKE_ASSET)
        self.smoke = split_clusters(sheet) if sheet is not None else []
        self.hyper_glow = bake_glow(self.hyper, (255, 255, 255, 255))
        self.puffs = []
        self.effects = []
        self.skin = skin or {}
        self.on_title = True
        self.title_ready = False
        self.extras_open = False
        self.dev_open = False
        self.dev_clicks = 0
        self.dev_note = ""
        self.extras = {k: False for k, _, _ in EXTRA_DEFS}
        self.extra_clock = ENDLESS
        self.extras_note = ""
        self.settings = {k: True for k, _, _ in SETTING_DEFS}
        self.settings_open = False
        self.motes = [[random.uniform(0, WIDTH), random.uniform(0, HEIGHT),
                       random.uniform(1.0, 2.8), random.uniform(-11, -3),
                       random.uniform(0.25, 0.7)]
                      for _ in range(PARTICLE_COUNT)]
        self.title_art = self.build_title()
        self.title_bg = load_title_background()
        self.board_bg = self.build_board_backdrop()
        self.panel_bg = translucent((PANEL_W, PANEL_H), PANEL_FILL, PANEL_EDGE, 14)
        self.menu_bg = translucent(self.menu_rect().size, PANEL_FILL,
                                   PANEL_EDGE, 16)
        self.mode = ENDLESS
        self.audio = audio if audio is not None else Audio.silent()
        # scale = device pixels per font pixel, so glyphs are 7*scale tall
        self.font_huge = load_font(7, bold=True)   # 49px
        self.font_score = load_font(5, bold=True)  # 35px
        self.font_big = load_font(3, bold=True)    # 21px
        self.font = load_font(2)                   # 14px
        self.font_small = load_font(2)
        self.build_widgets()
        self.build_title_widgets()
        self.build_dev_widgets()
        self.reset()

    def build_title(self):
        """Title art with a soft dark halo, so it reads on any background."""
        art = load_title_art()
        if art is None:
            return None
        pad = 16
        out = pygame.Surface((art.get_width() + pad * 2,
                              art.get_height() + pad * 2), pygame.SRCALPHA)
        shade = art.copy()
        shade.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
        for radius in (12, 7, 3):
            blur = pygame.transform.smoothscale(
                shade, (art.get_width() + radius * 2, art.get_height() + radius * 2))
            blur.set_alpha(64)
            out.blit(blur, (pad - radius, pad - radius))
        out.blit(art, (pad, pad))
        return out

    def build_title_widgets(self):
        cx = WIDTH // 2
        w, h, gap = 250, 52, 12
        specs = ((("ENDLESS", lambda: self.start_game(ENDLESS), GOLD),
                  ("TIMED", lambda: self.start_game(TIMED), (126, 216, 150))),
                 (("SHAPES", lambda: self.start_game(SHAPES), (232, 150, 96)),
                  ("EXTRAS", self.open_extras, (176, 140, 240))),
                 (("MENU", self.open_settings, (150, 160, 190)),
                  ("QUIT", self.quit, (232, 92, 92))))
        self.title_buttons = []
        for row, pair in enumerate(specs):
            for col, (label, action, accent) in enumerate(pair):
                x = cx - w - gap // 2 + col * (w + gap)
                y = 396 + row * (h + gap)
                self.title_buttons.append(
                    Button((x, y, w, h), label, action, accent=accent))

        # extras chooser
        box = self.extras_rect()
        self.extra_rows = []
        for i, (key, label, blurb) in enumerate(EXTRA_DEFS):
            self.extra_rows.append(
                (key, pygame.Rect(box.x + 26, box.y + 70 + i * EXTRA_ROW,
                                  box.width - 52, EXTRA_ROW - 6), label, blurb))
        half = (box.width - 52 - 12) // 2
        by = box.y + 70 + len(EXTRA_DEFS) * EXTRA_ROW + 12
        self.extra_buttons = [
            Button((box.x + 26, by, half, 40), "ENDLESS",
                   lambda: self.set_extra_clock(ENDLESS), accent=GOLD),
            Button((box.x + 26 + half + 12, by, half, 40), "TIMED",
                   lambda: self.set_extra_clock(TIMED), accent=(126, 216, 150)),
            Button((box.x + 26, by + 52, half, 40), "BACK",
                   self.close_extras),
            Button((box.x + 26 + half + 12, by + 52, half, 40), "PLAY",
                   self.play_extras, accent=(126, 216, 150)),
        ]

    @staticmethod
    def dev_rect():
        return pygame.Rect(WIDTH // 2 - 260, 70, 520, 590)

    def logo_rect(self):
        """Where the title art sits, for the secret dev-mode taps."""
        if self.title_art is None:
            return pygame.Rect(WIDTH // 2 - 200, 60, 400, 180)
        return self.title_art.get_rect(center=(WIDTH // 2, 148))

    def build_dev_widgets(self):
        """Developer mode: fire each effect and cue on demand."""
        box = self.dev_rect()
        pad, gap = 24, 8
        w = (box.width - pad * 2 - gap) // 2
        specs = [
            ("MATCH", lambda: self.dev_effect("match")),
            ("EXPLODE", lambda: self.dev_effect("explode")),
            ("SMOKE", lambda: self.dev_smoke()),
            ("HYPER FX", lambda: self.dev_effect("hyper")),
            ("GO!", lambda: self.dev_go()),
            ("LEVEL UP", lambda: self.dev_levelup()),
            ("RAINBOW BLAST", lambda: self.dev_rainbow()),
            ("BOMB BLAST", lambda: self.dev_bomb()),
            ("SHAKE", lambda: self.add_shake(SHAKE_MAX)),
            ("SPAWN FLAME", lambda: self.dev_place(FLAME)),
            ("SPAWN RAINBOW", lambda: self.dev_place(HYPER)),
            ("SPAWN BOMB", lambda: self.dev_place(None, CELL_BOMB)),
            ("SPAWN ROCK", lambda: self.dev_place(None, CELL_ROCK)),
            ("CLOSE", self.close_dev),
        ]
        self.dev_buttons = []
        for i, (label, action) in enumerate(specs):
            x = box.x + pad + (i % 2) * (w + gap)
            y = box.y + 96 + (i // 2) * 46
            self.dev_buttons.append(Button((x, y, w, 40), label, action))

        sounds = ["match3", "twomatch", "cascade2", "cascade3", "explode",
                  "hyper", "flamemade", "hypermade", "rainbowcharge",
                  "rainbowzap", "flyoff", "go", "levelup", "gameover",
                  "menuclick", "select", "nomatch", "falling", "bonus",
                  "shuffle"]
        self.dev_sounds = ScrollList((box.x + pad, box.y + 96 + 7 * 46 + 10,
                                      box.width - pad * 2, 150))
        self.dev_sounds.items = sounds

    def open_dev(self):
        self.dev_open = True
        self.dev_note = "DEVELOPER MODE"
        self.audio.play("menuclick")

    def close_dev(self):
        self.dev_open = False
        self.dev_clicks = 0

    # -- developer actions -------------------------------------------------

    def dev_cell(self):
        return ROWS // 2, COLS // 2

    def dev_ensure_board(self):
        if not self.grid or self.grid[0][0] is None:
            self.grid = new_grid()

    def dev_effect(self, name):
        r, c = self.dev_cell()
        self.spawn_effect(name, r, c)
        self.dev_note = f"{name} x1"

    def dev_smoke(self):
        r, c = self.dev_cell()
        self.spawn_smoke(r, c)
        self.dev_note = f"smoke ({len(self.puffs)} puffs)"

    def dev_go(self):
        self.go_left = GO_TIME
        self.audio.play("go")
        self.dev_note = "GO!"

    def dev_levelup(self):
        self.close_dev()
        self.begin_levelup()

    def dev_rainbow(self):
        r, c = self.dev_cell()
        self.grid[r][c] = Gem(HYPER_KIND, HYPER)
        targets = {(rr, cc) for rr in range(ROWS) for cc in range(COLS)
                   if self.grid[rr][cc] is not None
                   and self.grid[rr][cc].cell_type == CELL_GEM
                   and abs(rr - r) + abs(cc - c) <= 4}
        self.close_dev()
        self.begin_rainbow((r, c), targets)

    def dev_bomb(self):
        r, c = self.dev_cell()
        self.grid[r][c] = Gem.bomb(1)
        self.move_pending = True
        self.close_dev()
        self.settle()

    def dev_place(self, power, cell_type=None):
        r, c = self.dev_cell()
        if cell_type == CELL_BOMB:
            self.grid[r][c] = Gem.bomb(random.randint(BOMB_FUSE_MIN, BOMB_FUSE_MAX))
            self.dev_note = "bomb placed at centre"
        elif cell_type == CELL_ROCK:
            self.grid[r][c] = Gem.rock()
            self.dev_note = "rock placed at centre"
        elif power == HYPER:
            self.grid[r][c] = Gem(HYPER_KIND, HYPER)
            self.dev_note = "rainbow placed at centre"
        else:
            self.grid[r][c] = Gem(self.grid[r][c].kind if
                                  self.grid[r][c].cell_type == CELL_GEM else 0,
                                  FLAME)
            self.dev_note = "flame placed at centre"

    def draw_dev(self, screen):
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((6, 8, 18, 205))
        screen.blit(veil, (0, 0))
        box = self.dev_rect()
        screen.blit(translucent(box.size, PANEL_FILL, PANEL_EDGE, 16),
                    box.topleft)
        title = self.font_big.render("DEV MODE", True, GOLD)
        screen.blit(title, (box.x + 24, box.y + 22))
        if self.dev_note:
            note = self.font_small.render(self.dev_note, True, DIM)
            screen.blit(note, (box.right - 24 - note.get_width(), box.y + 28))
        hint = self.font_small.render("EFFECTS", True, DIM)
        screen.blit(hint, (box.x + 24, box.y + 74))
        for button in self.dev_buttons:
            button.draw(screen, self.font)
        label = self.font_small.render("SOUNDS - CLICK TO PLAY", True, DIM)
        screen.blit(label, (box.x + 24, self.dev_sounds.rect.y - 18))
        self.dev_sounds.draw(screen, self.font_small)

    @staticmethod
    def settings_rect():
        return pygame.Rect(WIDTH // 2 - 240, 128, 480, 452)

    def open_settings(self):
        """Kept as a name; the graphics toggles live in the main menu now."""
        self.open_menu()
        self.audio.play("menuclick")

    def close_settings(self):
        self.settings_open = False
        self.audio.play("menuclick")

    def toggle_setting(self, key):
        self.settings[key] = not self.settings.get(key, True)
        if key == "shake":
            self.shake = 0.0
        self.audio.play("menuclick")

    @staticmethod
    def extras_rect():
        return pygame.Rect(WIDTH // 2 - 250, 96, 500, 540)

    def open_extras(self):
        self.extras_open = True
        self.audio.play("menuclick")

    def close_extras(self):
        self.extras_open = False
        self.dev_open = False
        self.dev_clicks = 0
        self.dev_note = ""
        self.audio.play("menuclick")

    def toggle_extra(self, key):
        self.extras[key] = not self.extras.get(key, False)
        if key == "zen" and self.extras["zen"]:
            self.extra_clock = ENDLESS      # zen has no clock, ever
        self.audio.play("menuclick")

    def set_extra_clock(self, clock):
        if self.extras.get("zen"):
            return                          # locked to endless
        self.extra_clock = clock
        self.audio.play("menuclick")

    def play_extras(self):
        if not any(self.extras.values()):
            self.extras_note = "PICK AT LEAST ONE"
            return
        self.extras_open = False
        self.dev_open = False
        self.dev_clicks = 0
        self.dev_note = ""
        self.start_game(EXTRAS)

    def start_game(self, mode):
        """Leave the title screen and begin a run in the chosen mode."""
        self.on_title = False
        self.title_ready = False
        self.audio.play("menuclick")
        self.reset(mode)          # reset() swaps the music to the mode's list

    def draw_title(self, screen):
        photo = self.title_bg or (self.backgrounds[0] if self.backgrounds else None)
        if photo is None:
            screen.fill(BG)
        else:
            screen.blit(photo, (0, 0))
        # lighter veil when it is the purpose-made title art
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((6, 8, 18, 60 if self.title_bg else 120))
        screen.blit(veil, (0, 0))

        art = self.title_art
        if art is not None:
            # a slow bob plus a gentle brightness shimmer
            bob = int(6 * math.sin(self.time * 1.5))
            glow = 0.5 + 0.5 * math.sin(self.time * 2.1)
            # The artwork is white, so a white glow on white letters is
            # invisible. A COLOURED halo that drifts through the spectrum
            # reads clearly and suits the name.
            hue = (self.time * 0.11) % 1.0
            for i, spread in enumerate((1.09, 1.05)):
                shade = colorsys.hsv_to_rgb((hue + i * 0.13) % 1.0, 0.75, 1.0)
                halo = pygame.transform.smoothscale(
                    art, (int(art.get_width() * spread),
                          int(art.get_height() * spread)))
                halo.fill(tuple(int(c * 255) for c in shade)
                          + (int((70 + 95 * glow) * (1.0 - i * 0.35)),),
                          special_flags=pygame.BLEND_RGBA_MULT)
                screen.blit(halo, halo.get_rect(center=(WIDTH // 2, 148 + bob)),
                            special_flags=pygame.BLEND_RGBA_ADD)
            screen.blit(art, art.get_rect(center=(WIDTH // 2, 148 + bob)))
        else:
            big = self.font_huge.render("PRISMAC", True, TEXT)
            screen.blit(big, big.get_rect(center=(WIDTH // 2, 148)))

        if self.title_ready:
            label = self.font_big.render("CHOOSE A MODE", True, DIM)
            # sits clear above the first row of buttons (y=396)
            screen.blit(label, label.get_rect(center=(WIDTH // 2, 362)))
            for button in self.title_buttons:
                button.draw(screen, self.font)
        else:
            pulse = 0.5 + 0.5 * math.sin(self.time * 3.0)
            prompt = self.font_big.render("CLICK TO START", True, TEXT)
            prompt.set_alpha(int(120 + 135 * pulse))
            screen.blit(prompt, prompt.get_rect(center=(WIDTH // 2, 470)))

        if self.extras_open:
            self.draw_extras(screen)
        if self.menu_open:
            self.draw_menu(screen)

        if self.dev_open:
            self.draw_dev(screen)

        credit = self.font_small.render(CREDITS, True, DIM)
        screen.blit(credit, (WIDTH - 20 - credit.get_width(),
                             HEIGHT - 20 - credit.get_height()))

    def draw_extras(self, screen):
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((6, 8, 18, 200))
        screen.blit(veil, (0, 0))
        box = self.extras_rect()
        screen.blit(translucent(box.size, PANEL_FILL, PANEL_EDGE, 16),
                    box.topleft)
        title = self.font_big.render("EXTRAS", True, TEXT)
        screen.blit(title, (box.x + 26, box.y + 24))
        hint = self.font_small.render("PICK ANY", True, DIM)
        screen.blit(hint, (box.right - 26 - hint.get_width(), box.y + 30))

        for key, rect, label, blurb in self.extra_rows:
            on = self.extras.get(key, False)
            screen.blit(translucent(rect.size,
                                    GOLD + (60,) if on else (255, 255, 255, 18),
                                    None, 8), rect.topleft)
            tick = pygame.Rect(rect.x + 8, rect.centery - 10, 20, 20)
            pygame.draw.rect(screen, TEXT if on else DIM, tick, 2,
                             border_radius=4)
            if on:
                pygame.draw.line(screen, GOLD, (tick.x + 4, tick.centery),
                                 (tick.centerx, tick.bottom - 5), 3)
                pygame.draw.line(screen, GOLD, (tick.centerx, tick.bottom - 5),
                                 (tick.right - 3, tick.y + 3), 3)
            # label on top, blurb on its own line underneath - a pixel font
            # is far too wide to fit both side by side
            name = self.font.render(label, True, TEXT if on else DIM)
            screen.blit(name, (rect.x + 38, rect.y + 5))
            note_font = Button.fit(self.font_small, blurb, rect.width - 46)
            note = note_font.render(blurb, True, DIM)
            screen.blit(note, (rect.x + 38, rect.y + 5 + name.get_height() + 4))

        zen = self.extras.get("zen")
        for button in self.extra_buttons:
            if button.label in (ENDLESS.upper(), TIMED.upper()):
                button.hover = (not zen and
                                self.extra_clock.upper() == button.label)
            button.draw(screen, self.font)
        if zen:
            lock = self.font_small.render("ZEN IS ALWAYS ENDLESS", True, DIM)
            screen.blit(lock, (box.x + 26, self.extra_buttons[0].rect.y - 18))
        if self.extras_note:
            warn = self.font_small.render(self.extras_note, True, (255, 150, 150))
            screen.blit(warn, (box.x + 26, box.bottom - 26))

    def reset(self, mode=None):
        if mode is not None:
            self.mode = mode
        self.time = 0.0
        self.score = 0
        self.level = 1
        self.level_floor = 0          # score at which the current level began
        self.menu_open = False
        self.music_open = False
        self.dragging = None
        self.wants_quit = False
        self.hint = None
        self.hint_left = 0.0
        self.effects = []
        self.go_left = 0.0
        self.flyers = []
        self.multi_run = False
        self.move_pending = False
        self.spent_bombs = set()
        self.rainbow_targets = []
        self.rainbow_all = set()
        self.rainbow_bolts = []
        self.rainbow_origin = None
        self.rainbow_done = 0
        self.rainbow_step = RAINBOW_STEP
        self.shake = 0.0
        self.shake_t = 0.0
        self.frame = None
        self.note = ""
        self.shape_cells = None
        self.shape_name = None
        self.time_left = TIMED_SECONDS
        self.lock_kind = random.randrange(N_TYPES)
        self.lock_left = LOCK_SECONDS
        self.over = False
        self.time_pops = []          # floating "+3s" labels
        self.puffs = []              # smoke left by flame gems
        # While the title screen is up its own track keeps playing; the mode
        # playlist only takes over once a game actually starts.
        if not self.on_title:
            # an Extras run with the clock on should still get the timed music
            self.audio.use_playlist(
                TIMED_MUSIC_MODE if (self.mode == EXTRAS and self.timed)
                else self.mode)
        self.new_board()

    def apply_extras(self, grid):
        """Rewrite a freshly built grid to suit the active modifiers."""
        # MONO is purely cosmetic - the gems are drawn greyscale but keep
        # their distinct kinds. Forcing them all to one kind would make the
        # whole board a single enormous match.
        # Explosives mode does NOT convert gems already on the board - they
        # arrive as explosives from the top, handled in collapse()/new_grid().
        return grid

    def pick_shape(self):
        """A new silhouette for the current Shapes level.

        Avoids repeating the shape you just played, so consecutive levels
        always look different.
        """
        choices = [n for n in SHAPE_MASKS if n != getattr(self, "shape_name", None)]
        self.shape_name = random.choice(choices or list(SHAPE_MASKS))
        self.shape_cells = shape_mask(self.shape_name)

    def new_board(self):
        """Fresh grid for the current level, rained in from above."""
        if self.mode == SHAPES:
            # A new level means a new silhouette; it only stays fixed for the
            # duration of one level, including any reshuffle within it.
            self.pick_shape()
            self.grid = new_shapes_grid(bonuses=self.timed,
                                        mask=self.shape_cells)
        else:
            self.grid = self.apply_extras(
                new_grid(bonuses=self.timed, chaos=self.extra("chaos")))
        self.begin_intro()

    def mode_label(self):
        if self.mode == EXTRAS:
            on = [lbl for k, lbl, _ in EXTRA_DEFS if self.extras.get(k)]
            return on[0] if len(on) == 1 else f"EXTRAS x{len(on)}"
        if self.mode == SHAPES:
            return "SHAPES"
        return "TIMED" if self.timed else "ENDLESS"

    def extra(self, key):
        """Is this modifier switched on for the current run?"""
        return self.mode == EXTRAS and self.extras.get(key, False)

    @property
    def timed(self):
        if self.mode == EXTRAS:
            return self.extra_clock == TIMED and not self.extra("zen")
        return self.mode == TIMED

    @property
    def scoring(self):
        """Zen keeps no score, so it also never levels up."""
        return not self.extra("zen")

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
    def build_banner():
        """The LEVEL UP artwork, sized to the board and given a soft dark
        halo so white lettering still reads on a pale background."""
        art = load_still(BANNER_ASSET)
        if art is None:
            return None
        target = int(BOARD_W * 0.82)
        w, h = art.get_size()
        art = pygame.transform.smoothscale(
            art, (target, max(1, int(h * target / w))))

        pad = 14
        out = pygame.Surface((art.get_width() + pad * 2,
                              art.get_height() + pad * 2), pygame.SRCALPHA)
        shadow = art.copy()
        shadow.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
        for radius in (10, 6, 3):
            blur = pygame.transform.smoothscale(
                shadow, (art.get_width() + radius * 2,
                         art.get_height() + radius * 2))
            blur.set_alpha(70)
            out.blit(blur, (pad - radius, pad - radius))
        out.blit(art, (pad, pad))
        return out

    def skinned(self, name, size):
        """Scaled skin image, or None if that file was not supplied."""
        art = self.skin.get(name)
        return stretch(art, size) if art is not None else None

    def build_board_backdrop(self):
        """The board surface, baked once instead of redrawn every frame.

        With ui/board.png present that artwork is the board and the checker
        pattern is dropped - a texture and a checkerboard fight each other.
        """
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

    def add_shake(self, amount):
        if not self.settings.get("shake", True):
            return
        """Kick the camera. Amounts add up but are capped, so a huge cascade
        does not turn into an earthquake."""
        self.shake = min(SHAKE_MAX, self.shake + amount)

    def shake_offset(self):
        """Decaying wobble on two different frequencies, so it does not read
        as a clean sine wave."""
        if self.shake <= 0.15:
            return (0, 0)
        a = self.shake
        return (int(math.sin(self.shake_t * 46.0) * a
                    + math.sin(self.shake_t * 71.0) * a * 0.4),
                int(math.cos(self.shake_t * 53.0) * a * 0.8
                    + math.cos(self.shake_t * 89.0) * a * 0.3))

    def spawn_effect(self, name, r, c):
        """Play an animation centred on a board cell, if that effect exists."""
        anim = self.anims.get(name)
        if anim is None or len(self.effects) >= MAX_EFFECTS:
            return
        self.effects.append(Effect(anim,
                                   BOARD_X + int((c + 0.5) * TILE),
                                   BOARD_Y + int((r + 0.5) * TILE)))

    def puff_cells(self, cells, per_cell=2, force=0.5):
        """A small amount of smoke spread over many cells.

        Used for a hypercube wipe: a full burst on every gem would be dozens
        of clouds, so this is deliberately thin and capped.
        """
        if not self.smoke:
            return
        picks = list(cells)
        random.shuffle(picks)
        budget = max(0, MAX_EFFECTS - len(self.puffs))
        for r, c in picks[:max(1, budget // max(1, per_cell))]:
            x = BOARD_X + int((c + 0.5) * TILE)
            y = BOARD_Y + int((r + 0.5) * TILE)
            for i in range(per_cell):
                self.puffs.append(Puff(random.choice(self.smoke), x, y,
                                       angle=random.uniform(0, math.tau),
                                       force=force))

    def spawn_smoke(self, r, c, count=7):
        """A cloud where a flame gem went off.

        Puffs are thrown out on an even spread of angles with a random wobble,
        so the burst reads as a ring rather than a random scatter, and each
        one draws a different piece of smoke.png.
        """
        if not self.smoke or len(self.puffs) > MAX_EFFECTS:
            return
        x = BOARD_X + int((c + 0.5) * TILE)
        y = BOARD_Y + int((r + 0.5) * TILE)
        for i in range(count):
            angle = math.tau * i / count + random.uniform(-0.45, 0.45)
            self.puffs.append(Puff(random.choice(self.smoke), x, y,
                                   angle=angle,
                                   force=random.uniform(0.65, 1.15)))
        # one slow fat puff in the middle, so the centre is not hollow
        self.puffs.append(Puff(max(self.smoke, key=lambda s: s.get_width()),
                               x, y, angle=random.uniform(0, math.tau),
                               force=0.28))

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
        """Throw every gem off the board, then hold a banner, then refill.

        Sequence: gems fly off -> LEVEL banner in the middle of the board ->
        a beat -> the new board rains in -> a beat -> GO!
        """
        self.level_floor += self.level_target()   # overflow carries forward
        self.level += 1
        self.sel = None
        self.press = None
        self.pair = None
        self.matched = set()
        self.spawns = {}
        self.falls = {}
        self.note = ""

        self.flyers = []
        for r in range(ROWS):
            for c in range(COLS):
                gem = self.grid[r][c]
                # A hole is a Gem with cell_type CELL_EMPTY, not None - without
                # this check a Shapes board throws a flyer from every hole,
                # drawn as gem kind 0.
                if gem is None or gem.cell_type == CELL_EMPTY:
                    continue
                # stagger by distance from the centre so it ripples outward
                dr, dc = r - (ROWS - 1) / 2, c - (COLS - 1) / 2
                delay = math.hypot(dr, dc) / max(ROWS, COLS) * 0.42
                self.flyers.append(FlyingGem(
                    self.sprite_for(gem),
                    BOARD_X + (c + 0.5) * TILE,
                    BOARD_Y + (r + 0.5) * TILE,
                    delay + random.uniform(0.0, 0.06)))

        # Empty the board immediately. Otherwise draw_scene keeps drawing the
        # gems in place while their copies fly away, so the board looks full
        # right through the transition.
        self.grid = [[None] * COLS for _ in range(ROWS)]

        self.state = "flyoff"
        self.t = 0.0
        # No camera shake here: it moves the board and panel with it, which
        # reads as the board itself flying away. Only the gems should move.
        self.audio.play("flyoff")

    def begin_banner(self):
        self.state = "banner"
        self.t = 0.0
        self.flyers = []
        self.audio.play("levelup")

    def banner_length(self):
        return BANNER_IN + BANNER_HOLD + BANNER_OUT + DROP_PAUSE

    def banner_pose(self):
        """(x_offset, alpha) for the LEVEL banner.

        Fixed size throughout: it slides in, holds, then flies off to the
        side, the same way the GO! card behaves. No scaling.
        """
        t = self.t
        if t < BANNER_IN:
            p = ease_out(clamp01(t / BANNER_IN))
            return int(-WIDTH * (1.0 - p)), int(255 * clamp01(t / (BANNER_IN * 0.6)))
        t -= BANNER_IN
        if t < BANNER_HOLD:
            return 0, 255
        t -= BANNER_HOLD
        p = clamp01(t / BANNER_OUT)
        return int(WIDTH * ease_in_out(p)), int(255 * (1.0 - clamp01(p * 1.4)))

    def secret_shuffle(self):
        """Hidden reshuffle. New board, score and level untouched.

        Only fires when the board is settled, so it can't interrupt a cascade
        that is still paying out points.
        """
        if self.over or self.state != "idle":
            return False
        self.grid = (new_shapes_grid(self.timed, self.shape_cells)
                     if self.mode == SHAPES
                     else new_grid(bonuses=self.timed,
                                   chaos=self.extra("chaos")))
        self.audio.play("shuffle")
        self.begin_intro()          # rains the new board in like any other
        return True

    # -- widgets ----------------------------------------------------------

    def build_widgets(self):
        x = PANEL_X + 16
        w = PANEL_W - 32
        bottom = PANEL_Y + PANEL_H - 16
        self.buttons = [
            Button((x, bottom - 46 * 3 - 20, w, 46), "HINT",
                   self.show_hint, accent=HINT_COLOR),
            Button((x, bottom - 46 * 2 - 10, w, 46), "MUSIC",
                   self.open_music, accent=(150, 160, 190)),
            Button((x, bottom - 46, w, 46), "MENU", self.open_menu),
        ]

        box = self.menu_rect()
        sx, sw = box.x + 30, box.width - 60
        self.sliders = [
            Slider((sx, box.y + 104, sw, 8), "MUSIC",
                   lambda: self.audio.music_volume, self.audio.set_music_volume),
            Slider((sx, box.y + 168, sw, 8), "SOUND EFFECTS",
                   lambda: self.audio.sfx_volume, self.audio.set_sfx_volume),
        ]
        # graphics toggles sit between the sliders and the buttons
        self.setting_rows = []
        for i, (key, label, blurb) in enumerate(SETTING_DEFS):
            self.setting_rows.append(
                (key, pygame.Rect(sx, box.y + 226 + i * EXTRA_ROW,
                                  sw, EXTRA_ROW - 6), label, blurb))
        self.setting_buttons = []

        half = (sw - 20) // 2
        self.menu_buttons = [
            Button((sx, self.setting_rows[-1][1].bottom + 14,
                    sw, 42), "RETURN TO TITLE",
                   self.return_to_title, accent=GOLD),
            Button((sx, self.setting_rows[-1][1].bottom + 66, half, 42),
                   "RESUME", self.close_menu),
            Button((sx + half + 20, self.setting_rows[-1][1].bottom + 66,
                    half, 42), "QUIT", self.quit, accent=(232, 92, 92)),
        ]

        picker = self.music_rect()
        self.music_list = ScrollList((picker.x + 24, picker.y + 76,
                                      picker.width - 48, picker.height - 150))
        pw = picker.width - 48
        self.music_buttons = [
            Button((picker.x + 24, picker.bottom - 62, pw, 44), "CLOSE",
                   self.close_music,
                   art=self.skinned("menubutton", (pw, 44)),
                   art_hover=self.skinned("menubuttonhovered", (pw, 44))),
        ]

        over = self.over_rect()
        ox, ow = over.x + 34, over.width - 68
        third = (ow - 20) // 2
        self.over_buttons = [
            Button((ox, over.bottom - 74, third, 46), "PLAY AGAIN",
                   lambda: self.reset(self.mode), accent=(126, 216, 150)),
            Button((ox + third + 20, over.bottom - 74, third, 46), "TITLE",
                   self.return_to_title, accent=GOLD),
        ]

    @staticmethod
    def music_rect():
        return pygame.Rect(WIDTH // 2 - 230, HEIGHT // 2 - 220, 460, 440)

    @staticmethod
    def over_rect():
        return pygame.Rect(WIDTH // 2 - 210, HEIGHT // 2 - 150, 420, 300)

    @staticmethod
    def menu_rect():
        return pygame.Rect(WIDTH // 2 - 230, 70, 460, 580)

    # -- button actions ---------------------------------------------------

    def show_hint(self):
        if self.over or self.state != "idle":
            return
        self.hint = find_hint(self.grid)
        self.hint_left = HINT_SECONDS if self.hint else 0.0
        self.note = "" if self.hint else "no moves - reshuffling"
        if self.hint is None:
            self.secret_shuffle()

    def open_music(self):
        """Song picker. Choosing one plays it, then the shuffle resumes."""
        self.music_open = True
        self.menu_open = False
        self.sel = None
        self.dragging = None
        self.music_list.items = self.audio.track_names()
        playing = self.audio.now_playing()
        self.music_list.current = (self.music_list.items.index(playing)
                                   if playing in self.music_list.items else -1)
        self.music_list.offset = 0.0

    def close_music(self):
        self.music_open = False

    def return_to_title(self):
        self.menu_open = False
        self.music_open = False
        self.over = False
        self.on_title = True
        self.title_ready = False
        self.audio.chosen = None
        self.audio.use_playlist(TITLE)

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
        if self.on_title and self.settings_open:
            for slider in self.setting_sliders:
                if slider.hit(pos):
                    return slider
            for button in self.setting_buttons:
                if button.hit(pos):
                    return button
            return None
        if self.on_title and self.extras_open:
            for button in self.extra_buttons:
                if button.hit(pos):
                    return button
            return None
        if self.on_title:
            if self.menu_open:
                for button in self.title_buttons:
                    button.hover = False
                for slider in self.sliders:
                    if slider.hit(pos):
                        return slider
                for button in self.menu_buttons:
                    if button.hit(pos):
                        return button
                return None
            if self.title_ready:
                for button in self.title_buttons:
                    if button.hit(pos):
                        return button
            return None
        if self.music_open:
            for button in self.music_buttons:
                if button.hit(pos):
                    return button
            return None
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
        if self.on_title and self.dev_open:
            row = self.dev_sounds.index_at(pos)
            if row >= 0:
                self.audio.play(self.dev_sounds.items[row])
                self.dev_sounds.current = row
                self.dev_note = f"played {self.dev_sounds.items[row]}"
                return
            for button in self.dev_buttons:
                if button.hit(pos):
                    button.down = True
                    return
            if not self.dev_rect().collidepoint(pos):
                self.close_dev()
            return

        if self.on_title and self.logo_rect().collidepoint(pos):
            self.dev_clicks += 1
            if self.dev_clicks >= DEV_CLICKS:
                self.dev_clicks = 0
                self.open_dev()
                return

        if self.on_title and self.extras_open:
            for key, rect, _, _ in self.extra_rows:
                if rect.collidepoint(pos):
                    self.toggle_extra(key)
                    self.extras_note = ""
                    return
            # no row hit: fall through so the buttons below still work
        elif self.on_title and not self.title_ready:
            self.title_ready = True        # first click reveals the modes
            self.audio.play("menuclick")
            return
        # the graphics toggles live in the menu, which is reachable from both
        # the title screen and the board - so this must come before any
        # on_title early return
        if self.menu_open:
            for key, rect, _, _ in self.setting_rows:
                if rect.collidepoint(pos):
                    self.toggle_setting(key)
                    return

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
        if self.on_title:
            if self.menu_open and not self.menu_rect().collidepoint(pos):
                self.audio.play("menuclick")
                self.close_menu()
            return
        if self.music_open:
            row = self.music_list.index_at(pos)
            if row >= 0:
                self.audio.play("menuclick")
                name = self.audio.play_chosen(row)
                self.music_list.current = row
                if name:
                    self.note = f"playing {name}"
            elif not self.music_rect().collidepoint(pos):
                self.audio.play("menuclick")
                self.close_music()
            return
        if self.over:
            return                     # nothing but those two buttons is live
        if self.menu_open:
            for key, rect, _, _ in self.setting_rows:
                if rect.collidepoint(pos):
                    self.toggle_setting(key)
                    return
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
        elif cell == self.sel:
            self.sel = None            # click the selected gem again to drop it
            self.press = None          # ...and do not let mouse-up re-select
            self.audio.play("select")
        elif self.sel is not None and adjacent(self.sel, cell):
            self.begin_swap(self.sel, cell)
        else:
            self.sel = cell
            self.audio.play("select")

    def on_motion(self, pos):
        if self.dragging is not None:
            self.dragging.set_from(pos)
            return
        if self.on_title:
            active = ([] if self.menu_open
                      else self.extra_buttons if self.extras_open
                      else (self.title_buttons if self.title_ready else []))
        elif self.over:
            active = self.over_buttons
        elif self.menu_open:
            active = self.menu_buttons
        else:
            active = self.buttons
        for button in (self.buttons + self.menu_buttons + self.over_buttons
                       + self.title_buttons + self.setting_buttons
                       + self.extra_buttons):
            button.hover = button in active and button.hit(pos)

    def on_up(self, pos):
        if self.dragging is not None:
            self.dragging = None
            return

        fired = None
        for button in (self.buttons + self.menu_buttons + self.over_buttons
                       + self.title_buttons + self.music_buttons
                       + self.extra_buttons + self.dev_buttons
                       + self.setting_buttons):
            if button.down and button.hit(pos):
                fired = button
            button.down = False
        if fired is not None:
            fired.action()
            return

        if (self.over or self.menu_open or self.music_open
                or self.state != "idle" or self.press is None):
            return
        cell = self.cell_at(pos)
        if cell is not None and cell != self.press and adjacent(self.press, cell):
            self.begin_swap(self.press, cell)
        self.press = None

    def begin_swap(self, a, b):
        for r, c in (a, b):
            cell = self.grid[r][c]
            if cell is None or cell.cell_type == CELL_EMPTY:
                return             # nothing may move into a blacked-out cell
        self.move_pending = True          # this is a player move, fuses tick
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
        if self.on_title:
            return
        self.update_motes(dt)
        if self.effects:
            self.effects = [e for e in self.effects if e.update(dt)]
        if self.go_left > 0:
            self.go_left = max(0.0, self.go_left - dt)
        if self.shake > 0:
            self.shake_t += dt
            self.shake = max(0.0, self.shake - self.shake * SHAKE_DECAY * dt
                             - 0.6 * dt)
        if self.time_pops:
            self.time_pops = [p for p in self.time_pops if p.update(dt)]
        if self.puffs:
            self.puffs = [p for p in self.puffs if p.update(dt)]

        # The clock only runs while the board is actually playable. Opening
        # the menu pauses it - otherwise adjusting the volume costs you time.
        if (self.timed and not self.over
                and not self.menu_open and not self.music_open
                and not getattr(self, "dev_open", False)
                and self.state not in PAUSED_STATES):
            self.time_left -= dt
            if self.time_left <= 0:
                self.time_left = 0.0
                self.end_game()
        if self.extra("lock") and self.state == "idle" and not self.over:
            self.lock_left -= dt
            if self.lock_left <= 0:
                choices = [k for k in range(N_TYPES) if k != self.lock_kind]
                self.lock_kind = random.choice(choices or [self.lock_kind])
                self.lock_left = LOCK_SECONDS
        if self.hint_left > 0:
            self.hint_left = max(0.0, self.hint_left - dt)
            if self.hint_left == 0:
                self.hint = None
        for cell in list(self.pops):
            self.pops[cell] -= dt
            if self.pops[cell] <= 0:
                del self.pops[cell]

        if self.state == "idle":
            return

        if self.state == "rainbow":
            self.update_rainbow(dt)
            return

        if self.state == "flyoff":
            self.t += dt
            for flyer in self.flyers:
                flyer.update(dt)
            if self.t >= FLYOFF_TIME:
                self.begin_banner()
            return

        if self.state == "banner":
            self.t += dt
            if self.t >= self.banner_length():
                self.new_board()          # rains the fresh gems in
            return

        if self.state == "settling":
            self.t += dt
            if self.t >= GO_PAUSE:
                self.state = "idle"
                self.t = 0.0
                self.go_left = GO_TIME
                self.audio.play("go")
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
            self.state = "settling"      # a beat before GO!
            self.t = 0.0
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
                self.multi_run = False
                self.begin_clear(*plan_clear(self.grid, runs))
            else:
                self.settle()

    def begin_rainbow(self, hyper, targets):
        """Charge, then zap each target in turn.

        The gems are removed from the board progressively so the wipe reads
        as the rainbow gem doing the work, rather than everything vanishing
        at once.
        """
        cx = BOARD_X + (hyper[1] + 0.5) * TILE
        cy = BOARD_Y + (hyper[0] + 0.5) * TILE
        ordered = sorted(targets, key=lambda rc: math.hypot(
            BOARD_X + (rc[1] + 0.5) * TILE - cx,
            BOARD_Y + (rc[0] + 0.5) * TILE - cy))
        self.rainbow_origin = hyper
        self.rainbow_targets = ordered
        self.rainbow_done = 0
        self.rainbow_bolts = []
        self.rainbow_all = set(targets)
        step = min(RAINBOW_STEP,
                   max(0.02, (RAINBOW_MAX - RAINBOW_CHARGE) / max(1, len(ordered))))
        self.rainbow_step = step
        self.state = "rainbow"
        self.t = 0.0
        self.add_shake(SHAKE_RAINBOW)
        self.audio.play("rainbowcharge")

    def update_rainbow(self, dt):
        self.t += dt
        self.rainbow_bolts = [b for b in self.rainbow_bolts if b[2] > 0]
        self.rainbow_bolts = [(a, b, life - dt) for a, b, life in self.rainbow_bolts]

        if self.t < RAINBOW_CHARGE:
            return
        want = int((self.t - RAINBOW_CHARGE) / self.rainbow_step)
        want = min(want, len(self.rainbow_targets))
        while self.rainbow_done < want:
            r, c = self.rainbow_targets[self.rainbow_done]
            self.rainbow_done += 1
            self.rainbow_bolts.append((self.rainbow_origin, (r, c), 0.16))
            self.spawn_effect("match", r, c)
            if self.rainbow_done % ZAP_EVERY == 0:
                self.audio.play("rainbowzap")
                self.add_shake(SHAKE_RAINBOW * 0.16)
            if self.smoke and len(self.puffs) < MAX_EFFECTS:
                x = BOARD_X + int((c + 0.5) * TILE)
                y = BOARD_Y + int((r + 0.5) * TILE)
                self.puffs.append(Puff(random.choice(self.smoke), x, y,
                                       angle=random.uniform(0, math.tau),
                                       force=0.45))

        if (self.rainbow_done >= len(self.rainbow_targets)
                and self.t >= RAINBOW_CHARGE
                + len(self.rainbow_targets) * self.rainbow_step + RAINBOW_TAIL):
            targets = self.rainbow_all
            self.rainbow_all = set()
            self.rainbow_targets = []
            self.cascade = 1
            self.multi_run = False
            self.begin_clear(targets, {})

    def draw_rainbow(self, screen):
        """Lightning from the rainbow gem to everything it is destroying."""
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        charge = clamp01(self.t / RAINBOW_CHARGE)
        for (ar, ac), (br, bc), life in self.rainbow_bolts:
            x1 = BOARD_X + (ac + 0.5) * TILE
            y1 = BOARD_Y + (ar + 0.5) * TILE
            x2 = BOARD_X + (bc + 0.5) * TILE
            y2 = BOARD_Y + (br + 0.5) * TILE
            alpha = int(235 * clamp01(life / 0.16))
            hue = (self.time * 0.7 + ar * 0.07 + ac * 0.05) % 1.0
            col = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(hue, 0.55, 1.0))
            points = [(x1, y1)]
            segments = 5
            for i in range(1, segments):
                f = i / segments
                jitter = (1.0 - abs(f - 0.5) * 2) * TILE * 0.42
                points.append((x1 + (x2 - x1) * f + random.uniform(-jitter, jitter),
                               y1 + (y2 - y1) * f + random.uniform(-jitter, jitter)))
            points.append((x2, y2))
            pygame.draw.lines(layer, col + (alpha,), False, points, 3)
            pygame.draw.lines(layer, (255, 255, 255, alpha), False, points, 1)
        # the gem itself glowing harder as it charges
        if self.rainbow_origin is not None:
            x = BOARD_X + (self.rainbow_origin[1] + 0.5) * TILE
            y = BOARD_Y + (self.rainbow_origin[0] + 0.5) * TILE
            pulse = 0.5 + 0.5 * math.sin(self.time * 30)
            radius = int(TILE * (0.35 + 0.5 * charge + 0.1 * pulse))
            pygame.draw.circle(layer, (255, 255, 255, int(70 + 120 * charge)),
                               (int(x), int(y)), radius, 4)
        screen.blit(layer, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

    def resolve_swap(self):
        a, b = self.pair
        ga = self.grid[a[0]][a[1]]
        gb = self.grid[b[0]][b[1]]

        # hypercube path: always legal, never needs a match
        if ga.power == HYPER or gb.power == HYPER:
            hyper, other = (a, b) if ga.power == HYPER else (b, a)
            both = ga.power == HYPER and gb.power == HYPER
            targets = hyper_targets(self.grid, hyper, other)
            # Actually complete the swap so the rainbow gem ends up in the
            # square it was dragged into, rather than snapping back and
            # detonating from where it started.
            self.apply_swap()
            origin = other
            self.note = "BOARD WIPE!" if both else "RAINBOW!"
            self.spawn_effect("hyper", *origin)
            self.begin_rainbow(origin, targets)
            return

        self.apply_swap()
        runs = find_runs(self.grid)
        if runs:
            self.cascade = 1
            # two or more separate runs from one move: L/T shapes, or a swap
            # that completes two lines at once
            self.multi_run = len(runs) >= 2
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
        if not self.scoring:
            gained = 0
        elif self.extra("lock"):
            # only the locked colour pays out
            gained = sum(POINTS_PER_GEM * self.cascade for r, c in cells
                         if self.grid[r][c] is not None
                         and self.grid[r][c].kind == self.lock_kind)
        else:
            gained = len(cells) * POINTS_PER_GEM * self.cascade
        if self.scoring:
            for power in spawns.values():
                gained += HYPER_BONUS if power == HYPER else FLAME_BONUS
        self.score += gained

        self.audio.play_match(self.cascade, self.multi_run)
        for power in spawns.values():
            self.audio.play("hypermade" if power == HYPER else "flamemade")
        if any(self.grid[r][c] is not None and self.grid[r][c].power == FLAME
               for r, c in cells):
            self.add_shake(SHAKE_FLAME)
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
        self.falls = collapse(self.grid, bonuses=self.timed,
                              chaos=self.extra("chaos"),
                              shapes=self.mode == SHAPES,
                              boom=self.extra("boom"),
                              mask=getattr(self, "shape_cells", None))
        self.apply_extras(self.grid)
        self.audio.play("falling")
        self.state = "fall"

    def tick_bombs(self):
        """Count every bomb down one move, and set off any that reach zero.

        Returns the cells the detonation clears, or None if nothing went off.
        """
        live = [(r, c) for r in range(ROWS) for c in range(COLS)
                if self.grid[r][c] is not None
                and self.grid[r][c].cell_type == CELL_BOMB]
        if not live:
            return None
        spent = set()
        for r, c in live:
            gem = self.grid[r][c]
            gem.fuse = max(0, gem.fuse - 1)
            if gem.fuse == 0:
                spent.add((r, c))
        self.spent_bombs = spent
        if not spent:
            return None
        return detonate(self.grid, spent)

    def settle(self):
        self.pair = None
        self.cascade = 0
        # Only a move the player made counts down a fuse. settle() also runs
        # at the end of every cascade step, which would otherwise burn several
        # moves off every bomb for a single swap.
        blast = self.tick_bombs() if self.move_pending else None
        self.move_pending = False
        if blast:
            self.cascade = 1
            self.multi_run = False
            self.note = "BOOM!"
            self.add_shake(SHAKE_BOMB)
            self.audio.play("explode")
            for r, c in self.spent_bombs:
                self.spawn_effect("explode", r, c)
                self.spawn_smoke(r, c)
            self.begin_clear(blast, {})
            return
        if self.scoring and self.level_progress() >= 1.0:
            self.begin_levelup()
            return
        if not has_move(self.grid):
            if self.mode == SHAPES:
                # a Shapes board is fixed: running out of moves ends the run
                self.note = "NO MOVES LEFT"
                self.end_game()
                return
            self.grid = new_grid(bonuses=self.timed,
                                 chaos=self.extra("chaos"),
                                 shapes=self.mode == SHAPES)
            self.note = "no moves - reshuffled"
            self.audio.play("shuffle")
        self.state = "idle"

    # -- drawing ----------------------------------------------------------

    @staticmethod
    def greyscale(sprite):
        """Desaturate a sprite without needing numpy.

        pygame.surfarray requires numpy, which is not installed everywhere,
        so this uses the built-in transform when available and falls back to
        a plain per-pixel pass. Only runs once per gem at startup.
        """
        try:
            return pygame.transform.grayscale(sprite)
        except (AttributeError, pygame.error):
            pass

        out = sprite.copy()
        out.lock()
        width, height = out.get_size()
        for x in range(width):
            for y in range(height):
                r, g, b, a = out.get_at((x, y))
                if a:
                    lum = int(r * 0.30 + g * 0.59 + b * 0.11)
                    out.set_at((x, y), (lum, lum, lum, a))
        out.unlock()
        return out

    def sprite_for(self, gem):
        if gem.cell_type == CELL_EMPTY:
            return self.blank_tile
        # rocks and bombs are not gems: they have their own artwork and are
        # never recoloured by mono or drawn as a gem kind
        if gem.cell_type == CELL_ROCK:
            return self.chaos_art.get("rock") or self.fallback_block((150, 146, 138))
        if gem.cell_type == CELL_BOMB:
            return self.chaos_art.get("bomb") or self.fallback_block((60, 60, 66))
        if gem.power == HYPER:
            return self.hyper
        mono = self.extra("mono")
        if gem.power == FLAME:
            return (self.mono_flame if mono else self.flame)[gem.kind]
        return (self.mono_normal if mono else self.normal)[gem.kind]

    def fallback_block(self, colour):
        """Drawn shape for a rock or bomb when its art is missing, so the
        cell is still visibly not a gem rather than invisible."""
        key = colour
        cached = self._blocks.get(key)
        if cached is None:
            cached = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            pad = GEM_PAD + 3
            pygame.draw.rect(cached, colour,
                             (pad, pad, TILE - pad * 2, TILE - pad * 2),
                             border_radius=10)
            pygame.draw.rect(cached, tuple(int(v * 0.6) for v in colour),
                             (pad, pad, TILE - pad * 2, TILE - pad * 2), 3,
                             border_radius=10)
            self._blocks[key] = cached
        return cached

    def draw_fuse(self, screen, gem, x, y):
        """The move counter on a bomb, and a warning pulse when it is close."""
        if gem.cell_type != CELL_BOMB:
            return
        fuse = max(0, int(getattr(gem, "fuse", 0)))
        hot = fuse <= 2
        pulse = 0.5 + 0.5 * math.sin(self.time * (7.0 if hot else 3.0))
        if hot:
            ring = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
            pygame.draw.rect(ring, (255, 90, 70, int(90 + 110 * pulse)),
                             (2, 2, TILE - 4, TILE - 4), 3, border_radius=10)
            screen.blit(ring, (int(x), int(y)))
        label = self.font_big.render(str(fuse), True, (255, 255, 255))
        pad = 5
        w = label.get_width() + pad * 2
        h = label.get_height() + 2
        chip = translucent((w, h), (200, 60, 50, 235) if hot
                           else (30, 34, 48, 225), None, h // 2)
        chip.blit(label, (pad, 1))
        screen.blit(chip, (int(x + (TILE - w) / 2), int(y + TILE - h - 4)))

    def draw_behind(self, screen, gem, x, y):
        """Whatever sits *under* a special gem: fire, or the power-gem halo."""
        cx, cy = int(x + TILE / 2), int(y + TILE / 2)

        if gem.power == FLAME:
            halo = self.flame_halo[gem.kind]
            # two offset breathing rates so it never looks like a metronome
            t = self.time * 2.0 + (cx * 0.021 + cy * 0.017)
            pulse = 0.5 + 0.5 * math.sin(t)
            swell = 0.94 + 0.09 * pulse + 0.03 * math.sin(t * 2.3)
            image = pygame.transform.rotozoom(halo, 0, swell)
            image.set_alpha(74 + int(66 * pulse))
            screen.blit(image, image.get_rect(center=(cx, cy)),
                        special_flags=pygame.BLEND_RGBA_ADD)

        elif gem.power == HYPER:
            pulse = 0.5 + 0.5 * math.sin(self.time * 3.2)
            image = pygame.transform.rotozoom(
                self.hyper_glow, (self.time * 26) % 360, 0.94 + 0.10 * pulse)
            image.set_alpha(150 + int(90 * pulse))
            screen.blit(image, image.get_rect(center=(cx, cy)),
                        special_flags=pygame.BLEND_RGBA_ADD)

    def draw_glint(self, screen, gem, x, y):
        """Specular sweep across a flame gem, on a per-gem cycle.

        Each gem gets its own phase from its board position, so a cluster of
        flame gems does not glint in unison.
        """
        if gem.power != FLAME:
            return
        frames = self.flame_glint[gem.kind]
        if not frames:
            return
        phase = (x * 0.013 + y * 0.019) % 1.0
        cycle = (self.time / GLINT_PERIOD + phase) % 1.0
        sweep = cycle / GLINT_SWEEP
        if sweep >= 1.0:
            return                      # resting between sweeps
        index = min(len(frames) - 1, int(sweep * len(frames)))
        frame = frames[index]
        # fade in and out so the streak does not pop at either end
        edge = math.sin(sweep * math.pi)
        frame = frame.copy()
        frame.fill((255, 255, 255, int(235 * edge)),
                   special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(frame, (int(x), int(y)),
                    special_flags=pygame.BLEND_RGBA_ADD)

    def gem_draw_info(self, r, c):
        """Returns (x, y, scale) for the gem at r,c."""
        x = BOARD_X + c * TILE
        y = BOARD_Y + r * TILE
        scale = 1.0

        if (self.state == "rainbow" and (r, c) == self.rainbow_origin
                and self.t < RAINBOW_CHARGE):
            # the gem rattles harder as it winds up
            wind = clamp01(self.t / RAINBOW_CHARGE)
            amp = 1.5 + 6.5 * wind * wind
            x += math.sin(self.t * 58.0) * amp
            y += math.cos(self.t * 47.0) * amp * 0.8
            scale = 1.0 + 0.16 * wind
            return x, y, scale

        if self.state in ("swap", "swapback") and self.pair and (r, c) in self.pair:
            a, b = self.pair
            other = b if (r, c) == a else a
            p = (ease_back(self.t) if self.state == "swap"
                 else 1 - ease_in_out(self.t))
            x += (other[1] - c) * TILE * p
            y += (other[0] - r) * TILE * p
            # a small arc so the two gems visibly pass one another
            lift = math.sin(clamp01(self.t if self.state == "swap"
                                    else 1 - self.t) * math.pi)
            scale += 0.07 * lift

        elif self.state == "clear" and (r, c) in self.matched:
            # swell a touch before collapsing - a gem that only shrinks reads
            # as fading out, one that pops first reads as being destroyed
            if self.t < 0.22:
                scale = 1.0 + 0.16 * ease_out(self.t / 0.22)
            else:
                scale = 1.16 * max(0.0, 1.0 - ease_in_out((self.t - 0.22) / 0.78))

        elif self.state == "fall" and (r, c) in self.falls:
            d = self.falls[(r, c)]
            # longer drops get a slightly softer landing, so a gem falling
            # eight rows does not arrive at the same speed as one falling one
            curve = ease_bounce(self.t) if d >= 3 else ease_out(self.t)
            y -= d * TILE * (1 - curve)

        elif self.state == "intro":
            # each column starts a little later, so the board lands left to right
            p = clamp01((self.t * INTRO_TIME - c * INTRO_STAGGER) / INTRO_FALL)
            y -= (ROWS + 2) * TILE * (1 - ease_bounce(p))

        elif self.state == "levelup":
            # old board peels away diagonally before the next one drops
            delay = (r + c) / (ROWS + COLS) * 0.30
            p = clamp01((self.t * self.levelup_pause() - delay) / 0.40)
            scale = 1.0 - ease_in_out(p)
            y -= 30 * p

        if (r, c) in self.pops:
            p = 1.0 - self.pops[(r, c)] / POP_TIME
            scale *= 1.0 + 0.5 * (1 - p) * math.cos(p * 13.0) * (1 - p)

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

        if not self.scoring:
            # Zen keeps no score, so the readouts would only ever show 0
            zen = self.font_score.render("ZEN", True, GOLD)
            screen.blit(zen, (x, PANEL_Y + 40))
            for button in self.buttons:
                button.draw(screen, self.font)
            if self.note:
                self.wrapped(screen, self.note, x, PANEL_Y + 208, width, GOLD)
            track = self.audio.now_playing()
            if track:
                screen.blit(self.font_small.render("NOW PLAYING", True, DIM),
                            (x, PANEL_Y + PANEL_H - 250))
                self.wrapped(screen, track, x, PANEL_Y + PANEL_H - 232,
                             width, DIM)
            return

        screen.blit(self.font_small.render("SCORE", True, DIM), (x, PANEL_Y + 26))
        screen.blit(self.font_score.render(f"{self.score:,}", True, TEXT),
                    (x, PANEL_Y + 48))

        if self.timed:
            low = self.time_left <= LOW_TIME
            pulse = 0.5 + 0.5 * math.sin(self.time * 6.0)
            color = ((255, int(90 + 60 * pulse), int(90 + 40 * pulse)) if low
                     else TEXT)
            secs = int(math.ceil(self.time_left))
            screen.blit(self.font_small.render("TIME", True, DIM),
                        (x, PANEL_Y + 116))
            screen.blit(self.font_score.render(f"{secs // 60}:{secs % 60:02d}",
                                               True, color), (x, PANEL_Y + 138))
            screen.blit(self.font_small.render(f"LEVEL {self.level}", True, DIM),
                        (x, PANEL_Y + 182))
        else:
            screen.blit(self.font_small.render("LEVEL", True, DIM),
                        (x, PANEL_Y + 116))
            screen.blit(self.font_score.render(str(self.level), True, TEXT),
                        (x, PANEL_Y + 138))

        # The bar always shows progress toward the next level. In timed mode
        # the clock has its own readout above, so mirroring it here left no
        # indication of how close the next level was.
        self.bar(screen, x, PANEL_Y + (200 if self.timed else 184), width, 10,
                 self.level_progress(), GOLD)

        if self.extra("lock"):
            y = PANEL_Y + 250
            screen.blit(self.font_small.render("SCORING", True, DIM), (x, y))
            sprite = self.normal[self.lock_kind]
            screen.blit(sprite, (x, y + 20))
            secs = max(0, int(math.ceil(self.lock_left)))
            screen.blit(self.font_score.render(str(secs), True,
                        (232, 96, 96) if secs <= 3 else TEXT),
                        (x + TILE + 12, y + 36))
            self.bar(screen, x, y + TILE + 26, width, 8,
                     self.lock_left / LOCK_SECONDS, (176, 140, 240))

        mode = self.font_small.render("TIMED" if self.timed else "ENDLESS",
                                      True, DIM)
        screen.blit(mode, (PANEL_X + PANEL_W - 16 - mode.get_width(),
                           PANEL_Y + 28))

        if self.note:
            self.wrapped(screen, self.note, x, PANEL_Y + 214, width, GOLD)

        track = self.audio.now_playing()
        if track:
            screen.blit(self.font_small.render("NOW PLAYING", True, DIM),
                        (x, PANEL_Y + PANEL_H - 252))
            self.wrapped(screen, track, x, PANEL_Y + PANEL_H - 230, width, DIM)

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

    def draw_holes(self, screen, opaque=False):
        """Black out the cells that are not part of a Shapes silhouette.

        Drawn twice: once under the gems so the board reads as a shape, and
        again over them, because a gem falling into a lower row passes
        visually through any hole above it.
        """
        if self.mode != SHAPES:
            return
        shade = (0, 0, 0, 255) if opaque else (0, 0, 0, 150)
        tile = translucent((TILE, TILE), shade, None, 0)
        for r in range(ROWS):
            for c in range(COLS):
                cell = self.grid[r][c]
                if cell is not None and cell.cell_type == CELL_EMPTY:
                    screen.blit(tile, (BOARD_X + c * TILE, BOARD_Y + r * TILE))

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
        # nearest-neighbour: smoothscale would blur the pixel type back out
        resize = (pygame.transform.scale if art is None
                  else pygame.transform.smoothscale)
        image = resize(image, size)

        # The halo is the image's own shape blown up slightly, NOT a filled
        # rectangle - filling the bounding box is what produced a white block.
        halo = resize(image, (int(size[0] * 1.16), int(size[1] * 1.16)))
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

    def draw_music(self, screen):
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((8, 9, 13, 190))
        screen.blit(veil, (0, 0))
        box = self.music_rect()
        screen.blit(translucent(box.size, PANEL_FILL, PANEL_EDGE, 16),
                    box.topleft)
        title = self.font_big.render("MUSIC", True, TEXT)
        screen.blit(title, (box.x + 24, box.y + 24))
        hint = self.font_small.render("SCROLL WHEEL", True, DIM)
        screen.blit(hint, (box.right - 24 - hint.get_width(), box.y + 30))
        self.music_list.draw(screen, self.font)
        for button in self.music_buttons:
            button.draw(screen, self.font)

    def draw_menu(self, screen):
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((8, 9, 13, 190))
        screen.blit(veil, (0, 0))

        box = self.menu_rect()
        screen.blit(self.menu_bg, box.topleft)

        title = self.font_big.render("MENU", True, TEXT)
        screen.blit(title, (box.x + 30, box.y + 26))

        # Pixel glyphs are far wider per character than proportional type, so
        # this sits under the title rather than beside it, and stays short.
        hint = self.font_small.render("ESC TO CLOSE", True, DIM)
        screen.blit(hint, (box.right - 30 - hint.get_width(),
                           box.y + 26 + title.get_height() - hint.get_height()))

        for key, rect, label, blurb in self.setting_rows:
            on = self.settings.get(key, True)
            screen.blit(translucent(rect.size,
                                    GOLD + (60,) if on else (255, 255, 255, 18),
                                    None, 8), rect.topleft)
            tick = pygame.Rect(rect.x + 8, rect.centery - 10, 20, 20)
            pygame.draw.rect(screen, TEXT if on else DIM, tick, 2,
                             border_radius=4)
            if on:
                pygame.draw.line(screen, GOLD, (tick.x + 4, tick.centery),
                                 (tick.centerx, tick.bottom - 5), 3)
                pygame.draw.line(screen, GOLD, (tick.centerx, tick.bottom - 5),
                                 (tick.right - 3, tick.y + 3), 3)
            name = self.font.render(label, True, TEXT if on else DIM)
            screen.blit(name, (rect.x + 38, rect.y + 5))
            note = Button.fit(self.font_small, blurb, rect.width - 46)
            screen.blit(note.render(blurb, True, DIM),
                        (rect.x + 38, rect.y + 5 + name.get_height() + 4))

        for slider in self.sliders:
            slider.draw(screen, self.font, self.font_small,
                        dragging=self.dragging is slider)

        head = self.font_small.render("GRAPHICS", True, DIM)
        screen.blit(head, (box.x + 30, box.y + 210))
        for key, rect, label, blurb in self.setting_rows:
            on = self.settings.get(key, True)
            screen.blit(translucent(rect.size,
                                    GOLD + (60,) if on else (255, 255, 255, 18),
                                    None, 8), rect.topleft)
            tick = pygame.Rect(rect.x + 8, rect.centery - 10, 20, 20)
            pygame.draw.rect(screen, TEXT if on else DIM, tick, 2,
                             border_radius=4)
            if on:
                pygame.draw.line(screen, GOLD, (tick.x + 4, tick.centery),
                                 (tick.centerx, tick.bottom - 5), 3)
                pygame.draw.line(screen, GOLD, (tick.centerx, tick.bottom - 5),
                                 (tick.right - 3, tick.y + 3), 3)
            name = self.font.render(label, True, TEXT if on else DIM)
            screen.blit(name, (rect.x + 38, rect.y + 5))
            note = Button.fit(self.font_small, blurb, rect.width - 46)
            screen.blit(note.render(blurb, True, DIM),
                        (rect.x + 38, rect.y + 5 + name.get_height() + 4))

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
        if self.on_title:
            self.draw_title(screen)
            return
        offset = self.shake_offset()
        if offset == (0, 0):
            target = screen
        else:
            if self.frame is None:
                self.frame = pygame.Surface((WIDTH, HEIGHT))
            target = self.frame

        if self.state in ("flyoff", "banner"):
            self.draw_transition(target)
        else:
            self.draw_scene(target)

        if target is not screen:
            # Blow the frame up just enough that the shake offset can never
            # slide a bare edge into view.
            pad = SHAKE_MAX + 2
            big = pygame.transform.smoothscale(
                target, (WIDTH + pad * 2, HEIGHT + pad * 2))
            screen.blit(big, (offset[0] - pad, offset[1] - pad))

    def draw_transition(self, screen):
        """Gems flying off, then the LEVEL banner over an empty board."""
        self.draw_scene(screen)          # background, panel, empty board
        if self.state == "rainbow":
            self.update_rainbow(dt)
            return

        if self.state == "flyoff":
            for flyer in self.flyers:
                flyer.draw(screen)
            return

        dx, alpha = self.banner_pose()
        alpha = max(0, min(255, alpha))
        cx = BOARD_X + BOARD_W // 2 + dx
        cy = BOARD_Y + BOARD_H // 2
        image = self.banner
        if image is None:
            image = self.font_huge.render("LEVEL UP", True, TEXT)
        shown = image.copy()
        shown.set_alpha(alpha)
        screen.blit(shown, shown.get_rect(center=(cx, cy)))

        label = self.font_score.render(f"LEVEL {self.level}", True, TEXT)
        label.set_alpha(alpha)
        screen.blit(label, label.get_rect(
            center=(cx, cy + image.get_height() // 2 + 26)))

    def update_motes(self, dt):
        if not self.settings.get("particles", True):
            return
        for m in self.motes:
            m[0] += math.sin(self.time * 0.4 + m[2]) * 6 * dt
            m[1] += m[3] * dt
            if m[1] < -m[2]:
                m[1] = HEIGHT + m[2]
                m[0] = random.uniform(0, WIDTH)

    def draw_motes(self, screen):
        if not self.settings.get("particles", True):
            return
        layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        for x, y, size, _, alpha in self.motes:
            pygame.draw.circle(layer, (150, 175, 255, int(alpha * 30)),
                               (int(x), int(y)), max(1, int(size)))
        screen.blit(layer, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

    def draw_scene(self, screen, background=True):
        if not background:
            screen.fill((0, 0, 0, 0))       # UI only, on transparency
        else:
            photo = self.background_for_level()
            if photo is None:
                screen.fill(BG)
            else:
                screen.blit(photo, (0, 0))
        self.draw_motes(screen)
        self.draw_panel(screen)

        screen.blit(self.board_bg, (BOARD_X, BOARD_Y))
        if self.mode == SHAPES:
            self.draw_holes(screen)

        if self.sel is not None:
            r, c = self.sel
            grow = int(3 * (0.5 + 0.5 * math.sin(self.time * 6.0)))
            pygame.draw.rect(screen, (255, 255, 255),
                             (BOARD_X + c * TILE, BOARD_Y + r * TILE, TILE, TILE), 3,
                             border_radius=6)

        clip = screen.get_clip()
        screen.set_clip(pygame.Rect(BOARD_X, BOARD_Y, COLS * TILE, ROWS * TILE))
        for r in range(ROWS):
            for c in range(COLS):
                gem = self.grid[r][c]
                if gem is None or gem.cell_type == CELL_EMPTY:
                    continue          # a hole in a Shapes board: show nothing
                if (self.state == "rainbow"
                        and (r, c) in self.rainbow_all
                        and (r, c) in self.rainbow_targets[:self.rainbow_done]):
                    continue          # already zapped
                x, y, scale = self.gem_draw_info(r, c)
                sprite = self.sprite_for(gem)
                if (gem.cell_type == CELL_GEM and gem.power != NORMAL
                        and scale > 0.05):
                    self.draw_behind(screen, gem, x, y)
                if abs(scale - 1.0) > 0.001:
                    if scale <= 0.02:
                        continue
                    s = max(1, int(TILE * scale))
                    sprite = pygame.transform.smoothscale(sprite, (s, s))
                    x += (TILE - s) / 2
                    y += (TILE - s) / 2
                screen.blit(sprite, (int(x), int(y)))
                if gem.cell_type == CELL_BOMB:
                    self.draw_fuse(screen, gem, x, y)
                elif gem.bonus:
                    self.draw_bonus_tag(screen, x, y)
        for puff in self.puffs:
            puff.draw(screen)
        for effect in self.effects:
            effect.draw(screen)
        for pop in self.time_pops:
            pop.draw(screen, self.font_big)
        screen.set_clip(clip)
        if self.state == "rainbow":
            self.draw_rainbow(screen)
        self.draw_holes(screen, opaque=True)
        self.draw_hint(screen)
        if self.go_left > 0:
            self.draw_go(screen)

        if self.state == "levelup":
            self.draw_levelup(screen)
        if self.menu_open:
            self.draw_menu(screen)
        if self.music_open:
            self.draw_music(screen)
        if self.over:
            self.draw_over(screen)


# --------------------------------------------------------------------------

def main():
    # This line has to come BEFORE pygame.init(). The default mixer buffer is
    # 4096 samples, which puts a very audible delay between clicking a gem and
    # hearing it pop. 512 makes the feedback feel instant.
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
    pygame.init()
    pygame.display.set_caption("Match Three")
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
    for label, name in (("smoke", SMOKE_ASSET),):
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

    describe_assets()

    backgrounds = load_backgrounds()
    if not backgrounds:
        print("No backgrounds found - using a generated one so the "
              "translucent UI still reads.\n")
        backgrounds = [fallback_background()]
    if backgrounds:
        print(f"{len(backgrounds)} backgrounds loaded, one per level\n")
    elif os.path.isdir(BACKGROUND_DIR):
        print(f"No images found in {BACKGROUND_DIR}\n")

    skin = load_ui_skin()
    if skin:
        print("UI skin: " + ", ".join(sorted(skin)) + "\n")
    elif os.path.isdir(UI_DIR):
        print(f"No skin images found in {UI_DIR}\n")

    game = Game(sprites, audio, effects, backgrounds, skin)

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    if game.dev_open:
                        game.close_dev()
                    elif game.music_open:
                        game.close_music()
                    elif game.menu_open:
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
                    game.open_music()
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
            elif e.type == pygame.MOUSEWHEEL and game.music_open:
                game.music_list.scroll(-e.y)
            elif e.type == pygame.MOUSEWHEEL and game.dev_open:
                game.dev_sounds.scroll(-e.y)

        if game.wants_quit:
            pygame.quit()
            sys.exit()

        game.update(dt)
        game.draw(screen)
        pygame.display.flip()


if __name__ == "__main__":
    main()
