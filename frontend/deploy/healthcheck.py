"""Container readiness checks; never call an LLM or expose configuration values."""
import json
import sys
from urllib.request import urlopen

if sys.argv[1] == 'rag':
    with urlopen('http://127.0.0.1:8001/health', timeout=8) as response:
        data = json.load(response)
    assert data.get('ready') and data.get('indexes') and all(data['indexes'].values())
else:
    with urlopen('http://127.0.0.1:8008/openapi.json', timeout=8) as response:
        assert '/voice/stt' in json.load(response)['paths']
