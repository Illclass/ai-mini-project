#!/usr/bin/env bash
# 개발용 통합 실행 스크립트: DB → 인증서버(:8080) → RAG(:8001) [→ 음성(:8008)]
#
#   ./dev.sh           DB · 인증서버 · RAG 실행
#   ./dev.sh --voice   음성 서비스까지 실행
#   Ctrl + C           이 스크립트가 띄운 서버를 모두 종료 (DB 컨테이너는 계속 실행)
#
#   RAG 앱 선택 (기본: 새 구조 app.main)
#     RAG_APP=<모듈:앱> ./dev.sh   # 다른 RAG 앱으로 실행 (기본 app.main:app)
#
# 로그: logs/auth.log · logs/rag.log · logs/voice.log

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT/logs"
DB_CONTAINER="ai-mini-db"
DB_PORT=53301
PY=python3.11
RAG_APP="${RAG_APP:-app.main:app}"

WITH_VOICE=0
for arg in "$@"; do
  case "$arg" in
    --voice) WITH_VOICE=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "알 수 없는 옵션: $arg (./dev.sh --help)"; exit 1 ;;
  esac
done

# ---------- 출력 ----------
info() { printf '\033[36m▶ %s\033[0m\n' "$*"; }
ok()   { printf '\033[32m✔ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*"; }
fail() { printf '\033[31m✘ %s\033[0m\n' "$*"; exit 1; }

# ---------- 종료 처리 ----------
PIDS=""
cleanup() {
  local rc=$?
  trap - INT TERM EXIT
  [ -z "$PIDS" ] && exit "$rc"
  echo
  info "서버 종료 중..."
  for pid in $PIDS; do
    pkill -TERM -P "$pid" 2>/dev/null
    kill -TERM "$pid" 2>/dev/null
  done
  sleep 1
  for pid in $PIDS; do
    kill -KILL "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null   # "Terminated" 메시지 숨김
  done
  ok "종료 완료 (DB 컨테이너는 계속 실행 중: docker stop $DB_CONTAINER)"
  exit "$rc"
}
trap cleanup INT TERM EXIT

# ---------- 공통 함수 ----------
port_busy() { lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1 || nc -z localhost "$1" >/dev/null 2>&1; }

require_free_port() {
  if port_busy "$1"; then
    warn "$1 포트를 이미 사용 중입니다 ($2):"
    lsof -iTCP:"$1" -sTCP:LISTEN -P | tail -n +2 | awk '{print "   PID " $2 "  " $1}'
    fail "해당 프로세스를 종료한 뒤 다시 실행하세요 (kill <PID>)"
  fi
}

# $1=포트 $2=이름 $3=PID $4=로그 $5=제한시간(초)
wait_for_port() {
  local i=0
  while [ "$i" -lt "$5" ]; do
    port_busy "$1" && return 0
    if ! kill -0 "$3" 2>/dev/null; then
      warn "$2 이(가) 시작 중에 종료되었습니다. 로그 마지막 부분:"
      tail -20 "$4"
      fail "$2 실행 실패 ($4)"
    fi
    sleep 1; i=$((i + 1))
  done
  tail -20 "$4"
  fail "$2 이(가) ${5}초 안에 준비되지 않았습니다 ($4)"
}

require_env_file() {
  [ -f "$1" ] || fail "$1 이(가) 없습니다. .env.example 을 참고해 만들어 주세요."
}

# 루트 가상환경(.venv) 하나를 모든 Python 서비스가 같이 씀 — 패키지 목록은 루트 requirements.txt
VENV_PY="$ROOT/.venv/bin/python"
ensure_venv() {
  if [ ! -x "$VENV_PY" ]; then
    command -v "$PY" >/dev/null || fail "$PY 이(가) 없습니다 (brew install python@3.11)"
    info "가상환경 생성 (.venv)"
    "$PY" -m venv "$ROOT/.venv" || fail "가상환경 생성 실패"
  fi
  if ! "$VENV_PY" -c "import langchain_openai, faiss, fastapi, faster_whisper, jose" 2>/dev/null; then
    info "패키지 설치 (처음 한 번, torch 포함 수 분 소요)"
    "$VENV_PY" -m pip install -q -U pip setuptools wheel &&
      "$VENV_PY" -m pip install -q -r "$ROOT/requirements.txt" ||
      fail "패키지 설치 실패 (requirements.txt)"
  fi
}

mkdir -p "$LOG_DIR"

# ---------- 0) 사전 점검 ----------
require_env_file "$ROOT/auth-server/.env"
require_env_file "$ROOT/rag-service/.env"
require_free_port 8080 "인증서버"
require_free_port 8001 "RAG"
if [ "$WITH_VOICE" = 1 ]; then
  require_env_file "$ROOT/voice-service/app/.env"
  require_free_port 8008 "음성"
  command -v ffmpeg >/dev/null || fail "ffmpeg 이(가) 없습니다 (brew install ffmpeg)"
fi

# auth-server/.env 의 DB_PASSWORD · JWT_SECRET 을 이 스크립트 환경으로 불러옴
set -a; . "$ROOT/auth-server/.env"; set +a
[ -n "${DB_PASSWORD:-}" ] || fail "auth-server/.env 에 DB_PASSWORD 가 비어 있습니다"
[ -n "${JWT_SECRET:-}" ]  || fail "auth-server/.env 에 JWT_SECRET 이 비어 있습니다"

# ---------- 1) DB ----------
command -v docker >/dev/null || fail "docker 가 없습니다 (Docker Desktop 설치)"
docker info >/dev/null 2>&1 || fail "Docker 가 실행 중이 아닙니다 (Docker Desktop 실행)"

if [ -z "$(docker ps -aq -f name="^${DB_CONTAINER}$")" ]; then
  info "DB: 컨테이너 생성 ($DB_CONTAINER, :$DB_PORT)"
  docker run -d --name "$DB_CONTAINER" -p "$DB_PORT":3306 \
    -e MARIADB_ROOT_PASSWORD="$DB_PASSWORD" -e MARIADB_DATABASE=sql_db \
    -v "$DB_CONTAINER":/var/lib/mysql mariadb:11 >/dev/null || fail "DB 컨테이너 생성 실패"
elif [ -z "$(docker ps -q -f name="^${DB_CONTAINER}$")" ]; then
  info "DB: 컨테이너 시작"
  docker start "$DB_CONTAINER" >/dev/null || fail "DB 컨테이너 시작 실패"
fi

i=0
until docker exec "$DB_CONTAINER" healthcheck.sh --connect --innodb_initialized >/dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -gt 60 ] && fail "DB 가 60초 안에 준비되지 않았습니다 (docker logs $DB_CONTAINER)"
  sleep 1
done

# users 테이블 (없을 때만 생성)
docker exec -i -e MYSQL_PWD="$DB_PASSWORD" "$DB_CONTAINER" mariadb -uroot sql_db <<'SQL' || fail "users 테이블 확인 실패 (DB 비밀번호가 컨테이너와 다른지 확인)"
CREATE TABLE IF NOT EXISTS `users` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL,
  `password` varchar(255) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
SQL
ok "DB 준비 완료 (localhost:$DB_PORT / sql_db)"

# ---------- 2) 인증서버 ----------
info "인증서버: 빌드"
(cd "$ROOT/auth-server" && ./gradlew :app:installDist --no-configuration-cache -q) \
  > "$LOG_DIR/auth-build.log" 2>&1 || { tail -20 "$LOG_DIR/auth-build.log"; fail "인증서버 빌드 실패 (logs/auth-build.log)"; }

info "인증서버: 실행"
(cd "$ROOT/auth-server" && exec app/build/install/app/bin/app) > "$LOG_DIR/auth.log" 2>&1 &
AUTH_PID=$!; PIDS="$PIDS $AUTH_PID"
wait_for_port 8080 "인증서버" "$AUTH_PID" "$LOG_DIR/auth.log" 30
ok "인증서버 준비 완료 (http://localhost:8080/login)"

# ---------- 3) RAG ----------
ensure_venv
info "RAG: 실행 ($RAG_APP)"
(cd "$ROOT/rag-service" && exec "$VENV_PY" -m uvicorn "$RAG_APP" --port 8001) \
  > "$LOG_DIR/rag.log" 2>&1 &
RAG_PID=$!; PIDS="$PIDS $RAG_PID"
wait_for_port 8001 "RAG" "$RAG_PID" "$LOG_DIR/rag.log" 60
ok "RAG 준비 완료 (http://127.0.0.1:8001/docs)"

# ---------- 4) 음성 (선택) ----------
if [ "$WITH_VOICE" = 1 ]; then
  info "음성: 실행 (첫 실행은 Whisper 모델 다운로드로 오래 걸릴 수 있음)"
  (cd "$ROOT/voice-service" && exec "$VENV_PY" -m uvicorn app.main:app --port 8008) \
    > "$LOG_DIR/voice.log" 2>&1 &
  VOICE_PID=$!; PIDS="$PIDS $VOICE_PID"
  wait_for_port 8008 "음성" "$VOICE_PID" "$LOG_DIR/voice.log" 300
  ok "음성 준비 완료 (http://localhost:8008/index.html, 로그인 후 접속)"
fi

# ---------- 실행 중 ----------
echo
ok "모두 실행 중 — 종료하려면 Ctrl + C"
echo "   회원가입   http://localhost:8080/signup"
echo "   RAG 질의   http://127.0.0.1:8001/docs"
[ "$WITH_VOICE" = 1 ] && echo "   음성 데모  http://localhost:8008/index.html"
echo "   로그       tail -f logs/*.log"

# 서버 하나가 죽으면 알려 주고 전체 종료
while true; do
  for pid in $PIDS; do
    if ! kill -0 "$pid" 2>/dev/null; then
      warn "서버 하나가 종료되었습니다 (PID $pid). logs/ 를 확인하세요."
      cleanup
    fi
  done
  sleep 2
done
