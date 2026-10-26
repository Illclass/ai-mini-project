from fastapi import APIRouter, Form, Depends, HTTPException, Cookie
from app.services.tts_service import text_to_speech
import os

router = APIRouter()

# JWT 검증은 app/auth.py 하나로 통일 (비밀키는 환경변수 JWT_SECRET, Bearer·쿠키 모두 허용)
from app.auth import get_current_user

# Path to the uploads folder for saving output files
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/")
async def tts_endpoint(
    current_user: dict = Depends(get_current_user),   # Authentication added
    text: str = Form(...)
):
    try:
        file_name = "openai_tts_output.mp3"
        output_path = os.path.join(UPLOAD_DIR, file_name)

        # Actual TTS generation processing
        file_path = text_to_speech(text, output_path)  # Absolute path for internal storage

        # Return web path for client
        return {
            "message": "TTS processing complete (OpenAI TTS)",
            "file_path": f"/uploads/{file_name}",  # Return web path only
            "user": current_user  # For debugging: verify user information
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))