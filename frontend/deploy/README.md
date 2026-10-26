# ChemBridge 전체 Docker 실행

DB·Java 인증·RAG·음성(STT/TTS)·Vue/Nginx를 루트 Compose로 실행합니다. 기존 `dev.sh`, 개발용 DB 컨테이너와 별도이며 백엔드 소스는 변경하지 않습니다.

## 준비

- Docker Desktop 실행. 이 프로젝트의 로컬 임베딩/Whisper를 위해 Docker 메모리 8GB를 기준으로 검증했습니다.
- 기존 환경 파일 3개가 필요합니다. 비밀값은 Git에 올리지 않습니다.
  - `auth-server/.env`: `DB_PASSWORD`, `JWT_SECRET`
  - `rag-service/.env`: `OPENAI_API_KEY`, 선택 사항 `LLM_MODEL`, `EMBEDDING_MODEL`
  - `voice-service/app/.env`: `OPENAI_API_KEY`, 선택 사항 `WHISPER_MODEL`
- 인증의 JWT 설정을 RAG·음성에도 전달합니다. 기존 `.env` 값을 변경하거나 이미지에 복사하지 않습니다.
- 기존 FAISS 인덱스를 재사용할 때는 생성에 사용한 임베딩 모델과 `EMBEDDING_MODEL`이 같아야 합니다. 기본은 `bge-m3`입니다.

## 실행·종료

저장소 루트에서:

```bash
docker compose up -d --build
```

준비가 끝나면 **http://localhost:5190** 에서 회원가입 후 사용합니다. 기존 개발 DB 계정은 자동 복사하지 않습니다. 최초 빌드·모델 다운로드·인덱스 생성에는 시간이 걸릴 수 있습니다.

```bash
docker compose ps -a                    # 서비스 상태, index-init의 Exited (0)는 정상
docker compose logs -f rag voice        # 준비/오류 확인 (Ctrl+C는 로그 보기만 종료)
docker compose stop                    # 종료, 컨테이너·데이터 유지
docker compose up -d                    # 재실행
docker compose down                    # 컨테이너·네트워크 제거, 데이터 볼륨 유지
```

`down -v`는 DB·인덱스·모델 볼륨까지 삭제하므로 일반 종료에 사용하지 않습니다. 다른 포트가 필요하면 `WEB_PORT=5191 docker compose up -d`로 실행합니다.

## 구성

| 서비스 | 역할 / 저장 |
|---|---|
| web | Vue 프로덕션 빌드 + Nginx, 외부 공개는 `127.0.0.1:5190`만 |
| auth | Java 17 / Spring Boot, DB 주소 `db:3306` |
| db | MariaDB 11.4, 최초 users 테이블 생성, `chembridge_db-data` 볼륨 |
| index-init | 기존 로컬 인덱스를 별도 볼륨으로 복사. 없으면 저장소 PDF로 적재. 이미 완성된 볼륨은 유지 |
| rag | 단일 워커, 검색 인덱스 읽기 전용, `chembridge_indexes` 볼륨 |
| voice | CPU Whisper + ffmpeg + 실제 TTS, 단일 워커 |

모델 캐시는 `chembridge_models` 볼륨을 공유합니다. RAG·음성의 패키지는 이미지별로 분리해 기존 의존성 버전 충돌을 피합니다. 새 패키지는 추가하지 않았습니다.

Nginx가 `/api/*` → `auth:8080`, `/rag-query`·`/health` → `rag:8001`, `/voice/*` → `voice:8008`로 연결합니다. 같은 호스트로 쿠키와 Origin을 전달하며 업로드는 12MB, 응답 대기는 180초입니다. Docker DNS를 재조회해 백엔드 IP가 바뀌어도 복구합니다.

DB·인덱스·모델은 개발 환경과 분리됩니다. 컨테이너가 준비된 뒤 의존 서비스를 실행하며, 양쪽 검색 인덱스가 준비되어야 RAG가 healthy가 됩니다.

## 검증

```bash
# Python 표준 라이브러리만 사용. 별도 Compose DB에 테스트 계정을 생성합니다.
python3 frontend/deploy/smoke.py
# DB·인증을 재시작해 계정 유지와 프록시 복구까지 확인
python3 frontend/deploy/smoke.py --restart
# 실제 RAG 2회와 TTS 1회 호출. STT는 로컬 Whisper, 호스트 ffmpeg 필요
python3 frontend/deploy/smoke.py --live
```

`--live`는 설정된 API의 사용 비용이 발생할 수 있습니다. 테스트 계정 비밀번호·토큰은 메모리에서만 사용하며 출력하지 않습니다. 테스트 계정은 Compose DB에 남습니다.

## 적용 범위

- 로컬 시연용 HTTP 구성입니다. `localhost`에서는 마이크를 사용할 수 있습니다. 외부 공개는 별도 도메인/HTTPS와 배포용 인증·쿠키 정책 검토 후 진행합니다.
- 등록 계정·DB와 검색 인덱스는 재시작해도 유지됩니다. 원문 PDF가 바뀌면 기존 인덱스가 자동 갱신되는 것은 아닙니다.
- 기존 WAV 업로드 500 및 무음 인식 문제는 음성 코드의 별도 이슈이며 이번 배포 작업에서 수정하지 않았습니다. 브라우저에서 사용하는 WebM 경로를 검증했습니다.
- Compose 준비 대기와 Nginx DNS: [Docker 공식 문서](https://docs.docker.com/compose/how-tos/startup-order/), [Nginx 공식 문서](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#resolve).
