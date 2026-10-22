# ChemBridge

반도체 공정(소부장 포함) **외국인 근로자**를 위한 **화학물질 안전 · 중대재해 법령 다국어(ko · zh · vi) RAG 안내 서비스**
— SKALA AI 서비스 개발 Mini-project

```
Vue(:5174) ─로그인─▶ Java 인증서버(:8080) ─▶ MariaDB(:53301)
    │                 (ACCESS_TOKEN 쿠키 발급)
    └─/rag-query─▶ RAG FastAPI(:8001) ─▶ FAISS(law · msds) + OpenAI
```

## 현재 상태 (2026-10-22, Day 1)

| 구분 | 상태 |
|---|---|
| 인증서버 (회원가입 · 로그인 · JWT) | ✅ 동작 |
| RAG API `/health` · `/rag-query` | ✅ 끝까지 동작 — 검색·생성은 **임시 구현**, 각 담당이 다듬는 중 |
| 법령 인덱스 (중대재해처벌법, 조문 단위) | ✅ `faiss_db/law` |
| MSDS 인덱스 | ⬜ `ingest/ingest_msds.py` 뼈대만 |
| 다국어 질문 → 한국어 변환 | ⬜ TODO (답변은 요청 언어로 나옴) |
| 평가셋 · 검색 적중률 | ⬜ 형식 예시 1개 |
| Vue 프론트 · Docker Compose | ⬜ 예정 |
| 약속 확인 테스트 · CI | ✅ 10개 통과, PR 마다 자동 실행 |

## 폴더 구조

```
ai-mini-project/
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

- `topic`: `chemical_safety` · `serious_accident_law` / `language`: `ko` · `zh` · `vi`
- 401 토큰 없음·만료·위조 / 422 형식 오류 / 503 LLM·인덱스 문제
- `GET /health` → 200 준비 · 503 미준비, topic 별 인덱스 상태 포함
- Swagger: http://localhost:8001/docs

## 시작하기

**준비물:** Docker Desktop · Java 17+ · Python 3.11 · (음성은 ffmpeg)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -U pip setuptools wheel && pip install -r requirements.txt   # 처음 한 번 (torch 포함, 수 분)
```

`.env` 는 서비스마다 위치가 다릅니다 (`.env.example` 참고, **Git 에 올리지 않음** — 값은 팀 DM 으로 공유).

| 위치 | 변수 |
|---|---|
| `auth-server/.env` | `DB_PASSWORD`, `JWT_SECRET` |
| `rag-service/.env` | `OPENAI_API_KEY` (+ 선택 `LLM_MODEL`, `EMBEDDING_MODEL`) |
| `voice-service/app/.env` | `OPENAI_API_KEY` |

```bash
./dev.sh            # DB · 인증서버(:8080) · RAG(:8001) — Ctrl+C 로 모두 종료, 로그는 logs/
./dev.sh --voice    # 음성 서비스(:8008)까지
```

- 회원가입 http://localhost:8080/signup → 로그인 → RAG 질의 http://localhost:8001/docs
- DB 컨테이너 `ai-mini-db` 와 `users` 테이블은 `dev.sh` 가 자동으로 만듭니다.
- 로그인하면 원본 코드대로 `localhost:8008` 로 이동합니다. 음성을 안 띄웠으면 "연결 거부"가 정상입니다.
- ⚠ 프론트·테스트에서 RAG 는 **`localhost:8001`** 로 부르세요. `127.0.0.1` 이면 쿠키가 안 가서 401 입니다.
- 기존 템플릿 서버로 띄우기: `RAG_APP=rag_external-web_pdf_closed_llm:app ./dev.sh`

**법령 인덱스 만들기** (rag-service/ 에서):

```bash
python ingest_law.py --input laws/sapa.pdf --law-name "중대재해 처벌 등에 관한 법률" --abbr sapa \
  --effective-date 2022-01-27 --source-url "https://www.law.go.kr/" --out faiss_db/law
```

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

## 팀

| 파트 | 담당 |
|---|---|
| 데이터 파이프라인 | 윤서진 |
| Retriever(검색) · 평가 | 김규빈 |
| LLM(생성) | 박진근 |
| 인증 연동 · API | 정지우 |
| 프론트엔드 · 배포 | 강지훈 |

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
