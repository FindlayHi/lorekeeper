<p align="center"><a href="https://lorekeeper-cgv.pages.dev/"><img src="docs/og/card.png" alt="Lorekeeper. Hold a key. Ask out loud. Hear the answer." width="100%"></a></p>

<p align="center">
  Hold <kbd>Ctrl</kbd> <kbd>Alt</kbd> <kbd>Space</kbd> in any game, ask out loud, let go.<br>
  <b>A voice companion for PC games.</b> Lore, quest steps, items and builds, even clipping the moment,<br>answered in your ear for the game you're in, <b>without spoilers</b>.
</p>

<p align="center">
  <img alt="Windows" src="https://img.shields.io/badge/Windows_10%20%7C%2011-0b0b2b?style=for-the-badge&logo=windows11&logoColor=49c6ff">
  <img alt="Mac coming soon" src="https://img.shields.io/badge/Mac-coming_soon-3b1f6e?style=for-the-badge&logo=apple&logoColor=f2efe6">
  <img alt="Python" src="https://img.shields.io/badge/Python_3.10+-3b1f6e?style=for-the-badge&logo=python&logoColor=f2efe6">
  <img alt="Claude" src="https://img.shields.io/badge/Claude_Pro%20%7C%20Max-7a3cff?style=for-the-badge&logo=anthropic&logoColor=f2efe6">
  <img alt="Or Ollama, LM Studio, OpenAI" src="https://img.shields.io/badge/or-Ollama%20%7C%20LM_Studio%20%7C%20OpenAI-3b1f6e?style=for-the-badge">
  <img alt="Cost" src="https://img.shields.io/badge/~0.1%C2%A2_per_ask-e0284f?style=for-the-badge">
  <img alt="Offline voice" src="https://img.shields.io/badge/voice-offline-2f6bff?style=for-the-badge">
</p>

<p align="center"><sub><b>WORKS WITH</b> &nbsp; Steam &middot; Epic Games &middot; GOG &middot; RomM &middot; RetroArch &amp; emulators &middot; Xbox Game Bar &middot; plays nice with Discord voice chat</sub></p>

<p align="center"><b><a href="https://lorekeeper-cgv.pages.dev/">Website</a></b> &nbsp;·&nbsp; <a href="#install">Install</a> &nbsp;·&nbsp; <a href="#just-ask">Examples</a> &nbsp;·&nbsp; <a href="#settings">Settings</a></p>

<br>

## How it works

<table>
<tr>
<td width="25%" valign="top" align="center"><img src="docs/img/mic.svg" width="48" alt=""><br><b>1 · Hold &amp; ask</b><br><sub>Hold the hotkey and talk, or turn on listen mode and say "Lorekeeper, …". Whisper hears you <i>on your PC</i>; audio never leaves it.</sub></td>
<td width="25%" valign="top" align="center"><img src="docs/img/pad.svg" width="48" alt=""><br><b>2 · Game detected</b><br><sub>Matched from your Steam, Epic and GOG installs. Emulator? Say "I'm playing Chrono Trigger" or pick it in the tray.</sub></td>
<td width="25%" valign="top" align="center"><img src="docs/img/scroll.svg" width="48" alt=""><br><b>3 · Wiki + your AI</b><br><sub>That game's wiki is searched directly, then Claude answers through Claude Code on the plan you already have (no API key; about 3–5 s), or your own Ollama, LM Studio or OpenAI.</sub></td>
<td width="25%" valign="top" align="center"><img src="docs/img/speaker.svg" width="48" alt=""><br><b>4 · Hear it</b><br><sub>A natural voice reads it a sentence at a time, offline. A small box shows it too, on your second monitor.</sub></td>
</tr>
</table>

## Just ask

| | You say | Lorekeeper |
|---|---|---|
| <sub>ENTER THE GUNGEON</sub> | *"What does the Gilded Hydra do?"* | What it does, then its flavor text: **"Heads Up!"** |
| <sub>ENTER THE GUNGEON</sub> | *"What synergy did I just get?"* | Reads the banner from the last few seconds of your screen, then looks it up. |
| <sub>BALDUR'S GATE 3</sub> | *"What does the Phalar Aluve do?"* | Sing or Shriek, and what each does, plus the blade's inscription. |
| <sub>DEAD BY DAYLIGHT</sub> | *"What does Dead Hard do?"* | The perk in plain words, straight from the official wiki. |
| <sub>DEAD BY DAYLIGHT</sub> | *"What's my loadout?"* | Reads your perks, item and add-ons from their icons, then what each one does. |
| <sub>ELDEN RING</sub> | *"Who is Ranni?"* | The lore, only up to where you are. |
| <sub>ELDEN RING</sub> | *"I just beat Margit."* | "Noted." That moves your spoiler line forward. |
| <sub>ELDEN RING</sub> | *"Where do I go next?"* | The next step. Nothing past it. |
| <sub>ELDEN RING</sub> | *"Spoil it."* | The last question again, nothing held back. |
| <sub>DIABLO IV</sub> | *"Is this better than my helm?"* | The verdict first, then the numbers that decide it, for your build. |
| <sub>ANY GAME</sub> | *"Clip it."* | Saves the last 30 seconds with Steam's recorder. |

## Why Lorekeeper

<table>
<tr>
<td width="33%" valign="top"><h3>🛡️ Spoiler-safe</h3>Progress notes per game set the line. "Where do I go" gets the next step, not the ending. It also <b>learns as you play</b>: your class, build, act and choices come from what you ask.</td>
<td width="33%" valign="top"><h3>🎙️ Listen mode</h3>No key to hold. <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>L</kbd>, then just say "Lorekeeper, …". Follow-ups right after an answer don't need the name. Chatting with friends is ignored.</td>
<td width="33%" valign="top"><h3>🧠 10-minute memory</h3>"What did that sign say two minutes ago?" works. "Remember this as the vault code" keeps a screen for good.</td>
</tr>
<tr>
<td valign="top"><h3>⚔️ Gear tracker</h3>Hover an item: "save this as my helm". Later: "is this better than my helm?" compares stat by stat. Made for Diablo; works with any tooltip.</td>
<td valign="top"><h3>🖥️ Fullscreen-proof</h3>Exclusive fullscreen is fine: the hotkey, the voice and screen capture all work. Settable hotkey, including mouse side buttons.</td>
<td valign="top"><h3>🔓 Free &amp; open</h3>Runs on the Claude plan you have (about 0.1¢ per ask), or free on your own GPU with Ollama or LM Studio. Voice and speech-to-text run on your PC. All the code is right here.</td>
</tr>
</table>

## Install

You need **Windows 10 or 11** (Mac is coming soon) and one of: a **Claude Pro or Max** plan, a local model in **Ollama** or **LM Studio**, or an **OpenAI** (or other OpenAI-compatible) API key. See [Choose your AI](#choose-your-ai).

1. **[Download Lorekeeper-Setup.exe](https://github.com/FindlayHi/lorekeeper/releases/latest/download/Lorekeeper-Setup.exe)** and run it. There's no admin prompt, and it installs just for you.
2. Windows may say *"Windows protected your PC"*, because the installer isn't code-signed yet. Click **More info → Run anyway**.
3. Lorekeeper starts in the tray. The first time, it downloads its voice (about 120 MB), and if [Claude Code](https://claude.com/claude-code) isn't installed it offers to install it and helps you sign in. Using Ollama, LM Studio or OpenAI instead? Say no, then pick it in the tray under **AI**.

Then launch a game and hold <kbd>Ctrl</kbd> <kbd>Alt</kbd> <kbd>Space</kbd>.

### Choose your AI

Tray → **AI** picks who answers:

| | What you need | Notes |
|---|---|---|
| **Claude Code** *(default)* | a Claude Pro or Max plan | best answers: it also searches the web when the wiki pages Lorekeeper fetched don't cover it |
| **Ollama** | [Ollama](https://ollama.com) running, with a model pulled | free, on your GPU. A vision model (`gemma3:4b`, `qwen2.5vl:7b`) also reads the screen for "what is this" |
| **LM Studio** | [LM Studio](https://lmstudio.ai)'s server on, with a model loaded | same as Ollama |
| **OpenAI API** | an API key (tray → AI → **API key…**) | pay per use |
| **Custom server…** | any OpenAI-compatible `/v1` address: OpenRouter, Groq, llama.cpp, vLLM… | key optional |

Pick one, then pick its model from the list under it, and **Test**. Lorekeeper always fetches the game's wiki pages before it asks, so a model with no web search still answers from the wiki. When the pages don't cover it, it says so rather than guessing. Keys are kept in Windows Credential Manager, never in the settings file.

<details>
<summary><b>From source</b> (Python 3.10+)</summary>
<br>

```powershell
git clone https://github.com/FindlayHi/lorekeeper
cd lorekeeper
.\setup.ps1
```
`setup.ps1` makes a virtual environment, installs the dependencies, downloads the voice and adds a Start menu shortcut. To build the installer yourself: `pyinstaller packaging/lorekeeper.spec`, then `iscc /DAppVersion=x.y.z packaging\lorekeeper.iss`. GitHub Actions does both on every version tag.
</details>

<details>
<summary><b>🎮 Add a game: build a cartridge</b></summary>
<br>

A game's **cartridge** tells Lorekeeper which wiki to take icons from, which icon sets a player can't name from the art (perks, add-ons, status effects), and where on screen each sits. Carts live in [`assets/cartridges.json`](assets/cartridges.json), and the site serves them to every install, so a new cart needs no app update.

The easy way: clone the repo, open [Claude Code](https://claude.com/claude-code) in it and say *"make a cart for &lt;game&gt;"*. The `lorekeeper-cart` skill (in `.claude/skills/`) checks the wiki, asks you for a few screenshots, measures the HUD, proves the cart on your frames and opens a pull request. The tools it uses are in `tools/cart/` if you'd rather do it by hand: `wiki_probe.py`, `measure.py`, `check.py` and `eval_cart.py`.

Today a cart needs a wiki on wiki.gg or Fandom whose icon files share a name prefix (like `IconPerks_`).
</details>

<details>
<summary><b>🕹️ Works with RomM (and any emulator)</b></summary>
<br>

Retro games are detected from the emulator's window title: RetroArch, Dolphin, DuckStation, PCSX2, PPSSPP, Ryujinx, mGBA, Mesen and more.

Connect your [RomM](https://romm.app) library (tray → **RomM → Connect RomM…**, then approve the code in RomM; no password is typed into Lorekeeper) and you also get:
- **The right game, by its real name:** emulator titles and the RomM web player resolve to the game in your library, platform included. "Zelda Link to the Past" becomes *The Legend of Zelda: A Link to the Past (SNES)*.
- **Your walkthroughs:** text guides stored on the game in RomM (its GameFAQs import, or your uploads) are searched for the part you're on.
- **Your notes, both ways:** your own RomM notes on the game go with every question, and Lorekeeper's progress notes are kept on the game in RomM as a note titled "Lorekeeper".

Older games also get [StrategyWiki](https://strategywiki.org) walkthrough chapters for "where do I go" questions, with or without RomM.
</details>

<details>
<summary><b>🎙️ Listen mode, in detail</b></summary>
<br>

Press <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>L</kbd> (or tray → **Listen mode**, or say *"start listening"*). Start each question with **"Lorekeeper, …"**. For 8 seconds after an answer, ask a follow-up without the name. Say just *"Lorekeeper"* and it answers "Yes?" and waits.

The mic stays open, but Whisper only runs when someone's talking, so it costs almost nothing while you're quiet. It ignores everything while Lorekeeper is speaking (so it doesn't hear itself through speakers), while you hold the hotkey, and when no game is in front. Say *"stop listening"* or press the key again to turn it off.
</details>

<details>
<summary><b>⚔️ Gear tracker, in detail</b></summary>
<br>

Hover an item so its tooltip shows and say *"save this as my helm"*. Lorekeeper reads every stat into that game's gear file. Then:
- *"Is this better than my helm?"* gives the verdict first, then the two or three numbers that decide it, for your build. Gear math uses Sonnet.
- *"What's my gear?"* lists what's saved. *"Forget my second ring"* removes one.

Slots understand the usual words: helmet or head, chest piece, off hand, second ring, and so on.
</details>

<details>
<summary><b>🧠 Memory and notes, in detail</b></summary>
<br>

- **Screen:** the last 5 seconds at one frame a second, plus 10 minutes at one frame every 10 seconds, in memory only. "Just", "two minutes ago" and "earlier" choose which frames go with your question.
- **Icons:** in games whose things show only as icons (Dead by Daylight perks, items, add-ons, status effects, and buffs from teammates' perks), Lorekeeper matches them against the game wiki's icons on your PC and names them exactly; AI models can't tell them apart from the art. Each game's **cartridge** says which wiki, which icon sets, and where on the HUD each one sits, so they read right over any background. Cartridges are kept in [`cartridges.json`](docs/cartridges.json), fetched at startup, so more games arrive without an update.
- **Saved screens:** *"Remember this as the vault code"* keeps it on disk for that game; *"what was the vault code?"* brings it back.
- **Notes:** *"I just beat Margit"*, *"I'm in Act 2"* or *"note: I sided with the Emperor"* are saved at once, with no AI. Lasting facts your questions reveal are noted too.

Everything per game is a plain file you can edit, in `%APPDATA%\Lorekeeper\games\`: `<game>.md` (notes), `<game>.gear.json`, and `<game>/saved/`.
</details>

<details>
<summary><b>⚙️ Settings</b></summary>
<br>

<a id="settings"></a>Most settings are in the tray: game, hotkey, listen key, voice, spoilers, box and screen. Everything else is in tray → **Settings file** (`%APPDATA%\Lorekeeper\config.json`):

| Key | Default | |
|---|---|---|
| `hotkey` | `ctrl+alt+space` | hold to talk; any key, combo, or `mouse4`/`mouse5` |
| `hotkeyEverywhere` | `false` | off: the hotkey only acts while a game is in front, and anywhere else it passes through, so another app that uses the same shortcut still gets it there. On: it works everywhere |
| `listen` / `listenKey` | `false` / `ctrl+alt+l` | listen mode and its on/off key |
| `followUpSeconds` | `8` | how long after an answer a follow-up needs no name |
| `clipKeys` | `ctrl+f10` | in Steam → Settings → Game Recording, set **Save the last 30 seconds** to <kbd>Ctrl</kbd>+<kbd>F10</kbd>. Or use `win+alt+g` for Game Bar |
| `kokoroVoice` | `af_nicole:0.5,bf_isabella:0.5` | tray → **Voice**, or any [Kokoro voice](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) or blend |
| `voice` | `kokoro` | `edge` = Microsoft online voices; `sapi` = Windows' robotic one |
| `ai` | `claude` | `claude`, or `openai` for any OpenAI-compatible server (tray → **AI**) |
| `model` / `deepModel` | `haiku` / `sonnet` | Claude Code's models; say "in detail" or "tell me more" for the deep one |
| `aiUrl` / `aiModel` / `aiDeepModel` | | the server (e.g. `http://localhost:11434/v1`), its model, and an optional bigger one for "in detail" and gear math (blank = `aiModel`) |
| `whisper` / `whisperDevice` | `base.en` / `cpu` | `small.en` hears names better; `cuda` with an NVIDIA GPU |
| `spoilers` / `screen` | `false` / `true` | also in the tray |
| `boxWhileSpeaking` / `boxSeconds` | `false` / `12` | tray → **Keep it up while talking**: the box stays until the voice has finished, so you can read along; then it closes after `boxSeconds` |
| `font` / `fontSize` | *(pixel font)* / `0` | any installed font family, and its size in pixels, for the whole app: tray and answer box. `0` is the usual size for that font. tray → **Reset font** clears these |
| `boxFont` / `boxFontSize` | *(follow `font`)* | the answer box's own font and size; whichever is blank follows `font` / `fontSize` |
| `telemetry` | *(asked on first run)* | anonymous usage counts; also in the tray. See [Privacy](#privacy--usage-counts) |
</details>

<details>
<summary><b>🧩 Gotchas</b></summary>
<br>

- **Game running as admin?** Windows keeps its keys from non-admin apps, so run Lorekeeper as admin too.
- **Exclusive fullscreen** covers the box on that screen, but the voice still works. If a game shows black to screen capture, Lorekeeper says so and goes by your words.
- **Anti-cheat:** Lorekeeper reads the screen the way Discord and OBS do, and watches one hotkey like push-to-talk. It never touches the game's memory or files. "Clip it" sends one key press, to Steam.
- **Wikis and walkthroughs:** each game's own wiki is searched directly (wiki.gg, Fandom, bg3.wiki and more), and new games get their wiki found and remembered on first use. For "where do I go" and "how do I beat" questions, the matching chapter of the game's [StrategyWiki](https://strategywiki.org) walkthrough comes along too. That's ideal for older games.
- **Your own guides:** drop any text FAQ (`.txt` or `.md`) into `%APPDATA%\Lorekeeper\games\<game>\guides\`, and Lorekeeper searches it for the part you're asking about.
</details>

<details>
<summary><b>⌨️ Command line</b></summary>
<br>

```
python lorekeeper.py --ask "what does the casey do"   # typed, printed, for the game in front
python lorekeeper.py --games                          # installed games it knows
python lorekeeper.py --voices                         # sample wavs of every voice
```
</details>

## Privacy & usage counts

Your voice and its transcription stay on your PC. Your question (and a screenshot, when it asks about the screen) goes to the AI you picked: Claude through your own Claude Code login, or your Ollama / LM Studio (which stay on your PC) or API provider. Wiki searches go to the game's wiki. Nothing else about what you play or say leaves your PC.

To know how many people use it, Lorekeeper sends an **anonymous count** to [PostHog](https://posthog.com): an `installed` event once, and an `active` event at most once a day. Each carries only:

| | Example |
|---|---|
| a random install id, made on your PC and tied to nothing | `3f9c…` (in `%APPDATA%\Lorekeeper\telemetry.json`) |
| Lorekeeper's version and commit | `0.1.0`, `2b5b271` |
| Windows version | `Windows 11`, build `26200` |
| whether listen mode and RomM are on, and the voice engine | `true`, `false`, `kokoro` |
| which kind of AI answers (never its address or model) | `claude`, `ollama`, `lmstudio`, `openai`, `custom` |

Never your games, questions, answers, notes, screenshots, file paths, user name, RomM address, AI address, model or key, or hardware. No person profiles, and IP geolocation is turned off. The code is all in [`telemetry.py`](telemetry.py). The installer asks whether you want to share these counts, with neither answer picked for you (installs from source are asked the first time Lorekeeper runs). Nothing is sent unless you say yes.

**To change your answer:** tray → **Share anonymous usage counts**, or `"telemetry": true/false` in the settings file. Setting the `DO_NOT_TRACK=1` environment variable also turns it off and skips the question. Off means nothing is sent and no id is made.

<br>

<p align="center"><sub>Lorekeeper is free and open source. Not affiliated with Anthropic or any game publisher.</sub></p>
