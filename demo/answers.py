"""Step 1 of the demo: ask Lorekeeper the demo's questions for real (wiki lookup + claude -p), save script.json.
Every answer in the video is what Lorekeeper actually said. Run from the repo root with the venv's python."""
import json, os, sys, tempfile, time

os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())   # keep the demo's notes out of yours
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import brain, capture, gear, lookup, notes  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SCENES = [
    {'game': 'Enter the Gungeon', 'q': 'What does the Gilded Hydra do?', 'notes': []},
    {'game': 'The Witcher 3: Wild Hunt', 'q': 'I found the Botchling under the house. What should I do with it?',
     'notes': ['Agreed to help the Bloody Baron find his wife and daughter (Family Matters)', 'Found the Botchling under the house']},
    {'game': 'Diablo IV', 'q': 'Is this better than my helm?', 'notes': ['Sorcerer, Intelligence crit build'], 'gear': True},
]


def tooltip_shot():
    """A drawn Diablo-style comparison (no game art): the equipped helm and the hovered one."""
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 22)
    fb = ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf', 26)
    img = Image.new('RGB', (1920, 1080), (40, 50, 40))
    d = ImageDraw.Draw(img)

    def tip(x, title, lines, header=None):
        d.rectangle((x, 120, x + 460, 640), fill=(18, 14, 12), outline=(120, 90, 40), width=3)
        y = 135
        if header:
            d.text((x + 20, y), header, font=f, fill=(170, 170, 170))
            y += 34
        d.text((x + 20, y), title, font=fb, fill=(230, 140, 40))
        y += 44
        for line in lines:
            d.text((x + 20, y), line, font=f, fill=(220, 210, 190))
            y += 34
    tip(900, 'Harlequin Crest', ['Unique Helm', '800 Item Power', '+1,040 Armor', '+12.5% Damage Reduction', '+98 Strength',
                                 '+8.0% Cooldown Reduction', 'Gain +4 Ranks to all Skills'], 'EQUIPPED')
    tip(1400, "Tal Rasha's Iridescent Loop", ['Legendary Helm', '925 Item Power', '+1,150 Armor', '+172 Intelligence',
                                             '+14.2% Critical Strike Chance', '+11.0% Cooldown Reduction', '+31% Critical Strike Damage'])
    return capture.Screen.files([(time.time(), capture.jpeg(img))], 'this')


def main():
    out = []
    for s in SCENES:
        g = {'name': s['game'], 'id': '', 'source': 'named', 'dir': ''}
        for n in s['notes']:
            notes.add(g, n)
        t = time.time()
        shots = tooltip_shot() if s.get('gear') else []
        if s.get('gear'):
            gear.save(g, 'helm', {'name': 'Harlequin Crest', 'type': 'Unique Helm', 'power': '800 Item Power',
                                  'stats': ['+1,040 Armor', '+12.5% Damage Reduction', '+98 Strength', '+8.0% Cooldown Reduction',
                                            'Gain +4 Ranks to all Skills']})
        wiki = '' if shots else lookup.wiki(s['q'], g['name'], folder=notes.FOLDER, progress=notes.read(g, 3))
        p = brain.start('sonnet' if s.get('gear') else 'haiku')
        a, usd = brain.ask(p, brain.request(s['q'], g, notes.read(g), [], wiki, gear.text(g) if s.get('gear') else ''), shots)
        a, _ = brain.split_note(a, s['q'])
        print(f"{s['game']}: {a}  (${usd:.4f}, {time.time() - t:.1f}s)", flush=True)
        out.append({'game': s['game'], 'q': s['q'], 'a': a, 'secs': round(time.time() - t, 1), 'usd': usd})
    out.append({'game': 'Any game', 'q': 'Clip it.', 'a': 'Clipped. The last thirty seconds are saved.', 'clip': True})
    with open(os.path.join(HERE, 'script.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
