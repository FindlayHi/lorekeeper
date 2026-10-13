"""Where Lorekeeper keeps its files, and its settings (config.json, edited by hand or from the tray)."""
import json, os

HOME = os.path.expanduser('~')
DIR = os.environ.get('LOREKEEPER_DIR') or os.path.join(os.environ.get('APPDATA') or os.path.join(HOME, '.config'), 'Lorekeeper')   # tests point it elsewhere
FILE = os.path.join(DIR, 'config.json')
MODELS = os.path.join(os.environ.get('LOCALAPPDATA') or DIR, 'Lorekeeper', 'models')   # big files: not roamed

DEFAULTS = {
    'hotkey': 'ctrl+alt+space',  # hold to talk, let go to ask; any key or mouse4/mouse5 (tray → Hotkey)
    'hotkeyEverywhere': False,   # False: the hotkey only acts while a game is in front, and passes through everywhere else,
                                 # so another app that uses the same shortcut (another voice assistant, say) still gets it there
    'listen': False,             # listen mode: no key to hold, start with "Lorekeeper, …"
    'listenKey': 'ctrl+alt+l',   # turns listen mode on and off
    'followUpSeconds': 8,        # after an answer, this long to ask a follow-up without the wake word
    'ai': 'claude',              # who answers: claude (Claude Code on your Claude plan) or openai (any OpenAI-compatible server; tray → AI)
    'model': 'haiku',            # Claude Code: quick answers; "in detail" asks use deepModel
    'deepModel': 'sonnet',
    'aiUrl': '',                 # openai: the server, e.g. http://localhost:11434/v1 (Ollama), http://localhost:1234/v1 (LM Studio)
    'aiModel': '',               # openai: the model for quick answers (tray → AI lists the server's)
    'aiDeepModel': '',           # openai: for "in detail" and gear math; '' = aiModel
    'mic': '',                   # a microphone by name (tray → Microphone); '' = Windows' default input
    'whisper': 'base.en',        # base.en is quick on CPU; small.en hears names better
    'whisperDevice': 'cpu',      # cuda with an NVIDIA card and the CUDA libraries
    'voice': 'kokoro',           # kokoro: neural, on this PC; edge: Microsoft online; sapi: Windows' own (robotic)
    'kokoroVoice': 'af_nicole:0.5,bf_isabella:0.5',   # tray → Voice; or any kokoro voice or blend "a:0.5,b:0.5"
    'edgeVoice': 'en-GB-SoniaNeural',
    'pitch': '-8Hz',             # edge only: lower = throatier
    'rate': 0,                   # speed, -10..10
    'box': True,                 # show the question and answer in a small box too
    'boxSeconds': 12,
    'spoilers': False,           # True: answers ignore your progress notes
    'screen': True,              # "what is this item" sends a screenshot
    'lore': True,                # answer from the game's lore pack first (if its cartridge has one), the live wiki after
    'checkUpdates': True,        # once a day, ask GitHub whether there's a newer release (tray → Update when there is)
    'rommUrl': '',               # set by tray → RomM → Connect RomM… (the token is in Windows Credential Manager)
    'telemetry': None,           # anonymous install/daily-use counts (telemetry.py): None = not asked yet, asked once on first run
    'posthogKey': 'phc_CpjGEfKDMnBjL6dxg6Dwb8cBDUJAKRdj64ivGH3by5fB',   # PostHog project API key: write-only, safe to publish
    'posthogHost': 'https://us.i.posthog.com',
    'clipKeys': 'ctrl+f10',              # "clip it" presses this: Steam → Game Recording → "Save the last 30 seconds" (set it to Ctrl+F10), or Game Bar's win+alt+g
}


def load():
    try:
        with open(FILE, encoding='utf-8') as f:
            return {**DEFAULTS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(cfg):
    os.makedirs(DIR, exist_ok=True)
    with open(FILE, 'w', encoding='utf-8') as f:
        json.dump({k: v for k, v in cfg.items() if DEFAULTS.get(k) != v}, f, indent=1)
