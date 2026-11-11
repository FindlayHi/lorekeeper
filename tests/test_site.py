import hashlib, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_lore_packs_match_their_cartridge_hash():
    with open(os.path.join(ROOT, 'docs', 'cartridges.json'), encoding='utf-8') as f:
        games = json.load(f)['games']
    checked = 0
    for name, cart in games.items():
        lore = cart.get('lore')
        if not lore:
            continue
        path = os.path.join(ROOT, 'docs', *lore['file'].split('/'))
        assert os.path.isfile(path), f'{name}: docs/{lore["file"]} is missing'
        with open(path, 'rb') as f:
            got = hashlib.sha256(f.read()).hexdigest()
        assert got == lore['sha256'].lower(), f'{name}: docs/{lore["file"]} does not match the sha256 in cartridges.json'
        checked += 1
    assert checked, 'no cartridge has a lore pointer'


def test_site_has_a_404_page():
    assert os.path.isfile(os.path.join(ROOT, 'docs', '404.html'))
