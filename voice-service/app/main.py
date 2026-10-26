##### The following practice code is intended for educational purposes only. For contact : architect@ajou.ac.kr, audit@korea.ac.kr 林圣烨 Ph.D.
#### This practice code is not a completed commercial version but has been developed for educational purposes; supplementation is required depending on the deployment objective for use as a commercial service.

from fastapi import FastAPI, Depends, HTTPException, status, Cookie, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

from app.routers.stt_router import router as stt_router
from app.routers.tts_router import router as tts_router
from app.routers.stt_tts_router import router as stt_tts_router
from app.routers.voice_router import router as voice_router

from pathlib import Path
from dotenv import load_dotenv
import os
import openai

# 0) Load environment variables (.env)

APP_DIR = Path(__file__).resolve().parent           # .../voice-ai-pjt/app
PROJECT_DIR = APP_DIR.parent                        # .../voice-ai-pjt

dotenv_path = APP_DIR / ".env"                      # app/.env
# dotenv_path = PROJECT_DIR / ".env"                # Replace with this line if placed in the root directory
load_dotenv(dotenv_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("API key is not configured. Please check the .env file.")
openai.api_key = OPENAI_API_KEY

# 1) Path configuration

STATIC_DIR = APP_DIR / "static"                     # Static resources such as HTML/CSS/JS, favicon
UPLOAD_DIR = APP_DIR / "routers" / "uploads"

INDEX_HTML   = STATIC_DIR / "index.html"
STT_HTML     = STATIC_DIR / "stt.html"
TTS_HTML     = STATIC_DIR / "tts.html"
STT_TTS_HTML = STATIC_DIR / "stt-tts.html"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 2) FastAPI App

app = FastAPI()

# JWT 검증은 app/auth.py 하나로 통일 (비밀키는 환경변수 JWT_SECRET, Bearer·쿠키 모두 허용)
from app.auth import get_current_user

# 4) (Key) HTML is served only as a "route" + protected with Depends
#    - Direct access to /index.html is also blocked (= JWT required to open)
#    - StaticFiles is used only for serving non-HTML static resources (CSS/JS/images)

def _must_exist(p: Path, name: str):
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"{name} not found: {p}")

@app.get("/", include_in_schema=False)
async def root_page(current_user: dict = Depends(get_current_user)):
    _must_exist(INDEX_HTML, "index.html")
    return FileResponse(INDEX_HTML)

@app.get("/index.html", include_in_schema=False)
async def index_page(current_user: dict = Depends(get_current_user)):
    _must_exist(INDEX_HTML, "index.html")
    return FileResponse(INDEX_HTML)

@app.get("/stt.html", include_in_schema=False)
async def stt_page(current_user: dict = Depends(get_current_user)):
    _must_exist(STT_HTML, "stt.html")
    return FileResponse(STT_HTML)

@app.get("/tts.html", include_in_schema=False)
async def tts_page(current_user: dict = Depends(get_current_user)):
    _must_exist(TTS_HTML, "tts.html")
    return FileResponse(TTS_HTML)

@app.get("/stt-tts.html", include_in_schema=False)
# [Q02] 음성 통번역 HTML의 접근 제어
# 힌트: 페이지 함수 실행 전 인증 의존성이 먼저 수행되도록 연결하세요.
# TODO Q02: 기본값 None을 인증 의존성 호출로 바꾸세요.
async def stt_tts_page(current_user: dict = Depends(get_current_user)):
    _must_exist(STT_TTS_HTML, "stt-tts.html")
    return FileResponse(STT_TTS_HTML)

# 5) Static file mount
#    Note: If /static is opened with StaticFiles(directory=STATIC_DIR),
#       "direct access" to /static/index.html becomes possible.
#       Therefore, HTML files must be served only as "routes",
#       and it is safer to separate static resources into a dedicated directory.
#
#    ▶ Recommended structure:
#       app/static/pages/*.html (served only via routes)
#       app/static/assets/*     (served via mount)
#
#    Here, we configure with minimal intervention to fit the current structure (single STATIC_DIR):
#    - Allow access under /static, but block direct access to HTML files
#      such as /static/index.html with a 404 response
#      (HTML filename requests are blocked in the Middleware below)

@app.middleware("http")
async def block_direct_html_under_static(request: Request, call_next):
    # Block direct requests for HTML files via the /static path
    # (e.g., /static/index.html, /static/stt.html, etc.)
    path = request.url.path
    if path.startswith("/static/") and path.lower().endswith(".html"):
        return Response(status_code=404)
    return await call_next(request)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")      # /static/*
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")    # /uploads/*

# 6) CORS
#   - If using authentication cookie-based approach, the combination of allow_origins="*" + allow_credentials=True is not allowed.
#   - If the API is only used from the current page (8008), there is no need to set CORS permissively.
#   - If there is a fetch that integrates with 8080 (authentication server), allow only the exact origin.

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8008",
        "http://127.0.0.1:8008",
        "http://localhost:5174",   # ChemBridge 프론트 (Vite). 보통은 Vite 프록시로 같은 출처라 필요 없다
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 7) Prevent favicon 404 (Depends can be removed if you want to handle it as 204 without authentication)
#    - Current requirement: Block access without login, so Depends is maintained

@app.get("/favicon.ico", include_in_schema=False)
def favicon(current_user: dict = Depends(get_current_user)):
    ico = STATIC_DIR / "favicon.ico"
    if ico.exists():
        return FileResponse(
            ico,
            media_type="image/x-icon",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    return Response(status_code=204)


# 8) Router registration (if you want to protect the API with JWT as well, it is recommended to apply Depends(get_current_user) inside the router)

app.include_router(stt_router, prefix="/stt")
app.include_router(tts_router, prefix="/tts")
app.include_router(stt_tts_router, prefix="/stt-tts")
app.include_router(voice_router, prefix="/voice")   # ChemBridge 프론트 음성 모드

# 9) Local execution

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8008, reload=True)
    
# 1. Direct access blocking without authentication is applied: Both of the following must be blocked to function correctly
# http://localhost:8008/index.html  → 401
# http://localhost:8008/static/index.html → 404 (blocked by middleware)
    
# With virtual environment activated
# python -m pip install --upgrade pip setuptools wheel
# python -m pip install -r requirements.txt 

# Run the voice assistant app
# python -m uvicorn app.main:app --port 8008
# Step-by-step operation test after Java authentication..
# http://localhost:8008/index.html -> Voice recognition recording test
# http://localhost:8008/stt-tts.html -> Voice recognition recording -> STT conversion demo

