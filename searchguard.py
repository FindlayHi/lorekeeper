"""The check every WebSearch passes before it runs: Claude Code calls it as a PreToolUse hook (brain.start), and exit 2 stops
the search. A poisoned page can ask the model to search for the player's notes or gear, so the query a search engine sees
is held to the game and topic: short, no links or addresses, no long codes, nothing copied from what the player keeps
private. Standard library only: it runs once per search, and the installed app runs it as `Lorekeeper.exe --search-guard`
before anything heavy loads."""
import json, os, re, sys

PRIVATE = 'private.json'   # beside system.md in the `claude -p`'s folder: brain.private(): {allowed: what was said, private: notes, gear}
MOST = 120   # characters: "Elden Ring Rennala Queen of the Full Moon weakness" is 50
RUN = 6   # words in a row from the notes or gear that the player didn't say: a note being read out, not a name ("Rennala Queen of the Full Moon")
BAD = [
    (re.compile(r'https?:|www\.', re.I), 'it has a link in it'),   # a bare host is fine: site:terraria.wiki.gg
    (re.compile(r'@'), 'it has an address in it'),
    (re.compile(r'\d{6,}'), 'it has a long number in it'),
    (re.compile(r'[A-Za-z0-9+/=_-]{24,}'), 'it has a long code in it'),
]


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def runs(text, n=RUN):
    w = words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def check(query, private='', allowed=''):
    """Why the query is refused, or '' if it may run. allowed: text the query may quote freely (the question, the game)."""
    if len(query) > MOST:
        return 'it is too long'
    for rx, why in BAD:
        if rx.search(query):
            return why
    if runs(query) & (runs(private) - runs(allowed)):
        return "it copies the player's notes or gear"
    return ''


def main():
    """The hook: the PreToolUse payload on stdin -> exit 0 to let the search run, exit 2 (reason on stderr) to stop it."""
    try:
        raw = (sys.stdin.buffer if sys.stdin else open(0, 'rb', closefd=False)).read()
        j = json.loads(raw.decode('utf-8', 'replace'))
        query = str((j.get('tool_input') or {}).get('query') or '')
        folder = j.get('cwd') or os.getcwd()
    except Exception as e:
        return refuse(f'the search guard could not read the search ({type(e).__name__})')
    try:
        with open(os.path.join(folder, PRIVATE), encoding='utf-8') as f:
            kept = json.load(f)
    except (OSError, ValueError):
        kept = {}   # a one-off job (no question sent yet): the other checks still hold
    why = check(query, kept.get('private', ''), kept.get('allowed', ''))
    return refuse(why) if why else 0


def refuse(why):
    try:
        sys.stderr.write(f'Search blocked: {why}. Search for the game and the topic only.\n')
        sys.stderr.flush()
    except Exception:   # a windowed app may have no stderr: exit 2 still blocks
        pass
    return 2


if __name__ == '__main__':
    sys.exit(main())
