# 작업 카드 — 정지우 (인증 연동·API)

## 할 일
1. `app/auth.py` 검토: Java 인증서버의 `ACCESS_TOKEN` 쿠키를 `JWT_SECRET` 으로 검증 (임시 구현 있음)
2. `app/main.py`
   - 요청 로그 미들웨어: 경로·상태코드·지연(ms)만 기록, **질문 원문·토큰은 기록하지 않음**
   - 오류 응답 정리: 401(인증) · 422(형식) · 503(LLM 타임아웃·인덱스 미준비)
   - Swagger(`/docs`) 설명 보강
3. 쿠키 방식 vs Bearer 헤더 — 강사님 답변에 맞춰 결정

## 고칠 파일
`rag-service/app/main.py`, `rag-service/app/auth.py`

## 완료 기준
- 토큰 없음 401, 위조 토큰 401, 잘못된 topic 422, 정상 200
- `logs/rag.log` 에 질문 원문이 없음
- 약속 확인 테스트 통과

## AI 에게 붙여 넣을 프롬프트
```
[프로젝트 규칙]
- rag-service/rag/schema.py 의 RagRequest/RagResponse 는 바꾸지 않는다.
- /rag-query 는 rag.chain.answer(req) 만 호출한다. 검색·LLM 을 직접 부르지 않는다.
- 고칠 파일: rag-service/app/main.py, app/auth.py 만. 비밀키는 환경변수(JWT_SECRET)로만.

[고칠 파일 내용]
(app/main.py 와 app/auth.py 전체)

[요청]
FastAPI 미들웨어로 요청마다 경로, 상태코드, 처리시간(ms)을 로그로 남겨 줘. 요청 본문(질문)과 쿠키는 절대 기록하지 마.
```
