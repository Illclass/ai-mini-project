# AI 서비스 개발 Mini-project

SKALA「AI 서비스 개발 Mini-project」(3일 과정) 조별 프로젝트 저장소입니다.
강의 제공 압축파일(`ai-practice.zip`)을 기반으로 폴더를 정리했습니다.

```
Vue.js 프론트 → Java 인증서버(:8080, JWT 발급) → FastAPI AI 서비스
                                              ├─ RAG 서비스(:8001)  PDF·웹 → FAISS → OpenAI
                                              └─ 음성 서비스(:8008) Whisper STT → GPT → TTS
```

---

## 📌 원본 압축파일에서 바뀐 점

> 압축파일을 받은 팀원은 아래 표를 보고 경로를 맞춰 주세요.

### 1. 폴더 이름 변경

교재 Day 3 `docker-compose.yml` 예시의 `build` 경로(`./auth-server`, `./rag-service`, `./frontend`)에 맞췄습니다.

| 원본 (`share/…`) | 변경 후 | 내용 |
|---|---|---|
| `workplace/` | **`auth-server/`** | Java 인증서버 (회원가입·로그인·JWT) |
| `rag-code-template_ext/` | **`rag-service/`** | External RAG 서비스 템플릿 (조별 직접 구현 대상) |
| `voice-ai_code/` | **`voice-service/`** | 음성 서비스 (STT → GPT → TTS, Day1 데모·확장 트랙) |
| `intro_main.html` 외 2개 (루트) | **`consoles/`** | RAG API 테스트용 콘솔 페이지 |
| — | `frontend/` (예정) | Vue.js 프론트 — 압축파일에 없음, 추후 추가 |

- 코드 안에서 폴더명을 경로로 참조하는 곳은 없어서 **이름 변경으로 동작이 바뀌지 않습니다.**
- Java 패키지명 `workplace`, Gradle 프로젝트명 `java-server`, 서비스 안의 파일명은 원본 그대로입니다.
  (주석에 `workplace % ./gradlew build`라고 나오면 `auth-server`로 읽으면 됩니다.)

### 2. 파일 수정

| 파일 | 변경 내용 | 이유 |
|---|---|---|
| `voice-service/requirements.txt` | UTF-16 → **UTF-8**, CRLF → LF (패키지 내용 동일) | UTF-16이면 `pip install -r` 이 실패할 수 있음 |

### 3. 실습 빈칸(TODO) 채움

원본 코드는 **빈칸 채우기 실습** 형태라 그대로는 회원가입·로그인·PDF 질의가 동작하지 않았습니다. 모두 채워 두었습니다.

| 서비스 | TODO | 채운 내용 |
|---|---|---|
| `auth-server` `SimpleAuthServer.java` | ① 로그인 검증 | `authService.login(username, password)` |
| | ② 세션 조회 | `SESSION_STORE.get(sessionId)` |
| | ③ JWT 검증 | `JwtUtil.verifyToken(token)` |
| | ④ 인증 실패 조건 | `sessionUser == null && !jwtOk` |
| | ⑤-A 비밀번호 해시 | `BCrypt.hashpw(rawPassword, BCrypt.gensalt(12))` |
| | ⑤-B 비밀번호 검증 | `BCrypt.checkpw(rawPassword, u.getPassword())` |
| `rag-service` `rag_external-web_pdf_closed_llm.py` | Q01 청크 설정 | `chunk_size=500, chunk_overlap=80` |
| | Q02 PDF 벡터화 | `FAISS.from_documents(docs, OpenAIEmbeddings())` |
| | Q03 저장소 선택 | `VECTORSTORE_PDF` |
| | Q04 유사도 검색 | `similarity_search_with_score(prompt, k=top_k)` |
| | Q05 LLM 호출 | `llm.invoke([HumanMessage(content=full_prompt)]).content` |
| `voice-service` `main.py` · `routers/stt_tts_router.py` | Q01 JWT 검증 · Q02 페이지 보호 | `jwt.decode(...)` · `Depends(get_current_user)` |
| | Q03 STT · Q04 번역 · Q05 TTS | `transcribe_audio_file_local` · `get_llm_response` · `text_to_speech` |

- 검증: 회원가입 → 로그인(401/200) → JWT·세션 쿠키 검증 → 위조 토큰 401, PDF 업로드 → 질의 → 문서에 없는 질문은 "찾을 수 없습니다" 까지 확인.
- `voice-service` 는 코드만 채웠고 **실행 검증은 아직** 하지 않았습니다.

### 4. 새로 추가

| 파일 | 내용 |
|---|---|
| `dev.sh` | DB · 인증서버 · RAG(· 음성)를 한 번에 실행하는 개발용 스크립트 |
| `.gitignore` | `.env`, 빌드 산출물(`.gradle/`, `build/`, `bin/`), `__pycache__`, 가상환경, `node_modules`, 음성 파일, `faiss_db/`, `logs/` 등 제외 |
| `.env.example` | 필요한 환경변수 목록 (값은 비워 둠) |
| `README.md` | 이 문서 |

### 5. 제외한 것

- `__pycache__/`, `.DS_Store` 는 복사하지 않았습니다.
- `rag-service/.env`(원본에 API 키 포함)와 `rag-service/faiss_db/`(미리 만든 벡터 인덱스)는 폴더에는 있지만 **Git에서는 무시**됩니다.
  인덱스를 팀원과 공유하려면 `.gitignore`의 `faiss_db/` 줄을 주석 처리하세요.

---

## 📁 폴더 구조

```
AI-mini/
├── auth-server/        Java 17 · Gradle · 순수 HttpServer · MariaDB · BCrypt · JWT
│   └── app/src/main/
│       ├── java/workplace/SimpleAuthServer.java
│       └── resources/web/   login.html · signup.html · app.js · style.css
├── rag-service/        FastAPI · LangChain 1.x · FAISS · OpenAI(gpt-4o)
│   ├── rag_external-web_pdf_closed_llm.py
│   ├── requirements-e.txt
│   └── faiss_db/{pdf,web}/
├── voice-service/      FastAPI · faster-whisper · OpenAI GPT(gpt-4o-mini) · TTS(tts-1, nova)
│   ├── app/{main.py, routers/, services/, static/}
│   ├── Dockerfile · docker-compose.yml
│   └── requirements.txt
├── consoles/           intro_main.html · external_index.html · internal_index.html
├── dev.sh              통합 실행 스크립트 (로그는 logs/)
├── .env.example
└── .gitignore
```

---

## 🔑 환경변수

서비스마다 `.env`를 읽는 위치가 다릅니다. `.env.example`을 참고해 각 위치에 만들어 주세요.

| 서비스 | 위치 | 변수 |
|---|---|---|
| rag-service | `rag-service/.env` | `OPENAI_API_KEY`, `JWT_SECRET`(Java와 같은 값), (`LLM_MODEL`, `EMBEDDING_MODEL`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`) |
| voice-service | `voice-service/app/.env` | `OPENAI_API_KEY`, (`WHISPER_MODEL`, 기본 `small`) |
| auth-server | 셸 환경변수 (`export`) | `JWT_SECRET`, `DB_PASSWORD` |

> ⚠️ **JWT 비밀키 불일치**: `voice-service/app/main.py`는 `SECRET_KEY = "RANDOM_SECRET_KEY"`로 하드코딩되어 있고,
> Java는 `JWT_SECRET` 환경변수를 읽습니다. 두 값이 같아야 토큰 검증이 통과합니다.
> `./dev.sh` 로 실행하면 `auth-server/.env` 의 `JWT_SECRET` 이 RAG 에도 그대로 전달됩니다.

---

## 🧩 rag-service 구조와 담당

공통 이름(요청·응답 필드, 메타데이터 키, topic·language 값)은 **`rag/schema.py` 에서만 정의**하고 모두 import 해서 씁니다.
지금은 끝까지 한 번 동작하도록 임시 구현이 들어 있고, 각자 자기 파일을 다듬으면 됩니다.

| 파일 | 담당 | 하는 일 | 지금 상태 |
|---|---|---|---|
| `app/main.py` | 정지우 | `/health`, `/rag-query`, CORS, 503 처리 | 동작 (로그 TODO) |
| `app/auth.py` | 정지우 | `ACCESS_TOKEN` 쿠키 JWT 검증 → 401 | 임시 구현 (검토 필요) |
| `rag/schema.py` | 전원 | 공통 이름 · 요청/응답 모델 | 완료 |
| `rag/chain.py` | 김규빈 · 박진근 | 비상 질문 확인 → 검색 → 생성 → `latency_ms` | 동작 (zh·vi 비상 표현 TODO) |
| `rag/stores.py` | 김규빈 | topic 별 FAISS 로드 (`faiss_db/law`, `faiss_db/msds`) | 동작 |
| `rag/query.py` | 김규빈 | 다국어 → 한국어, 동의어 확장 | 동의어 일부, 번역 TODO |
| `rag/retriever.py` | 김규빈 | `retrieve(question, topic, product_id, k)` | 동작 |
| `rag/prompt.py` | 박진근 | 프롬프트 규칙 | 임시 구현 |
| `rag/llm.py` | 박진근 | LLM 호출 · 타임아웃 · 재시도 | 동작 |
| `rag/generator.py` | 박진근 | 답변 · `sources` · `needs_review` · `handoff` | 임시 구현 |
| `ingest_law.py` | 윤서진 | 법령 조문 단위 적재 (`--out faiss_db/law`) | 동작 (`doc_id`·`topic`·`title`·`section` 추가 필요) |
| `ingest/ingest_msds.py` | 윤서진 | MSDS 16개 항목 단위 적재 → `faiss_db/msds` | 뼈대 |
| `eval/questions.json` · `eval/run_eval.py` | 김규빈 · 박진근 | 평가셋 · 검색 적중률 · 생성 판정 | 형식 예시 · 뼈대 |
| `rag_external-web_pdf_closed_llm.py` | — | 기존 템플릿 (참고용, `/upload-paper` 등) | 그대로 |

**흐름:** `RagRequest` → `chain.answer()` → `query.normalize_question()` → `retriever.retrieve()` → `generator.generate()` → `RagResponse`

**법령 인덱스 만들기** (rag-service/ 에서):

```bash
python ingest_law.py --input laws/sapa.pdf --law-name "중대재해 처벌 등에 관한 법률" --abbr sapa \
  --effective-date 2022-01-27 --source-url "https://www.law.go.kr/" --out faiss_db/law
```

> ⚠️ 브라우저(프론트)는 RAG 를 **`http://localhost:8001`** 로 불러야 합니다. 로그인 쿠키가 `localhost` 이름으로 발급되므로
> `127.0.0.1:8001` 로 부르면 쿠키가 전달되지 않아 401 이 납니다.

---

## ▶️ 실행 방법

### 처음 한 번: 가상환경 (루트에서 한 번에)

모든 Python 서비스(RAG · 음성 · 적재 스크립트)가 **루트의 `.venv` 하나**를 같이 씁니다.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt     # rag-service + voice-service 패키지 (torch 포함, 수 분)
```

> `voice-service/requirements.txt` 의 `requests` 는 langchain-community 와 맞추려고 `>=2.32.5,<3.0` 으로 풀었습니다.

### 한 번에 실행 (권장): `./dev.sh`

```bash
./dev.sh            # DB · 인증서버(:8080) · RAG(:8001)
./dev.sh --voice    # 음성 서비스(:8008)까지
```

**준비물**: Docker Desktop 실행 중 · Java 17+ · Python 3.11 · `auth-server/.env` · `rag-service/.env`
(`--voice` 는 추가로 `ffmpeg` · `voice-service/app/.env`)

스크립트가 하는 일:

1. 포트(8080·8001·8008)가 비어 있는지 확인 — 사용 중이면 PID를 알려 주고 멈춤
2. MariaDB 컨테이너 `ai-mini-db` 생성/시작 → `users` 테이블이 없으면 생성
3. 인증서버 빌드(`installDist`) 후 실행
4. 루트 `.venv` 가 없거나 패키지가 없으면 `requirements.txt` 로 자동 설치 후 RAG 실행
5. 서버가 준비될 때까지 기다렸다가 다음 단계로 진행
6. **`Ctrl + C` 한 번으로 띄운 서버 모두 종료** (DB 컨테이너는 계속 실행 — `docker stop ai-mini-db`)

로그는 `logs/auth.log`, `logs/rag.log`, `logs/voice.log` 에 쌓입니다 (`tail -f logs/*.log`).

> 💡 로그인에 성공하면 원본 코드대로 `localhost:8008` 로 이동합니다. 음성 서비스를 안 띄웠으면 "연결 거부"가 정상이며,
> 로그인 상태는 http://localhost:8080/api/auth/check 로 확인할 수 있습니다.

### 따로 실행하기

#### 0. MariaDB 준비

인증서버는 `jdbc:mariadb://localhost:53301/sql_db` (user `root`)에 접속합니다. `users` 테이블을 미리 만들어 둡니다.
(`./dev.sh` 를 한 번 실행했다면 이미 만들어져 있습니다.)

```sql
CREATE TABLE `users` (
  `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(100) NOT NULL,
  `password` varchar(255) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### 1. 인증서버 (:8080)

```bash
cd auth-server
set -a && source .env && set +a
./gradlew :app:run --no-configuration-cache
```

→ http://localhost:8080/signup · http://localhost:8080/login

#### 2. RAG 서비스 (:8001)

```bash
source .venv/bin/activate        # 루트에서
cd rag-service
python -m uvicorn rag_external-web_pdf_closed_llm:app --port 8001 --reload
```

→ http://127.0.0.1:8001/docs (Swagger) · 엔드포인트: `/upload-paper`, `/upload-topic`, `/rag-query`
(`localhost` 로 연결이 거부되면 `127.0.0.1` 로 접속 — RAG는 IPv4 에만 열립니다)

#### 3. 음성 서비스 (:8008)

```bash
brew install ffmpeg
source .venv/bin/activate        # 루트에서
cd voice-service
python -m uvicorn app.main:app --port 8008
```

→ 인증서버에서 로그인한 뒤 http://localhost:8008/index.html, http://localhost:8008/stt-tts.html
(Docker로 실행하려면 `docker compose up -d --build`)

#### 4. 콘솔 페이지

콘솔은 http 로 열어야 합니다 (RAG 서버 CORS 허용 포트가 5174).

```bash
cd consoles && python3.11 -m http.server 5174
```

→ http://localhost:5174/intro_main.html 에서 BASE_URL 을 `http://127.0.0.1:8001` 로 설정

---

## ✅ 조별로 해야 할 일 (교재 기준)

실습 빈칸(TODO)은 채워져 동작하지만, `rag-service` 의 **API 형태는 아직 템플릿 그대로**라 교재 요구사항과 다음이 다릅니다.

| 항목 | 현재 템플릿 | 교재 목표 |
|---|---|---|
| 인증 | 없음 | `Depends(verify_jwt)` — 토큰 없으면 **401** |
| 요청 | `{prompt, source, top_k}` | `{question, source}` |
| 응답 | `{prompt, response}` | `{answer, sources, needs_review, handoff, latency_ms}` |
| 근거 없음 | LLM 호출 | 검색 0건이면 LLM 호출 안 함 → `"찾을 수 없습니다"`, `handoff: true` |
| 임베딩 | `OpenAIEmbeddings` | 교재 예시는 `BAAI/bge-m3` (선택) |

그 외:

- [ ] `frontend/` — Vue.js 화면 (로딩·오류·출처·handoff·401 처리)
- [ ] 루트 `docker-compose.yml` — `db`, `auth`, `rag`, `web` 일괄 기동
- [ ] 평가셋 20쌍 이상 (예외 질문 3개 이상 포함) + 개선 전후 비교
- [ ] 지연·토큰 로그 미들웨어
- [ ] (확장 +5) 음성 연동 / Internal RAG / Fine-tuning·Agent 중 1개

### 체크포인트

| # | 시점 | 내용 |
|---|---|---|
| ① | Day1 | 1장 기획서 (사용자 가치·데이터·아키텍처/API·역할 분담) |
| ② | Day1 | 로그인 → JWT → `/rag-query` 호출 1회 성공 |
| ③ | Day2 | Swagger로 API 시연 (401/200, 근거 답변, 예외 질문) |
| ④ | Day2 | End-to-End 데모 |
| ⑤ | Day3 | 최종 제출물 (데모·아키텍처·발표·README·평가셋) |
