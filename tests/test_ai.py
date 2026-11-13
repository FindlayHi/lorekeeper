"""The OpenAI-compatible backend (Ollama, LM Studio, OpenAI…), against a fake server on localhost: no network."""
import json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
os.environ.setdefault('LOREKEEPER_DIR', tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest  # noqa: E402
import brain, config  # noqa: E402


class Fake(BaseHTTPRequestHandler):
    """Replies with whatever the test put in `reply`: (status, body str or list of SSE chunks)."""
    reply, got, redirect = (200, []), [], None   # redirect: where the first GET is sent on to

    def log_message(self, *a):
        pass

    def _send(self):
        status, body = Fake.reply
        self.send_response(status)
        if isinstance(body, list):
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            for chunk in body:
                self.wfile.write(chunk.encode())
                self.wfile.flush()
        else:
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body.encode())

    def do_GET(self):
        Fake.got.append(('GET', self.path, self.headers.get('Authorization'), None))
        if Fake.redirect and len(Fake.got) == 1:
            self.send_response(302)
            self.send_header('Location', Fake.redirect)
            self.end_headers()
            return
        self._send()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        Fake.got.append(('POST', self.path, self.headers.get('Authorization'), body))
        self._send()


@pytest.fixture
def server(monkeypatch):
    s = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    Fake.got = []
    monkeypatch.setattr(brain, 'key', lambda cfg=None: '')
    cfg = {**config.DEFAULTS, 'ai': 'openai', 'aiUrl': f'http://127.0.0.1:{s.server_port}/v1', 'aiModel': 'quick', 'aiDeepModel': 'deep'}
    brain.use(cfg)
    yield cfg
    brain.use({})
    s.shutdown()


def chunks(*pieces, done=True):
    out = [f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}\n\n" for p in pieces]
    return out + (['data: [DONE]\n\n'] if done else [])


def test_sse_yields_the_text_pieces_and_stops_at_done():
    lines = ''.join(chunks('Hel', 'lo') + chunks('ignored')).splitlines()
    lines.insert(0, ': keep-alive')
    lines.insert(1, json.dumps({'choices': [{'delta': {'role': 'assistant'}}]}))   # not a data line
    assert ''.join(brain.sse(lines)) == 'Hello'
    assert ''.join(brain.sse([b'data: {"choices":[{"delta":{"content":"bytes"}}]}'])) == 'bytes'


def test_sse_raises_an_error_sent_mid_stream():
    with pytest.raises(brain.ServerError, match='out of memory'):
        list(brain.sse(['data: {"error": {"message": "out of memory"}}']))


def test_think_blocks_are_never_spoken():
    assert brain.unthink('<think>hmm, the wiki says</think>\n\nIt heals you.') == 'It heals you.'
    assert brain.unthink('<think>still thinking about') == ''   # a partial stream: nothing yet
    assert brain.unthink('No thinking here.') == 'No thinking here.'


def test_content_puts_each_screenshot_after_its_label(tmp_path):
    shot = tmp_path / 'a.jpg'
    shot.write_bytes(b'\xff\xd8jpeg')
    c = brain.content('Question: what is this?', [(str(shot), 'the screen'), (str(tmp_path / 'gone.jpg'), 'missing')])
    assert c[0] == {'type': 'text', 'text': 'the screen'}
    assert c[1]['type'] == 'image_url' and c[1]['image_url']['url'].startswith('data:image/jpeg;base64,/9')
    assert c[2] == {'type': 'text', 'text': 'Question: what is this?'} and len(c) == 3
    assert brain.content('plain') == 'plain'   # no screenshots: plain text, which models without vision take


def test_kinds_and_names_from_the_address():
    assert brain.kind({}) == 'claude' and brain.name({}) == 'Claude Code'
    assert brain.kind({'ai': 'openai', 'aiUrl': 'http://localhost:11434/v1/'}) == 'ollama'
    assert brain.kind({'ai': 'openai', 'aiUrl': 'http://localhost:1234/v1'}) == 'lmstudio'
    assert brain.kind({'ai': 'openai', 'aiUrl': 'https://api.openai.com/v1'}) == 'openai'
    assert brain.kind({'ai': 'openai', 'aiUrl': 'https://openrouter.ai/api/v1'}) == 'custom'
    assert brain.name({'ai': 'openai', 'aiUrl': 'http://localhost:1234/v1'}) == 'LM Studio'


def test_ready_says_what_is_missing():
    ok, msg = brain.ready({'ai': 'openai', 'aiUrl': 'http://localhost:11434/v1', 'aiModel': ''})
    assert not ok and 'No model' in msg and 'Ollama' in msg
    assert brain.ready({'ai': 'openai', 'aiUrl': 'http://localhost:11434/v1', 'aiModel': 'gemma3:4b'}) == (True, 'Ollama, gemma3:4b')


def test_http_prompt_has_no_web_search():
    s = brain.system_prompt(False, True)
    assert 'WebSearch' not in s and 'tool calls' not in s and "couldn't find it rather than guessing" in s
    assert 'WebSearch' in brain.system_prompt(False)   # Claude Code keeps it


def test_haiku_and_sonnet_map_to_the_quick_and_deep_models(server):
    assert brain._model('haiku', server) == 'quick'
    assert brain._model('sonnet', server) == 'deep'
    assert brain._model('sonnet', {**server, 'aiDeepModel': ''}) == 'quick'   # blank deep = the quick one


def test_an_answer_streams_without_the_thinking(server):
    Fake.reply = (200, chunks('<think>let me', ' see</think>', 'It heals ', 'you. ', 'NOTE: Gungeoneer'))
    p = brain.start('sonnet', spoilers=True)
    assert p.poll() is None and p.model == 'sonnet' and p.spoilers
    seen = []
    a, usd = brain.ask(p, 'Question: what does it do?', (), seen.append)
    assert a == 'It heals you. NOTE: Gungeoneer' and usd == 0
    assert seen and not any('think' in s or 'let me' in s for s in seen)
    method, path, auth, body = Fake.got[0]
    assert (method, path, auth) == ('POST', '/v1/chat/completions', None)   # a local server: no key, no header
    assert body['model'] == 'deep' and body['stream'] is True
    assert body['messages'][0]['role'] == 'system' and 'WebSearch' not in body['messages'][0]['content']
    assert body['messages'][1] == {'role': 'user', 'content': 'Question: what does it do?'}


def test_the_key_goes_as_a_bearer_token(server, monkeypatch):
    monkeypatch.setattr(brain, 'key', lambda cfg=None: 'sk-test')
    Fake.reply = (200, chunks('ok'))
    brain.ask(brain.start('haiku'), 'hi')
    assert Fake.got[0][2] == 'Bearer sk-test'


class Ring:
    """keyring, in memory."""
    def __init__(self, **saved):
        self.saved = dict(saved)

    def get_password(self, service, name):
        return self.saved.get(name)

    def set_password(self, service, name, k):
        self.saved[name] = k

    def delete_password(self, service, name):
        del self.saved[name]


def test_a_key_is_kept_for_one_server_and_sent_nowhere_else(monkeypatch):
    ring = Ring()
    monkeypatch.setitem(sys.modules, 'keyring', ring)
    openai, ollama = {'aiUrl': 'https://api.openai.com/v1'}, {'aiUrl': 'http://localhost:11434/v1'}
    brain.set_key('sk-openai', openai)
    assert brain.key(openai) == 'sk-openai' and brain.key({'aiUrl': 'https://API.openai.com/v1/'}) == 'sk-openai'
    assert brain.key(ollama) == '' and brain.key({'aiUrl': 'http://api.openai.com/v1'}) == '' and brain.key({}) == ''
    assert 'Authorization' not in brain._req(ollama, '/models').headers
    assert brain._req(openai, '/models').headers['Authorization'] == 'Bearer sk-openai'
    brain.set_key('', openai)
    assert brain.key(openai) == '' and not ring.saved


def test_an_older_versions_single_key_becomes_the_key_of_the_server_in_use(monkeypatch):
    ring = Ring(**{'ai-key': 'sk-old'})
    monkeypatch.setitem(sys.modules, 'keyring', ring)
    openai, other = {'aiUrl': 'https://api.openai.com/v1'}, {'aiUrl': 'https://elsewhere.example/v1'}
    assert brain.key(openai) == 'sk-old' and ring.saved == {'ai-key:https://api.openai.com': 'sk-old'}
    assert brain.key(other) == ''


def test_a_redirect_to_another_server_goes_without_the_key(server, monkeypatch):
    monkeypatch.setattr(brain, 'key', lambda cfg=None: 'sk-test')
    other = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    Fake.redirect = f'http://127.0.0.1:{other.server_port}/v1/models'
    Fake.reply = (200, json.dumps({'data': [{'id': 'm'}]}))
    try:
        assert brain.models(server) == ['m']
    finally:
        Fake.redirect = None
        other.shutdown()
    assert [g[2] for g in Fake.got] == ['Bearer sk-test', None]


def test_warm_keeps_an_http_session_for_the_same_model(server):
    w = brain.Warm()
    w.prime('haiku', False)
    first = w.p
    assert w.take('haiku', False) is first
    w.prime('haiku', False)
    assert w.take('sonnet', False) is not first


def test_models_lists_the_server_ids(server):
    Fake.reply = (200, json.dumps({'object': 'list', 'data': [{'id': 'qwen2.5vl:3b'}, {'id': 'Gemma3:4b'}, {'id': 'qwen2.5vl:3b'}, {'id': 'text-embedding-nomic-embed-text-v1.5'}]}))
    assert brain.models() == ['Gemma3:4b', 'qwen2.5vl:3b']
    assert Fake.got[0][1] == '/v1/models'


def test_test_says_working(server):
    Fake.reply = (200, chunks('Ready.'))
    assert brain.test(server) == (True, 'your AI server, quick: working.')


@pytest.mark.parametrize('status, body, says', [
    (401, '{"error": {"message": "Incorrect API key"}}', 'refused the API key'),
    (404, '{"error": {"message": "model \\"quick\\" not found, try pulling it first"}}', "quick isn't on"),
    (400, '{"error": {"message": "model does not support image input"}}', "can't see images"),
    (500, '{"error": {"message": "llama runner process has terminated"}}', 'failed (500): llama runner'),
])
def test_server_errors_are_said_plainly(server, status, body, says):
    Fake.reply = (status, body)
    a, _ = brain.ask(brain.start('haiku'), 'hi')
    assert says in a


def test_a_server_that_is_not_running():
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()   # nothing listens there now
    cfg = {'ai': 'openai', 'aiUrl': f'http://127.0.0.1:{port}/v1', 'aiModel': 'm'}
    brain.use(cfg)
    try:
        a, _ = brain.ask(brain.start('haiku'), 'hi')
    finally:
        brain.use({})
    assert a.startswith("Can't reach your AI server at http://127.0.0.1") and 'Is it running?' in a
    with pytest.raises(brain.ServerError, match="Can't reach"):
        brain.models(cfg)


def test_extract_reads_json_from_an_http_model(server, tmp_path):
    shot = tmp_path / 's.jpg'
    shot.write_bytes(b'\xff\xd8')
    Fake.reply = (200, chunks('```json\n{"name": "Helm of Ages", "stats": ["+5 Armor"]}\n```'))
    assert brain.extract([(str(shot), '')])['name'] == 'Helm of Ages'
    body = Fake.got[0][3]
    assert body['messages'][0]['content'] == brain.EXTRACT and body['messages'][1]['content'][1]['type'] == 'image_url'
