"""FAISS docstore에서 '인접 조항' 목록을 뽑아 프론트용 related.json 을 만든다.
임베딩 모델·API 키 없이 index.pkl 만 읽는다. 사용법: python export_related.py"""
import json, pickle, re, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "related.json"
SNIP = 150


def load(path):
    with open(path, "rb") as f:
        store, ids = pickle.load(f)          # (InMemoryDocstore, index_to_id)
    docs = store._dict
    return [docs[ids[i]] for i in range(len(ids))]


def clean(text):
    text = re.sub(r"^\[[^\]]*\]\s*", "", text)   # MSDS 머리말 [제목 | 물질 | 항목]
    return re.sub(r"\s+", " ", text).strip()[:SNIP]


related = {}
for name in ("law", "msds"):
    p = Path(__file__).resolve().parent / "faiss_db" / name / "index.pkl"
    for d in load(p):
        m = d.metadata
        doc_id, section = m.get("doc_id"), m.get("section", "")
        if not doc_id:
            continue
        arr = related.setdefault(doc_id, [])
        if arr and arr[-1]["s"] == section:      # 같은 조항이 여러 조각이면 하나로
            continue
        arr.append({"s": section, "t": clean(d.page_content)})

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(related, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{OUT} · 문서 {len(related)}개 · 항목 {sum(len(v) for v in related.values())}개 · {OUT.stat().st_size//1024}KB")
