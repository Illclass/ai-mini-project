# ChemBridge frontend

Vue 3 + Vite. 기존 투명 유리 디자인을 유지하며 Java 회원가입·로그인과 RAG 질문·답변 API를 연결했습니다. 음성 입력·재생만 미리보기입니다.

## 실행

루트 README의 백엔드 설정을 먼저 준비합니다. 인증 서버에는 실제 `DB_PASSWORD`, `JWT_SECRET`이 필요하고 RAG에도 같은 `JWT_SECRET`을 전달해야 합니다. OpenAI 키는 RAG 서버에서만 사용합니다.

```sh
# 저장소 루트, 별도 터미널
./dev.sh
# frontend/
npm ci
npm run dev
```

http://localhost:5174 에서 회원가입 후 로그인합니다. 실제 계정 없이 로그인할 수 있는 디자인 모드는 제거했습니다. `dev.sh`는 프론트를 실행하지 않습니다.

## 연결

Vite가 동일 출처 요청을 아래 서버로 프록시합니다. 쿠키는 `credentials: include`로 전달하며 JWT는 프론트에서 읽거나 저장하지 않습니다.

| 경로 | 대상 | 처리 |
|---|---|---|
| `/api/signup` | Java :8080 | form 전송, 성공 리다이렉트 수신 후 로그인 폼 |
| `/api/login` | Java :8080 | form 전송, 성공 후 인증 쿠키 확인 |
| `/api/auth/check` | Java :8080 | 새로고침 시 로그인 상태 확인 |
| `/api/logout` | Java :8080 | 쿠키 삭제 후 인증 종료 확인 |
| `/rag-query` | FastAPI :8001 | 질문·영역·언어 전송, 실제 답변·출처 표시 |
| `/health` | FastAPI :8001 | 서버·인덱스 상태 |

배포 서버에서도 같은 경로로 reverse proxy를 구성해야 합니다. `npm run preview`는 정적 빌드 확인용으로 API 프록시를 제공하지 않습니다.

- 화학물질 안전·중대재해 법령 선택, ko/zh/vi 지원.
- 질문 실패: 입력 내용 유지, 해당 질문 재시도. 화면 이동 시 요청 취소.
- RAG 401: 로그인 화면으로 이동하고 작성 질문을 메모리에 보관, 재로그인 후 복원. 자동 재전송하지 않음.
- 422·503·연결 실패·시간 초과: 해당 언어로 오류 표시.
- `handoff`는 담당자 확인 경고, `needs_review`는 추가 확인 안내.
- 출처 제목·조항과 실제 http(s) 원문 링크 표시. 원문 링크가 없으면 문서 정보만 표시.
- 회원가입: 비밀번호 확인·중복 아이디 안내. 서버의 trim/BCrypt 특성 때문에 앞뒤 공백과 72바이트 초과 비밀번호는 가입 전 차단.
- 계정·비밀번호·토큰·대화는 브라우저 저장소에 보관하지 않음. 선택 언어만 저장. 새로고침하면 대화는 초기화.
- 현재 질문은 각각 독립 요청. 대화 이력을 백엔드에 보내는 계약은 없음.
- 음성 버튼과 듣기는 명시된 미리보기이며 실제 녹음·오디오 출력 없음.
- 로컬 인덱스가 없으면 답변·출처 생성 검증이 제한되며, 백엔드의 근거 없음/handoff 응답을 그대로 표시.

## 공통 계약과 검증

프론트에서 Python 모듈을 직접 import할 수 없어 `rag/schema.py`를 읽는 생성기로 공개 계약 JSON을 만듭니다. 백엔드 계약 변경 시 재생성하고 diff를 확인합니다.

```sh
# 저장소 루트
.venv/bin/python frontend/scripts/generate-contract.py
.venv/bin/python frontend/scripts/generate-contract.py --check
cd frontend
npm test
npm run build
# 저장소 루트/rag-service
../.venv/bin/python -m pytest -q tests
```

`src/api/client.js`는 요청·응답 검증, `src/api/contract.json`은 공유 계약, `src/locales/api.js`는 API 상태 문구, `src/App.vue`는 인증·질문 상태를 담당합니다. 레이아웃·모션은 기존 Vue 컴포넌트와 glass CSS를 유지합니다. 새 런타임 패키지는 추가하지 않았습니다.
