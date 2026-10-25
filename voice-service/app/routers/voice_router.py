"""ChemBridge 음성 API — 담당: 김규빈

프론트 음성 모드: 녹음 → POST /voice/stt → (질문 확인·전송) → RAG → POST /voice/tts → 재생
    POST /voice/stt   multipart: audio(webm/ogg/mp4/wav), language(ko·zh·vi·en·km) → {"text": "..."}
    POST /voice/tts   JSON {"text": "...", "language": "ko"} → audio/mpeg (파일로 남기지 않고 바로 응답)

- 로그인 필요 (app/auth.py, RAG 와 같은 JWT)
- 업로드 파일은 임시 폴더에 무작위 이름으로 저장하고 처리 뒤 바로 지운다 (업로드 파일명은 쓰지 않음)
- 오류는 상태 코드로 돌려준다 (400 형식·길이, 413 너무 큼, 422 인식 결과 없음, 502 TTS 실패, 500 그 밖)
"""
import logging
import os
import re
import tempfile
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.services.stt_service import convert_webm_to_wav, model as whisper_model
from app.services.tts_service import synthesize

logger = logging.getLogger(__name__)
router = APIRouter(tags=["voice"])

LANGUAGES = ("ko", "zh", "vi", "en", "km")       # rag-service/rag/schema.py LANGUAGES 와 같은 순서
AUDIO_TYPES = {".webm", ".ogg", ".mp4", ".m4a", ".wav", ".mp3"}
MAX_AUDIO_BYTES = 10 * 1024 * 1024               # 약 10분 분량 (질문 한 개면 충분)
MAX_TTS_CHARS = 1500                              # 읽기용 문장 상한 (프론트가 줄여서 보냄)

# Whisper 인식 힌트: 물질명·용어를 먼저 알려 주면 동음이의어로 잘못 받아쓰는 일이 줄어든다
# (예: 중국어 氢氟酸 → 轻浮酸, 베트남어 axit flohydric → "ác xịt phlo híd rực")
TERMS = {
    "ko": "불산, 불화수소, 황산, 과산화수소, 암모니아수, 염산, 질산, 인산, TMAH, 현상액, 아세톤, 메탄올, IPA, PGMEA, 수산화나트륨, 보호구, MSDS, 중대재해처벌법",
    "zh": "氢氟酸、硫酸、过氧化氢、氨水、盐酸、硝酸、磷酸、TMAH、显影液、丙酮、甲醇、异丙醇、PGMEA、氢氧化钠、防护用品、MSDS",
    "vi": "axit flohydric, axit sunfuric, hydro peroxit, amoniac, axit clohydric, axit nitric, axit photphoric, TMAH, axeton, metanol, IPA, PGMEA, natri hydroxit, đồ bảo hộ, MSDS",
    "en": "hydrofluoric acid, sulfuric acid, hydrogen peroxide, ammonium hydroxide, hydrochloric acid, nitric acid, phosphoric acid, TMAH, acetone, methanol, IPA, PGMEA, sodium hydroxide, PPE, MSDS",
    "km": "អាស៊ីតហ្វ្លុយអូរីក អាស៊ីតស៊ុលហ្វួរិក ឧបករណ៍ការពារ MSDS",
}
# 인식 결과가 고른 언어의 문자가 아니면(예: 크메르어로 골랐는데 영어 문장) 잘못 들은 것으로 보고 버린다
SCRIPTS = {"ko": r"[가-힣]", "zh": r"[\u4e00-\u9fff]", "km": r"[\u1780-\u17ff]",
           "vi": r"[A-Za-zÀ-ỹ]", "en": r"[A-Za-z]"}


@router.post("/stt")
async def stt(
    audio: UploadFile = File(...),
    language: Literal["ko", "zh", "vi", "en", "km"] = Form("ko"),
    user: dict = Depends(get_current_user),
):
    """녹음 → 텍스트. language 는 Whisper 인식 언어 힌트 (자동 감지보다 짧은 질문에서 정확함)."""
    ext = os.path.splitext(audio.filename or "")[1].lower() or ".webm"
    if ext not in AUDIO_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported audio type: {ext}")
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio is too large")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio")

    with tempfile.TemporaryDirectory(prefix="chembridge-stt-") as tmp:
        src, wav = os.path.join(tmp, "input" + ext), os.path.join(tmp, "input.wav")
        with open(src, "wb") as f:
            f.write(data)
        try:
            convert_webm_to_wav(src, wav)   # ffmpeg 는 확장자와 관계없이 변환한다
            segments, _ = whisper_model.transcribe(wav, language=language, beam_size=5, vad_filter=True,
                                                   initial_prompt=TERMS[language])
            text = "".join(seg.text for seg in segments).strip()
        except Exception:
            logger.exception("STT failed")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Speech recognition failed") from None
    if not text or not re.search(SCRIPTS[language], text):
        logger.info("STT rejected lang=%s text=%r", language, text[:80])
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No speech recognized")
    logger.info("STT ok user=%s lang=%s chars=%d", user["id"], language, len(text))
    return {"text": text, "language": language}


class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TTS_CHARS)
    language: Literal["ko", "zh", "vi", "en", "km"] = "ko"


@router.post("/tts", response_class=Response,
             responses={200: {"content": {"audio/mpeg": {}}, "description": "MP3 음성"}})
def tts(req: TtsRequest, user: dict = Depends(get_current_user)):
    """읽기용 문장 → MP3. OpenAI tts-1 은 입력 문장의 언어로 읽는다 (language 는 기록용)."""
    if not req.text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty text")
    try:
        audio = synthesize(req.text.strip())
    except Exception:
        logger.exception("TTS failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Speech synthesis failed") from None
    logger.info("TTS ok user=%s lang=%s chars=%d", user["id"], req.language, len(req.text))
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
