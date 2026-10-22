# AGENTS.md — AI 코딩 도구용 프로젝트 규칙

이 저장소에서 코드를 쓰는 AI(ChatGPT, Cursor, Copilot, Claude 등)는 작업 전에 이 규칙을 따른다.

## 프로젝트
**ChemBridge** — 반도체 공정 외국인 근로자를 위한 화학안전·중대재해 법령 다국어(ko·zh·vi) RAG 안내 서비스.

```
Vue(:5174) → Java 인증(:8080, JWT 쿠키) → RAG FastAPI(:8001) → FAISS + OpenAI
```

## 반드시 지킬 규칙
1. **`rag-service/rag/schema.py` 의 이름을 바꾸지 않는다.** 요청·응답 필드(`question`, `topic`, `product_id`, `language`, `answer`, `sources`, `needs_review`, `handoff`, `latency_ms`), 메타데이터 키, topic·language 값은 모두 여기서 import 해서 쓴다. 문자열로 직접 쓰지 않는다.
2. **담당 파일만 고친다.** 아래 표에 없는 파일을 고쳐야 하면 먼저 사람에게 묻는다.
3. **함수 이름·입력·출력 형식은 그대로 두고 `TODO` 안만 채운다.**
4. **API 는 `rag.chain.answer()` 하나만 부른다.** 검색·LLM 을 API 에서 직접 부르지 않는다 (비상 안내·handoff 가 빠진다).
5. **비밀값을 코드에 쓰지 않는다.** API 키·JWT 비밀키·DB 비밀번호는 `.env` 에만. `.env`, `faiss_db/`, `.venv/` 는 커밋하지 않는다.
6. **새 패키지를 추가하면** 해당 `requirements*.txt` 에 넣고 사람에게 알린다.
7. **법률 판단을 하지 않는다.** "처벌받는다/책임 있다"고 단정하는 답을 만들지 않는다 → `handoff=True`.
8. **작업이 끝나면 약속 확인 테스트를 돌린다** (아래). 실패하면 고친 뒤 끝낸다.

## 담당 파일 (rag-service/)
| 파일 | 담당 |
|---|---|
| `ingest_law.py`, `ingest/`, `data/` | 윤서진 (데이터) |
| `rag/stores.py`, `rag/query.py`, `rag/retriever.py`, `eval/` | 김규빈 (검색·평가) |
| `rag/prompt.py`, `rag/llm.py`, `rag/generator.py` | 박진근 (생성) |
| `app/main.py`, `app/auth.py` | 정지우 (API) |
| `frontend/` (예정), `docker-compose.yml` (예정) | 강지훈 (프론트·배포) |
| `rag/schema.py`, `rag/chain.py` | 공동 — 바꾸기 전에 팀에 공유 |

## 실행·테스트
```bash
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt   # 처음 한 번
./dev.sh                                         # DB · 인증 · RAG 실행 (Ctrl+C 로 종료)
cd rag-service && ../.venv/bin/python -m pytest -q tests   # 약속 확인 테스트
```
- 프론트는 RAG 를 `http://localhost:8001` 로 부른다 (`127.0.0.1` 이면 쿠키가 안 가서 401).

## Git
- 각자 자기 브랜치(`feat/이름-작업`)에서 작업하고 PR 로 `main` 에 합친다. `main` 에 바로 push 하지 않는다.
- `git push --force` 금지.
