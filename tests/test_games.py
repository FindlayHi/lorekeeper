import json, os, sys, tempfile

D = tempfile.mkdtemp()
os.environ['LOREKEEPER_DIR'] = D
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import games  # noqa: E402

LIB = r'''"libraryfolders"
{
	"0"
	{
		"path"		"%s"
		"apps" { "1245620" "1" }
	}
}'''

ACF = '''"AppState"
{
	"appid"		"%s"
	"name"		"%s"
	"installdir"		"%s"
}'''


def steam_tree():
    steam = tempfile.mkdtemp()
    apps = os.path.join(steam, 'steamapps')
    os.makedirs(apps)
    open(os.path.join(apps, 'libraryfolders.vdf'), 'w').write(LIB % steam.replace('\\', '\\\\'))
    for appid, name, d in [('1245620', 'ELDEN RING', 'ELDEN RING'), ('228980', 'Steamworks Common Redistributables', 'Steamworks Shared'),
                           ('1086940', "Baldur's Gate 3", "Baldurs Gate 3")]:
        open(os.path.join(apps, f'appmanifest_{appid}.acf'), 'w').write(ACF % (appid, name, d))
    return steam


def test_vdf_nested():
    v = games.vdf('"a" { "b" "1" "c" { "d" "x\\\\y" } } "e" "2"')
    assert v == {'a': {'b': '1', 'c': {'d': 'x\\y'}}, 'e': '2'}


def test_steam_index_skips_tools():
    steam = steam_tree()
    names = sorted(g['name'] for g in games.steam_games(steam))
    assert names == ["Baldur's Gate 3", 'ELDEN RING']


def test_match_by_exe_and_title():
    gs = games.steam_games(steam_tree())
    er = next(g for g in gs if g['name'] == 'ELDEN RING')
    assert games.match(os.path.join(er['dir'], 'Game', 'eldenring.exe'), '', gs)['name'] == 'ELDEN RING'
    assert games.match(r'C:\elsewhere\bg3.exe', "Baldur's Gate 3 (1.0)", gs)['name'] == "Baldur's Gate 3"
    assert games.match(r'C:\Windows\notepad.exe', 'Untitled - Notepad', gs) is None
    assert games.match(r'C:\elsewhere\er.exe', 'ELDEN RING™', gs)['name'] == 'ELDEN RING'
    assert games.match(r'C:\elsewhere\bg3.exe', 'Baldurs Gate 3 - Vulkan', gs)['name'] == "Baldur's Gate 3"


def test_a_title_that_only_holds_a_games_name_is_not_that_game():
    gs = [{'name': n, 'id': '', 'source': 'steam', 'dir': 'D:\\S\\' + n} for n in ('Rust', 'Hades', 'Control', 'Portal', 'Among Us')]
    for title in ('Trusted logins - KeePass', 'Lampshades invoice.docx - Word', 'Quality control - Slack',
                  'Bank - Customer portal - Brave', 'Inbox - among users - Outlook', 'Rusty Lake', 'Portals of Phereon'):
        assert games.match(r'C:\Apps\other.exe', title, gs) is None, title
    assert games.match(r'C:\Apps\other.exe', 'Hades', gs)['name'] == 'Hades'
    assert games.match(r'C:\Apps\other.exe', 'Among Us - v2024', gs)['name'] == 'Among Us'


def test_epic_manifest():
    m = tempfile.mkdtemp()
    json.dump({'DisplayName': 'Hades', 'AppName': 'Min', 'InstallLocation': r'C:\Epic\Hades', 'AppCategories': ['public', 'games']},
              open(os.path.join(m, 'x.item'), 'w'))
    json.dump({'DisplayName': 'Unreal', 'InstallLocation': r'C:\Epic\UE', 'AppCategories': ['engines']}, open(os.path.join(m, 'y.item'), 'w'))
    assert [g['name'] for g in games.epic_games(m)] == ['Hades']


def test_find_named_game():
    gs = games.steam_games(steam_tree())
    assert games.find('elden ring', gs)['name'] == 'ELDEN RING'
    assert games.find('baldurs gate', gs)['name'] == "Baldur's Gate 3"
    assert games.find('chrono trigger', gs) == {'name': 'Chrono Trigger', 'id': '', 'source': 'named', 'dir': ''}


def test_pin_holds_until_another_game():
    gs = games.steam_games(steam_tree())
    json.dump(gs, open(games.INDEX, 'w'))
    games.pin({'name': 'Chrono Trigger'}, r'C:\emu\retroarch.exe')
    assert games.current(r'C:\emu\retroarch.exe', 'RetroArch')[0]['name'] == 'Chrono Trigger'
    assert games.current(r'C:\Program Files\Google\Chrome\chrome.exe', 'wiki')[0]['name'] == 'Chrono Trigger'
    er = os.path.join(gs[0]['dir'], 'game.exe')
    assert games.current(er, '')[0]['name'] == gs[0]['name']
    assert games.pinned() is None


def fake_reg(tree):
    return lambda path: tree.get(path, {})


UNI = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
BNET = '"C:\\ProgramData\\Battle.net\\Agent\\Blizzard Uninstaller.exe" --lang=enUS --uid=%s --displayname="x"'


def test_battle_net_from_uninstall_keys():
    reg = fake_reg({UNI: {
        'Battle.net': {'DisplayName': 'Battle.net', 'InstallLocation': r'C:\Program Files (x86)\Battle.net', 'UninstallString': BNET % 'battle.net'},
        'Diablo IV': {'DisplayName': 'Diablo IV', 'InstallLocation': r'D:\Diablo IV', 'UninstallString': BNET % 'fenris'},
        'Steam': {'DisplayName': 'Steam', 'InstallLocation': r'C:\Steam', 'UninstallString': r'"C:\Steam\uninstall.exe"'},
        'Blank': {'DisplayName': 'Blank', 'UninstallString': BNET % 'x'}}})
    assert games.battle_net_games(reg) == [{'name': 'Diablo IV', 'id': 'fenris', 'source': 'battlenet', 'dir': os.path.normpath(r'D:\Diablo IV')}]
    assert games.battle_net_games(fake_reg({})) == []


def xbox_drive(root_name='XboxGames', record=True):
    d = tempfile.mkdtemp()
    if record:
        open(os.path.join(d, '.GamingRoot'), 'wb').write(b'RGBX\x01\x00\x00\x00' + (root_name + '\0').encode('utf-16-le'))
    os.makedirs(os.path.join(d, root_name, 'Forza Horizon 5', 'Content'))
    os.makedirs(os.path.join(d, root_name, 'GameSave'))
    return d


def test_xbox_follows_gamingroot_and_matches_exe():
    d = xbox_drive('Games4Me')
    gs = games.xbox_games([d])
    assert [g['name'] for g in gs] == ['Forza Horizon 5']
    exe = os.path.join(d, 'Games4Me', 'Forza Horizon 5', 'Content', 'ForzaHorizon5.exe')
    assert games.match(exe, '', gs)['name'] == 'Forza Horizon 5'


def test_xbox_falls_back_to_xboxgames_and_stays_silent():
    assert [g['name'] for g in games.xbox_games([xbox_drive(record=False)])] == ['Forza Horizon 5']
    assert games.xbox_games([tempfile.mkdtemp()]) == []


def test_ea_games_keys():
    reg = fake_reg({r'SOFTWARE\EA Games': {'Mass Effect': {'Install Dir': 'C:\\EA\\ME\\'}, 'Junk': {'Other': 'x'}, 'EA app': {'Install Dir': 'C:\\EA'}}})
    assert [(g['name'], g['dir']) for g in games.ea_games(reg)] == [('Mass Effect', os.path.normpath('C:\\EA\\ME\\'))]
    assert games.ea_games(fake_reg({})) == []


def test_ubisoft_name_from_uninstall_key_or_folder():
    reg = fake_reg({r'SOFTWARE\Ubisoft\Launcher\Installs': {'635': {'InstallDir': 'C:/Ubi/Far Cry 6/'}, '1': {'InstallDir': 'C:/Ubi/Anno 1800/'}},
                    UNI: {'Uplay Install 635': {'DisplayName': 'Far Cry 6'}}})
    assert sorted(g['name'] for g in games.ubisoft_games(reg)) == ['Anno 1800', 'Far Cry 6']
    assert games.ubisoft_games(fake_reg({})) == []


def test_launchers_not_games():
    for exe in ('Battle.net.exe', 'EADesktop.exe', 'upc.exe', 'UbisoftConnect.exe', 'XboxPcApp.exe', 'GamingServices.exe', 'steam.exe', 'discord.exe'):
        assert games.LAUNCHERS.search('C:\\x\\' + exe), exe
    assert not games.LAUNCHERS.search(r'D:\Diablo IV\Diablo IV.exe')
    assert games.ea_games(fake_reg({r'SOFTWARE\EA Games': {'EA app': {'Install Dir': 'C:\\EA'}}})) == []


def test_dedupe_prefers_existing_dir_then_first_source():
    real = tempfile.mkdtemp()
    a = {'name': 'Mass Effect', 'id': '1', 'source': 'steam', 'dir': r'Z:\gone'}
    b = {'name': 'Mass Effect™', 'id': '2', 'source': 'ea', 'dir': real}
    c = {'name': 'Hades', 'id': '3', 'source': 'steam', 'dir': real}
    d = {'name': 'hades', 'id': '4', 'source': 'epic', 'dir': real}
    assert games.dedupe([a, c, b, d]) == [c, b]   # the Steam row for a missing folder loses to the EA row that exists


def test_dedupe_ties_go_to_earlier_source():
    real = tempfile.mkdtemp()
    s = {'name': 'Hades', 'id': '3', 'source': 'steam', 'dir': real}
    e = {'name': 'HADES', 'id': '4', 'source': 'epic', 'dir': real}
    assert games.dedupe([s, e]) == [s]
    assert games.dedupe([e, s]) == [e]


def test_build_survives_a_broken_source(capsys, monkeypatch):
    def boom():
        raise RuntimeError('registry locked')
    ok = {'name': 'Hades', 'id': '1', 'source': 'epic', 'dir': ''}
    monkeypatch.setattr(games, '_sources', lambda: [('steam', boom), ('epic', lambda: [ok]), ('ea', lambda: [{'name': 'EA app', 'id': '', 'source': 'ea', 'dir': 'x'}])])
    assert games.build() == [ok]
    assert 'steam scan failed: registry locked' in capsys.readouterr().out
