# ChemBridge

반도체 공정(소부장 포함) **외국인 작업자**를 위한 **화학물질 안전 · 산업안전 법령 다국어 RAG 안내 서비스**
— SKALA AI 서비스 개발 Mini-project

작업자가 자기 언어(한국어 · 중국어 · 베트남어 · 영어 · 크메르어)로 물으면, 공급자 MSDS · KOSHA 지침 · 법령 원문에서 근거를 찾아
출처와 함께 답합니다. **근거가 없거나 검증에 실패하면 답하지 않고 담당자 확인으로 넘기며**, 몸에 묻음 · 흡입 같은 비상 상황은
검색 · LLM 을 거치지 않고 비상 안내를 먼저 보여 줍니다. 현장 안전교육 · 작업 승인 · 법률 판단을 대신하지 않습니다.

```
Vue 화면(:5174)
 ├─ 로그인 ──▶ Java 인증서버(:8080) ─▶ MariaDB
 │             JWT 쿠키 발급, 만료·위조 401
 ├─ /rag-query ─▶ RAG FastAPI(:8001)
 │     ① 비상·범위 밖 질문은 바로 안내
 │     ② 제품·장비 범위 지정 + FAISS 검색
 │        (bge-m3, 외국어 질문은 한국어로 번역)
 │     ③ LLM 답변 (gpt-6-luna, 문장마다 원문 인용)
 │     ④ 인용·수치·번역·검증 LLM 통과 시에만 응답
 └─ /voice ─▶ 음성 서버(:8008)
       Whisper 음성 인식 · TTS 답변 읽기

적재: MSDS 13종 · 법령 5종 · KOSHA 지침 8종 · 현장지침
      → 항목/조문 단위 청크 → bge-m3 → FAISS (law · msds)
```

## 주요 기능

| 기능 | 내용 |
|---|---|
| 5개 언어 | ko · zh · vi · en · km. 화면 언어와 다른 말로 물으면 질문한 말로 답한다 |
| 작업 단계별 추천 질문 | 작업 전 · 취급 · 보관 · 작업 중 · 작업 후 · 비상 6단계, 단계별 안내 PDF |
| 제품 · 장비 범위 | 가상 장비 10대 · MSDS 13종 중 고르면 그 범위에서만 답한다. 물질명만 말해도 제품 자동 지정 |
| 근거 답변 | 소제목(알아둘 내용 · 권고사항 · 법령 문구 · ⚠ 주의사항) + 목록, 문장마다 출처 번호, 같은 문서 출처는 한 줄로 |
| 번역 경고 원문 대조 | 외국어 답변의 중요 경고 아래 한국어 원문을 작게 함께 표시 |
| 보류 이유 안내 | "근거와 맞지 않아 보류", "제품을 확인하지 못함" 등 이유와 다음 행동 |
| 출처 원문 보기 | 인용한 MSDS 항목 · 조문의 PDF 쪽으로 바로 이동 |
| 음성 (확장) | 말로 묻기 · 답변 듣기 · 손 없이 쓰는 음성 대화 모드 (크메르어 제외) |
| 외국어 자료집 | 비상 표현 사전 · 안전 용어집 69개 (`rag-service/data/lexicon/`) |

---

## 실행 방법

### 처음 한 번 준비 (10~15분)

필요한 것: **Git, Docker Desktop(실행 중), Java 17 이상, Python 3.11, Node 22, ffmpeg(음성)**

```bash
git clone https://github.com/Illclass/ai-mini-project.git && cd ai-mini-project
python3.11 -m venv .venv && source .venv/bin/activate
pip install -U pip setuptools wheel && pip install -r requirements.txt     # torch 때문에 몇 분 걸림
(cd frontend && npm ci)
```

**`.env` 파일 3개** — 값은 팀 내부에서만 전달합니다 (Git · 단톡방에 올리지 않기)

| 파일 | 내용 |
|---|---|
| `auth-server/.env` | `DB_PASSWORD`, `JWT_SECRET` |
| `rag-service/.env` | `OPENAI_API_KEY`, 선택 `LLM_MODEL`(기본 gpt-6-luna) · `EMBEDDING_MODEL`(기본 bge-m3) |
| `voice-service/app/.env` | `OPENAI_API_KEY`, 선택 `WHISPER_MODEL` |

**인덱스 만들기** — `faiss_db/` 는 Git 에 없어서 각자 한 번 만듭니다 (로컬 임베딩, 약 6분, 비용 없음)

```bash
cd rag-service && ./ingest_all.sh && cd ..
```

적재 코드나 `data/` 가 바뀐 dev 를 받았을 때도 다시 실행합니다.

### A. Docker 로 한 번에 실행 (시연용)

```bash
docker compose up -d --build
```

접속 **http://localhost:5190** → 회원가입 후 사용. DB · 인증 · RAG · 음성 · 화면을 함께 띄우며 개발용 서버 · DB 와 분리됩니다.
처음에는 빌드 · 모델 다운로드 · 인덱스 생성에 시간이 걸립니다. 종료 `docker compose stop`, 재실행 `docker compose up -d`.
상세(메모리 8GB 기준, 데이터 유지, 점검 명령): [frontend/deploy/README.md](frontend/deploy/README.md)

### B. 개발용 실행

터미널 두 개를 씁니다.

```bash
./dev.sh --voice                 # 터미널 1: DB · 인증(:8080) · RAG(:8001) · 음성(:8008). 음성이 필요 없으면 --voice 생략
cd frontend && npm run dev       # 터미널 2: 화면(:5174)
```

- 접속 **http://localhost:5174** → 회원가입 · 로그인 → 작업 상황 선택 → 질문
- API 만 확인: http://localhost:8001/docs (Swagger) → `POST /rag-query` → Try it out
- 끌 때는 각 터미널에서 `Ctrl + C`. DB 컨테이너 `ai-mini-db` 와 `users` 테이블은 `dev.sh` 가 자동으로 만들고, 로그는 `logs/` 에 쌓입니다.
- RAG 코드를 고치면 `dev.sh` 를 다시 켜야 반영됩니다 (화면은 자동 반영).

### 막히면

| 증상 | 해결 |
|---|---|
| `Address already in use` | 이미 서버가 켜져 있음 → 켜 둔 터미널에서 `Ctrl + C`, 또는 `lsof -iTCP:8080 -sTCP:LISTEN` 으로 PID 확인 후 `kill <PID>` |
| `docker ... not running` | Docker Desktop 앱을 먼저 실행 |
| `/rag-query` 가 401 | 로그인을 안 했거나 `127.0.0.1` 로 접속함 → 주소를 **`localhost`** 로 |
| `/health` 가 503 | 인덱스가 없음 → `rag-service/ingest_all.sh` |
| 화면이 `Cannot find package` 오류 | 새 패키지가 추가된 dev 를 받음 → `cd frontend && npm install` |
| `OPENAI_API_KEY` 오류 | `rag-service/.env` 가 없거나 비어 있음 |
| `pip install` 실패 | `python3.11 --version` 확인 (3.14 등 다른 버전 금지) |

---

## 평가 결과

평가셋 `rag-service/eval/questions.json` 70문항 (물질별 13 · 법령 13 · 다국어 24 · 공통 6 · 위험사고 5 · 제품 지정 5 · 장비 지정 4).
교재 규칙대로 **한 번에 하나씩 바꾸고 같은 평가셋으로 다시 쟀습니다.** 상세 기록: [rag-service/eval/reports/](rag-service/eval/reports/README.md)

### 검색 (hit@5: 기대 근거가 상위 5개 안에 든 비율)

| 단계 | 바꾼 것 | hit@5 |
|---|---|---|
| 기준점 | ada-002 임베딩, 번역 없음 | 56% |
| 1 | 외국어 질문을 한국어로 번역해 검색 | 80% |
| 2 | 임베딩 4종 비교 → **bge-m3** 선택 (로컬, 비용 없음) | 98% |
| 3 | 물질명으로 제품 자동 지정 · 제품 범위 검색 (평가셋 60 → 70문항) | 96% |
| 4 | 변형 질문 순위 병합, 한국어 외 모두 번역, 동의어(이송 · 희석 · 보호구) | 97% |
| 현재 | 장비 범위 검색 · MSDS 항목 단위 적재 | **100%** (5개 언어 모두), hit@1 84%, MRR 0.90 |

### 답변 (답이 나와야 하는 한국어 32문항 중 실제로 답한 수)

| 단계 | 바꾼 것 | 답변 |
|---|---|---|
| 기준점 | — | 10 |
| 1 | 모델 교체(gpt-6-luna), 인용 비교에서 PDF 줄바꿈 무시 | 18~23 |
| 2 | 원문 강도 유지, 서버가 MSDS 에서 제품 정보 직접 확인 | 20~25 |
| 3 | MSDS 표 항목(9 · 14 · 15 · 16항)을 '잘린 경고' 판정에서 제외 | 25 |
| 4 | 법령 '각 호' 의무 · 지침 요구 문체 · KOSHA 꼬리말 오탐 수정 | 29~30 |
| 5 | 검증 실패 시 1회 재생성, 질문 관련 경고만 붙이기 | **30** |

- 보류해야 하는 5문항(비상 · 법률 판단 요청)은 처음부터 끝까지 모두 보류. 37문항 전체로는 최근 **35/37**, 평균 응답 약 10초
- 같은 질문도 검증 LLM 판정이 조금씩 달라 33~35/37 사이에서 오갑니다.
- 점수는 검증을 느슨하게 해서가 아니라 **맞는 답을 틀렸다고 막던 오탐을 하나씩 찾아 고쳐서** 올렸습니다.

### 외국어 (중국어 · 베트남어 · 영어 · 크메르어 48문항)

| 단계 | 바꾼 것 | 기대대로 |
|---|---|---|
| 기준점 | — | 26/43 |
| 1 | 금액 · 서수 · 조항 번호 비교, 질문한 언어로 답하기 | 30/46 |
| 2 | 법령 PDF 쪽 머리글 제거, 독성표(11 · 12항) 경고 제외, 시간 단위 현지화, 코드 경고(P403+P233 …) 묶기 | 37/48 |
| 3 | 외국어 자료집 (비상 표현 사전 · 안전 용어집) | **41/48 (85%)** |

추천 질문 56개(4개 언어 × 14)는 29 → 47개가 답변됩니다.

### 환각 점검

일반 8문항 + 함정 9문항의 답변 문장을 인용 원문과 하나씩 대조했습니다. **지어낸 내용은 찾지 못했고**, 자료에 없는 물질(톨루엔) · 없는 항목(MSDS 17항) ·
없는 정보(유통기한)는 모두 보류됐습니다. 수치(메탄올 인화점 9.7 °C, 불산 TWA 0.5 ppm 등)는 원문과 일치했습니다. 표본이 작아 환각이 없다고 보장하지는 않습니다.

### 운영 지표

| 항목 | 값 |
|---|---|
| 응답 시간 | 한국어 평균 약 10초 · 외국어 약 20초 · 비상 안내 0.1초 이내 · 검색만 약 0.5초 |
| 질문당 LLM 비용 | 한국어 약 0.0026달러(약 4원), 외국어 약 0.005달러 — 입력 약 1.9만 · 출력 약 1.4천 토큰, 호출 2.6회 |
| 임베딩 비용 | 0원 (로컬 bge-m3) |
| 로그 | `logs/rag-latency-*.json` 경로별 요청 수 · 오류율 · 지연. 질문 원문은 저장하지 않음 |

---

## 데이터 출처

`rag-service/ingest_all.sh` 가 아래 자료를 적재합니다. 원문 PDF 는 `rag-service/data/` 에 있습니다.

| ID | 자료 | 출처 | 기준일 |
|---|---|---|---|
| L1 | 산업안전보건법 (제52 · 110~116조) | [국가법령정보센터](https://www.law.go.kr) | 2026-08-01 시행 |
| L4 | 산업안전보건기준에 관한 규칙 (제31~34 · 299 · 420~511조) | 국가법령정보센터 | 2026-03-02 시행 |
| L5 | 산업안전보건법 시행규칙 (제156~171조) | 국가법령정보센터 | 2026-08-01 시행 |
| L2 | 중대재해 처벌 등에 관한 법률 | 국가법령정보센터 | 2022-01-27 시행본 (학습용, 현행 판단 불가) |
| L3 | 화학물질관리법 | 국가법령정보센터 | 2026-10-08 시행 |
| K1~K8 | KOSHA 가이드 — 유해화학물질 저장(K-1-2023) · 위험물 취급장소(G-9-2013) · 개인보호구(G-12-2013) · 경고표지(W-14-2020) · MSDS 작성(W-15-2020) · 유해성 분류(W-16-2020) · 리스크 관리(X-27-2012) · 불산 중독 예방(H-123-2013) | [안전보건공단](https://www.kosha.or.kr) | 각 지침 발행일 |
| S1 | 가상 현장 안전지침 (DEMO-A, 시연용) | 팀 작성 | 2026-10-23 |
| D1~D13 | MSDS — 황산 · 불산 · 과산화수소 · 암모니아수 · 염산 · 질산 · 인산 · TMAH · 아세톤 · 메탄올 · IPA · PGMEA · 수산화나트륨 | [Sigma-Aldrich Korea](https://www.sigmaaldrich.com/KR/ko) (과산화수소 · 인산은 Merck) | 2026-06~08 개정본 |
| — | 가상 장비 10대 ↔ 사용 물질 연결 | 팀 작성 `data/equipment_map.json` | 시연용 |

전체 목록(제품번호 · CAS · 개정일): [docs/데이터_출처표.xlsx](docs/데이터_출처표.xlsx) · `rag-service/ingest_all.sh`

- 법령 원문은 안내용이며 공식 해석이 아닙니다. 답변에는 시행일과 "현행 여부 확인 필요"를 함께 표시합니다.
- 원문 PDF 는 데모 · 학습용으로 함께 두었습니다. 다시 배포할 때는 각 원 출처의 이용 조건을 확인합니다.
- MSDS 는 데모 제품 기준입니다. 실제 작업 제품 · 농도 · 개정본과 같다고 보지 말고 현장 공급자 MSDS 를 따릅니다.
- 가상 장비 · 현장지침(S1)은 시연용으로 만든 자료입니다.

---

## 팀원별 담당

| 이름 | 파트 | 주요 작업 · 산출물 | 주요 파일 |
|---|---|---|---|
| 윤서진 | 데이터 파이프라인 · 발표 | 자료 수집 · 법령/지침 장 단위 청크 · MSDS 적재 · 메타데이터 / 데이터 출처표 · 발표 자료 | `ingest_law.py` · `ingest/` · `data/` |
| 김규빈 | 검색 · 평가 · 통합 | 질문 번역 · 동의어 · 제품/장비 범위 검색 · 임베딩 비교 / 평가셋 70문항 · 검색 · 답변 · 외국어 평가 / 평가 결과로 답변 생성 보완 (프롬프트 · 근거 · 번역 검사 오탐 수정, 비상 감지 확대, 소제목 · 목록 답변 형식) · 외국어 자료집 · 답변 화면 정리 · 자동 시험 · 브랜치 통합 | `rag/query.py` · `rag/retriever.py` · `rag/lexicon.py` · `eval/` (보완: `rag/prompt.py` · `rag/generator.py`) |
| 박진근 | LLM 답변 생성 | 프롬프트 · 번역 · 주장별 근거 검증 · 보류 분기 · 보류 이유 진단 / 생성 평가 | `rag/prompt.py` · `rag/generator.py` · `rag/llm.py` · `rag/diagnostics.py` |
| 정지우 | 인증 · API | Java 로그인 · JWT 발급/검증 · 401 처리 · 요청/응답 규격 · 로그 / API 명세서 · Swagger | `auth-server/` · `rag-service/app/` · `output/pdf/ChemBridge_API_명세서.pdf` |
| 강지훈 | 화면 · 배포 | 5개 언어 화면 · 추천 질문 · 제품/장비 선택 · 출처 원문 보기 · 음성 모드 / 전체 Docker Compose | `frontend/` · `docker-compose.yml` · `frontend/deploy/` |

`rag/chain.py`(검색 → 생성 연결)와 `rag/schema.py`(공통 이름)는 함께 관리합니다. 초기 작업 카드와 병합 · 검증 기록: [docs/archive/](docs/archive)

---

## 폴더 구조

```
ai-mini-project/
├── frontend/             Vue 3 + Vite 화면 (deploy/ : Docker 이미지 · nginx · 점검 스크립트)
├── rag-service/          RAG API (FastAPI)
│   ├── app/              /health · /rag-query · JWT 검증 · 오류 처리
│   ├── rag/              검색 · 생성 · 검증 (아래 흐름)
│   ├── ingest_law.py · ingest/   법령 · 지침 · MSDS 적재,  ingest_all.sh  전체 적재
│   ├── data/             원문 PDF · 장비 연결표 · lexicon/(비상 표현 사전 · 안전 용어집)
│   ├── eval/             평가셋 · 평가 스크립트 · reports/(발표용 기록)
│   └── tests/            자동 시험
├── auth-server/          Java 인증서버 (Gradle · MariaDB · BCrypt · JWT)
├── voice-service/        음성 서비스 (Whisper 음성 인식 · TTS) — 확장 트랙
├── docker-compose.yml    전체 서비스 한 번에 실행
├── dev.sh                개발용 DB · 인증 · RAG (· 음성) 실행
├── docs/                 데이터 출처표 · archive/(초기 작업 카드 · 병합 · 검증 기록)
└── .github/workflows/    자동 시험 (contract-test)
```

RAG 흐름: `RagRequest` → `chain.answer()` → `preflight_result()`(비상 · 범위 밖) → `resolve_product_id()` → `retriever.retrieve()`
→ `generator.generate()`(초안 → 인용 · 수치 · 번역 검사 → 검증 LLM) → `RagResponse`

## API 계약

```json
POST /rag-query   (쿠키 ACCESS_TOKEN 필요)
요청 {"question": "불산 취급 시 필요한 보호구는?", "topic": "chemical_safety", "product_id": null, "equipment_id": null, "language": "ko"}
응답 {"answer": "...", "sources": [{"doc_id": "D2", "section": "8. 노출방지 및 개인보호구", "title": "...", "url": "..."}],
      "needs_review": true, "handoff": false, "latency_ms": 9200}
```

- `topic`: `chemical_safety` · `serious_accident_law` / `language`: `ko` · `zh` · `vi` · `en` · `km`
- `handoff: true` = 답변 보류 또는 비상 · 법률 판단 요청 → 담당자 연결. 보류 이유는 응답 머리글 `X-ChemBridge-Outcome` · `-Reason` · `-Request-Id`
- 401 토큰 없음 · 만료 · 위조 / 422 형식 오류 / 503 LLM · 인덱스 문제
- `GET /health` → 200 준비 · 503 미준비, topic 별 인덱스 상태 포함
- Swagger: http://localhost:8001/docs · 명세서: [output/pdf/ChemBridge_API_명세서.pdf](output/pdf/ChemBridge_API_명세서.pdf)

## 테스트 · CI

```bash
cd rag-service && ../.venv/bin/python -m pytest -q tests      # RAG 900여 개, LLM · 검색은 가짜로 바꿔 돌림 (비용 · 키 불필요)
cd frontend && npm test                                       # 화면 80여 개 (API 계약 · 음성 모드 · 다국어 문구 · 라우팅)
```

- push · PR 마다 GitHub Actions(`contract-test`)가 둘 다 실행합니다. **❌ 가 뜬 PR 은 병합하지 않습니다.**
- 답의 **정확도**는 이 시험이 아니라 `eval/` 평가셋으로 잽니다.
  - 검색: `cd rag-service && PYTHONPATH=. ../.venv/bin/python -m eval.run_eval`
  - 답변: `cd rag-service && PYTHONPATH=. ../.venv/bin/python eval/answer_eval.py - <이름>` (LLM 비용 발생, 37문항 약 6분)

## 작업 규칙

1. 자기 브랜치(`feat/이름-작업`)에서 작업하고 **dev** 에 합칩니다. 제출 전에 dev 를 main 으로 PR 합니다.
2. `rag/schema.py` 의 이름은 바꾸지 않고 import 해서 씁니다. 바꿔야 하면 팀에 먼저 공유합니다.
3. 비밀값은 `.env` 에만 둡니다. `git add .` 대신 고친 파일만 add 합니다.
4. 법률 판단(처벌 · 책임 단정)과 작업 승인을 하지 않습니다 → `handoff: true`.
5. 외국어 비상 표현 · 번역 용어는 코드가 아니라 `rag-service/data/lexicon/*.json` 에 추가하고 `tests/test_lexicon.py` 에 예문을 넣습니다.

## 한계와 다음 단계

| 한계 | 다음 단계 |
|---|---|
| 응답 시간이 길다 (한국어 약 10초, 외국어 약 20초) | 검증 LLM · 번역 검사 병렬화, 자주 묻는 질문의 검토된 답변 저장 |
| 같은 질문도 검증 판정이 조금씩 달라진다 | 판정이 흔들리는 문항을 모아 검증 규칙 보완 |
| 자료 범위: 데모 MSDS 13종 · 가상 장비 · 가상 현장지침 | 고객사의 실제 MSDS · SOP 연동, 법령 개정 자동 반영 |
| 외국어 자료집은 원어민 검수 전 초안 | 원어민 · GHS 공식 번역으로 검수 |
| 효과(사고 감소 · 시간 절감)는 미측정 | 실제 작업자 대상 시범 적용 |
| 사용 기록을 품질 개선에 쓰지 못한다 (지금은 경로 · 지연 · 오류율만 남기고 질문 원문은 저장하지 않음) | 동의를 받고 개인정보를 가린 질문 · 답변 · 보류 이유 로그를 남겨 ① 보류가 잦은 질문을 평가셋 · 자료 · 용어집 보강에 쓰고 ② 판정이 흔들리는 문항을 찾아 검증 규칙을 고친다 |
| 신입 교육 자료가 따로 없다 | 로그에서 자주 묻는 질문을 작업 단계 · 물질별로 모아 신입 교육용 질문 모음 · 작업 전 확인 목록 · 언어별 용어 카드를 만들고, 담당자 확인으로 넘어간 질문은 선임 답변과 함께 교육 사례로 쌓는다 |

## 참고: 원본 골격(`ai-practice.zip`)에서 바뀐 점

- 폴더 이름: `workplace` → `auth-server`, `rag-code-template_ext` → `rag-service`, `voice-ai_code` → `voice-service`
- 실습 빈칸(TODO) 채움: 인증서버 ①~⑤, RAG Q01~Q05, 음성 Q01~Q05
- `voice-service/requirements.txt`: UTF-16 → UTF-8, `requests` 를 `>=2.32.5,<3.0` 으로 (langchain-community 호환)
- 새 구조: `rag-service/app`, `rag/`, `ingest/`, `eval/`, `tests/`. 실습용 템플릿 서버(`rag_external-web_pdf_closed_llm.py`)와 HTML 콘솔은 새 구조로 대체해 제외했습니다
