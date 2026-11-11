"""First run of an installed Lorekeeper: what setup.ps1 does for a source checkout, done from the app.
  - the Kokoro voice model (~120 MB) downloads in the background, progress in the box; answers use Windows' voice until then
  - no Claude Code, and it's the AI picked? offer to install it (Anthropic's official installer, in a terminal window) and
    sign in, or point at tray → AI for Ollama / LM Studio / OpenAI
  - Claude Code there but signed out, or billing an API key instead of the plan? say so, with a click to sign in"""
import hashlib, os, shutil, subprocess, threading, time, urllib.request
import config

MODEL_URL = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/'
MODEL_FILES = ('kokoro-v1.0.int8.onnx', 'voices-v1.0.bin')
MODEL_SHA256 = {   # of the model-files-v1.0 release's files; a download that differs is thrown away (keep setup.ps1 in step)
    'kokoro-v1.0.int8.onnx': '6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb',
    'voices-v1.0.bin': 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'}
CLAUDE_INSTALL = 'irm https://claude.ai/install.ps1 | iex'
CLAUDE_SIGN_IN = 'claude auth login --claudeai'   # the Pro / Max plan, not Console API billing


def missing_models():
    return [f for f in MODEL_FILES if not os.path.exists(os.path.join(config.MODELS, f))]


def download_models(progress=lambda done, total: None):
    """Fetch the missing model files, each to a .part file renamed when whole and matching its SHA-256 (a mismatch raises
    and leaves nothing behind). Returns True when all are present."""
    os.makedirs(config.MODELS, exist_ok=True)
    todo = missing_models()
    sizes, got = {}, 0
    for f in todo:
        try:
            req = urllib.request.Request(MODEL_URL + f, method='HEAD', headers={'User-Agent': 'Lorekeeper'})
            sizes[f] = int(urllib.request.urlopen(req, timeout=20).headers.get('Content-Length') or 0)
        except Exception:
            sizes[f] = 0
    total = sum(sizes.values())
    for f in todo:
        dest = os.path.join(config.MODELS, f)
        part, h = dest + '.part', hashlib.sha256()
        with urllib.request.urlopen(urllib.request.Request(MODEL_URL + f, headers={'User-Agent': 'Lorekeeper'}), timeout=60) as r, open(part, 'wb') as out:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                got += len(chunk)
                progress(got, total)
        if h.hexdigest() != MODEL_SHA256[f]:
            os.remove(part)
            raise ValueError(f'{f} does not match its expected checksum')
        os.replace(part, dest)
    return not missing_models()


def claude_installed():
    import brain   # its PATH includes where Claude Code's own installer puts it
    return bool(shutil.which('claude'))


def install_claude():
    """Anthropic's official Windows installer in a visible PowerShell window, then Claude Code itself to sign in."""
    cmd = (f"Write-Host 'Installing Claude Code (Anthropic''s official installer)...'; {CLAUDE_INSTALL}; "
           "$env:Path = \"$env:USERPROFILE\\.local\\bin;$env:Path\"; "
           "Write-Host ''; Write-Host 'Now sign in with your Claude Pro or Max account in the browser that opens.'; "
           f"{CLAUDE_SIGN_IN}; Write-Host ''; Write-Host 'Done. You can close this window.'")
    _console(cmd, stay=True)


def sign_in_claude():
    """Claude Code's own sign-in (it opens claude.ai in the browser) in a visible window that closes itself once signed in,
    and stays open with the reason if it didn't work."""
    import brain   # its PATH includes where Claude Code's own installer puts it
    exe = (shutil.which('claude') or 'claude').replace("'", "''")
    _console("Write-Host 'Sign in with your Claude Pro or Max account in the browser that opens.'; "
             f"& '{exe}' {CLAUDE_SIGN_IN.split(' ', 1)[1]}; "
             "if ($LASTEXITCODE) { Read-Host 'Sign-in did not finish. Press Enter to close' }")


def _console(cmd, stay=False):
    subprocess.Popen(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass'] + (['-NoExit'] if stay else []) + ['-Command', cmd],
                     creationflags=0x00000010)   # CREATE_NEW_CONSOLE: the person needs to see and type in it


_watching = threading.Event()


def wait_for_sign_in(box, then=lambda: None, every=3, give_up=600):
    """After opening an install or sign-in window (which can't tell us when it's done): watch Claude Code until it's
    signed in, say so once, then call `then`. One watcher at a time."""
    import brain
    if _watching.is_set():
        return
    _watching.set()

    def run():
        try:
            end = time.time() + give_up
            while time.time() < end:
                time.sleep(every)
                state, note = brain.claude_state()
                if state == 'plan':
                    return box.show('Claude Code', f"Signed in{f' ({note.title()})' if note else ''}. Hold the hotkey in a game and ask.", title=True)
                if state == 'api-key':
                    return box.show('Claude Code', api_key_warning(note), title=True)
        finally:
            _watching.clear()
            then()
    threading.Thread(target=run, daemon=True).start()


def api_key_warning(source):
    return (f'Claude Code is using {source}, so asks are billed to that key, not your Claude plan. '
            'Remove it from your environment variables to use the plan.')


def run(app, box):
    """Called once the app is up. Models first (no questions asked), then Claude Code if it's missing."""
    def models():
        if not missing_models():
            return
        box.show('Getting the voice ready', 'Downloading the voice (about 120 MB, once). Answers use the Windows voice until it is done.',
                 stay=True, title=True)
        last = [-1]

        def progress(done, total):
            pct = int(done * 100 / total) if total else 0
            if pct >= last[0] + 5:
                last[0] = pct
                box.show('Getting the voice ready', f'Downloading the voice: {pct}%', stay=True, title=True)
        try:
            ok = download_models(progress)
        except Exception as e:
            ok = False
            print('model download:', e)
        if ok:
            app.voice._kokoro = None   # loads on the next answer
            box.show('Voice ready', 'Lorekeeper has its voice. Hold the hotkey in a game and ask.', title=True)
        else:
            box.show('Voice download failed', 'Answers use the Windows voice for now. Lorekeeper tries again next time it starts.', title=True)

    def claude():
        if app.cfg.get('ai', 'claude') != 'claude':
            return
        if claude_installed():
            import brain
            state, note = brain.claude_state()
            if state == 'signed-out':
                box.show('Claude Code is signed out', 'Click here to sign in with your Claude Pro or Max plan, '
                         'or pick another AI in the tray: AI.', stay=True, title=True, hint='CLICK TO SIGN IN',
                         on_click=lambda: (sign_in_claude(), wait_for_sign_in(box)))
            elif state == 'api-key':
                box.show('Claude Code', api_key_warning(note), title=True)
            return

        def ask():
            from tkinter import messagebox
            if messagebox.askyesno('Lorekeeper needs Claude Code',
                                   'Lorekeeper answers through Claude Code, on the Claude Pro or Max plan you already have '
                                   '(no API key, no extra bill).\n\nInstall Claude Code now? A window opens with Anthropic\'s '
                                   'official installer, then asks you to sign in.\n\nNo Claude plan? Say no, then pick Ollama, '
                                   'LM Studio or an OpenAI key in the tray under AI.', parent=box.root):
                install_claude()
                box.show('Claude Code', 'Finish the install and sign in in the window that opened. Lorekeeper notices when you are signed in.',
                         stay=True, title=True)
                wait_for_sign_in(box)
            else:
                box.show('Claude Code', 'Install it any time (claude.com/claude-code), or pick another AI in the tray: AI.', stay=True, title=True)
        box.root.after(2500, ask)

    def both():
        claude()
        models()
    threading.Thread(target=both, daemon=True).start()
