# ChemBridge Generation — 현재 VS Code 저장소 작업 안내

## 반영 범위

2026-10-23, `/Users/jingeun/Downloads/ai-mini-project`의 pull 완료 커밋 `c7c4771`을 기준으로 작업했습니다. 시작 당시 main과 origin/main이 같고 미커밋 변경은 없었습니다. `feat/rag-generation` 브랜치를 만들었으며 main 수정·commit·push는 하지 않았습니다.

사용자가 **Generation 파일만 반영하고 공동 변경은 남겨 두도록** 지정했습니다. 따라서 `rag/chain.py`, `rag/schema.py`, 기존 `tests/test_contract.py`와 Retriever·적재·JWT·API·프론트·팀 README는 그대로입니다. 이전 Generation 코어를 재사용했으며 별도 RAG 엔진은 만들지 않았습니다. 이후 프롬프트 연결 정리에서도 기존 미커밋 작업을 보존했습니다.

## 파일과 담당

```text
rag-service/
├── rag/
│   ├── prompt.py       # 박진근: 프롬프트·메시지 조립·다국어 문구/번역 규칙
│   ├── generator.py    # 박진근: Hit/Document 입력·생성 연결·근거/출처/보류 검증
│   └── llm.py          # 박진근: 기존 평문 호출 + 구조화 LLM 호출·timeout 설정
├── tests/generation/   # 생성 전용 Mock/실제 호출 구분 테스트
└── GENERATION.md
```

팀원들이 공유한 담당 파일 구조에 맞췄습니다. 추가했던 generation.py, generation_policy.py, generation_response.py의 기능은 위 세 파일로 옮겼고 해당 추가 파일은 제거했습니다. 원본은 작업 폴더에 백업했습니다. 공동 schema.py와 chain.py는 그대로입니다.

호출 경로는 `generator.generate()` → 같은 파일의 `generate_answer()` → `prompt.build_document_messages()` → `llm.build_structured_llm()` → generator의 인용·출처 검증입니다.

- 규칙 문구와 컨텍스트 조립: prompt.py의 SYSTEM_PROMPT/build_document_messages. 기존 build_messages(question, hits, language) 입력·dict 반환 형식 유지.
- 생성 및 검증: generator.py. 기존 generate(question, hits, language) 진입점과 needs_review/needs_handoff 함수 유지. 선택 keyword는 내부 직접 호출용이며 HTTP 계약은 변경하지 않음.
- 제공자 호출: llm.py. 기존 call_llm 인터페이스 유지. 검증된 생성 경로는 build_structured_llm을 쓰며 timeout 기본 30초·자동 재시도 0회.
- 생성 보조 데이터 타입은 generator 안에서 관리하며 팀 API 타입과 enum은 schema.py에서 가져옵니다.

## 호출 계약

```python
from rag.generator import generate_answer
from rag.generator import generate

# Generation 단독: Retriever의 실제 원문과 metadata를 보존한 Document 목록
result = generate_answer(
    question, documents,                  # str, list[Document]
    language="ko",                       # ko / zh / vi
    product_id=None, topic=None,
    mode="qa",                           # qa / learn / precheck (내부 옵션)
    structured_llm=None,                  # Mock: invoke(messages) 구현
    model=None, timeout_seconds=30.0,
)
# result.model_dump(): answer, sources, needs_review, handoff

# 기존 팀 함수의 위치 인자 호환 유지
response = generate(question, hits, language)
# MSDS 검증에는 요청에서 받은 제품 식별자가 필요
response = generate(question, hits, language, product_id=product_id, topic=topic)
```

기존 HTTP 요청 필드는 question/topic/product_id/language, 응답은 answer/sources/needs_review/handoff/latency_ms 그대로입니다. mode는 API 필드로 추가하지 않았습니다. 질문의 '신입', '작업 전' 표현으로 표시 방식을 선택할 수도 있습니다.

## 구현된 기능

- 문서 원문과 메타데이터 전체를 비신뢰 데이터로 프롬프트에 전달합니다. 문서 안의 지시를 시스템 지시로 취급하지 않습니다.
- 모델은 문장, 분류, 적용 조건, chunk_id와 원문 인용을 반환합니다. 서버가 존재하는 chunk_id와 원문 부분 문자열을 검증하고 출처를 만듭니다. 조문명·문서명·URL은 모델 출력에서 받지 않습니다.
- 법령 의무와 권고 지침을 구분합니다. 시행일만으로 현행성을 단정하지 않고, 적용 조건·현행성 불명확 시 needs_review/handoff를 표시합니다. 오래된 법령을 곧바로 폐지된 법령이라고 단정하지 않습니다.
- MSDS는 요청 product_id와 검색 제품의 일치, 제품명·제품번호·농도·개정일의 원문 근거를 확인합니다. 불명확하거나 서로 다르면 보류합니다.
- ko/zh/vi의 쉬운 안내문을 제공하고 경고·조건의 원문을 보존합니다. 번역의 수치·단위·금지·제외 조건 누락을 검사합니다.
- 법적 책임 판단, 작업 승인, 위험한 현장 조작 요청은 답변을 보류합니다.
- Generation 함수 자체는 긴급 질문에서 LLM을 호출하지 않고 현장 비상절차·한국 119·담당자 연락을 우선 안내합니다.
- LLM의 네트워크 timeout은 기본 30초, 자동 재시도 0회입니다. 원시 오류·키는 응답에 노출하지 않으며 제공자 장애는 기존 API의 503 처리로 전달합니다. 전체 요청의 절대 시간 제한은 아닙니다.

인용 검사는 출처 존재와 인용문 일치를 확인할 뿐, 모든 문장의 의미적 정당성이나 번역 품질을 보증하지 않습니다. 실제 자료와 전문가 검토가 추가로 필요합니다.

## 아직 공동 연결이 필요한 부분 — 현재 API의 제한

**현재 chain.py는 그대로이므로 다음 두 가지는 완성되지 않았습니다.**

1. chain이 검색을 먼저 실행합니다. Generation은 긴급 질문에서 LLM을 생략하지만, HTTP 요청은 검색을 기다릴 수 있습니다. 검색 전 preflight를 실행하는 공동 변경이 필요합니다. 현재 상태를 '긴급 상황 즉시 안내가 API 전체에 구현됐다'고 표현하면 안 됩니다.
2. chain은 generate(question, hits, language)만 호출합니다. product_id/topic이 생성 단계까지 전달되지 않으므로 현재 HTTP MSDS 질문은 제품 확인 보류가 됩니다. 직접 Generation을 호출할 때는 product_id를 전달해 검증할 수 있습니다. 검색 결과의 제품 ID를 사용자 선택값으로 추측해 채우지 않습니다.

공동 연결안은 별도 `chembridge-shared-connection.patch`에 남겼습니다. 이 패치는 chain.py와 기존 계약 테스트의 가짜 자료·Mock 연결점만 변경하며 현재 저장소에는 적용하지 않았습니다. API 응답 필드 변경은 없습니다.

## 출처 계약

- 내부: 기존 law_name/article_no/source_url/doc_type/chunk_id를 보존하고 확인 가능한 팀 메타데이터를 함께 유지합니다.
- 외부: 팀 Source의 doc_id/section/title/url만 반환합니다. 공통 schema.py를 바꾸지 않았습니다.
- doc_id는 문서 ID, chunk_id는 개별 청크 ID입니다. 하나를 다른 것으로 임의 대체하지 않습니다.
- 필수 메타데이터가 없거나 ID가 충돌하면 출처를 지어내지 않고 보류합니다.
- MSDS에 해당하지 않는 law_name/article_no는 내부에서 빈 문자열로 취급합니다. 외부 sources의 필드 확장·null 정책은 데이터/API 담당의 합의가 필요합니다.

## 테스트와 결과

이번 작업은 기존 검증용 Python 3.12 가상환경으로 실행했습니다. 새 저장소에는 아직 .venv가 없습니다. 프로젝트의 권장 Python은 3.11이며 새 패키지/requirements 변경은 없습니다.

```bash
cd rag-service
python -m pytest -q tests/generation
python -m pytest -q tests
```

| 구분 | 이번 실제 반영본 결과 |
|---|---|
| Generation 오프라인 테스트 | 195 통과, 실제 LLM 9개 건너뜀 |
| 전체 오프라인 테스트 | 204 통과, 1 실패, 실제 LLM 9개 건너뜀 |
| 문법 검사 | 팀 담당 Python 3개와 생성 테스트 문법 검사 통과 |
| 실제 LLM | 이번 프롬프트 연결 정리에서도 실행하지 않음 |

전체 테스트의 유일한 실패는 기존 `test_answer_has_contract_fields`입니다. 그 가짜 Hit에 필수 chunk_id/doc_type이 없고, Mock도 예전 평문 호출에 연결되어 있습니다. 새 생성기는 검증할 수 없는 출처를 반환하지 않으므로 sources=[]가 되어 기존 기대와 충돌합니다. 테스트를 건너뛰거나 검증을 약화하지 않았습니다. 사용자 요청대로 공동 테스트는 수정하지 않았습니다. 따라서 현재 전체 CI가 성공했다고 보고하면 안 됩니다.

공동 연결안까지 적용한 검증용 사본에서는 205 통과·9 건너뜀을 확인했지만, 이는 **현재 VS Code 저장소에 적용된 결과가 아닙니다.** 추가 HTTP 연결 테스트는 검토용 파일로 따로 보관했습니다.

가상 테스트에는 실사용 금지 문구가 포함된 제품 자료를 사용합니다. 실제 FAISS 엔진 테스트는 가짜 임베딩과 Mock LLM을 사용하므로 실제 OpenAI 검색·답변 성공과 구분합니다. 공개 OSHA 짧은 발췌는 별도 fixture이며 한국 현행 법령이나 실제 MSDS라고 취급하지 않습니다.

이전 작업에서 실제 LLM 9개 사례를 확인한 이력은 있으나 이번 저장소의 실제 서비스 성공을 의미하지 않습니다. 이전 마지막 전체 실행은 8 통과·제공자 오류 1 실패, 해당 1개 재실행은 통과였습니다.

실제 LLM을 별도로 검증하려면 허용된 자료만 사용하고 키가 있는 환경에서 실행합니다.

```bash
RAG_RUN_GENERATION_LIVE=1 python -m pytest -q tests/generation -m live
```

## Swagger 확인 방법

현재 이 저장소에는 .env, .venv, 법령/MSDS FAISS 인덱스가 없습니다. 이전 폴더의 비밀키와 데이터를 임의 복사하지 않았습니다.

1. 팀 README에 따라 가상환경과 의존성을 준비하고, 키/JWT_SECRET을 기존 .env 방식으로 설정합니다.
2. 데이터 담당에게 팀 메타데이터가 보존된 법령/MSDS 인덱스를 받거나 공식 적재 절차로 만듭니다.
3. `rag-service`에서 `python -m uvicorn app.main:app --port 8001 --reload`로 실행합니다.
4. Java를 실행하고 `http://localhost:8080`에서 로그인한 뒤 `http://localhost:8001/docs`로 접속합니다. localhost와 127.0.0.1을 섞으면 쿠키가 전달되지 않을 수 있습니다.
5. /health의 주제별 인덱스를 확인하고 POST /rag-query를 실행합니다.

```json
{"question":"신입에게 법령 자료의 적용 조건을 쉽게 설명해줘","topic":"serious_accident_law","product_id":null,"language":"ko"}
```

language를 zh/vi로 바꾸어 확인할 수 있습니다. 401은 로그인/쿠키, 503은 모델·설정·인덱스 장애 등을 확인합니다. 출처가 비어 있고 두 플래그가 true라면 근거/메타데이터/제품 식별 보류일 수 있습니다. MSDS의 정상 HTTP 검증과 긴급 질문의 검색 생략은 공동 연결 후 확인해야 합니다.

## 팀에 공유할 사항

- 규빈 님: list[Hit]의 text와 metadata를 보존합니다. chain의 검색 전 preflight와 product_id/topic 전달은 공동 변경안에 남겨 두었습니다. zh/vi 검색어 번역은 여전히 query.py의 TODO이며 생성 번역과 별개입니다.
- 서진 님: 각 청크의 실제 doc_id/chunk_id/doc_type/source_url을 보존합니다. 법령의 law_name/article_no와 시행본, MSDS의 제품 식별·농도·개정일 원문이 필요합니다. 현재 legacy 법령 적재의 doc_id 보완과 MSDS 적재 TODO는 그대로입니다.
- 정지우 님: API 필드·JWT·503 정책은 유지했습니다. 공동 계약 테스트의 가짜 자료와 Mock 연결점 보완, sources의 추가 필드/null 정책은 별도 협의가 필요합니다.
- 지훈 님: needs_review/handoff는 담당자 확인 필요 표시이며 실제 연락 완료가 아닙니다. 긴급 안내는 API 응답 대기 없이도 표시하는 설계가 필요합니다.
- 진근 님: 현재 브랜치에서 Generation 프롬프트·검증·다국어 테스트를 이어서 개발하면 됩니다. 팀 담당 파일 prompt.py/generator.py/llm.py에서 이어서 개발합니다. 추가 런타임 모듈은 제거했습니다.
