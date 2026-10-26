"""정확성 판정용 실행 — 담당: 김규빈 (2026-10-26)

eval/accuracy_set.json 의 질문을 실제 검색·생성으로 한 번씩 돌려 답변·출처·보류 이유를 저장한다.
정확 · 근거 · 환각 판정은 사람이 저장된 답변과 원문을 대조해 적는다 (eval/reports/06_정확성_판정.md).

    cd rag-service && PYTHONPATH=. ../.venv/bin/python eval/accuracy_eval.py eval/results/accuracy_run.json
"""
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from rag import generator, stores  # noqa: E402
from rag.chain import answer  # noqa: E402
from rag.schema import RagRequest  # noqa: E402

stores.load_all()
reasons = []
_review = generator._review_result


def _record(reason, *args, **kwargs):
    reasons.append(reason)
    return _review(reason, *args, **kwargs)


generator._review_result = _record

items = json.loads((Path(__file__).resolve().parent / "accuracy_set.json").read_text(encoding="utf-8"))["items"]
if len(sys.argv) > 2:   # 일부 문항만: ... accuracy_eval.py <결과.json> A13,X01
    items = [i for i in items if i["id"] in sys.argv[2].split(",")]
out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "eval/results/accuracy_run.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
rows = []
for item in items:
    reasons.clear()
    for attempt in range(3):   # 모델 서버 일시 장애만 다시 시도한다
        try:
            res = answer(RagRequest(question=item["q"], topic=item["topic"], language="ko",
                                    equipment_id=item.get("equipment_id"), product_id=item.get("product_id")))
            break
        except generator.GenerationUnavailable:
            time.sleep(20)
    else:
        print("⚠", item["id"], "모델 서버 연결 실패")
        continue
    got = "answer" if res.sources else "handoff"
    rows.append({**item, "got": got, "reasons": list(reasons), "needs_review": res.needs_review,
                 "latency_ms": res.latency_ms, "answer": res.answer,
                 "sources": [f"{s.doc_id} {s.section}" for s in res.sources]})
    print(("✅" if got == item["expect"] else "❌"), item["id"], got, reasons[-1:] if got != item["expect"] else "", flush=True)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
