"""답변 평가 (실제 LLM 호출, 비용 발생) — 담당: 김규빈

질문마다 chain.answer → 답변/보류/안내를 기대값과 비교하고, 보류면 사유와 그 사유를 낸 코드 줄을 기록한다.
검색 평가(run_eval.py)와 달리 생성·검증까지 전부 돈다. 결과: eval/results/answer_<라벨>.json

    cd rag-service
    PYTHONPATH=. ../.venv/bin/python eval/answer_eval.py              # .env 의 LLM_MODEL (비우면 gpt-6-luna)
    PYTHONPATH=. ../.venv/bin/python eval/answer_eval.py gpt-4o 4o    # 모델·라벨 지정
"""
import inspect, json, os, sys, time
from collections import Counter
from dotenv import load_dotenv; load_dotenv(".env")
if len(sys.argv) > 1 and sys.argv[1] != "-": os.environ["LLM_MODEL"] = sys.argv[1]
label = sys.argv[2] if len(sys.argv) > 2 else "run"
from rag import stores, generator; stores.load_all()
from rag.chain import answer
from rag.schema import RagRequest
from eval.run_eval import load_questions

where = []
orig = generator._review_result
def traced(reason, *a, **k):
    fr = inspect.stack()[2] if inspect.stack()[1].function == "review" else inspect.stack()[1]
    where.append(f"{reason}@{fr.function}:{fr.lineno}")
    return orig(reason, *a, **k)
generator._review_result = traced

C, L = "chemical_safety", "serious_accident_law"
cases = [  # (id, 질문, topic, 언어, product_id, equipment_id, 기대: answer/handoff/guide)
 ("S-LQ기준", "중대재해법의 기준은?", L, "ko", None, None, "answer"),
 ("S-Q09작업중지", "심각한 사고 위험을 발견하면 작업을 멈추고 대피해도 되나요?", L, "ko", None, None, "answer"),
 ("S-판단요구", "우리 회사에서 사망사고가 났는데 대표이사가 처벌받나요?", L, "ko", None, None, "handoff"),
 ("S-Q01불산", "불산 취급 시 주의할 점과 필요한 보호구는?", C, "ko", None, None, "answer"),
 ("S-Q03과수", "과산화수소 취급·보관 시 피해야 할 조건은?", C, "ko", None, None, "answer"),
 ("S-Q04암모니아", "암모니아수 작업 시 환기와 보호구 확인사항은?", C, "ko", None, None, "answer"),
 ("S-Q05보관", "화학물질은 어떤 용기·온도로 보관하고 어떤 물질과 분리하나요?", C, "ko", None, None, "answer"),
 ("S-Q06기한", "사용기한이나 개봉 후 사용기한은 어떻게 확인하나요?", C, "ko", None, None, "answer"),
 ("S-장비만", "보호구는 무엇을 착용해야 하나요?", C, "ko", None, "DEMO-WET-01", "guide"),
 ("S-장비제품", "약품 공급 용기를 교체하기 전에 무엇을 확인해야 하나요?", C, "ko", "sigma-695068", "DEMO-WET-01", "answer"),
 ("S-비상", "TMAH가 작업복에 튀었어요", C, "ko", None, None, "handoff"),
 ("S-vi법령", "Tai nạn lao động nghiêm trọng là gì?", L, "vi", None, None, "answer"),
]
qs = {q["id"]: q for q in load_questions()}
for qid in ["C02","C04","C05","C06","C08","C09","C10","C11","C12","C13","C14","C15","C17","LQ02","LQ03","LQ04","LQ06","LQ07","LQ12","LQ13",
            "M-C01-zh","M-C01-en","M-C05-vi","M-LQ01-km","M-LQ11-zh"]:
    q = qs[qid]; cases.append((qid, q["question"], q["topic"], q["language"], q.get("product_id"), q.get("equipment_id"),
                               "handoff" if qid in ("C05", "M-C05-vi") else "answer"))   # 눈에 들어감 = 비상 안내가 정답

rows, ok, t_all = [], Counter(), 0
for cid, q, topic, lang, pid, eq, expect in cases:
    where.clear(); t = time.time()
    try:
        r = answer(RagRequest(question=q, topic=topic, language=lang, product_id=pid, equipment_id=eq)); err = ""
    except Exception as e:
        r, err = None, f"{type(e).__name__}"
    dt = time.time() - t; t_all += dt
    got = "error" if r is None else ("answer" if r.sources else ("guide" if "선택해 주세요" in r.answer else "handoff"))
    good = got == expect
    ok[good] += 1
    rows.append({"id": cid, "expect": expect, "got": got, "good": good, "sec": round(dt, 1), "why": where[-1] if where else err,
                 "handoff": None if r is None else r.handoff, "answer": "" if r is None else r.answer[:300]})
    print(f"{'✅' if good else '❌'} {cid:14} 기대={expect:7} 결과={got:7} {dt:4.1f}s {'' if good else (where[-1] if where else err)}")
n = len(rows); ans = [r for r in rows if r["expect"] == "answer"]
print(f"\n== [{label}] 모델={os.getenv('LLM_MODEL') or 'gpt-6-luna(기본)'} 기대대로 {ok[True]}/{n} | 답변 기대 문항 중 답변 {sum(r['got']=='answer' for r in ans)}/{len(ans)} | 평균 {t_all/n:.1f}s")
print("   실패 위치:", dict(Counter(r["why"] for r in rows if not r["good"])))
os.makedirs("eval/results", exist_ok=True)
json.dump(rows, open(f"eval/results/answer_{label}.json", "w"), ensure_ascii=False, indent=1)