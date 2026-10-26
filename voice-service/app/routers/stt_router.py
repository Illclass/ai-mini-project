from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, Cookie
import shutil
import os
import uuid

# Replace with local Whisper STT function (transcribe_audio_file_local)
from app.services.stt_service import transcribe_audio_file_local, convert_webm_to_wav

router = APIRouter()

# JWT 검증은 app/auth.py 하나로 통일 (비밀키는 환경변수 JWT_SECRET, Bearer·쿠키 모두 허용)
from app.auth import get_current_user

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/")
async def stt(
    current_user: dict = Depends(get_current_user),
    audio: UploadFile = File(...)):
    # 업로드 파일명은 쓰지 않는다 (경로 조작·덮어쓰기 방지). 무작위 이름으로 저장하고 처리 뒤 지운다.
    request_id = uuid.uuid4().hex
    webm_path = os.path.join(UPLOAD_DIR, f"{request_id}.webm")
    wav_path = os.path.join(UPLOAD_DIR, f"{request_id}.wav")
    with open(webm_path, "wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)
    try:
        convert_webm_to_wav(webm_path, wav_path)
        text = transcribe_audio_file_local(wav_path)
        return {"text": text, "user": current_user}
    except Exception:
        # 오류를 200 으로 돌려주지 않는다
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Speech recognition failed")
    finally:
        for path in (webm_path, wav_path):
            if os.path.exists(path):
                os.remove(path)
