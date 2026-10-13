import hashlib, io, json, os, sys, tempfile, zipfile

os.environ['LOREKEEPER_DIR'] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import icons  # noqa: E402
import rag  # noqa: E402

CHUNKS = [
    {'id': 'a', 'url': 'https://deadbydaylight.wiki.gg/wiki/Hex:_Ruin', 'title': 'Hex: Ruin', 'section': 'Description',
     'text': 'Hex: Ruin makes generators regress faster while a hex totem is standing. Cleansing the totem ends it.', 'kind': 'mechanic'},
    {'id': 'b', 'url': 'https://deadbydaylight.wiki.gg/wiki/Lithe', 'title': 'Lithe', 'section': 'Description',
     'text': 'Lithe gives a burst of speed after vaulting a window while running, then goes on cooldown.', 'kind': 'mechanic'},
    {'id': 'c', 'url': 'https://deadbydaylight.wiki.gg/wiki/Toolbox', 'title': 'Toolbox', 'section': 'Charges',
     'text': 'A toolbox repairs generators faster and spends its charges as it works.', 'kind': 'item'},
]


def pack(chunks=CHUNKS, man=None, extra=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('lore.json', json.dumps(man or {'schema': 1, 'game': 'Dead by Daylight', 'trust': 'official', 'builtForBuild': '100',
                                                   'sources': [{'host': 'deadbydaylight.wiki.gg'}]}))
        z.writestr('chunks.jsonl', '\n'.join(json.dumps(c) for c in chunks))
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return buf.getvalue()


def test_good_pack_loads_and_finds_the_right_section():
    p = rag.load(pack())
    assert p and p['trust'] == 'official' and len(p['chunks']) == 3
    assert rag.search(p, 'what does Hex Ruin do to generators')[0][1]['id'] == 'a'
    assert rag.search(p, 'how does Lithe work after a vault')[0][1]['id'] == 'b'


def test_hash_must_match():
    data = pack()
    assert rag.load(data, hashlib.sha256(data).hexdigest())
    assert rag.load(data, '0' * 64) is None


def test_bad_packs_are_refused():
    assert rag.load(b'not a zip') is None
    assert rag.load(pack(man={'schema': 2, 'trust': 'official'})) is None
    assert rag.load(pack(man={'schema': 1, 'trust': 'god'})) is None
    assert rag.load(pack(extra={'../evil.json': '{}'})) is None
    assert rag.load(pack(extra={'sub/x.npy': 'x'})) is None
    assert rag.load(pack(chunks=[{'id': 'x', 'url': 'file:///etc/passwd', 'text': 'hi'}])) is None
    assert rag.load(pack(chunks=[])) is None


def test_chunk_fields_are_clamped():
    p = rag.load(pack(chunks=[dict(CHUNKS[0], kind='<script>', text='x' * 99999)]))
    assert p['chunks'][0]['kind'] == 'lore' and len(p['chunks'][0]['text']) == rag.MAX_TEXT


def test_pointer_only_names_a_pack_in_the_lore_folder():
    sha = 'a' * 64
    assert rag.pointer({'file': 'lore/dead-by-daylight.zip', 'sha256': sha, 'version': 2, 'builtForBuild': 77})['build'] == '77'
    for bad in ('../x.zip', 'lore/../x.zip', 'http://evil/x.zip', 'lore/a/b.zip', '/lore/x.zip', 'lore/x.exe'):
        assert rag.pointer({'file': bad, 'sha256': sha}) is None
    assert rag.pointer({'file': 'lore/x.zip', 'sha256': 'zz'}) is None
    assert rag.pointer(None) is None


def test_cart_carries_a_valid_pointer_and_drops_a_bad_one():
    cart = {'host': 'deadbydaylight.wiki.gg', 'sets': [{'kind': 'perks', 'prefix': 'IconPerks_', 'shape': 'diamond'}]}
    ok = icons.valid({'games': {'G': dict(cart, lore={'file': 'lore/g.zip', 'sha256': 'b' * 64})}})
    bad = icons.valid({'games': {'G': dict(cart, lore={'file': '../g.zip', 'sha256': 'b' * 64})}})
    assert ok['g']['lore']['file'] == 'lore/g.zip' and bad['g']['lore'] is None


def test_context_is_sure_or_empty_and_flags_a_patched_game(tmp_path):
    folder = str(tmp_path)
    data = pack()
    path = rag._path(folder, 'Dead by Daylight')
    os.makedirs(os.path.dirname(path))
    open(path, 'wb').write(data)
    rag._packs.clear()
    ptr = {'sha256': hashlib.sha256(data).hexdigest()}
    out = rag.context('Dead by Daylight', ptr, 'what does Hex Ruin do to generators', folder)
    assert out.startswith('Source: https://deadbydaylight.wiki.gg/wiki/Hex:_Ruin') and 'regress' in out and rag.STALE not in out
    assert rag.STALE in rag.context('Dead by Daylight', ptr, 'what does Hex Ruin do to generators', folder, build='101')
    assert rag.context('Dead by Daylight', ptr, 'who is the best streamer', folder) == ''   # nothing sure: the live wiki is asked
    assert rag.context('Elden Ring', None, 'anything', folder, fetch=False) == ''


def test_a_tampered_cached_pack_is_not_used(tmp_path):
    folder = str(tmp_path)
    path = rag._path(folder, 'Dead by Daylight')
    os.makedirs(os.path.dirname(path))
    open(path, 'wb').write(pack())
    rag._packs.clear()
    assert rag.get('Dead by Daylight', {'sha256': '0' * 64}, folder, fetch=False) is None


def test_a_local_pack_may_name_its_files_but_an_official_one_may_not():
    mine = [dict(CHUNKS[0], url='local:my-guide.md')]
    assert rag.load(pack(chunks=mine, man={'schema': 1, 'trust': 'local'}))
    assert rag.load(pack(chunks=mine)) is None
    assert rag.load(pack(chunks=[dict(CHUNKS[0], url='local:../x')], man={'schema': 1, 'trust': 'local'})) is None


def test_a_dropped_in_pack_is_used_but_cannot_claim_to_be_official(tmp_path):
    folder = str(tmp_path)
    mine = rag._path(folder, 'Elden Ring', True)
    os.makedirs(os.path.dirname(mine))
    local = pack(man={'schema': 1, 'game': 'Elden Ring', 'trust': 'local'}, chunks=[dict(CHUNKS[0], url='local:notes.md')])
    open(mine, 'wb').write(local)
    rag._packs.clear()
    assert rag.get('Elden Ring', None, folder, fetch=False)['trust'] == 'local'
    open(mine, 'wb').write(pack())   # says trust official, but anyone can drop a file in
    rag._packs.clear()
    assert rag.get('Elden Ring', None, folder, fetch=False) is None


def test_a_cached_official_pack_needs_the_carts_pointer(tmp_path):
    folder = str(tmp_path)
    data = pack()
    path = rag._path(folder, 'Dead by Daylight')
    os.makedirs(os.path.dirname(path))
    open(path, 'wb').write(data)
    rag._packs.clear()
    assert rag.get('Dead by Daylight', None, folder, fetch=False) is None   # the cart no longer offers lore


ENTS = [
    {'name': 'Hex: Ruin', 'kind': 'perk', 'url': 'https://deadbydaylight.wiki.gg/wiki/Hex:_Ruin', 'aliases': [], 'text': 'Hex: Ruin is a Unique Perk. Generators regress at 100/125/150 %.'},
    {'name': 'Lithe', 'kind': 'perk', 'url': 'https://deadbydaylight.wiki.gg/wiki/Lithe', 'aliases': [], 'text': 'Lithe grants +50 % Haste for 3 seconds after a Rushed Vault.'},
    {'name': 'Sprint Burst', 'kind': 'perk', 'url': 'https://deadbydaylight.wiki.gg/wiki/Sprint_Burst', 'aliases': ['sb'], 'text': 'Sprint Burst grants +50 % Haste for 2 seconds.'},
    {'name': 'Sally Smithson', 'kind': 'boss', 'url': 'https://deadbydaylight.wiki.gg/wiki/Sally_Smithson', 'aliases': ['The Nurse'], 'text': 'The Nurse: movement speed 96.25 %.'},
    {'name': 'Spirit', 'kind': 'boss', 'url': 'https://deadbydaylight.wiki.gg/wiki/Spirit', 'aliases': [], 'text': 'Rin Yamaoka, the Spirit.'},
    {'name': 'Spirit Fury', 'kind': 'perk', 'url': 'https://deadbydaylight.wiki.gg/wiki/Spirit_Fury', 'aliases': [], 'text': 'Spirit Fury breaks pallets.'},
]


def epack(ents=ENTS):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('lore.json', json.dumps({'schema': 1, 'game': 'Dead by Daylight', 'trust': 'official'}))
        z.writestr('chunks.jsonl', '\n'.join(json.dumps(c) for c in CHUNKS))
        z.writestr('entities.jsonl', '\n'.join(json.dumps(e) for e in ents))
    return buf.getvalue()


def test_a_named_thing_is_looked_up_exactly():
    p = rag.load(epack())
    got = rag.retrieve(p, 'what does Sprint Burst do')
    assert [e['name'] for e in got['entities']] == ['Sprint Burst'] and got['sure']
    assert 'Source: https://deadbydaylight.wiki.gg/wiki/Sprint_Burst' in rag.render(got) and '2 seconds' in rag.render(got)


def test_names_match_without_prefix_punctuation_or_the():
    p = rag.load(epack())
    assert [e['name'] for e in rag.find(p, 'how do i stop ruin')] == ['Hex: Ruin']
    assert [e['name'] for e in rag.find(p, "hex ruin and lithe, which is better")] == ['Hex: Ruin', 'Lithe']
    assert [e['name'] for e in rag.find(p, 'how do i counter the nurse')] == ['Sally Smithson']   # by alias
    assert [e['name'] for e in rag.find(p, 'what does sb do')] == ['Sprint Burst']
    assert rag.find(p, 'what is the best perk') == []


def test_the_longer_name_wins_over_one_inside_it():
    p = rag.load(epack())
    assert [e['name'] for e in rag.find(p, 'what does spirit fury do')] == ['Spirit Fury']
    assert [e['name'] for e in rag.find(p, 'how fast is the spirit')] == ['Spirit']


def test_names_read_from_the_screen_are_taken_exactly():
    p = rag.load(epack())
    assert [e['name'] for e in rag.find(p, 'what do my perks do', names=['Lithe', 'Not A Perk'])] == ['Lithe']
    assert rag.entry('Dead by Daylight', None, 'Lithe', folder='x', fetch=False) == ''   # no pack on disk


def test_a_name_two_things_share_is_not_a_shorthand():
    two = ENTS + [dict(ENTS[0], name='Ruin Remix', url='https://deadbydaylight.wiki.gg/wiki/Ruin_Remix', aliases=['ruin'])]
    p = rag.load(epack(two))
    assert '4 ruin' not in p['names'] and 'ruin' not in p['names']   # both claim it
    assert [e['name'] for e in rag.find(p, 'hex ruin')] == ['Hex: Ruin']


def test_entries_are_validated_like_chunks():
    bad = [dict(ENTS[0], url='file:///etc/passwd'), dict(ENTS[1], kind='<x>', aliases='lithe', text='y' * 99999)]
    p = rag.load(epack(bad))
    assert [e['name'] for e in p['entities']] == ['Lithe'] and p['entities'][0]['kind'] == 'lore' and p['entities'][0]['aliases'] == []
    assert len(p['entities'][0]['text']) == rag.ENTITY_TEXT
