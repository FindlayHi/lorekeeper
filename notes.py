"""Per-game notes: where the player is, their build, choices. They set the spoiler horizon and help Whisper spell names.
One plain markdown file per game in <config>/games/, edit freely."""
import os, re, time
import config

FOLDER = os.path.join(config.DIR, 'games')


def slug(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'unknown'


def path(game):
    return os.path.join(FOLDER, slug(game['name']) + '.md')


def read(game, most=40):
    if not game:
        return ''
    try:
        with open(path(game), encoding='utf-8') as f:
            lines = [l.rstrip() for l in f if l.strip() and not l.startswith('#')]
    except OSError:
        return ''
    return '\n'.join(lines[-most:])


def add(game, line):
    os.makedirs(FOLDER, exist_ok=True)
    p = path(game)
    new = not os.path.exists(p)
    with open(p, 'a', encoding='utf-8') as f:
        if new:
            f.write(f"# {game['name']}\n\n")
        f.write(f"- {time.strftime('%Y-%m-%d')}: {line.strip()}\n")
    if game.get('source') == 'romm':   # keep them on the game in RomM too
        import threading, romm
        threading.Thread(target=romm.save_notes, args=(game, read(game, 200)), daemon=True).start()


def forget_learned(game):
    """Takes back the last note Lorekeeper learned by itself ("forget that note") -> the note, or ''."""
    try:
        with open(path(game), encoding='utf-8') as f:
            lines = f.readlines()
    except OSError:
        return ''
    i = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].rstrip().endswith('(learned)')), None)
    if i is None:
        return ''
    gone = lines.pop(i)
    with open(path(game), 'w', encoding='utf-8') as f:
        f.writelines(lines)
    if game.get('source') == 'romm':
        import threading, romm
        threading.Thread(target=romm.save_notes, args=(game, read(game, 200)), daemon=True).start()
    return re.sub(r'^- [\d-]+: |\s*\(learned\)$', '', gone.strip())


def names(game):
    """Capitalized words from the notes (bosses, places, characters), for Whisper's hint."""
    seen = []
    for w in re.findall(r"\b[A-Z][\w'-]{2,}(?: [A-Z][\w'-]+)*", read(game)):
        if w not in seen:
            seen.append(w)
    return seen[-30:]
