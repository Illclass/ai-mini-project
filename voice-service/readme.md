# ChemBridge 음성 API (프론트 음성 모드)

| 경로 | 입력 | 출력 |
|---|---|---|
| `POST /voice/stt` | multipart `audio`(webm·ogg·mp4·wav), `language`(ko·zh·vi·en·km) | `{"text": "..."}` · 422 인식 실패 |
| `POST /voice/tts` | JSON `{"text": "...", "language": "ko"}` (1500자 이하) | `audio/mpeg` |

- 로그인 필요: Java 인증서버 토큰(ACCESS_TOKEN 쿠키 또는 Bearer). 비밀키는 환경변수 `JWT_SECRET` (`app/auth.py`)
- 인식 정확도를 위해 언어별 물질명을 Whisper 에 힌트로 준다 (`voice_router.TERMS`). 고른 언어의 문자가 아닌 결과는 422
- 업로드 파일은 임시 폴더에서 처리 후 삭제
- 테스트: `cd voice-service && ../.venv/bin/python -m pytest -q tests` (Whisper·OpenAI 없이 동작)

---

# Install ffmpeg (Linux Ubuntu)
sudo apt update
sudo apt install -y ffmpeg pkg-config

# Install ffmpeg (MacOS)
brew install ffmpeg
ffmpeg -version

# With virtual environment activated
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt