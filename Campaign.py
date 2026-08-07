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
import json
import math
import os
import random
import sys
from pathlib import Path

import pygame

try:
    import numpy as np           # optional: only used to pitch-shift cascades
except ImportError:
    np = None

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

COLS, ROWS = 9, 9

# --- render scale ---------------------------------------------------------
# The whole UI is authored at 1080x810 and every pixel number in the layout
# and drawing code goes through S(). Raising RENDER_SCALE redraws the game
# into a larger layer - gems, glyphs and panels are all genuinely rendered at
# that size rather than blown up afterwards, which is the only thing that
# actually adds detail. Display still fits the layer to the screen, so the
# picture stays the same size and simply gets sharper.
BASE_WIDTH, BASE_HEIGHT = 1080, 810
BASE_TILE = 83
BASE_MARGIN = 27
BASE_GEM_PAD = 3
BASE_PANEL_W = 248
BASE_PANEL_Y = 30
BASE_EXTRA_ROW = 52
BASE_FONTS = {"huge": 7, "score": 5, "big": 3, "body": 2, "small": 2}

RENDER_SCALE = 1.0


def S(n):
    """Scale an authored 1080x810 pixel number to the current render scale."""
    return int(n * RENDER_SCALE)


def font_scale(name):
    """Pixel-font scale for a role.

    The 5x7 bitmap face only scales in whole numbers - fractional scaling is
    exactly what makes it mushy - so at 125% and 150% the type cannot land
    exactly in proportion. Rounding down errs slightly small, which keeps the
    airy padding the layout was designed around; rounding up left text
    crowding the edges of its rows. 100% and 200% land exactly either way.
    """
    return max(1, int(BASE_FONTS[name] * RENDER_SCALE))


WIDTH, HEIGHT = BASE_WIDTH, BASE_HEIGHT
TILE = BASE_TILE
MARGIN = BASE_MARGIN
GEM_PAD = BASE_GEM_PAD
PANEL_W = BASE_PANEL_W
PANEL_Y = BASE_PANEL_Y
EXTRA_ROW = BASE_EXTRA_ROW
FONT_SCALE = BASE_FONTS["big"]

PANEL_X = MARGIN
PANEL_H = HEIGHT - PANEL_Y * 2
BOARD_W = BOARD_H = COLS * TILE
BOARD_X = PANEL_X + PANEL_W + S(26)
BOARD_Y = (HEIGHT - BOARD_H) // 2


def apply_render_scale(k):
    """Recompute every scale-dependent module constant."""
    global RENDER_SCALE, WIDTH, HEIGHT, TILE, MARGIN, GEM_PAD, PANEL_W
    global PANEL_Y, EXTRA_ROW, FONT_SCALE, PANEL_X, PANEL_H
    global BOARD_W, BOARD_H, BOARD_X, BOARD_Y
    RENDER_SCALE = float(k)
    WIDTH, HEIGHT = S(BASE_WIDTH), S(BASE_HEIGHT)
    TILE = S(BASE_TILE)
    MARGIN = S(BASE_MARGIN)
    GEM_PAD = max(1, S(BASE_GEM_PAD))
    PANEL_W = S(BASE_PANEL_W)
    PANEL_Y = S(BASE_PANEL_Y)
    EXTRA_ROW = S(BASE_EXTRA_ROW)
    FONT_SCALE = font_scale("big")
    PANEL_X = MARGIN
    PANEL_H = HEIGHT - PANEL_Y * 2
    BOARD_W = BOARD_H = COLS * TILE
    BOARD_X = PANEL_X + PANEL_W + S(26)
    BOARD_Y = (HEIGHT - BOARD_H) // 2


# Internal render resolution, offered in fullscreen. Higher settings render
# more pixels for the same on-screen size, so the picture gets sharper rather
# than bigger.
# (factor, label)
SCALE_OPTIONS = (
    (1.00, "100%"),
    (1.25, "125%"),
    (1.50, "150%"),
    (2.00, "200%"),
)
DEFAULT_RENDER_SCALE = 1.00

HINT_SECONDS = 4.0          # how long a hint stays lit

FPS = 60

# progression
LEVEL_BASE_TARGET = 1200   # points needed to clear level 1
LEVEL_GROWTH = 1.35        # each level needs this much more than the last

# timed mode
ENDLESS, TIMED, TITLE = "endless", "timed", "title"
TIMED_MUSIC_MODE = "timedmusic"   # an Extras run that is on the clock
CREDITS_MODE = "credits"          # the credits roll has its own track
SECRET_MUSIC_MODE = "secret"      # the hidden playlist, found from the picker
SHAPES, EXTRAS, CHAOS = "shapes", "extras", "chaos"
CAMPAIGN = "campaign"
CAMPAIGN_MUSIC_MODE = "campaignmusic"   # the current area's own tracks

# Ten areas, in order. The name is also the folder looked for inside
# campaign/ - campaign/Beach/ holds that area's backdrop and music.
CAMPAIGN_AREAS = (
    "Beach", "Dock", "City", "Forest", "Mine",
    "Cave", "Crystal Cavern", "Volcanic Core", "Underground City", "The Deep",
)
LEVELS_PER_AREA = 5
CAMPAIGN_LEVELS = len(CAMPAIGN_AREAS) * LEVELS_PER_AREA

# Objective kinds. Each is a small, legible challenge:
#   score - reach a score inside a move budget
#   gems  - clear a number of gems inside a move budget
#   time  - reach a score before the clock runs out
GOAL_SCORE, GOAL_GEMS, GOAL_TIME = "score", "gems", "time"


# Modifiers thrown into later levels. ZEN is deliberately absent: it turns
# scoring off, which would make every objective impossible.
CAMPAIGN_MODIFIERS = ("mono", "boom", "lock", "spotlight", "chaos")


def campaign_modifiers(area, step):
    """Which Extras modifiers a level runs with.

    The first two areas are clean so the basics can be learned. After that a
    modifier appears on the harder steps of each area, a second one from the
    Volcanic Core, and The Deep finishes on three at once. Which modifiers
    appear rotates with the area so the run keeps changing shape.
    """
    if area < 2:
        return ()
    slots = 1 + (area >= 7) + (area >= 9)
    # Only the back half of each area carries them, so every area opens with
    # a clean level before it complicates things.
    if step < 5 - slots - (0 if area >= 7 else 1):
        return ()
    picks = []
    for i in range(slots):
        picks.append(CAMPAIGN_MODIFIERS[(area + step + i * 2) % len(CAMPAIGN_MODIFIERS)])
    return tuple(dict.fromkeys(picks))


def campaign_level(number):
    """The objective for level `number` (1-based, continuous across areas).

    Difficulty is generated rather than hand-listed so the curve stays smooth
    across all fifty: targets climb with the area while the budget tightens,
    and the three goal kinds rotate so no area is five of the same task.
    """
    number = max(1, min(CAMPAIGN_LEVELS, int(number)))
    area = (number - 1) // LEVELS_PER_AREA          # 0..9
    step = (number - 1) % LEVELS_PER_AREA           # 0..4
    kind = (GOAL_SCORE, GOAL_GEMS, GOAL_SCORE, GOAL_TIME, GOAL_SCORE)[step]

    # Area sets the scale, step raises it within the area.
    ramp = 1.0 + area * 0.55 + step * 0.16
    mods = campaign_modifiers(area, step)

    if kind == GOAL_GEMS:
        target = int(round((26 + area * 7 + step * 4) / 2.0) * 2)
        budget = max(6, 22 + area - step * 2)
        return {"kind": kind, "target": target, "moves": budget,
                "extras": mods,
                "text": f"CLEAR {target} GEMS IN {budget} MOVES"}
    if kind == GOAL_TIME:
        target = int(round(900 * ramp / 50.0) * 50)
        seconds = max(30, 75 - area * 3)
        return {"kind": kind, "target": target, "seconds": float(seconds),
                "extras": mods,
                "text": f"SCORE {target:,} IN {seconds}S"}
    target = int(round(700 * ramp / 50.0) * 50)
    budget = max(5, 20 + area - step * 3)
    return {"kind": kind, "target": target, "moves": budget,
            "extras": mods,
            "text": f"SCORE {target:,} IN {budget} MOVES"}


def campaign_modifier_label(goal):
    """'MONO + COLOR LOCK' for a level's modifiers, or '' if it has none."""
    names = {k: label for k, label, _ in EXTRA_DEFS}
    mods = (goal or {}).get("extras", ())
    return " + ".join(names.get(k, k.upper()) for k in mods)


def campaign_area_of(number):
    return max(0, min(len(CAMPAIGN_AREAS) - 1,
                      (int(number) - 1) // LEVELS_PER_AREA))

# Extras: modifiers the player can stack. Each is (key, label, blurb).
EXTRA_DEFS = (
    ("zen",     "ZEN",            "No Clock/Score"),
    ("mono",    "MONO",           "Black & White"),
    ("boom",    "EXPLOSIVES",     "Explosive Gems Spawn Freely"),
    ("lock",    "COLOR LOCK",    "One Color Scores (Swaps Every 10s)"),
    ("spotlight", "SPOTLIGHT",    "Only A Circle Around Your Cursor"),
    ("chaos",   "CHAOS",          "???"),
)
LOCK_SECONDS = 10.0
# Panel buttons a campaign level takes over, since the area picks both.
LOCKED_IN_CAMPAIGN = ("BACKGROUNDS", "MUSIC")
# Row height in the level picker. campaign_rect() and
# build_campaign_widgets() both derive from this, so it can only be
# changed in one place.
CAMPAIGN_ROW_H = 64
CAMPAIGN_ROW_GAP = 10
SPOTLIGHT_RADIUS = 132     # lit radius around the cursor, authored px
SPOTLIGHT_FEATHER = 46     # soft edge on the spotlight, authored px

# graphics toggles, both on by default and switchable from the title menu
SETTING_DEFS = (
    ("fullscreen",  "FULLSCREEN",   "Fills Screen to Aspect Ratio"),
    ("backgrounds", "BACKGROUNDS",  "Show Level Artwork"),
    ("opaque",      "REDUCE TRANSPARENCY", "Solid Panels And Buttons"),
    ("smooth",      "SMOOTH ANIMATION", "Smooth Gem Animations"),
    ("shake",     "CAMERA SHAKE",        "Screen Shakes on Explosions"),
    ("particles", "BACKGROUND PARTICLES", "Small Particle Effects"),
)

# Resolution options for the game window
# (width, height, label, description)

PARTICLE_COUNT = 46

# rainbow gem detonation: a short charge, then the targets zapped one by one
RAINBOW_CHARGE = 0.55      # hypercube shaking before anything pops
RAINBOW_STEP = 0.055       # gap between each gem being taken out
RAINBOW_TAIL = 0.30        # a beat after the last one
RAINBOW_MAX = 1.9          # hard ceiling, so a board wipe cannot drag
CHAIN_STEP = 0.10          # delay between chained explosion steps
ZAP_EVERY = 2              # play the zap sound on every Nth gem
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
SHAKE_RAMP = 0.06        # very fast ramp up
SHAKE_FLYOFF = 4.5       # reduced intensity
SHAKE_DECAY = 1.8        # much faster decay for quick fade out (was 0.5)
SHAKE_BOMB = 3.0         # reduced
SHAKE_RAINBOW = 4.5      # reduced
SHAKE_FLAME = 3.0        # reduced
SHAKE_MAX = 10.0         # reduced (was 15.0)

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

BG_CROSSFADE = 2.6         # seconds for the new level backdrop to slide up

# Level backdrops do not composite correctly on macOS: in fullscreen the
# letterboxed area comes out black while the bars show the photo. Until that
# is tracked down, backgrounds default to off there and the slide between
# them is skipped entirely. The toggle is still in the menu, so it can be
# switched back on to test.
IS_MACOS = sys.platform == "darwin"
BACKDROPS_OK = not IS_MACOS
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
# Dialog boxes are NOT glass: the side panel wants to show the board through
# it, but a menu you are reading needs to be solid.
DIALOG_FILL = (28, 33, 56, 250)
DIALOG_EDGE = (128, 148, 214, 190)
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


def get_saves_dir():
    """Get the Prismac Saves folder in the user's Documents directory.
    
    This is cross-platform compatible for Mac and Windows.
    Creates the directory if it doesn't exist.
    
    Returns:
        str: Path to the Prismac Saves folder
    """
    # Get Documents folder (works on Mac, Windows, and Linux)
    documents = Path.home() / "Documents"
    
    # Create Prismac Saves subfolder
    saves_dir = documents / "Prismac Saves"
    saves_dir.mkdir(parents=True, exist_ok=True)
    
    return str(saves_dir)


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
BACKGROUND_FADE_TIME = 0.8
UI_DIR = asset_folder("ui")
CHAOS_DIR = asset_folder("chaos")
TITLE_DIR = asset_folder("title")
CAMPAIGN_DIR = asset_folder("campaign")
CREDITS_DIR = asset_folder("credits")

# Save files now go to Documents/Prismac Saves (cross-platform)
SAVES_DIR = get_saves_dir()
SAVE_FILE = os.path.join(SAVES_DIR, "prismac_save.json")
SETTINGS_FILE = os.path.join(SAVES_DIR, "prismac_settings.json")
# "smooth animation" off keeps the same timings but drops the springiness
WIPE_HOLD = 3.0            # seconds YES must be held to erase save data
RESUME_HOLD = 1.5          # seconds NO must be held to bin a saved run
SAVED_MODES = (ENDLESS, SHAPES) if False else ("endless", "shapes")

# The credits roll. ("h", ...) is a heading, ("r", ...) a rule, ("", ...)
# a plain line, and ("s", ...) a blank spacer.
CREDITS_TEXT = (
    ("t", "PRISMAC"),
    ("s", ""), ("s", ""),

    ("h", "CREATED BY"), ("r", ""),
    ("b", "TY FUKUSHIMA"),
    ("s", ""), ("s", ""),

    ("h", "GAME DESIGN"), ("r", ""),
    ("", "GAME DESIGN"), ("b", "TY FUKUSHIMA"),
    ("", "GAMEPLAY DESIGN"), ("b", "TY FUKUSHIMA"),
    ("", "LEVEL AND MODE DESIGN"), ("b", "TY FUKUSHIMA"),
    ("", "SYSTEMS DESIGN"), ("b", "TY FUKUSHIMA"),
    ("s", ""), ("s", ""),

    ("h", "PROGRAMMING"), ("r", ""),
    ("", "LEAD PROGRAMMER"), ("b", "TY FUKUSHIMA"),
    ("", "ENGINE / FRAMEWORK"), ("b", "PYTHON, PYGAME"),
    ("", "PROGRAMMING ASSISTANCE"),
    ("b", "CLAUDE CODE"), ("b", "CHATGPT CODEX"),
    ("s", ""), ("s", ""),

    ("h", "ART AND DESIGN"), ("r", ""),
    ("", "ART DIRECTION"), ("b", "TY FUKUSHIMA"),
    ("", "UI / INTERFACE DESIGN"), ("b", "TY FUKUSHIMA"),
    ("", "VISUAL DESIGN"), ("b", "TY FUKUSHIMA"),
    ("", "PIXEL ART EDITING"), ("b", "TY FUKUSHIMA"),
    ("s", ""), ("s", ""),

    ("h", "AUDIO DIRECTION"), ("r", ""),
    ("", "AUDIO SELECTION"), ("b", "TY FUKUSHIMA"),
    ("", "MUSIC AND SOUND INTEGRATION"), ("b", "TY FUKUSHIMA"),
    ("s", ""), ("s", ""),

    ("h", "EFFECTS"), ("r", ""),
    ("b", "TY FUKUSHIMA"),
    ("s", ""), ("s", ""),

    ("h", "ART ASSETS"), ("r", ""),
    ("", "GEM ASSETS"),
    ("b", "COLORED GEMS"), ("b", "BY B2719680"),
    ("s", ""),
    ("", "ADDITIONAL ARTWORK"),
    ("b", "RAINBOW, ROCK AND BOMB GEMS"),
    ("b", "CREATED IN ADOBE PHOTOSHOP"),
    ("s", ""),
    ("", "PIXEL ART BACKGROUNDS"),
    ("b", "PIXEL ART BACKGROUNDS 10"),
    ("b", "SKY CLOUD - BY ARLUDUS"),
    ("s", ""),
    ("b", "PIXEL ART BACKGROUNDS"), ("b", "BY FLORESWA"),
    ("s", ""),
    ("b", "VARIOUS BACKGROUNDS"), ("b", "BY STEALTHIX"),
    ("s", ""),
    ("b", "SWAMP PIXEL GAME BACKGROUNDS"),
    ("b", "BY FREE GAME ASSETS"),
    ("s", ""),
    ("", "OTHER BACKGROUND SOURCES"),
    ("b", "VECTEEZY"), ("b", "PIXABAY"),
    ("b", "FREEPIK"), ("b", "ADOBE STOCK"),
    ("s", ""),
    ("", "COMMUNITY INSPIRATION"),
    ("b", "R/KINGDOMHEARTS"), ("b", "R/PIXELART"),
    ("s", ""), ("s", ""),

    ("h", "SOUND EFFECTS"), ("r", ""),
    ("b", "UNIVERSAL UI/MENU SOUNDPACK"),
    ("b", "BY CYREX STUDIOS"),
    ("s", ""),
    ("b", "TRIPLE TREAT"),
    ("b", "SOUND EFFECTS FOR MATCH-3 GAMES"),
    ("b", "BY SABLE BLOOM"),
    ("s", ""),
    ("", "INSPIRED BY"),
    ("b", "BEJEWELED (2001)"),
    ("b", "BEJEWELED 2 DELUXE (2004)"),
    ("b", "BY POPCAP GAMES"),
    ("s", ""), ("s", ""),

    ("h", "MUSIC AND AUDIO"), ("r", ""),
    ("", "PIXABAY FREE USE MUSIC"),
    ("b", "PRIVATE CHAN"), ("b", "DJARTMUSIC"),
    ("b", "NOCOPYRIGHTSOUNDS633"), ("b", "MOODMODE"),
    ("b", "RETRO-BGM-CHAN"), ("b", "NIKNET_ART"),
    ("s", ""),
    ("", "YOUTUBE"), ("b", "8-BIT UNIVERSE"),
    ("s", ""),
    ("", "FEATURED SONGS"),
    ("b", "SIMPLE AND CLEAN"), ("b", "HIKARU UTADA"),
    ("s", ""),
    ("b", "ROXAS"), ("b", "YOKO SHIMOMURA"),
    ("s", ""),
    ("b", "BLUE (DA BA DEE)"), ("b", "EIFFEL 65"),
    ("s", ""),
    ("b", "GET LUCKY"), ("b", "DAFT PUNK"),
    ("s", ""),
    ("b", "LAST FRIDAY NIGHT"), ("b", "KATY PERRY"),
    ("s", ""),
    ("b", "SMELLS LIKE TEEN SPIRIT"), ("b", "NIRVANA"),
    ("s", ""), ("s", ""),

    ("h", "SPECIAL THANKS"), ("r", ""),
    ("b", "THE CREATORS WHO SHARE ASSETS"),
    ("b", "WITH THE GAME DEV COMMUNITY"),
    ("s", ""),
    ("b", "EVERYONE WHO PLAYTESTED PRISMAC"),
    ("s", ""), ("s", ""),

    ("h", "LEGAL NOTICE"), ("r", ""),
    ("b", "PRISMAC IS AN INDEPENDENT,"),
    ("b", "NON-COMMERCIAL FAN PROJECT."),
    ("s", ""),
    ("b", "NOT AFFILIATED WITH, ENDORSED BY OR"),
    ("b", "SPONSORED BY POPCAP GAMES,"),
    ("b", "ELECTRONIC ARTS, DISNEY, SQUARE ENIX"),
    ("b", "OR ANY OTHER REFERENCED CREATOR."),
    ("s", ""),
    ("b", "ALL TRADEMARKS AND COPYRIGHTED WORKS"),
    ("b", "BELONG TO THEIR RESPECTIVE OWNERS."),
    ("b", "THIRD-PARTY ASSETS ARE CREDITED"),
    ("b", "TO THEIR ORIGINAL CREATORS."),
    ("s", ""), ("s", ""),

    ("t", "THANK YOU FOR PLAYING"),
    ("s", ""),
    ("", "(C) 2026 TY FUKUSHIMA"),
    ("s", ""), ("s", ""), ("s", ""),
)

BASE_CREDIT_SPEED = 44     # pixels per second at 100%
CREDIT_GEMS = 20           # gems drifting behind the roll
DEBRIS_MAX = 22            # flying gems on screen at once from explosions
BASE_CREDIT_LINE = 26

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
SECRET_MUSIC_SUBDIR = "secret"
SECRET_TAPS = 5            # taps on the picker title to reveal it

MUSIC_VOLUME = 0.35        # starting music level, 0.0 - 1.0
SFX_START_VOLUME = 0.8     # starting sound-effect level, 0.0 - 1.0
VOLUME_STEP = 0.05         # how much the - and = keys move the slider
BASE_VOL_WIDTH = 150
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
    
    # A rock cannot be MATCHED, but an explosion does destroy it - that is
    # the only way to clear one off the board. Holes are never cleared.
    blast = detonate(g, {rc for rc in clear
                         if g[rc[0]][rc[1]] is not None
                         and (g[rc[0]][rc[1]].cell_type == CELL_BOMB
                              or (g[rc[0]][rc[1]].cell_type == CELL_GEM
                                  and g[rc[0]][rc[1]].power == FLAME))})
    clear = {rc for rc in clear
             if is_clear_cell(g[rc[0]][rc[1]])
             or (g[rc[0]][rc[1]] is not None
                 and g[rc[0]][rc[1]].cell_type == CELL_ROCK
                 and rc in blast)}
    return clear, spawns


def rock_bomb_targets(g, hyper_cell, other_cell):
    """What a rainbow gem destroys when swapped with a rock or bomb.
    
    Rainbow + Rock -> destroy all rocks (including the swapped one)
    Rainbow + Bomb -> destroy all bombs (including the swapped one)
    """
    other = g[other_cell[0]][other_cell[1]]
    cell_type_to_destroy = other.cell_type  # CELL_ROCK or CELL_BOMB
    targets = {(r, c) for r in range(ROWS) for c in range(COLS)
               if g[r][c] is not None and g[r][c].cell_type == cell_type_to_destroy}
    # The swapped cell, and the rainbow gem itself - it is consumed here just
    # as it is when swapped with an ordinary gem.
    targets.add(other_cell)
    targets.add(hyper_cell)
    return targets


def hyper_targets(g, hyper_cell, other_cell):
    """What a hypercube destroys when swapped into `other_cell`."""
    other = g[other_cell[0]][other_cell[1]]
    if other.power == HYPER:
        return {(r, c) for r in range(ROWS) for c in range(COLS) if g[r][c] is not None}
    if other.cell_type in (CELL_ROCK, CELL_BOMB):
        # A rock or bomb has no colour to match on, so fall through to the
        # clear-them-all rule. resolve_swap already routes here, but this
        # keeps the function correct on its own.
        return rock_bomb_targets(g, hyper_cell, other_cell)
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


def campaign_area_dir(area):
    """campaign/<Area Name>/, matched case- and punctuation-insensitively so
    'crystal cavern' and 'CrystalCavern' both work."""
    if not os.path.isdir(CAMPAIGN_DIR):
        return None
    want = _norm(CAMPAIGN_AREAS[area])
    for name in sorted(os.listdir(CAMPAIGN_DIR)):
        path = os.path.join(CAMPAIGN_DIR, name)
        if os.path.isdir(path) and _norm(name) == want:
            return path
    return None


def load_campaign_background(area):
    """The backdrop from that area's folder, scaled to cover the layer."""
    folder = campaign_area_dir(area)
    if folder is None:
        return None
    for filename in sorted(os.listdir(folder)):
        if os.path.splitext(filename)[1].lower() not in (".png", ".webp",
                                                         ".jpg", ".jpeg"):
            continue
        try:
            art = pygame.image.load(os.path.join(folder, filename))
            art = art.convert_alpha() if art.get_alpha() else art.convert()
        except pygame.error:
            continue
        w, h = art.get_size()
        scale = max(WIDTH / w, HEIGHT / h)        # cover, never squashed
        art = pygame.transform.smoothscale(
            art, (int(w * scale + 0.5), int(h * scale + 0.5)))
        canvas = pygame.Surface((WIDTH, HEIGHT))
        canvas.blit(art, ((WIDTH - art.get_width()) // 2,
                          (HEIGHT - art.get_height()) // 2))
        return canvas
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
            art = pygame.image.load(os.path.join(TITLE_DIR, filename))
            art = art.convert_alpha() if art.get_alpha() else art.convert()
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


def read_settings():
    try:
        with open(SETTINGS_FILE, "r") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_settings(data):
    try:
        with open(SETTINGS_FILE, "w") as handle:
            json.dump(data, handle)
    except OSError:
        pass


def read_saves():
    """{mode: state} from disk. A missing or broken file is simply no save."""
    try:
        with open(SAVE_FILE, "r") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_saves(data):
    try:
        with open(SAVE_FILE, "w") as handle:
            json.dump(data, handle)
    except OSError:
        pass                      # a read-only folder should not crash the game


def grid_intact(grid):
    """True when every cell holds something. During the level transition the
    board is deliberately emptied, and there is nothing worth saving then."""
    return all(cell is not None for row in grid for cell in row)


def pack_grid(grid):
    """Grid -> plain lists. A None cell is stored as an empty one so a
    partially-built board can never raise."""
    """Grid -> plain lists.

    Cells can legitimately be None during the level transition, when the
    board has been emptied ready for the new one, so those are stored as
    holes rather than crashing.
    """
    """Grid -> plain lists, so every cell type survives a round trip."""
    return [[([c.cell_type, c.kind, c.power, int(bool(c.bonus)),
               getattr(c, "fuse", 0)] if c is not None
              else [CELL_EMPTY, 0, NORMAL, 0, 0]) for c in row]
            for row in grid]


def unpack_grid(raw):
    """Rebuild a saved grid, or None to mean "deal a fresh board"."""
    """Rebuild a grid, or None if the data does not fit the current board."""
    if not isinstance(raw, list) or len(raw) != ROWS:
        return None
    grid = []
    for row in raw:
        if not isinstance(row, list) or len(row) != COLS:
            return None
        cells = []
        for entry in row:
            try:
                ctype, kind, power, bonus, fuse = entry
            except (TypeError, ValueError):
                return None
            if ctype == CELL_EMPTY:
                cells.append(Gem.empty())
            elif ctype == CELL_ROCK:
                cells.append(Gem.rock())
            elif ctype == CELL_BOMB:
                cells.append(Gem.bomb(int(fuse) or BOMB_FUSE_MIN))
            else:
                if power != HYPER and not (0 <= kind < N_TYPES):
                    return None
                cells.append(Gem(int(kind), int(power), bool(bonus)))
        grid.append(cells)
    return grid


def load_credits_art():
    """background.png and logo.png from credits/."""
    found = {"background": None, "logo": None}
    if not os.path.isdir(CREDITS_DIR):
        return found
    for filename in sorted(os.listdir(CREDITS_DIR)):
        stem, ext = os.path.splitext(filename)
        if ext.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        try:
            art = pygame.image.load(os.path.join(CREDITS_DIR, filename))
        except pygame.error:
            continue
        key = _norm(stem)
        if key.startswith("background"):
            art = art.convert()
            pw, ph = art.get_size()
            f = max(WIDTH / pw, HEIGHT / ph)
            art = pygame.transform.smoothscale(
                art, (int(pw * f + 0.5), int(ph * f + 0.5)))
            canvas = pygame.Surface((WIDTH, HEIGHT))
            canvas.blit(art, ((WIDTH - art.get_width()) // 2,
                              (HEIGHT - art.get_height()) // 2))
            found["background"] = canvas
        elif key.startswith("logo"):
            art = art.convert_alpha()
            target = 168
            w, h = art.get_size()
            found["logo"] = pygame.transform.smoothscale(
                art, (target, max(1, int(h * target / w))))
    return found


def load_backgrounds():
    """Photos from backgrounds/, scaled to cover the window.

    Cover rather than stretch: the image keeps its aspect ratio and the
    overflow is cropped, so nothing ends up squashed.
    """
    shots = []
    failures = []
    if not os.path.isdir(BACKGROUND_DIR):
        print(f"  backgrounds folder not found at {BACKGROUND_DIR}")
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
                path = os.path.join(BACKGROUND_DIR, filename)
                try:
                    photo = pygame.image.load(path)
                except pygame.error as err:
                    # Say so. This used to fail silently, which made a
                    # missing decoder (SDL_image often ships without WEBP on
                    # macOS) look like a black screen with no explanation.
                    print(f"  could not read {filename}: {err}")
                    failures.append(filename)
                    break
                try:
                    # convert() is only an optimisation and its result is tied
                    # to the current display format; if it fails the raw
                    # surface still draws perfectly well.
                    photo = (photo.convert_alpha() if photo.get_alpha()
                             else photo.convert())
                except pygame.error:
                    pass
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
    if failures:
        print(f"  {len(failures)} background(s) could not be decoded. "
              "If they are .webp, re-save them as .png - SDL_image is often "
              "built without WEBP support on macOS.")
    if not shots and names:
        print(f"  found {len(names)} background file(s) but loaded none.")
    return shots


OPAQUE_UI = False          # set by the "reduce transparency" option


def translucent(size, fill, edge=None, radius=14, solid=True):
    """Rounded rect with real alpha. pygame.draw cannot blend alpha straight
    onto the display, so anything see-through has to be built here first.

    Every panel, board and button goes through here, so the reduce-
    transparency option only has to force the alpha up in one place.
    `solid=False` marks the dimming veils, which must stay see-through.
    """
    if OPAQUE_UI and solid and len(fill) == 4 and fill[3] > 0:
        fill = fill[:3] + (255,)
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
        self.credits_playlist = []
        self.secret_playlist = []
        self.campaign_playlist = []
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

        credits_index = self.index_folder(CREDITS_DIR)
        self.credits_playlist = [credits_index[k] for k in sorted(credits_index)]

        timed_dir = os.path.join(MUSIC_DIR, TIMED_MUSIC_SUBDIR)
        timed_index = self.index_folder(timed_dir)
        self.timed_playlist = [timed_index[key] for key in sorted(timed_index)]
        random.shuffle(self.timed_playlist)

        # music/secret/ - only ever reached through the picker easter egg, so
        # it is kept in filename order rather than shuffled.
        secret_dir = os.path.join(MUSIC_DIR, SECRET_MUSIC_SUBDIR)
        secret_index = self.index_folder(secret_dir)
        self.secret_playlist = [secret_index[key] for key in sorted(secret_index)]

        if not self.playlist:
            self.missing.append("music (nothing in music/)")
        if not self.title_playlist:
            self.missing.append("title music (nothing in title/)")
        if not self.timed_playlist:
            self.missing.append(f"timed music (nothing in {TIMED_MUSIC_SUBDIR}/)")
        # secret/ is optional and silent about being empty - that is the point
        if not self.playlist and not self.timed_playlist:
            return

        pygame.mixer.music.set_volume(self.music_volume)
        pygame.mixer.music.set_endevent(MUSIC_END)
        self.use_playlist(TITLE)

    def set_campaign_playlist(self, paths):
        """Point the campaign playlist at one area's folder."""
        changed = paths != self.campaign_playlist
        self.campaign_playlist = list(paths)
        if changed and self.mode == CAMPAIGN_MUSIC_MODE:
            # Already listening to the old area: restart on the new one
            self.playlist_started = False
            self.use_playlist(CAMPAIGN_MUSIC_MODE)

    def active_list(self):
        """Falls back to the main playlist if a set is empty, so the game
        never goes silent."""
        if self.mode == SECRET_MUSIC_MODE and self.secret_playlist:
            return self.secret_playlist
        if self.mode == CAMPAIGN_MUSIC_MODE and self.campaign_playlist:
            return self.campaign_playlist
        if self.mode == CREDITS_MODE and self.credits_playlist:
            return self.credits_playlist
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
        a.credits_playlist = []
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
        self.scale0 = random.uniform(0.28, 0.50) * force  # bigger starting smoke
        self.scale1 = self.scale0 * random.uniform(2.6, 4.0)  # scales up more
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


class ScorePop:
    """A floating point value that drifts up and fades where a match/explosion occurred."""

    LIFE = 1.4
    __slots__ = ("x", "y", "t", "points", "is_rainbow")

    def __init__(self, x, y, points, is_rainbow=False):
        self.x = x
        self.y = y
        self.points = points
        self.is_rainbow = is_rainbow
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        return self.t < self.LIFE

    def draw(self, screen, font):
        progress = self.t / self.LIFE
        
        # White text for regular scores, rainbow for special events
        if self.is_rainbow:
            # Cycle through full rainbow using HSV color space
            # Hue from 0 to 1 represents the full color spectrum
            hue = progress % 1.0
            rgb = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
            color = tuple(int(c * 255) for c in rgb)
            label = font.render(str(self.points), True, color)
        else:
            label = font.render(str(self.points), True, (255, 255, 255))  # white
        
        label = label.copy()
        # Soft fade in over first 0.2s, then fade out
        fade_in = min(1.0, progress * 5.0)  # quick fade in
        fade_out = max(0.0, 1.0 - (progress - 0.6) * 1.67)  # fade out from 60% onwards
        alpha = fade_in * fade_out
        label.set_alpha(int(255 * alpha))
        # Float up 20 pixels over lifetime with slight bounce
        # Add a little bounce using sine wave
        drift = 20 * ease_out(progress)
        bounce = math.sin(progress * math.pi * 2.5) * 2.0  # small bouncy motion
        screen.blit(label, label.get_rect(
            center=(self.x + bounce, self.y - drift)))


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

    def __init__(self, image, x, y, delay, origin=None, force=1.0):
        self.image = self.crop(image)
        self.x, self.y = x, y
        # Thrown outward from a centre: the middle of the board for a level
        # transition, or the blast itself for an explosion.
        cx, cy = origin or (BOARD_X + BOARD_W / 2, BOARD_Y + BOARD_H / 2)
        if abs(x - cx) < 1 and abs(y - cy) < 1:
            angle = random.uniform(0, math.tau)      # sitting on the centre
        else:
            angle = math.atan2(y - cy, x - cx) + random.uniform(-0.5, 0.5)
        speed = random.uniform(620, 1150) * force
        self.dx = math.cos(angle) * speed
        self.dy = math.sin(angle) * speed - random.uniform(120, 300)
        self.spin = random.uniform(-620, 620)
        self.delay = delay
        self.t = 0.0

    def update(self, dt):
        self.t += dt

    def draw_at(self, surface, place, scale):
        """Same motion, but plotted in display coordinates so a gem can fly
        past the edge of the 4:3 area and off the real screen."""
        p = self.t - self.delay
        if p <= 0:
            x, y = place(self.x - TILE / 2, self.y - TILE / 2)
            art = self.image if scale == 1 else pygame.transform.smoothscale(
                self.image, (max(1, int(TILE * scale)),) * 2)
            surface.blit(art, (int(x), int(y)))
            return
        image = pygame.transform.rotozoom(self.image, self.spin * p, scale)
        fade = max(0, int(255 * (1.0 - clamp01(p / 0.75))))
        image.set_alpha(fade)
        cx, cy = place(self.x + self.dx * p,
                       self.y + self.dy * p + 900 * p * p)
        surface.blit(image, image.get_rect(center=(int(cx), int(cy))))

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

    @property
    def ROW(self):
        return S(34)

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
        screen.blit(translucent(self.rect.size, (255, 255, 255, 16), None, S(8)),
                    self.rect.topleft)
        clip = screen.get_clip()
        screen.set_clip(self.rect)
        top = int(self.offset)
        for i in range(top, min(len(self.items), top + self.visible + 1)):
            y = self.rect.y + (i - top) * self.ROW
            if i == self.current:
                screen.blit(translucent((self.rect.width, self.ROW - S(2)),
                                        GOLD + (70,), None, S(6)),
                            (self.rect.x, y))
            elif i == self.hover:
                screen.blit(translucent((self.rect.width, self.ROW - S(2)),
                                        (255, 255, 255, 34), None, S(6)),
                            (self.rect.x, y))
            colour = GOLD if i == self.current else TEXT
            label = Button.fit(font, self.items[i], self.rect.width - S(20))
            image = label.render(self.items[i], True, colour)
            screen.blit(image, (self.rect.x + S(10),
                                y + (self.ROW - image.get_height()) // 2))
        screen.set_clip(clip)

        # scrollbar, only when there is something to scroll to
        if self.max_offset() > 0:
            span = self.rect.height * self.visible / len(self.items)
            pos = (self.rect.height - span) * self.offset / self.max_offset()
            screen.blit(translucent((S(4), int(span)), (255, 255, 255, 110), None, S(2)),
                        (self.rect.right - S(6), self.rect.y + int(pos)))


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

    def draw(self, screen, font, lift=0.0):
        """`lift` (0..1) eases the button up a couple of pixels and widens it
        slightly on hover. It is passed as 0 when smooth animation is off, so
        the button is drawn exactly where it always was."""
        font = self.fit(font, self.label, self.rect.width - S(14))
        if self.down and self.hover:
            fill = BTN_DOWN
        elif self.hover:
            fill = BTN_HOVER
        else:
            fill = BTN
        rect = self.rect
        if lift > 0.01:
            grow = int(round(S(4) * lift))
            rect = self.rect.inflate(grow, grow).move(0, -int(round(S(2) * lift)))
        screen.blit(translucent(rect.size, fill, PANEL_EDGE, S(10)), rect.topleft)
        if self.accent:
            pygame.draw.rect(screen, self.accent,
                             (rect.x, rect.y + S(8), S(3), rect.height - S(16)),
                             border_radius=S(2))
        text = font.render(self.label, True, TEXT if self.hover else (206, 212, 228))
        screen.blit(text, text.get_rect(center=rect.center))


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
        screen.blit(label, (self.rect.x, self.rect.y - small.get_height() - S(8)))
        pct = small.render(f"{int(round(value * 100))}%", True, DIM)
        screen.blit(pct, (self.rect.right - pct.get_width(),
                          self.rect.y - pct.get_height() - S(8)))

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
                           S(9) if dragging else S(8))


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
        # Campaign: which level is being played, which area the picker is
        # showing, and how far the player has got. campaign_unlocked is the
        # highest level they may start.
        self.campaign_level_num = 1
        self.campaign_area = 0
        self.campaign_unlocked = 1
        self.campaign_open = False
        self.campaign_bg = None
        self.campaign_arrows = []
        self.campaign_rows = []
        self.campaign_buttons = []
        self.extras = {k: False for k, _, _ in EXTRA_DEFS}
        self.extra_clock = ENDLESS
        self.extras_note = ""
        # everything on by default except fullscreen, which should not be
        # forced on someone the first time they launch the game
        self.settings = {k: k not in ("fullscreen", "opaque")
                         for k, _, _ in SETTING_DEFS}
        if not BACKDROPS_OK:
            self.settings["backgrounds"] = False
        self.settings_open = False
        self.display = None
        self.credit_armed = False      # first click arms, second opens
        self.credits_open = False
        self.resume_open = False
        self.resume_mode = ENDLESS
        self.data_wiped = False
        self.wipe_open = False
        self.wipe_held = 0.0
        self.fresh_held = 0.0
        # Where the spotlight sits. draw() gets no pointer, so on_motion
        # keeps this current; the board centre is a sane opening position.
        self.mouse = (BOARD_X + BOARD_W // 2, BOARD_Y + BOARD_H // 2)
        self._spot_hole = None
        self._spot_mask = None      # NO on the continue prompt
        self.credit_scroll = 0.0
        self.credits_art = load_credits_art()
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
        self.build_fonts()
        self.timed_duration_picker_open = False
        self.timed_duration_choice = 90.0  # default 1:30
        self.timed_bonus_gems = True
        self.build_widgets()
        self.build_title_widgets()
        self.build_campaign_widgets()
        self.bg_index_override = None  # track current background override
        self.bg_index = 0  # cached random background index
        self.bg_transition_active = False
        self.bg_transition = 0.0
        self.bg_transition_from = None
        self.bg_transition_to = None
        self.bg_picker_open = False
        self.note_time = 0.0  # timer for note fade in/out
        self.reset()

    def build_fonts(self):
        """(Re)build the type at the current render scale. Whole-number scales
        keep the 5x7 bitmap face crisp instead of interpolated."""
        self.font_huge = load_font(font_scale("huge"), bold=True)
        self.font_score = load_font(font_scale("score"), bold=True)
        self.font_big = load_font(font_scale("big"), bold=True)
        self.font = load_font(font_scale("body"))
        self.font_small = load_font(font_scale("small"))

    def build_title(self):
        """Title art with a soft dark halo, so it reads on any background."""
        art = load_title_art()
        if art is None:
            return None
        pad = S(16)
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
        w, h, gap = S(250), S(52), S(12)
        specs = ((("ENDLESS", lambda: self.ask_resume(ENDLESS), GOLD),
                  ("TIMED", lambda: self.ask_resume(TIMED), (126, 216, 150))),
                 (("SHAPES", lambda: self.ask_resume(SHAPES), (232, 150, 96)),
                  ("EXTRAS", self.open_extras, (176, 140, 240))),
                 (("MENU", self.open_settings, (150, 160, 190)),
                  ("QUIT", self.quit, (232, 92, 92))))
        # CAMPAIGN sits above the pairs and spans the full width of both
        # columns, so it reads as the headline mode rather than a sixth
        # option. Everything else shifts down by one row to make room.
        top = S(378)
        self.title_buttons = [
            Button((cx - w - gap // 2, top, w * 2 + gap, h), "CAMPAIGN",
                   self.open_campaign, accent=(96, 200, 232)),
        ]
        for row, pair in enumerate(specs):
            for col, (label, action, accent) in enumerate(pair):
                x = cx - w - gap // 2 + col * (w + gap)
                y = top + (row + 1) * (h + gap)
                self.title_buttons.append(
                    Button((x, y, w, h), label, action, accent=accent))

        # extras chooser
        box = self.extras_rect()
        self.extra_rows = []
        for i, (key, label, blurb) in enumerate(EXTRA_DEFS):
            self.extra_rows.append(
                (key, pygame.Rect(box.x + S(26), box.y + S(70) + i * EXTRA_ROW,
                                  box.width - S(52), EXTRA_ROW - S(6)), label, blurb))
        half = (box.width - S(52) - S(12)) // 2
        by = box.y + S(70) + len(EXTRA_DEFS) * EXTRA_ROW + S(12)
        self.extra_buttons = [
            Button((box.x + S(26), by, half, S(40)), "ENDLESS",
                   lambda: self.set_extra_clock(ENDLESS), accent=GOLD),
            Button((box.x + S(26) + half + S(12), by, half, S(40)), "TIMED",
                   lambda: self.set_extra_clock(TIMED), accent=(126, 216, 150)),
            Button((box.x + S(26), by + S(52), half, S(40)), "BACK",
                   self.close_extras),
            Button((box.x + S(26) + half + S(12), by + S(52), half, S(40)), "PLAY",
                   self.play_extras, accent=(126, 216, 150)),
        ]

    # -- campaign picker ---------------------------------------------------

    @staticmethod
    def campaign_rect():
        # Height is derived from what actually goes inside - header, area
        # name, five rows and the BACK button - rather than guessed, which is
        # how the last row ended up under the button.
        rows = (LEVELS_PER_AREA * (S(CAMPAIGN_ROW_H) + S(CAMPAIGN_ROW_GAP))
                - S(CAMPAIGN_ROW_GAP))
        height = S(146) + rows + S(18) + S(46) + S(18)
        width = S(560)
        return pygame.Rect(WIDTH // 2 - width // 2, HEIGHT // 2 - height // 2,
                           width, height)

    def build_campaign_widgets(self):
        box = self.campaign_rect()
        arrow = S(46)
        ay = box.y + S(74)
        self.campaign_arrows = [
            Button((box.x + S(24), ay, arrow, arrow), "<",
                   lambda: self.step_area(-1), accent=(96, 200, 232)),
            Button((box.right - S(24) - arrow, ay, arrow, arrow), ">",
                   lambda: self.step_area(1), accent=(96, 200, 232)),
        ]
        self.campaign_rows = []
        rw = box.width - S(96)
        rh = S(CAMPAIGN_ROW_H)
        for i in range(LEVELS_PER_AREA):
            self.campaign_rows.append(
                pygame.Rect(box.x + S(48),
                            box.y + S(146) + i * (rh + S(CAMPAIGN_ROW_GAP)),
                            rw, rh))
        self.campaign_buttons = [
            Button((box.x + S(48), box.bottom - S(18) - S(46),
                    box.width - S(96), S(46)), "BACK", self.close_campaign),
        ]

    def open_campaign(self):
        self.campaign_open = True
        self.campaign_area = campaign_area_of(self.campaign_unlocked)
        self.build_campaign_widgets()
        self.audio.play("menuclick")
        self.preview_area()

    def close_campaign(self):
        self.campaign_open = False
        self.campaign_bg = None          # back to the title artwork
        self.audio.use_playlist(TITLE)
        self.audio.play("menuclick")

    def step_area(self, delta):
        """Left/right through the ten areas. Stops at the ends rather than
        wrapping, so the order reads as a journey."""
        target = self.campaign_area + delta
        if not 0 <= target < len(CAMPAIGN_AREAS):
            return
        self.campaign_area = target
        self.audio.play("menuclick")
        self.preview_area()

    def preview_area(self):
        """Show and play the area being browsed, so the picker sits in the
        place it is offering rather than on the title backdrop."""
        self.load_campaign_area(self.campaign_area)
        self.audio.use_playlist(CAMPAIGN_MUSIC_MODE)

    def campaign_level_at(self, index):
        """Continuous level number for row `index` of the shown area."""
        return self.campaign_area * LEVELS_PER_AREA + index + 1

    def start_campaign_level(self, number):
        if number > self.campaign_unlocked:
            self.set_note("LOCKED")
            return
        self.campaign_level_num = number
        self.campaign_open = False
        self.on_title = False
        self.title_ready = False
        self.audio.play("menuclick")
        self.reset(CAMPAIGN)

    def ask_wipe(self):
        self.wipe_open = True
        self.wipe_held = 0.0
        self.audio.play("menuclick")

    def close_wipe(self):
        self.wipe_open = False
        self.wipe_held = 0.0
        self.audio.play("menuclick")

    def do_wipe(self):
        """Delete every save. Only reached after holding YES the full time."""
        for path in (SAVE_FILE, SETTINGS_FILE):
            try:
                os.remove(path)
            except OSError:
                pass
        self.settings = {k: k not in ("fullscreen", "opaque")
                         for k, _, _ in SETTING_DEFS}
        if not BACKDROPS_OK:
            self.settings["backgrounds"] = False
        if self.display is not None:
            self.settings["fullscreen"] = self.display.fullscreen
        self.wipe_open = False
        self.wipe_held = 0.0
        self.menu_open = False
        self.note = ""
        # Nothing is reloaded: the player is asked to close the game so the
        # next launch starts genuinely clean, and every input is ignored.
        self.data_wiped = True
        self.audio.play("gameover")

    @staticmethod
    def wipe_rect():
        return pygame.Rect(WIDTH // 2 - S(210), HEIGHT // 2 - S(110), S(420), S(220))

    def update_wipe(self, dt, held):
        """YES has to be held down for WIPE_HOLD seconds."""
        if not self.wipe_open:
            return
        if held:
            self.wipe_held += dt
            if self.wipe_held >= WIPE_HOLD:
                self.do_wipe()
        else:
            self.wipe_held = max(0.0, self.wipe_held - dt * 2.5)

    def draw_wipe(self, screen):
        box = self.wipe_rect()
        screen.blit(translucent(box.size, DIALOG_FILL, (232, 92, 92, 250), S(16)),
                    box.topleft)
        lines = [(self.font_big, "ERASE ALL SAVE DATA?", (255, 140, 140)),
                 (self.font_small, "SAVED RUNS AND SETTINGS", DIM),
                 (self.font_small, "HOLD YES TO CONFIRM", DIM)]
        y = box.y + S(24)
        for font, text, colour in lines:
            img = font.render(text, True, colour)
            screen.blit(img, (box.centerx - img.get_width() // 2, y))
            y += img.get_height() + 10

        yes, no = self.wipe_buttons
        no.draw(screen, self.font)
        yes.draw(screen, self.font)
        # progress fills the YES button as it is held
        frac = clamp01(self.wipe_held / WIPE_HOLD)
        if frac > 0:
            width = int(yes.rect.width * frac)
            if width > 2:
                screen.blit(translucent((width, yes.rect.height),
                                        (232, 92, 92, 245), None, 10),
                            yes.rect.topleft)
                label = self.font.render("YES", True, TEXT)
                screen.blit(label, label.get_rect(center=yes.rect.center))

    @staticmethod
    def resume_rect():
        return pygame.Rect(WIDTH // 2 - S(210), HEIGHT // 2 - S(110), S(420), S(220))

    def ask_resume(self, mode):
        """Offer to continue a saved run, or start fresh and bin the save."""
        if not self.has_save(mode):
            self.start_game(mode)
            return
        self.resume_mode = mode
        self.resume_open = True
        self.fresh_held = 0.0
        self.audio.play("menuclick")

    def do_resume(self):
        self.resume_open = False
        self.fresh_held = 0.0
        self.resume_run(self.resume_mode)

    def do_fresh(self):
        """NO wipes the save, as asked - a fresh run replaces it."""
        self.resume_open = False
        self.fresh_held = 0.0
        self.clear_save(self.resume_mode)
        self.start_game(self.resume_mode)

    def update_resume(self, dt, held):
        """NO has to be held for RESUME_HOLD seconds.

        Continuing is the safe answer and stays a single click; it is only
        throwing the run away that asks for a deliberate press. The meter
        drains faster than it fills, so letting go part-way clearly resets.
        """
        if not self.resume_open:
            return
        if held:
            self.fresh_held += dt
            if self.fresh_held >= RESUME_HOLD:
                self.do_fresh()
        else:
            self.fresh_held = max(0.0, self.fresh_held - dt * 2.5)

    def draw_resume(self, screen):
        box = self.resume_rect()
        screen.blit(translucent(box.size, DIALOG_FILL, DIALOG_EDGE, S(16)),
                    box.topleft)
        entry = read_saves().get(self.resume_mode) or {}
        lines = [(self.font_big, "CONTINUE?", TEXT),
                 (self.font_small,
                  f"{self.resume_mode.upper()}  LEVEL {entry.get('level', 1)}"
                  f"  {int(entry.get('score', 0)):,} PTS", DIM),
                 (self.font_small, "HOLD NO TO START OVER", DIM),
                 ]
        y = box.y + S(26)
        for font, text, colour in lines:
            img = font.render(text, True, colour)
            screen.blit(img, (box.centerx - img.get_width() // 2, y))
            y += img.get_height() + 12
        for button in self.resume_buttons:
            button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))

        # NO fills up as it is held, the same language the wipe prompt uses
        no = self.resume_buttons[1]
        frac = clamp01(self.fresh_held / RESUME_HOLD)
        if frac > 0:
            width = int(no.rect.width * frac)
            if width > S(2):
                screen.blit(translucent((width, no.rect.height),
                                        (232, 92, 92, 245), None, S(10)),
                            no.rect.topleft)
                label = self.font.render("NO", True, TEXT)
                screen.blit(label, label.get_rect(center=no.rect.center))

    def draw_duration_picker(self, screen):
        box = self.duration_picker_rect()
        screen.blit(translucent(box.size, DIALOG_FILL, DIALOG_EDGE, S(16)),
                    box.topleft)
        title = self.font_big.render("SELECT DURATION", True, TEXT)
        screen.blit(title, (box.centerx - title.get_width() // 2, box.y + S(20)))
        for button in self.duration_buttons:
            button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))

    @staticmethod
    def settings_rect():
        return pygame.Rect(WIDTH // 2 - S(240), S(128), S(480), S(452))

    def spawn_credit_gems(self):
        """Gems drifting behind the credits roll.

        Deliberately slow and semi-transparent - they are wallpaper, not
        something to read past.
        """
        self.credit_gems = []
        margin = WIDTH * 0.22          # keep clear of the text column
        for i in range(CREDIT_GEMS):
            side = random.choice((0, 1))
            self.credit_gems.append({
                "kind": random.randrange(N_TYPES),
                "x": (random.uniform(10, margin) if side == 0
                      else random.uniform(WIDTH - margin, WIDTH - 10)),
                "y": random.uniform(0, HEIGHT + 200),
                "dy": random.uniform(-26, -9),
                "sway": random.uniform(8, 24),
                "phase": random.uniform(0, math.tau),
                "spin": random.uniform(-22, 22),
                "angle": random.uniform(0, 360),
                "scale": random.uniform(0.34, 0.72),
                "alpha": random.randint(55, 115),
            })

    def update_credit_gems(self, dt):
        if not self.bubbly:
            return
        for g in self.credit_gems:
            g["y"] += g["dy"] * dt
            g["angle"] += g["spin"] * dt
            if g["y"] < -TILE:
                g["y"] = HEIGHT + TILE
                margin = WIDTH * 0.22
                g["x"] = (random.uniform(10, margin) if random.random() < 0.5
                          else random.uniform(WIDTH - margin, WIDTH - 10))
                g["kind"] = random.randrange(N_TYPES)

    def draw_credit_gems(self, screen):
        if not self.bubbly or not self.credit_gems:
            return
        for g in self.credit_gems:
            sprite = self.normal[g["kind"] % len(self.normal)]
            size = max(4, int(TILE * g["scale"]))
            art = pygame.transform.rotozoom(sprite, g["angle"],
                                            size / sprite.get_width())
            art.set_alpha(g["alpha"])
            x = g["x"] + math.sin(self.time * 0.5 + g["phase"]) * g["sway"]
            screen.blit(art, art.get_rect(center=(int(x), int(g["y"]))))

    def open_credits(self):
        self.spawn_credit_gems()
        self.credits_open = True
        self.credit_armed = False
        self.credit_scroll = self.start_scroll()
        self.audio.play("menuclick")
        self.audio.use_playlist(CREDITS_MODE)

    def close_credits(self):
        self.credits_open = False
        self.credit_armed = False
        self.audio.play("menuclick")
        self.audio.use_playlist(TITLE)

    def credit_rect(self):
        """Hit area for the credit line at the bottom right of the title."""
        text = self.credit_label()
        image = self.font_small.render(text, True, DIM)
        return pygame.Rect(WIDTH - S(20) - image.get_width(),
                           HEIGHT - S(22) - image.get_height(),
                           image.get_width(), image.get_height()).inflate(16, 12)

    def credit_label(self):
        return "CLICK AGAIN TO VIEW CREDITS" if self.credit_armed else CREDITS

    def logo_block(self):
        """Height the logo occupies at the top of the roll."""
        logo = self.credits_art.get("logo")
        return (logo.get_height() + S(46)) if logo is not None else 0

    def start_scroll(self):
        """Scroll position that leaves the logo centred on screen."""
        logo = self.credits_art.get("logo")
        h = logo.get_height() if logo is not None else 0
        return HEIGHT - (HEIGHT // 2 - h // 2)

    def credits_height(self):
        return self.logo_block() + len(CREDITS_TEXT) * S(BASE_CREDIT_LINE) + HEIGHT

    def draw_credits(self, screen, background=True):
        art = self.credits_art.get("background")
        if background:
            if art is not None:
                screen.blit(art, (0, 0))
            else:
                screen.fill(BG)
        self.draw_credit_gems(screen)

        cx = WIDTH // 2
        top = HEIGHT - self.credit_scroll

        logo = self.credits_art.get("logo")
        if logo is not None and -logo.get_height() < top < HEIGHT:
            screen.blit(logo, (cx - logo.get_width() // 2, int(top)))

        y = top + self.logo_block()
        for kind, text in CREDITS_TEXT:
            if -S(40) < y < HEIGHT + S(40) and text:
                if kind == "t":
                    img = self.font_score.render(text, True, GOLD)
                elif kind == "h":
                    img = self.font_big.render(text, True, TEXT)
                elif kind == "b":
                    img = self.font_small.render(text, True, TEXT)
                else:
                    img = self.font_small.render(text, True, DIM)
                screen.blit(img, (cx - img.get_width() // 2, int(y)))
            elif kind == "r" and -S(40) < y < HEIGHT + S(40):
                pygame.draw.rect(screen, PANEL_EDGE[:3],
                                 (cx - S(150), int(y) + S(6), S(300), max(1, S(2))))
            y += S(BASE_CREDIT_LINE)

        for button in self.credit_buttons:
            button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))

    def open_settings(self):
        """Kept as a name; the graphics toggles live in the main menu now."""
        self.open_menu()
        self.audio.play("menuclick")

    def close_settings(self):
        self.settings_open = False
        self.audio.play("menuclick")

    def apply_opacity(self):
        """Push the option into the module flag and rebuild what was baked
        with the old alpha."""
        global OPAQUE_UI
        OPAQUE_UI = bool(self.settings.get("opaque", False))
        self.panel_bg = translucent((PANEL_W, PANEL_H), PANEL_FILL,
                                    PANEL_EDGE, 18)
        self.board_bg = self.build_board_backdrop()
        self.build_widgets()
        self.build_title_widgets()

    def save_settings(self):
        if self.data_wiped:
            return
        write_settings({"settings": self.settings,
                        "music": round(self.audio.music_volume, 3),
                        "sfx": round(self.audio.sfx_volume, 3)})

    def load_settings(self):
        data = read_settings()
        stored = data.get("settings")
        if isinstance(stored, dict):
            for key, _, _ in SETTING_DEFS:
                if isinstance(stored.get(key), bool):
                    self.settings[key] = stored[key]
            rs = stored.get("render_scale")
            if isinstance(rs, (int, float)) and any(
                    abs(rs - f) < 0.01 for f, _ in SCALE_OPTIONS):
                self.settings["render_scale"] = float(rs)
        self.apply_opacity()
        if isinstance(data.get("music"), (int, float)):
            self.audio.set_music_volume(float(data["music"]))
        if isinstance(data.get("sfx"), (int, float)):
            self.audio.set_sfx_volume(float(data["sfx"]))

    @property
    def bubbly(self):
        """Are the springy flourishes switched on?

        Off keeps every animation the same LENGTH - it just removes the
        overshoot, bounce and wobble, so motion is flat and businesslike.
        """
        return self.settings.get("smooth", True)

    def ease_land(self, t):
        """Settle curve: springy when smooth is on, plain glide when off."""
        return ease_bounce(t) if self.bubbly else ease_in_out(t)

    def ease_pop(self, t):
        return ease_back(t) if self.bubbly else ease_in_out(t)

    def toggle_setting(self, key):
        if key == "fullscreen" and self.display is not None:
            surface = self.display.toggle_with(self)
            self.settings[key] = bool(surface.get_flags() & pygame.FULLSCREEN)
            # Windowed mode opens a real WIDTH x HEIGHT window, so a 2x layer
            # would ask for a 2160x1620 window and overflow the monitor. Drop
            # to 1:1 on the way out and restore the choice on the way back in.
            if self.settings[key]:
                want = self.settings.get("render_scale", DEFAULT_RENDER_SCALE)
                if abs(want - RENDER_SCALE) > 0.01:
                    self.apply_scale(want)
            elif abs(RENDER_SCALE - 1.0) > 0.01:
                self.rebuild_at_scale(1.0)
            if self.menu_open:
                self.build_scale_buttons()  # rebuild for new fullscreen state
            self.audio.play("menuclick")
            self.save_settings()      # this return used to skip the write
            return
        self.settings[key] = not self.settings.get(key, True)
        if key == "shake":
            self.shake = 0.0
            self.shake_target = 0.0
        if key == "opaque":
            self.apply_opacity()
        self.audio.play("menuclick")
        self.save_settings()

    @staticmethod
    def extras_rect():
        return pygame.Rect(WIDTH // 2 - S(250), S(96), S(500), S(540))

    def open_extras(self):
        self.extras_open = True
        self.audio.play("menuclick")

    def close_extras(self):
        self.extras_open = False
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
        self.start_game(EXTRAS)

    def start_game(self, mode):
        """Leave the title screen and begin a run in the chosen mode."""
        # For timed mode, show duration picker first
        if mode == TIMED:
            if self.timed_duration_picker_open:
                # Already picking, don't re-trigger
                return
            self.timed_duration_picker_open = True
            self.resume_mode = TIMED  # Track which mode we're picking for
            return
        # For Extras mode with Timed clock, also show duration picker
        if mode == EXTRAS and self.extra_clock == TIMED:
            if self.timed_duration_picker_open:
                return
            self.timed_duration_picker_open = True
            self.resume_mode = EXTRAS  # Track that we're picking for Extras
            return
        self.on_title = False
        self.title_ready = False
        self.audio.play("menuclick")
        self.reset(mode)          # reset() swaps the music to the mode's list

    def draw_title(self, screen, background=True):
        if self.credits_open:
            self.draw_credits(screen, background)
            if self.data_wiped:
                self.draw_wiped(screen)
            return
        if background:
            photo = self.title_bg or (self.backgrounds[0]
                                      if self.backgrounds else None)
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
                screen.blit(halo, halo.get_rect(center=(WIDTH // 2, S(148) + bob)),
                            special_flags=pygame.BLEND_RGBA_ADD)
            screen.blit(art, art.get_rect(center=(WIDTH // 2, S(148) + bob)))
        else:
            big = self.font_huge.render("PRISMAC", True, TEXT)
            screen.blit(big, big.get_rect(center=(WIDTH // 2, S(148))))

        if self.title_ready:
            label = self.font_big.render("CHOOSE A MODE", True, (255,255,255))
            # sits clear above the first row of buttons (y=396)
            screen.blit(label, label.get_rect(center=(WIDTH // 2, S(362))))
            for button in self.title_buttons:
                button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))
        else:
            pulse = 0.5 + 0.5 * math.sin(self.time * 3.0)
            prompt = self.font_big.render("CLICK TO START", True, TEXT)
            prompt.set_alpha(int(120 + 135 * pulse))
            screen.blit(prompt, prompt.get_rect(center=(WIDTH // 2, S(470))))

        # Darken the title art itself. A translucent veil blitted onto this
        # SRCALPHA layer does not composite reliably, so this multiplies the
        # colour down instead - the logo dims but keeps its shape.
        alpha = self.overlay_veil()
        if alpha:
            k = max(0, 255 - alpha)
            screen.fill((k, k, k, 255), special_flags=pygame.BLEND_RGBA_MULT)

        if self.data_wiped:
            self.draw_wiped(screen)
            return
        if self.timed_duration_picker_open:
            self.draw_duration_picker(screen)
        if self.resume_open:
            self.draw_resume(screen)
        if self.wipe_open:
            self.draw_wipe(screen)
        if self.extras_open:
            self.draw_extras(screen)
        if self.campaign_open:
            self.draw_campaign(screen)
        if self.menu_open:
            self.draw_menu(screen)
        if self.wipe_open:
            self.draw_wipe(screen)


        credit = self.font_small.render(self.credit_label(), True,
                                        GOLD if self.credit_armed else DIM)
        screen.blit(credit, (WIDTH - S(20) - credit.get_width(),
                             HEIGHT - S(20) - credit.get_height()))

    def draw_campaign(self, screen):
        box = self.campaign_rect()
        screen.blit(translucent(box.size, DIALOG_FILL, DIALOG_EDGE, S(16)),
                    box.topleft)
        title = self.font_big.render("CAMPAIGN", True, TEXT)
        screen.blit(title, (box.x + S(24), box.y + S(22)))
        done = self.font_small.render(
            f"{self.campaign_unlocked - 1}/{CAMPAIGN_LEVELS}", True, DIM)
        screen.blit(done, (box.right - S(24) - done.get_width(), box.y + S(28)))

        # area name between the arrows
        name = self.font_big.render(CAMPAIGN_AREAS[self.campaign_area], True,
                                    (96, 200, 232))
        screen.blit(name, (box.centerx - name.get_width() // 2,
                           box.y + S(80)))
        num = self.font_small.render(
            f"AREA {self.campaign_area + 1} OF {len(CAMPAIGN_AREAS)}", True, DIM)
        screen.blit(num, (box.centerx - num.get_width() // 2, box.y + S(112)))

        for i, arrow in enumerate(self.campaign_arrows):
            # grey the arrow out at either end of the run of areas
            live = (self.campaign_area > 0) if i == 0 \
                else (self.campaign_area < len(CAMPAIGN_AREAS) - 1)
            r = arrow.rect
            tint = (96, 200, 232) if live else (90, 96, 110)
            screen.blit(translucent(r.size,
                                    (255, 255, 255, 30 if live else 12),
                                    None, S(8)), r.topleft)
            # The bitmap face has no < or > glyph, so the arrowheads are
            # drawn rather than typed.
            w, h = S(11), S(15)
            if i == 0:
                pts = [(r.centerx + w // 2, r.centery - h // 2),
                       (r.centerx + w // 2, r.centery + h // 2),
                       (r.centerx - w // 2, r.centery)]
            else:
                pts = [(r.centerx - w // 2, r.centery - h // 2),
                       (r.centerx - w // 2, r.centery + h // 2),
                       (r.centerx + w // 2, r.centery)]
            pygame.draw.polygon(screen, tint, pts)

        for i, rect in enumerate(self.campaign_rows):
            number = self.campaign_level_at(i)
            goal = campaign_level(number)
            locked = number > self.campaign_unlocked
            beaten = number < self.campaign_unlocked
            if locked:
                fill = (255, 255, 255, 12)
            elif beaten:
                fill = (126, 216, 150, 46)
            else:
                fill = GOLD + (60,)
            screen.blit(translucent(rect.size, fill, None, S(8)), rect.topleft)

            label = self.font.render(
                f"LEVEL {number}", True, (90, 96, 110) if locked else TEXT)
            screen.blit(label, (rect.x + S(14), rect.y + S(6)))
            text = "LOCKED" if locked else goal["text"]
            note = Button.fit(self.font_small, text, rect.width - S(120))
            screen.blit(note.render(text, True, DIM),
                        (rect.x + S(14),
                         rect.y + S(6) + label.get_height() + S(4)))
            mods = "" if locked else campaign_modifier_label(goal)
            if mods:
                # the twist this level adds, in the Extras accent colour
                chip = Button.fit(self.font_small, mods, rect.width - S(120))
                screen.blit(chip.render(mods, True, (176, 140, 240)),
                            (rect.x + S(14), rect.y + S(6)
                             + label.get_height() + S(4)
                             + note.get_height() + S(2)))
            if beaten:
                tick = self.font.render("CLEAR", True, (126, 216, 150))
                screen.blit(tick, (rect.right - S(14) - tick.get_width(),
                                   rect.centery - tick.get_height() // 2))
            elif not locked:
                play = self.font.render("PLAY", True, GOLD)
                screen.blit(play, (rect.right - S(14) - play.get_width(),
                                   rect.centery - play.get_height() // 2))

        for button in self.campaign_buttons:
            button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))

    def draw_extras(self, screen):
        box = self.extras_rect()
        screen.blit(translucent(box.size, DIALOG_FILL, DIALOG_EDGE, S(16)),
                    box.topleft)
        title = self.font_big.render("EXTRAS", True, TEXT)
        screen.blit(title, (box.x + S(26), box.y + S(24)))
        hint = self.font_small.render("PICK ANY", True, DIM)
        screen.blit(hint, (box.right - S(26) - hint.get_width(), box.y + S(30)))

        for key, rect, label, blurb in self.extra_rows:
            on = self.extras.get(key, False)
            screen.blit(translucent(rect.size,
                                    GOLD + (60,) if on else (255, 255, 255, 18),
                                    None, S(8)), rect.topleft)
            tick = pygame.Rect(rect.x + S(8), rect.centery - S(10), S(20), S(20))
            pygame.draw.rect(screen, TEXT if on else DIM, tick, max(1, S(2)),
                             border_radius=S(4))
            if on:
                pygame.draw.line(screen, GOLD, (tick.x + S(4), tick.centery),
                                 (tick.centerx, tick.bottom - S(5)), S(3))
                pygame.draw.line(screen, GOLD, (tick.centerx, tick.bottom - S(5)),
                                 (tick.right - S(3), tick.y + S(3)), S(3))
            # label on top, blurb on its own line underneath - a pixel font
            # is far too wide to fit both side by side
            name = self.font.render(label, True, TEXT if on else DIM)
            screen.blit(name, (rect.x + S(38), rect.y + S(5)))
            note_font = Button.fit(self.font_small, blurb, rect.width - S(46))
            note = note_font.render(blurb, True, DIM)
            screen.blit(note, (rect.x + S(38), rect.y + S(5) + name.get_height() + S(4)))

        zen = self.extras.get("zen")
        for button in self.extra_buttons:
            if button.label in (ENDLESS.upper(), TIMED.upper()):
                button.hover = (not zen and
                                self.extra_clock.upper() == button.label)
            button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))
        if zen:
            lock = self.font_small.render("ZEN IS ALWAYS ENDLESS", True, DIM)
            screen.blit(lock, (box.x + S(26), self.extra_buttons[0].rect.y - S(18)))
        note = self.font_small.render("EXTRAS RUNS ARE NOT SAVED", True, DIM)
        screen.blit(note, (box.centerx - note.get_width() // 2,
                           box.bottom - S(26)))
        if self.extras_note:
            warn = self.font_small.render(self.extras_note, True, (255, 150, 150))
            screen.blit(warn, (box.x + S(26), box.bottom - S(44)))

    def reset(self, mode=None):
        if mode is not None:
            self.mode = mode
        self.time = 0.0
        self.score = 0
        self.level = 1
        self.level_floor = 0          # score at which the current level began
        self.menu_open = False
        self.music_open = False
        self.music_secret = False   # picker showing the hidden folder
        self.music_title_taps = 0   # taps on the picker title
        self.dragging = None
        self.wants_quit = False
        self.hint = None
        self.hint_left = 0.0
        self.effects = []
        self.go_left = 0.0
        self.flyers = []
        self.debris = []
        self.scheduled_actions = []
        self.multi_run = False
        self.move_pending = False
        self.spent_bombs = set()
        self.rainbow_targets = []
        self.rainbow_all = set()
        self.rainbow_bolts = []
        self.rainbow_origin = None
        self.rainbow_done = 0
        self.rainbow_step = RAINBOW_STEP
        self._bg_current = None
        self._bg_previous = None
        self._bg_was_title = True
        self.credit_gems = []
        self._bg_blend = 1.0
        self.shown_score = float(getattr(self, "score", 0))
        self.shown_progress = 0.0
        self.hover_lift = {}
        self.shake = 0.0
        self.shake_target = 0.0  # smooth ramp towards target
        self.shake_t = 0.0
        self.frame = None
        self.note = ""
        self.note_time = 0.0
        self.shape_cells = None
        self.shape_name = None
        # Campaign run state. goal is None outside campaign runs, which is
        # what every campaign check keys off.
        self.goal = campaign_level(self.campaign_level_num) \
            if self.mode == CAMPAIGN else None
        self.moves_left = (self.goal or {}).get("moves", 0)
        self.gems_cleared = 0
        self.campaign_won = False
        # Use the selected duration for timed mode, otherwise use default
        if self.mode == CAMPAIGN and self.timed:
            self.time_left = self.goal["seconds"]
        elif self.timed:
            self.time_left = self.timed_duration_choice
        else:
            self.time_left = TIMED_SECONDS
        self.lock_kind = random.randrange(N_TYPES)
        self.lock_left = LOCK_SECONDS
        self.over = False
        self.bg_index_override = None  # reset background to random each game
        # Cache the random background selection so it doesn't change every frame
        if self.backgrounds:
            self.bg_index = random.randrange(len(self.backgrounds))
        else:
            self.bg_index = 0
        self.time_pops = []          # floating "+3s" labels
        self.score_pops = []         # floating score labels
        self.puffs = []              # smoke left by flame gems
        # While the title screen is up its own track keeps playing; the mode
        # playlist only takes over once a game actually starts.
        if self.mode == CAMPAIGN:
            self.load_campaign_area(campaign_area_of(self.campaign_level_num))
        if not self.on_title:
            if self.mode == CAMPAIGN:
                self.audio.use_playlist(CAMPAIGN_MUSIC_MODE)
            else:
                # an Extras run with the clock on still gets the timed music
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
            self.grid = new_shapes_grid(bonuses=self.timed and self.timed_bonus_gems,
                                        mask=self.shape_cells)
        else:
            self.grid = self.apply_extras(
                new_grid(bonuses=self.timed and self.timed_bonus_gems, chaos=self.extra("chaos")))
        self.begin_intro()

    def mode_label(self):
        if self.mode == EXTRAS:
            on = [lbl for k, lbl, _ in EXTRA_DEFS if self.extras.get(k)]
            return on[0] if len(on) == 1 else f"EXTRAS x{len(on)}"
        if self.mode == SHAPES:
            return "SHAPES"
        if self.mode == CAMPAIGN:
            return CAMPAIGN_AREAS[campaign_area_of(self.campaign_level_num)].upper()
        return "TIMED" if self.timed else "ENDLESS"

    def extra(self, key):
        """Is this modifier switched on for the current run?

        Campaign levels carry their own set, baked into the objective, so
        every modifier check works there without any extra plumbing.
        """
        if self.mode == CAMPAIGN:
            return bool(self.goal) and key in self.goal.get("extras", ())
        return self.mode == EXTRAS and self.extras.get(key, False)

    @property
    def timed(self):
        if self.mode == CAMPAIGN:
            return bool(self.goal and self.goal["kind"] == GOAL_TIME)
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

        pad = S(14)
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
        # The ui/ skin folder was removed from the project; everything is
        # drawn rather than blitted from artwork. Kept as a no-op so the
        # dozens of call sites do not all need touching.
        return None

    def _unused_skinned(self, name, size):
        """Scaled skin image, or None if that file was not supplied."""
        art = self.skin.get(name)
        return stretch(art, size) if art is not None else None

    def build_board_backdrop(self):
        """The board surface, baked once instead of redrawn every frame.

        With ui/board.png present that artwork is the board and the checker
        pattern is dropped - a texture and a checkerboard fight each other.
        """
        base = translucent((BOARD_W, BOARD_H), BOARD_FILL, None, S(14))
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

    def load_campaign_area(self, area):
        """Swap in one area's backdrop and music."""
        self.campaign_bg = load_campaign_background(area)
        folder = campaign_area_dir(area)
        tracks = []
        if folder:
            index = Audio.index_folder(folder)
            tracks = [index[k] for k in sorted(index)]
        self.audio.set_campaign_playlist(tracks)

    def background_for_level(self):
        if self.mode == CAMPAIGN and self.campaign_bg is not None:
            return self.campaign_bg
        if not self.backgrounds:
            return None
        if self.bg_index_override is not None:
            return self.backgrounds[self.bg_index_override]
        return self.backgrounds[self.bg_index]

    def advance_background(self):
        """Move to the next background for the next level, if no override is active."""
        if not self.backgrounds:
            return
        if self.bg_index_override is not None:
            return
        if len(self.backgrounds) < 2:
            return
        self.bg_index = (self.bg_index + 1) % len(self.backgrounds)

    def update_background_transition(self, dt):
        return

    # -- effects ----------------------------------------------------------

    def set_note(self, text):
        """Set a note with automatic fade in/out timing."""
        self.note = text
        self.note_time = 0.0

    def ease_background(self, dt):
        if self._bg_previous is None:
            return
        if not BACKDROPS_OK:
            self._bg_blend = 1.0
            self._bg_previous = None
            return
        self._bg_blend += dt / BG_CROSSFADE
        if self._bg_blend >= 1.0:
            self._bg_blend = 1.0
            self._bg_previous = None

    def ease_readouts(self, dt):
        """Let the score and the level bar catch up to their real values.

        Purely cosmetic: with smooth animation off they simply snap, so the
        numbers on screen are always the true ones either way.
        """
        if not self.bubbly:
            self.shown_score = float(self.score)
            self.shown_progress = self.level_progress()
            self.hover_lift.clear()
            return

        # a score jump should feel like it is racking up, not ticking forever
        gap = self.score - self.shown_score
        if abs(gap) < 1.0:
            self.shown_score = float(self.score)
        else:
            self.shown_score += gap * min(1.0, dt * 7.0) + (1 if gap > 0 else -1)

        target = self.level_progress()
        step = target - self.shown_progress
        if abs(step) < 0.002:
            self.shown_progress = target
        else:
            self.shown_progress += step * min(1.0, dt * 6.0)

        for button in (self.buttons + self.menu_buttons + self.title_buttons
                       + self.extra_buttons + self.over_buttons
                       + self.music_buttons + self.resume_buttons):
            key = id(button)
            want = 1.0 if button.hover else 0.0
            have = self.hover_lift.get(key, 0.0)
            self.hover_lift[key] = have + (want - have) * min(1.0, dt * 12.0)

    def draw_note(self, screen, x, y, width):
        """Draw note with fade in/out and rainbow color for BOARD WIPE and RAINBOW."""
        if not self.note:
            return
        # Fade in first 0.3s, out after 2.0s, total 2.5s
        fade_in = min(1.0, self.note_time / 0.3)
        fade_out = max(0.0, 1.0 - (self.note_time - 2.0) / 0.5) if self.note_time > 2.0 else 1.0
        alpha = fade_in * fade_out
        if self.bubbly:
            # drifts up a few pixels as it appears, so it does not just blink on
            y += int(round(10 * (1.0 - ease_out(fade_in))))
        
        # Use rainbow color for "BOARD WIPE!" and "RAINBOW!", normal gold for others
        if "BOARD WIPE" in self.note or "RAINBOW" in self.note:
            hue = (self.note_time * 0.8) % 1.0
            rgb = colorsys.hsv_to_rgb(hue, 0.9, 1.0)
            color = tuple(int(c * 255) for c in rgb)
        else:
            color = GOLD
        
        # Render text
        label = self.font.render(self.note, True, color)
        label = label.copy()
        label.set_alpha(int(255 * alpha))
        
        # Center text
        text_rect = label.get_rect(center=(x + width // 2, y))
        screen.blit(label, text_rect)

    def add_shake(self, amount):
        if not self.settings.get("shake", True):
            return
        """Kick the camera. Amounts add up but are capped, so a huge cascade
        does not turn into an earthquake. Smoothly ramps in/out for natural feel."""
        self.shake_target = min(SHAKE_MAX, self.shake_target + amount)

    def shake_offset(self):
        """INSANE explosive camera shake - rapid violent jitter."""
        if self.shake <= 0.15:
            return (0, 0)
        a = self.shake
        # EXTREME frequencies create frantic, violent jittering
        # Much faster and more intense - increased amplitudes
        x = (math.sin(self.shake_t * 45.0) * a * 0.85
             + math.sin(self.shake_t * 67.3) * a * 0.65
             + math.cos(self.shake_t * 82.1) * a * 0.55
             + math.sin(self.shake_t * 31.7) * a * 0.4)
        y = (math.cos(self.shake_t * 52.4) * a * 0.85
             + math.cos(self.shake_t * 71.8) * a * 0.65
             + math.sin(self.shake_t * 93.2) * a * 0.55
             + math.cos(self.shake_t * 38.6) * a * 0.4)
        return (int(x), int(y))

    def spawn_effect(self, name, r, c):
        """Play an animation centred on a board cell, if that effect exists."""
        anim = self.anims.get(name)
        if anim is None or len(self.effects) >= MAX_EFFECTS:
            return
        self.effects.append(Effect(anim,
                                   BOARD_X + int((c + 0.5) * TILE),
                                   BOARD_Y + int((r + 0.5) * TILE)))

    def schedule_action(self, delay, func, *args, **kwargs):
        if delay <= 0:
            func(*args, **kwargs)
            return
        self.scheduled_actions.append([delay, func, args, kwargs])

    def update_scheduled_actions(self, dt):
        if not self.scheduled_actions:
            return
        remaining = []
        for delay, func, args, kwargs in self.scheduled_actions:
            delay -= dt
            if delay <= 0:
                func(*args, **kwargs)
            else:
                remaining.append([delay, func, args, kwargs])
        self.scheduled_actions = remaining

    def select_hurl_cells(self, blast, source, max_cells=4):
        if len(blast) <= max_cells:
            return blast
        if source not in blast:
            return set(sorted(blast)[:max_cells])
        others = [cell for cell in blast if cell != source]
        others.sort(key=lambda rc: abs(rc[0] - source[0]) + abs(rc[1] - source[1]))
        return {source} | set(others[:max_cells - 1])

    def explosion_chain(self, sources):
        chain = []
        queue = list(sorted(sources))
        seen = set(queue)
        while queue:
            r, c = queue.pop()
            blast = {(r, c)}
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr, cc = r + dr, c + dc
                    if not in_bounds(rr, cc):
                        continue
                    gem = self.grid[rr][cc]
                    if gem is None:
                        continue
                    if ((gem.cell_type == CELL_GEM and gem.power == FLAME)
                            or gem.cell_type == CELL_BOMB):
                        if (rr, cc) not in seen:
                            queue.append((rr, cc))
                            seen.add((rr, cc))
                        continue
                    blast.add((rr, cc))
            chain.append(((r, c), blast))
        return chain

    def execute_scheduled_explosion(self, source, blast, max_hurl=4):
        r, c = source
        if self.bubbly and blast:
            hurl_cells = self.select_hurl_cells(blast, source, max_cells=max_hurl)
            self.hurl_blast(hurl_cells, source)
        self.spawn_effect("explode", r, c)
        self.spawn_smoke(r, c)
        self.audio.play("explode")
        self.add_shake(SHAKE_FLAME * 0.5)

    def schedule_explosion_chain(self, sources, max_hurl=4):
        for step, (source, blast) in enumerate(self.explosion_chain(sources)):
            self.schedule_action(step * CHAIN_STEP,
                                 self.execute_scheduled_explosion,
                                 source, blast,
                                 max_hurl=max_hurl)

    def hurl_blast(self, cells, origin):
        """Throw the gems an explosion destroyed off the screen.

        Only with smooth animation on - flat mode keeps the plain pop.
        Capped: a rainbow gem swapped into a bomb sets off every bomb on the
        board, and each of those blasts asked for its own handful of debris,
        which buried the screen in flying gems.
        """
        if not self.bubbly or not cells:
            return
        if getattr(self, "rainbow_thrown", False):
            self.rainbow_thrown = False
            return          # already thrown one at a time during the zap
        budget = DEBRIS_MAX - len(self.debris)
        if budget <= 0:
            return
        ox = BOARD_X + (origin[1] + 0.5) * TILE
        oy = BOARD_Y + (origin[0] + 0.5) * TILE
        for r, c in list(cells)[:budget]:
            gem = self.grid[r][c]
            if gem is None or gem.cell_type == CELL_EMPTY:
                continue
            self.debris.append(FlyingGem(
                self.sprite_for(gem),
                BOARD_X + (c + 0.5) * TILE,
                BOARD_Y + (r + 0.5) * TILE,
                random.uniform(0.0, 0.05),
                origin=(ox, oy), force=0.75))

    def puff_cells(self, cells, per_cell=3, force=0.5):
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

    def spawn_smoke(self, r, c, count=14):
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
        # increased force for bigger central puff
        self.puffs.append(Puff(max(self.smoke, key=lambda s: s.get_width()),
                               x, y, angle=random.uniform(0, math.tau),
                               force=0.42))

    def spawn_effect_at(self, name, x, y):
        anim = self.anims.get(name)
        if anim is not None and len(self.effects) < MAX_EFFECTS:
            self.effects.append(Effect(anim, x, y))

    # -- progression ------------------------------------------------------

    def end_game(self):
        if self.over:
            return                # already ended; do not replay the sound
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
        self.advance_background()
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
                if not self.bubbly:
                    continue          # flat mode fades the board out instead
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
        flat = not self.bubbly          # no sliding: fade in and out on the spot
        if t < BANNER_IN:
            p = ease_out(clamp01(t / BANNER_IN))
            alpha = int(255 * clamp01(t / (BANNER_IN * 0.6)))
            return (0 if flat else int(-WIDTH * (1.0 - p))), alpha
        t -= BANNER_IN
        if t < BANNER_HOLD:
            return 0, 255
        t -= BANNER_HOLD
        p = clamp01(t / BANNER_OUT)
        alpha = int(255 * (1.0 - clamp01(p * 1.4)))
        return (0 if flat else int(WIDTH * ease_in_out(p))), alpha

    def secret_shuffle(self):
        """Hidden reshuffle. New board, score and level untouched.

        Only fires when the board is settled, so it can't interrupt a cascade
        that is still paying out points.
        """
        if self.over or self.state != "idle":
            return False
        self.grid = (new_shapes_grid(self.timed and self.timed_bonus_gems, self.shape_cells)
                     if self.mode == SHAPES
                     else new_grid(bonuses=self.timed and self.timed_bonus_gems,
                                   chaos=self.extra("chaos")))
        self.audio.play("shuffle")
        self.begin_intro()          # rains the new board in like any other
        return True

    # -- widgets ----------------------------------------------------------

    def build_widgets(self):
        x = PANEL_X + S(16)
        w = PANEL_W - S(32)
        bottom = PANEL_Y + PANEL_H - S(16)
        self.buttons = [
            Button((x, bottom - S(46) * 4 - S(30), w, S(46)), "HINT",
                   self.show_hint, accent=HINT_COLOR),
            Button((x, bottom - S(46) * 3 - S(20), w, S(46)), "BACKGROUNDS",
                   self.open_background_picker, accent=(176, 140, 240)),
            Button((x, bottom - S(46) * 2 - S(10), w, S(46)), "MUSIC",
                   self.open_music, accent=(150, 160, 190)),
            Button((x, bottom - S(46), w, S(46)), "MENU", self.open_menu),
        ]

        box = self.menu_rect()
        sx, sw = box.x + S(30), box.width - S(60)
        self.sliders = [
            Slider((sx, box.y + S(104), sw, S(8)), "MUSIC",
                   lambda: self.audio.music_volume, self.audio.set_music_volume),
            Slider((sx, box.y + S(168), sw, S(8)), "SOUND EFFECTS",
                   lambda: self.audio.sfx_volume, self.audio.set_sfx_volume),
        ]
        # graphics toggles sit between the sliders and the buttons
        self.setting_rows = []
        for i, (key, label, blurb) in enumerate(SETTING_DEFS):
            self.setting_rows.append(
                (key, pygame.Rect(sx, box.y + S(226) + i * EXTRA_ROW,
                                  sw, EXTRA_ROW - S(6)), label, blurb))
        self.setting_buttons = []

        # Zoom chips, built on demand and only while fullscreen. The band they
        # sit in is reserved unconditionally so the buttons underneath keep one
        # fixed home - moving them around was what broke their hitboxes.
        self.scale_buttons = []
        self.scale_band_y = self.setting_rows[-1][1].bottom + S(34)
        self.scale_band_h = S(42)

        half = (sw - S(20)) // 2
        below = self.scale_band_y + self.scale_band_h
        # RETURN TO TITLE gets the full width and a taller box - it is the
        # one people reach for most
        self.menu_buttons = [
            # RESUME and QUIT share a row; the bottom button changes with
            # context - RETURN TO TITLE SCREEN in a game, RESET DATA on the
            # title screen, where wiping saves actually belongs.
            Button((sx, below + S(18), half, S(52)), "RESUME", self.close_menu,
                   accent=(126, 216, 150)),
            Button((sx + half + S(20), below + S(18), half, S(52)), "QUIT", self.quit,
                   accent=(232, 92, 92)),
            Button((sx, below + S(82), sw, S(52)), "RETURN TO TITLE SCREEN",
                   self.return_to_title, accent=GOLD),
        ]

        wbox = self.wipe_rect()
        whalf = (wbox.width - S(72)) // 2
        self.wipe_buttons = [
            Button((wbox.x + S(30), wbox.bottom - S(66), whalf, S(46)), "YES",
                   lambda: None, accent=(232, 92, 92)),
            Button((wbox.x + S(42) + whalf, wbox.bottom - S(66), whalf, S(46)), "NO",
                   self.close_wipe),
        ]

        rbox = self.resume_rect()
        rhalf = (rbox.width - S(72)) // 2
        self.resume_buttons = [
            Button((rbox.x + S(30), rbox.bottom - S(66), rhalf, S(46)), "YES",
                   self.do_resume, accent=(126, 216, 150)),
            # NO throws the saved run away, so it is hold-to-confirm - the
            # action is a no-op and update_resume fires it instead.
            Button((rbox.x + S(42) + rhalf, rbox.bottom - S(66), rhalf, S(46)), "NO",
                   lambda: None, accent=(232, 92, 92)),
        ]

        # Duration picker for timed mode
        dbox = self.duration_picker_rect()
        # 2x2 grid of buttons, centered
        btn_w = S(90)
        btn_h = S(50)
        gap = S(20)
        total_w = btn_w * 2 + gap
        start_x = dbox.centerx - total_w // 2
        self.timed_bonus_button = Button(
            (dbox.centerx - S(120), dbox.y + S(220), S(240), S(44)),
            self.timed_gems_label(),
            self.toggle_timed_bonus_gems,
            accent=(232, 150, 96),
            art=self.skinned("menubutton", (240, 44)),
            art_hover=self.skinned("menubuttonhovered", (240, 44)),
        )
        self.duration_buttons = [
    Button(
        (start_x, dbox.y + S(80), btn_w, btn_h),
        "1:00",
        lambda: self.pick_duration(60.0),
        accent=(232, 150, 96),
        art=self.skinned("menubutton", (btn_w, btn_h)),
        art_hover=self.skinned("menubuttonhovered", (btn_w, btn_h)),
    ),
    Button(
        (start_x + btn_w + gap, dbox.y + S(80), btn_w, btn_h),
        "1:30",
        lambda: self.pick_duration(90.0),
        accent=(232, 150, 96),
        art=self.skinned("menubutton", (btn_w, btn_h)),
        art_hover=self.skinned("menubuttonhovered", (btn_w, btn_h)),
    ),
    Button(
        (start_x, dbox.y + S(80) + btn_h + gap, btn_w, btn_h),
        "2:00",
        lambda: self.pick_duration(120.0),
        accent=(232, 150, 96),
        art=self.skinned("menubutton", (btn_w, btn_h)),
        art_hover=self.skinned("menubuttonhovered", (btn_w, btn_h)),
    ),
    Button(
        (start_x + btn_w + gap, dbox.y + S(80) + btn_h + gap, btn_w, btn_h),
        "2:30",
        lambda: self.pick_duration(150.0),
        accent=(232, 150, 96),
        art=self.skinned("menubutton", (btn_w, btn_h)),
        art_hover=self.skinned("menubuttonhovered", (btn_w, btn_h)),
    ),
    self.timed_bonus_button,
]

        self.credit_buttons = [
            Button((WIDTH - 190, HEIGHT - 78, 160, 48), "BACK",
                   self.close_credits),
        ]

        picker = self.music_rect()
        self.music_list = ScrollList((picker.x + S(24), picker.y + S(76),
                                      picker.width - S(48), picker.height - S(150)))
        pw = picker.width - S(48)
        self.music_buttons = [
            Button((picker.x + S(24), picker.bottom - S(62), pw, S(44)), "CLOSE",
                   self.close_music,
                   art=self.skinned("menubutton", (pw, S(44))),
                   art_hover=self.skinned("menubuttonhovered", (pw, S(44)))),
        ]

        # Background picker list
        bgpicker = self.music_rect()  # reuse same rect
        self.bg_list = ScrollList((bgpicker.x + S(24), bgpicker.y + S(76),
                                   bgpicker.width - S(48), bgpicker.height - S(150)))
        bgw = bgpicker.width - S(48)
        self.bg_picker_buttons = [
            Button((bgpicker.x + S(24), bgpicker.bottom - S(62), bgw, S(44)), "CLOSE",
                   self.close_background_picker,
                   art=self.skinned("menubutton", (bgw, 44)),
                   art_hover=self.skinned("menubuttonhovered", (bgw, 44))),
        ]

        over = self.over_rect()
        ox, ow = over.x + S(34), over.width - S(68)
        third = (ow - S(20)) // 2
        self.over_buttons = [
            Button((ox, over.bottom - S(74), third, S(46)), "PLAY AGAIN",
                   self.replay_or_advance, accent=(126, 216, 150)),
            Button((ox + third + S(20), over.bottom - S(74), third, S(46)), "TITLE",
                   self.return_to_title, accent=GOLD),
        ]

    @staticmethod
    def music_rect():
        return pygame.Rect(WIDTH // 2 - S(230), HEIGHT // 2 - S(220), S(460), S(440))

    def music_title_rect(self):
        """Hitbox for the picker's heading. Derived from the rendered text so
        it stays honest at every render scale, and padded so it is tappable
        rather than pixel-perfect."""
        box = self.music_rect()
        image = self.font_big.render(self.music_title(), True, TEXT)
        return pygame.Rect(box.x + S(24), box.y + S(24),
                           image.get_width() + S(12),
                           image.get_height() + S(8))

    def music_title(self):
        return "Secret ;)" if self.music_secret else "MUSIC"

    @staticmethod
    def duration_picker_rect():
        return pygame.Rect(WIDTH // 2 - S(230), HEIGHT // 2 - S(170), S(460), S(280))

    @staticmethod
    def over_rect():
        return pygame.Rect(WIDTH // 2 - S(210), HEIGHT // 2 - S(150), S(420), S(300))

    @staticmethod
    def menu_rect():
        # Wide enough for a row of four zoom chips, tall enough for the
        # buttons underneath them.
        return pygame.Rect(WIDTH // 2 - S(330), S(8), S(660), S(768))

    # -- button actions ---------------------------------------------------

    def show_hint(self):
        if self.over or self.state != "idle":
            return
        self.hint = find_hint(self.grid)
        self.hint_left = HINT_SECONDS if self.hint else 0.0
        self.note = "" if self.hint else "no moves - reshuffling"
        if self.hint is None:
            self.secret_shuffle()

    def locked_picker(self, label):
        """Campaign levels supply their own backdrop and music, so those two
        pickers are switched off for the run rather than silently ignored."""
        if self.mode != CAMPAIGN:
            return False
        area = CAMPAIGN_AREAS[campaign_area_of(self.campaign_level_num)]
        self.set_note(f"{label} SET BY {area.upper()}")
        self.audio.play("menuclick")
        return True

    def open_music(self):
        """Song picker. Choosing one plays it, then the shuffle resumes."""
        if self.locked_picker("MUSIC"):
            return
        self.music_open = True
        self.menu_open = False
        self.sel = None
        self.dragging = None
        self.music_title_taps = 0
        self.music_secret = self.audio.mode == SECRET_MUSIC_MODE
        self.music_list.items = self.audio.track_names()
        playing = self.audio.now_playing()
        self.music_list.current = (self.music_list.items.index(playing)
                                   if playing in self.music_list.items else -1)
        self.music_list.offset = 0.0

    def tap_music_title(self):
        """Five taps on the picker heading open the hidden folder.

        Counted per visit: the tally resets whenever the picker opens, so a
        stray click days ago cannot leave it one tap from firing.
        """
        self.music_title_taps += 1
        if self.music_title_taps < SECRET_TAPS:
            self.audio.play("menuclick")
            return
        self.music_title_taps = 0
        self.toggle_secret_music()

    def toggle_secret_music(self):
        if not self.music_secret:
            if not self.audio.secret_playlist:
                # Nothing to show. Say so plainly rather than opening an
                # empty list that looks broken.
                self.audio.play("menuclick")
                self.note = f"nothing in music/{SECRET_MUSIC_SUBDIR}"
                return
            self.music_secret = True
            self.audio.use_playlist(SECRET_MUSIC_MODE)
        else:
            self.music_secret = False
            self.audio.use_playlist(self.current_music_mode())
        self.audio.play("levelup")
        self.refresh_music_list()
        self.note = "secret playlist" if self.music_secret else "back to music"

    def current_music_mode(self):
        """Whichever playlist this part of the game would normally use."""
        if self.on_title:
            return TITLE
        if self.mode == EXTRAS and self.timed:
            return TIMED_MUSIC_MODE
        return self.mode

    def refresh_music_list(self):
        self.music_list.items = self.audio.track_names()
        playing = self.audio.now_playing()
        self.music_list.current = (self.music_list.items.index(playing)
                                   if playing in self.music_list.items else -1)
        self.music_list.offset = 0.0

    def overlay_open(self):
        """True when any panel sits above the screen. The title screen's
        first click reveals the mode buttons, and that must not eat clicks
        aimed at a panel on top of it."""
        return (self.menu_open or self.music_open or self.bg_picker_open
                or self.extras_open or self.credits_open or self.wipe_open
                or self.resume_open or self.timed_duration_picker_open
                or self.campaign_open)

    def close_music(self):
        self.music_open = False

    def pick_duration(self, seconds):
        """Select timed mode duration and start the game."""
        self.timed_duration_choice = seconds
        self.timed_duration_picker_open = False
        self.on_title = False
        self.title_ready = False
        self.audio.play("menuclick")
        # Use resume_mode to know whether starting TIMED or EXTRAS with TIMED clock
        mode = self.resume_mode if self.resume_mode else TIMED
        self.reset(mode)

    def toggle_timed_bonus_gems(self):
        self.timed_bonus_gems = not self.timed_bonus_gems
        self.timed_bonus_button.label = self.timed_gems_label()
        self.audio.play("menuclick")

    def timed_gems_label(self):
        return f"TIMED GEMS: {'ON' if self.timed_bonus_gems else 'OFF'}"

    def close_duration_picker(self):
        """Dismiss the duration picker without starting."""
        self.timed_duration_picker_open = False
        self.audio.play("menuclick")

    def open_background_picker(self):
        """Open the background picker dialog."""
        if self.locked_picker("BACKGROUND"):
            return
        self.bg_picker_open = True
        self.menu_open = False
        self.sel = None
        self.dragging = None
        # Generate list of background names
        if self.backgrounds:
            self.bg_list.items = [f"BG {i+1}" for i in range(len(self.backgrounds))]
            self.bg_list.current = self.bg_index_override if self.bg_index_override is not None else 0
            self.bg_list.offset = 0.0
        self.audio.play("menuclick")

    def close_background_picker(self):
        self.bg_picker_open = False
        self.audio.play("menuclick")

    # -- saving ------------------------------------------------------------

    def replay_or_advance(self):
        """PLAY AGAIN retries a failed level, or moves on from a cleared one."""
        if self.mode == CAMPAIGN and self.campaign_won:
            if self.campaign_level_num < CAMPAIGN_LEVELS:
                self.campaign_level_num += 1
            else:
                self.return_to_title()      # the run is finished
                return
        self.reset(self.mode)

    def save_campaign(self):
        if self.data_wiped:
            return
        data = read_saves()
        data["campaign"] = {"unlocked": int(self.campaign_unlocked)}
        write_saves(data)

    def load_campaign(self):
        entry = read_saves().get("campaign")
        if isinstance(entry, dict):
            got = entry.get("unlocked")
            if isinstance(got, int):
                self.campaign_unlocked = max(1, min(CAMPAIGN_LEVELS, got))
        # open the picker on the area they are actually up to
        self.campaign_area = campaign_area_of(self.campaign_unlocked)

    def savable(self):
        """Endless, Shapes and Timed can be resumed. Extras cannot: a run is
        defined by the modifiers picked for it, so there is nothing stable to
        come back to."""
        return self.mode in (ENDLESS, SHAPES, TIMED) and not self.over

    def save_run(self):
        if self.data_wiped or not self.savable() or self.on_title:
            return
        # The board is emptied to None during the level-up fly-off, so there
        # is nothing coherent to store until the new one has arrived. Keep
        # whatever was saved before rather than crashing or writing a blank.
        if any(cell is None for row in self.grid for cell in row):
            return
        if self.state in ("flyoff", "banner", "settling"):
            # the board is mid-swap between levels and holds nothing useful;
            # store the progress and let the resume deal a fresh one
            data = read_saves()
            data[self.mode] = {
                "score": self.score, "level": self.level,
                "level_floor": self.level_floor, "shape": self.shape_name,
                "time_left": round(self.time_left, 2), "grid": None,
            }
            write_saves(data)
            return
        data = read_saves()
        if not grid_intact(self.grid):
            # mid-transition: keep the score and level, drop the board and
            # let the resume build a fresh one
            entry = {"score": self.score, "level": self.level,
                     "level_floor": self.level_floor,
                     "shape": self.shape_name,
                     "time_left": round(self.time_left, 2)}
            if self.score > 0 or self.level > 1:
                data[self.mode] = entry
                write_saves(data)
            return
        if self.score <= 0 and self.level <= 1:
            # nothing achieved yet - clear any stale save rather than store
            # a board the player would be asked about for no reason
            if self.mode in data:
                data.pop(self.mode, None)
                write_saves(data)
            return
        data[self.mode] = {
            "score": self.score,
            "level": self.level,
            "level_floor": self.level_floor,
            "shape": self.shape_name,
            "time_left": round(self.time_left, 2),
            "grid": pack_grid(self.grid),
        }
        write_saves(data)

    def has_save(self, mode):
        """A save only counts if there is actual progress in it.

        Level 1 with no points is just a fresh board, so offering to resume
        it would be a pointless prompt.
        """
        entry = read_saves().get(mode)
        if not isinstance(entry, dict) or "grid" not in entry:
            return False
        return int(entry.get("score", 0)) > 0 or int(entry.get("level", 1)) > 1

    def clear_save(self, mode):
        data = read_saves()
        if not grid_intact(self.grid):
            # mid-transition: keep the score and level, drop the board and
            # let the resume build a fresh one
            entry = {"score": self.score, "level": self.level,
                     "level_floor": self.level_floor,
                     "shape": self.shape_name,
                     "time_left": round(self.time_left, 2)}
            if self.score > 0 or self.level > 1:
                data[self.mode] = entry
                write_saves(data)
            return
        if mode in data:
            del data[mode]
            write_saves(data)

    def resume_run(self, mode):
        """Start `mode` from its save. Falls back to a new run if the saved
        board no longer fits the current board size or gem set."""
        entry = read_saves().get(mode) or {}
        grid = unpack_grid(entry.get("grid"))
        # For resume, skip the duration picker and go straight to the game
        # using the saved time_left instead
        self.on_title = False
        self.title_ready = False
        self.audio.play("menuclick")
        self.reset(mode)
        if grid is None:
            return False
        self.score = int(entry.get("score", 0))
        self.level = max(1, int(entry.get("level", 1)))
        self.level_floor = int(entry.get("level_floor", 0))
        if mode == TIMED:
            # a saved clock is worth keeping, but never below a few seconds
            saved = entry.get("time_left")
            if isinstance(saved, (int, float)):
                self.time_left = max(8.0, min(TIMED_MAX, float(saved)))
        if mode == SHAPES:
            self.shape_name = entry.get("shape") or self.shape_name
            if self.shape_name in SHAPE_MASKS:
                self.shape_cells = shape_mask(self.shape_name)
        # a saved board that somehow has a free match or no move would strand
        # the player, so fall back to a fresh one and keep the progress
        if find_matches(grid) or not has_move(grid):
            return True
        self.grid = grid
        self.begin_intro()
        return True

    def draw_wiped(self, screen):
        box = pygame.Rect(WIDTH // 2 - S(230), HEIGHT // 2 - S(90), S(460), S(180))
        screen.blit(translucent(box.size, DIALOG_FILL, DIALOG_EDGE, S(16)),
                    box.topleft)
        lines = [(self.font_big, "DATA RESET", GOLD),
                 (self.font_small, "ALL SAVES AND SETTINGS DELETED", DIM),
                 (self.font, "PLEASE CLOSE THE GAME", TEXT)]
        y = box.y + S(30)
        for font, text, colour in lines:
            img = font.render(text, True, colour)
            screen.blit(img, (box.centerx - img.get_width() // 2, y))
            y += img.get_height() + 16

    def return_to_title(self):
        self.save_run()
        self.campaign_bg = None       # stop showing the area on the title
        self.campaign_open = False
        self.menu_open = False
        self.music_open = False
        self.over = False
        self.on_title = True
        self.title_ready = False
        self.audio.chosen = None
        self.audio.use_playlist(TITLE)

    def open_menu(self):
        self.sync_menu_labels()
        self.build_scale_buttons()  # rebuild scale buttons whenever menu opens
        # the menu takes over: nothing else stays open behind it
        self.music_open = False
        self.bg_picker_open = False
        self.extras_open = False
        self.resume_open = False
        self.credits_open = False
        self.wipe_open = False
        self.timed_duration_picker_open = False
        self.menu_open = True
        self.sel = None
        self.dragging = None

    def build_scale_buttons(self):
        """Render-scale chips, laid into the reserved band. Fullscreen only."""
        self.scale_buttons = []
        if self.display is None or not self.display.fullscreen:
            return

        box = self.menu_rect()
        sx, sw = box.x + S(30), box.width - S(60)
        current = RENDER_SCALE

        gap = S(8)
        btn_w = (sw - gap * (len(SCALE_OPTIONS) - 1)) // len(SCALE_OPTIONS)
        for i, (factor, label) in enumerate(SCALE_OPTIONS):
            on = abs(factor - current) < 0.01
            self.scale_buttons.append(Button(
                (sx + i * (btn_w + gap), self.scale_band_y,
                 btn_w, self.scale_band_h),
                label,
                lambda f=factor: self.apply_scale(f),
                accent=GOLD if on else (120, 126, 140),
            ))

    def apply_scale(self, factor):
        """Menu action: change the internal render resolution."""
        if self.display is None or not self.display.fullscreen:
            return
        if abs(RENDER_SCALE - factor) < 0.01:
            return
        self.rebuild_at_scale(factor)
        self.settings["render_scale"] = factor
        self.note = f"render scale {int(factor * 100)}%"
        self.save_settings()

    def rebuild_at_scale(self, factor):
        """Re-render the game at a new internal resolution.

        Everything derived from the layout constants has to be rebuilt: the
        type, the gem art, the cached panel surfaces and every widget rect.
        Rebuilding only some of them was what made earlier attempts at this
        fall apart.
        """
        was = RENDER_SCALE
        apply_render_scale(factor)
        if was:
            k = RENDER_SCALE / was
            self.mouse = (int(self.mouse[0] * k), int(self.mouse[1] * k))
        self.build_fonts()
        self.reload_assets()                 # sprites, effects, backdrops
        self.panel_bg = translucent((PANEL_W, PANEL_H), PANEL_FILL,
                                    PANEL_EDGE, S(14))
        self.menu_bg = translucent(self.menu_rect().size, PANEL_FILL,
                                   PANEL_EDGE, S(16))
        self.motes = [[random.uniform(0, WIDTH), random.uniform(0, HEIGHT),
                       random.uniform(1.0, 2.8) * RENDER_SCALE,
                       random.uniform(-11, -3) * RENDER_SCALE,
                       random.uniform(0.25, 0.7)]
                      for _ in range(PARTICLE_COUNT)]
        self.build_widgets()
        self.build_title_widgets()
        self.build_campaign_widgets()
        self.apply_opacity()
        if self.display is not None:
            self.display.resize_layer()
        self.build_scale_buttons()           # refresh which chip is lit

    def close_menu(self):
        self.menu_open = False
        self.dragging = None

    def quit(self):
        self.save_run()
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
        if self.on_title and self.resume_open:
            for button in self.resume_buttons:
                if button.hit(pos):
                    button.down = True
                    self.audio.play("menuclick")
                    return
            if not self.resume_rect().collidepoint(pos):
                # clicking away backs out without touching the save
                self.resume_open = False
                self.fresh_held = 0.0
                self.audio.play("menuclick")
            return
        if self.on_title and self.credits_open:
            for button in self.credit_buttons:
                if button.hit(pos):
                    button.down = True
                    self.audio.play("menuclick")
                    return
            return
        if self.on_title and not self.extras_open and not self.menu_open \
                and self.credit_rect().collidepoint(pos):
            if self.credit_armed:
                self.open_credits()
            else:
                self.credit_armed = True
                self.audio.play("menuclick")
            return
        if self.on_title and self.settings_open:
            for slider in self.setting_sliders:
                if slider.hit(pos):
                    return slider
            for button in self.setting_buttons:
                if button.hit(pos):
                    return button
            return None
        if self.on_title and self.campaign_open:
            for i, rect in enumerate(self.campaign_rows):
                if rect.collidepoint(pos):
                    self.start_campaign_level(self.campaign_level_at(i))
                    return
            for button in self.campaign_arrows + self.campaign_buttons:
                if button.hit(pos):
                    button.down = True
                    self.audio.play("menuclick")
                    return
            if not self.campaign_rect().collidepoint(pos):
                self.close_campaign()
            return
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
                for button in self.scale_buttons:
                    if button.hit(pos):
                        return button
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
        if self.bg_picker_open:
            for button in self.bg_picker_buttons:
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
            for button in self.scale_buttons:
                if button.hit(pos):
                    return button
            for button in self.menu_buttons:
                if button.hit(pos):
                    return button
            return None
        for button in self.buttons:
            if self.mode == CAMPAIGN and button.label in LOCKED_IN_CAMPAIGN:
                continue          # the area owns these; do not even hover
            if button.hit(pos):
                return button
        return None

    def on_down(self, pos):
        if self.data_wiped:
            return                       # nothing is clickable any more
        if self.on_title and self.timed_duration_picker_open:
            for button in self.duration_buttons:
                if button.hit(pos):
                    button.down = True
                    return
            # Click outside the picker dismisses it
            if not self.duration_picker_rect().collidepoint(pos):
                self.close_duration_picker()
            return
        if self.on_title and self.extras_open:
            for key, rect, _, _ in self.extra_rows:
                if rect.collidepoint(pos):
                    self.toggle_extra(key)
                    self.extras_note = ""
                    return
            if not self.extras_rect().collidepoint(pos):
                # clicking away backs out, keeping whatever was ticked
                self.close_extras()
                return
            # inside the box but not on a row: fall through to the buttons
        elif self.on_title and not self.title_ready and not self.overlay_open():
            self.title_ready = True        # first click reveals the modes
            self.audio.play("menuclick")
            return
        # the graphics toggles live in the menu, which is reachable from both
        # the title screen and the board - so this must come before any
        # on_title early return
        if self.wipe_open:
            for button in self.wipe_buttons:
                if button.hit(pos):
                    button.down = True
                    if button.label == "NO":
                        self.audio.play("menuclick")
                    return
            return
        if self.menu_open:
            # Rows and scale chips are handled here; anything else inside the
            # box must fall through to widgets_at so the RESUME / QUIT /
            # RETURN TO TITLE buttons still arm themselves on mouse-down.
            for key, rect, _, _ in self.setting_rows:
                if rect.collidepoint(pos):
                    self.toggle_setting(key)
                    return
            if not self.menu_rect().collidepoint(pos):
                self.audio.play("menuclick")
                self.close_menu()      # click outside the box dismisses it
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
        # The picker panels are reachable from the title screen too, so they
        # get first refusal. The title catch-all below swallows everything it
        # sees, which is why choosing a song from the title screen never
        # worked.
        if self.on_title and not (self.music_open or self.bg_picker_open):
            if self.menu_open and not self.menu_rect().collidepoint(pos):
                self.audio.play("menuclick")
                self.close_menu()
            return
        if self.music_open:
            if self.music_title_rect().collidepoint(pos):
                self.tap_music_title()
                return
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
        if self.bg_picker_open:
            row = self.bg_list.index_at(pos)
            if row >= 0:
                self.audio.play("menuclick")
                self.bg_index_override = row
                self.bg_list.current = row
            elif not self.music_rect().collidepoint(pos):
                self.audio.play("menuclick")
                self.close_background_picker()
            return
        if self.over:
            return                     # nothing but those two buttons is live
        if self.wipe_open:
            for button in self.wipe_buttons:
                if button.hit(pos):
                    button.down = True
                    if button.label == "NO":
                        self.audio.play("menuclick")
                    return
            return
        if self.state not in ("idle", "clear", "fall"):
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
        self.mouse = pos            # before any early return, or the
                                    # spotlight freezes mid-drag
        if self.data_wiped:
            return
        if self.dragging is not None:
            self.dragging.set_from(pos)
            return
        # Handle hover for music and background picker lists
        if self.music_open:
            self.music_list.hover = self.music_list.index_at(pos)
            return
        if self.bg_picker_open:
            self.bg_list.hover = self.bg_list.index_at(pos)
            return
        # Don't allow button hover when duration picker is open
        if self.timed_duration_picker_open:
            return
        if self.on_title:
            if self.menu_open:
                active = []
            elif self.credits_open:
                active = self.credit_buttons
            elif self.resume_open:
                active = self.resume_buttons
            elif self.wipe_open:
                active = self.wipe_buttons
            elif self.campaign_open:
                active = self.campaign_arrows + self.campaign_buttons
            elif self.extras_open:
                active = self.extra_buttons
            else:
                active = (self.title_buttons if self.title_ready else [])
        elif self.over:
            active = self.over_buttons
        elif self.menu_open:
            active = self.menu_buttons
        else:
            active = self.buttons
        for button in (self.buttons + self.menu_buttons + self.over_buttons
                       + self.title_buttons + self.setting_buttons
                       + self.extra_buttons + self.duration_buttons
                       + self.credit_buttons + self.music_buttons
                       + self.bg_picker_buttons + self.resume_buttons
                       + self.campaign_arrows + self.campaign_buttons
                       + self.wipe_buttons):
            button.hover = button in active and button.hit(pos)

    def on_up(self, pos):
        if self.data_wiped:
            return
        if self.dragging is not None:
            self.dragging = None
            return

        fired = None
        for button in (self.buttons + self.menu_buttons + self.over_buttons
                       + self.title_buttons + self.music_buttons
                       + self.extra_buttons + self.scale_buttons
                       + self.setting_buttons + self.credit_buttons
                       + self.resume_buttons + self.wipe_buttons + self.duration_buttons
                       + self.campaign_arrows + self.campaign_buttons
                       + self.bg_picker_buttons):
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
        self.ease_readouts(dt)
        self.ease_background(dt)
        # Debris from explosions lives outside the state machine so it always
        # finishes its arc, whatever the board is doing.
        if self.debris:
            for piece in self.debris:
                piece.update(dt)
            self.debris = [p for p in self.debris if p.t < p.delay + 0.95]
        if self.scheduled_actions:
            self.update_scheduled_actions(dt)
        if self.credits_open:
            self.update_credit_gems(dt)
            self.credit_scroll += S(BASE_CREDIT_SPEED) * dt
            if self.credit_scroll > self.credits_height():
                self.credit_scroll = self.start_scroll()   # loop the roll
        if self.on_title:
            self.update_motes(dt)
            return
        self.update_motes(dt)
        if self.effects:
            self.effects = [e for e in self.effects if e.update(dt)]
        if self.go_left > 0:
            self.go_left = max(0.0, self.go_left - dt)
        if self.shake > 0 or self.shake_target > 0:
            self.shake_t += dt
            # Smoothly ramp towards target over SHAKE_RAMP seconds
            if self.shake < self.shake_target:
                self.shake = min(self.shake_target, self.shake + (self.shake_target / SHAKE_RAMP) * dt)
            else:
                self.shake = max(self.shake_target, self.shake - (self.shake_target / SHAKE_RAMP) * dt)
            # Decay the target smoothly
            self.shake_target = max(0.0, self.shake_target - self.shake_target * SHAKE_DECAY * dt)
        # Update note timer for fade in/out
        if self.note:
            self.note_time += dt
            if self.note_time > 2.5:  # Clear note after 2.5 seconds
                self.note = ""
        if self.time_pops:
            self.time_pops = [p for p in self.time_pops if p.update(dt)]
        if self.score_pops:
            self.score_pops = [p for p in self.score_pops if p.update(dt)]
        if self.puffs:
            self.puffs = [p for p in self.puffs if p.update(dt)]

        # The clock only runs while the board is actually playable. Opening
        # the menu pauses it - otherwise adjusting the volume costs you time.
        if (self.timed and not self.over
                and not self.menu_open and not self.music_open
                and not self.bg_picker_open
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
            # Check if this gem is a flame gem or bomb and spawn explosion
            # effects immediately when the rainbow zaps it.
            gem = self.grid[r][c]
            if gem is not None and (gem.power == FLAME or gem.cell_type == CELL_BOMB):
                if self.bubbly:
                    self.schedule_explosion_chain({(r, c)}, max_hurl=2)
                self.spawn_effect("explode", r, c)
                self.spawn_smoke(r, c)
                self.audio.play("explode")
                self.add_shake(SHAKE_FLAME * 0.5)
            else:
                if self.bubbly:
                    self.hurl_blast({(r, c)}, self.rainbow_origin)
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
            self.begin_clear(targets, {}, is_rainbow=True)

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
            
            # Check if swapping with rock or bomb
            other_gem = self.grid[other[0]][other[1]]
            if other_gem.cell_type == CELL_ROCK or other_gem.cell_type == CELL_BOMB:
                # Apply swap FIRST so the bomb/rock is now at hyper position
                self.apply_swap()
                # Now get targets with the swapped positions (bomb/rock is now at hyper)
                targets = rock_bomb_targets(self.grid, other, hyper)
                origin = hyper  # Origin is now where the bomb/rock ended up after swap
                cell_type_name = "ROCKS" if other_gem.cell_type == CELL_ROCK else "BOMBS"
                self.set_note(f"ALL {cell_type_name}!")
                self.spawn_effect("hyper", *origin)
                self.begin_rainbow(origin, targets)
                return
            
            targets = hyper_targets(self.grid, hyper, other)
            # Actually complete the swap so the rainbow gem ends up in the
            # square it was dragged into, rather than snapping back and
            # detonating from where it started.
            self.apply_swap()
            origin = other
            self.set_note("BOARD WIPE!" if both else "RAINBOW!")
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

    def begin_clear(self, cells, spawns, is_rainbow=False):
        self.matched = cells
        self.spawns = spawns
        self.award_time(cells)
        explosive_cells = set()
        for r, c in cells:
            gem = self.grid[r][c]
            if gem is not None and (gem.power == FLAME or gem.cell_type == CELL_BOMB):
                explosive_cells.add((r, c))
        for r, c in cells:
            if (r, c) in explosive_cells:
                continue
            self.spawn_effect("match", r, c)
        if not self.scoring:
            gained = 0
        elif self.extra("lock"):
            # only the locked colour pays out
            gained = 0
            matched_locked = []
            for r, c in cells:
                if self.grid[r][c] is not None and self.grid[r][c].kind == self.lock_kind:
                    pts = POINTS_PER_GEM * self.cascade
                    gained += pts
                    matched_locked.append((r, c))
            # Show one accumulated score pop at center of matched cells
            if matched_locked:
                avg_r = sum(rc[0] for rc in matched_locked) / len(matched_locked)
                avg_c = sum(rc[1] for rc in matched_locked) / len(matched_locked)
                x = BOARD_X + int((avg_c + 0.5) * TILE)
                y = BOARD_Y + int((avg_r + 0.5) * TILE)
                self.score_pops.append(ScorePop(x, y, gained, is_rainbow=is_rainbow))
        else:
            gained = len(cells) * POINTS_PER_GEM * self.cascade
            # Show one accumulated score pop at center of matched cells
            avg_r = sum(rc[0] for rc in cells) / len(cells)
            avg_c = sum(rc[1] for rc in cells) / len(cells)
            x = BOARD_X + int((avg_c + 0.5) * TILE)
            y = BOARD_Y + int((avg_r + 0.5) * TILE)
            # Use rainbow color if this is a rainbow gem detonation
            self.score_pops.append(ScorePop(x, y, gained, is_rainbow=is_rainbow))
        
        # Bonus gems: show individual popups for each one
        if self.scoring:
            for (r, c), power in spawns.items():
                bonus = HYPER_BONUS if power == HYPER else FLAME_BONUS
                gained += bonus
                # Show bonus score pop at power gem location
                x = BOARD_X + int((c + 0.5) * TILE)
                y = BOARD_Y + int((r + 0.5) * TILE)
                self.score_pops.append(ScorePop(x, y, bonus))
        self.score += gained
        self.gems_cleared += len(cells)

        self.audio.play_match(self.cascade, self.multi_run)
        for power in spawns.values():
            self.audio.play("hypermade" if power == HYPER else "flamemade")
        flames = [rc for rc in cells
                  if self.grid[rc[0]][rc[1]] is not None
                  and self.grid[rc[0]][rc[1]].power == FLAME]
        if flames and not is_rainbow:
            self.add_shake(SHAKE_FLAME)
            self.audio.play("explode")
            self.hurl_blast(cells, flames[0])
        if HYPER in spawns.values():
            self.set_note("HYPERCUBE!")
        elif FLAME in spawns.values():
            self.set_note("FLAME GEM!")
        elif self.cascade > 1:
            self.set_note(f"CASCADE x{self.cascade}")
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
        self.falls = collapse(self.grid, bonuses=self.timed and self.timed_bonus_gems,
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

    def campaign_done(self):
        """Has the objective been met? Checked after every settled move."""
        goal = self.goal
        if goal is None:
            return False
        if goal["kind"] == GOAL_GEMS:
            return self.gems_cleared >= goal["target"]
        return self.score >= goal["target"]

    def check_campaign(self, spent_move):
        """Win, lose, or carry on. Winning takes priority over running out:
        landing the target on the final move is a win, not a loss."""
        if self.mode != CAMPAIGN or self.goal is None or self.over:
            return
        if spent_move and self.goal["kind"] != GOAL_TIME:
            self.moves_left = max(0, self.moves_left - 1)
        if self.campaign_done():
            self.win_campaign()
            return
        if self.goal["kind"] != GOAL_TIME and self.moves_left <= 0:
            self.end_game()          # clears the note, so say it afterwards
            self.set_note("OUT OF MOVES")

    def win_campaign(self):
        self.campaign_won = True
        self.unlock_next_level()
        self.set_note("LEVEL COMPLETE")
        self.audio.play("levelup")
        self.over = True
        self.sel = None
        self.hint = None
        self.menu_open = False

    def unlock_next_level(self):
        nxt = min(CAMPAIGN_LEVELS, self.campaign_level_num + 1)
        if nxt > self.campaign_unlocked:
            self.campaign_unlocked = nxt
            self.save_campaign()

    def settle(self):
        self.pair = None
        self.cascade = 0
        # Only a move the player made counts down a fuse. settle() also runs
        # at the end of every cascade step, which would otherwise burn several
        # moves off every bomb for a single swap.
        spent_move = self.move_pending
        blast = self.tick_bombs() if self.move_pending else None
        self.move_pending = False
        if blast:
            self.cascade = 1
            self.multi_run = False
            self.set_note("BOOM!")
            self.add_shake(SHAKE_BOMB)
            self.audio.play("explode")
            for r, c in self.spent_bombs:
                self.spawn_effect("explode", r, c)
                self.spawn_smoke(r, c)
            if self.spent_bombs:
                self.hurl_blast(blast, next(iter(self.spent_bombs)))
            self.begin_clear(blast, {})
            return
        if (self.scoring and self.mode != CAMPAIGN
                and self.level_progress() >= 1.0):
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
        if self.mode == CAMPAIGN:
            self.check_campaign(spent_move)

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
                             (2, 2, TILE - S(4), TILE - S(4)), S(3), border_radius=S(10))
            screen.blit(ring, (int(x), int(y)))
        label = self.font_big.render(str(fuse), True, (255, 255, 255))
        pad = S(5)
        w = label.get_width() + pad * 2
        h = label.get_height() + S(2)
        chip = translucent((w, h), (200, 60, 50, 235) if hot
                           else (30, 34, 48, 225), None, h // 2)
        chip.blit(label, (pad, 1))
        screen.blit(chip, (int(x + (TILE - w) / 2), int(y + TILE - h - S(4))))

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

    def selection_pulse(self):
        """A small scale wobble on the gem you have picked up."""
        if not self.bubbly:
            return 1.0
        return 1.0 + 0.045 * math.sin(self.time * 6.5)

    def gem_draw_info(self, r, c):
        """Returns (x, y, scale) for the gem at r,c."""
        x = BOARD_X + c * TILE
        y = BOARD_Y + r * TILE
        scale = 1.0

        if self.state == "idle" and self.sel == (r, c):
            return x, y, self.selection_pulse()

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
            p = (self.ease_pop(self.t) if self.state == "swap"
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
            curve = (self.ease_land(self.t) if d >= 3
                     else ease_out(self.t))
            y -= d * TILE * (1 - curve)

        elif self.state == "intro":
            # each column starts a little later, so the board lands left to right
            p = clamp01((self.t * INTRO_TIME - c * INTRO_STAGGER) / INTRO_FALL)
            y -= (ROWS + 2) * TILE * (1 - self.ease_land(p))

        elif self.state == "levelup":
            # old board peels away diagonally before the next one drops
            delay = (r + c) / (ROWS + COLS) * 0.30
            p = clamp01((self.t * self.levelup_pause() - delay) / 0.40)
            scale = 1.0 - ease_in_out(p)
            y -= S(30) * p

        if (r, c) in self.pops:
            p = 1.0 - self.pops[(r, c)] / POP_TIME
            scale *= 1.0 + 0.5 * (1 - p) * math.cos(p * 13.0) * (1 - p)

        return x, y, scale

    def draw_bonus_tag(self, screen, x, y):
        """Green +3s badge, pinned to the bottom of a bonus gem."""
        pulse = 0.5 + 0.5 * math.sin(self.time * 4.5)
        label = self.font_small.render(f"+{int(BONUS_SECONDS)}s", True,
                                       (18, 32, 24))
        pad = S(5)
        w = label.get_width() + pad * 2
        h = label.get_height() + S(2)
        chip = translucent((w, h), (126, 240, 168, 200 + int(55 * pulse)),
                           None, h // 2)
        chip.blit(label, (pad, 1))
        screen.blit(chip, (int(x + (TILE - w) / 2), int(y + TILE - h - S(3))))

        ring = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        pygame.draw.rect(ring, (126, 240, 168, int(70 + 60 * pulse)),
                         (2, 2, TILE - S(4), TILE - S(4)), S(2), border_radius=S(10))
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
        x = PANEL_X + S(16)
        width = PANEL_W - S(32)

        if not self.scoring:
            # Zen keeps no score, so the readouts would only ever show 0
            zen = self.font_score.render("ZEN", True, GOLD)
            screen.blit(zen, (x, PANEL_Y + S(40)))
            for button in self.buttons:
                button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))
            self.draw_note(screen, x, PANEL_Y + S(208), width)
            track = self.audio.now_playing()
            if track:
                screen.blit(self.font_small.render("NOW PLAYING", True, DIM),
                            (x, PANEL_Y + PANEL_H - S(296)))
                self.wrapped(screen, track, x, PANEL_Y + PANEL_H - S(274),
                             width, DIM)
            return

        screen.blit(self.font_small.render("SCORE", True, DIM), (x, PANEL_Y + S(26)))
        screen.blit(self.font_score.render(f"{int(self.shown_score):,}", True, TEXT),
                    (x, PANEL_Y + S(48)))

        if self.timed:
            low = self.time_left <= LOW_TIME
            pulse = 0.5 + 0.5 * math.sin(self.time * 6.0)
            color = ((255, int(90 + 60 * pulse), int(90 + 40 * pulse)) if low
                     else TEXT)
            secs = int(math.ceil(self.time_left))
            screen.blit(self.font_small.render("TIME", True, DIM),
                        (x, PANEL_Y + S(116)))
            screen.blit(self.font_score.render(f"{secs // 60}:{secs % 60:02d}",
                                               True, color), (x, PANEL_Y + S(138)))
            if self.mode != CAMPAIGN:
                screen.blit(self.font_small.render(f"LEVEL {self.level}",
                                                   True, DIM),
                            (x, PANEL_Y + S(182)))
        elif self.mode != CAMPAIGN:
            screen.blit(self.font_small.render("LEVEL", True, DIM),
                        (x, PANEL_Y + S(116)))
            screen.blit(self.font_score.render(str(self.level), True, TEXT),
                        (x, PANEL_Y + S(138)))

        # The bar always shows progress toward the next level. In timed mode
        # the clock has its own readout above, so mirroring it here left no
        # indication of how close the next level was. Campaign has no levels
        # to climb - its own objective bar goes here instead.
        if self.mode != CAMPAIGN:
            self.bar(screen, x, PANEL_Y + (S(200) if self.timed else S(184)),
                     width, S(10), self.shown_progress, GOLD)

        if self.extra("lock"):
            y = PANEL_Y + S(250)
            screen.blit(self.font_small.render("SCORING", True, DIM), (x, y))
            sprite = self.normal[self.lock_kind]
            screen.blit(sprite, (x, y + 20))
            secs = max(0, int(math.ceil(self.lock_left)))
            screen.blit(self.font_score.render(str(secs), True,
                        (232, 96, 96) if secs <= 3 else TEXT),
                        (x + TILE + S(12), y + S(36)))
            self.bar(screen, x, y + TILE + S(26), width, S(8),
                     self.lock_left / LOCK_SECONDS, (176, 140, 240))

        mode = self.font_small.render(self.mode_label(), True, DIM)
        screen.blit(mode, (PANEL_X + PANEL_W - S(16) - mode.get_width(),
                           PANEL_Y + S(28)))

        # Timed mode has an extra bar above this, so the note sits lower
        # there to keep clear of it.
        note_y = PANEL_Y + (S(246) if self.timed else S(214))
        if self.mode == EXTRAS and self.timed and self.extra("lock"):
            note_y -= S(6)
        self.draw_note(screen, x, note_y, width)

        track = self.audio.now_playing()
        if track:
            screen.blit(self.font_small.render("NOW PLAYING", True, DIM),
                        (x, PANEL_Y + PANEL_H - S(296)))
            self.wrapped(screen, track, x, PANEL_Y + PANEL_H - S(274), width, DIM)

        if self.mode == CAMPAIGN and self.goal is not None:
            self.draw_objective(screen, x,
                                PANEL_Y + (S(186) if self.timed else S(116)),
                                width)

        for button in self.buttons:
            if self.mode == CAMPAIGN and button.label in LOCKED_IN_CAMPAIGN:
                self.draw_locked_button(screen, button)
            else:
                button.draw(screen, self.font,
                            self.hover_lift.get(id(button), 0.0))

    def draw_locked_button(self, screen, button):
        """A panel button the current mode has taken control of."""
        screen.blit(translucent(button.rect.size, (255, 255, 255, 10), None,
                                S(10)), button.rect.topleft)
        label = Button.fit(self.font, button.label, button.rect.width - S(14))
        image = label.render(button.label, True, (86, 92, 106))
        screen.blit(image, image.get_rect(center=button.rect.center))

    def draw_objective(self, screen, x, y, width):
        """Objective and how far along it is, on the score panel."""
        goal = self.goal
        # The badge at the top of the panel already names the area, so this
        # only needs the level number.
        head = self.font_small.render(f"LEVEL {self.campaign_level_num}", True,
                                      (96, 200, 232))
        screen.blit(head, (x, y))
        y += head.get_height() + S(6)

        # "SCORE 1,300 IN 15 MOVES" is too wide for the panel in one line, so
        # it breaks at the IN, which stays on the second line to keep it
        # reading as one sentence.
        head_text, _, tail = goal["text"].partition(" IN ")
        for line in (head_text, f"IN {tail}") if tail else (head_text,):
            img = Button.fit(self.font_small, line, width)
            screen.blit(img.render(line, True, TEXT), (x, y))
            y += img.get_height() + S(3)
        y += S(5)

        if goal["kind"] == GOAL_GEMS:
            have, need = self.gems_cleared, goal["target"]
        else:
            have, need = self.score, goal["target"]
        frac = clamp01(have / max(1, need))
        bar = pygame.Rect(x, y, width, S(6))
        screen.blit(translucent(bar.size, (255, 255, 255, 38), None, S(3)),
                    bar.topleft)
        if frac > 0:
            screen.blit(translucent((max(S(3), int(width * frac)), bar.height),
                                    GOLD + (235,), None, S(3)), bar.topleft)
        y += bar.height + S(6)

        mods = campaign_modifier_label(goal)
        if mods:
            self.wrapped(screen, mods, x, y, width, (176, 140, 240))
            y += self.font_small.get_height() * (
                1 + (self.font_small.size(mods)[0] > width)) + S(6)

        if goal["kind"] != GOAL_TIME:
            hot = self.moves_left <= 3
            left = self.font_small.render(f"{self.moves_left} MOVES LEFT", True,
                                          (232, 92, 92) if hot else DIM)
            screen.blit(left, (x, y))

    def wrapped(self, screen, text, x, y, width, color):
        """Panel is narrow, so long notes need to wrap rather than overflow."""
        words = text.split()
        line = ""
        for word in words:
            trial = f"{line} {word}".strip()
            if self.font_small.size(trial)[0] > width and line:
                screen.blit(self.font_small.render(line, True, color), (x, y))
                y += self.font_small.get_height() + S(3)
                line = word
            else:
                line = trial
        if line:
            screen.blit(self.font_small.render(line, True, color), (x, y))

    def spotlight_hole(self):
        """A black tile whose alpha fades from clear at the centre to solid
        at the rim. Cached: rebuilding this gradient every frame was the one
        part of the effect expensive enough to notice."""
        radius = S(SPOTLIGHT_RADIUS)
        feather = max(1, S(SPOTLIGHT_FEATHER))
        size = radius * 2
        if self._spot_hole is not None and self._spot_hole.get_width() == size:
            return self._spot_hole
        hole = pygame.Surface((size, size), pygame.SRCALPHA)
        hole.fill((0, 0, 0, 255))
        # Concentric circles from the rim inwards. pygame.draw writes raw
        # pixel values rather than blending, so each ring simply replaces the
        # alpha under it.
        steps = max(2, feather)
        for i in range(steps + 1):
            f = i / steps
            r = int(radius - feather * (1 - f))
            alpha = int(255 * (1 - f) ** 2)
            if r > 0:
                pygame.draw.circle(hole, (0, 0, 0, alpha), (radius, radius), r)
        self._spot_hole = hole
        return hole

    def draw_spotlight(self, screen):
        """Black everywhere except a soft circle around the pointer."""
        if self._spot_mask is None or self._spot_mask.get_size() != (WIDTH, HEIGHT):
            self._spot_mask = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        mask = self._spot_mask
        mask.fill((0, 0, 0, 255))
        hole = self.spotlight_hole()
        radius = hole.get_width() // 2
        mx, my = self.mouse
        # BLEND_RGBA_MIN keeps the lower alpha of the two, which punches the
        # cached gradient straight through the black sheet in one blit.
        mask.blit(hole, (int(mx) - radius, int(my) - radius),
                  special_flags=pygame.BLEND_RGBA_MIN)
        screen.blit(mask, (0, 0))

    def draw_holes(self, screen, opaque=False):
        """Darken the cells that are not part of a Shapes silhouette.

        Drawn twice: once under the gems so the board reads as a shape, and
        again over them, because a gem falling into a lower row passes
        visually through any hole above it. Always darkened tiles, never opaque.
        """
        if self.mode != SHAPES:
            return
        # Always use darkened tiles - no opaque blocks
        shade = (14, 16, 26, 200)
        tile = translucent((TILE, TILE), shade, None, S(0))
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
                             (2, 2, TILE - S(4), TILE - S(4)),
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

        box = self.over_rect()
        screen.blit(translucent(box.size, DIALOG_FILL, DIALOG_EDGE, S(16)),
                    box.topleft)

        if self.mode == CAMPAIGN and self.goal is not None:
            area = CAMPAIGN_AREAS[campaign_area_of(self.campaign_level_num)]
            if self.campaign_won:
                lines = [(self.font_huge, "COMPLETE", (126, 216, 150), 26),
                         (self.font_score, f"{self.score:,}", GOLD, 14),
                         (self.font_small, "POINTS", DIM, 20),
                         (self.font, f"{area} - level {self.campaign_level_num}",
                          DIM, 0)]
            else:
                lines = [(self.font_huge, "FAILED", (232, 92, 92), 26),
                         (self.font, self.goal["text"], DIM, 16),
                         (self.font_score, f"{self.score:,}", GOLD, 14),
                         (self.font_small, "POINTS", DIM, 0)]
        else:
            lines = [(self.font_huge, "TIME UP", TEXT, 30),
                     (self.font_score, f"{self.score:,}", GOLD, 14),
                     (self.font_small, "POINTS", DIM, 22),
                     (self.font, f"reached level {self.level}", DIM, 0)]
        y = box.y + S(34)
        for font, text, color, gap in lines:
            image = font.render(text, True, color)
            screen.blit(image, (box.centerx - image.get_width() // 2, y))
            y += image.get_height() + gap

        for button in self.over_buttons:
            button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))

    def draw_music(self, screen):
        box = self.music_rect()
        screen.blit(translucent(box.size, DIALOG_FILL, DIALOG_EDGE, S(16)),
                    box.topleft)
        title = self.font_big.render(self.music_title(), True,
                                     GOLD if self.music_secret else TEXT)
        screen.blit(title, (box.x + S(24), box.y + S(24)))
        hint = self.font_small.render("SCROLL WHEEL", True, DIM)
        screen.blit(hint, (box.right - S(24) - hint.get_width(), box.y + S(30)))
        self.music_list.draw(screen, self.font)
        for button in self.music_buttons:
            button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))

    def draw_background_picker(self, screen):
        box = self.music_rect()
        screen.blit(translucent(box.size, DIALOG_FILL, DIALOG_EDGE, S(16)),
                    box.topleft)
        title = self.font_big.render("BACKGROUNDS", True, TEXT)
        screen.blit(title, (box.x + S(24), box.y + S(24)))
        hint = self.font_small.render("SCROLL WHEEL", True, DIM)
        screen.blit(hint, (box.right - S(24) - hint.get_width(), box.y + S(30)))
        self.bg_list.draw(screen, self.font)
        for button in self.bg_picker_buttons:
            button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))

    def sync_menu_labels(self):
        """Point the two context buttons at the right thing for where we are."""
        bottom = self.menu_buttons[2]
        if self.on_title:
            bottom.label, bottom.action = "RESET DATA", self.ask_wipe
            bottom.accent = (232, 92, 92)
        else:
            bottom.label = "RETURN TO TITLE SCREEN"
            bottom.action = self.return_to_title
            bottom.accent = GOLD

    def draw_menu(self, screen):
        self.sync_menu_labels()

        box = self.menu_rect()
        screen.blit(self.menu_bg, box.topleft)

        title = self.font_big.render("MENU", True, TEXT)
        screen.blit(title, (box.x + S(30), box.y + S(26)))

        # Pixel glyphs are far wider per character than proportional type, so
        # this sits under the title rather than beside it, and stays short.
        hint = self.font_small.render("ESC TO CLOSE", True, DIM)
        screen.blit(hint, (box.right - S(30) - hint.get_width(),
                           box.y + S(26) + title.get_height() - hint.get_height()))

        for key, rect, label, blurb in self.setting_rows:
            on = self.settings.get(key, True)
            screen.blit(translucent(rect.size,
                                    GOLD + (60,) if on else (255, 255, 255, 18),
                                    None, S(8)), rect.topleft)
            tick = pygame.Rect(rect.x + S(8), rect.centery - S(10), S(20), S(20))
            pygame.draw.rect(screen, TEXT if on else DIM, tick, max(1, S(2)),
                             border_radius=S(4))
            if on:
                pygame.draw.line(screen, GOLD, (tick.x + S(4), tick.centery),
                                 (tick.centerx, tick.bottom - S(5)), S(3))
                pygame.draw.line(screen, GOLD, (tick.centerx, tick.bottom - S(5)),
                                 (tick.right - S(3), tick.y + S(3)), S(3))
            name = self.font.render(label, True, TEXT if on else DIM)
            screen.blit(name, (rect.x + S(38), rect.y + S(5)))
            note = Button.fit(self.font_small, blurb, rect.width - S(46))
            screen.blit(note.render(blurb, True, DIM),
                        (rect.x + S(38), rect.y + S(5) + name.get_height() + S(4)))

        for slider in self.sliders:
            slider.draw(screen, self.font, self.font_small,
                        dragging=self.dragging is slider)

        head = self.font_small.render("GRAPHICS", True, DIM)
        screen.blit(head, (box.x + S(30), box.y + S(210)))
        for key, rect, label, blurb in self.setting_rows:
            on = self.settings.get(key, True)
            screen.blit(translucent(rect.size,
                                    GOLD + (60,) if on else (255, 255, 255, 18),
                                    None, S(8)), rect.topleft)
            tick = pygame.Rect(rect.x + S(8), rect.centery - S(10), S(20), S(20))
            pygame.draw.rect(screen, TEXT if on else DIM, tick, max(1, S(2)),
                             border_radius=S(4))
            if on:
                pygame.draw.line(screen, GOLD, (tick.x + S(4), tick.centery),
                                 (tick.centerx, tick.bottom - S(5)), S(3))
                pygame.draw.line(screen, GOLD, (tick.centerx, tick.bottom - S(5)),
                                 (tick.right - S(3), tick.y + S(3)), S(3))
            name = self.font.render(label, True, TEXT if on else DIM)
            screen.blit(name, (rect.x + S(38), rect.y + S(5)))
            note = Button.fit(self.font_small, blurb, rect.width - S(46))
            screen.blit(note.render(blurb, True, DIM),
                        (rect.x + S(38), rect.y + S(5) + name.get_height() + S(4)))

        if self.scale_buttons:
            head = self.font_small.render("RESOLUTION", True, DIM)
            screen.blit(head, (box.x + S(30), self.scale_band_y - S(20)))
            for button in self.scale_buttons:
                button.draw(screen, self.font_small,
                            self.hover_lift.get(id(button), 0.0))

        for button in self.menu_buttons:
            button.draw(screen, self.font, self.hover_lift.get(id(button), 0.0))

    def draw_levelup(self, screen):
        """Shockwave and banner when the level bar fills."""
        p = ease_out(self.t)
        ring = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        center = (BOARD_X + BOARD_W // 2, BOARD_Y + BOARD_H // 2)
        pygame.draw.circle(ring, (255, 255, 255, int(170 * (1 - p))),
                           center, int(p * WIDTH * 0.85), S(10))
        screen.blit(ring, (0, 0))
        banner = self.font_huge.render(f"LEVEL {self.level}", True, (255, 255, 255))
        banner.set_alpha(int(255 * (1 - abs(self.t * 2 - 1))))
        screen.blit(banner, (WIDTH // 2 - banner.get_width() // 2,
                             center[1] - banner.get_height() // 2))

    def reload_assets(self):
        """Re-decode every image after a display mode change.

        Surfaces converted for the previous format are discarded; on macOS
        keeping them results in black sprites.
        """
        normal, flame, hyper, _ = build_sprites()
        self.normal, self.flame, self.hyper = normal, flame, hyper
        self.mono_normal = [self.greyscale(s) for s in self.normal]
        self.mono_flame = [self.greyscale(s) for s in self.flame]
        self.flame_halo = [bake_halo(s, (255, 150, 46)) for s in self.flame]
        self.flame_glint = [bake_glints(s) for s in self.flame]
        self.hyper_glow = bake_halo(self.hyper, (210, 225, 255), 1.42)
        self.anims, _ = build_effects()
        self.chaos_art = load_chaos_assets()
        sheet = load_still(SMOKE_ASSET)
        self.smoke = split_clusters(sheet) if sheet is not None else []
        # A generated fallback is sized to the layer, so it has to be remade
        # when the render scale changes or it covers only part of the frame.
        loaded = load_backgrounds()
        if loaded:
            self.backgrounds = loaded
        elif not self.backgrounds or self.backgrounds[0].get_size() != (WIDTH, HEIGHT):
            self.backgrounds = [fallback_background()]
        self.title_bg = load_title_background()
        self.title_art = self.build_title()
        self.banner = self.build_banner()
        self.skin = load_ui_skin()
        self.board_bg = self.build_board_backdrop()
        self.plate = self.skinned("score", SCORE_PLATE.size) \
            if "SCORE_PLATE" in globals() else None
        self._blocks = {}
        self.frame = None

    def overlay_veil(self):
        """Alpha of the dimming behind whichever overlay is open, or 0.

        The credits roll dims lightly over its own artwork.

        Drawn across the whole display rather than the 4:3 layer, so the
        letterbox bars dim with everything else.
        """
        if self.data_wiped:
            return 244
        if self.credits_open:
            return 120
        if self.wipe_open:
            return 232
        if (self.menu_open or self.music_open or self.bg_picker_open
                or self.extras_open or self.resume_open
                or self.timed_duration_picker_open):
            return 226
        if self.over:
            return 214
        return 0

    def draw_wide(self, surface, scale, offset, under):
        """Effects that should span the WHOLE display, not the 4:3 layer.

        Drawn straight onto the display in its own coordinates: background
        motes underneath the UI, flying gems and the level banner on top, so
        in fullscreen they carry on past the letterbox bars.
        """
        dw, dh = surface.get_size()

        def place(x, y):
            return x * scale + offset[0], y * scale + offset[1]

        if under:
            if self.settings.get("particles", True):
                layer = pygame.Surface((dw, dh), pygame.SRCALPHA)
                span = max(dw, dh)
                for mx, my, size, _, alpha in self.motes:
                    # motes live in a 0..1 space so they cover any window
                    pygame.draw.circle(
                        layer, (170, 190, 255, int(alpha * 34)),
                        (int(mx / WIDTH * dw), int(my / HEIGHT * dh)),
                        max(1, int(size * scale)))
                surface.blit(layer, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            # The transition art that belongs behind the 4:3 UI layer.
            # The board-level banner still goes here, but flying gems should
            # appear over the board and side panel instead.
            if self.state == "banner" and not self.on_title:
                self.draw_banner_at(surface, place, scale)

            alpha = self.overlay_veil()
            if alpha:
                veil = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
                veil.fill((7, 8, 16, alpha))
                surface.blit(veil, (0, 0))
            return

        # debris still flies over the board, but not over an open menu
        if not self.overlay_veil():
            for piece in self.debris:
                piece.draw_at(surface, place, scale)

        if self.state == "flyoff":
            for flyer in self.flyers:
                flyer.draw_at(surface, place, scale)

    def draw_banner_at(self, surface, place, scale):
        image = self.banner
        if image is None:
            return
        dx, alpha = self.banner_pose()
        if alpha <= 0:
            return
        size = (max(1, int(image.get_width() * scale)),
                max(1, int(image.get_height() * scale)))
        art = pygame.transform.smoothscale(image, size)
        art.set_alpha(max(0, min(255, alpha)))
        cx, cy = place(BOARD_X + BOARD_W / 2 + dx, BOARD_Y + BOARD_H / 2)
        surface.blit(art, art.get_rect(center=(int(cx), int(cy))))

    def backdrop_pair(self):
        """(outgoing, incoming, 0..1) for the background crossfade.

        The photo changes with the level, so this keeps the previous one
        around and blends across. With smooth animation off it cuts straight
        to the new one.
        """
        photo = self.backdrop_photo()
        if photo is not self._bg_current:
            # Only slide between two LEVEL backdrops. Moving to or from the
            # title screen and the credits has its own artwork, and animating
            # that reads as a glitch rather than a transition.
            same_context = not self.on_title and not self._bg_was_title
            if (BACKDROPS_OK and self.bubbly
                    and self._bg_current is not None and same_context):
                self._bg_previous = self._bg_current
                self._bg_blend = 0.0
            else:
                self._bg_previous = None
                self._bg_blend = 1.0
            self._bg_current = photo
        self._bg_was_title = self.on_title
        if self._bg_previous is None:
            return None, photo, 1.0
        return self._bg_previous, photo, self._bg_blend

    def backdrop_photo(self):
        if not self.settings.get("backgrounds", True) and not self.on_title:
            return None
        """The background image for whatever is currently on screen.

        Handed to the Display so it can cover the full screen, rather than
        being baked into the 4:3 layer that gets letterboxed.
        """
        if self.on_title:
            if self.campaign_open and self.campaign_bg is not None:
                return self.campaign_bg      # preview the area being browsed
            if self.credits_open:
                return (self.credits_art.get("background")
                        or self.title_bg
                        or (self.backgrounds[0] if self.backgrounds else None))
            return self.title_bg or (self.backgrounds[0]
                                     if self.backgrounds else None)
        if self.mode == CAMPAIGN and self.campaign_bg is not None:
            return self.campaign_bg      # the area's own artwork
        return self.background_for_level()

    def draw(self, screen, background=True):
        if self.on_title:
            self.draw_title(screen, background=background)
            return
        offset = self.shake_offset()
        
        # Draw background directly to screen (no shake applied)
        # Only paint a backdrop when this surface owns it. On the letterboxed
        # path the Display has already drawn the background, and filling here
        # put an opaque block over it - which flashed in and out with shake.
        if background:
            photo = self.background_for_level()
            if photo is None:
                screen.fill(BG)
            else:
                screen.blit(photo, (0, 0))
        
        # Draw board and UI to a temporary surface with shake offset applied
        if offset == (0, 0):
            target = screen
        else:
            if self.frame is None:
                self.frame = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            self.frame.fill((0, 0, 0, 0))
            target = self.frame

        if self.state in ("flyoff", "banner"):
            self.draw_transition(target, background=False)  # No background, we drew it above
        else:
            self.draw_scene(target, background=False)  # No background, we drew it above

        if target is not screen:
            # Translate (don't scale) the board/UI by the shake offset
            screen.blit(target, offset)

    def flat_fade(self):
        """0..1 fade used instead of the fly-off when smooth is switched off."""
        if self.state == "flyoff":
            return clamp01(self.t / max(0.01, FLYOFF_TIME))
        return 1.0

    def draw_transition(self, screen, background=True):
        """Gems flying off, then the LEVEL banner over an empty board."""
        self.draw_scene(screen, background=background)

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
        """No-op: the motes are painted across the whole display by
        draw_wide(), so they are not confined to the 4:3 area."""
        return

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
                             (BOARD_X + c * TILE, BOARD_Y + r * TILE, TILE, TILE), S(3),
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
        for pop in self.score_pops:
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

        # Draw the level banner in front of the board UI if needed.
        if self.state == "banner":
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

        # Spotlight: black out everything but a circle at the cursor, then
        # put the score panel back on top so the readouts and buttons stay
        # readable. It goes here, after the board but before the veil and any
        # overlay, so menus and dialogs are never dimmed by it.
        if self.extra("spotlight"):
            self.draw_spotlight(screen)
            self.draw_panel(screen)

        # Dim the board and side panel before any overlay. The display-space
        # veil sits UNDER this layer, so without this the board stayed at full
        # brightness behind a menu.
        alpha = self.overlay_veil()
        if alpha:
            k = max(0, 255 - alpha)
            screen.fill((k, k, k, 255), special_flags=pygame.BLEND_RGBA_MULT)

        # Draw menus last so they appear on top
        if self.menu_open:
            self.draw_menu(screen)
        if self.wipe_open:
            self.draw_wipe(screen)
        if self.music_open:
            self.draw_music(screen)
        if self.bg_picker_open:
            self.draw_background_picker(screen)
        if self.over:
            self.draw_over(screen)


# --------------------------------------------------------------------------

class Display:
    """Presents the fixed 960x720 game on any window or screen.

    The UI is never stretched: it is scaled by a single factor and centred.
    The background photo is scaled separately to COVER the whole display, so
    a wide screen shows more background rather than distorted gems.
    """

    def __init__(self, fullscreen=False):
        self.fullscreen = False
        self.surface = None
        self.layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self._cover_cache = {}
        self._scaled = None
        self._pre = None
        self.scaler = "smooth_dest"
        self.pick_scaler()
        self.scale = 1.0
        self.offset = (0, 0)
        self.set_fullscreen(fullscreen)

    def set_fullscreen(self, on, game=None):
        """Switch mode, then rebuild anything that was converted for the old
        display format.

        macOS invalidates surfaces produced by convert()/convert_alpha() when
        the display mode changes - they render black. Windows tolerates it,
        which is why this only showed up on one platform.
        """
        self.fullscreen = on
        if on:
            self.surface = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.surface = pygame.display.set_mode((WIDTH, HEIGHT))
        self.recompute()
        self.layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self._scaled = None
        self._pre = None
        if game is not None:
            game.reload_assets()
        return self.surface

    def toggle_with(self, game):
        return self.set_fullscreen(not self.fullscreen, game)

    def toggle(self):
        return self.set_fullscreen(not self.fullscreen)

    def pick_scaler(self):
        """Work out which scaling call preserves alpha on THIS machine.

        smoothscale silently drops the alpha channel on some SDL builds,
        which paints the whole 4:3 area solid black over the background.
        Rather than assume, scale a known-transparent test surface and check
        the result, falling back to plain scale() - which is nearest
        neighbour, but always keeps alpha - if smoothscale fails the test.
        """
        probe = pygame.Surface((32, 32), pygame.SRCALPHA)
        probe.fill((0, 0, 0, 0))
        pygame.draw.rect(probe, (255, 0, 0, 255), (8, 8, 16, 16))
        size = (64, 64)

        def clear_corner(surface):
            try:
                return surface.get_at((1, 1))[3] == 0
            except IndexError:
                return False

        # 1. smoothscale into a surface we allocated with SRCALPHA
        try:
            dest = pygame.Surface(size, pygame.SRCALPHA)
            dest.fill((0, 0, 0, 0))
            pygame.transform.smoothscale(probe, size, dest)
            if clear_corner(dest):
                self.scaler = "smooth_dest"
                return
        except (TypeError, ValueError, pygame.error):
            pass

        # 2. plain smoothscale
        try:
            if clear_corner(pygame.transform.smoothscale(probe, size)):
                self.scaler = "smooth"
                return
        except pygame.error:
            pass

        # 3. nearest neighbour. Slightly harder edges when the window is not
        #    an exact multiple, but the alpha always survives.
        self.scaler = "nearest"
        print("  note: smoothscale drops alpha on this build - using "
              "nearest-neighbour scaling instead.")

    def scale_layer(self, size):
        if self._scaled is None or self._scaled.get_size() != size:
            self._scaled = pygame.Surface(size, pygame.SRCALPHA)
        self._scaled.fill((0, 0, 0, 0))

        lw, lh = self.layer.get_size()
        fx, fy = size[0] / lw, size[1] / lh
        # Exact integer ratio: nearest neighbour is not merely adequate here,
        # it is correct - every source pixel becomes a clean square block, and
        # smoothing would only soften edges that need no softening.
        if abs(fx - round(fx)) < 0.002 and abs(fy - round(fy)) < 0.002:
            self._scaled.blit(pygame.transform.scale(self.layer, size), (0, 0))
            return self._scaled

        if self.scaler == "smooth_dest":
            pygame.transform.smoothscale(self.layer, size, self._scaled)
        elif self.scaler == "smooth":
            self._scaled.blit(pygame.transform.smoothscale(self.layer, size),
                              (0, 0))
        else:
            self._scaled.blit(pygame.transform.scale(self.layer, size), (0, 0))
        return self._scaled

    def recompute(self):
        dw, dh = self.surface.get_size()
        # The layer is fitted to the screen, so a higher render scale means
        # a bigger layer meeting a smaller fit factor - same picture size,
        # more pixels behind it.
        self.scale = min(dw / WIDTH, dh / HEIGHT)
        self.offset = (int((dw - WIDTH * self.scale) / 2),
                       int((dh - HEIGHT * self.scale) / 2))

    def resize_layer(self):
        """Rebuild the render target after a render-scale change."""
        self.layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.recompute()
        self._scaled = None
        self._pre = None
        self._cover_cache.clear()

    def to_game(self, pos):
        """Turn a real mouse position into virtual 960x720 coordinates."""
        if self.scale <= 0:
            return pos
        return (int((pos[0] - self.offset[0]) / self.scale),
                int((pos[1] - self.offset[1]) / self.scale))

    def cover(self, photo, alpha=255, rise=0.0):
        """Scale a background to fill the whole display, cropping the excess.

        The scaled copy is cached per (photo, size): rescaling a full-size
        photo every frame was wasteful, and doubly so now two of them are
        blended during a crossfade.
        """
        if alpha <= 0:
            return
        dw, dh = self.surface.get_size()
        key = (id(photo), dw, dh)
        art = self._cover_cache.get(key)
        if art is None:
            pw, ph = photo.get_size()
            f = max(dw / pw, dh / ph)
            art = pygame.transform.smoothscale(
                photo, (int(pw * f + 0.5), int(ph * f + 0.5)))
            if len(self._cover_cache) > 6:
                self._cover_cache.clear()
            self._cover_cache[key] = art
        pos = ((dw - art.get_width()) // 2,
               (dh - art.get_height()) // 2 + int(dh * rise))
        if alpha >= 255:
            self.surface.blit(art, pos)
        else:
            faded = art.copy()
            faded.set_alpha(alpha)
            self.surface.blit(faded, pos)

    def present(self, game):
        self.surface.fill(BG)
        outgoing, photo, blend = game.backdrop_pair()
        # Always lay the current backdrop down flat first. The sliding copies
        # are drawn at an offset, which leaves bare screen behind them - and
        # bare screen is BG, which reads as black.
        if photo is not None:
            self.cover(photo)
        if outgoing is not None and blend < 1.0:
            self.cover(outgoing, rise=-ease_in_out(blend) * 0.35)
            self.cover(photo, int(60 + 195 * blend),
                       rise=(1.0 - ease_in_out(blend)) * 0.9)

        game.draw_wide(self.surface, self.scale, self.offset, under=True)

        self.layer.fill((0, 0, 0, 0))
        game.draw(self.layer, background=False)

        if abs(self.scale - 1.0) < 0.001 and self.offset == (0, 0):
            self.surface.blit(self.layer, (0, 0))
        else:
            size = (max(1, int(WIDTH * self.scale)),
                    max(1, int(HEIGHT * self.scale)))
            self.surface.blit(self.scale_layer(size), self.offset)

        game.draw_wide(self.surface, self.scale, self.offset, under=False)
        pygame.display.flip()




def main():
    # This line has to come BEFORE pygame.init(). The default mixer buffer is
    # 4096 samples, which puts a very audible delay between clicking a gem and
    # hearing it pop. 512 makes the feedback feel instant.
    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
    pygame.init()
    pygame.display.set_caption("Prismac")
    display = Display(fullscreen=False)
    screen = display.surface
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

    if not pygame.image.get_extended():
        print("WARNING: SDL_image has no extended format support - only BMP "
              "will load. Backgrounds and gem art will be missing.\n")
    print("Backgrounds:")
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
    game.display = display
    game.load_settings()
    game.load_campaign()
    if game.settings.get("fullscreen") and not display.fullscreen:
        display.set_fullscreen(True, game)
    game.settings["fullscreen"] = display.fullscreen
    # The saved render scale can only be applied once we know we are actually
    # fullscreen, since windowed mode always renders 1:1.
    saved = game.settings.get("render_scale", DEFAULT_RENDER_SCALE)
    if display.fullscreen and abs(saved - RENDER_SCALE) > 0.01:
        game.apply_scale(saved)

    while True:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif e.type == pygame.KEYDOWN and not game.data_wiped:
                if e.key == pygame.K_ESCAPE:
                    if game.music_open:
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
                elif e.key == pygame.K_F11:
                    display.toggle_with(game)
                elif e.key == pygame.K_n:
                    game.open_music()
                elif e.key == pygame.K_t:
                    game.set_mode(TIMED if game.mode == ENDLESS else ENDLESS)
            elif e.type == MUSIC_END:
                audio.next_track()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                game.on_down(display.to_game(e.pos))
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                game.on_up(display.to_game(e.pos))
            elif e.type == pygame.MOUSEMOTION:
                game.on_motion(display.to_game(e.pos))
            elif e.type == pygame.MOUSEWHEEL:
                if game.music_open:
                    game.music_list.scroll(-e.y)
                elif game.bg_picker_open:
                    game.bg_list.scroll(-e.y)

        if game.wants_quit:
            pygame.quit()
            sys.exit()

        if game.wipe_open:
            held = (pygame.mouse.get_pressed()[0]
                    and game.wipe_buttons[0].rect.collidepoint(
                        display.to_game(pygame.mouse.get_pos())))
            game.update_wipe(dt, held)

        if game.resume_open:
            held = (pygame.mouse.get_pressed()[0]
                    and game.resume_buttons[1].rect.collidepoint(
                        display.to_game(pygame.mouse.get_pos())))
            game.update_resume(dt, held)
        game.update(dt)
        display.present(game)


if __name__ == "__main__":
    main()
