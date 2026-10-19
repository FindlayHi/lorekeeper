import os, sys, tempfile

os.environ['LOREKEEPER_DIR'] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import brain, capture, commands, notes, voice  # noqa: E402


def test_commands():
    p = commands.parse
    assert p('Clip it.') == ('clip', '')
    assert p('Lorekeeper, clip that!') == ('clip', '')
    for said in ('Hey, can you clip it?', 'Okay Lorekeeper, clip that please.', 'Could you please clip it for me?', 'Um, clip it now.'):
        assert p(said) == ('clip', ''), said
    assert p('Hey, can you stop?') == ('stop', '') and p('Can you repeat that?') == ('repeat', '')
    assert p('Can you tell me what this does?') is None
    assert p('Okay, spoil it.') == ('spoil', '')
    assert p("I'm playing Enter the Gungeon") == ('playing', 'Enter the Gungeon')
    assert p('I just beat Margit.') == ('note', 'I just beat Margit')
    assert p("I'm at Stormveil Castle") == ('note', "I'm at Stormveil Castle")
    assert p('Note: I went with a dex build') == ('note', 'I went with a dex build')
    assert p("I'm at Stormveil, where do I go next?") is None
    assert p('What synergy did I just get?') is None
    assert p('Stop.') == ('stop', '')
    assert p('repeat that') == ('repeat', '')


def test_screen_words():
    assert capture.wants('what synergy did I just get')
    assert capture.wants('what does this item do')
    assert not capture.wants('what does the Shadow Bullets synergy do')
    assert capture.wants('What perks do I have equipped right now?') and capture.wants('show my loadout')
    assert not capture.wants('what does dead hard do')
    assert capture.JUST.search('what synergy did I just get')


def test_deep_model_words():
    assert brain.DEEP.search('tell me more about the Gungeon lore')
    assert not brain.DEEP.search('what does the casey do')


def test_request_and_prompt():
    g = {'name': 'Enter the Gungeon', 'id': '311690', 'source': 'steam'}
    r = brain.request('what does Shadow Clone do', g, '- 2026-10-12: on chamber 3', [{'q': 'a', 'a': 'b'}])
    assert r.startswith('Game: Enter the Gungeon (Steam app 311690)') and 'chamber 3' in r and r.endswith('Question: what does Shadow Clone do')
    assert 'Game: unknown' in brain.request('hi', None, '', [])
    assert len(brain.SYSTEM + brain.SPOILER_SAFE) < 4000


def test_notes_and_names():
    g = {'name': 'ELDEN RING'}
    notes.add(g, 'I just beat Margit at Stormveil Castle')
    assert 'Margit' in notes.read(g) and 'Stormveil Castle' in notes.names(g)
    assert notes.path(g).endswith('elden-ring.md')


def test_split_for_speech():
    assert voice.split('**Shadow Clone** doubles you. See https://x.y/z for more.\nIts flavor text: "Me too."') == \
        ['Shadow Clone doubles you.', 'See  for more.', 'Its flavor text: "Me too."']


def test_gear_and_snap_commands():
    p = commands.parse
    assert p('Save this as my helm.') == ('gear_save', 'my helm')
    assert p('This is my new chest piece') == ('gear_save', 'chest piece')
    assert p('Forget my second ring') == ('gear_forget', 'second ring')
    assert p("What's my gear?") == ('gear_list', '')
    assert p('Remember this.') == ('snap', '')
    assert p('Remember this as the vault code') == ('snap', 'the vault code')
    assert p('Remember: I sided with the Emperor') == ('note', 'I sided with the Emperor')
    assert p('Is this better than my helm?') is None


def test_gear_slots_and_wants():
    import gear
    assert gear.slot('my helmet') == 'helm' and gear.slot('second ring') == 'ring 2' and gear.slot('chest piece') == 'chest'
    assert gear.slot('my weird totem') == 'weird totem'
    assert gear.wants('is this better than my helm') and gear.wants('what is my dps') and not gear.wants('who is Ranni')


def test_split_note():
    q = "I'm a sorcerer going crit, is this better?"
    assert brain.split_note('Yes, swap it.\nNOTE: Sorcerer, crit build', q) == ('Yes, swap it.', 'Sorcerer, crit build')
    assert brain.split_note('Yes, swap it. NOTE: Act 3', "I'm in act 3, which ring?") == ('Yes, swap it.', 'Act 3')
    assert brain.split_note('No notes here.', q) == ('No notes here.', '')


def test_sources_never_spoken():
    a = 'It sings or shrieks.\nSources:\n- [Phalar Aluve - BG3 Wiki](https://bg3.wiki/wiki/Phalar_Aluve)'
    assert brain.split_note(a, 'what does Phalar Aluve do') == ('It sings or shrieks.', '')
    assert brain.split_note('Swap it.\nNOTE: Act 2\n\nSources:\n- [x](y)', 'just got to act 2, swap?') == ('Swap it.', 'Act 2')
    assert brain.spoken('Dead Hard dodges a hit. Sour') == 'Dead Hard dodges a hit. Sour'
