# ChemBridge Generation — 구현 및 팀 연결 안내

2026-10-23 기준. 박진근 담당인 `rag/prompt.py`, `rag/generator.py`, `rag/llm.py`와 Generation 전용 테스트를 구현했습니다. 공통 API 계약은 유지합니다. 최신 원격 main의 데이터 적재 변경은 이 작업 브랜치에 아직 병합하지 않았습니다.

## 호출 방법

```python
from rag.generator import generate, generate_answer, preflight_result

# 검색 담당이 반환한 실제 Hit 목록을 그대로 전달합니다.
response = generate(
    question, hits, language,
    product_id=product_id,
    topic=topic,
)
# RagResponse: answer, sources, needs_review, handoff, latency_ms

# Document 직접 연결: 검색/적재/API 처리는 수행하지 않습니다.
result = generate_answer(
    question, documents,  # str, list[Document]
    language="ko", product_id=product_id, topic=topic,
    mode="qa",           # qa / learn / precheck: 내부 옵션
    timeout_seconds=30.0,
)
# model_dump(): answer, sources, needs_review, handoff

# 공동 chain에서 검색 전에 사용할 수 있는 Generation의 사전 검사입니다.
early = preflight_result(question, language)
```

`mode`와 내부 검토 사유는 HTTP 최상위 필드로 추가하지 않았습니다. `generate()`가 반환하는 `latency_ms=0`은 공동 chain이 전체 소요 시간으로 채워야 합니다.

## Generation 구현

- `prompt.py`: 문서만 근거로 답변, 쉬운 표현, 법령 의무/기술지침 권고 구분, ko/zh/vi 안내·번역 규칙.
- `generator.py`: 실제 문서 인용과 chunk_id 검증, 제품 식별, 수치 비교, 별도 LLM의 주장 검증, 답변/출처/검토 플래그 구성.
- `llm.py`: 구조화된 생성/검증 LLM 호출. 각각 기본 timeout 30초, SDK 자동 재시도 없음. 전체 요청의 절대 시간 제한은 아닙니다.
- 정상 근거 답변은 생성과 검증으로 보통 LLM을 2회 호출합니다. 비상·범위 밖 요청·일부 근거 오류는 먼저 보류합니다. 제공자 오류는 원시 오류나 키를 노출하지 않습니다.
- 법령 시행일만으로 현행성·현장 적용을 확정하지 않습니다. MSDS는 제품명·제품번호·농도·개정일의 본문 근거와 요청 product_id를 확인합니다.
- 출처는 모델이 생성한 이름/URL을 사용하지 않습니다. 내부 메타데이터를 보존하고, 외부에는 공통 `Source`의 `doc_id`, `section`, `title`, `url`을 반환합니다.
- `needs_review`/`handoff`는 추가 확인 필요 표시이며, 실제 연락 또는 작업 승인 완료를 의미하지 않습니다.

## 이번에 확인하고 수정한 오류

1. MSDS 원문의 `2026.07.14`와 메타데이터의 `2026-07-14`를 같은 날짜로 비교합니다. 원문 인용과 메타데이터는 바꾸지 않습니다. 모호한 날짜·잘못된 날짜·미래 날짜·개정일 불일치는 계속 거부합니다.
2. PDF 줄바꿈을 문장 끝으로 오인하던 경고 추출을 보완했습니다. 같은 원문 안의 연속 문자열을 보존하고 표시할 때만 줄바꿈을 정리합니다. 연락처/공휴일 안내, 약어 설명, 문서 안내가 경고에 섞이지 않도록 했습니다.
3. 경고의 앞뒤가 잘려 문맥을 확인할 수 없는 MSDS는 조각을 임의 완성하지 않고 LLM 호출 전에 보류합니다. 추출은 규칙 기반이므로 모든 문서 형태를 완벽히 판별하지는 못합니다.

## 검사 결과

```bash
cd rag-service
python -m pytest -q tests/generation
python -m pytest -q tests
```

2026-10-23 현재 로컬 코드에서 전체 오프라인 검사: **378 통과, 기존 공동 테스트 1 실패, 실제 호출용 12개 건너뜀**. Generation 전용 범위는 **369 통과, 12개 건너뜀**입니다. 날짜 회귀 검사 25개, 경고문 회귀 검사 18개, pull된 API와 Generation의 Mock 연결 검사 6개가 포함됩니다. 새 의존성은 추가하지 않았습니다. 검증 환경은 Python 3.12이며 프로젝트 권장은 3.11입니다.

기존 실패는 `tests/test_contract.py::test_answer_has_contract_fields`입니다. 가짜 Hit에 검증용 메타데이터가 부족하고 Mock이 기존 평문 LLM 호출에 연결되어, 검증 후 `sources=[]`가 반환되는 것과 기대가 충돌합니다. 공동 테스트를 수정하거나 검증을 약화해 우회하지 않았습니다. 따라서 전체 CI 통과 상태는 아닙니다.

실제 호출은 위 오프라인 검사와 별도로 수행했습니다.

| 실제 호출 사례 | 확인한 결과 |
|---|---|
| 가상 색상 원문과 고정 초안의 일치/모순 | 실제 검증 LLM이 청록색 일치를 통과, 빨간색 모순을 차단. 초안 생성은 고정값이었음 |
| 저장소의 실제 법령 PDF → 임시 FAISS → 생성·검증 | 법의 목적 설명과 실제 출처 확인. 문서에 없는 질문은 보류 |
| 실제 황산 MSDS의 1·3·16항 제공 | 원문 날짜/제품 식별 검증 후 답변 생성·검증 완료 |
| 실제 황산 MSDS의 폐기 주의사항도 제공 | 불필요한 경고는 제거되고 “다른 폐기물과 혼합 금지.”는 유지 |
| MSDS 기본 검색 상위 5건 | 제품 식별 근거 부족 또는 잘린 경고 문맥 때문에 보류 |

실제 MSDS 정상 사례는 필요한 실제 항목을 명시적으로 고른 진단입니다. 기본 검색 전체 흐름의 성공을 의미하지 않습니다. 테스트용 FAISS는 메모리에만 만들었고 운영 인덱스·API·JWT·프론트 전체 연결을 검증하지 않았습니다. 최근 실제 MSDS 호출은 한국어 기준이며 다국어 규칙은 오프라인 회귀 검사로 확인했습니다. 사용한 출처 URL 일부는 기관/공급자 홈페이지이므로 정확한 개정본 링크는 데이터 담당과 확인해야 합니다.

실제 모델용 기존 테스트는 명시적으로 활성화할 때만 호출합니다. 키는 Git에 포함되지 않는 `.env` 또는 환경변수로 설정합니다.

```bash
RAG_RUN_GENERATION_LIVE=1 python -m pytest -q tests/generation -m live
```

위 명령은 저장소에 있는 가상/공개 발췌 테스트이며, 위 MSDS 임시 인덱스 진단을 그대로 재현하는 명령은 아닙니다.

## 팀 통합 때 함께 해결할 항목

- 공동 `chain.py`: 요청의 `product_id`, `topic`을 Generation에 전달하고 검색 전에 `preflight_result()`를 실행해야 합니다. 현재 chain은 그대로이며 긴급 질문도 검색을 먼저 기다릴 수 있습니다.
- 검색/데이터: MSDS의 제품 식별(1항), 농도(3항), 개정일(16항) 등 필요한 실제 근거가 함께 전달되도록 연결하고, 잘린 경고 문맥을 복구해야 합니다. 검색 결과에서 요청 제품 ID를 임의 추측해 채우지 않습니다.
- API/공동 테스트: 최신 구조화 LLM·검증 LLM 연결에 맞춰 공통 테스트의 가짜 자료와 Mock을 정비해야 합니다.
- 통합 검증: 운영 FAISS, Swagger/JWT, 실제 제품 선택, ko/zh/vi 답변·경고 유지, 지연을 팀 코드와 합친 뒤 확인해야 합니다.

이번 공유 시점에는 기능을 추가로 늘리지 않고, 위 연결 항목을 담당자들과 함께 검증합니다. 기존 `chembridge-shared-connection.patch`는 과거 제안이며 최신 코드를 확인하지 않고 그대로 적용하지 않습니다.
