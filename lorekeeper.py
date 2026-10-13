#!/usr/bin/env python3
"""Lorekeeper: hold Ctrl+Alt+Space in a game, ask out loud, let go, hear the answer.

It knows which game is in front (Steam, Epic, GOG installs; or pin one from the tray / "I'm playing X"), looks the
answer up on the game's wiki through `claude -p` on your Claude plan (or your own Ollama / LM Studio / OpenAI-compatible
server), and reads it aloud. Progress notes per game keep
answers spoiler-safe ("I just beat Margit"); "spoil it" re-asks without the guard. "Clip it" presses your clip key.
  lorekeeper.py                 run (tray icon)
  lorekeeper.py --ask "<q>"     one question for the game in front, typed, printed (no voice)
  lorekeeper.py --games         the installed games it knows, rebuilt
  lorekeeper.py --romm-connect <url>   pair with your RomM (approve the code it shows)
  lorekeeper.py --voices        sample wavs of the voices, to choose kokoroVoice
Settings: %APPDATA%/Lorekeeper/config.json. Log: log.jsonl beside it.
"""
import json, os, re, sys, threading, time

if sys.platform == 'win32':
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FROZEN = getattr(sys, 'frozen', False)   # the installed app (PyInstaller): no console, so output goes to a log file
if FROZEN:
    _logdir = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'Lorekeeper')
    os.makedirs(_logdir, exist_ok=True)
    sys.stdout = sys.stderr = open(os.path.join(_logdir, 'app.log'), 'a', encoding='utf-8', buffering=1)
    print(f"--- {__import__('time').strftime('%Y-%m-%d %H:%M:%S')} Lorekeeper starting", flush=True)
import brain, capture, commands, config, games, gear, listen, lookup, notes, icons, rag, romm, telemetry, updater, voice  # noqa: E402

LOG = os.path.join(config.DIR, 'log.jsonl')
TURN_SECS = 600

def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def log(row):
    os.makedirs(config.DIR, exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'at': time.strftime('%Y-%m-%d %H:%M:%S'), **row}) + '\n')


class App:
    def __init__(self, cfg, box=None):
        import ears, capture
        self.cfg, self._box = cfg, box
        brain.use(cfg)
        self.ears = ears.Ears(cfg['whisper'], cfg['whisperDevice'])
        self.ears.mic = cfg['mic']
        self.voice = voice.Voice(cfg['voice'], cfg['edgeVoice'], cfg['rate'], cfg['pitch'], cfg['kokoroVoice'], config.MODELS)
        self.warm = brain.Warm()
        self.game, self.gen, self.frames, self.seen, self.looking = None, 0, [], '', None
        self.screen = capture.Screen(active=lambda: bool(self.game))
        self.turns, self.last, self.last_q, self.spoil_next = [], '', '', False
        self.down_at, self._spoke_at, self.hk = 0, 0, None
        self.listener = listen.Listener(self.ears, self.heard, self.listen_muted, cfg['followUpSeconds'], self.woke, self.hint)
        if cfg['listen']:
            self.set_listen(True, quiet=True)
        self._games, self._pin = games.index(), games.pinned()   # in memory: the hook asks in_game() on every press
        threading.Thread(target=icons.prefetch, args=(self._games, notes.FOLDER), daemon=True).start()   # not on the first question
        threading.Thread(target=self._watch_game, daemon=True).start()

    def in_game(self):
        """Is a game in front right now? No file reads: it runs inside the keyboard hook."""
        if self.cfg['hotkeyEverywhere']:
            return True
        exe, title = games.win.front()
        if not exe:
            return False
        if romm.EMULATORS.search(exe) or (self.cfg.get('rommUrl') and 'romm' in (title or '').lower()):
            return True   # an emulator, or the RomM web player
        if games.LAUNCHERS.search(exe):
            return False
        return bool(self._pin) or bool(games.match(exe, title, self._games))

    def _watch_game(self):
        while True:   # cheap: one window call and a list scan; keeps the tray and the screen buffer current
            try:
                g, exe = games.current()
                self._games, self._pin = games.index(), games.pinned()
                if g or not games.LAUNCHERS.search(exe or ''):   # alt-tabbed to a browser or Discord: keep the last game
                    self.game = g
            except Exception as e:
                print('game:', e)
            time.sleep(2)

    @property
    def box(self):
        return self._box if self.cfg['box'] else None

    def say(self, question, answer, title=False):
        self.voice.say(answer)
        if self.box:
            self.box.show(question, answer, title=title)
        if self.listener.on:
            self.after_speaking()

    def hint(self):
        return ', '.join(([self.game['name']] if self.game else []) + notes.names(self.game))

    def after_speaking(self):
        """Once the answer has been said, a follow-up needs no wake word for a few seconds."""
        def wait():
            time.sleep(0.3)
            while self.voice.busy():
                time.sleep(0.1)
            self.listener.follow_up()
        threading.Thread(target=wait, daemon=True).start()

    # listen mode
    def set_listen(self, on, quiet=False):
        try:
            self.listener.start() if on else self.listener.stop()
        except Exception as e:
            return self.say('', f"Can't hear the mic: {e}")
        self.cfg['listen'] = on
        config.save(self.cfg)
        if not quiet:
            self.say('Listen mode', 'Listening. Say Lorekeeper, then your question.' if on else 'Stopped listening.', title=True)

    def toggle_listen(self):
        self.set_listen(not self.listener.on)

    def listen_muted(self):
        """Skip the mic: it would hear Lorekeeper's own voice, the hotkey is in use, or no game is in front."""
        now = time.time()
        if self.voice.busy():
            self._spoke_at = now
            return True
        return now - self._spoke_at < 0.5 or bool(self.hk and self.hk.held) or not self.in_game()

    def woke(self):
        self.voice.say('Yes?')
        if self.box:
            self.box.show('👂 Listening…', '', stay=True)

    def heard(self, q):
        self.gen += 1
        g, _ = games.current()
        self.game = g or self.game
        self.look(icons.asks(q, self.game, notes.FOLDER) or capture.wants(q))
        self.handle(q, self.gen)

    # hotkey
    def down(self):
        self.gen += 1
        self.voice.stop()
        self.down_at = time.time()
        g, _ = games.current()
        self.game = g or self.game
        try:
            self.ears.start()
        except Exception as e:
            return self.say('', f"Can't hear the mic: {e}")
        if self.box:
            self.box.show(f"🎧 {self.game['name'] if self.game else 'Listening'}…", '', stay=True)
        self.looking = threading.Thread(target=self.look, daemon=True)
        self.looking.start()
        threading.Thread(target=self.warm.prime, args=(self.cfg['model'], self.cfg['spoilers']), daemon=True).start()

    def look(self, icons_too=True):
        """The screen at key-down, and what its icons show (Dead by Daylight perks...), read while the question is still being said."""
        self.seen = ''
        self.frames = self.screen.now() if self.cfg['screen'] else []
        if self.frames and icons_too and icons.cart(self.game, notes.FOLDER):
            try:
                self.seen = icons.text(self.screen.full, self.game, notes.FOLDER)
            except Exception as e:
                print('icons:', e)

    def cancel(self):
        self.ears.stop()
        self.warm.drop()
        if self.box:
            self.box.hide()

    def up(self):
        gen = self.gen
        audio = self.ears.stop()
        if time.time() - self.down_at < 0.35:   # a tap: that just stopped the voice
            self.warm.drop()
            return self.box and self.box.hide()
        q = self.ears.text(audio, self.hint())
        if gen != self.gen:
            return
        if not q:
            self.warm.drop()
            return self.say('', "Didn't catch that.")
        self.handle(q, gen)

    def handle(self, q, gen):
        if self.box:
            self.box.show(q, '…', stay=True)
        c = commands.parse(q)
        if c:
            self.warm.drop()
            return self.command(q, *c)
        self.answer(q, gen)

    def command(self, q, action, arg):
        g = self.game
        if action == 'stop':
            self.voice.stop()
            return self.box and self.box.hide()
        if action in ('listen_on', 'listen_off'):
            return self.set_listen(action == 'listen_on')
        if action == 'repeat':
            return self.say(q, self.last or 'Nothing to repeat yet.')
        if action == 'clip':
            if not self.cfg['clipKeys']:
                return self.say(q, 'No clip key set. Put your Steam clip key in the config as clipKeys.')
            import hotkey
            hotkey.press(self.cfg['clipKeys'])
            log({'game': g and g['name'], 'q': q, 'a': 'clipped'})
            return self.box and self.box.show(q, '🎬 Clipped.')   # silent: a voice line would end up in the clip
        if action == 'playing':
            g = games.find(arg, games.index())
            exe, _ = games.win.front()
            games.pin(g, '' if games.LAUNCHERS.search(exe or '') else exe)
            self.game = g
            return self.say(q, f"Got it, {g['name']}.")
        if action == 'auto':
            games.unpin()
            self.game, _ = games.current()
            return self.say(q, f"Detecting games again. Now: {self.game['name']}." if self.game else 'Detecting games again.')
        if action.startswith('gear') or action == 'snap':
            if not g:
                return self.say(q, "Which game? Say I'm playing, then the name.")
            return self.gear_command(q, action, arg, g)
        if action == 'note':
            if not g:
                return self.say(q, "Which game? Say I'm playing, then the name.")
            notes.add(g, arg)
            return self.say(q, 'Noted.')
        if action == 'spoil':
            if not self.last_q:
                self.spoil_next = True
                return self.say(q, 'Spoilers on for the next question.')
            self.spoil_next = True
            return self.answer(self.last_q, self.gen)

    def gear_command(self, q, action, arg, g):
        if action == 'gear_list':
            return self.say(q, gear.summary(g))
        if action == 'gear_forget':
            where = gear.slot(arg)
            return self.say(q, f'Forgot your {where}.' if gear.forget(g, where) else f'No {where} was saved.')
        if not self.frames:
            return self.say(q, "I can't see the screen, so I can't save it.")
        if action == 'snap':
            capture.save_shot(notes.FOLDER, g, self.frames[-1][1], arg)
            return self.say(q, f'Saved the screen as {arg}.' if arg else 'Saved the screen.')
        where = gear.slot(arg)   # gear_save: read the hovered tooltip
        if self.box:
            self.box.show(q, f'Reading the item for your {where}…', stay=True)
        shots = capture.Screen.files(self.frames[-1:], '')
        try:
            item = brain.extract(shots, self.cfg['model'])
        finally:
            for path, _ in shots:
                _rm(path)
        if item.get('error') or not item.get('name'):
            return self.say(q, "I couldn't read an item there. Hover over it so its tooltip shows, then say it again.")
        gear.save(g, where, item)
        log({'game': g['name'], 'q': q, 'a': f'saved {where}', 'item': item})
        return self.say(q, f"Saved {item['name']} as your {where}.")

    def lore(self, q):
        """What the game's lore pack says about the question, '' if the cartridge has none or nothing in it is sure."""
        try:
            c = self.cfg['lore'] and icons.cart(self.game, notes.FOLDER)
            return rag.context(self.game['name'], c['lore'], q, config.DIR) if c else ''
        except Exception as e:
            print('lore:', e)
            return ''

    def answer(self, q, gen):
        started = time.time()
        spoilers = self.cfg['spoilers'] or self.spoil_next
        self.spoil_next = False
        if self.looking:
            self.looking.join(8)   # the key-down look: icons take a couple of seconds
        seen = self.seen if capture.wants(q) or icons.asks(q, self.game, notes.FOLDER) else ''
        shots = capture.Screen.files(self.frames, q) if self.cfg['screen'] and capture.wants(q) else []
        saved = capture.saved_for(notes.FOLDER, self.game, q)   # on disk for good: never deleted below
        kit = gear.text(self.game) if gear.wants(q) else ''
        model = self.cfg['deepModel'] if brain.DEEP.search(q) or (kit or shots) and gear.wants(q) else self.cfg['model']   # gear math: the bigger model
        p = self.warm.take(model, spoilers)
        if not p:
            return self.say(q, 'Claude Code is not installed. Install it and sign in, or pick another AI in the tray, then ask again.')
        if capture.wants(q) and not self.cfg['screen'] and not saved:
            self.voice.say("Use the screen is off in the tray, so I can't look. Going by your words.")
        elif capture.wants(q) and not shots and not saved and not seen:
            self.voice.say("I couldn't see the screen, so going by your words.")
        now = time.time()
        self.turns = [t for t in self.turns if now - t['t'] < TURN_SECS][-3:]
        wiki = '' if shots or saved or kit else self.lore(q) or lookup.wiki(q, self.game and self.game['name'], folder=notes.FOLDER, progress=notes.read(self.game, 3))   # a screenshot names the thing; the model searches then
        wiki = '\n\n'.join(x for x in (romm.context(self.game, q), wiki) if x)   # RomM walkthroughs first: they're the player's own
        text = brain.request(q, self.game, notes.read(self.game), self.turns, wiki, kit, seen)
        spoken = []

        def streamed(s):   # speak each sentence as it completes; the last, maybe partial, waits
            if gen != self.gen:
                return
            s = brain.spoken(s)   # the saved note and any Sources list are never spoken
            parts = voice.split(s)[:-1]
            if parts[:len(spoken)] != spoken:
                return   # a new message began (text before a search): wait for the result
            for part in parts[len(spoken):]:
                spoken.append(part)
                self.voice.say(part)
            if self.box:
                self.box.show(q, s, stay=True)
        try:
            a, usd = brain.ask(p, text, saved + shots, streamed)
        finally:
            for path, _ in shots:
                _rm(path)
        a, learned = brain.split_note(a)
        if learned and self.game:
            notes.add(self.game, learned + ' (learned)')
        if gen != self.gen:
            return
        rest = voice.split(a)
        if rest[:len(spoken)] == spoken:
            rest = rest[len(spoken):]
        else:
            self.voice.stop()   # what was spoken was not the answer after all
        self.voice.say(' '.join(rest))
        if self.box:
            self.box.show(q, a)
        if self.listener.on:
            self.after_speaking()
        self.last, self.last_q = a, q
        self.turns.append({'t': time.time(), 'q': q, 'a': a})
        log({'game': self.game and self.game['name'], 'q': q, 'a': a, 'usd': round(usd, 5), 'secs': round(time.time() - started, 1),
             'model': model, 'spoilers': spoilers, 'shots': len(shots), 'saved': len(saved), 'gear': bool(kit), 'learned': learned,
             'icons': seen.split('\n', 1)[0].split(': ', 1)[-1] if seen else ''})


def tray(app, box):
    import art, hotkey, pystray

    def pin_to(g):
        def do(*_):
            games.pin(g)
            app.game, app._pin = g, games.pinned()
        return do

    def auto(*_):
        games.unpin()
        app._pin = None
        app.game, _ = games.current()

    def pick_list():
        gs = sorted({g['name']: g for g in games.index()}.values(), key=lambda g: g['name'].lower())
        return [pystray.MenuItem('Auto-detect', auto, checked=lambda _: games.pinned() is None), pystray.Menu.SEPARATOR] + \
               [pystray.MenuItem(g['name'], pin_to(g), checked=lambda _, n=g['name']: bool(games.pinned()) and games.pinned()['game']['name'] == n)
                for g in gs] + [pystray.Menu.SEPARATOR, pystray.MenuItem('Rescan installed games', lambda *_: games.build())]

    def flip(k):
        def do(*_):
            app.cfg[k] = not app.cfg[k]
            config.save(app.cfg)
        return do

    def quit_(icon, _):
        icon.stop()
        app.warm.drop()
        box.quit()

    def set_hotkey(*_):
        box.show('Set the hotkey', 'Press the key, combo or mouse side button you want. Esc to cancel.', stay=True, title=True)

        def done(combo):
            if combo:
                app.cfg['hotkey'] = combo
                config.save(app.cfg)
            box.show('Hotkey', f"Hold {hotkey.pretty(app.hk.combo)} and ask." if combo else 'Unchanged.', title=True)
        app.hk.record(done)

    def set_listen_key(*_):
        box.show('Set the listen key', 'Press the key or combo that turns listen mode on and off. Esc to cancel.', stay=True, title=True)

        def done(combo):
            if combo:
                app.cfg['listenKey'] = combo
                config.save(app.cfg)
            box.show('Listen key', f"{hotkey.pretty(app.lk.combo)} turns listen mode on and off." if combo else 'Unchanged.', title=True)
        app.lk.record(done)

    def connect_romm(*_):
        def ask():   # on the Tk thread
            from tkinter import simpledialog
            addr = simpledialog.askstring('Connect RomM', 'Your RomM address, e.g. http://192.168.0.50:3010',
                                          initialvalue=romm.url() or 'http://', parent=box.root)
            if not addr or addr.strip() in ('http://', 'https://'):
                return

            def on_code(code, approve):
                plain = ' This address is plain http: the token will cross your network unencrypted.' if approve.startswith('http://') else ''
                box.show('Connect RomM', f'Approve code {code} in RomM. Opening it in your browser…{plain}', stay=True, title=True)
                os.startfile(approve)

            def on_done(user, err):
                app.cfg['rommUrl'] = romm.url() or app.cfg.get('rommUrl', '')
                box.show('RomM', f'Connected as {user}. Play from RomM or an emulator and just ask.' if user else err, title=True)
                app.voice.say('RomM connected.' if user else err)
            romm.pair(addr, on_code, on_done)
        box.root.after(0, ask)

    def disconnect_romm(*_):
        romm.forget()
        app.cfg.pop('rommUrl', None)
        cfg = config.load()
        cfg.pop('rommUrl', None)
        config.save(cfg)
        box.show('RomM', 'Disconnected. Remove the "Lorekeeper" device in RomM to revoke it there too.', title=True)

    def use_voice(v):
        def do(*_):
            app.voice.stop()
            app.voice.kokoro_voice = app.cfg['kokoroVoice'] = v
            config.save(app.cfg)
            app.voice.say(voice.PREVIEW)
        return do

    def voice_list():
        kokoro = app.cfg['voice'] == 'kokoro'
        return [pystray.MenuItem(name, use_voice(v), checked=lambda _, v=v: kokoro and app.cfg['kokoroVoice'] == v, radio=True, enabled=kokoro)
                for name, v in voice.VOICES.items()] + [pystray.Menu.SEPARATOR,
                pystray.MenuItem('Hear a sample', lambda *_: (app.voice.stop(), app.voice.say(voice.PREVIEW)))]

    menu = pystray.Menu(
        pystray.MenuItem(lambda _: f"Playing: {app.game['name'] if app.game else 'nothing detected'}", None, enabled=False),
        pystray.MenuItem('Pick the game', pystray.Menu(pick_list)),
        pystray.MenuItem(lambda _: f'Hotkey: {hotkey.pretty(app.hk.combo)}  (change…)', set_hotkey),
        pystray.MenuItem('Listen mode (say "Lorekeeper, …")', lambda *_: app.toggle_listen(), checked=lambda _: app.listener.on),
        pystray.MenuItem(lambda _: f'Listen key: {hotkey.pretty(app.lk.combo)}  (change…)', set_listen_key),
        pystray.MenuItem('Hotkey works outside games too', flip('hotkeyEverywhere'), checked=lambda _: app.cfg['hotkeyEverywhere']),
        pystray.MenuItem('Voice', pystray.Menu(voice_list)),
        pystray.MenuItem('RomM', pystray.Menu(lambda: [
            pystray.MenuItem(f'Connected: {romm.url()}', None, enabled=False), pystray.MenuItem('Disconnect', disconnect_romm)]
            if romm.connected() else [pystray.MenuItem('Connect RomM…', connect_romm)])),
        pystray.MenuItem('Spoilers', flip('spoilers'), checked=lambda _: app.cfg['spoilers']),
        pystray.MenuItem('Show answers in a box', flip('box'), checked=lambda _: app.cfg['box']),
        pystray.MenuItem('Use the screen', flip('screen'), checked=lambda _: app.cfg['screen']),
        pystray.MenuItem("This game's notes", lambda *_: app.game and (notes.add(app.game, 'notes opened') if not os.path.exists(notes.path(app.game)) else None,
                                                                     os.startfile(notes.path(app.game))), enabled=lambda _: bool(app.game)),
        pystray.MenuItem('Share anonymous usage counts', flip('telemetry'), checked=lambda _: app.cfg['telemetry'] is True),
        pystray.MenuItem('Settings file', lambda *_: (config.save(app.cfg), os.startfile(config.FILE))),
        pystray.MenuItem('Ask log', lambda *_: os.path.exists(LOG) and os.startfile(LOG)),
        pystray.MenuItem('Quit', quit_))
    icon = art.tray_icon(pystray, 'Lorekeeper', 'Lorekeeper', menu)   # the pixel book; its cover turns blue in listen mode

    # Lorekeeper's own menu, drawn like the site; the native one above stays as the fallback
    from panel import Item, Panel

    def games_page():
        gs = sorted({g['name']: g for g in games.index()}.values(), key=lambda g: g['name'].lower())
        pinned = lambda: (games.pinned() or {}).get('game', {}).get('name')
        return ([Item('Auto-detect', action=auto, radio=lambda: games.pinned() is None)]
                + [Item(g['name'], action=pin_to(g), radio=lambda n=g['name']: pinned() == n) for g in gs]
                + [Item('Rescan installed games', action=lambda: games.build(), note='scan')])

    def use_mic(name):
        def do():
            app.cfg['mic'] = app.ears.mic = name
            config.save(app.cfg)
            if app.listener.on:   # listen mode: reopen on the new mic
                app.listener.stop()
                app.listener.start()
        return do

    def mics_page():
        import ears
        names = ears.inputs()
        cur = app.cfg['mic'] if app.cfg['mic'] in names else ''
        return ([Item('Windows default', action=use_mic(''), radio=lambda: not app.cfg['mic'] or app.cfg['mic'] not in names)]
                + [Item(n, action=use_mic(n), radio=lambda n=n: app.cfg['mic'] == n) for n in names])

    def voices_page():
        kokoro = app.cfg['voice'] == 'kokoro'
        return [Item(name, action=use_voice(v), radio=lambda v=v: kokoro and app.cfg['kokoroVoice'] == v, enabled=kokoro)
                for name, v in voice.VOICES.items()]

    def romm_page():
        host = romm.url().split('://', 1)[-1]
        return [Item('Connected to', enabled=False, note=host), Item('Disconnect', action=disconnect_romm)]

    ai_models = {'url': None, 'ids': [], 'err': ''}   # the server's models, fetched off the Tk thread

    def redraw():
        box.root.after(0, lambda: [p.draw() for p in pnl.panes()])

    def fetch_models(then=None):
        def run():
            url = app.cfg.get('aiUrl')
            try:
                ids, err = brain.models(app.cfg), ''
            except Exception as e:
                ids, err = [], str(e)
            ai_models.update(url=url, ids=ids, err=err)
            if ids and app.cfg.get('aiModel') not in ids:   # a new server: start on its first model
                app.cfg['aiModel'] = ids[0]
                config.save(app.cfg)
            redraw()
            if then:
                then(ids, err)
        threading.Thread(target=run, daemon=True).start()

    def ai_changed():
        app.warm.drop()   # the process started ahead belongs to the old AI
        config.save(app.cfg)
        brain.use(app.cfg)

    def use_ai(k):
        def do():
            if k == 'claude':
                app.cfg['ai'] = 'claude'
                ai_changed()
                return box.show('AI', 'Claude Code answers, on your Claude plan.' if brain.claude_ok() else
                                "Claude Code answers, but it isn't installed yet: claude.com/claude-code", title=True)
            app.cfg['ai'], app.cfg['aiUrl'] = 'openai', brain.PRESETS[k][1]
            ai_changed()
            box.show('AI', f'Asking {brain.name()} for its models…', stay=True, title=True)
            fetch_models(lambda ids, err: box.show('AI', err or (
                f"{brain.name()} answers with {app.cfg['aiModel']}. Pick another model under AI." if ids else
                f'{brain.name()} has no models yet.' + (' Pull one with: ollama pull gemma3:4b' if k == 'ollama' else
                                                       ' Download and load one in LM Studio.' if k == 'lmstudio' else '')), title=True))
        return do

    def custom_ai():
        def ask():   # on the Tk thread
            from tkinter import simpledialog
            addr = simpledialog.askstring('Custom AI server', 'An OpenAI-compatible address, ending in /v1\ne.g. https://openrouter.ai/api/v1',
                                          initialvalue=app.cfg.get('aiUrl') or 'http://', parent=box.root)
            if not addr or addr.strip() in ('http://', 'https://'):
                return
            app.cfg['ai'], app.cfg['aiUrl'] = 'openai', addr.strip().rstrip('/')
            ai_changed()
            box.show('AI', 'Asking the server for its models…', stay=True, title=True)
            fetch_models(lambda ids, err: box.show('AI', err or (f"Answering with {app.cfg['aiModel']}. Pick another model under AI." if ids else
                                                                 'The server lists no models. Set aiModel in the settings file.'), title=True))
        box.root.after(0, ask)

    def use_model(m):
        def do():
            app.cfg['aiModel'] = m
            ai_changed()
        return do

    def set_ai_key():
        def ask():
            from tkinter import simpledialog
            url = app.cfg.get('aiUrl', '')
            plain = url.startswith('http://') and not re.match(r'http://(localhost|127\.|\[::1\])', url)
            k = simpledialog.askstring('API key', f'The API key for {brain.name()} (blank removes it). Kept in Windows Credential Manager.'
                                       + ('\n\nThis address is plain http: the key crosses your network unencrypted.' if plain else ''),
                                       show='*', parent=box.root)
            if k is None:
                return
            brain.set_key(k.strip())
            box.show('AI', 'Key saved.' if k.strip() else 'Key removed.', title=True)
            if brain.http():
                fetch_models()
        box.root.after(0, ask)

    def test_ai():
        def run():
            box.show('AI', f'Testing {brain.name()}…', stay=True, title=True)
            ok, msg = brain.test(app.cfg)
            box.show('AI', msg, title=True)
        threading.Thread(target=run, daemon=True).start()

    def ai_page():
        k = brain.kind(app.cfg)
        rows = [Item('Claude Code (your Claude plan)', action=use_ai('claude'), radio=lambda: brain.kind(app.cfg) == 'claude')]
        rows += [Item(n if p != 'openai' else 'OpenAI API', action=use_ai(p), radio=lambda p=p: brain.kind(app.cfg) == p)
                 for p, (n, _) in brain.PRESETS.items()]
        rows.append(Item('Custom server…', action=custom_ai, radio=lambda: brain.kind(app.cfg) == 'custom'))
        if k != 'claude':
            if ai_models['url'] != app.cfg.get('aiUrl'):
                ai_models['url'] = app.cfg.get('aiUrl')   # once per address; the page redraws when they arrive
                fetch_models()
            rows.append(Item('MODEL', header=True))
            if ai_models['ids']:
                rows += [Item(m, action=use_model(m), radio=lambda m=m: app.cfg.get('aiModel') == m) for m in ai_models['ids']]
            else:
                rows.append(Item(app.cfg.get('aiModel') or 'No models found', enabled=False, note='' if app.cfg.get('aiModel') else 'none'))
            rows.append(Item('API key…', action=set_ai_key, note=lambda: 'set' if brain.key() else 'none'))
        rows.append(Item('Test', action=test_ai, note=lambda: brain.name(app.cfg)))
        return rows

    def notes_open():
        if not os.path.exists(notes.path(app.game)):
            notes.add(app.game, 'notes opened')
        os.startfile(notes.path(app.game))

    def items():
        up = getattr(app, 'updater', None) and app.updater.available
        return ([Item(f'Update to {up[0]}', action=lambda: app.updater.update(box), note='new')] if up else []) + [
            Item('GAME', header=True),
            Item('Pick the game', sub=games_page),
            Item("This game's notes", action=notes_open, enabled=lambda: bool(app.game)),
            Item('TALK', header=True),
            Item(lambda: f'Hotkey: {hotkey.pretty(app.hk.combo)}', action=set_hotkey, note='change'),
            Item('Works outside games too', action=flip('hotkeyEverywhere'), check=lambda: app.cfg['hotkeyEverywhere']),
            Item('Listen mode', action=app.toggle_listen, check=lambda: app.listener.on),
            Item(lambda: f'Listen key: {hotkey.pretty(app.lk.combo)}', action=set_listen_key, note='change'),
            Item('Microphone', sub=mics_page),
            Item('VOICE & ANSWERS', header=True),
            Item(lambda: f'AI: {brain.name(app.cfg)}', sub=ai_page),
            Item('Voice', sub=voices_page),
            Item('Spoilers', action=flip('spoilers'), check=lambda: app.cfg['spoilers']),
            Item('Show answers in a box', action=flip('box'), check=lambda: app.cfg['box']),
            Item('Use the screen', action=flip('screen'), check=lambda: app.cfg['screen']),
            Item('MORE', header=True),
            Item('RomM', sub=romm_page) if romm.connected() else Item('Connect RomM', action=connect_romm, note='pair'),
            Item('Share anonymous usage counts', action=flip('telemetry'), check=lambda: app.cfg['telemetry'] is True),
            Item('Settings file', action=lambda: (config.save(app.cfg), os.startfile(config.FILE))),
            Item('Ask log', action=lambda: os.path.exists(LOG) and os.startfile(LOG)),
            Item('Check for updates', action=check_now, note=telemetry.VERSION),
            Item('Quit', action=lambda: quit_(icon, None)),
        ]

    def check_now():
        def run():
            box.show('Updates', 'Checking…', title=True)
            found = app.updater.check()
            if found:
                box.show('Updates', f'Lorekeeper {found[0]} is out. Click here to update (your notes and settings stay).',
                         title=True, on_click=lambda: app.updater.update(box), hint='CLICK TO UPDATE')
            else:
                box.show('Updates', f'You have the latest Lorekeeper ({telemetry.VERSION}).', title=True)
        threading.Thread(target=run, daemon=True).start()

    def status():
        playing = f"Playing: {app.game['name']}" if app.game else 'No game in front'
        return playing, f'Hold {hotkey.pretty(app.hk.combo)} to ask · {hotkey.pretty(app.lk.combo)} listen mode'
    pnl = Panel(box.root, items, status)
    icon.on_click = lambda: pnl.open()
    icon.run_detached()

    def watch_listen():   # listen mode flips from the menu, the listen key and startup, so follow the listener itself
        while True:
            icon.listening = app.listener.on
            time.sleep(0.5)
    threading.Thread(target=watch_listen, daemon=True).start()
    return icon


def selftest(ci=False):
    """ci: a build machine with no mic, speakers, screen or Claude Code; still checks every library loads and works."""
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            print(f'ok   {name}: {fn()}', flush=True)
        except Exception as e:
            ok = False
            print(f'FAIL {name}: {type(e).__name__}: {e}', flush=True)
    import tempfile
    import numpy as np
    check('voice (kokoro)', lambda: (lambda v: (v._load(), f'{len(v._kokoro.create("Lorekeeper test.", voice="af_nicole")[0])} samples'))(
        voice.Voice('sapi', models=config.MODELS))[1] if not __import__('firstrun').missing_models() or ci and __import__('firstrun').download_models() else 'model not downloaded yet (first run fetches it)')
    check('ears (whisper)', lambda: (lambda e: (e.ready.wait(300), repr(e.text(np.zeros(16000, dtype='float32')))))(
        __import__('ears').Ears(config.load()['whisper'], 'cpu'))[1])
    if not ci:
        check('screen', lambda: f"{len(capture.Screen(active=lambda: False).now())} frame(s)")
    check('tray + hotkey libs', lambda: (__import__('pystray'), __import__('hotkey').parse('ctrl+alt+space'))[1])
    check('screen libs', lambda: (__import__('dxcam'), __import__('PIL.ImageGrab'))[1].__name__)
    if not ci:
        check('sound out', lambda: __import__('sounddevice').query_devices(kind='output')['name'])
    check('sound libs', lambda: (__import__('sounddevice'), __import__('soundfile'))[1].__name__)
    check('ai', lambda: (lambda ok, msg: msg if ok or brain.http() else 'Claude Code not installed (first run offers to install it)')(*brain.ready()))
    check('games index', lambda: f'{len(games.build())} games')
    print('SELFTEST', 'PASSED' if ok else 'FAILED', flush=True)
    return 0 if ok else 1


def already_running():
    """One Lorekeeper at a time (installed and source copies included): two would both answer every hotkey press.
    A named mutex lives as long as the process that made it, so a crash never leaves it stuck."""
    if sys.platform != 'win32':
        return False
    import ctypes
    k = ctypes.windll.kernel32
    k.CreateMutexW.restype = ctypes.c_void_p
    already_running.handle = k.CreateMutexW(None, False, 'Local\\Lorekeeper.SingleInstance')   # kept open until exit
    return k.GetLastError() == 183   # ERROR_ALREADY_EXISTS


def main():
    args = sys.argv[1:]
    cfg = config.load()
    brain.use(cfg)
    if args[:1] == ['--games']:
        return print('\n'.join(f"{g['name']}  [{g['source']}]  {g['dir']}" for g in games.build()) or 'no games found')
    if args[:1] == ['--selftest']:   # the installed build's smoke test: every native piece loads and works
        return sys.exit(selftest(ci='--ci' in args))
    if args[:1] == ['--romm-connect']:   # same as tray → RomM → Connect RomM…
        done = threading.Event()
        romm.pair(args[1] if len(args) > 1 else input('RomM address: '),
                  lambda code, link: (print(f'Approve code {code} in RomM: {link}', flush=True), os.startfile(link)),
                  lambda user, err: (print(f'Connected as {user}.' if user else err, flush=True), done.set()))
        done.wait(700)
        return
    if args[:1] == ['--voices']:   # sample wavs to choose kokoroVoice by ear
        folder = os.path.join(config.DIR, 'voices')
        voice.samples(folder, config.MODELS)
        return print(folder)
    if args[:1] == ['--ask']:
        q = ' '.join(args[1:])
        g, exe = games.current()
        print(f"[{g['name'] if g else 'no game'}]  {exe}")
        p = brain.start(cfg['deepModel'] if brain.DEEP.search(q) else cfg['model'], cfg['spoilers'])
        if not p:
            return print(brain.ready(cfg)[1])
        t = time.time()
        wiki = '\n\n'.join(x for x in (romm.context(g, q), lookup.wiki(q, g and g['name'], folder=notes.FOLDER, progress=notes.read(g, 3))) if x)
        print(f'(wiki {len(wiki)} chars in {time.time() - t:.1f}s)')
        a, usd = brain.ask(p, brain.request(q, g, notes.read(g), [], wiki, gear.text(g) if gear.wants(q) else ''))
        a, learned = brain.split_note(a)
        if learned and g:
            notes.add(g, learned + ' (learned)')
        return print(f'{a}\n({brain.name(cfg)}, ${usd:.4f}, {time.time() - t:.1f}s)' + (f'\n[noted: {learned}]' if learned else ''))
    if already_running():
        ctypes = __import__('ctypes')
        ctypes.windll.user32.MessageBoxW(None, 'Lorekeeper is already running: look for the pixel book in your tray '
                                               '(click the ^ arrow by the clock if it is hidden).', 'Lorekeeper', 0x40)
        return
    import box as boxmod, hotkey
    ok, msg = brain.ready(cfg)
    if not ok:
        print(msg, file=sys.stderr)
    b = boxmod.Box(cfg['boxSeconds'])
    app = App(cfg, b)
    try:
        hk = hotkey.Hotkey(cfg['hotkey'], app.down, app.up, app.cancel, app.in_game)
    except ValueError:
        hk = hotkey.Hotkey(config.DEFAULTS['hotkey'], app.down, app.up, app.cancel, app.in_game)
    app.hk = hk
    threading.Thread(target=hk.run, daemon=True).start()
    try:
        lk = hotkey.Hotkey(cfg['listenKey'], app.toggle_listen, lambda: None)
    except ValueError:
        lk = hotkey.Hotkey(config.DEFAULTS['listenKey'], app.toggle_listen, lambda: None)
    app.lk = lk
    threading.Thread(target=lk.run, daemon=True).start()
    tray(app, b)
    app.updater = updater.Updater(telemetry.VERSION, app.cfg, lambda v: b.show(
        'Update available', f'Lorekeeper {v} is out. Click here to update, or later from the tray (your notes and settings stay).',
        title=True, on_click=lambda: app.updater.update(b), hint='CLICK TO UPDATE'))
    app.updater.start()
    b.show('Lorekeeper is ready', f"Hold {hotkey.pretty(hk.combo)} in a game and ask." + (f" Playing {app.game['name']}." if app.game else ''), title=True)
    if telemetry.should_ask(app.cfg):   # first run: ask once; nothing is sent before a yes
        def ask():
            from tkinter import messagebox
            app.cfg['telemetry'] = bool(messagebox.askyesno('Lorekeeper', telemetry.QUESTION, parent=b.root))
            config.save(app.cfg)
        b.root.after(1500, ask)
    telemetry.start(app.cfg)   # reads the setting live: a later yes in the tray starts the counts
    import firstrun
    firstrun.run(app, b)   # an installed copy: fetch the voice model, offer to install Claude Code (when it's the AI)
    b.run()


if __name__ == '__main__':
    main()
