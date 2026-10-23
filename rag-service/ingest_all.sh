#!/usr/bin/env bash
# 문서 27개(법령 5 · KOSHA 지침 8 · 가상 현장지침 1 · MSDS 13)를 한 번에 FAISS 에 적재한다.
# 값은 docs/데이터_출처표.xlsx 기준. 문서를 추가·변경하면 출처표와 이 파일을 같이 고친다.
#
#   cd rag-service
#   ./ingest_all.sh --dry-run   # 청크 수만 확인 (임베딩·저장 안 함, 비용 없음)
#   ./ingest_all.sh             # faiss_db/law, faiss_db/msds 를 지우고 새로 적재 (OpenAI 임베딩 비용 발생)
set -euo pipefail
cd "$(dirname "$0")"

PY="../.venv/bin/python"
[[ -x "$PY" ]] || { echo "루트 가상환경(.venv)이 없습니다. README 의 환경 설정을 먼저 하세요." >&2; exit 1; }

MODE="--append"
if [[ "${1:-}" == "--dry-run" ]]; then
  MODE="--dry-run"
else
  rm -rf faiss_db/law faiss_db/msds
fi

LAW_URL="https://www.law.go.kr"
KOSHA_URL="https://www.kosha.or.kr"
SIGMA_URL="https://www.sigmaaldrich.com/KR/ko"

law() {   # law <파일> <문서ID> <법령명> <시행일> [조 범위]
  "$PY" ingest_law.py --mode law --input "data/laws/$1" --doc-id "$2" --law-name "$3" \
    --effective-date "$4" --source-url "$LAW_URL" ${5:+--only "$5"} $MODE | grep -aE "^\[(law|guide)\]|^\[경고\]|^\[알림\]|^저장 완료" || true
}
guide() { # guide <파일> <문서ID> <지침명> <날짜> [URL]
  "$PY" ingest_law.py --mode guide --input "$1" --doc-id "$2" --law-name "$3" \
    --effective-date "$4" --source-url "${5:-$KOSHA_URL}" $MODE | grep -aE "^\[(law|guide)\]|^\[경고\]|^\[알림\]|^저장 완료" || true
}
msds() {  # msds <파일> <문서ID> <product_id> <물질명> <공급사> <CAS> <개정일> <제목>
  "$PY" ingest/ingest_msds.py --input "data/msds/$1" --doc-id "$2" --product-id "$3" --substance "$4" \
    --supplier "$5" --cas-no "$6" --revision-date "$7" --title "$8" --source-url "$SIGMA_URL" $MODE 2>&1 \
    | grep -aE "^\[msds\]|^\[경고\]|^저장 완료" || true
}

echo "== 법령 → faiss_db/law"
law L1_산안법.pdf         L1 "산업안전보건법"                  2026-08-01 "52,110-116"
law L1_안전보건규칙.pdf   L4 "산업안전보건기준에 관한 규칙"    2026-03-02 "31-34,299,420-511"
law L1_시행규칙.pdf       L5 "산업안전보건법 시행규칙"         2026-08-01 "156-171"
law L2_중대재해처벌법.pdf L2 "중대재해 처벌 등에 관한 법률"    2022-01-27
law L3_화관법.pdf         L3 "화학물질관리법"                  2026-10-08

echo "== KOSHA 지침 · 현장지침 → faiss_db/msds"
guide data/laws/K1_화학물질저장.pdf K1 "KOSHA K-1-2023 유해화학물질 저장 관련 지침"                         2023
guide data/laws/K2_위험표시.pdf     K2 "KOSHA G-9-2013 위험물 취급장소 관련 지침"                           2013-11
guide data/laws/K3_개인보호구.pdf   K3 "KOSHA G-12-2013 개인보호구의 사용 및 관리에 관한 기술지침"          2013-08-30
guide data/laws/K4_경고표지.pdf     K4 "KOSHA W-14-2020 경고표지 작성 지침"                                 2020-12
guide data/laws/K5_MSDS작성.pdf     K5 "KOSHA W-15-2020 물질안전보건자료 작성 지침"                         2020-12
guide data/laws/K6_유해성분류.pdf   K6 "KOSHA W-16-2020 화학물질의 유해성·위험성 분류 지침"                 2020-12
guide data/laws/K7_리스크관리.pdf   K7 "KOSHA X-27-2012 화학물질 리스크 관리를 위한 작업공정별 관리요령"    2012-06
guide data/laws/K8_불산지침.pdf     K8 "KOSHA H-123-2013 불산·불화수소 취급근로자의 중독 예방 및 응급대응 지침" 2013-12
guide data/site/S1_가상현장안전지침.pdf S1 "S1 가상 현장 안전지침 (DEMO-A, 시연용)" 2026-10-23 ""

echo "== MSDS → faiss_db/msds"
SA="Sigma-Aldrich Korea"; MK="Merck(Millipore)"
msds D1_황산.pdf          D1  sigma-339741  황산          "$SA" 7664-93-9 2026-07-14 "황산 MSDS (Sulfuric acid)"
msds D2_불산.pdf          D2  sigma-695068  불산          "$SA" 7664-39-3 2026-07-17 "불산 MSDS (Hydrofluoric acid)"
msds D3_과산화수소.pdf    D3  merck-8.22287 과산화수소    "$MK" 7722-84-1 2026-08-04 "과산화수소 MSDS (Hydrogen peroxide 30%)"
msds D4_암모니아수.pdf    D4  sigma-221228  암모니아수    "$SA" 1336-21-6 2026-07-09 "암모니아수 MSDS (Ammonium hydroxide solution)"
msds D5_염산.pdf          D5  sigma-258148  염산          "$SA" 7647-01-0 2026-06-09 "염산 MSDS (Hydrochloric acid)"
msds D6_질산.pdf          D6  sigma-438073  질산          "$SA" 7697-37-2 2026-06-05 "질산 MSDS (Nitric acid)"
msds D7_인산.pdf          D7  merck-1.00573 인산          "$MK" 7664-38-2 2026-07-31 "인산 MSDS (ortho-Phosphoric acid 85%)"
msds D8_TMAH.pdf          D8  sigma-328251  TMAH          "$SA" 75-59-2   2026-07-14 "TMAH MSDS (Tetramethylammonium hydroxide solution)"
msds D9_아세톤.pdf        D9  sigma-179124  아세톤        "$SA" 67-64-1   2026-07-14 "아세톤 MSDS (Acetone)"
msds D10_메탄올.pdf       D10 sigma-34860   메탄올        "$SA" 67-56-1   2026-07-01 "메탄올 MSDS (Methanol)"
msds D11_IPA.pdf          D11 sigma-563935  IPA           "$SA" 67-63-0   2026-06-30 "IPA MSDS (Isopropanol 70~75%)"
msds D12_PGMEA.pdf        D12 sigma-484431  PGMEA         "$SA" 108-65-6  2026-07-14 "PGMEA MSDS (Propylene glycol monomethyl ether acetate)"
msds D13_수산화나트륨.pdf D13 sigma-221465  수산화나트륨  "$SA" 1310-73-2 2026-07-09 "수산화나트륨 MSDS (Sodium hydroxide)"

if [[ "$MODE" == "--dry-run" ]]; then
  echo "(dry-run 끝: 저장하지 않았습니다)"
else
  echo "적재 완료. RAG 서버를 재시작하고 /health 에서 indexes 가 모두 true 인지 확인하세요."
fi
