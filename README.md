# ChemBridge

반도체 공정(소부장 포함) **외국인 근로자**를 위한 **화학물질 안전 · 중대재해 법령 다국어(ko · zh · vi) RAG 안내 서비스**
— SKALA AI 서비스 개발 Mini-project

```
Vue(:5174) ─로그인─▶ Java 인증서버(:8080) ─▶ MariaDB(:53301)
    │                 (ACCESS_TOKEN 쿠키 발급)
    └─/rag-query─▶ RAG FastAPI(:8001) ─▶ FAISS(law · msds) + OpenAI
```

## 전체 Docker 실행 (음성 포함)

환경 파일 3개를 준비하고 Docker Desktop을 켠 뒤 저장소 루트에서 실행합니다.

```bash
docker compose up -d --build
```

접속: **http://localhost:5190**. DB·인증·RAG·음성·프론트를 함께 실행하며 기존 개발 서버/DB와 분리됩니다. 처음에는 빌드·모델·인덱스 준비를 기다려야 합니다. 종료는 `docker compose stop`, 다시 실행은 `docker compose up -d`입니다.

[환경 설정·데이터 유지·테스트 상세](frontend/deploy/README.md)


---

## 👋 팀원은 여기부터 — 순서대로 따라 하면 됩니다

### 1단계. 내 작업 카드 열기 (1분)

| 이름 | 파트 | 작업 카드 |
|---|---|---|
| 윤서진 | 데이터 파이프라인 | [docs/tasks/윤서진_데이터.md](docs/tasks/윤서진_데이터.md) |
| 박진근 | LLM(생성) | [docs/tasks/박진근_생성.md](docs/tasks/박진근_생성.md) |
| 정지우 | 인증 연동 · API | [docs/tasks/정지우_API.md](docs/tasks/정지우_API.md) |
| 강지훈 | 프론트엔드 · 배포 | [docs/tasks/강지훈_프론트배포.md](docs/tasks/강지훈_프론트배포.md) |
| 김규빈 | Retriever(검색) · 평가 | (본인) |

카드에 **할 일 · 고칠 파일 · 완료 기준 · AI 에게 붙여 넣을 프롬프트**가 있습니다.

### 2단계. 내 컴퓨터에 준비하기 (처음 한 번, 10~15분)

1. 설치되어 있어야 하는 것: **Git, Docker Desktop(실행 중), Java 17 이상, Python 3.11**
2. 저장소 받기
   ```bash
   cd ~/workspace
   git clone https://github.com/Illclass/ai-mini-project.git
   cd ai-mini-project
   ```
3. 파이썬 가상환경 + 패키지 설치 (torch 때문에 몇 분 걸림)
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -U pip setuptools wheel
   pip install -r requirements.txt
   ```
4. **`.env` 파일 3개 만들기** — 값은 **김규빈에게 DM 으로 받으세요** (Git·단톡방에 올리지 않기)
   - `auth-server/.env` → `DB_PASSWORD=...`, `JWT_SECRET=...`
   - `rag-service/.env` → `OPENAI_API_KEY=...`
   - `voice-service/app/.env` → `OPENAI_API_KEY=...` (음성 담당만)
5. 법령 인덱스 만들기 (`faiss_db/` 는 Git 에 없어서 각자 한 번 만들어야 함)
   ```bash
   cd rag-service
   ../.venv/bin/python ingest_law.py --input laws/sapa.pdf --law-name "중대재해 처벌 등에 관한 법률" \
     --abbr sapa --effective-date 2022-01-27 --source-url "https://www.law.go.kr/" --out faiss_db/law
   cd ..
   ```

### 3단계. 전체 실행해 보기 (2분)

```bash
./dev.sh
```

- `✔ 모두 실행 중` 이 나오면 성공. 끌 때는 `Ctrl + C`
- 브라우저에서 확인:
  1. http://localhost:8080/signup → 가입 → 로그인 (로그인 후 "연결 거부" 화면이 떠도 **정상**)
  2. http://localhost:8001/docs → `POST /rag-query` → **Try it out** → 아래를 붙여 넣고 **Execute**
     ```json
     {"question": "중대재해법의 기준은?", "topic": "serious_accident_law", "language": "ko"}
     ```
  3. 아래 Response 에 `answer` 와 `sources` 가 나오면 끝

### 4단계. 내 브랜치에서 작업하기

```bash
git switch main
git pull origin main
git switch -c feat/내이름-작업내용        # 예: feat/jinkeun-prompt
```

**AI(ChatGPT 등)로 작업할 때**
1. 작업 카드 맨 아래 **"AI 에게 붙여 넣을 프롬프트"** 를 복사
2. `(여기에 ... 붙여 넣기)` 자리에 해당 파일 내용을 붙여 넣기
3. AI 가 준 코드로 **내 담당 파일만** 바꾸기
4. Cursor · Copilot 을 쓰면 [`AGENTS.md`](AGENTS.md) 규칙을 AI 가 자동으로 읽습니다

### 5단계. 확인하고 올리기

```bash
cd rag-service && ../.venv/bin/python -m pytest -q tests && cd ..   # "10 passed" 가 나와야 함
git add 내가-고친-파일
git commit -m "무엇을 했는지 한 줄"
git push -u origin feat/내이름-작업내용
```

- GitHub → **Pull requests → New pull request** → `main` ← 내 브랜치 → **Create**
- PR 화면에 ✅ 가 뜨면 병합, ❌ 면 고친 뒤 다시 push (❌ 인 PR 은 병합하지 않기)
- `git add .` 대신 **고친 파일만** add 하세요 (`.env` 실수 방지)

### 막히면

| 증상 | 해결 |
|---|---|
| `Address already in use` | 이미 서버가 켜져 있음 → 켜 둔 터미널에서 `Ctrl + C`, 또는 `lsof -iTCP:8080 -sTCP:LISTEN` 으로 PID 확인 후 `kill <PID>` |
| `docker ... not running` | Docker Desktop 앱을 먼저 실행 |
| `/rag-query` 가 401 | 로그인을 안 했거나, `127.0.0.1` 로 접속함 → 주소를 **`localhost`** 로 |
| `/health` 가 503 | 법령 인덱스가 없음 → 2단계 5번 다시 |
| `OPENAI_API_KEY` 오류 | `rag-service/.env` 가 없거나 비어 있음 |
| `pip install` 실패 | Python 버전 확인 `python3.11 --version` (3.14 등 다른 버전 금지) |
| 테스트 ❌ | 에러 메시지를 통째로 AI 에 붙여 넣고 "이 테스트가 통과하게 고쳐 줘" |
| 그래도 안 되면 | 에러 화면 캡처해서 김규빈에게 |

---

## 현재 상태 (2026-10-22, Day 1)

| 구분 | 상태 |
|---|---|
| 인증서버 (회원가입 · 로그인 · JWT) | ✅ 동작 |
| RAG API `/health` · `/rag-query` | ✅ 끝까지 동작 — 검색·생성은 **임시 구현**, 각 담당이 다듬는 중 |
| 법령 인덱스 (중대재해처벌법, 조문 단위) | ✅ `faiss_db/law` |
| MSDS 인덱스 | ⬜ `ingest/ingest_msds.py` 뼈대만 |
| 다국어 질문 → 한국어 변환 | ⬜ TODO (답변은 요청 언어로 나옴) |
| 평가셋 · 검색 적중률 | ⬜ 형식 예시 1개 |
| Vue 프론트 | ✅ 임시 데이터 기반 디자인 미리보기 — 실제 인증·RAG·음성 API 연동 전 |
| Docker Compose | ✅ 전체 서비스·음성 포함 로컬 구성 추가 (아래 Day 1 표의 다른 항목은 당시 기록) |
| 약속 확인 테스트 · CI | ✅ 10개 통과, PR 마다 자동 실행 |

## 프론트 개발 서버

```bash
cd frontend
npm ci
npm run dev
```

http://localhost:5174 에서 회원가입·로그인 → 작업 상황 선택 → 질문·답변을 확인합니다. 실제 인증·RAG 서버가 필요하며 음성은 `./dev.sh --voice`로 함께 실행합니다. ko·zh·vi·en·km 화면을 지원하고 km는 글 질문만 제공합니다. Docker 전체 실행은 위 안내를 사용하세요.

빌드는 `npm run build`로 확인합니다. 파일 구조와 실제 API 연결 지점은 [frontend/README.md](frontend/README.md)를 참고하세요. `dev.sh`는 프론트 서버를 실행하지 않으므로 별도 터미널에서 실행합니다.

## 폴더 구조

```
ai-mini-project/
├── frontend/             Vue 3 + Vite 디자인 미리보기 (임시 데이터)
├── rag-service/          RAG API (FastAPI) — 아래 표 참고
├── auth-server/          Java 인증서버 (Gradle · MariaDB · BCrypt · JWT)
├── voice-service/        음성 서비스 (Whisper STT → GPT → TTS) — 확장 트랙
├── consoles/             RAG 테스트용 HTML 콘솔 (기존 템플릿용)
├── docs/tasks/           팀원별 작업 카드 (할 일 · 완료 기준 · AI 프롬프트)
├── .github/workflows/    CI (약속 확인 테스트)
├── AGENTS.md · CLAUDE.md AI 코딩 도구용 규칙
├── dev.sh                DB · 인증 · RAG 한 번에 실행
├── requirements.txt      Python 패키지 전체 (루트 .venv 하나)
└── .env.example          환경변수 목록
```

### rag-service

| 파일 | 담당 | 역할 |
|---|---|---|
| `rag/schema.py` | 전원 | **공통 이름** — 요청·응답 필드, 메타데이터 키, topic · language 값 |
| `app/main.py` · `app/auth.py` | 정지우 | `/health`, `/rag-query`, JWT 쿠키 검증, 오류 처리 |
| `rag/chain.py` | 김규빈 · 박진근 | 비상 질문 확인 → 검색 → 생성 → `latency_ms` |
| `rag/stores.py` · `rag/query.py` · `rag/retriever.py` | 김규빈 | 인덱스 로드, 질문 다듬기(동의어 · 번역), 검색 |
| `rag/prompt.py` · `rag/llm.py` · `rag/generator.py` | 박진근 | 프롬프트, LLM 호출, `sources` · `needs_review` · `handoff` |
| `ingest_law.py` · `ingest/` · `data/` | 윤서진 | 법령 · MSDS 적재 |
| `eval/` | 김규빈 · 박진근 | 평가셋, 검색 적중률 · 생성 판정 |
| `tests/` | 전원 | 약속 확인 테스트 |
| `rag_external-web_pdf_closed_llm.py` | — | 기존 템플릿 (참고용, `/upload-paper` 등) |

흐름: `RagRequest` → `chain.answer()` → `query.normalize_question()` → `retriever.retrieve()` → `generator.generate()` → `RagResponse`

## API 계약

```json
POST /rag-query   (쿠키 ACCESS_TOKEN 필요)
요청 {"question": "중대재해법의 기준은?", "topic": "serious_accident_law", "product_id": null, "language": "ko"}
응답 {"answer": "...", "sources": [{"doc_id": "L2", "section": "제2조 제2호", "title": "...", "url": "..."}],
      "needs_review": false, "handoff": false, "latency_ms": 1250}
```

- `topic`: `chemical_safety` · `serious_accident_law` / `language`: `ko` · `zh` · `vi` · `en` · `km`
- 401 토큰 없음·만료·위조 / 422 형식 오류 / 503 LLM·인덱스 문제
- `GET /health` → 200 준비 · 503 미준비, topic 별 인덱스 상태 포함
- Swagger: http://localhost:8001/docs

## 실행 참고

- 설치·실행 순서는 위 **"팀원은 여기부터"** 2~3단계를 따릅니다.
- `./dev.sh --voice` → 음성 서비스(:8008)까지 실행 (ffmpeg, `voice-service/app/.env` 필요). 프론트 음성 모드는 이 옵션으로 띄워야 동작합니다
  - 흐름: 마이크 녹음 → `POST /voice/stt` → 인식된 질문 확인·전송 → `/rag-query` → `POST /voice/tts` 로 답변 자동 재생
  - 크메르어(km)는 음성 인식·합성 품질이 낮아 음성 모드에서 제외 (글 질문만)
  - **음성 대화 모드** (입력창 옆 [음성 대화], 손 없이): 한 번 켜면 말소리를 알아서 듣고 → 인식된 질문을 3초 뒤 자동 전송 → 답변을 읽고 → 다시 듣습니다. '취소'·'대화 종료'라고 말하거나 화면을 눌러 멈춥니다 (`frontend/src/api/listener.js`)
- 기존 템플릿 서버로 띄우기: `RAG_APP=rag_external-web_pdf_closed_llm:app ./dev.sh`
- DB 컨테이너 `ai-mini-db` 와 `users` 테이블은 `dev.sh` 가 자동으로 만듭니다. 로그는 `logs/` 에 쌓입니다.
- 선택 환경변수 (`rag-service/.env`): `LLM_MODEL`(기본 gpt-6-luna), `EMBEDDING_MODEL` — 적재와 검색에 **같은 값**을 써야 합니다.

## 테스트 · CI

```bash
cd rag-service && ../.venv/bin/python -m pytest -q tests
```

- 검색·LLM 을 가짜로 바꿔 돌리므로 비용·키가 필요 없습니다 (1초 내외).
- 확인하는 것: 401 · 422, 응답 필드 · 출처 형식, 근거 없으면 LLM 미호출 + handoff, 판단 요구 · 비상 질문 handoff, `/health` 형식
- PR 을 올리거나 `main` 에 병합하면 GitHub Actions(`contract-test`)가 자동 실행합니다. **❌ 가 뜬 PR 은 병합하지 않습니다.**
- 답의 **정확도**는 이 테스트가 아니라 `eval/` 평가셋으로 측정합니다.

## 작업 규칙

자세한 규칙은 [`AGENTS.md`](AGENTS.md), 각자 할 일은 [`docs/tasks/`](docs/tasks) 를 보세요.

1. `rag/schema.py` 의 이름은 바꾸지 않고 import 해서 씁니다. 바꿔야 하면 팀에 먼저 공유합니다.
2. 담당 파일만 고치고, 함수 이름·입출력은 그대로 둔 채 `TODO` 를 채웁니다.
3. 비밀값은 `.env` 에만 둡니다.
4. 법률 판단(처벌·책임 단정)을 하지 않습니다 → `handoff: true`.
5. 자기 브랜치(`feat/이름-작업`)에서 작업하고 PR 로 `main` 에 합칩니다.

## 데이터 출처 (기획서 기준)

| ID | 출처 | 상태 |
|---|---|---|
| L1 | 국가법령정보센터 — 산업안전보건법 114조, 안전보건규칙 422조 | 적재 전 |
| L2 | 국가법령정보센터 — 중대재해 처벌 등에 관한 법률 (법률 제17907호, 시행 2022.1.27.) | ✅ 적재 (`faiss_db/law`) |
| D1 | Sigma-Aldrich Korea — Sulfuric acid 339741 MSDS | 적재 전 |
| K1 | 안전보건공단 화학물질정보 | 참고용 |

법령 원문은 안내용이며 공식 해석이 아닙니다. MSDS 는 참고용이며 현장 공급자 MSDS 를 따릅니다.

## 참고: 원본 골격(`ai-practice.zip`)에서 바뀐 점

- 폴더 이름: `workplace` → `auth-server`, `rag-code-template_ext` → `rag-service`, `voice-ai_code` → `voice-service`, HTML → `consoles/`
- 실습 빈칸(TODO) 채움: 인증서버 ①~⑤, RAG Q01~Q05, 음성 Q01~Q05
- `voice-service/requirements.txt`: UTF-16 → UTF-8, `requests` 를 `>=2.32.5,<3.0` 으로 (langchain-community 호환)
- 새 구조: `rag-service/app`, `rag/`, `ingest/`, `eval/`, `tests/` (기존 템플릿 파일은 그대로 둠)
