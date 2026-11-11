import atexit
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
VERSION = "v1.3.0"        # release version tag
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
ALT_RETRY_FILE = "alt_retry_button.png"   # optional: a picture of the WHOLE retry button, "RETRY (0/1)".
                                          # Only used as an extra check when retry_text.png finds nothing.
ALT_RETRY_THRESHOLD = 0.85   # the alt picture has the button colour around the word, so it is a bit looser
ALT_RETRY_WORD_COLS = (24, 100)   # the RETRY word only (x range inside the alt picture), because the
                                  # "(0/1)" counter changes; it is tried as well as the whole picture
SCAN_INTERVAL = 0.5       # seconds between screen checks for the retry button
MONITOR_INDEX = 1         # 1 = primary monitor, 2 = second monitor, ...
SCALES = [1.0]            # extra sizes to try on top of the automatic resolution scaling (leave as is)
RETRY_SCALES = [0.80, 0.85, 0.90, 0.95, 1.0, 1.05, 1.10, 1.15, 1.20, 1.30]
                          # extra sizes tried ONLY for the retry button on screens that are not 1080p.
                          # Roblox buttons / text do not always grow exactly with the screen height, so
                          # the 1080p picture of the screen can show the button a bit bigger or smaller
                          # than retry_text.png. Whichever size fits best wins.
RETRY_DEBUG = False       # True = write the best retry score to the log every few seconds
                          # (to see how close a screen is to being detected)
BASE_HEIGHT = 1080        # all template images were taken at this screen height (1080p)
FORCE_SCALE = None        # None = automatic (screen height / 1080). Set e.g. 1.33 to force a scale
SCALE_THRESHOLD_RELAX = 0.05   # on a non-1080p screen every match threshold is lowered by this much
                               # (scaling the picture blurs it a little, so scores come out lower)
AFTER_CLICK_DELAY = 7     # seconds of doing NOTHING right after clicking retry
RETRY_CONFIRM_DELAY = 0.4 # re-check this long after first sighting (buttons fade in)
SAVE_CLICK_DEBUG = False   # saves last_retry_click.png showing exactly where it clicked

# --- Mission result detection (the gold COMPLETED / FAILED text on the end screen) ---
RESULT_FILES = {"completed": "result_completed.png", "failed": "result_failed.png"}
RESULT_THRESHOLD = 0.70   # lower it if results aren't detected
FIX_RETRY_WAIT = 2.0      # "Fix retry": seconds between seeing COMPLETED / FAILED and the click

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
MISSION_TIMEOUT = 120.0     # a mission longer than this many seconds (2 min) counts as stuck
RESCUE_CLICK_DELAY = 0.5    # seconds between the clicks on the middle of the screen
# Before clicking, the character is forced to look at the ground: press ctrl, move the mouse down
# for LOOK_DOWN_TIME seconds, press ctrl again.
# Before that look-down, the "still shifted" check: if the shifted ability 2 icon
# (shifted_ability2.png, same two folders) is on screen, the player is still shifted, so ability 2
# (the shifted one) is spammed for STILL_SHIFTED_SPAM_TIME. The wait before looking down
# (STILL_SHIFTED_WAIT) starts STILL_SHIFTED_WAIT_START seconds after the spam started, so it runs
# partly during the spam. Then the macro looks down and tries to kill the player.
SHIFTED_ICON_FILE = "shifted_ability2.png"
SHIFTED_ICON_THRESHOLD = 0.80        # lower it if the icon isn't being detected
STILL_SHIFTED_SPAM_TIME = 5.0        # spam ability 2 (shifted) this long
STILL_SHIFTED_SPAM_INTERVAL = 0.1    # seconds between those ability 2 presses
STILL_SHIFTED_WAIT_START = 2.0       # the wait below starts this many seconds after the spam started
STILL_SHIFTED_WAIT = 15.0            # wait this long before looking down
DEBUG_RESCUE_KEY = "f3+k"            # DEBUG: F3+K triggers the stuck-mission rescue by hand (remove later)
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
SHIFTED4_SPAM_TIME = 8.0         # spam the shifted ability 4 for this long
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

# --- Family "Shiki": ability 4 icon during the buying time ---
# While strafing A after ability 3, the ability 4 icon (shiki_ability4.png, same two folders) is
# watched. The moment it shows up, ability 4 is spammed for SHIKI_ABILITY4_SPAM_TIME and the buying
# time is over (the plain ABILITY4_COOLDOWN timer stays as a fallback if the icon is never seen).
SHIKI_ABILITY4_FILE = "shiki_ability4.png"
SHIKI_ABILITY4_THRESHOLD = 0.80      # lower it if the icon isn't being detected
SHIKI_ABILITY4_CHECK_INTERVAL = 0.25 # seconds between two looks for the icon
SHIKI_ABILITY4_CHECK_AFTER = 3.0     # start looking for the icon this many seconds after ability 3
SHIKI_ABILITY4_SPAM_TIME = 2.0       # spam ability 4 this long once the icon is seen
SHIKI_ABILITY4_SPAM_INTERVAL = 0.1   # seconds between those ability 4 presses

# --- Movement (every config): dashing copied from a recorded macro, Space spammed non-stop ---
UNIVERSAL_DASH_TIME = 8.2         # seconds of spamming
UNIVERSAL_DASH_HOLD = (0.065, 0.09)  # how long each Space press is held
UNIVERSAL_DASH_PRESS_GAP = (0.05, 0.08)  # pause between two presses
UNIVERSAL_AFTER_ABILITY3_WAIT = 2.0  # Universal family: wait this long after ability 3 ...
# ... then ctrl, mouse dragged down (LOOK_DOWN_TIME), ctrl again (forces the player to look down),
# then ability 4 once, then the shifting sequence goes on as usual (no buying time, no icon check)

# --- Settings window ---
MOVE_SHIFTED_OPTIONS = ("Left", "Right", "Stand")   # "Move while shifted" (step 9)
DEFAULT_MOVE_SHIFTED = "Right"
MOVE_SHIFTED_BADGES = {
    "Left":  ("L", "#3b82f6", "#ffffff"),
    "Right": ("R", "#14b8a6", "#ffffff"),
    "Stand": ("S", "#7a8398", "#ffffff"),
}
FAMILIES = ("Shiki", "Universal", "Blood Awakening")
DEFAULT_FAMILY = "Shiki"
FAMILY_LABELS = {f: f for f in FAMILIES}   # what the dropdown shows
FAMILY_TAGS = {}   # entry -> tag text in the dropdown ("WIP" yellow, "Beta" blue), e.g. {"Universal": "Beta"}
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
    "theme": DEFAULT_THEME,
    "low_quality": False,   # True = only the "low quality fix" pictures are used
    "move_shifted": DEFAULT_MOVE_SHIFTED,   # direction held at step 9: Left (A) / Right (D) / Stand
    "fix_retry": False,     # True = end of mission is read from COMPLETED / FAILED, retry is clicked
                            # at fix_retry_pos
    "fix_retry_pos": None,  # [x, y] screen pixels picked by the user (None = not set yet)
    "retry_scale": None,    # template size that last found the retry button on a non-1080p screen
                            # (None = not found yet). Tried first; updated when another size matches
    "always_on_top": False, # footer switch "Always on top" (kept between runs)
    "window": None,         # {"x", "y", "w", "h"} of the main window (None = never moved/resized)
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
    if saved.get("theme") in THEMES:
        settings["theme"] = saved["theme"]
    if isinstance(saved.get("low_quality"), bool):
        settings["low_quality"] = saved["low_quality"]
    if saved.get("move_shifted") in MOVE_SHIFTED_OPTIONS:
        settings["move_shifted"] = saved["move_shifted"]
    if isinstance(saved.get("always_on_top"), bool):
        settings["always_on_top"] = saved["always_on_top"]
    rs = saved.get("retry_scale")
    if isinstance(rs, (int, float)) and not isinstance(rs, bool) and 0.3 <= rs <= 3.0:
        settings["retry_scale"] = float(rs)
    if isinstance(saved.get("fix_retry"), bool):
        settings["fix_retry"] = saved["fix_retry"]
    pos = saved.get("fix_retry_pos")
    if (isinstance(pos, (list, tuple)) and len(pos) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in pos)):
        settings["fix_retry_pos"] = [pos[0], pos[1]]
    win = saved.get("window")
    if (isinstance(win, dict) and all(
            isinstance(win.get(k), int) and not isinstance(win.get(k), bool)
            for k in ("x", "y", "w", "h"))):
        settings["window"] = {k: win[k] for k in ("x", "y", "w", "h")}


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
                    (START_KEY, request_start),
                    (DEBUG_RESCUE_KEY, debug_trigger_rescue)):   # DEBUG: F3+K
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


def rescue_embed(eliminated, mission_no, mission_seconds=None):
    """Discord embed for the stuck-mission rescue: it started / it worked."""
    limit = f"{int(MISSION_TIMEOUT // 60)}m {int(MISSION_TIMEOUT % 60):02d}s"
    if eliminated:
        embed = {
            "title": f"Mission #{mission_no} - Player eliminated",
            "color": 0x34D399,
            "description": "The retry button showed up, so the stuck mission is over: "
                           "the player was **successfully eliminated**.",
        }
        if mission_seconds is not None:
            embed["footer"] = {"text": f"Mission length {fmt_time(mission_seconds)}"}
    else:
        embed = {
            "title": f"Mission #{mission_no} - Stuck mission",
            "color": 0xFBBF24,
            "description": f"This mission ran longer than {limit}, so the macro is now "
                           "**trying to eliminate the player** (looking at the ground, then "
                           "clicking the middle of the screen until retry shows up).",
        }
    embed["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return embed


def notify_rescue_async(eliminated, mission_no, mission_seconds=None):
    """Send the rescue embed in the background (only if a webhook is set). Mentions you when
    mentions are on and a user ID is set."""
    if not webhook_url():
        return
    embed = rescue_embed(eliminated, mission_no, mission_seconds)

    def work():
        ok, msg = post_webhook("", ping=True, embed=embed)
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
         "rescuing": False,         # True while the stuck-mission rescue is clicking
         "rescued": False,          # True once the rescue started in the current mission
         "debug_rescue": False}     # DEBUG: set by F3+K, makes tick() start the rescue right now
stats = {"missions": 0, "retries": 0}
loot = {kind: 0 for kind in LOOT_FILES}
results = {"completed": 0, "failed": 0}
worker = None

_sct = None
_sct_lock = threading.Lock()   # guards _sct re-creation when the monitor turns off/on
_monitor = None
_scale = 1.0     # real screen height / BASE_HEIGHT (set when the macro starts)
_retry_template = None
_alt_retry_templates = []        # extra looks of the retry button: [(templates, dx)] - see load_alt_retry()
_start_template = None
_shiki_ability4_icon = None      # Shiki: ability 4 icon, seen = ability 4 is ready
_shifted_icon = None             # shifted ability 2 icon: seen at the rescue = player is still shifted
_loot_templates = {}
_result_templates = {}
_grab_template = None
_last_scan = 0.0
_last_grab = 0.0


class RetryFound(Exception):
    def __init__(self, match, quality="normal", kind=None):
        super().__init__("retry button found")
        self.match = match
        self.quality = quality    # which look matched: "normal" or "low" (low graphics),
                                  # or "fix" (Fix retry: the COMPLETED / FAILED text was seen)
        self.kind = kind          # "completed" / "failed" (Fix retry only)


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


def debug_trigger_rescue():
    """DEBUG (F3+K): start the stuck-mission rescue right now, as if 2m had passed.
    Remove this function, DEBUG_RESCUE_KEY and the lines marked DEBUG when it is not needed."""
    if not running():
        log("DEBUG F3+K: start the macro first")
        return
    if state["rescuing"]:
        return
    state["debug_rescue"] = True
    log("DEBUG F3+K: rescue requested")


def start_macro(manual=False):
    global worker
    if running():
        return
    state.update(paused=False, quit=False, manual_start=manual,
                 phase_status="waiting", mission_t0=None, rescuing=False,
                 debug_rescue=False)
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


def find_quality_template(screen_bgr, templates, threshold, scales=None):
    """Look for every look of a template. Returns (match, quality) of the best one that
    passes the threshold, or None. The quality says which look it was ("normal" / "low")."""
    best = None
    for quality, tpl in templates.items():
        m = find_template(screen_bgr, tpl, threshold, scales)
        if m and (best is None or m[2] > best[0][2]):
            best = (m, quality)
    return best


_small_cache = (None, None)
_scale_hint = {}      # id(template) -> (best size, scans left before sweeping again)


def _coarse_best_scale(screen_bgr, template, scales):
    """Pick the template size that fits best using a half-resolution picture (4x cheaper than
    matching every size at full resolution)."""
    global _small_cache
    hint = _scale_hint.get(id(template))
    if hint and hint[1] > 0:                  # the best size is the same every scan: reuse it
        _scale_hint[id(template)] = (hint[0], hint[1] - 1)
        return hint[0]
    if _small_cache[0] is not screen_bgr:
        _small_cache = (screen_bgr, cv2.resize(screen_bgr, None, fx=0.5, fy=0.5,
                                               interpolation=cv2.INTER_AREA))
    small = _small_cache[1]
    best_scale, best_score = 1.0, -1.0
    for scale in scales:
        t = cv2.resize(template, None, fx=scale * 0.5, fy=scale * 0.5,
                       interpolation=cv2.INTER_AREA)
        th, tw = t.shape[:2]
        if th < 4 or tw < 4 or th > small.shape[0] or tw > small.shape[1]:
            continue
        score = cv2.minMaxLoc(cv2.matchTemplate(small, t, cv2.TM_CCOEFF_NORMED))[1]
        if score > best_score:
            best_scale, best_score = scale, score
    if best_score >= 0.6:       # only trust it when the button really is on screen
        _scale_hint[id(template)] = (best_scale, 20)     # sweep again after 20 scans
    return best_scale


def best_match(screen_bgr, template, scales=None):
    """Return (center_x, center_y, score, w, h) of the best match, or None."""
    best = None
    scales = scales or SCALES
    if len(scales) > 1:
        scales = [_coarse_best_scale(screen_bgr, template, scales)]   # one full-size match only
    for scale in scales:
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


def relax(threshold):
    """Match thresholds are a bit lower on screens that are not 1080p (the scaled picture is blurrier)."""
    if abs(_scale - 1.0) > 0.01:
        return threshold - SCALE_THRESHOLD_RELAX
    return threshold


def find_template(screen_bgr, template, threshold, scales=None):
    best = best_match(screen_bgr, template, scales)
    if best and best[2] >= relax(threshold):
        return best
    return None


# --- Monitor turned off (DisplayPort drops the display when the monitor is switched off) ---
_MONITOR_OFF_RETRY_INTERVAL = 2.0   # seconds between reinit attempts while the monitor is off
_monitor_was_off = False            # used to log "monitor back" once


def _reinit_mss():
    """Create a fresh mss instance (called when a grab fails or returns a black frame).
    Returns True when the new instance works, False when the monitor is still unreachable."""
    global _sct, _monitor, _scale
    with _sct_lock:
        # Close the stale instance cleanly (best-effort).
        try:
            if _sct is not None:
                _sct.close()
        except Exception:  # noqa: BLE001
            pass
        new_sct = None
        try:
            new_sct = mss.mss()
            mon = new_sct.monitors[MONITOR_INDEX]
            # Quick sanity-grab to confirm the monitor is really back.
            test = np.array(new_sct.grab(mon))
            if test.max() == 0:
                new_sct.close()
                return False
            _sct = new_sct
            _monitor = mon
            _scale = FORCE_SCALE if FORCE_SCALE else _monitor["height"] / BASE_HEIGHT
            return True
        except Exception:  # noqa: BLE001
            try:
                if new_sct is not None:
                    new_sct.close()
            except Exception:  # noqa: BLE001
                pass
            return False


def grab_screen():
    """The screen as a BGR image, always scaled to 1080p size so the template images (which are
    1080p) match on any resolution. Positions in this image are 1080p positions: multiply by
    _scale to get real screen pixels.

    If the monitor is turned off (physical button), mss raises or returns a black frame.
    The function then waits in a loop, logging once, until the monitor comes back, and
    continues transparently so the macro never crashes or stops. Stop (F7) still works
    while it waits."""
    global _monitor_was_off
    while True:
        try:
            shot = np.array(_sct.grab(_monitor))
            img = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
            # An all-black frame means the monitor is off (or going to sleep).
            if img.max() == 0:
                raise OSError("All-black frame - monitor appears to be off")
            if _monitor_was_off:
                _monitor_was_off = False
                log("Monitor is back - resuming screen detection")
            if abs(_scale - 1.0) > 0.01:
                interp = cv2.INTER_AREA if _scale > 1 else cv2.INTER_CUBIC
                img = cv2.resize(img, None, fx=1 / _scale, fy=1 / _scale, interpolation=interp)
            return img
        except SystemExit:
            raise
        except Exception:  # noqa: BLE001
            if not _monitor_was_off:
                _monitor_was_off = True
                log("Monitor appears to be off - waiting for it to come back (screen detection paused)")
            if state["quit"]:
                raise SystemExit
            # Try to reconnect mss; if it fails, wait and try again (in short steps, so Stop works).
            if not _reinit_mss():
                end = time.time() + _MONITOR_OFF_RETRY_INTERVAL
                while time.time() < end:
                    if state["quit"]:
                        raise SystemExit
                    time.sleep(0.1)


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
    if settings["family"] == "Shiki":
        return   # Shiki: ability 1 is a perk, no need to press it
    if find_template(red_mask(screen), _grab_template, GRAB_THRESHOLD):
        _last_grab = time.time()
        log(f"Grabbed! Pressing {KEY_GRAB.upper()}")
        tap(KEY_GRAB)


def icon_visible():
    return find_quality_template(grab_screen(), _start_template, START_THRESHOLD) is not None


# --------------------- tick / wait (stay responsive) --------------------
def load_alt_retry():
    """alt_retry_button.png (and image/low quality fix/alt_retry_button.png): the whole button.
    Two looks are made of it: the whole picture and the RETRY word only (the "(0/1)" counter
    changes). dx = how far the picture's centre is from the whole button's centre, so a match
    can be turned back into the button centre for the click."""
    _alt_retry_templates.clear()
    try:
        whole = load_quality_templates(ALT_RETRY_FILE)
    except FileNotFoundError:
        return
    _alt_retry_templates.append((whole, 0))
    x0, x1 = ALT_RETRY_WORD_COLS
    word, dx = {}, 0
    for quality, img in whole.items():
        w = img.shape[1]
        if 0 <= x0 < x1 <= w:
            word[quality] = img[:, x0:x1]
            dx = w / 2 - (x0 + x1) / 2
    if word:
        _alt_retry_templates.append((word, dx))
    log(f"{ALT_RETRY_FILE} loaded - used as an extra check for the retry button")


_last_debug_log = 0.0


def _log_retry_score(screen, scales):
    """RETRY_DEBUG: log the best retry score (even when it is below the threshold)."""
    global _last_debug_log
    if time.time() - _last_debug_log < 5:
        return
    _last_debug_log = time.time()
    for quality, tpl in _retry_template.items():
        best = best_match(screen, tpl, scales)
        if best:
            log(f"[debug] retry best score ({quality}): {best[2]:.3f} "
                f"(needs {relax(THRESHOLD):.2f}), template size {best[3]}x{best[4]}")


_retry_scans = 0


def _match_retry(screen, scales):
    """retry_text.png first, then alt_retry_button.png, at the given template sizes.
    Returns (match, quality, size) or None. size = how much bigger/smaller than the picture."""
    found = find_quality_template(screen, _retry_template, THRESHOLD, scales)
    if found:
        match, quality = found
        return match, quality, match[3] / _retry_template[quality].shape[1]
    for templates, dx in _alt_retry_templates:
        alt = find_quality_template(screen, templates, ALT_RETRY_THRESHOLD, scales)
        if alt:
            (cx, cy, score, w, h), quality = alt
            size = w / templates[quality].shape[1]
            # centre of the whole button (dx is in picture pixels, so it grows with the size)
            return (cx + dx * size, cy, score, w, h), quality, size
    return None


def find_retry(screen):
    """The retry button: retry_text.png first, then (extra check) alt_retry_button.png.
    Returns (match, quality) like find_quality_template, or None.

    Not 1080p: the size that matched last time (settings "retry_scale", saved in the json) is
    tried first. Only when it misses are the other sizes (RETRY_SCALES) tried - and if one of
    those matches, it becomes the saved size from then on."""
    global _retry_scans
    if abs(_scale - 1.0) <= 0.01:
        found = _match_retry(screen, None)
        return found[:2] if found else None
    if RETRY_DEBUG:
        _log_retry_score(screen, RETRY_SCALES)
    saved = settings.get("retry_scale")
    found = _match_retry(screen, [saved]) if saved else None
    if not found:
        # the other sizes cost more: with a saved size they are tried every 4th scan only
        _retry_scans += 1
        if not saved or _retry_scans % 4 == 0:
            found = _match_retry(screen, RETRY_SCALES)
            if found:
                size = min(RETRY_SCALES, key=lambda sc: abs(sc - found[2]))
                if saved is None or abs(size - saved) > 0.001:
                    settings["retry_scale"] = size
                    save_stats()
                    log(f"Retry button matched at size x{size:.2f} (score {found[0][2]:.2f}) "
                        "- saved, it is tried first from now on")
    return found[:2] if found else None


def fix_retry_active():
    """Fix retry is on, a click position is saved and the result pictures are loaded."""
    return bool(settings["fix_retry"] and settings["fix_retry_pos"] and _result_templates)


def find_result(screen):
    """The COMPLETED / FAILED text on screen: (kind, (cx, cy, score, w, h)) or None."""
    if not _result_templates:
        return None
    mask = gold_mask(screen)
    best = None
    for kind, tpl in _result_templates.items():
        th, tw = tpl.shape[:2]
        if th > mask.shape[0] or tw > mask.shape[1]:
            continue
        res = cv2.matchTemplate(mask, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score >= relax(RESULT_THRESHOLD) and (best is None or score > best[1][2]):
            best = (kind, (loc[0] + tw // 2, loc[1] + th // 2, score, tw, th))
    return best


def scan_for_retry():
    """Look for the end of the mission once (and for a grab). Raises RetryFound if it is there.
    Normal: the retry button. Fix retry: the COMPLETED / FAILED text."""
    global _last_scan
    _last_scan = time.time()
    screen = grab_screen()
    check_grabbed(screen)
    if fix_retry_active():
        seen = find_result(screen)
        if seen:
            time.sleep(RETRY_CONFIRM_DELAY)          # text fades in: make sure it stays
            again = find_result(grab_screen())
            if again and again[0] == seen[0]:
                raise RetryFound(again[1], "fix", again[0])
        return
    found = find_retry(screen)
    if found:
        match = found[0]
        # screens often fade/animate in: look again and click only if it's
        # still there, at the same spot
        time.sleep(RETRY_CONFIRM_DELAY)
        again = find_retry(grab_screen())
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


def still_shifted():
    """True when the shifted ability 2 icon is on screen (the player is still shifted)."""
    if not _shifted_icon:
        return False
    return find_quality_template(grab_screen(), _shifted_icon, SHIFTED_ICON_THRESHOLD) is not None


def rescue_clicks(debug=False):
    """Stuck mission (longer than MISSION_TIMEOUT): look at the ground (ctrl, mouse down for 2s,
    ctrl), then click the middle of the screen every RESCUE_CLICK_DELAY seconds until the retry
    button can be seen. The retry button being found raises RetryFound, so the normal
    end-of-mission handling takes over."""
    state["rescuing"] = True
    if not debug:
        state["rescued"] = True
    for held in (KEY_STRAFE_D, KEY_STRAFE):
        try:
            pydirectinput.keyUp(held)          # step 9 may be holding D / A: let go before rescuing
        except Exception:  # noqa: BLE001
            pass
    if not debug:
        notify_rescue_async(False, stats["missions"])  # Discord: stuck, trying to eliminate
    cx = _monitor["left"] + _monitor["width"] // 2
    cy = _monitor["top"] + _monitor["height"] // 2
    log(f"Mission is taking longer than {MISSION_TIMEOUT:g}s - looking at the ground, then "
        "clicking the middle of the screen until retry shows up")
    show("Stuck mission", "Looking at the ground, then clicking the middle of the screen")

    def click_phase():
        """Click the middle every RESCUE_CLICK_DELAY seconds until retry shows up."""
        while True:
            tick(scan_retry=False)                      # stop / pause
            loop_start = time.time()
            scan_for_retry()                            # raises RetryFound when it is visible
            click_middle(cx, cy)
            end = loop_start + RESCUE_CLICK_DELAY      # click-to-click gap = exactly the delay
            while time.time() < end:
                tick(scan_retry=False)
                time.sleep(0.05)

    try:
        # still shifted? (the shifted ability 2 icon is on screen): spam ability 2, then wait
        if debug:
            log("DEBUG F3+K: running the rescue now")
        if _shifted_icon is None:
            log(f"Rescue: {SHIFTED_ICON_FILE} not found - can't tell if the player is still shifted")
        elif still_shifted():
            log("Rescue: shifted ability 2 icon seen - still shifted")
            show("Stuck mission", f"Still shifted - spamming ability 2 for {STILL_SHIFTED_SPAM_TIME:g}s")
            log(f"Rescue: spamming ability 2 for {STILL_SHIFTED_SPAM_TIME:g}s, the {STILL_SHIFTED_WAIT:g}s "
                f"wait starts {STILL_SHIFTED_WAIT_START:g}s after the spam started")
            spam_start = time.time()
            wait_end = spam_start + STILL_SHIFTED_WAIT_START + STILL_SHIFTED_WAIT
            spam_key_for(KEY_ABILITY_1ST, STILL_SHIFTED_SPAM_TIME, STILL_SHIFTED_SPAM_INTERVAL,
                         "ability 2 (shifted)")
            while True:     # the rest of the wait (it started during the spam)
                remaining = wait_end - time.time()
                if remaining <= 0:
                    break
                show("Stuck mission", f"Waiting {remaining:.0f}s before looking down")
                wait(min(0.5, remaining))
        else:
            log("Rescue: shifted ability 2 icon not seen - not shifted")
        look_down(lambda: tick(scan_retry=False))
        click_phase()
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
        if state["debug_rescue"] and not state["rescuing"]:     # DEBUG: F3+K
            state["debug_rescue"] = False
            rescue_clicks(debug=True)
        elif (not state["rescuing"] and t0 is not None
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


def click_exact(x, y):
    """Click one exact screen position (Fix retry: the position the user picked)."""
    pydirectinput.moveTo(int(x), int(y))
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
            if best and best[2] >= relax(LOOT_THRESHOLD):
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
        if m[2] >= relax(RESULT_THRESHOLD) and (result is None or m[2] > result[1][2]):
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
    """Strafe A for the length of ability 4's cooldown. Call right after ability 3.
    Returns True when the Shiki ability 4 icon was seen (buying time over early), else False."""
    start = time.time()
    total = ABILITY4_COOLDOWN + ABILITY4_COOLDOWN_MARGIN
    keys = BUY_TIME_MOVES
    i = 0
    next_strafe = start
    next_look = start + SHIKI_ABILITY4_CHECK_AFTER
    while True:
        now = time.time()
        remaining = total - (now - start)
        if remaining <= 0:
            return False
        if _shiki_ability4_icon and now >= next_look:
            next_look = now + SHIKI_ABILITY4_CHECK_INTERVAL
            if find_quality_template(grab_screen(), _shiki_ability4_icon,
                                     SHIKI_ABILITY4_THRESHOLD) is not None:
                log("Shiki ability 4 icon seen")
                return True
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


def spam_recorded_dash(key, seconds):
    """The movement (every config): Space pressed over and over with the timings of a recorded macro
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


def shift_sequence():
    """The shift: ability 5 spam, the wait, shifted ability 4, then ability 5 until the retry
    button shows up."""
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
    move = settings["move_shifted"]
    hold_key = KEY_STRAFE_D if move == "Right" else KEY_STRAFE if move == "Left" else None
    hold_txt = f"holding {hold_key.upper()}" if hold_key else "standing still"
    log(f"Ability 5 over and over + {hold_txt} (until the mission ends "
        f"or the mission passes {MISSION_TIMEOUT:g}s)")
    presses = 0
    next_5 = time.time()
    d_held = False
    try:
        while True:
            now = time.time()
            t0 = state["mission_t0"]
            timed_out = t0 is not None and now - t0 > MISSION_TIMEOUT
            if timed_out:
                if d_held:                       # mission too long: let go of the key
                    pydirectinput.keyUp(hold_key)
                    d_held = False
                    log(f"Mission over {MISSION_TIMEOUT:g}s - released {hold_key.upper()}")
            elif hold_key and not d_held:
                pydirectinput.keyDown(hold_key)   # hold A / D (the end of the mission ends this)
                d_held = True
            if now >= next_5:
                presses += 1
                show("Ability 5", f"Pressed x{presses} + {hold_txt} "
                                  "- until the mission ends")
                tap(KEY_ABILITY_LAST)
                next_5 = time.time() + ABILITY_5_CHECK_INTERVAL
            wait(0.05)
    finally:
        if hold_key:
            pydirectinput.keyUp(hold_key)    # retry found / stop / error: never leave it held


# ---------------------------- the routine -------------------------------
def run_mission():
    state["manual_start"] = False   # a mission is running now: forget any leftover F8 press
    state["mission_t0"] = time.time()   # for the stuck-mission rescue (MISSION_TIMEOUT)
    state["rescued"] = False
    stats["missions"] += 1
    push_stats()
    ev.put(("mission_started",))
    set_status("running")

    set_step(0)
    show("Ability 2", "Only ability 2 for now - no dashing yet")
    log("Ability 2")
    tap(KEY_ABILITY_1ST)
    wait(AFTER_ABILITY2_DELAY)  # nothing else happens until the dash sequence

    # read once per mission: the movement is the same for every config,
    # the family (abilities) decides what happens from ability 3 on
    universal = settings["family"] == "Universal"   # ability 3, wait, look down, ability 4, shift
    blood = settings["family"] == "Blood Awakening"

    set_step(1)
    log(f"Movement: spamming dash for {UNIVERSAL_DASH_TIME:g}s")
    spam_recorded_dash(KEY_DASH, UNIVERSAL_DASH_TIME)

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

        if universal:
            # Universal: ability 3 -> wait -> look down (ctrl, drag mouse down, ctrl) -> ability 4
            set_step(4)
            show("Waiting", f"{UNIVERSAL_AFTER_ABILITY3_WAIT:g}s after ability 3")
            log(f"Universal: waiting {UNIVERSAL_AFTER_ABILITY3_WAIT:g}s after ability 3")
            wait(UNIVERSAL_AFTER_ABILITY3_WAIT)
            show("Looking down", "ctrl, mouse down, ctrl")
            log("Universal: looking down (ctrl, mouse down, ctrl)")
            look_down(lambda: tick(scan_retry=False))
            set_step(5)
            show("Ability 4")
            log("Ability 4")
            tap(KEY_ABILITY_3RD)
            wait(AFTER_ABILITY_DELAY)
        else:
            set_step(4)
            show("Buying time", f"Strafing {KEY_STRAFE.upper()} until ability 4 is off cooldown")
            log(f"Buying time for {ABILITY4_COOLDOWN:.0f}s (ability 4 cooldown)")
            icon_seen = buy_time_until_ability4_ready()

            set_step(5)
            if icon_seen:
                show("Ability 4", f"Icon seen - spamming ability 4 for {SHIKI_ABILITY4_SPAM_TIME:g}s")
                log(f"Ability 4 spam for {SHIKI_ABILITY4_SPAM_TIME:g}s (icon seen)")
                spam_key_for(KEY_ABILITY_3RD, SHIKI_ABILITY4_SPAM_TIME,
                             SHIKI_ABILITY4_SPAM_INTERVAL, "ability 4")
            else:
                show("Ability 4")
                log("Ability 4")
                tap(KEY_ABILITY_3RD)
            wait(AFTER_ABILITY_DELAY)

    shift_sequence()


# --------------------------- macro thread -------------------------------
def macro_main():
    global _sct, _monitor, _scale, _retry_template, _start_template, _grab_template
    global _shiki_ability4_icon, _shifted_icon
    try:
        _retry_template = load_quality_templates(TEMPLATE_FILE)
        load_alt_retry()
        _start_template = load_quality_templates(START_TEMPLATE_FILE)
        try:
            _shiki_ability4_icon = load_quality_templates(SHIKI_ABILITY4_FILE)
        except FileNotFoundError:
            _shiki_ability4_icon = None
            log(f"Shiki: {SHIKI_ABILITY4_FILE} not found - buying time uses the {ABILITY4_COOLDOWN:.0f}s timer")
        try:
            _shifted_icon = load_quality_templates(SHIFTED_ICON_FILE)
        except FileNotFoundError:
            _shifted_icon = None
            log(f"Rescue: {SHIFTED_ICON_FILE} not found - the still-shifted check is skipped")
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
        if settings["fix_retry"]:
            if not settings["fix_retry_pos"]:
                log("Fix retry is on but no click position is set (Settings > Configs) - "
                    "using the normal retry detection")
            elif not _result_templates:
                log("Fix retry needs result_completed.png / result_failed.png - "
                    "using the normal retry detection")
            else:
                log(f"Fix retry on: the retry click goes to {tuple(settings['fix_retry_pos'])} "
                    f"{FIX_RETRY_WAIT:g}s after COMPLETED / FAILED shows up")
        log("Started. Click into Roblox; the routine starts when the mission begins.")

        # Initialise mss manually so _reinit_mss() can replace it while running.
        try:
            _sct = mss.mss()
            _monitor = _sct.monitors[MONITOR_INDEX]
            _scale = FORCE_SCALE if FORCE_SCALE else _monitor["height"] / BASE_HEIGHT
            if abs(_scale - 1.0) > 0.01:
                log(f"Screen is {_monitor['width']}x{_monitor['height']}: scaling the picture "
                    f"to 1080p size (x{1 / _scale:.2f}) so the images match")

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
                    mission_t0 = state["mission_t0"]
                    state["mission_t0"] = None     # the mission is over (no rescue needed)
                    was_rescued, state["rescued"] = state["rescued"], False
                    cx, cy, score, tw, th = r.match
                    # cx, cy are 1080p-picture positions: back to real screen pixels
                    abs_x = _monitor["left"] + int(cx * _scale)
                    abs_y = _monitor["top"] + int(cy * _scale)
                    ev.put(("mission_ended",))
                    set_status("retrying")
                    set_step(-1)
                    fix = r.quality == "fix"
                    if fix:
                        log(f"Mission ended: {r.kind.upper()} text seen (Fix retry, score {score:.2f})")
                    else:
                        log(f"Retry found ({r.quality} quality, score {score:.2f})")
                    if was_rescued:
                        log("Stuck mission is over - player eliminated")
                        notify_rescue_async(True, stats["missions"],
                                            time.time() - mission_t0 if mission_t0 else None)
                    if fix:      # no retry button was seen: use the graphics setting for the loot
                        low = bool(settings["low_quality"])
                        q = "low" if low else "normal"
                    else:
                        low = r.quality == "low"
                        q = r.quality
                    loot_found, result = {}, None
                    loot_on = bool(_loot_templates.get(q))   # loot icons of THIS quality
                    # normal quality: result + loot are read before the click.
                    # low quality: only the result now, the loot after the click (see below)
                    if fix:
                        # Fix retry: wait FIX_RETRY_WAIT seconds (result + loot are read meanwhile)
                        show("Mission ended", f"{r.kind.capitalize()} - clicking retry in "
                                              f"{FIX_RETRY_WAIT:g}s")
                        log(f"Waiting {FIX_RETRY_WAIT:g}s before clicking the retry position")
                        loot_found, result = scan_end_screen(
                            q, want_loot=loot_on and not low, want_result=True,
                            scan_time=FIX_RETRY_WAIT)
                        if result is None:
                            result = (r.kind, r.match)      # seen when it was detected
                        record_result(result)
                        if loot_on and not low:
                            record_loot(loot_found)
                    elif _result_templates or (loot_on and not low):
                        show("Retry found", "Checking the result and loot..."
                             if not low else "Checking the result...")
                        loot_found, result = scan_end_screen(
                            q, want_loot=not low, want_result=True)
                        if _result_templates:
                            record_result(result)
                        if loot_on and not low:
                            record_loot(loot_found)
                    if not low:
                        notify_mission_async(result, loot_found)   # Discord stats embed (if on)
                    show("Retry found" if not fix else "Mission ended", "Clicking...")
                    if fix:
                        px, py = settings["fix_retry_pos"]
                        log(f"Clicking retry at the saved position ({px}, {py})")
                        click_exact(px, py)
                    else:
                        log("Clicking retry")
                        save_click_debug(cx, cy, tw, th)
                        click_at(abs_x, abs_y, int(tw * _scale), int(th * _scale))
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
                                q, want_loot=True, want_result=False,
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
        finally:
            # Clean up the mss instance (whether we're stopping or _reinit_mss() replaced it):
            # close whatever is current now.
            with _sct_lock:
                try:
                    if _sct is not None:
                        _sct.close()
                except Exception:  # noqa: BLE001
                    pass
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
        self.geo_job = None

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
        min_h = max(560, h - 160)
        w, h, x, y = self.restore_geometry(w, h, min_h)   # last size / spot (default: top-left)
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.minsize(400, min_h)
        style_title_bar(root, self.BG)
        root.deiconify()
        root.bind("<Configure>", self.on_configure)       # remember moves / resizes
        root.bind("<FocusIn>", self.keep_settings_on_top, add="+")   # settings stays above this window
        root.bind("<ButtonPress>", self.keep_settings_on_top, add="+")
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
        geo = r.geometry()      # size + position now: the theme change must not move / resize the window
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
        r.geometry(geo)         # same size and place as before (the log takes up any difference)
        style_title_bar(r, self.BG)
        self.keep_settings_on_top()      # (debounced: one single lift, no flicker)

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

    def keep_settings_on_top(self, _event=None):
        """The settings window stays above the main window, even when that one is always on top."""
        if self.settings_win is None or getattr(self, "_lift_job", None):
            return                       # nothing to do, or a lift is already scheduled
        self._lift_job = self.root.after(60, self._lift_settings)

    def _lift_settings(self):
        """One single lift, 60 ms after the last request (many events -> no flicker)."""
        self._lift_job = None
        win = self.settings_win
        if win is None:
            return
        try:
            win.lift()                   # it is owned by the main window and topmost already
        except tk.TclError:
            pass

    def on_topmost_toggle(self):
        on = bool(self.topmost.get())
        self.root.attributes("-topmost", on)
        self.keep_settings_on_top()
        settings["always_on_top"] = on
        save_stats()

    def build_footer(self):
        foot = tk.Frame(self.root, bg=self.BG)
        foot.pack(side="bottom", fill="x", padx=18, pady=(4, 12))
        self.topmost = tk.BooleanVar(value=bool(settings.get("always_on_top")))
        self.root.attributes("-topmost", self.topmost.get())     # restore the saved state
        left = tk.Frame(foot, bg=self.BG)
        left.pack(side="left")
        sw = ToggleSwitch(left, self.topmost, self.on_topmost_toggle, parent_bg=self.BG)
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

    # ----- remembering the window size / position -----
    def restore_geometry(self, w, h, min_h):
        """Saved size + position, kept inside the screen. Returns (w, h, x, y)."""
        win = settings.get("window")
        if not win:
            return w, h, 20, 20
        r = self.root
        vx, vy = r.winfo_vrootx(), r.winfo_vrooty()
        vw = max(r.winfo_vrootwidth(), r.winfo_screenwidth())
        vh = max(r.winfo_vrootheight(), r.winfo_screenheight())
        w = min(max(win["w"], 400), vw)
        h = min(max(win["h"], min_h), vh)
        # keep a good part of the window (and its title bar) on a screen, e.g. after a
        # monitor was unplugged
        x = min(max(win["x"], vx - w + 120), vx + vw - 120)
        y = min(max(win["y"], vy), vy + vh - 80)
        return w, h, x, y

    def on_configure(self, event):
        if event.widget is not self.root:      # ignore the child widgets
            return
        if self.geo_job:
            self.root.after_cancel(self.geo_job)
        self.geo_job = self.root.after(800, self.save_window)   # once it stops moving

    def save_window(self):
        self.geo_job = None
        r = self.root
        try:
            if r.state() != "normal":          # minimized / maximized: keep the last good one
                return
            m = re.match(r"(\d+)x(\d+)([+-])(-?\d+)([+-])(-?\d+)$", r.geometry())
        except tk.TclError:
            return
        if not m:
            return
        w, h = int(m.group(1)), int(m.group(2))
        x = int(m.group(4)) * (1 if m.group(3) == "+" else -1)
        y = int(m.group(6)) * (1 if m.group(5) == "+" else -1)
        new = {"x": x, "y": y, "w": w, "h": h}
        if new != settings.get("window"):
            settings["window"] = new
            save_stats()

    def on_close(self):
        if self.geo_job:
            self.root.after_cancel(self.geo_job)
        self.save_window()
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
    optional tag (WIP / Beta). items = [(key, label, (letter, badge_bg, letter_fg), tag), ...]
    where tag is None, "WIP" or "Beta"."""
    BG, HOVER, EDGE = "#1a1e29", "#232a3d", "#2a3042"
    TEXT, SUB, ACCENT = "#e6e9f2", "#7a8398", "#3b82f6"
    WIP_BG, WIP_FG = "#2e2410", "#fbbf24"
    BETA_BG, BETA_FG = "#10223d", "#60a5fa"

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
        _key, label, badge, tag_text = self.items[key]
        row = tk.Frame(parent, bg=bg, cursor="hand2")
        parts = [self.make_badge(row, badge, bg)]
        parts[0].pack(side="left", padx=(12, 10), pady=9)
        name = tk.Label(row, text=label, font=(App.FONT, 10), fg=self.TEXT, bg=bg)
        name.pack(side="left")
        parts.append(name)
        if tag_text:
            beta = tag_text == "Beta"
            tag = tk.Label(row, text=tag_text, font=(App.FONT, 7, "bold"),
                           fg=self.BETA_FG if beta else self.WIP_FG,
                           bg=self.BETA_BG if beta else self.WIP_BG, padx=6, pady=1)
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
        self.pos_capturing = False  # waiting for the click that sets the Fix retry position
        self.pos_wait_release = False
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
        self.transient(app.root)             # owned by the main window = always drawn above it
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
        old_w, old_h = self.winfo_width(), self.winfo_height()
        self.build_ui(tab)
        self.update_idletasks()
        # keep the size it had; it only grows if the new look really needs more room
        self.geometry(f"{max(old_w, self.winfo_reqwidth())}x{max(old_h, self.winfo_reqheight())}")
        style_title_bar(self, App.BG)
        self.app.keep_settings_on_top()

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
        # section 1: abilities (the family)
        self.v_family = tk.StringVar(value=settings["family"])
        c = self.card(page, "ABILITIES")
        items = [(f, FAMILY_LABELS[f], FAMILY_BADGES[f], FAMILY_TAGS.get(f)) for f in FAMILIES]
        self.family_dd = ModernDropdown(c, items, settings["family"], self.on_family_pick)
        self.family_dd.pack(fill="x")
        tk.Label(c, text="Yeager not recommended", font=(App.FONT, 8),
                 fg=App.SUB, bg=App.CARD, anchor="w").pack(fill="x", pady=(8, 0))

        # section 2: graphics
        self.v_lowq = tk.BooleanVar(value=settings["low_quality"])
        g = self.card(page, "GRAPHICS",
                      "Turn this on if you play on low graphics. It uses ONLY the pictures in "
                      "image/low quality fix to find the retry button, the loot and the "
                      "mission start. Body fragments are NOT checked in this mode (no fix "
                      "for the false detections yet).")
        self.check(g, "Low quality mode", self.v_lowq, self.on_lowq_toggle)

        # section 3: movement while shifted (step 9)
        self.v_move_shifted = tk.StringVar(value=settings["move_shifted"])
        ms = self.card(page, "MOVE WHILE SHIFTED",
                       "The direction you move in after shifting (while spamming ability 5). "
                       f"Left holds {KEY_STRAFE.upper()}, Right holds {KEY_STRAFE_D.upper()}, "
                       "Stand holds nothing.")
        ms_items = [(o, o, MOVE_SHIFTED_BADGES[o], None) for o in MOVE_SHIFTED_OPTIONS]
        self.move_shifted_dd = ModernDropdown(ms, ms_items, settings["move_shifted"],
                                              self.on_move_shifted_pick)
        self.move_shifted_dd.pack(fill="x")

        # section 4: fix retry
        self.v_fix = tk.BooleanVar(value=settings["fix_retry"])
        f = self.card(page, "FIX RETRY",
                      "Turn this on if the retry button is not being detected. The macro then "
                      "watches for the COMPLETED / FAILED text instead, waits "
                      f"{FIX_RETRY_WAIT:g} seconds and clicks the position you set below.")
        self.check(f, "Fix retry", self.v_fix, self.on_fix_toggle)
        pos_row = tk.Frame(f, bg=App.CARD)
        pos_row.pack(fill="x", pady=(6, 0))
        self.fix_pos_title = tk.Label(pos_row, text="Retry click position", font=(App.FONT, 10),
                                      bg=App.CARD, anchor="w")
        self.fix_pos_title.pack(side="left")
        self.fix_pos_btn = tk.Label(pos_row, text="Set position", font=(App.FONT, 9, "bold"),
                                    padx=12, pady=5)
        self.fix_pos_btn.pack(side="right")
        self.fix_pos_btn.bind("<Button-1>", lambda _e: self.start_pos_capture())
        self.fix_pos_btn.bind("<Enter>", lambda _e: self.fix_pos_hover(True))
        self.fix_pos_btn.bind("<Leave>", lambda _e: self.fix_pos_hover(False))
        self.fix_pos_value = tk.Label(f, text="", font=(App.FONT, 9), bg=App.CARD, anchor="w")
        self.fix_pos_value.pack(fill="x", pady=(4, 0))
        self.refresh_fix_pos()

    # ----- fix retry helpers -----
    def fix_pos_hover(self, on):
        if self.v_fix.get() and not self.pos_capturing:
            self.fix_pos_btn.configure(bg=App.ACCENT_BG_HOVER if on else App.ACCENT_BG)

    def refresh_fix_pos(self):
        """Colours / texts of the position row: greyed out while Fix retry is off."""
        on = bool(self.v_fix.get())
        pos = settings["fix_retry_pos"]
        text = f"X: {pos[0]}   Y: {pos[1]}" if pos else "Not set yet - press Set position, then click the retry button."
        if self.pos_capturing:
            text = "Now click the retry button (Esc to cancel)..."
        self.fix_pos_title.configure(fg=App.TEXT if on else App.DIS_TEXT)
        self.fix_pos_value.configure(text=text, fg=App.SUB if on else App.DIS_TEXT)
        if on:
            self.fix_pos_btn.configure(fg=App.ACCENT_TEXT, bg=App.ACCENT_BG, cursor="hand2",
                                       text="Click now..." if self.pos_capturing else "Set position")
        else:
            self.fix_pos_btn.configure(fg=App.DIS_TEXT, bg=App.DIS_FILL, cursor="arrow",
                                       text="Set position")

    def on_fix_toggle(self):
        if running():
            self.v_fix.set(not self.v_fix.get())      # put the switch back
            self.say("Stop the macro before changing Fix retry.", error=True)
            return
        settings["fix_retry"] = bool(self.v_fix.get())
        if not settings["fix_retry"]:
            self.cancel_pos_capture()
        save_stats()
        self.refresh_fix_pos()
        if settings["fix_retry"] and not settings["fix_retry_pos"]:
            self.say("Fix retry on - now set the retry click position.", good=True)
        else:
            self.say("Fix retry " + ("on" if settings["fix_retry"] else "off"), good=True)

    def start_pos_capture(self):
        """Like OP Auto Clicker: press the button, then click anywhere - that spot is saved."""
        if not self.v_fix.get() or self.pos_capturing:
            return
        self.pos_capturing = True
        self.pos_wait_release = True      # let go of the mouse button that pressed "Set position"
        self.refresh_fix_pos()
        self.say("Click the retry button now (Esc to cancel).")
        set_move_cursor()                 # move cursor while picking ...
        self.make_pos_tip()               # ... with the live coordinates at its bottom right
        self.poll_pos_capture()

    def make_pos_tip(self):
        """Small click-through label that follows the cursor and shows its coordinates."""
        self.destroy_pos_tip()
        # screenshot-style tint over every screen (the click is taken by it, so it can't press
        # anything in the game while the position is being picked)
        try:
            gm = ctypes.windll.user32.GetSystemMetrics
            vx, vy, vw, vh = gm(76), gm(77), gm(78), gm(79)      # the whole virtual screen
            shade = tk.Toplevel(self)
            shade.overrideredirect(True)
            shade.configure(bg="#000000", cursor="fleur")
            shade.attributes("-topmost", True)
            shade.attributes("-alpha", POS_TINT_ALPHA)
            shade.geometry(f"{vw}x{vh}+{vx}+{vy}")
            self.pos_shade = shade
        except (tk.TclError, OSError):
            self.pos_shade = None
        tip = tk.Toplevel(self)
        tip.overrideredirect(True)
        tip.attributes("-topmost", True)
        lbl = tk.Label(tip, text="", font=("Consolas", 10, "bold"), fg="#ffffff", bg="#111827",
                       padx=6, pady=2, bd=1, relief="solid")
        lbl.pack()
        tip.update_idletasks()
        try:     # click-through + never takes focus
            hwnd = ctypes.windll.user32.GetAncestor(tip.winfo_id(), 2)
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x20 | 0x80 | 0x08000000)
        except Exception:  # noqa: BLE001
            pass
        self.pos_tip, self.pos_tip_label = tip, lbl

    def update_pos_tip(self, x, y):
        tip = getattr(self, "pos_tip", None)
        if tip is None:
            return
        try:
            self.pos_tip_label.configure(text=f"{x}, {y}")
            tip.update_idletasks()
            w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
            px, py = x + 18, y + 22                        # bottom right of the cursor
            if px + w > tip.winfo_screenwidth():          # near the screen edge: flip to the other side
                px = x - w - 8
            if py + h > tip.winfo_screenheight():
                py = y - h - 8
            tip.geometry(f"+{px}+{py}")
            tip.lift()
        except tk.TclError:
            self.pos_tip = None

    def destroy_pos_tip(self):
        for name in ("pos_tip", "pos_shade"):      # the coordinate label and the screen tint
            win = getattr(self, name, None)
            setattr(self, name, None)
            if win is not None:
                try:
                    win.destroy()
                except tk.TclError:
                    pass

    def cancel_pos_capture(self):
        self.destroy_pos_tip()
        restore_cursors()
        if self.pos_capturing:
            self.pos_capturing = False
            try:
                self.refresh_fix_pos()
            except tk.TclError:
                pass

    def poll_pos_capture(self):
        if not self.pos_capturing:
            return
        user32 = ctypes.windll.user32
        if user32.GetAsyncKeyState(0x1B) & 0x8000:           # Esc
            self.cancel_pos_capture()
            self.say("Cancelled.")
            return
        down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)  # left mouse button

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        self.update_pos_tip(int(pt.x), int(pt.y))             # live coordinates next to the cursor
        if self.pos_wait_release:
            if not down:
                self.pos_wait_release = False
        elif down:
            settings["fix_retry_pos"] = [int(pt.x), int(pt.y)]
            self.pos_capturing = False
            self.destroy_pos_tip()
            restore_cursors()
            save_stats()
            self.refresh_fix_pos()
            self.say(f"Saved position ({pt.x}, {pt.y}).", good=True)
            return
        self.after(15, self.poll_pos_capture)

    def on_move_shifted_pick(self, key):
        self.v_move_shifted.set(key)
        self.commit()

    def on_lowq_toggle(self):
        if running():
            self.v_lowq.set(not self.v_lowq.get())      # put the switch back
            self.say("Stop the macro before changing low quality mode.", error=True)
            return
        settings["low_quality"] = bool(self.v_lowq.get())
        save_stats()
        self.say("Low quality mode " + ("on" if settings["low_quality"] else "off"), good=True)

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
        ms = self.v_move_shifted.get()
        settings["move_shifted"] = ms if ms in MOVE_SHIFTED_OPTIONS else DEFAULT_MOVE_SHIFTED
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
        self.cancel_pos_capture()
        self.commit()
        self.app.settings_win = None
        self.destroy()


# ---- "Set position" (Fix retry): move cursor everywhere on screen while picking ----
_CURSOR_OCR_IDS = (32512, 32513, 32515, 32649)   # arrow, text, cross, hand: all become the move cursor
_cursor_replaced = False
POS_TINT_ALPHA = 0.65     # how dark the screen gets while picking the position (0 = clear, 1 = black)


def set_move_cursor():
    """Turn the system cursors into the Windows "move" cursor (four arrows), also over other windows."""
    global _cursor_replaced
    if _cursor_replaced:
        return
    try:
        u = ctypes.windll.user32
        u.LoadCursorW.restype = ctypes.c_void_p
        u.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        u.CopyIcon.restype = ctypes.c_void_p
        u.CopyIcon.argtypes = [ctypes.c_void_p]
        u.SetSystemCursor.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        for target in _CURSOR_OCR_IDS:
            handle = u.CopyIcon(u.LoadCursorW(None, 32646))     # IDC_SIZEALL
            if handle:
                u.SetSystemCursor(handle, target)    # (Windows owns / frees the copy)
        _cursor_replaced = True
    except Exception:  # noqa: BLE001
        pass


def restore_cursors():
    """Give the normal system cursors back."""
    global _cursor_replaced
    if not _cursor_replaced:
        return
    _cursor_replaced = False
    try:
        ctypes.windll.user32.SystemParametersInfoW(0x0057, 0, None, 0)   # SPI_SETCURSORS
    except Exception:  # noqa: BLE001
        pass


atexit.register(restore_cursors)      # never leave the move cursor behind


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
