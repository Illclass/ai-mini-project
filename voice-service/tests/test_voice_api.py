"""음성 API 테스트 — 담당: 김규빈. Whisper·OpenAI 없이 돈다 (서비스 모듈을 가짜로 바꿔 끼움).

    cd voice-service && ../.venv/bin/python -m pytest -q tests
"""
import sys
import time
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

SECRET = "test-only-secret-key-for-voice-api-0123456789"
calls = {}


class _Seg:
    def __init__(self, text):
        self.text = text


class _FakeWhisper:
    def transcribe(self, path, language=None, **kwargs):
        calls["stt_language"], calls["prompt"] = language, kwargs.get("initial_prompt")
        return ([_Seg(t) for t in calls.get("speech", [" 불산 보호구는 ", "무엇인가요?"])]), None


stt_stub = types.ModuleType("app.services.stt_service")
stt_stub.model = _FakeWhisper()
stt_stub.convert_webm_to_wav = lambda src, dst: open(dst, "wb").write(b"wav")
stt_stub.transcribe_audio_file_local = lambda path: "text"
tts_stub = types.ModuleType("app.services.tts_service")
tts_stub.synthesize = lambda text: (calls.__setitem__("tts_text", text), b"ID3fake-mp3")[1]
tts_stub.text_to_speech = lambda text, path: path
sys.modules["app.services.stt_service"] = stt_stub
sys.modules["app.services.tts_service"] = tts_stub

from app.routers.voice_router import router  # noqa: E402

app = FastAPI()
app.include_router(router, prefix="/voice")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    calls.clear()
    return TestClient(app)


def token(secret=SECRET, exp_in=600):
    return jwt.encode({"sub": "7", "username": "worker", "iss": "simple-auth-server", "exp": int(time.time()) + exp_in},
                      secret, algorithm="HS256")


def test_requires_valid_jwt(client):
    files = {"audio": ("a.webm", b"x", "audio/webm")}
    assert client.post("/voice/stt", files=files).status_code == 401
    assert client.post("/voice/stt", files=files, headers={"Authorization": f"Bearer {token('wrong-secret-' * 4)}"}).status_code == 401
    assert client.post("/voice/stt", files=files, headers={"Authorization": f"Bearer {token(exp_in=-10)}"}).status_code == 401


def test_stt_with_cookie_and_language_hint(client):
    client.cookies.set("ACCESS_TOKEN", token())
    r = client.post("/voice/stt", files={"audio": ("../../evil.webm", b"audio", "audio/webm")}, data={"language": "ko"})
    assert r.status_code == 200 and r.json() == {"text": "불산 보호구는 무엇인가요?", "language": "ko"}
    assert calls["stt_language"] == "ko"


def test_stt_errors_are_status_codes(client):
    h = {"Authorization": f"Bearer {token()}"}
    assert client.post("/voice/stt", files={"audio": ("a.exe", b"x", "application/octet-stream")}, headers=h).status_code == 400
    assert client.post("/voice/stt", files={"audio": ("a.webm", b"x", "audio/webm")}, data={"language": "ja"}, headers=h).status_code == 422
    calls["speech"] = []
    assert client.post("/voice/stt", files={"audio": ("a.webm", b"x", "audio/webm")}, headers=h).status_code == 422


def test_stt_rejects_text_in_wrong_script_and_sends_terms(client):
    h = {"Authorization": f"Bearer {token()}"}
    calls["speech"] = ["Sometimes we think we are on the wrong road."]   # 크메르어 녹음을 영어로 잘못 들음
    assert client.post("/voice/stt", files={"audio": ("a.webm", b"x", "audio/webm")}, data={"language": "km"}, headers=h).status_code == 422
    calls["speech"] = ["处理氢氟酸时需要哪些防护用品"]
    assert client.post("/voice/stt", files={"audio": ("a.webm", b"x", "audio/webm")}, data={"language": "zh"}, headers=h).status_code == 200
    assert "氢氟酸" in calls["prompt"]


def test_tts_returns_mp3_bytes(client):
    h = {"Authorization": f"Bearer {token()}"}
    r = client.post("/voice/tts", json={"text": "보호장갑을 착용하세요.", "language": "ko"}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content.startswith(b"ID3")
    assert calls["tts_text"] == "보호장갑을 착용하세요."
    assert client.post("/voice/tts", json={"text": "x" * 1501}, headers=h).status_code == 422


def test_missing_secret_is_503(client, monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    assert client.post("/voice/tts", json={"text": "a"}, headers={"Authorization": f"Bearer {token()}"}).status_code == 503
