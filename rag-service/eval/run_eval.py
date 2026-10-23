"""평가 — 담당: 김규빈 (검색 지표) · 박진근 (생성 지표)

questions.json 항목:
    id, category, question, language, topic, product_id, equipment_id(선택),
    expected_answer, expected_sources [{doc_id, section}],
    expected_behavior: "answer" | "not_found" | "handoff"
    (다국어 문항은 base = 기준 한국어 문항 ID)

expected_sources.section 비교 규칙 (청크를 나누는 단위가 문서마다 달라서):
    법령   "제52조" · "제2조 제2호"  → 조 번호(제N조)가 같으면 적중
    MSDS  "8"                    → MSDS 항목 번호가 같으면 적중
    지침   "13.4" · "2"            → 절 번호가 같거나 그 아래 절이면 적중
    ""                           → doc_id 만 같으면 적중
기대 근거가 여러 개면 하나라도 상위 k 안에 있으면 적중으로 본다.

실행 (rag-service/ 에서)
    python -m eval.run_eval                                  # 지금 인덱스(faiss_db/)로 검색 평가
    python -m eval.run_eval --models ada-002,3-small,3-large,bge-m3 --build --translate both
                                                             # 임베딩 모델 비교 (faiss_db/eval/<모델>/ 에 인덱스 생성)
    python -m eval.run_eval --full                           # 답변까지 생성해 handoff·찾을 수 없음 판정 (LLM 비용)
"""
import argparse
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent          # rag-service/
load_dotenv(ROOT / ".env")

from rag import stores                                 # noqa: E402
from rag.embeddings import get_embeddings, model_name  # noqa: E402
from rag.products import resolve_product_id            # noqa: E402
from rag.retriever import retrieve                     # noqa: E402
from rag.schema import INDEX_DIRS, TOPICS              # noqa: E402

KS = (1, 3, 5)
MODEL_ALIASES = {
    "ada-002": "text-embedding-ada-002",
    "3-small": "text-embedding-3-small",
    "3-large": "text-embedding-3-large",
    "bge-m3": "bge-m3",
}
ARTICLE_RE = re.compile(r"제\d+조(?:의\d+)?")


def load_questions(path: str = "eval/questions.json") -> List[dict]:
    """평가셋 로드."""
    with open(ROOT / path, encoding="utf-8") as f:
        return json.load(f)


def section_matches(meta: dict, expected: str) -> bool:
    """청크 메타데이터가 기대 section 과 맞는가 (모듈 설명의 비교 규칙)."""
    if not expected:
        return True
    if meta.get("doc_type") == "msds":
        return str(meta.get("msds_section_no", "")) == expected.rstrip(".")
    art = ARTICLE_RE.match(expected)
    if art:
        return (meta.get("article_no") or "") == art.group(0)
    head = (meta.get("section") or "").split(" ")[0]
    return head == expected or head.startswith(expected + ".")


def first_hit_rank(hits: List[dict], expected_sources: List[dict]) -> Optional[int]:
    """기대 근거가 처음 나온 순위 (1부터). 없으면 None."""
    for rank, h in enumerate(hits, start=1):
        meta = h["metadata"]
        for exp in expected_sources:
            if meta.get("doc_id") == exp["doc_id"] and section_matches(meta, exp.get("section", "")):
                return rank
    return None


def hit_at_k(hits: List[dict], expected_sources: List[dict], k: int = 5) -> bool:
    """검색 적중: 기대 근거(doc_id + section)가 상위 k 개 hits 안에 있는가."""
    rank = first_hit_rank(hits, expected_sources)
    return rank is not None and rank <= k


def judge_behavior(response: dict, expected_behavior: str) -> bool:
    """생성 판정: handoff · "찾을 수 없음" 이 기대와 맞는가."""
    not_found = not response.get("sources")
    if expected_behavior == "handoff":
        return bool(response.get("handoff"))
    if expected_behavior == "not_found":
        return not_found
    return not not_found and not response.get("handoff")


# ---------------------------------------------------------------------------
# 임베딩 모델별 인덱스 (비교 평가용)
# ---------------------------------------------------------------------------
def eval_index_dir(alias: str, topic: str) -> Path:
    return ROOT / "faiss_db" / "eval" / alias / Path(INDEX_DIRS[topic]).name


def build_eval_indexes(alias: str) -> None:
    """지금 인덱스(faiss_db/)의 청크를 그대로 가져와 다른 모델로 다시 임베딩한다 (청킹이 같아야 공정한 비교)."""
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document

    emb = None
    for topic in TOPICS:
        out = eval_index_dir(alias, topic)
        if (out / "index.faiss").exists():
            print(f"  [{alias}] {topic}: 이미 있음 → 건너뜀")
            continue
        emb = emb or get_embeddings(MODEL_ALIASES[alias])
        src = FAISS.load_local(str(ROOT / INDEX_DIRS[topic]), get_embeddings(),
                               allow_dangerous_deserialization=True)
        docs = [Document(page_content=d.page_content, metadata=d.metadata) for d in src.docstore._dict.values()]
        t0 = time.time()
        store = FAISS.from_documents(docs, emb)
        out.mkdir(parents=True, exist_ok=True)
        store.save_local(str(out))
        print(f"  [{alias}] {topic}: 청크 {len(docs)}개 임베딩 {time.time() - t0:.0f}초")


def use_indexes(alias: Optional[str]) -> None:
    """stores 에 평가할 인덱스를 올린다. alias=None 이면 지금 서비스 인덱스(faiss_db/)."""
    from langchain_community.vectorstores import FAISS

    stores._STORES.clear()
    if alias is None:
        stores.load_all()
        return
    emb = get_embeddings(MODEL_ALIASES[alias])
    for topic in TOPICS:
        stores._STORES[topic] = FAISS.load_local(str(eval_index_dir(alias, topic)), emb,
                                                 allow_dangerous_deserialization=True)


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def run_retrieval(questions: List[dict], translate: bool, k: int) -> List[dict]:
    """질문마다 retrieve → 첫 적중 순위 · 검색 시간. translate=False 면 외국어 질문도 번역 없이 검색."""
    rows = []
    for q in questions:
        if not q["expected_sources"]:
            continue
        lang = q["language"] if translate else "ko"
        t0 = time.time()
        pid = resolve_product_id(q["question"], q["topic"], lang, q.get("product_id"), q.get("equipment_id"))
        hits = retrieve(q["question"], q["topic"], pid, k=k, language=lang, equipment_id=q.get("equipment_id"))
        ms = (time.time() - t0) * 1000
        rows.append({"id": q["id"], "category": q.get("category", ""), "language": q["language"],
                     "rank": first_hit_rank(hits, q["expected_sources"]), "ms": ms,
                     "top": [f"{h['metadata'].get('doc_id')} {h['metadata'].get('section', '')}" for h in hits[:3]]})
    return rows


def summarize(rows: List[dict]) -> Dict[str, float]:
    n = len(rows) or 1
    out = {f"hit@{k}": sum(1 for r in rows if r["rank"] and r["rank"] <= k) / n for k in KS}
    out["MRR"] = sum(1 / r["rank"] for r in rows if r["rank"]) / n
    out["ms"] = sum(r["ms"] for r in rows) / n
    out["n"] = len(rows)
    return out


def group_by(rows: List[dict], key: str) -> Dict[str, Dict[str, float]]:
    groups = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r)
    return {g: summarize(rs) for g, rs in groups.items()}


def fmt(s: Dict[str, float]) -> str:
    return " | ".join([f"{s[f'hit@{k}']:.0%}" for k in KS] + [f"{s['MRR']:.2f}", f"{s['ms']:.0f}"])


def run_full(questions: List[dict]) -> None:
    """chain.answer 로 답변까지 만들어 handoff · 찾을 수 없음 판정 (LLM 호출 비용 발생)."""
    from rag.chain import answer
    from rag.schema import RagRequest

    ok = 0
    for q in questions:
        req = RagRequest(question=q["question"], topic=q["topic"], product_id=q.get("product_id"),
                         equipment_id=q.get("equipment_id"), language=q["language"])
        resp = answer(req).model_dump()
        good = judge_behavior(resp, q["expected_behavior"])
        ok += good
        print(f"{'✅' if good else '❌'} {q['id']:<14} 기대={q['expected_behavior']:<9} "
              f"handoff={resp['handoff']} 근거={len(resp['sources'])} {resp['latency_ms']}ms")
    print(f"\n동작 정확도: {ok}/{len(questions)} = {ok / max(len(questions), 1):.0%}")


def main() -> None:
    """질문마다 retrieve → hit_at_k (--full 이면 chain.answer → judge_behavior). 결과표 출력·저장."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", default="eval/questions.json")
    ap.add_argument("--models", default="", help=f"쉼표로 구분: {','.join(MODEL_ALIASES)} (비우면 지금 인덱스)")
    ap.add_argument("--build", action="store_true", help="모델별 평가 인덱스가 없으면 만든다 (임베딩 비용)")
    ap.add_argument("--translate", default="on", choices=["on", "off", "both"], help="외국어 질문 한국어 번역")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--full", action="store_true", help="답변 생성까지 평가 (LLM 비용)")
    args = ap.parse_args()

    questions = load_questions(args.questions)
    if args.full:
        use_indexes(None)
        run_full(questions)
        return

    aliases = [a.strip() for a in args.models.split(",") if a.strip()] or [None]
    modes = {"on": [True], "off": [False], "both": [False, True]}[args.translate]
    results = []
    for alias in aliases:
        if alias and args.build:
            build_eval_indexes(alias)
        use_indexes(alias)
        for tr in modes:
            label = f"{alias or model_name()} / {'번역' if tr else '번역 없음'}"
            print(f"평가 중: {label}")
            rows = run_retrieval(questions, tr, args.k)
            results.append({"label": label, "rows": rows, "all": summarize(rows),
                            "category": group_by(rows, "category"), "language": group_by(rows, "language")})

    head = "| 조합 | hit@1 | hit@3 | hit@5 | MRR | 검색 ms |\n|---|---|---|---|---|---|"
    lines = [f"# 검색 평가 결과 ({datetime.now():%Y-%m-%d %H:%M})", "",
             f"문항 {results[0]['all']['n']}개 (근거가 있는 문항만), top_k={args.k}", "", "## 전체", head]
    lines += [f"| {r['label']} | {fmt(r['all'])} |" for r in results]
    for key, title in (("language", "언어별 hit@5"), ("category", "유형별 hit@5")):
        groups = sorted({g for r in results for g in r[key]})
        lines += ["", f"## {title}", "| 조합 | " + " | ".join(groups) + " |", "|---" * (len(groups) + 1) + "|"]
        lines += [f"| {r['label']} | " + " | ".join(f"{r[key][g]['hit@5']:.0%}" if g in r[key] else "-"
                                                    for g in groups) + " |" for r in results]
    lines += ["", "## 놓친 문항 (상위 5개 안에 기대 근거 없음)"]
    for r in results:
        missed = [x for x in r["rows"] if not (x["rank"] and x["rank"] <= 5)]
        lines.append(f"- **{r['label']}** ({len(missed)}개): " +
                     ", ".join(f"{x['id']} → {x['top'][0] if x['top'] else '결과 없음'}" for x in missed))
    report = "\n".join(lines)
    print("\n" + report)

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M}"
    (out_dir / f"{stamp}_retrieval.md").write_text(report + "\n", encoding="utf-8")
    (out_dir / f"{stamp}_retrieval.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n저장: eval/results/{stamp}_retrieval.md")


if __name__ == "__main__":
    main()
