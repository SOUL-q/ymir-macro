"""
ymir v1 by soul.py - AOTR mission macro with a status window (external keyboard/mouse input only).

Routine per mission:
  1. Ability 2 (only that), then wait 1.5s before anything else
  2. Dash 14 times (one dash = Space pressed twice, with a gap between dashes)
  3. Strafe (A, double-tap)
  4. Ability 3
  5. Buy time by strafing A (starts right after ability 3) for 15 seconds, the cooldown
     ability 4 has after ability 3
  6. Ability 4
  7. Spam ability 5 for 5 seconds -> this shifts you into the titan (abilities change),
     then wait. (It keeps spamming 4 more seconds in the background, inside that wait,
     so the shift is used for sure: SHIFT_SPAM_EXTRA)
  8. 17 seconds into that wait: spam the shifted ability 4 for 6 seconds, then wait 3 seconds
  9. Press ability 5 over and over until the RETRY button shows up

Flow:
  - The mission counts as started when the ability-2 icon (mission_start.png) shows up.
  - When the word RETRY (retry_text.png) shows up, it clicks it, then does NOTHING
    until the next mission starts, and repeats.

Result + loot tracking:
  When the RETRY button shows up, the end screen is also scanned for the words
  COMPLETED / FAILED (result_completed.png, result_failed.png) and counted.
  The loot icons are scanned at the same moment
  (loot_scroll.png, loot_body.png, loot_defence.png, loot_offence.png,
  loot_support.png - keep them in the "image" folder next to this script).
  Normal quality retry button found: the loot is scanned BEFORE retry is clicked, with the normal
  pictures.  Low quality retry button found (image/low quality fix/): only the COMPLETED / FAILED
  result is read before the click; the loot is scanned ONLY during the 3s (LOW_LOOT_SCAN_TIME) after
  retry was clicked, with the pictures
  from "low quality fix" only (the normal pictures are never used then).
  Every kind that is on screen counts as 1 for that mission, whatever the number
  in its corner says.  1 scroll + 2 different fragments = "1 scroll, 2 fragments".

Movement (Settings > Configs > Movements): only changes the initial dash sequence, before
  ability 4 is used. "Shiki" = 14 dashes + strafe A, "Universal" = spam dash for 7.6s + strafe A,
  "Wings of Freedom" = spam dash for 8s, then strafe A for 4s.

Family / abilities (Settings > Configs > Abilities): "Blood Awakening" skips ability 3, the
  buying time and ability 4: right after the movement it goes to the ability 5 shift, the wait,
  shifted ability 4 and shifted ability 5.  "Universal" (WIP, not the default) then after ability 3 spams ability 4
  for 5s, strafes A once, D for 2s, A for 4s, then goes on with the ability 5 shift. "Shiki" keeps
  the routine described above (14 dashes, 15s of buying time, ability 4 once).

Updates (footer > Updates):
  Looks at the latest GitHub release of UPDATE_REPO (also once at start). If its tag is newer than
  VERSION it asks to install it: the .exe attached to the release is downloaded, checked, and
  swapped in for the running .exe, then the macro restarts. Running the plain .py only opens the
  release page. Only works while the macro is stopped.

Stuck-mission rescue:
  If a mission runs longer than MISSION_TIMEOUT (2 minutes), something obscure went wrong after the
  shift. The macro then presses ctrl, moves the mouse down for 2s and presses ctrl again (the
  character looks at the ground), and clicks the middle of the screen every RESCUE_CLICK_DELAY
  (0.5s) until the retry button shows up, and goes on as usual (result / loot scan, retry click, next mission).

Low quality mode (Settings > Configs > Graphics):
  When on, ONLY the pictures from "image/low quality fix" are used to find the retry button, the
  loot and the mission start (the normal pictures are not even loaded). Body fragments are not
  searched for at all in this mode (their low quality picture gives false hits - no fix for now).
  Stop the macro to change it.
  When off, both looks are searched (auto-detect), as before.

Grabbed detection:
  When the red text YOUR STREAK IS IN DANGER (grabbed_text.png - keep it next to this
  script) shows up, the macro presses the "escape grab" key (default 1, changeable in
  Settings) - again every GRAB_REPEAT seconds while the text is still on screen.

Install:
    pip install mss opencv-python numpy pydirectinput keyboard
    (tkinter comes with Python on Windows)
    Keep all images in a folder called "image" next to this script. The low graphics looks
    (retry button, ability 2 icon, loot - same file names) go in image/low quality fix/.
    ymir_logo_app.png (header logo; text fallback if missing).
    ymir.ico (window icon; default icon if missing).

Run (as administrator, Roblox in windowed/borderless mode):
    python main.py

Hotkeys (work even while Roblox is focused):
    F8 = start / manual start     F6 = pause / resume     F7 = stop
    (these are the defaults - every key can be changed in Settings, bottom of the window)

Settings (footer -> Settings):
    Keybinds : hotkeys + in-game keys
    Discord  : optional webhook, stats embed after every mission, stats graph every N hours
              (+ test buttons), mention on errors (needs your user ID)
    Configs  : Shiki / Universal (WIP) / Blood Awakening (WIP) (default Shiki)
    Everything is saved in aotr_stats.json inside the Documents folder, in "Ymir Macro".
Slamming the mouse into a screen corner also aborts (pydirectinput failsafe).
"""

import base64
import ctypes
import json
import os
import hashlib
import queue
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import uuid
import webbrowser
from tkinter import messagebox, ttk

import cv2
import keyboard
import mss
import numpy as np
import pydirectinput

# ----------------------------- SETTINGS ---------------------------------
VERSION = "v1.1.3"        # release version tag
                          # (shown in the footer, next to "Always on top")

# --- Update checker (footer > Updates) ---
UPDATE_REPO = "SOUL-q/ymir-macro"   # <-- your GitHub "owner/repo" (public). Releases are read from it
UPDATE_CHECK_ON_START = True       # look for a newer release a moment after the window opens
UPDATE_TIMEOUT = 15                # seconds before a GitHub request is given up

# --- Window logo (keep next to this script; falls back to the text "ymir" if missing) ---
LOGO_FILE = "ymir_logo_app.png"
ICON_FILE = "ymir.ico"   # window / taskbar icon (the lambda); skipped if missing

# --- Retry button detection ---
TEMPLATE_FILE = "retry_text.png"     # just the word RETRY (keep next to this script)
THRESHOLD = 0.90          # strict on purpose, so the Leave button can't match
SCAN_INTERVAL = 0.5       # seconds between screen checks for the retry button
MONITOR_INDEX = 1         # 1 = primary monitor, 2 = second monitor, ...
SCALES = [1.0]            # e.g. [0.8, 0.9, 1.0, 1.1, 1.2] if resolution differs
AFTER_CLICK_DELAY = 7     # seconds of doing NOTHING right after clicking retry
RETRY_CONFIRM_DELAY = 0.4 # re-check this long after first sighting (buttons fade in)
SAVE_CLICK_DEBUG = False   # saves last_retry_click.png showing exactly where it clicked

# --- Mission result detection (the gold COMPLETED / FAILED text on the end screen) ---
RESULT_FILES = {"completed": "result_completed.png", "failed": "result_failed.png"}
RESULT_THRESHOLD = 0.70   # lower it if results aren't detected

# --- Loot detection (looked for on the end screen, right before clicking retry) ---
LOOT_ENABLED = True
LOOT_FILES = {                       # kind -> template file (the icon only, no number)
    "scroll": "loot_scroll.png",
    "body": "loot_body.png",         # yellow fragment
    "defence": "loot_defence.png",   # blue fragment
    "offence": "loot_offence.png",   # red fragment
    "support": "loot_support.png",   # green fragment
}
FRAGMENT_KINDS = ("body", "defence", "offence", "support")
LOOT_THRESHOLD = 0.75     # lower it if loot is missed, raise it if you get false hits
LOOT_SCAN_TIME = 1.0      # seconds spent looking (items can fade in) before clicking retry
LOOT_SCAN_STEP = 0.25     # seconds between looks during that time
LOW_LOOT_SCAN_TIME = 3.0  # low quality only: the loot is looked for ONLY during this many seconds
                          # right after the retry click (nothing is looked for before the click)
SAVE_LOOT_DEBUG = False    # saves last_end_scan.png with boxes around the result + loot found

# --- Grabbed detection (the red YOUR STREAK IS IN DANGER text) ---
GRAB_ENABLED = True
GRAB_FILE = "grabbed_text.png"   # screenshot of just that text (keep next to this script)
GRAB_THRESHOLD = 0.70            # lower it if the grab isn't noticed, raise it for false hits
GRAB_REPEAT = 1.0                # while the text stays, press the key again after this many seconds

# --- Mission start detection (ability 2 icon) ---
START_TEMPLATE_FILE = "mission_start.png"
START_THRESHOLD = 0.80    # lower it if the icon isn't being detected
START_SETTLE_DELAY = 1.0  # extra wait after the icon appears, before ability 2
ICON_GONE_TIMEOUT = 20    # after retry, max seconds to wait for the old HUD to vanish

# --- Ability 4 cooldown (it can't be used until this long after ability 3) ---
ABILITY4_COOLDOWN = 15.0           # seconds of buying time after ability 3
ABILITY4_COOLDOWN_MARGIN = 0.3     # tiny extra, so ability 4 is surely off cooldown

# --- Stuck-mission rescue (a very rare obscure bug after the shift can leave the macro stuck) ---
MISSION_TIMEOUT = 120.0     # a mission longer than this many seconds counts as stuck
RESCUE_CLICK_DELAY = 0.5    # seconds between the clicks on the middle of the screen
# Before clicking, the character is forced to look at the ground: press ctrl, move the mouse down
# for LOOK_DOWN_TIME seconds, press ctrl again.
LOOK_DOWN_KEY = "ctrl"
LOOK_DOWN_TIME = 2.0        # seconds the mouse is moved down
LOOK_DOWN_STEP = 0.01       # seconds between two small downward mouse movements
LOOK_DOWN_PIXELS = 15       # pixels moved down per step (relative movement, works in a locked mouse)

# --- Saved stats (kept between runs; the Reset button in the window erases them) ---
STATS_FILE = "aotr_stats.json"   # saved in Documents\Ymir Macro
STATS_FOLDER = "Ymir Macro"      # folder created inside your Documents folder
IMAGE_FOLDER = "image"           # all images (templates, logo, icon) are loaded from this folder,
                                 # next to this script / .exe
LOW_FOLDER = "low quality fix"   # inside the image folder: the low graphics looks of the retry button,
                                 # the ability 2 icon and the loot (same file names as the normal ones)

# --- Mission routine timings ---
AFTER_ABILITY_DELAY = 0.6        # pause after ability 3 / 4
AFTER_ABILITY2_DELAY = 1.5       # pause after ability 2, before the dash sequence starts
DASH_COUNT = 14                  # number of dashes (each dash = Space pressed twice)
DASH_GAP = (0.45, 0.55)          # seconds between one dash and the next (~0.5)
DOUBLE_TAP_GAP = (0.06, 0.12)    # seconds between the two presses of ONE dash/strafe
STRAFE_DELAY = (0.15, 0.25)      # seconds between A strafes while buying time (~0.2)
SHIFT_SPAM_TIME = 5.0            # after ability 4: spam ability 5 for this long, so the shift is used for sure
SHIFT_SPAM_INTERVAL = 0.2        # seconds between those ability 5 presses
SHIFT_SPAM_EXTRA = 4.0           # keeps spamming ability 5 this much longer, but INSIDE the wait below:
                                 # the macro already counts the shift as used after SHIFT_SPAM_TIME and
                                 # starts the wait below, while still pressing 5 in the background
                                 # (5s + 4s = 9s of real spamming)
SHIFTED4_SPAM_AT = 17.0          # the shift takes ~22s; this many seconds after the 5 spam, start spamming
                                 # the shifted ability 4 (it runs past the 22s mark, that's intended)
SHIFTED4_SPAM_TIME = 6.0         # spam the shifted ability 4 for this long
SHIFTED4_SPAM_INTERVAL = 0.2     # seconds between those ability 4 presses
SHIFTED_4_TO_5_DELAY = 3.0       # after the shifted ability 4 spam, wait this long, then ability 5
ABILITY_5_CHECK_INTERVAL = 1.0   # how often to press 5 (set to its cooldown
                                 # if pressing early causes problems)

# --- Default keys (change them in the Settings window; your choice is saved in STATS_FILE) ---
KEY_ABILITY_1ST = "2"
KEY_ABILITY_2ND = "3"
KEY_ABILITY_3RD = "4"
KEY_ABILITY_LAST = "5"
KEY_DASH = "space"
KEY_STRAFE = "a"
KEY_STRAFE_D = "d"    # the other strafe direction (Universal family)
KEY_GRAB = "1"       # pressed when you get grabbed
KEY_BACK = "s"
# moves rotated (each one double-tapped) while waiting for ability 4: just A, spammed
BUY_TIME_MOVES = [KEY_STRAFE]

# --- Default hotkeys (also changeable in the Settings window) ---
START_KEY = "f8"
PAUSE_KEY = "f6"
QUIT_KEY = "f7"   # stops the macro (the window stays open)

# --- Family "Universal" routine (Shiki keeps the original routine above) ---
# Universal movement dashing, copied from a recorded macro: Space spammed non-stop
UNIVERSAL_DASH_TIME = 8.2         # seconds of spamming
UNIVERSAL_DASH_HOLD = (0.065, 0.09)  # how long each Space press is held
UNIVERSAL_DASH_PRESS_GAP = (0.05, 0.08)  # pause between two presses
UNIVERSAL_ABILITY4_SPAM = 5.0      # after ability 3: spam ability 4 for this long
UNIVERSAL_ABILITY4_INTERVAL = 0.2  # seconds between those ability 4 presses
# then: strafe A once, strafe D for UNIVERSAL_STRAFE_D_TIME, strafe A for UNIVERSAL_STRAFE_A_TIME,
# and only then the ability 5 shift
UNIVERSAL_STRAFE_D_TIME = 2.0
UNIVERSAL_STRAFE_A_TIME = 4.0

# --- Movement (Settings > Configs > Movements): only changes the initial dash sequence,
# before ability 4 has been used.  Shiki = DASH_COUNT dashes, Universal = spam dash for UNIVERSAL_DASH_TIME
# dashes (both followed by one strafe A), Wings of Freedom = spam dash, then strafe A.
WINGS_DASH_TIME = 8.0            # seconds of spamming dash
WINGS_DASH_GAP = (0.15, 0.25)    # seconds between the dashes while spamming
WINGS_STRAFE_TIME = 4.0          # seconds of strafing A afterwards

# --- Settings window ---
MOVEMENTS = ("Shiki", "Universal", "Wings of Freedom")
DEFAULT_MOVEMENT = "Shiki"
MOVEMENT_WIP = ("Universal",)    # these get a WIP tag in the dropdown
MOVEMENT_BADGES = {
    "Shiki":            ("S", "#3b82f6", "#ffffff"),   # blue S
    "Universal":        ("U", "#facc15", "#1a1500"),   # yellow U
    "Wings of Freedom": ("W", "#14b8a6", "#ffffff"),   # teal W
}
FAMILIES = ("Shiki", "Universal", "Blood Awakening")
DEFAULT_FAMILY = "Shiki"
FAMILY_LABELS = {f: f for f in FAMILIES}   # what the dropdown shows
FAMILY_WIP = ("Universal", "Blood Awakening")   # these get a WIP tag in the dropdown
# icon next to each entry: (letter, badge colour, letter colour)
FAMILY_BADGES = {
    "Shiki":           ("S", "#3b82f6", "#ffffff"),   # blue S
    "Universal":       ("U", "#facc15", "#1a1500"),   # yellow U
    "Blood Awakening": ("B", "#ef4444", "#ffffff"),   # red B
}


# --- Themes (Settings > Themes). Every theme = 5 base colours (the rest is blended from
# them) + optional hand-picked overrides + style (font, corner radius, card outline).
DEFAULT_THEME = "Default"
_BASE_STYLE = dict(FONT="Segoe UI", MONO="Consolas",
                   R_TILE=10,      # corner radius of the buttons / tiles
                   R_PILL=None,    # corner radius of the status pill (None = fully round)
                   R_SEG=3,        # corner radius of the step bar
                   R_SWITCH=10,    # roundness of the on/off switches (10 = fully round)
                   CARD_BW=1)      # card outline: 1 = thin line, 0 = borderless
THEMES = {
    "Default": dict(
        colors=("#0b0e14", "#11151e", "#e6e9f2", "#7a8398", "#3b82f6"),   # bg, card, text, sub, accent
        over={
            "BORDER": "#1a2030", "LOGBG": "#0f121a", "FIELD": "#1a1e29", "FIELD_EDGE": "#2a3042",
            "FIELD_HOVER": "#212637", "FIELD_EDGE_HOVER": "#3a4156", "ACCENT_BG": "#16254a",
            "ACCENT_BG_HOVER": "#1d3266", "ACCENT_LINE": "#3b6fe0", "ACCENT_BADGE": "#3b5cb0",
            "ACCENT_TEXT": "#9db8ff", "ACCENT_SOFT": "#7aa7ff", "STEP_DONE": "#2f55b8",
            "STEP_PENDING": "#232a3b", "SCROLL": "#262c3d", "SCROLL_HOVER": "#323a52",
            "DIS_FILL": "#13161e", "DIS_EDGE": "#1b202c", "DIS_TEXT": "#4b5264",
            "DIS_BADGE": "#232837", "DIS_ICON": "#3c4254", "BADGE_HOVER": "#4a5270",
            "BADGE_FG": "#9aa3b8", "BADGE_FG_HOVER": "#b4bcd0", "LOG_TS": "#586073",
            "SWITCH_OFF": "#272e40",
            "PILLS": {"idle": ("Idle", "#1d2230", "#9aa3b8"),
                      "waiting": ("Waiting", "#2e2410", "#fbbf24"),
                      "running": ("Running", "#0f2a22", "#34d399"),
                      "retrying": ("Retrying", "#14243f", "#60a5fa"),
                      "paused": ("Paused", "#251d3f", "#a78bfa")},
        },
        style={}),
    "Violet": dict(
        colors=("#0e0b17", "#161225", "#ece8f8", "#8a82a8", "#8b5cf6"),
        over={}, style=dict(R_TILE=12)),
    "Rose": dict(
        colors=("#140c10", "#1f1319", "#f7e9ee", "#a88994", "#f472b6"),
        over={}, style=dict(R_TILE=16, CARD_BW=0)),
    "Ember": dict(
        colors=("#12100d", "#1b1814", "#f1ebe2", "#9a8f80", "#f97316"),
        over={}, style=dict(FONT="Bahnschrift", R_TILE=6, R_SEG=1, R_SWITCH=6)),
    "Terminal": dict(
        colors=("#050806", "#0a110c", "#c7f9d4", "#5f8f6f", "#22c55e"),
        over={"BORDER": lambda P: _mix(P["CARD"], P["ACCENT"], 0.35),
              "FIELD_EDGE": lambda P: _mix(P["CARD"], P["ACCENT"], 0.3)},
        style=dict(FONT="Consolas", R_TILE=2, R_PILL=2, R_SEG=0, R_SWITCH=2)),
    "Ocean": dict(
        colors=("#08111a", "#0d1a27", "#e3f1f7", "#7e97a8", "#06b6d4"),
        over={}, style=dict(R_TILE=8, CARD_BW=0)),
}


def _mix(a, b, t):
    """Blend colour a towards colour b by t (0..1). Colours are '#rrggbb'."""
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


_font_names = None


def _font_or(family, fallback="Segoe UI"):
    """The font if this PC has it, otherwise the fallback (so a theme never looks broken)."""
    global _font_names
    if _font_names is None:
        try:
            from tkinter import font as tkfont
            _font_names = {f.lower() for f in tkfont.families()}
        except Exception:
            _font_names = set()
    return family if (not _font_names or family.lower() in _font_names) else fallback


def build_palette(name):
    """All colours + style values of one theme, as a dict (keys become App.<KEY>)."""
    spec = THEMES.get(name) or THEMES[DEFAULT_THEME]
    bg, card, text, sub, accent = spec["colors"]
    m = _mix
    field = m(card, text, 0.05)
    acc_bg = m(card, accent, 0.22)
    soft = m(accent, "#ffffff", 0.3)
    P = {
        "BG": bg, "CARD": card, "TEXT": text, "SUB": sub, "ACCENT": accent,
        "BORDER": m(card, text, 0.07), "LOGBG": m(bg, card, 0.65),
        "FIELD": field, "FIELD_EDGE": m(card, text, 0.12), "FIELD_HOVER": m(card, text, 0.09),
        "FIELD_EDGE_HOVER": m(card, text, 0.18),
        "ACCENT_BG": acc_bg, "ACCENT_BG_HOVER": m(card, accent, 0.32),
        "ACCENT_LINE": m(accent, "#000000", 0.1), "ACCENT_BADGE": m(card, accent, 0.65),
        "ACCENT_TEXT": m(accent, "#ffffff", 0.45), "ACCENT_SOFT": soft,
        "STEP_DONE": m(card, accent, 0.75), "STEP_PENDING": m(card, text, 0.09),
        "SCROLL": m(card, text, 0.12), "SCROLL_HOVER": m(card, text, 0.2),
        "DIS_FILL": m(card, bg, 0.3), "DIS_EDGE": m(card, text, 0.08),
        "DIS_TEXT": m(card, text, 0.28), "DIS_BADGE": m(card, text, 0.1),
        "DIS_ICON": m(card, text, 0.22), "BADGE_HOVER": m(card, text, 0.25),
        "BADGE_FG": m(card, text, 0.63), "BADGE_FG_HOVER": m(card, text, 0.76),
        "LOG_TS": m(card, text, 0.35), "SWITCH_OFF": m(card, text, 0.12), "KNOB": "#ffffff",
        "PILLS": {"idle": ("Idle", field, m(card, text, 0.63)),
                  "waiting": ("Waiting", m(card, "#fbbf24", 0.16), "#fbbf24"),
                  "running": ("Running", m(card, "#34d399", 0.16), "#34d399"),
                  "retrying": ("Retrying", acc_bg, soft),
                  "paused": ("Paused", m(card, "#a78bfa", 0.16), "#a78bfa")},
    }
    for key, value in spec["over"].items():
        P[key] = value(P) if callable(value) else value
    P.update(_BASE_STYLE)
    P.update(spec["style"])
    P["FONT"] = _font_or(P["FONT"])
    P["MONO"] = _font_or(P["MONO"], "Courier New")
    return P

MAX_GRAPH_HOURS = 24             # the stats graph interval can be 1 .. this many hours
WEBHOOK_TIMEOUT = 15             # seconds before a Discord request is given up
# -------------------------------------------------------------------------

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

pydirectinput.PAUSE = 0.0
pydirectinput.FAILSAFE = True


def app_dir():
    """Folder of the .exe (when compiled) or of this script. Templates, stats and
    debug screenshots live here, so they survive between runs."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def asset_path(filename):
    """Images are loaded from the "image" folder. One next to the .exe / script wins
    (so you can swap an image without recompiling); otherwise the copy bundled
    inside the .exe is used."""
    local = os.path.join(app_dir(), IMAGE_FOLDER, filename)
    if os.path.exists(local):
        return local
    return os.path.join(getattr(sys, "_MEIPASS", app_dir()), IMAGE_FOLDER, filename)


def documents_dir():
    """The user's real Documents folder (follows OneDrive redirection on Windows)."""
    if sys.platform == "win32":
        try:
            buf = ctypes.create_unicode_buffer(260)
            # CSIDL_PERSONAL = 5 (My Documents), SHGFP_TYPE_CURRENT = 0
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return buf.value
        except Exception:  # noqa: BLE001
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def data_dir():
    """Documents\\Ymir Macro - created if it doesn't exist yet. The json lives here."""
    path = os.path.join(documents_dir(), STATS_FOLDER)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return app_dir()   # can't create it: fall back to next to the script
    return path

STEP_NAMES = ["Ability 2", "Dashing", "Strafe", "Ability 3",
              "Buying time", "Ability 4", "Shift", "Shifted 4", "Ability 5"]

# ------------------------------ settings --------------------------------
# bind id -> (label shown in the Settings window, default key)
HOTKEY_BINDS = {
    "start": ("Start / manual start", START_KEY),
    "pause": ("Pause / resume", PAUSE_KEY),
    "stop": ("Stop", QUIT_KEY),
}
GAME_BINDS = {
    "ability2": ("Ability 2", KEY_ABILITY_1ST),
    "ability3": ("Ability 3", KEY_ABILITY_2ND),
    "ability4": ("Ability 4", KEY_ABILITY_3RD),
    "ability5": ("Ability 5", KEY_ABILITY_LAST),
    "dash": ("Dash", KEY_DASH),
    "strafe": ("Strafe A", KEY_STRAFE),
    "strafe_d": ("Strafe D", KEY_STRAFE_D),
    "grab": ("Escape grab", KEY_GRAB),
}
BIND_LABELS = {k: v[0] for k, v in {**HOTKEY_BINDS, **GAME_BINDS}.items()}
DEFAULT_KEYBINDS = {k: v[1] for k, v in {**HOTKEY_BINDS, **GAME_BINDS}.items()}
DEFAULT_WEBHOOK = {
    "url": "",              # empty = Discord is off
    "mention": False,       # ping the user in error messages
    "user_id": "",          # the Discord user ID that gets pinged
    "hourly_graph": False,  # send a stats graph every graph_hours hours
    "graph_hours": 1,       # that interval, in hours
    "notify_mission": True, # post a stats embed after every finished mission
    "notify_error": True,   # message when the macro hits an error
}

# the live settings (saved in STATS_FILE under "settings")
settings = {
    "keybinds": dict(DEFAULT_KEYBINDS),
    "webhook": dict(DEFAULT_WEBHOOK),
    "family": DEFAULT_FAMILY,
    "movement": DEFAULT_MOVEMENT,
    "theme": DEFAULT_THEME,
    "low_quality": False,   # True = only the "low quality fix" pictures are used
}


def apply_settings():
    """Copy the saved keybinds into the key variables the macro uses."""
    global START_KEY, PAUSE_KEY, QUIT_KEY
    global KEY_ABILITY_1ST, KEY_ABILITY_2ND, KEY_ABILITY_3RD, KEY_ABILITY_LAST
    global KEY_DASH, KEY_STRAFE, KEY_STRAFE_D, KEY_GRAB, BUY_TIME_MOVES
    kb = settings["keybinds"]
    START_KEY, PAUSE_KEY, QUIT_KEY = kb["start"], kb["pause"], kb["stop"]
    KEY_ABILITY_1ST, KEY_ABILITY_2ND = kb["ability2"], kb["ability3"]
    KEY_ABILITY_3RD, KEY_ABILITY_LAST = kb["ability4"], kb["ability5"]
    KEY_DASH, KEY_STRAFE, KEY_GRAB = kb["dash"], kb["strafe"], kb["grab"]
    KEY_STRAFE_D = kb["strafe_d"]
    BUY_TIME_MOVES = [KEY_STRAFE]


def load_settings(saved):
    """Merge the "settings" part of the json into the defaults (bad values are ignored)."""
    if not isinstance(saved, dict):
        return
    kb = saved.get("keybinds")
    if isinstance(kb, dict):
        merged = dict(DEFAULT_KEYBINDS)
        for bind_id in merged:
            value = kb.get(bind_id)
            if isinstance(value, str) and value.strip():
                merged[bind_id] = value.strip().lower()
        if len(set(merged.values())) == len(merged):   # a hand-edited file with clashes -> defaults
            settings["keybinds"] = merged
    wh = saved.get("webhook")
    if isinstance(wh, dict):
        for key, default in DEFAULT_WEBHOOK.items():
            value = wh.get(key, default)
            settings["webhook"][key] = value if isinstance(value, type(default)) else default
        hours = settings["webhook"]["graph_hours"]
        settings["webhook"]["graph_hours"] = min(MAX_GRAPH_HOURS, max(1, hours))
    if saved.get("family") in FAMILIES:
        settings["family"] = saved["family"]
    if saved.get("movement") in MOVEMENTS:
        settings["movement"] = saved["movement"]
    elif saved.get("family") == "Universal":
        settings["movement"] = "Universal"   # older save: Universal used to include its dashes
    if saved.get("theme") in THEMES:
        settings["theme"] = saved["theme"]
    if isinstance(saved.get("low_quality"), bool):
        settings["low_quality"] = saved["low_quality"]


# ----------------------------- hotkeys ----------------------------------
_hotkey_handles = []


HOTKEY_REPEAT_GAP = 0.6   # a hotkey can't fire again within this long (also ignores a held key's repeats)


def unregister_hotkeys():
    for kind, handle in _hotkey_handles:
        try:
            if kind == "combo":
                keyboard.remove_hotkey(handle)
            else:
                keyboard.unhook(handle)
        except Exception:  # noqa: BLE001
            pass
    _hotkey_handles.clear()


def _hotkey_handler(name, fn):
    """Wrap a hotkey action: never raises (an exception inside a keyboard callback can kill
    the library's listener thread, and then NO hotkey works any more) and ignores key repeats."""
    last = [0.0]

    def handler(_event=None):
        now = time.time()
        gap = now - last[0]
        last[0] = now        # a held key keeps refreshing this, so its repeats never re-fire
        if gap < HOTKEY_REPEAT_GAP:
            return
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log(f"Hotkey '{name}' error: {type(e).__name__}: {e}")
    return handler


def register_hotkeys():
    """(Re)bind F8 / F6 / F7 - or whatever they were changed to in Settings.
    A single key is bound with on_press_key, so it fires whatever other keys are (or seem to
    be) held down - add_hotkey stops working when the library thinks some key is stuck."""
    unregister_hotkeys()
    for key, fn in ((PAUSE_KEY, toggle_pause), (QUIT_KEY, request_stop),
                    (START_KEY, request_start)):
        handler = _hotkey_handler(key, fn)
        try:
            if "+" in key and key != "+":
                _hotkey_handles.append(("combo", keyboard.add_hotkey(key, handler)))
            else:
                _hotkey_handles.append(("key", keyboard.on_press_key(key, handler)))
        except (ValueError, KeyError) as e:
            log(f"Error: could not bind hotkey '{key}': {e}")


def to_game_key(name, keypad=False):
    """Turn a name from the keyboard library ('left shift') into one pydirectinput
    understands ('shiftleft'). Returns None if pydirectinput can't press that key."""
    n = name.lower().strip()
    if keypad and n.isdigit():
        n = "num" + n
    for side in ("left", "right"):
        if n.startswith(side + " "):
            n = n[len(side) + 1:] + side
    n = n.replace(" ", "").replace("windows", "win")
    known = getattr(pydirectinput, "KEYBOARD_MAPPING", None)
    if known is not None and n not in known:
        return None
    return n


# --------------------------- Discord webhook ----------------------------
def webhook_url():
    """The webhook URL if it looks valid, otherwise '' (= Discord is off)."""
    url = settings["webhook"]["url"].strip()
    return url if url.startswith("https://") and "/api/webhooks/" in url else ""


def mention_id():
    wh = settings["webhook"]
    uid = wh["user_id"].strip()
    return uid if wh["mention"] and uid.isdigit() else ""


def post_webhook(text, png=None, ping=True, title="ymir", embed=None):
    """Send one message (optionally with a PNG picture). Blocks; returns (ok, message)."""
    url = webhook_url()
    if not url:
        return False, "No valid webhook URL (it starts with https://discord.com/api/webhooks/)"
    uid = mention_id() if ping else ""
    payload = {"content": f"<@{uid}> {text}" if uid else text,
               "allowed_mentions": {"users": [uid]} if uid else {"parse": []}}
    if embed is not None:
        payload["embeds"] = [embed]
    if png is None:
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
    else:
        payload["embeds"] = [{"title": title, "color": 0x3B82F6,
                              "image": {"url": "attachment://stats.png"}}]
        boundary = uuid.uuid4().hex
        body = b"".join([
            (f"--{boundary}\r\n"
             'Content-Disposition: form-data; name="payload_json"\r\n'
             "Content-Type: application/json\r\n\r\n").encode(),
            json.dumps(payload).encode("utf-8"), b"\r\n",
            (f"--{boundary}\r\n"
             'Content-Disposition: form-data; name="files[0]"; filename="stats.png"\r\n'
             "Content-Type: image/png\r\n\r\n").encode(),
            png, b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    headers["User-Agent"] = "ymir-macro/1.0"   # Discord rejects the default python user agent
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT):
            return True, "Sent"
    except urllib.error.HTTPError as e:
        return False, f"Discord answered {e.code} {e.reason}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"Could not reach Discord: {e}"


def notify_async(text):
    """Send a webhook message in the background (never slows the macro down)."""
    if not webhook_url():
        return

    def work():
        ok, msg = post_webhook(text)
        if not ok:
            log(f"Discord: {msg}")
    threading.Thread(target=work, daemon=True).start()


def mission_embed(result, found):
    """The stats shown in Discord after every mission (text only, no picture)."""
    kind = result[0] if result else None
    snap = snapshot()
    done = snap["completed"] + snap["failed"]
    rate = f"{100 * snap['completed'] // done}%" if done else "-"
    parts = []
    if "scroll" in found:
        parts.append("1 scroll")
    frags = [k for k in FRAGMENT_KINDS if k in found]
    if frags:
        parts.append(f"{len(frags)} fragment{'s' if len(frags) != 1 else ''} ({', '.join(frags)})")
    run = fmt_time(time.time() - report["t0"]) if report["t0"] else "-"

    def field(name, value):
        return {"name": name, "value": str(value), "inline": True}
    return {
        "title": f"Mission #{stats['missions']} - "
                 f"{kind.capitalize() if kind else 'result not detected'}",
        "color": {"completed": 0x34D399, "failed": 0xF87171}.get(kind, 0x7A8398),
        "description": "**Loot:** " + (", ".join(parts) if parts else "nothing"),
        "fields": [field("Missions", stats["missions"]), field("Completed", snap["completed"]),
                   field("Failed", snap["failed"]), field("Success rate", rate),
                   field("Scrolls", snap["scrolls"]), field("Fragments", snap["fragments"])],
        "footer": {"text": f"Run time {run}"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def notify_mission_async(result, found):
    if not webhook_url() or not settings["webhook"]["notify_mission"]:
        return
    embed = mission_embed(result, found)

    def work():
        ok, msg = post_webhook("", ping=False, embed=embed)
        if not ok:
            log(f"Discord: {msg}")
    threading.Thread(target=work, daemon=True).start()


# ------------------------- hourly stats graph ---------------------------
report = {"run": 0, "base": None, "hourly": [], "t0": 0.0}


def snapshot():
    return {"completed": results["completed"], "failed": results["failed"],
            "scrolls": loot.get("scroll", 0),
            "fragments": sum(loot.get(k, 0) for k in FRAGMENT_KINDS)}


def report_rebase():
    """Call after the stats were reset, so the next hour doesn't count negative."""
    report["base"] = snapshot()


def render_graph(hourly, totals, run_seconds, hours=1):
    """Draw the report picture (bars per hour + totals) and return it as PNG bytes."""
    W, H = 960, 500
    BG, CARD, GRID = (23, 16, 13), (34, 23, 19), (56, 40, 34)       # BGR colours
    TEXT, SUB = (242, 233, 230), (152, 131, 122)
    GREEN, RED = (153, 211, 52), (113, 113, 248)
    font = cv2.FONT_HERSHEY_SIMPLEX
    img = np.full((H, W, 3), BG, np.uint8)

    def text(s, x, y, scale=0.55, color=TEXT, thick=1, anchor="l"):
        (tw, _), _ = cv2.getTextSize(s, font, scale, thick)
        if anchor == "c":
            x -= tw // 2
        elif anchor == "r":
            x -= tw
        cv2.putText(img, s, (int(x), int(y)), font, scale, color, thick, cv2.LINE_AA)

    text("ymir  |  stats report", 30, 48, 0.9, TEXT, 2)
    text(time.strftime("%Y-%m-%d %H:%M"), W - 30, 48, 0.55, SUB, 1, "r")
    cv2.rectangle(img, (20, 70), (640, 480), CARD, -1)
    cv2.rectangle(img, (660, 70), (940, 480), CARD, -1)

    # --- bars: completed / failed per hour ---
    text("Missions per hour" if hours == 1 else f"Missions per {hours} hours", 40, 102, 0.6, SUB)
    cv2.rectangle(img, (440, 90), (452, 102), GREEN, -1)
    text("Completed", 458, 102, 0.45)
    cv2.rectangle(img, (545, 90), (557, 102), RED, -1)
    text("Failed", 563, 102, 0.45)

    bars = hourly[-12:]
    left, right, top_y, bottom_y = 70, 620, 135, 430
    peak = max([1] + [max(h["completed"], h["failed"]) for h in bars])
    step = max(1, -(-peak // 5))
    top = step * -(-peak // step)
    for v in range(0, top + 1, step):
        y = bottom_y - (bottom_y - top_y) * v // top
        cv2.line(img, (left, y), (right, y), GRID, 1)
        text(str(v), left - 10, y + 5, 0.45, SUB, 1, "r")
    if not bars:
        text("No full hour recorded yet", (left + right) // 2, (top_y + bottom_y) // 2,
             0.6, SUB, 1, "c")
    else:
        slot = (right - left) / len(bars)
        bar_w = int(min(36, slot * 0.32))
        for i, h in enumerate(bars):
            cx = int(left + slot * (i + 0.5))
            for dx, key, color in ((-bar_w - 2, "completed", GREEN), (2, "failed", RED)):
                v = h[key]
                if v:
                    x1 = cx + dx
                    y1 = bottom_y - (bottom_y - top_y) * v // top
                    cv2.rectangle(img, (x1, y1), (x1 + bar_w, bottom_y), color, -1)
                    text(str(v), x1 + bar_w // 2, y1 - 6, 0.45, TEXT, 1, "c")
            text(time.strftime("%H:%M", time.localtime(h["t"])), cx, bottom_y + 24,
                 0.45, SUB, 1, "c")

    # --- totals ---
    text("Totals (since reset)", 680, 102, 0.6, SUB)
    done = totals["completed"] + totals["failed"]
    rate = f"{100 * totals['completed'] // done}%" if done else "-"
    rows = (("Missions", totals["missions"], TEXT), ("Completed", totals["completed"], GREEN),
            ("Failed", totals["failed"], RED), ("Success rate", rate, TEXT),
            ("Scrolls", totals["scrolls"], TEXT), ("Fragments", totals["fragments"], TEXT),
            ("Run time", fmt_time(run_seconds), TEXT))
    y = 148
    for label, value, color in rows:
        text(label, 680, y, 0.55, SUB)
        text(str(value), 920, y, 0.7, color, 2, "r")
        y += 44
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def current_entry():
    """What happened since the last report (or all-time numbers if nothing is running yet)."""
    now, base = snapshot(), report["base"]
    entry = {"t": time.time()}
    entry.update(now if base is None else {k: max(0, now[k] - base[k]) for k in now})
    return entry


def send_stats_graph(label, partial=False):
    """Draw the graph and post it. partial=True adds the interval that is still running
    (used by the test button). Blocks; returns (ok, message)."""
    hours = settings["webhook"]["graph_hours"]
    entries = list(report["hourly"])
    if partial:
        entries.append(current_entry())
    totals = dict(snapshot(), missions=stats["missions"])   # all-time numbers (since reset)
    run = time.time() - report["t0"] if report["t0"] and running() else 0
    png = render_graph(entries, totals, run, hours)
    return post_webhook(label, png=png, ping=False, title="Stats report")


def reporter_main(run_id):
    """Background timer: every N hours (Settings) while the macro runs, record that interval
    and (if turned on) send the graph to Discord."""
    last = time.time()
    while report["run"] == run_id and running():
        time.sleep(1)
        if time.time() - last < 3600 * settings["webhook"]["graph_hours"]:
            continue
        last = time.time()
        entry = current_entry()
        report["base"] = snapshot()
        report["hourly"].append(entry)
        del report["hourly"][:-24]
        if settings["webhook"]["hourly_graph"] and webhook_url():
            try:
                ok, msg = send_stats_graph("Stats report")
                log("Discord: stats graph sent" if ok else f"Discord: {msg}")
            except Exception as e:  # noqa: BLE001 - never kill the timer
                log(f"Discord: could not build the graph: {type(e).__name__}: {e}")


def start_reporter():
    report["run"] += 1
    report.update(base=snapshot(), hourly=[], t0=time.time())
    threading.Thread(target=reporter_main, args=(report["run"],), daemon=True).start()


# ------------------- shared state + events to the window ----------------
ev = queue.Queue()  # macro thread -> window
state = {"paused": False, "quit": False, "manual_start": False,
         "phase_status": "waiting",
         "mission_t0": None,        # when the current mission began (None = no mission running)
         "rescuing": False}         # True while the stuck-mission rescue is clicking
stats = {"missions": 0, "retries": 0}
loot = {kind: 0 for kind in LOOT_FILES}
results = {"completed": 0, "failed": 0}
worker = None

_sct = None
_monitor = None
_retry_template = None
_start_template = None
_loot_templates = {}
_result_templates = {}
_grab_template = None
_last_scan = 0.0
_last_grab = 0.0


class RetryFound(Exception):
    def __init__(self, match, quality="normal"):
        super().__init__("retry button found")
        self.match = match
        self.quality = quality    # which look matched: "normal" or "low" (low graphics)


def log(msg):
    ev.put(("log", msg))


def show(title, detail_text=""):
    ev.put(("now", title, detail_text))


def detail(text):
    ev.put(("detail", text))


def set_step(i):
    ev.put(("step", i))


def stats_path():
    return os.path.join(data_dir(), STATS_FILE)


def migrate_old_stats():
    """One time: if the json used to live next to the script, copy it into the Documents/Ymir Macro folder."""
    old = os.path.join(app_dir(), STATS_FILE)
    new = stats_path()
    if os.path.exists(old) and not os.path.exists(new) and os.path.abspath(old) != os.path.abspath(new):
        try:
            shutil.copy2(old, new)
        except OSError:
            pass


_save_lock = threading.Lock()


def save_stats():
    """Writes stats AND settings (same json). Resetting stats never touches settings."""
    data = {"missions": stats["missions"], "retries": stats["retries"],
            "completed": results["completed"], "failed": results["failed"],
            "loot": dict(loot), "settings": settings}
    try:
        with _save_lock:   # the macro thread and the Settings window both save
            tmp = stats_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, stats_path())  # never leaves a half-written file behind
    except OSError as e:
        log(f"Could not save stats: {e}")


def load_stats():
    migrate_old_stats()
    try:
        with open(stats_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return  # no file yet (or unreadable): start from zero
    load_settings(data.get("settings"))
    try:
        stats["missions"] = int(data.get("missions", 0))
        stats["retries"] = int(data.get("retries", 0))
        results["completed"] = int(data.get("completed", 0))
        results["failed"] = int(data.get("failed", 0))
        saved_loot = data.get("loot", {})
        for kind in loot:
            loot[kind] = int(saved_loot.get(kind, 0))
    except (TypeError, ValueError):
        pass


def push_stats(save=True):
    ev.put(("stats", stats["missions"], stats["retries"], dict(loot), dict(results)))
    if save:
        save_stats()


def reset_stats():
    """Erase everything (window + saved file) back to 0."""
    stats.update(missions=0, retries=0)
    results.update(completed=0, failed=0)
    for kind in loot:
        loot[kind] = 0
    report_rebase()
    push_stats()
    log("Stats reset to 0")


def set_status(key):
    if key in ("waiting", "running", "retrying"):
        state["phase_status"] = key
    if not state["paused"] or key in ("idle", "paused"):
        ev.put(("status", key))


# ----------------------------- controls ---------------------------------
def running():
    return worker is not None and worker.is_alive()


def toggle_pause():
    if not running():
        return
    state["paused"] = not state["paused"]
    if state["paused"]:
        ev.put(("status", "paused"))
        log("Paused")
    else:
        ev.put(("status", state["phase_status"]))
        log("Resumed")


def request_stop():
    if running():
        state["quit"] = True
        state["paused"] = False


def start_macro(manual=False):
    global worker
    if running():
        return
    state.update(paused=False, quit=False, manual_start=manual,
                 phase_status="waiting", mission_t0=None, rescuing=False)
    worker = threading.Thread(target=macro_main, daemon=True)
    worker.start()
    start_reporter()
    ev.put(("started",))


def request_start():
    if running():
        if state["quit"]:
            # still shutting down after a stop: start again as soon as it has finished
            old = worker

            def restart():
                old.join(3.0)
                if not running():
                    start_macro()
            threading.Thread(target=restart, daemon=True).start()
        elif state["phase_status"] == "waiting" and not state["paused"]:
            state["manual_start"] = True      # F8 while waiting = start the mission now
            log("Manual start requested")
        # during a mission F8 does nothing (it must not leave a stale manual start behind)
    else:
        start_macro()    # like the Start button: waits for the ability 2 icon


# ------------------------- screen detection -----------------------------
def load_template(filename):
    path = asset_path(filename)
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not load template image: {path}")
    return img


def load_quality_templates(filename):
    """{"normal": img, "low": img} for one template. The normal one is image/<filename>, the low
    graphics one is image/low quality fix/<filename>. At least one of them has to exist."""
    low_only = settings["low_quality"]      # low quality mode: the normal picture is never used
    found = {}
    for quality, name in (("normal", filename), ("low", os.path.join(LOW_FOLDER, filename))):
        if low_only and quality == "normal":
            continue
        try:
            found[quality] = load_template(name)
        except FileNotFoundError:
            pass
    if not found:
        shown = os.path.join(LOW_FOLDER, filename) if low_only else filename
        raise FileNotFoundError(f"Could not load template image: {asset_path(shown)}")
    return found


def find_quality_template(screen_bgr, templates, threshold):
    """Look for every look of a template. Returns (match, quality) of the best one that
    passes the threshold, or None. The quality says which look it was ("normal" / "low")."""
    best = None
    for quality, tpl in templates.items():
        m = find_template(screen_bgr, tpl, threshold)
        if m and (best is None or m[2] > best[0][2]):
            best = (m, quality)
    return best


def best_match(screen_bgr, template):
    """Return (center_x, center_y, score, w, h) of the best match, or None."""
    best = None
    for scale in SCALES:
        t = template if scale == 1.0 else cv2.resize(
            template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        th, tw = t.shape[:2]
        if th > screen_bgr.shape[0] or tw > screen_bgr.shape[1]:
            continue
        result = cv2.matchTemplate(screen_bgr, t, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)
        if best is None or score > best[2]:
            best = (loc[0] + tw // 2, loc[1] + th // 2, score, tw, th)
    return best


def find_template(screen_bgr, template, threshold):
    best = best_match(screen_bgr, template)
    if best and best[2] >= threshold:
        return best
    return None


def grab_screen():
    shot = np.array(_sct.grab(_monitor))
    return cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)


def red_mask(bgr):
    """Black/white image of the red text pixels (so the changing background doesn't matter)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return (cv2.inRange(hsv, (0, 120, 90), (10, 255, 255))
            | cv2.inRange(hsv, (170, 120, 90), (180, 255, 255)))


def check_grabbed(screen):
    """If the YOUR STREAK IS IN DANGER text is on screen, press the escape key."""
    global _last_grab
    if _grab_template is None or time.time() - _last_grab < GRAB_REPEAT:
        return
    if find_template(red_mask(screen), _grab_template, GRAB_THRESHOLD):
        _last_grab = time.time()
        log(f"Grabbed! Pressing {KEY_GRAB.upper()}")
        tap(KEY_GRAB)


def icon_visible():
    return find_quality_template(grab_screen(), _start_template, START_THRESHOLD) is not None


# --------------------- tick / wait (stay responsive) --------------------
def scan_for_retry():
    """Look for the retry button once (and for a grab). Raises RetryFound if it is there."""
    global _last_scan
    _last_scan = time.time()
    screen = grab_screen()
    check_grabbed(screen)
    found = find_quality_template(screen, _retry_template, THRESHOLD)
    if found:
        match = found[0]
        # screens often fade/animate in: look again and click only if it's
        # still there, at the same spot
        time.sleep(RETRY_CONFIRM_DELAY)
        again = find_quality_template(grab_screen(), _retry_template, THRESHOLD)
        if again and abs(again[0][0] - match[0]) <= 15 and abs(again[0][1] - match[1]) <= 15:
            raise RetryFound(again[0], again[1])


def _mouse_move_down(pixels):
    """Relative mouse movement (what a locked mouse in Roblox needs to turn the camera)."""
    ctypes.windll.user32.mouse_event(0x0001, 0, int(pixels), 0, 0)   # MOUSEEVENTF_MOVE


def look_down(check):
    """Press ctrl, move the mouse down for LOOK_DOWN_TIME seconds, press ctrl again.
    `check` is called all the time (stop / pause handling, may raise SystemExit)."""
    def press_ctrl():
        pydirectinput.keyDown(LOOK_DOWN_KEY)
        try:
            end = time.time() + 0.06
            while time.time() < end:
                check()
                time.sleep(0.01)
        finally:
            pydirectinput.keyUp(LOOK_DOWN_KEY)

    press_ctrl()
    end = time.time() + 0.15                 # let the cursor lock before moving
    while time.time() < end:
        check()
        time.sleep(0.01)
    end = time.time() + LOOK_DOWN_TIME
    while time.time() < end:
        check()
        _mouse_move_down(LOOK_DOWN_PIXELS)
        time.sleep(LOOK_DOWN_STEP)
    press_ctrl()
    end = time.time() + 0.15                 # let the cursor unlock before clicking
    while time.time() < end:
        check()
        time.sleep(0.01)


def click_middle(cx, cy):
    pydirectinput.moveTo(cx, cy)
    time.sleep(0.05)
    pydirectinput.moveRel(1, 0)
    time.sleep(0.05)
    pydirectinput.click()


def rescue_clicks():
    """Stuck mission (longer than MISSION_TIMEOUT): look at the ground (ctrl, mouse down for 2s,
    ctrl), then click the middle of the screen every RESCUE_CLICK_DELAY seconds until the retry
    button can be seen. The retry button being found raises RetryFound, so the normal
    end-of-mission handling takes over."""
    state["rescuing"] = True
    cx = _monitor["left"] + _monitor["width"] // 2
    cy = _monitor["top"] + _monitor["height"] // 2
    log(f"Mission is taking longer than {MISSION_TIMEOUT:g}s - looking at the ground, then "
        "clicking the middle of the screen until retry shows up")
    show("Stuck mission", "Looking at the ground, then clicking the middle of the screen")
    try:
        look_down(lambda: tick(scan_retry=False))
        while True:
            tick(scan_retry=False)                      # stop / pause
            loop_start = time.time()
            scan_for_retry()                            # raises RetryFound when it is visible
            click_middle(cx, cy)
            end = loop_start + RESCUE_CLICK_DELAY      # click-to-click gap = exactly the delay
            while time.time() < end:
                tick(scan_retry=False)
                time.sleep(0.05)
    finally:
        state["rescuing"] = False


def tick(scan_retry=True):
    """Called constantly: handles stop, pause, retry-button detection and the stuck-mission rescue."""
    if state["quit"]:
        raise SystemExit
    while state["paused"]:
        if state["quit"]:
            raise SystemExit
        time.sleep(0.1)
    if scan_retry:
        t0 = state["mission_t0"]
        if (not state["rescuing"] and t0 is not None
                and time.time() - t0 > MISSION_TIMEOUT):
            rescue_clicks()
        if time.time() - _last_scan >= SCAN_INTERVAL:
            scan_for_retry()


def wait(seconds, scan=True):
    end = time.time() + seconds
    while True:
        tick(scan)
        remaining = end - time.time()
        if remaining <= 0:
            break
        time.sleep(min(0.05, remaining))


# ----------------------------- inputs -----------------------------------
def tap(key):
    pydirectinput.keyDown(key)
    try:
        wait(random.uniform(0.03, 0.07), scan=False)   # raises SystemExit when stopped
    finally:
        pydirectinput.keyUp(key)   # never leave the key held down (it breaks the hotkeys)


def release_all_keys():
    """Best effort: let go of every key the macro presses (called when it stops)."""
    for key in {KEY_ABILITY_1ST, KEY_ABILITY_2ND, KEY_ABILITY_3RD, KEY_ABILITY_LAST,
                KEY_DASH, KEY_STRAFE, KEY_STRAFE_D, KEY_GRAB, KEY_BACK}:
        try:
            pydirectinput.keyUp(key)
        except Exception:  # noqa: BLE001
            pass


def double_tap(key):
    """One dash/strafe = the key pressed twice (like a-a)."""
    tap(key)
    wait(random.uniform(*DOUBLE_TAP_GAP), scan=False)
    tap(key)


def click_at(x, y, tw, th):
    x += random.randint(-tw // 6, tw // 6)
    y += random.randint(-th // 6, th // 6)
    pydirectinput.moveTo(x, y)
    time.sleep(random.uniform(0.08, 0.2))
    pydirectinput.moveRel(1, 0)
    time.sleep(0.05)
    pydirectinput.click()


def save_click_debug(cx, cy, tw, th):
    """Save a screenshot with a box where the click will land (for troubleshooting)."""
    if not SAVE_CLICK_DEBUG:
        return
    img = grab_screen()
    cv2.rectangle(img, (cx - tw // 2, cy - th // 2), (cx + tw // 2, cy + th // 2),
                  (0, 0, 255), 2)
    cv2.circle(img, (cx, cy), 6, (0, 0, 255), -1)
    out = os.path.join(app_dir(), "last_retry_click.png")
    cv2.imwrite(out, img)


# ----------------------------- loot tracking ----------------------------
def gold_mask(bgr):
    """Black/white image of the gold text pixels (so the background doesn't matter)."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (12, 70, 150), (40, 255, 255))


def scan_end_screen(quality="normal", want_loot=True, want_result=True, scan_time=None):
    """
    Look at the end screen for a moment. Only the loot icons of the same graphics quality as
    the retry button are looked for ("low" icons for a low graphics screen), so the two looks
    never get mixed up.
    Returns (loot, result):
      loot   = {kind: (cx, cy, score, w, h)} for every loot icon seen
      result = ("completed" | "failed", (cx, cy, score, w, h)) or None
    want_loot / want_result turn one of the two scans off.
    """
    loot_found = {}
    result_best = {}
    loot_tpls = _loot_templates.get(quality, {}) if want_loot else {}
    end = time.time() + (LOOT_SCAN_TIME if scan_time is None else scan_time)
    while True:
        screen = grab_screen()
        for kind, tpl in loot_tpls.items():
            best = best_match(screen, tpl)
            if best and best[2] >= LOOT_THRESHOLD:
                if kind not in loot_found or best[2] > loot_found[kind][2]:
                    loot_found[kind] = best
        if _result_templates and want_result:
            mask = gold_mask(screen)
            for kind, tpl in _result_templates.items():
                th, tw = tpl.shape[:2]
                if th > mask.shape[0] or tw > mask.shape[1]:
                    continue
                res = cv2.matchTemplate(mask, tpl, cv2.TM_CCOEFF_NORMED)
                _, score, _, loc = cv2.minMaxLoc(res)
                if kind not in result_best or score > result_best[kind][2]:
                    result_best[kind] = (loc[0] + tw // 2, loc[1] + th // 2, score, tw, th)
        if time.time() >= end:
            break
        wait(LOOT_SCAN_STEP, scan=False)

    result = None
    for kind, m in result_best.items():
        if m[2] >= RESULT_THRESHOLD and (result is None or m[2] > result[1][2]):
            result = (kind, m)

    if SAVE_LOOT_DEBUG and (loot_found or result):
        img = grab_screen()
        marks = {k: (v, (0, 255, 0)) for k, v in loot_found.items()}
        if result:
            marks["result " + result[0]] = (result[1], (0, 200, 255))
        for label, ((cx, cy, score, tw, th), color) in marks.items():
            cv2.rectangle(img, (cx - tw // 2, cy - th // 2), (cx + tw // 2, cy + th // 2),
                          color, 2)
            cv2.putText(img, f"{label} {score:.2f}", (cx - tw // 2, cy - th // 2 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        out = os.path.join(app_dir(), "last_end_scan.png")
        cv2.imwrite(out, img)
    return loot_found, result


def record_result(result):
    """Count the mission as completed or failed (if the text was seen)."""
    if result is None:
        log("Result: not detected")
    else:
        kind = result[0]
        results[kind] += 1
        log(f"Result: {kind.capitalize()}")
    push_stats()


def record_loot(found):
    """Add one to each kind that was seen, log it, update the window."""
    for kind in found:
        loot[kind] += 1
    scrolls = 1 if "scroll" in found else 0
    frags = [k for k in FRAGMENT_KINDS if k in found]
    if not found:
        log("Loot: nothing found")
    else:
        parts = []
        if scrolls:
            parts.append("1 scroll")
        if frags:
            parts.append(f"{len(frags)} fragment{'s' if len(frags) != 1 else ''} "
                         f"({', '.join(frags)})")
        log("Loot: " + ", ".join(parts))
    push_stats()


# ------------------- mission start / end handling -----------------------
def wait_for_mission_start(scan_retry=True):
    """Block until the ability-2 icon appears (or F8 is pressed).

    scan_retry=False means hands-off: no retry-button scanning and no clicks.
    It is used right after clicking retry, so we never click twice.
    """
    set_status("waiting")
    set_step(-1)
    show("Waiting for the mission", "Looking for the ability 2 icon")
    log("Waiting for the mission to start")
    while True:
        tick(scan_retry=scan_retry)
        if state["manual_start"]:
            state["manual_start"] = False
            return
        if icon_visible():
            log("Mission started (icon detected)")
            wait(START_SETTLE_DELAY, scan=False)
            return
        time.sleep(0.2)


def hands_off_wait(seconds):
    """Do nothing (no scanning, no inputs) for a while, showing a countdown."""
    end = time.time() + seconds
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            break
        show("Hands off", f"Waiting after the retry click... {remaining:.0f}s")
        wait(min(0.5, remaining), scan=False)


def wait_for_icon_gone():
    """After retry, wait for the old mission HUD to disappear (loading)."""
    show("Hands off", "Waiting for the next mission to load")
    deadline = time.time() + ICON_GONE_TIMEOUT
    while time.time() < deadline:
        tick(scan_retry=False)
        if not icon_visible():
            return
        time.sleep(0.2)


def buy_time_until_ability4_ready():
    """Strafe A for the length of ability 4's cooldown. Call right after ability 3."""
    start = time.time()
    total = ABILITY4_COOLDOWN + ABILITY4_COOLDOWN_MARGIN
    keys = BUY_TIME_MOVES
    i = 0
    next_strafe = start
    while True:
        now = time.time()
        remaining = total - (now - start)
        if remaining <= 0:
            return
        detail(f"Strafing {KEY_STRAFE.upper()}... ability 4 ready in {remaining:.0f}s")
        if now >= next_strafe:
            double_tap(keys[i % len(keys)])
            i += 1
            next_strafe = time.time() + random.uniform(*STRAFE_DELAY)
        wait(0.05)


def spam_key_for(key, seconds, interval, label):
    """Press one key over and over for a while."""
    end = time.time() + seconds
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            return
        detail(f"Spamming {label}... {remaining:.0f}s left")
        tap(key)
        wait(min(interval, max(remaining, 0.01)))


def strafe_for(key, seconds):
    """Double-tap a strafe key over and over for a while."""
    end = time.time() + seconds
    next_strafe = time.time()
    while True:
        now = time.time()
        remaining = end - now
        if remaining <= 0:
            return
        detail(f"Strafing {key.upper()}... {remaining:.0f}s left")
        if now >= next_strafe:
            double_tap(key)
            next_strafe = time.time() + random.uniform(*STRAFE_DELAY)
        wait(0.05)


def dash_spam_for(key, seconds):
    """Dash (double-tap) over and over for a while - Wings of Freedom movement."""
    end = time.time() + seconds
    next_dash = time.time()
    while True:
        now = time.time()
        remaining = end - now
        if remaining <= 0:
            return
        detail(f"Dashing... {remaining:.0f}s left")
        if now >= next_dash:
            double_tap(key)
            next_dash = time.time() + random.uniform(*WINGS_DASH_GAP)
        wait(0.05)


def spam_recorded_dash(key, seconds):
    """Universal movement: Space pressed over and over with the timings of a recorded macro
    (each press held ~65-90 ms, ~50-80 ms between presses)."""
    end = time.time() + seconds
    while True:
        remaining = end - time.time()
        if remaining <= 0:
            return
        show("Dashing", f"Spamming dash... {remaining:.0f}s left")
        pydirectinput.keyDown(key)
        try:
            wait(random.uniform(*UNIVERSAL_DASH_HOLD), scan=False)
        finally:
            pydirectinput.keyUp(key)
        wait(random.uniform(*UNIVERSAL_DASH_PRESS_GAP), scan=False)


# ---------------------------- the routine -------------------------------
def run_mission():
    state["manual_start"] = False   # a mission is running now: forget any leftover F8 press
    state["mission_t0"] = time.time()   # for the stuck-mission rescue (MISSION_TIMEOUT)
    stats["missions"] += 1
    push_stats()
    ev.put(("mission_started",))
    set_status("running")

    set_step(0)
    show("Ability 2", "Only ability 2 for now - no dashing yet")
    log("Ability 2")
    tap(KEY_ABILITY_1ST)
    wait(AFTER_ABILITY2_DELAY)  # nothing else happens until the dash sequence

    # read once per mission: the movement only changes the initial dash sequence,
    # the family (abilities) decides what happens from ability 3 on
    movement = settings["movement"]
    universal = settings["family"] == "Universal"
    blood = settings["family"] == "Blood Awakening"

    set_step(1)
    if movement == "Wings of Freedom":
        log(f"Movement: Wings of Freedom - dashing for {WINGS_DASH_TIME:g}s")
        show("Dashing", f"Spamming dash for {WINGS_DASH_TIME:g}s")
        dash_spam_for(KEY_DASH, WINGS_DASH_TIME)

        set_step(2)
        show("Strafe", f"Strafing {KEY_STRAFE.upper()} for {WINGS_STRAFE_TIME:g}s")
        log(f"Strafe {KEY_STRAFE.upper()} for {WINGS_STRAFE_TIME:g}s")
        strafe_for(KEY_STRAFE, WINGS_STRAFE_TIME)
    elif movement == "Universal":
        log(f"Movement: Universal - spamming dash for {UNIVERSAL_DASH_TIME:g}s")
        spam_recorded_dash(KEY_DASH, UNIVERSAL_DASH_TIME)

        set_step(2)
        show("Strafe", f"Double-tap {KEY_STRAFE.upper()}")
        log("Strafe")
        double_tap(KEY_STRAFE)
    else:
        log(f"Dashing x{DASH_COUNT}")
        for n in range(DASH_COUNT):
            show("Dashing", f"Dash {n + 1} / {DASH_COUNT}")
            double_tap(KEY_DASH)
            wait(random.uniform(*DASH_GAP))  # gap between dashes

        set_step(2)
        show("Strafe", f"Double-tap {KEY_STRAFE.upper()}")
        log("Strafe")
        double_tap(KEY_STRAFE)
    wait(0.3)

    if blood:
        # Blood Awakening: no ability 3 / buying time / ability 4 - straight to the ability 5 shift
        log("Blood Awakening: skipping to ability 5")
    else:
        set_step(3)
        show("Ability 3")
        log("Ability 3")
        tap(KEY_ABILITY_2ND)  # no pause: buying time starts right away

    if blood:
        pass
    elif universal:
        set_step(4)
        show("Ability 4", f"Spamming ability 4 for {UNIVERSAL_ABILITY4_SPAM:g}s")
        log(f"Ability 4 spam for {UNIVERSAL_ABILITY4_SPAM:g}s")
        spam_key_for(KEY_ABILITY_3RD, UNIVERSAL_ABILITY4_SPAM,
                     UNIVERSAL_ABILITY4_INTERVAL, "ability 4")
        set_step(5)
        show("Buying time", f"Strafe {KEY_STRAFE.upper()} once, {KEY_STRAFE_D.upper()}, "
                            f"then {KEY_STRAFE.upper()}")
        log(f"Strafe {KEY_STRAFE.upper()} once")
        double_tap(KEY_STRAFE)
        wait(random.uniform(*STRAFE_DELAY))
        log(f"Strafe {KEY_STRAFE_D.upper()} for {UNIVERSAL_STRAFE_D_TIME:g}s")
        strafe_for(KEY_STRAFE_D, UNIVERSAL_STRAFE_D_TIME)
        log(f"Strafe {KEY_STRAFE.upper()} for {UNIVERSAL_STRAFE_A_TIME:g}s")
        strafe_for(KEY_STRAFE, UNIVERSAL_STRAFE_A_TIME)
    else:
        set_step(4)
        show("Buying time", f"Strafing {KEY_STRAFE.upper()} until ability 4 is off cooldown")
        log(f"Buying time for {ABILITY4_COOLDOWN:.0f}s (ability 4 cooldown)")
        buy_time_until_ability4_ready()

        set_step(5)
        show("Ability 4")
        log("Ability 4")
        tap(KEY_ABILITY_3RD)
        wait(AFTER_ABILITY_DELAY)

    set_step(6)
    show("Shift", "Spamming ability 5 so the shift is used")
    log(f"Ability 5 spam for {SHIFT_SPAM_TIME:g}s (shift)")
    spam_end = time.time() + SHIFT_SPAM_TIME
    while time.time() < spam_end:
        tap(KEY_ABILITY_LAST)
        wait(SHIFT_SPAM_INTERVAL)
    log(f"Waiting {SHIFTED4_SPAM_AT:g}s for the shift (then shifted ability 4)")
    shift_end = time.time() + SHIFTED4_SPAM_AT
    extra_end = time.time() + SHIFT_SPAM_EXTRA   # still pressing 5 quietly during the first seconds of the wait
    while True:
        remaining = shift_end - time.time()
        if remaining <= 0:
            break
        show("Shift", f"Waiting for the shift... {remaining:.0f}s")
        if time.time() < extra_end:
            tap(KEY_ABILITY_LAST)
            wait(min(SHIFT_SPAM_INTERVAL, remaining))
        else:
            wait(min(0.5, remaining))

    set_step(7)
    log(f"Shifted ability 4 spam for {SHIFTED4_SPAM_TIME:g}s")
    spam_key_for(KEY_ABILITY_3RD, SHIFTED4_SPAM_TIME, SHIFTED4_SPAM_INTERVAL,
                 "shifted ability 4")
    show("Shifted ability 4", f"Waiting {SHIFTED_4_TO_5_DELAY:g}s before ability 5")
    wait(SHIFTED_4_TO_5_DELAY)

    set_step(8)
    log("Ability 5 over and over (until retry shows up)")
    presses = 0
    while True:
        presses += 1
        show("Ability 5", f"Pressed x{presses} - until the retry button shows up")
        tap(KEY_ABILITY_LAST)
        wait(ABILITY_5_CHECK_INTERVAL)


# --------------------------- macro thread -------------------------------
def macro_main():
    global _sct, _monitor, _retry_template, _start_template, _grab_template
    try:
        _retry_template = load_quality_templates(TEMPLATE_FILE)
        _start_template = load_quality_templates(START_TEMPLATE_FILE)
        _grab_template = None
        if GRAB_ENABLED:
            try:
                _grab_template = red_mask(load_template(GRAB_FILE))
            except FileNotFoundError:
                log(f"Grab: {GRAB_FILE} not found - grab detection is off")
        _result_templates.clear()
        for kind, filename in RESULT_FILES.items():
            try:
                _result_templates[kind] = gold_mask(load_template(filename))
            except FileNotFoundError:
                log(f"Result: {filename} not found - skipping {kind}")
        _loot_templates.clear()
        if LOOT_ENABLED:
            for quality, folder in (("normal", ""), ("low", LOW_FOLDER)):
                if settings["low_quality"] and quality == "normal":
                    continue        # low quality mode: only the low quality pictures
                _loot_templates[quality] = {}
                for kind, filename in LOOT_FILES.items():
                    if settings["low_quality"] and kind == "body":
                        continue    # low quality mode: body fragments are not searched at all
                    try:
                        _loot_templates[quality][kind] = load_template(
                            os.path.join(folder, filename))
                    except FileNotFoundError:
                        if quality == "normal" or any(
                                os.path.exists(asset_path(os.path.join(LOW_FOLDER, f)))
                                for f in LOOT_FILES.values()):
                            tag = "" if quality == "normal" else " (low quality)"
                            log(f"Loot{tag}: {filename} not found - skipping {kind}")
        if settings["low_quality"]:
            log("Low quality mode: using only the pictures from the low quality fix folder "
                "(body fragments are not checked)")
        log("Started. Click into Roblox; the routine starts when the mission begins.")

        with mss.mss() as sct:
            _sct = sct
            _monitor = sct.monitors[MONITOR_INDEX]

            need_start = True
            after_retry = False
            while True:
                try:
                    if need_start:
                        # right after a retry click: do nothing until the next
                        # mission starts (no retry scanning, no clicks, no keys)
                        wait_for_mission_start(scan_retry=not after_retry)
                        need_start = False
                        after_retry = False
                    run_mission()
                except RetryFound as r:
                    state["mission_t0"] = None     # the mission is over (no rescue needed)
                    cx, cy, score, tw, th = r.match
                    abs_x = _monitor["left"] + cx
                    abs_y = _monitor["top"] + cy
                    ev.put(("mission_ended",))
                    set_status("retrying")
                    set_step(-1)
                    log(f"Retry found ({r.quality} quality, score {score:.2f})")
                    low = r.quality == "low"
                    loot_found, result = {}, None
                    loot_on = bool(_loot_templates.get(r.quality))   # loot icons of THIS quality
                    # normal quality: result + loot are read before the click.
                    # low quality: only the result now, the loot after the click (see below)
                    if _result_templates or (loot_on and not low):
                        show("Retry found", "Checking the result and loot..."
                             if not low else "Checking the result...")
                        loot_found, result = scan_end_screen(
                            r.quality, want_loot=not low, want_result=True)
                        if _result_templates:
                            record_result(result)
                        if loot_on and not low:
                            record_loot(loot_found)
                    if not low:
                        notify_mission_async(result, loot_found)   # Discord stats embed (if on)
                    show("Retry found", "Clicking...")
                    log("Clicking retry")
                    save_click_debug(cx, cy, tw, th)
                    click_at(abs_x, abs_y, tw, th)
                    clicked_at = time.time()
                    stats["retries"] += 1
                    push_stats()
                    if low:
                        if loot_on:
                            show("Checking loot", f"Low quality: looking for the loot for "
                                                  f"{LOW_LOOT_SCAN_TIME:g}s after the click")
                            log(f"Low quality: checking the loot for {LOW_LOOT_SCAN_TIME:g}s "
                                "after the retry click")
                            loot_found, _ = scan_end_screen(
                                r.quality, want_loot=True, want_result=False,
                                scan_time=LOW_LOOT_SCAN_TIME)
                            record_loot(loot_found)
                        notify_mission_async(result, loot_found)
                    # the loot scan above counts as part of the hands-off time
                    left = max(0.0, AFTER_CLICK_DELAY - (time.time() - clicked_at))
                    log(f"Hands off for {left:.0f}s more, then waiting for the next mission")
                    hands_off_wait(left)
                    wait_for_icon_gone()
                    after_retry = True
                    need_start = True
    except SystemExit:
        log("Stopped")
    except Exception as e:  # noqa: BLE001 - show any error in the window
        log(f"Error: {type(e).__name__}: {e}")
        if settings["webhook"]["notify_error"]:
            notify_async(f"ymir stopped because of an error: {type(e).__name__}: {e}")
    finally:
        state["mission_t0"] = None
        release_all_keys()
        ev.put(("done",))


# ------------------------------- window ---------------------------------
def fmt_time(sec):
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


GITHUB_URL = "https://github.com/SOUL-q"
# 64x64 alpha mask of the GitHub mark; it is tinted + resized at runtime (any theme colour, any DPI)
GITHUB_MASK_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAAAAACPAi4CAAADt0lEQVR42pVXW2yMQRT+dnbpUvRCU3Vp1a0Xl7RItEE9IAgSkVQkLiVUCNEiooQEaUKppCX60gfx5E5F4vZC0jTufRGqoi5NpFRbLVva0j0edv+d88/+u//seZoz53zfP//MnMs4EEJScrPTUhNj3OjpbP3QWP+kGRGIyDvTRIq8r5zn0IQPL/lIlvKhZLgOvNxDIcVzMt4G7ir+QWGlY5czHH7Kc7KVpxmh8Vt+k4Z0bwq1/CrSlLOWvzHoNmnLLbcF/gFFIPeDGFy3KSKpUf+iiiKUSmX/KWLZwPGZgfNbNmPthZ+hML8vFWRndRu3Mo1tQOD+vAaAocUtVvAfh+MB4KahPxYA4AKAnbMMqocA8KuiumRfFLoamr62ERCblJo5At7qQ20AgEcr/b45288Z8SPv/3aDKaMwjUdv8rq5xnBBwLndiKxTcpmr7MN1mvQ+7l+AJyKCKdL7ZxwggK3R0ppgT5Aoh0O3AAKikFmn2xNwl60OAHn8qF7ZE1zj/rkAzjDdu1xjBd0McBoAz79VOkm3iAHeAuOY2qWTdeFqZJDRYjYzXWjXIfjHAzFXzGDaRb3CcaVfjrNFulQ8z/QI2thZpYsUqTT0a9au13I4ToyUyjfd2tkihyNFjFT6dAmYY4yIkspAXQLmOEiw+VhdAuZIolcqSboEo+WwR3SypiRKk2CyHHYKtvWuLM0OZDw7EPGZWRbqESxg2fKTaGCW1XoE+WzcgDU8P8zTwSf3EU+iKZygVqcRO88Ro4D3XN9pj1/iZf5vAFRygt5FdvipHdy/HMB8c/3MD4+f02pyzwEgzG2ltzpMXosu/WtyfusAgANERNR45FitPzOWTbSGjzr4VSnYe1hpuyWAxcb6XpatTBUm8NilR+v+qQW/y58LThIR0b1kIKNdWutYZDhuWDYcpcbd9m3slxRgRcDYN5kvIMGqA/4eCOtd/ibWxW7JZfP/l1sQbAtYnU99M7sB9x2/db2ZIC8YX8d2Kd1X7zqGAc6iZiLyXFWyS2xw62/6x42+ySIAcEyamTEg6Ax7VQJlib4a3RK6wehW8BWK3VlDRETPQuZF5SVwI6hhd9/zdV6HJgAABquB/ceEv2uRPt1GB/m9/kX9F+9gxdzD8dct06+zgvtEh9nEilDvpg2s4RuiljP55CkIk/DrAm7DFFMgjp+khX2zbmvz+6l1zh+K7TucdnWvtIuIiNS00k9E9OtEnEbWjdn7jqhZ/dAboqb9cZq1z5G7eYw6l7R5vu7jOzL5D54ffEhC1T+eAAAAAElFTkSuQmCC"
)


def tinted_icon(color_hex, px):
    """The GitHub mark in one colour, px x px, as a tk.PhotoImage (None if it can't be made)."""
    try:
        raw = base64.b64decode(GITHUB_MASK_B64)
        mask = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
        mask = cv2.resize(mask, (px, px), interpolation=cv2.INTER_AREA)
        r, g, b = (int(color_hex[i:i + 2], 16) for i in (1, 3, 5))
        img = np.zeros((px, px, 4), np.uint8)
        img[..., 0], img[..., 1], img[..., 2], img[..., 3] = b, g, r, mask
        ok, buf = cv2.imencode(".png", img)
        return tk.PhotoImage(data=base64.b64encode(buf.tobytes())) if ok else None
    except Exception:
        return None


def rounded_rect(c, x1, y1, x2, y2, r, **kw):
    """Draw a rounded rectangle on a canvas (a plain rectangle when the corners are ~square)."""
    if r < 2.5:
        return c.create_rectangle(x1, y1, x2, y2, **kw)
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
           x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


class ActionTile(tk.Canvas):
    """
    Control tile: icon top-left, hotkey badge top-right, label bottom-left.

    States:  normal  -> clickable
             active  -> blue border + tinted background (the current mode)
             disabled-> dimmed, not clickable
    """
    # (fill, outline, outline_width, label_fg, badge_outline, badge_fg)
    LOOK = {
        "normal":   ("#1a1e29", "#2a3042", 1, "#e6e9f2", "#3a4156", "#9aa3b8"),
        "hover":    ("#212637", "#3a4156", 1, "#ffffff", "#4a5270", "#b4bcd0"),
        "active":   ("#16254a", "#3b6fe0", 2, "#ffffff", "#3b5cb0", "#9db8ff"),
        "disabled": ("#13161e", "#1b202c", 1, "#4b5264", "#232837", "#4b5264"),
    }
    OFF_ICON = "#3c4254"

    def __init__(self, parent, label, key_text, icon, icon_color, on_click,
                 parent_bg, height=66):
        super().__init__(parent, width=120, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0)
        self.th = height
        self.label_text = label
        self.key_text = key_text
        self.icon = icon
        self.icon_color = icon_color
        self.on_click = on_click
        self.enabled = True
        self.active = False
        self.hovering = False
        self.pressed = False
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    # ----- drawing -----
    def draw(self):
        self.delete("all")
        w, h = max(self.winfo_width(), 60), self.th
        if not self.enabled:
            look = self.LOOK["disabled"]
        elif self.active:
            look = self.LOOK["active"]
        elif self.hovering:
            look = self.LOOK["hover"]
        else:
            look = self.LOOK["normal"]
        fill, outline, ow, label_fg, badge_line, badge_fg = look

        inset = ow / 2 + 0.5
        rounded_rect(self, inset, inset, w - inset, h - inset, App.R_TILE,
                     fill=fill, outline=outline, width=ow)

        self._draw_icon(24, 24, self.icon_color if self.enabled else self.OFF_ICON)

        # hotkey badge
        bx2, by1, bx2_h = w - 12, 12, 18
        bx1 = bx2 - max(30, 8 * len(self.key_text) + 14)
        rounded_rect(self, bx1, by1, bx2, by1 + bx2_h, min(5, App.R_TILE),
                     fill="", outline=badge_line, width=1)
        self.create_text((bx1 + bx2) / 2, by1 + bx2_h / 2, text=self.key_text,
                         fill=badge_fg, font=(App.FONT, 8, "bold"))

        self.create_text(16, h - 15, text=self.label_text, fill=label_fg,
                         anchor="w", font=(App.FONT, 10, "bold"))

    def _draw_icon(self, cx, cy, color):
        if self.icon == "play":
            self.create_polygon(cx - 5, cy - 8, cx - 5, cy + 8, cx + 8, cy,
                                fill=color, outline=color, width=2, joinstyle="round")
        elif self.icon == "pause":
            for dx in (-6, 2):
                rounded_rect(self, cx + dx, cy - 8, cx + dx + 5, cy + 8, 1.5,
                             fill=color, outline="")
        elif self.icon == "stop":
            rounded_rect(self, cx - 7, cy - 7, cx + 7, cy + 7, min(3, App.R_TILE),
                         fill=color, outline="")

    # ----- state -----
    def update_tile(self, label=None, enabled=None, active=None, key_text=None):
        if label is not None:
            self.label_text = label
        if key_text is not None:
            self.key_text = key_text
        if enabled is not None:
            self.enabled = enabled
            self.configure(cursor="hand2" if enabled else "arrow")
        if active is not None:
            self.active = active
        self.draw()

    # ----- mouse -----
    def _on_enter(self, _e):
        self.hovering = True
        self.draw()

    def _on_leave(self, _e):
        self.hovering = False
        self.pressed = False
        self.draw()

    def _on_press(self, _e):
        self.pressed = True

    def _on_release(self, e):
        was_pressed, self.pressed = self.pressed, False
        if (was_pressed and self.enabled and self.on_click
                and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.th):
            self.on_click()


class Pill(tk.Canvas):
    """Small rounded status badge with a coloured dot."""

    def __init__(self, parent, parent_bg, width=94, height=26):
        super().__init__(parent, width=width, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0)
        self.pw, self.ph = width, height

    def update_pill(self, text, bg, fg):
        self.delete("all")
        rounded_rect(self, 1, 1, self.pw - 1, self.ph - 1,
                     self.ph // 2 if App.R_PILL is None else App.R_PILL,
                     fill=bg, outline="")
        r = 3.5
        self.create_oval(14 - r, self.ph / 2 - r, 14 + r, self.ph / 2 + r,
                         fill=fg, outline="")
        self.create_text(26, self.ph / 2, text=text, fill=fg, anchor="w",
                         font=(App.FONT, 9, "bold"))


class ToggleSwitch(tk.Canvas):
    """Modern on/off switch bound to a BooleanVar (replaces the old tick boxes)."""
    ON, OFF, KNOB = "#3b82f6", "#272e40", "#ffffff"

    def __init__(self, parent, variable, command=None, parent_bg=None):
        super().__init__(parent, width=38, height=22, bg=parent_bg or App.CARD,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.var = variable
        self.command = command
        self.var.trace_add("write", lambda *_: self.draw())
        self.bind("<Button-1>", self.flip)
        self.draw()

    def flip(self, _e=None):
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def draw(self):
        try:
            self.delete("all")
            on = bool(self.var.get())
            rounded_rect(self, 1, 1, 37, 21, App.R_SWITCH, fill=self.ON if on else self.OFF,
                         outline="")
            x = 28 if on else 10
            rounded_rect(self, x - 7, 11 - 7, x + 7, 11 + 7, max(0, App.R_SWITCH - 3),
                         fill=self.KNOB, outline="")
        except tk.TclError:
            pass    # the window was closed


def switch_row(parent, text, var, command, bg, fg, sub_font=None, pady=4):
    """Label on the left, switch on the right. Clicking the label flips it too."""
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=pady)
    sw = ToggleSwitch(row, var, command, parent_bg=bg)
    sw.pack(side="right")
    lbl = tk.Label(row, text=text, font=sub_font or (App.FONT, 10), fg=fg, bg=bg, anchor="w",
                   cursor="hand2")
    lbl.pack(side="left", fill="x", expand=True)
    lbl.bind("<Button-1>", sw.flip)
    return row


class Stepper(tk.Canvas):
    """A row of small segments showing which mission step is running."""

    def __init__(self, parent, n_segments, parent_bg, colors):
        super().__init__(parent, height=6, bg=parent_bg, highlightthickness=0, bd=0)
        self.n_segments = n_segments
        self.current = -1
        self.seg_colors = colors  # (done, current, pending)
        self.bind("<Configure>", lambda _e: self.draw())

    def set_index(self, idx):
        self.current = idx
        self.draw()

    def draw(self):
        self.delete("all")
        width = max(int(self.winfo_width()), 20)
        gap = 5
        seg = (width - gap * (self.n_segments - 1)) / self.n_segments
        done, cur, pending = self.seg_colors
        for i in range(self.n_segments):
            x1 = i * (seg + gap)
            if self.current < 0 or i > self.current:
                col = pending
            elif i < self.current:
                col = done
            else:
                col = cur
            rounded_rect(self, x1, 0, x1 + seg, 6, App.R_SEG, fill=col, outline="")


def style_title_bar(root, bg_hex):
    """Dark title bar on Windows 10/11 (silently skipped if unsupported)."""
    try:
        root.update()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old id)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on))
        r, g, b = (int(bg_hex[i:i + 2], 16) for i in (1, 3, 5))
        color = ctypes.c_int(b << 16 | g << 8 | r)  # COLORREF 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))
    except Exception:
        pass


# ------------------------------- updater --------------------------------
_update = {"busy": False}


def parse_version(text):
    """'v1.1.2' -> (1, 1, 2, 0) so versions can be compared."""
    nums = [int(n) for n in re.findall(r"\d+", str(text))][:4]
    return tuple(nums + [0] * (4 - len(nums)))


def update_repo_ok():
    return bool(re.fullmatch(r"[\w.-]+/[\w.-]+", UPDATE_REPO)) and "REPO_NAME" not in UPDATE_REPO


def fetch_latest_release():
    """Ask GitHub for the latest (non-draft, non-prerelease) release of UPDATE_REPO."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest",
        headers={"User-Agent": "ymir-macro-updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))
    info = {"tag": str(data.get("tag_name", "")),
            "page": data.get("html_url") or f"https://github.com/{UPDATE_REPO}/releases",
            "url": None, "size": None, "digest": None}
    prefix = f"https://github.com/{UPDATE_REPO}/releases/download/"
    for a in data.get("assets", []):
        url = a.get("browser_download_url", "")
        if a.get("name", "").lower().endswith(".exe") and url.startswith(prefix):
            info.update(url=url, size=a.get("size"), digest=a.get("digest"))
            break
    return info


def _update_check_worker(manual):
    info, error = None, None
    try:
        info = fetch_latest_release()
    except urllib.error.HTTPError as e:
        error = "no release found on GitHub" if e.code == 404 else f"GitHub answered {e.code}"
    except Exception as e:  # noqa: BLE001  (no internet, timeout, bad json ...)
        error = f"{type(e).__name__}: {e}"
    ev.put(("update_result", manual, info, error))


def start_update_check(manual=False):
    if _update["busy"]:
        return
    if not update_repo_ok():
        if manual:
            log("Error: update checker - set UPDATE_REPO (owner/repo) at the top of the script")
        return
    _update["busy"] = True
    if manual:
        log("Checking for updates...")
    threading.Thread(target=_update_check_worker, args=(manual,), daemon=True).start()


def _install_update_worker(info):
    """Download the new .exe next to the running one, check it, then hand over to a small .bat
    that waits for this program to close, swaps the files and starts the new version."""
    exe = sys.executable
    new_path = exe + ".new"
    try:
        log(f"Downloading {info['tag']}...")
        req = urllib.request.Request(info["url"], headers={"User-Agent": "ymir-macro-updater"})
        sha = hashlib.sha256()
        done, last_pct = 0, -1
        with urllib.request.urlopen(req, timeout=UPDATE_TIMEOUT) as r, open(new_path, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total // 20 * 20
                    if pct != last_pct:
                        last_pct = pct
                        log(f"Downloading update... {pct}%")
        # make sure it is the whole, real file
        if info.get("size") and done != info["size"]:
            raise RuntimeError(f"incomplete download ({done} of {info['size']} bytes)")
        with open(new_path, "rb") as f:
            if f.read(2) != b"MZ":
                raise RuntimeError("the downloaded file is not a Windows program")
        digest = str(info.get("digest") or "")
        if digest.startswith("sha256:") and digest[7:].lower() != sha.hexdigest():
            raise RuntimeError("the download does not match GitHub's checksum")

        q = lambda path: path.replace("%", "%%")      # % is special inside a .bat
        bat = os.path.join(tempfile.gettempdir(), "ymir_update.bat")
        with open(bat, "w", encoding="mbcs", errors="replace", newline="\r\n") as f:
            f.write("\n".join([
                "@echo off",
                "set _MEIPASS2=",
                "set PYINSTALLER_RESET_ENVIRONMENT=1",
                f'cd /d "{q(os.path.dirname(exe))}"',
                "set /a n=0",
                ":wait",
                "set /a n+=1",
                f'move /y "{q(new_path)}" "{q(exe)}" >nul 2>&1',
                "if not errorlevel 1 goto done",
                "if %n% geq 60 goto end",
                "ping -n 2 127.0.0.1 >nul",
                "goto wait",
                ":done",
                f'start "" "{q(exe)}"',
                ":end",
                '(goto) 2>nul & del "%~f0"',
            ]) + "\n")
        env = {k: v for k, v in os.environ.items() if k != "_MEIPASS2"}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        subprocess.Popen(["cmd", "/c", bat], env=env, close_fds=True,
                         creationflags=0x08000000 | 0x00000008)   # no window, detached
        log("Update downloaded - restarting...")
        ev.put(("update_ready",))
    except Exception as e:  # noqa: BLE001
        log(f"Error: update failed - {type(e).__name__}: {e}")
        try:
            os.remove(new_path)
        except OSError:
            pass
        _update["busy"] = False


def install_update(info):
    threading.Thread(target=_install_update_worker, args=(info,), daemon=True).start()


class App:
    BG = "#0b0e14"
    CARD = "#11151e"
    BORDER = "#1a2030"
    LOGBG = "#0f121a"
    TEXT = "#e6e9f2"
    SUB = "#7a8398"
    ACCENT = "#3b82f6"
    # label, pill background, pill text/dot colour
    PILLS = {
        "idle":     ("Idle",     "#1d2230", "#9aa3b8"),
        "waiting":  ("Waiting",  "#2e2410", "#fbbf24"),
        "running":  ("Running",  "#0f2a22", "#34d399"),
        "retrying": ("Retrying", "#14243f", "#60a5fa"),
        "paused":   ("Paused",   "#251d3f", "#a78bfa"),
    }
    def idle_hint(self):
        return (f"Press Start or {START_KEY.upper()}. "
                "Keep this window off the game area.")

    def __init__(self, root):
        self.root = root
        self.run_t0 = None
        self.mission_t0 = None
        self.mission_last = None
        self.reset_armed = False
        self.reset_job = None
        self.settings_win = None
        self.pill_key = "idle"
        self.step_idx = -1

        root.withdraw()     # stay hidden while building, so the window never flickers on open
        apply_theme(settings["theme"])
        root.title("ymir")
        try:
            root.iconbitmap(asset_path(ICON_FILE))
        except (tk.TclError, OSError):
            pass  # no icon file: keep the default window icon
        root.configure(bg=self.BG)
        root.geometry("430x720+20+20")  # top-left, away from the game's HUD/buttons
        root.minsize(400, 660)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        try:
            ttk.Style(root).theme_use("clam")
        except tk.TclError:
            pass

        self.build_ui()
        self.set_pill("idle")
        self.set_step(-1)
        # size the window to what the content really needs (fonts get bigger with
        # Windows display scaling), so nothing is cut off when it opens
        root.update_idletasks()
        w = max(430, root.winfo_reqwidth())
        h = max(720, root.winfo_reqheight())
        root.geometry(f"{w}x{h}+20+20")
        root.minsize(400, max(560, h - 160))
        style_title_bar(root, self.BG)
        root.deiconify()
        self.pump()
        if UPDATE_CHECK_ON_START:
            root.after(1500, start_update_check)

    # ----- (re)building the window, themes -----
    def apply_styles(self):
        style = ttk.Style(self.root)
        style.configure("Vertical.TScrollbar", troughcolor=self.LOGBG,
                        background=self.SCROLL, bordercolor=self.LOGBG,
                        arrowcolor=self.SUB, lightcolor=self.SCROLL,
                        darkcolor=self.SCROLL, gripcount=0)
        style.map("Vertical.TScrollbar", background=[("active", self.SCROLL_HOVER)])

    def build_ui(self):
        self.apply_styles()
        self.build_header()
        self.build_now()
        self.build_stats()
        self.build_loot()
        self.build_footer()    # bottom-packed first, so these two never get cut off
        self.build_controls()
        self.build_log()       # the log takes whatever space is left

    def set_theme(self, name):
        apply_theme(name)
        save_stats()           # the theme lives in the settings part of the json
        self.rebuild_ui()

    def rebuild_ui(self):
        """Rebuild every widget in the new theme and put back what was on screen."""
        r = self.root
        self.disarm_reset()
        keep = {
            "title": self.now_title.cget("text"),
            "detail": self.now_detail.cget("text"),
            "stats": {k: w.cget("text") for k, w in self.stat_labels.items()},
            "loot": {k: w.cget("text") for k, w in self.loot_labels.items()},
            "topmost": bool(self.topmost.get()),
            "log": self.log_text.dump("1.0", "end-1c", text=True, tag=True),
        }
        for child in r.winfo_children():
            if child is not self.settings_win:      # the settings window is rebuilt by itself
                child.destroy()
        r.configure(bg=self.BG)
        self.build_ui()
        self.now_title.configure(text=keep["title"])
        self.now_detail.configure(text=keep["detail"])
        for k, text in keep["stats"].items():
            self.stat_labels[k].configure(text=text)
        for k, text in keep["loot"].items():
            self.loot_labels[k].configure(text=text)
        self.topmost.set(keep["topmost"])
        self.set_pill(self.pill_key)
        self.set_step(self.step_idx)
        t = self.log_text
        t.configure(state="normal")
        active = set()
        for kind, value, _index in keep["log"]:
            if kind == "tagon":
                active.add(value)
            elif kind == "tagoff":
                active.discard(value)
            elif kind == "text":
                t.insert("end", value, tuple(tag for tag in active if tag in
                                             ("ts", "err", "good", "info")))
        t.see("end")
        t.configure(state="disabled")
        r.update_idletasks()
        r.geometry(f"{max(r.winfo_width(), r.winfo_reqwidth())}x"
                   f"{max(r.winfo_height(), r.winfo_reqheight())}")
        style_title_bar(r, self.BG)

    # ----- layout helpers -----
    def card(self, title=None, expand=False, pad=(18, 14)):
        outer = tk.Frame(self.root, bg=self.CARD, highlightbackground=self.BORDER,
                         highlightthickness=self.CARD_BW)
        outer.pack(fill="both" if expand else "x", expand=expand, padx=16, pady=6)
        inner = tk.Frame(outer, bg=self.CARD)
        inner.pack(fill="both", expand=True, padx=pad[0], pady=pad[1])
        if title:
            tk.Label(inner, text=title, font=(App.FONT, 8, "bold"), fg=self.SUB,
                     bg=self.CARD, anchor="w").pack(fill="x", pady=(0, 10))
        return inner

    def build_header(self):
        head = tk.Frame(self.root, bg=self.BG)
        head.pack(fill="x", padx=18, pady=(16, 8))
        self.logo_img = None  # keep a reference, or tkinter drops the image
        try:
            logo_path = asset_path(LOGO_FILE)
            self.logo_img = tk.PhotoImage(file=logo_path)
        except (tk.TclError, OSError):
            pass
        if self.logo_img:
            tk.Label(head, image=self.logo_img, bg=self.BG, bd=0).pack(side="left")
        else:
            tk.Label(head, text="ymir", font=(App.FONT, 16, "bold"),
                     fg=self.TEXT, bg=self.BG).pack(side="left")
        self.pill = Pill(head, self.BG)
        self.pill.pack(side="right")

    def build_controls(self):
        row = tk.Frame(self.root, bg=self.BG)
        row.pack(side="bottom", fill="x", padx=16, pady=(5, 5))
        for col in range(3):
            row.columnconfigure(col, weight=1, uniform="tiles")

        self.btn_start = ActionTile(row, "Start", START_KEY.upper(), "play",
                                    self.ACCENT, lambda: start_macro(), self.BG)
        self.btn_pause = ActionTile(row, "Pause", PAUSE_KEY.upper(), "pause",
                                    "#f5b942", toggle_pause, self.BG)
        self.btn_stop = ActionTile(row, "Stop", QUIT_KEY.upper(), "stop",
                                   "#ef5350", request_stop, self.BG)
        for col, tile in enumerate((self.btn_start, self.btn_pause, self.btn_stop)):
            tile.grid(row=0, column=col, sticky="ew",
                      padx=(0 if col == 0 else 4, 0 if col == 2 else 4))

    def build_now(self):
        c = self.card()
        top = tk.Frame(c, bg=self.CARD)
        top.pack(fill="x")
        self.now_title = tk.Label(top, text="Not running", font=(App.FONT, 16, "bold"),
                                  fg=self.TEXT, bg=self.CARD, anchor="w")
        self.now_title.pack(side="left")
        self.step_count = tk.Label(top, text="", font=(App.FONT, 9),
                                   fg=self.SUB, bg=self.CARD)
        self.step_count.pack(side="right")
        self.now_detail = tk.Label(c, text=self.idle_hint(), font=(App.FONT, 10),
                                   fg=self.SUB, bg=self.CARD, anchor="w",
                                   justify="left", wraplength=360)
        self.now_detail.pack(fill="x", pady=(2, 12))
        self.stepper = Stepper(c, len(STEP_NAMES), self.CARD,
                               (self.STEP_DONE, self.ACCENT_SOFT, self.STEP_PENDING))
        self.stepper.pack(fill="x")

    def build_stats(self):
        c = self.card()
        row = tk.Frame(c, bg=self.CARD)
        row.pack(fill="x")
        self.stat_labels = {}
        items = (("missions", "Missions"), ("completed", "Completed"),
                 ("failed", "Failed"), ("mission_time", "Mission time"),
                 ("run_time", "Run time"))
        colors = {"completed": "#34d399", "failed": "#f87171"}
        for i, (key, caption) in enumerate(items):
            if i:
                tk.Frame(row, width=1, bg=self.BORDER).pack(side="left", fill="y", pady=2)
            box = tk.Frame(row, bg=self.CARD)
            box.pack(side="left", expand=True, fill="x")
            val = tk.Label(box, text="--:--" if key.endswith("_time") else "0",
                           font=(App.FONT, 16, "bold"),
                           fg=colors.get(key, self.TEXT), bg=self.CARD)
            val.pack()
            tk.Label(box, text=caption.upper(), font=(App.FONT, 7, "bold"), fg=self.SUB,
                     bg=self.CARD).pack(pady=(1, 0))
            self.stat_labels[key] = val

    LOOT_CHIPS = (("body", "Body", "#fbbf24"), ("defence", "Defence", "#60a5fa"),
                  ("offence", "Offence", "#f87171"), ("support", "Support", "#34d399"))

    def build_loot(self):
        c = self.card(pad=(10, 10))
        self.loot_labels = {}
        # columns: Scrolls | Fragments | divider | Body | Defence | Offence | Support
        cols = (("scrolls", "Scrolls", None), ("fragments", "Fragments", None),
                None,
                ("body", "Body", "#fbbf24"), ("defence", "Defence", "#60a5fa"),
                ("offence", "Offence", "#f87171"), ("support", "Support", "#34d399"))
        for n, item in enumerate(cols):
            if item is None:
                tk.Frame(c, width=1, bg=self.BORDER).grid(row=0, column=n,
                                                         sticky="ns", padx=4, pady=2)
                c.columnconfigure(n, weight=0)
                continue
            key, caption, color = item
            c.columnconfigure(n, weight=1, uniform="loot")
            box = tk.Frame(c, bg=self.CARD)
            box.grid(row=0, column=n, sticky="ew")
            val = tk.Label(box, text="0", font=(App.FONT, 15, "bold"),
                           fg=self.TEXT, bg=self.CARD)
            val.pack()
            cap = tk.Frame(box, bg=self.CARD)
            cap.pack()
            if color:
                tk.Label(cap, text="\u25cf", font=(App.FONT, 7), fg=color,
                         bg=self.CARD).pack(side="left", padx=(0, 4))
            tk.Label(cap, text=caption.upper(), font=(App.FONT, 7, "bold"), fg=self.SUB,
                     bg=self.CARD).pack(side="left")
            self.loot_labels[key] = val

    def on_reset_click(self, _e=None):
        """First click arms the button, a second click within 3s erases everything."""
        if self.reset_armed:
            self.disarm_reset()
            reset_stats()
        else:
            self.reset_armed = True
            self.reset_btn.configure(text="Click again to erase all stats", fg="#f87171")
            self.reset_job = self.root.after(3000, self.disarm_reset)

    def disarm_reset(self):
        if self.reset_job:
            try:
                self.root.after_cancel(self.reset_job)
            except tk.TclError:
                pass
            self.reset_job = None
        self.reset_armed = False
        self.reset_btn.configure(text="Reset stats", fg=self.SUB)

    def build_log(self):
        c = self.card("ACTIVITY", expand=True)
        wrap = tk.Frame(c, bg=self.LOGBG)
        wrap.pack(fill="both", expand=True)
        self.log_text = tk.Text(wrap, height=8, bg=self.LOGBG, fg=self.TEXT, bd=0,
                                highlightthickness=0, font=(App.MONO, 9),
                                wrap="word", state="disabled", padx=10, pady=8,
                                spacing1=1, spacing3=1)
        sb = ttk.Scrollbar(wrap, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.tag_configure("ts", foreground=self.LOG_TS)
        self.log_text.tag_configure("err", foreground="#f87171")
        self.log_text.tag_configure("good", foreground="#34d399")
        self.log_text.tag_configure("info", foreground=self.ACCENT_SOFT)

    def build_footer(self):
        foot = tk.Frame(self.root, bg=self.BG)
        foot.pack(side="bottom", fill="x", padx=18, pady=(4, 12))
        self.topmost = tk.BooleanVar(value=False)
        left = tk.Frame(foot, bg=self.BG)
        left.pack(side="left")
        sw = ToggleSwitch(left, self.topmost,
                          lambda: self.root.attributes("-topmost", self.topmost.get()),
                          parent_bg=self.BG)
        sw.pack(side="left")
        lbl = tk.Label(left, text="Always on top", font=(App.FONT, 9), fg=self.SUB,
                       bg=self.BG, cursor="hand2")
        lbl.pack(side="left", padx=(8, 0))
        lbl.bind("<Button-1>", sw.flip)
        tk.Label(left, text=VERSION, font=(App.FONT, 9), fg=self.SUB,
                 bg=self.BG).pack(side="left", padx=(14, 0))
        upd = tk.Label(left, text="\u21bb  Updates", font=(App.FONT, 9), fg=self.SUB,
                       bg=self.BG, cursor="hand2")
        upd.pack(side="left", padx=(14, 0))
        upd.bind("<Button-1>", lambda _e: start_update_check(manual=True))
        upd.bind("<Enter>", lambda _e: upd.configure(fg=self.TEXT))
        upd.bind("<Leave>", lambda _e: upd.configure(fg=self.SUB))

        self.reset_btn = tk.Label(foot, text="Reset stats", font=(App.FONT, 9),
                                  fg=self.SUB, bg=self.BG, cursor="hand2")
        self.reset_btn.pack(side="right")
        self.reset_btn.bind("<Button-1>", self.on_reset_click)
        self.reset_btn.bind("<Enter>", lambda _e: self.reset_btn.configure(
            fg="#f87171" if self.reset_armed else self.TEXT))
        self.reset_btn.bind("<Leave>", lambda _e: self.reset_btn.configure(
            fg="#f87171" if self.reset_armed else self.SUB))

        self.settings_btn = tk.Label(foot, text="\u2699  Settings", font=(App.FONT, 9),
                                     fg=self.SUB, bg=self.BG, cursor="hand2")
        self.settings_btn.pack(side="right", padx=(0, 16))
        self.settings_btn.bind("<Button-1>", lambda _e: self.open_settings())
        self.settings_btn.bind("<Enter>", lambda _e: self.settings_btn.configure(fg=self.TEXT))
        self.settings_btn.bind("<Leave>", lambda _e: self.settings_btn.configure(fg=self.SUB))

        # GitHub icon (opens the author's page); dim normally, bright on hover
        px = max(14, round(16 * max(1.0, self.root.winfo_fpixels("1i") / 96)))
        self.gh_dim, self.gh_hi = tinted_icon(self.SUB, px), tinted_icon(self.TEXT, px)
        if self.gh_dim is not None and self.gh_hi is not None:
            gh = tk.Label(foot, image=self.gh_dim, bg=self.BG, bd=0, cursor="hand2")
            gh.bind("<Enter>", lambda _e: gh.configure(image=self.gh_hi))
            gh.bind("<Leave>", lambda _e: gh.configure(image=self.gh_dim))
        else:
            gh = tk.Label(foot, text="GitHub", font=(App.FONT, 9), fg=self.SUB, bg=self.BG,
                          cursor="hand2")
            gh.bind("<Enter>", lambda _e: gh.configure(fg=self.TEXT))
            gh.bind("<Leave>", lambda _e: gh.configure(fg=self.SUB))
        gh.pack(side="right", padx=(0, 16))
        gh.bind("<Button-1>", lambda _e: webbrowser.open(GITHUB_URL))

    # ----- state updates -----
    def set_pill(self, key):
        self.pill_key = key
        text, bg, fg = self.PILLS[key]
        self.pill.update_pill(text, bg, fg)
        if key == "idle":
            self.btn_start.update_tile(enabled=True, active=False)
            self.btn_pause.update_tile(label="Pause", enabled=False, active=False)
            self.btn_stop.update_tile(enabled=False, active=False)
        elif key == "paused":
            self.btn_start.update_tile(enabled=False, active=False)
            self.btn_pause.update_tile(label="Resume", enabled=True, active=True)
            self.btn_stop.update_tile(enabled=True, active=False)
        else:  # waiting / running / retrying
            self.btn_start.update_tile(enabled=True, active=True)
            self.btn_pause.update_tile(label="Pause", enabled=True, active=False)
            self.btn_stop.update_tile(enabled=True, active=False)

    def set_step(self, idx):
        self.step_idx = idx
        self.stepper.set_index(idx)
        self.step_count.configure(
            text="" if idx < 0 else f"Step {idx + 1} of {len(STEP_NAMES)}")

    def add_log(self, msg):
        t = self.log_text
        t.configure(state="normal")
        t.insert("end", time.strftime("%H:%M:%S") + "   ", "ts")
        low = msg.lower()
        if low.startswith("error"):
            tag = "err"
        elif low.startswith(("mission started", "started")):
            tag = "good"
        elif low.startswith("result: completed"):
            tag = "good"
        elif low.startswith("result: failed"):
            tag = "err"
        elif low.startswith("loot:") and "nothing" not in low:
            tag = "good"
        elif low.startswith(("retry found", "hands off", "waiting")):
            tag = "info"
        else:
            tag = ""
        t.insert("end", msg + "\n", tag)
        lines = int(t.index("end-1c").split(".")[0])
        if lines > 300:
            t.delete("1.0", f"{lines - 300}.0")
        t.see("end")
        t.configure(state="disabled")

    def handle(self, e):
        kind = e[0]
        if kind == "log":
            self.add_log(e[1])
        elif kind == "now":
            self.now_title.configure(text=e[1])
            self.now_detail.configure(text=e[2])
        elif kind == "detail":
            self.now_detail.configure(text=e[1])
        elif kind == "step":
            self.set_step(e[1])
        elif kind == "status":
            self.set_pill(e[1])
        elif kind == "stats":
            self.stat_labels["missions"].configure(text=str(e[1]))
            self.stat_labels["completed"].configure(text=str(e[4]["completed"]))
            self.stat_labels["failed"].configure(text=str(e[4]["failed"]))
            counts = e[3]
            self.loot_labels["scrolls"].configure(text=str(counts["scroll"]))
            self.loot_labels["fragments"].configure(
                text=str(sum(counts[k] for k in FRAGMENT_KINDS)))
            for kind in FRAGMENT_KINDS:
                self.loot_labels[kind].configure(text=str(counts[kind]))
        elif kind == "captured":
            if self.settings_win:
                self.settings_win.on_captured(e[1], e[2])
        elif kind == "settings_msg":
            if self.settings_win:
                self.settings_win.say(e[1], error=e[2], good=e[3])
        elif kind == "update_result":
            self.on_update_result(e[1], e[2], e[3])
        elif kind == "update_ready":
            self.on_close()          # the .bat swaps the files and starts the new version
        elif kind == "mission_started":
            self.mission_t0 = time.time()
        elif kind == "mission_ended":
            if self.mission_t0:
                self.mission_last = time.time() - self.mission_t0
            self.mission_t0 = None
        elif kind == "started":
            self.run_t0 = time.time()
            self.mission_t0 = None
            self.mission_last = None
            self.set_pill("waiting")
        elif kind == "done":
            self.run_t0 = None
            self.mission_t0 = None
            self.set_pill("idle")
            self.set_step(-1)
            self.now_title.configure(text="Stopped")
            self.now_detail.configure(text=self.idle_hint())

    def pump(self):
        try:
            while True:
                self.handle(ev.get_nowait())
        except queue.Empty:
            pass
        if self.run_t0:
            self.stat_labels["run_time"].configure(text=fmt_time(time.time() - self.run_t0))
        if self.mission_t0:
            self.stat_labels["mission_time"].configure(
                text=fmt_time(time.time() - self.mission_t0))
        elif self.mission_last is not None:
            self.stat_labels["mission_time"].configure(text=fmt_time(self.mission_last))
        self.root.after(100, self.pump)

    def on_update_result(self, manual, info, error):
        _update["busy"] = False
        if error:
            if manual:
                log(f"Error: update check failed - {error}")
            return
        if not info or parse_version(info["tag"]) <= parse_version(VERSION):
            if manual:
                log(f"You are on the latest version ({VERSION})")
            return
        log(f"Update available: {info['tag']} (you have {VERSION})")
        if running():
            log("Stop the macro first, then click Updates to install it")
            return
        if not getattr(sys, "frozen", False) or not info["url"]:
            # plain .py (or a release without an .exe): just open the release page
            if messagebox.askyesno("Update available",
                                   f"{info['tag']} is available (you have {VERSION}).\n\n"
                                   "Open the release page?", parent=self.root):
                webbrowser.open(info["page"])
            return
        if messagebox.askyesno("Update available",
                               f"{info['tag']} is available (you have {VERSION}).\n\n"
                               "Download it and restart the macro now?", parent=self.root):
            _update["busy"] = True
            install_update(info)

    def open_settings(self):
        if self.settings_win is not None:
            self.settings_win.deiconify()
            self.settings_win.attributes("-topmost", True)
            self.settings_win.lift()
            self.settings_win.focus_force()
            return
        self.settings_win = SettingsWindow(self)

    def refresh_hotkeys(self):
        """Hotkeys were changed in Settings: update the tile badges and the hint."""
        self.btn_start.update_tile(key_text=START_KEY.upper())
        self.btn_pause.update_tile(key_text=PAUSE_KEY.upper())
        self.btn_stop.update_tile(key_text=QUIT_KEY.upper())
        if not running():
            self.now_detail.configure(text=self.idle_hint())

    def on_close(self):
        if self.settings_win is not None:
            self.settings_win.close()
        request_stop()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        self.root.destroy()


class KeyButton(tk.Label):
    """Clickable key badge: shows the current key, or 'Press a key...' while capturing."""
    NORMAL, HOVER, CAPTURE = "#1a1e29", "#212637", "#16254a"

    def __init__(self, parent, key, on_click):
        super().__init__(parent, width=14, font=(App.FONT, 9, "bold"), bd=0, pady=5,
                         cursor="hand2", highlightthickness=1)
        self.capturing = False
        self.show_key(key)
        self.bind("<Button-1>", lambda _e: on_click())
        self.bind("<Enter>", lambda _e: None if self.capturing else self.configure(bg=self.HOVER))
        self.bind("<Leave>", lambda _e: None if self.capturing else self.configure(bg=self.NORMAL))

    def show_key(self, key):
        self.capturing = False
        self.configure(text=key.upper(), fg=App.TEXT, bg=self.NORMAL,
                       highlightbackground=App.FIELD_EDGE, highlightcolor=App.FIELD_EDGE)

    def show_capturing(self):
        self.capturing = True
        self.configure(text="Press a key...", fg=App.ACCENT_TEXT, bg=self.CAPTURE,
                       highlightbackground=App.ACCENT_LINE, highlightcolor=App.ACCENT_LINE)


class ModernDropdown(tk.Frame):
    """Flat dark dropdown. Every entry shows a round letter badge, its name and an
    optional WIP tag. items = [(key, label, (letter, badge_bg, letter_fg), is_wip), ...]"""
    BG, HOVER, EDGE = "#1a1e29", "#232a3d", "#2a3042"
    TEXT, SUB, ACCENT = "#e6e9f2", "#7a8398", "#3b82f6"
    WIP_BG, WIP_FG = "#2e2410", "#fbbf24"

    def __init__(self, parent, items, value, on_change):
        super().__init__(parent, bg=self.BG, cursor="hand2", highlightthickness=1,
                         highlightbackground=self.EDGE, highlightcolor=self.EDGE)
        self.items = {it[0]: it for it in items}
        self.order = [it[0] for it in items]
        self.value = value if value in self.items else self.order[0]
        self.on_change = on_change
        self.popup = None
        self.row = None
        self.render_trigger()
        self.bind("<Destroy>", lambda e: self.close_popup() if e.widget is self else None)

    # ----- pieces -----
    def make_badge(self, parent, spec, bg):
        letter, color, fg = spec
        c = tk.Canvas(parent, width=22, height=22, bg=bg, highlightthickness=0, bd=0)
        c.create_oval(1, 1, 21, 21, fill=color, outline="")
        c.create_text(11, 11, text=letter, fill=fg, font=(App.FONT, 9, "bold"))
        return c

    def make_row(self, parent, key, bg, trailing):
        """One entry laid out as: badge  name  [WIP]  ........  trailing symbol."""
        _key, label, badge, wip = self.items[key]
        row = tk.Frame(parent, bg=bg, cursor="hand2")
        parts = [self.make_badge(row, badge, bg)]
        parts[0].pack(side="left", padx=(12, 10), pady=9)
        name = tk.Label(row, text=label, font=(App.FONT, 10), fg=self.TEXT, bg=bg)
        name.pack(side="left")
        parts.append(name)
        if wip:
            tag = tk.Label(row, text="WIP", font=(App.FONT, 7, "bold"), fg=self.WIP_FG,
                           bg=self.WIP_BG, padx=6, pady=1)
            tag.keep_bg = True
            tag.pack(side="left", padx=(8, 0))
            parts.append(tag)
        sym = tk.Label(row, text=trailing, font=(App.FONT, 9), bg=bg,
                       fg=self.ACCENT if trailing == "\u2713" else self.SUB)
        sym.pack(side="right", padx=(0, 14))
        parts.append(sym)
        return row, parts

    @staticmethod
    def paint(row, bg):
        row.configure(bg=bg)
        for w in row.winfo_children():
            if not getattr(w, "keep_bg", False):
                w.configure(bg=bg)

    # ----- closed state -----
    def render_trigger(self):
        if self.row is not None:
            self.row.destroy()
        self.row, parts = self.make_row(self, self.value, self.BG, "\u25be")
        self.row.pack(fill="x")
        for w in [self, self.row] + parts:
            w.bind("<Button-1>", lambda _e: self.toggle())
            w.bind("<Enter>", lambda _e: self.hover(True))
            w.bind("<Leave>", lambda _e: self.hover(False))

    def hover(self, on):
        edge = self.ACCENT if (on or self.popup) else self.EDGE
        self.configure(highlightbackground=edge, highlightcolor=edge)

    # ----- open state -----
    def toggle(self):
        if self.popup is not None:
            self.close_popup()
            return
        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 4
        pop = tk.Toplevel(self)
        pop.withdraw()                         # hidden until it is sized + placed (no flicker)
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)      # stays above the always-on-top settings window
        pop.configure(bg=self.EDGE)
        inner = tk.Frame(pop, bg=self.BG)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        for key in self.order:
            selected = key == self.value
            row, parts = self.make_row(inner, key, self.BG, "\u2713" if selected else "")
            row.pack(fill="x")
            for w in [row] + parts:
                w.bind("<Button-1>", lambda _e, k=key: self.pick(k))
                w.bind("<Enter>", lambda _e, r=row: self.paint(r, self.HOVER))
                w.bind("<Leave>", lambda _e, r=row: self.paint(r, self.BG))
        pop.update_idletasks()
        pop.geometry(f"{self.winfo_width()}x{pop.winfo_reqheight()}+{x}+{y}")
        pop.bind("<Escape>", lambda _e: self.close_popup())
        pop.bind("<FocusOut>", lambda _e: self.after(60, self.check_focus))
        self.popup = pop
        self.hover(True)
        pop.deiconify()
        pop.lift()
        pop.focus_force()

    def check_focus(self):
        """Close when the user clicks anywhere outside the list."""
        pop = self.popup
        if pop is None:
            return
        try:
            f = pop.focus_get()
        except KeyError:
            f = None
        if f is None or not str(f).startswith(str(pop)):
            self.close_popup()

    def close_popup(self):
        pop, self.popup = self.popup, None
        if pop is not None:
            try:
                pop.destroy()
            except tk.TclError:
                pass
        try:
            self.hover(False)
        except tk.TclError:
            pass

    def pick(self, key):
        self.close_popup()
        if key != self.value:
            self.value = key
            self.render_trigger()
            self.on_change(key)


class ThemeCard(tk.Canvas):
    """Clickable preview of one theme: a tiny mock of the window in that theme's look."""
    W, H = 170, 96

    def __init__(self, parent, name, selected, on_click, parent_bg):
        super().__init__(parent, width=self.W, height=self.H, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.name, self.selected, self.on_click = name, selected, on_click
        self.P = build_palette(name)
        self.hover = False
        self.bind("<Enter>", lambda _e: self.set_hover(True))
        self.bind("<Leave>", lambda _e: self.set_hover(False))
        self.bind("<Button-1>", lambda _e: self.on_click(self.name))
        self.draw()

    def set_hover(self, on):
        self.hover = on
        self.draw()

    def draw(self):
        P, W, H = self.P, self.W, self.H
        self.delete("all")
        if self.selected:
            line, lw = P["ACCENT"], 2
        elif self.hover:
            line, lw = P["FIELD_EDGE_HOVER"], 2
        else:
            line, lw = P["FIELD_EDGE"], 1
        rounded_rect(self, 1, 1, W - 1, H - 1, min(P["R_TILE"] + 2, 14),
                     fill=P["BG"], outline=line, width=lw)
        cr = min(P["R_TILE"] // 2, 6)
        # mini card: title bars + a status pill
        rounded_rect(self, 10, 10, W - 10, 40, cr, fill=P["CARD"],
                     outline=P["BORDER"] if P["CARD_BW"] else "")
        rounded_rect(self, 18, 18, 66, 24, 2, fill=P["TEXT"], outline="")
        rounded_rect(self, 18, 28, 48, 32, 2, fill=P["SUB"], outline="")
        pill_r = 7 if P["R_PILL"] is None else min(P["R_PILL"], 7)
        rounded_rect(self, W - 54, 18, W - 18, 32, pill_r, fill=P["ACCENT_BG"], outline="")
        self.create_oval(W - 48, 22, W - 42, 28, fill=P["ACCENT"], outline="")
        # three mini tiles, the first one "active"
        tw = (W - 20 - 12) / 3
        for i in range(3):
            x1 = 10 + i * (tw + 6)
            if i == 0:
                rounded_rect(self, x1, 48, x1 + tw, 64, cr, fill=P["ACCENT_BG"],
                             outline=P["ACCENT_LINE"], width=1)
            else:
                rounded_rect(self, x1, 48, x1 + tw, 64, cr, fill=P["FIELD"],
                             outline=P["FIELD_EDGE"], width=1)
        # name (in the theme's own font) + a tick when selected
        self.create_text(12, H - 16, text=self.name, fill=P["TEXT"], anchor="w",
                         font=(P["FONT"], 9, "bold"))
        if self.selected:
            self.create_oval(W - 25, H - 23, W - 11, H - 9, fill=P["ACCENT"], outline="")
            self.create_text(W - 18, H - 16, text="\u2713", fill="#ffffff",
                             font=("Segoe UI", 8, "bold"))
        else:
            self.create_oval(W - 20, H - 20, W - 12, H - 12, fill=P["ACCENT"], outline="")


class SettingsWindow(tk.Toplevel):
    """Settings: Keybinds / Discord / Configs / Themes. Every change is saved right away
    (into the same json as the stats)."""
    TABS = (("keys", "Keybinds"), ("discord", "Discord"), ("family", "Configs"),
            ("themes", "Themes"))
    UID_HELP = ("Discord > Settings > Advanced > Developer Mode on, then right-click "
                "your name > Copy User ID.")

    def __init__(self, app):
        super().__init__(app.root)
        self.withdraw()     # build everything hidden, then show it once - no flicker
        self.app = app
        self.capturing = None       # bind id waiting for a key press
        self.capture_hook = None
        self.save_job = None
        self.say_job = None
        self.key_buttons = {}
        self.pages = {}
        self.tab_widgets = {}

        self.title("ymir - settings")
        try:
            self.iconbitmap(asset_path(ICON_FILE))
        except (tk.TclError, OSError):
            pass
        self.resizable(False, False)
        self.attributes("-topmost", True)    # settings always stays above everything
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.build_ui("keys")
        self.update_idletasks()
        x, y = app.root.winfo_x() + 40, app.root.winfo_y() + 40
        self.geometry(f"440x{self.winfo_reqheight()}+{x}+{y}")
        style_title_bar(self, App.BG)
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()

    def build_ui(self, tab):
        """(Re)build every widget - on open, and again when the theme changes."""
        self.cancel_capture()
        for child in self.winfo_children():
            child.destroy()
        self.key_buttons, self.pages, self.tab_widgets = {}, {}, {}
        self.configure(bg=App.BG)
        self.build_tab_bar()
        body = tk.Frame(self, bg=App.BG)
        body.pack(fill="both", expand=True, padx=18)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        for key, _text in self.TABS:    # all pages sit on top of each other, one is raised
            page = tk.Frame(body, bg=App.BG)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page
        self.build_keys(self.pages["keys"])
        self.build_discord(self.pages["discord"])
        self.build_family(self.pages["family"])
        self.build_themes(self.pages["themes"])

        self.status = tk.Label(self, text="", font=(App.FONT, 9), fg=App.SUB, bg=App.BG,
                               anchor="w", wraplength=390, justify="left")
        self.status.pack(fill="x", padx=22, pady=(4, 14))
        self.show_tab(tab)

    def retheme(self, tab):
        """The theme changed: rebuild this window in the new look (same place, same size)."""
        self.commit()
        self.build_ui(tab)
        self.update_idletasks()
        self.geometry(f"{max(440, self.winfo_reqwidth())}x{self.winfo_reqheight()}")
        style_title_bar(self, App.BG)

    # ----- look -----
    def setup_styles(self):
        pass    # nothing to style: the dropdown and theme cards are custom widgets

    def card(self, parent, title, note=None):
        outer = tk.Frame(parent, bg=App.CARD, highlightbackground=App.BORDER,
                         highlightthickness=App.CARD_BW)
        outer.pack(fill="x", pady=6)
        inner = tk.Frame(outer, bg=App.CARD)
        inner.pack(fill="x", padx=16, pady=14)
        tk.Label(inner, text=title, font=(App.FONT, 8, "bold"), fg=App.SUB, bg=App.CARD,
                 anchor="w").pack(fill="x")
        if note:
            tk.Label(inner, text=note, font=(App.FONT, 9), fg=App.SUB, bg=App.CARD,
                     anchor="w", justify="left", wraplength=370).pack(fill="x", pady=(2, 0))
        tk.Frame(inner, height=8, bg=App.CARD).pack()
        return inner

    def check(self, parent, text, var, command):
        return switch_row(parent, text, var, command, App.CARD, App.TEXT)

    def entry(self, parent, var, show=None):
        e = tk.Entry(parent, textvariable=var, show=show, font=(App.FONT, 10),
                     bg=App.LOGBG, fg=App.TEXT, insertbackground=App.TEXT, relief="flat",
                     disabledbackground=App.DIS_FILL, disabledforeground=App.DIS_TEXT,
                     highlightthickness=1, highlightbackground=App.BORDER,
                     highlightcolor=App.ACCENT)
        e.pack(fill="x", ipady=5)
        return e

    def flat_button(self, parent, text, command):
        b = tk.Label(parent, text=text, font=(App.FONT, 9, "bold"), fg=App.ACCENT_TEXT,
                     bg=App.ACCENT_BG, padx=12, pady=5, cursor="hand2")
        b.bind("<Button-1>", lambda _e: command())
        b.bind("<Enter>", lambda _e: b.configure(bg=App.ACCENT_BG_HOVER))
        b.bind("<Leave>", lambda _e: b.configure(bg=App.ACCENT_BG))
        return b

    def hint(self, parent, text="", color=None):
        lbl = tk.Label(parent, text=text, font=(App.FONT, 8), fg=color or App.SUB,
                       bg=App.CARD, anchor="w", justify="left", wraplength=370)
        lbl.pack(fill="x", pady=(4, 0))
        return lbl

    # ----- tabs -----
    def build_tab_bar(self):
        bar = tk.Frame(self, bg=App.BG)
        bar.pack(fill="x", padx=22, pady=(16, 10))
        for key, text in self.TABS:
            cell = tk.Frame(bar, bg=App.BG, cursor="hand2")
            cell.pack(side="left", padx=(0, 24))
            lbl = tk.Label(cell, text=text, font=(App.FONT, 11, "bold"), fg=App.SUB,
                           bg=App.BG, cursor="hand2")
            lbl.pack()
            line = tk.Frame(cell, height=2, bg=App.BG)
            line.pack(fill="x", pady=(3, 0))
            for w in (cell, lbl):
                w.bind("<Button-1>", lambda _e, k=key: self.show_tab(k))
            self.tab_widgets[key] = (lbl, line)

    def show_tab(self, key):
        self.cancel_capture()
        for k, (lbl, line) in self.tab_widgets.items():
            on = k == key
            lbl.configure(fg=App.TEXT if on else App.SUB)
            line.configure(bg=App.ACCENT if on else App.BG)
        self.pages[key].tkraise()
        self.say("")

    # ----- keybinds tab -----
    def build_keys(self, page):
        c = self.card(page, "HOTKEYS", "Work even while Roblox is focused.")
        for bind_id, (label, _default) in HOTKEY_BINDS.items():
            self.key_row(c, bind_id, label)
        c = self.card(page, "IN-GAME KEYS",
                      "Set these to match your keybinds in Roblox.")
        for bind_id, (label, _default) in GAME_BINDS.items():
            self.key_row(c, bind_id, label)
        reset = tk.Label(c, text="Reset all keybinds to default", font=(App.FONT, 9),
                         fg=App.SUB, bg=App.CARD, cursor="hand2")
        reset.pack(anchor="e", pady=(8, 0))
        reset.bind("<Button-1>", lambda _e: self.reset_keybinds())
        reset.bind("<Enter>", lambda _e: reset.configure(fg=App.TEXT))
        reset.bind("<Leave>", lambda _e: reset.configure(fg=App.SUB))

    def key_row(self, parent, bind_id, label):
        row = tk.Frame(parent, bg=App.CARD)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, font=(App.FONT, 10), fg=App.TEXT,
                 bg=App.CARD).pack(side="left")
        btn = KeyButton(row, settings["keybinds"][bind_id],
                        lambda b=bind_id: self.start_capture(b))
        btn.pack(side="right")
        self.key_buttons[bind_id] = btn

    def refresh_key_buttons(self):
        for bind_id, btn in self.key_buttons.items():
            btn.show_key(settings["keybinds"][bind_id])

    def start_capture(self, bind_id):
        if running():
            self.say("Stop the macro before changing keybinds.", error=True)
            return
        self.cancel_capture()
        self.capturing = bind_id
        self.key_buttons[bind_id].show_capturing()
        unregister_hotkeys()    # so pressing e.g. F8 here doesn't start the macro
        self.capture_hook = keyboard.on_press(
            lambda e: ev.put(("captured", e.name, bool(getattr(e, "is_keypad", False)))))
        self.say(f"Press the new key for {BIND_LABELS[bind_id]} (Esc to cancel)")

    def cancel_capture(self):
        if self.capturing is None:
            return
        if self.capture_hook is not None:
            try:
                keyboard.unhook(self.capture_hook)
            except (KeyError, ValueError):
                pass
            self.capture_hook = None
        self.capturing = None
        self.refresh_key_buttons()
        register_hotkeys()

    def on_captured(self, name, keypad):
        """A key was pressed while a button was waiting for one."""
        bind_id = self.capturing
        if bind_id is None:
            return
        self.cancel_capture()
        name = name.lower()
        if name == "esc":
            self.say("Cancelled")
            return
        if bind_id in GAME_BINDS:
            key = to_game_key(name, keypad)
            if key is None:
                self.say(f"'{name}' can't be pressed by the macro - try another key.",
                         error=True)
                return
        else:
            key = name
        for other, value in settings["keybinds"].items():
            if other != bind_id and value == key:
                self.say(f"{key.upper()} is already used by {BIND_LABELS[other]}.", error=True)
                return
        settings["keybinds"][bind_id] = key
        self.keybinds_changed()
        self.say(f"{BIND_LABELS[bind_id]} = {key.upper()}", good=True)

    def reset_keybinds(self):
        if running():
            self.say("Stop the macro before changing keybinds.", error=True)
            return
        self.cancel_capture()
        settings["keybinds"] = dict(DEFAULT_KEYBINDS)
        self.keybinds_changed()
        self.say("Keybinds reset to default", good=True)

    def keybinds_changed(self):
        apply_settings()
        register_hotkeys()
        save_stats()
        self.refresh_key_buttons()
        self.app.refresh_hotkeys()

    # ----- discord tab -----
    def build_discord(self, page):
        wh = settings["webhook"]
        self.v_url = tk.StringVar(value=wh["url"])
        self.v_mention = tk.BooleanVar(value=wh["mention"])
        self.v_uid = tk.StringVar(value=wh["user_id"])
        self.v_hourly = tk.BooleanVar(value=wh["hourly_graph"])
        self.v_hours = tk.StringVar(value=str(wh["graph_hours"]))
        self.v_mission = tk.BooleanVar(value=wh["notify_mission"])
        self.v_error = tk.BooleanVar(value=wh["notify_error"])

        c = self.card(page, "WEBHOOK", "Optional. Leave the URL empty to keep Discord off.")
        self.url_entry = self.entry(c, self.v_url, show="\u2022")
        self.hint_url = self.hint(c, "", "#f87171")
        row = tk.Frame(c, bg=App.CARD)
        row.pack(fill="x", pady=(6, 0))
        self.v_show = tk.BooleanVar(value=False)
        show = tk.Frame(row, bg=App.CARD)
        show.pack(side="left")
        sw = ToggleSwitch(show, self.v_show, self.toggle_show, parent_bg=App.CARD)
        sw.pack(side="left")
        lbl = tk.Label(show, text="Show URL", font=(App.FONT, 9), fg=App.SUB, bg=App.CARD,
                       cursor="hand2")
        lbl.pack(side="left", padx=(8, 0))
        lbl.bind("<Button-1>", sw.flip)
        self.flat_button(row, "Send test message", self.test_webhook).pack(side="right")

        c = self.card(page, "MESSAGES")
        self.check(c, "Post my stats (embed) after every mission", self.v_mission,
                   self.on_toggle)
        self.check(c, "Message me when the macro hits an error", self.v_error, self.on_toggle)
        self.check(c, "Mention me in error messages", self.v_mention, self.on_toggle)
        row = tk.Frame(c, bg=App.CARD)
        row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text="User ID", font=(App.FONT, 10), fg=App.TEXT,
                 bg=App.CARD).pack(side="left", padx=(0, 10))
        inner = tk.Frame(row, bg=App.CARD)
        inner.pack(side="left", fill="x", expand=True)
        self.uid_entry = self.entry(inner, self.v_uid)
        self.hint_uid = self.hint(c, self.UID_HELP)

        c = self.card(page, "STATS GRAPH")
        self.check(c, "Send a stats graph on an interval", self.v_hourly, self.on_toggle)
        row = tk.Frame(c, bg=App.CARD)
        row.pack(fill="x", pady=(4, 0))
        tk.Label(row, text="Every", font=(App.FONT, 10), fg=App.TEXT,
                 bg=App.CARD).pack(side="left", padx=(0, 8))
        self.hours_spin = tk.Spinbox(row, from_=1, to=MAX_GRAPH_HOURS, width=4,
                                     textvariable=self.v_hours, command=self.save_soon,
                                     font=(App.FONT, 10), justify="center", bg=App.LOGBG,
                                     fg=App.TEXT, insertbackground=App.TEXT,
                                     buttonbackground=App.FIELD, relief="flat",
                                     highlightthickness=1, highlightbackground=App.BORDER,
                                     highlightcolor=App.ACCENT)
        self.hours_spin.pack(side="left", ipady=3)
        tk.Label(row, text="hour(s)", font=(App.FONT, 10), fg=App.TEXT,
                 bg=App.CARD).pack(side="left", padx=(8, 0))
        self.flat_button(row, "Send test graph", self.test_graph).pack(side="right")
        self.hint(c, "Sent while the macro is running. It never pings you.")

        for var in (self.v_url, self.v_uid, self.v_hours):
            var.trace_add("write", lambda *_: self.save_soon())
        self.update_dependents()

    def toggle_show(self):
        self.url_entry.configure(show="" if self.v_show.get() else "\u2022")

    def update_dependents(self):
        self.uid_entry.configure(state="normal" if self.v_mention.get() else "disabled")

    def on_toggle(self):
        self.update_dependents()
        self.commit()

    def test_webhook(self):
        self.commit()
        if not webhook_url():
            self.say("Paste a valid webhook URL first.", error=True)
            return
        self.say("Sending test message...")

        def work():
            ok, msg = post_webhook("Test message from ymir - the webhook works.")
            ev.put(("settings_msg", "Test message sent" if ok else msg, not ok, ok))
        threading.Thread(target=work, daemon=True).start()

    def test_graph(self):
        self.commit()
        if not webhook_url():
            self.say("Paste a valid webhook URL first.", error=True)
            return
        self.say("Building the graph...")

        def work():
            try:
                ok, msg = send_stats_graph("Test graph", partial=True)
            except Exception as e:  # noqa: BLE001
                ok, msg = False, f"Could not build the graph: {type(e).__name__}: {e}"
            ev.put(("settings_msg", "Test graph sent" if ok else msg, not ok, ok))
        threading.Thread(target=work, daemon=True).start()

    # ----- configs tab -----
    def build_family(self, page):
        # section 1: movements (only the initial dash sequence, before ability 4 is used)
        self.v_movement = tk.StringVar(value=settings["movement"])
        m = self.card(page, "MOVEMENTS",
                      "Only changes the initial dash sequence, before ability 4 is used.")
        m_items = [(f, f, MOVEMENT_BADGES[f], f in MOVEMENT_WIP) for f in MOVEMENTS]
        self.movement_dd = ModernDropdown(m, m_items, settings["movement"],
                                          self.on_movement_pick)
        self.movement_dd.pack(fill="x")

        # section 2: abilities (the family)
        self.v_family = tk.StringVar(value=settings["family"])
        c = self.card(page, "ABILITIES")
        items = [(f, FAMILY_LABELS[f], FAMILY_BADGES[f], f in FAMILY_WIP) for f in FAMILIES]
        self.family_dd = ModernDropdown(c, items, settings["family"], self.on_family_pick)
        self.family_dd.pack(fill="x")
        tk.Label(c, text="Fritz and yeager not recommended", font=(App.FONT, 8),
                 fg=App.SUB, bg=App.CARD, anchor="w").pack(fill="x", pady=(8, 0))

        # section 3: graphics
        self.v_lowq = tk.BooleanVar(value=settings["low_quality"])
        g = self.card(page, "GRAPHICS",
                      "Turn this on if you play on low graphics. It uses ONLY the pictures in "
                      "image/low quality fix to find the retry button, the loot and the "
                      "mission start. Body fragments are NOT checked in this mode (no fix "
                      "for the false detections yet).")
        self.check(g, "Low quality mode", self.v_lowq, self.on_lowq_toggle)

    def on_lowq_toggle(self):
        if running():
            self.v_lowq.set(not self.v_lowq.get())      # put the switch back
            self.say("Stop the macro before changing low quality mode.", error=True)
            return
        settings["low_quality"] = bool(self.v_lowq.get())
        save_stats()
        self.say("Low quality mode " + ("on" if settings["low_quality"] else "off"), good=True)

    def on_movement_pick(self, key):
        self.v_movement.set(key)
        self.commit()

    def on_family_pick(self, key):
        self.v_family.set(key)
        self.commit()

    # ----- themes tab -----
    def build_themes(self, page):
        c = self.card(page, "THEME", "Pick a look - the whole app updates instantly.")
        grid = tk.Frame(c, bg=App.CARD)
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        for i, name in enumerate(THEMES):
            card = ThemeCard(grid, name, name == settings["theme"], self.on_theme_pick,
                             App.CARD)
            card.grid(row=i // 2, column=i % 2, padx=4, pady=4)

    def on_theme_pick(self, name):
        if name == settings["theme"]:
            return
        self.app.set_theme(name)                           # main window rebuilds right now
        self.after(10, lambda: self.retheme("themes"))     # then this window follows

    # ----- saving -----
    def save_soon(self):
        """Typing in a text box saves a moment after the last key."""
        if self.save_job:
            self.after_cancel(self.save_job)
        self.save_job = self.after(500, self.commit)

    def commit(self):
        if self.save_job:
            try:
                self.after_cancel(self.save_job)
            except tk.TclError:
                pass
            self.save_job = None
        wh = settings["webhook"]
        wh["url"] = self.v_url.get().strip()
        wh["mention"] = bool(self.v_mention.get())
        wh["user_id"] = self.v_uid.get().strip()
        wh["hourly_graph"] = bool(self.v_hourly.get())
        wh["notify_mission"] = bool(self.v_mission.get())
        try:
            hours = int(self.v_hours.get())
        except ValueError:
            hours = wh["graph_hours"]      # box is empty / being typed: keep the old value
        wh["graph_hours"] = min(MAX_GRAPH_HOURS, max(1, hours))
        wh["notify_error"] = bool(self.v_error.get())
        fam = self.v_family.get()
        settings["family"] = fam if fam in FAMILIES else DEFAULT_FAMILY
        mov = self.v_movement.get()
        settings["movement"] = mov if mov in MOVEMENTS else DEFAULT_MOVEMENT
        save_stats()
        # gentle warnings (it still saves what was typed)
        bad_url = bool(wh["url"]) and not webhook_url()
        self.hint_url.configure(
            text="That doesn't look like a Discord webhook URL." if bad_url else "")
        bad_uid = wh["mention"] and not wh["user_id"].isdigit()
        self.hint_uid.configure(
            text="The user ID must be numbers only." if bad_uid else
                 self.UID_HELP,
            fg="#f87171" if bad_uid else App.SUB)

    def say(self, msg, error=False, good=False):
        self.status.configure(text=msg,
                              fg="#f87171" if error else "#34d399" if good else App.SUB)
        if self.say_job:
            self.after_cancel(self.say_job)
            self.say_job = None
        if msg and not msg.startswith("Press the new key"):
            self.say_job = self.after(5000, lambda: self.status.configure(text=""))

    def close(self):
        self.cancel_capture()
        self.commit()
        self.app.settings_win = None
        self.destroy()


def apply_theme(name):
    """Make `name` the live theme: sets the colours / radii / font every widget reads.
    (Widgets built afterwards use it; App.rebuild_ui() rebuilds the visible ones.)"""
    if name not in THEMES:
        name = DEFAULT_THEME
    P = build_palette(name)
    settings["theme"] = name
    for key, value in P.items():
        setattr(App, key, value)
    ActionTile.LOOK = {   # (fill, outline, outline_width, label_fg, badge_outline, badge_fg)
        "normal":   (P["FIELD"], P["FIELD_EDGE"], 1, P["TEXT"], P["FIELD_EDGE_HOVER"], P["BADGE_FG"]),
        "hover":    (P["FIELD_HOVER"], P["FIELD_EDGE_HOVER"], 1, "#ffffff", P["BADGE_HOVER"],
                     P["BADGE_FG_HOVER"]),
        "active":   (P["ACCENT_BG"], P["ACCENT_LINE"], 2, "#ffffff", P["ACCENT_BADGE"],
                     P["ACCENT_TEXT"]),
        "disabled": (P["DIS_FILL"], P["DIS_EDGE"], 1, P["DIS_TEXT"], P["DIS_BADGE"], P["DIS_TEXT"]),
    }
    ActionTile.OFF_ICON = P["DIS_ICON"]
    ToggleSwitch.ON, ToggleSwitch.OFF, ToggleSwitch.KNOB = P["ACCENT"], P["SWITCH_OFF"], P["KNOB"]
    KeyButton.NORMAL, KeyButton.HOVER, KeyButton.CAPTURE = (
        P["FIELD"], P["FIELD_HOVER"], P["ACCENT_BG"])
    ModernDropdown.BG, ModernDropdown.HOVER, ModernDropdown.EDGE = (
        P["FIELD"], P["FIELD_HOVER"], P["FIELD_EDGE"])
    ModernDropdown.TEXT, ModernDropdown.SUB, ModernDropdown.ACCENT = (
        P["TEXT"], P["SUB"], P["ACCENT"])
    ModernDropdown.WIP_BG, ModernDropdown.WIP_FG = P["PILLS"]["waiting"][1:]
    return name


def main():
    load_stats()          # stats + settings (saved keybinds, webhook, family)
    apply_settings()
    register_hotkeys()
    root = tk.Tk()
    App(root)
    push_stats(save=False)  # show the saved numbers right away
    root.mainloop()


if __name__ == "__main__":
    main()
