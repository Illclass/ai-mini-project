"""Local Compose integration checks. --live also calls the configured RAG/TTS providers.
Secrets stay in memory; only status summaries are printed. A separate test account is created.
"""
import argparse
import http.cookiejar
import json
import secrets
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://localhost:5190')
parser.add_argument('--live', action='store_true')
parser.add_argument('--restart', action='store_true', help='Restart only this Compose DB/auth to check persistence')
args = parser.parse_args()
base = args.url.rstrip('/')
assert urllib.parse.urlparse(base).hostname == 'localhost', 'This smoke test is for the local Compose stack only.'
jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def call(path, payload=None, content_type='application/json', expected=200):
    body = payload
    if isinstance(payload, dict):
        body = (urllib.parse.urlencode(payload) if content_type.startswith('application/x-www-form-urlencoded') else json.dumps(payload)).encode()
    request = urllib.request.Request(base+path, data=body, headers={
        'Content-Type': content_type, 'Accept': 'application/json', 'Origin': base,
    })
    try:
        response = client.open(request, timeout=180)
    except urllib.error.HTTPError as error:
        response = error
    data = response.read()
    assert response.code == expected, f'{path}: expected {expected}, got {response.code}'
    return data, response.headers

call('/api/auth/check', expected=401)
call('/rag-query', {'question':'보관 방법은?', 'topic':'chemical_safety', 'language':'ko'}, expected=401)
call('/voice/tts', {'text':'테스트', 'language':'ko'}, expected=401)
print('PASS unauthenticated auth/RAG/voice return 401')
username = 'compose_test_'+secrets.token_hex(5)
credentials = {'username': username, 'password': secrets.token_urlsafe(20)}
form = 'application/x-www-form-urlencoded'
call('/api/signup', credentials, form, expected=201)
call('/api/login', credentials, form)
assert json.loads(call('/api/auth/check')[0])['ok']
health = json.loads(call('/health')[0])
assert health['ready'] and all(health['indexes'].values())
print('PASS signup/login cookies, both RAG indexes ready')
html = call('/')[0].decode()
assert 'id="app"' in html
pdf = call('/guides/before.pdf')[0]
assert pdf.startswith(b'%PDF-')
print('PASS built frontend and PDF via web proxy')
# Check the actual production dependency graph, including lazy PDF viewer chunks.
modules = [urllib.parse.urljoin(base+'/', ref) for ref in re.findall(r'<script[^>]+src="([^"]+)"',html)]
seen, originals, workers = set(), set(), 0
while modules:
    module = modules.pop()
    if module in seen: continue
    seen.add(module)
    assert len(seen) <= 40, 'Unexpectedly large frontend module graph'
    path = urllib.parse.urlsplit(module).path
    code, headers = call(path)
    if path.endswith('.mjs'):
        assert headers.get_content_type() in ['application/javascript','text/javascript'], 'ES module worker has wrong MIME type'
        workers += 1
        continue
    text = code.decode()
    for ref in re.findall(r'["\']((?:\./|/assets/|assets/)[^"\']+-[A-Za-z0-9_-]{8}\.(?:js|mjs))["\']',text):
        modules.append(urllib.parse.urljoin(module, '/'+ref if ref.startswith('assets/') else ref))
    originals.update(re.findall(r'["\'](/assets/[^"\']+\.pdf)["\']',text))
assert workers, 'No PDF ES module worker found in built app'
assert len(originals) == 27, f'Expected 27 original PDFs, found {len(originals)}'
for path in originals:
    assert call(path)[0].startswith(b'%PDF-'), 'Original PDF is missing or served as HTML'
print('PASS PDF worker JavaScript MIME and all 27 bundled original PDFs')
if args.live:
    for question, product in [('황산을 보관할 때 어떤 점을 주의해야 하나요?', 'sigma-339741'), ('화학물질을 실내에 보관할 때 용기를 어떻게 관리하고 나눠 둬야 하나요?', None)]:
        result = json.loads(call('/rag-query', {'question':question, 'topic':'chemical_safety', 'language':'ko', 'product_id':product, 'equipment_id':None})[0])
        assert isinstance(result.get('answer'), str) and result['answer'].strip()
        assert isinstance(result.get('sources'), list)
        print('RAG', 'product' if product else 'general', 'answer_chars=',len(result['answer']), 'sources=',len(result['sources']), 'handoff=',result.get('handoff'))
    audio, headers = call('/voice/tts', {'text':'작업 전에 안전 정보를 확인하세요.', 'language':'ko'})
    assert headers.get('Content-Type','').startswith('audio/') and len(audio)>100
    import tempfile
    with tempfile.TemporaryDirectory(prefix='chembridge-compose-smoke-') as folder:
        mp3, webm = Path(folder)/'speech.mp3', Path(folder)/'speech.webm'
        mp3.write_bytes(audio)
        subprocess.run(['ffmpeg','-loglevel','error','-i',str(mp3),'-c:a','libopus',str(webm)],check=True)
        boundary='ComposeSmoke'+secrets.token_hex(12)
        payload=(f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\nko\r\n--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="speech.webm"\r\nContent-Type: audio/webm\r\n\r\n').encode()+webm.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
        result=json.loads(call('/voice/stt',payload,f'multipart/form-data; boundary={boundary}')[0])
        assert result['text'].strip()
        print('PASS real TTS → WebM → STT; recognized_chars=',len(result['text']))
if args.restart:
    subprocess.run(['docker','compose','restart','db','auth'],check=True,stdout=subprocess.DEVNULL)
    for _ in range(40):
        try:
            call('/api/login', credentials, form)
            break
        except (AssertionError,urllib.error.URLError):
            time.sleep(2)
    else:
        raise RuntimeError('DB/auth did not recover after restart')
    assert json.loads(call('/api/auth/check')[0])['ok']
    print('PASS account survives Compose DB/auth restart')
call('/api/logout',{},form)
call('/api/auth/check',expected=401)
print('PASS logout clears authentication')
