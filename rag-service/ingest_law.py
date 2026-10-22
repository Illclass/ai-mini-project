#!/usr/bin/env python3
"""법령 텍스트/PDF -> 조(條) 단위 청킹 -> 메타데이터 부착 -> FAISS 적재.

메타데이터(팀 합의안):
  필수: law_name / article_no / source_url / doc_type / chunk_id
  권장: article_title / effective_date
  선택: paragraph (긴 조를 항 단위로 나눴을 때만)

사용 예:
  # 1) 청킹 결과만 확인 (임베딩·API 호출 없음)
  python ingest_law.py --input laws/chemact.txt --law-name 화학물질관리법 --abbr chemact \
      --effective-date 2025-08-07 --source-url https://www.law.go.kr/ --dry-run

  # 2) 적재 (서버가 읽는 faiss_db/pdf 에 저장, 기존 인덱스에 추가하려면 --append)
  python ingest_law.py --input laws/chemact.txt --law-name 화학물질관리법 --abbr chemact \
      --effective-date 2025-08-07 --source-url https://www.law.go.kr/ --append
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚"

# 조 머리말: 줄 처음의 "제15조(제목)" 또는 "제15조의2(제목)" 또는 "제5조 삭제".
# 본문 중 "제2조제3호..." 같은 참조가 줄 처음에 와도 머리말로 오인하지 않도록
# 반드시 (제목) 또는 '삭제'가 바로 뒤따를 때만 인정한다.
ARTICLE_RE = re.compile(
    r"^[ \t]*제(\d+)조(?:의(\d+))?[ \t]*(?:\(([^)\n]+)\)|(삭제))",
    re.M,
)
APPENDIX_RE = re.compile(r"^[ \t]*(부칙|별표\s*\d*|별지\s*제?\d*호?\s*서식)", re.M)


def read_input(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader  # 지연 import (txt만 쓸 땐 불필요)

        reader = PdfReader(str(path))
        return "\n".join(t for p in reader.pages if (t := p.extract_text()))
    return path.read_text(encoding="utf-8")


def cut_appendix(text: str) -> str:
    """본칙만 남긴다: 첫 '부칙' / '별표' 줄부터 끝까지 제외."""
    m = APPENDIX_RE.search(text)
    return text[: m.start()] if m else text


def split_articles(text: str):
    heads = list(ARTICLE_RE.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.start():end].strip()
        no, sub, title, deleted = m.group(1), m.group(2), m.group(3), m.group(4)
        yield {
            "no": int(no),
            "sub": int(sub) if sub else 0,
            "title": (title or "").strip(),
            "deleted": bool(deleted),
            "body": body,
        }


def split_paragraphs(body: str):
    """긴 조를 ①②③ 단위로 쪼갠다. (번호, 텍스트) 목록 반환."""
    idx = [m.start() for m in re.finditer(f"[{CIRCLED}]", body)]
    if len(idx) < 2:
        return None
    parts = []
    # 첫 ① 앞의 머리(조 제목 줄)는 ① 항에 붙인다.
    bounds = [0] + idx[1:] + [len(body)]
    for a, b in zip(bounds, bounds[1:]):
        chunk = body[a:b].strip()
        m = re.search(f"[{CIRCLED}]", chunk)
        num = CIRCLED.index(m.group(0)) + 1 if m else 0
        parts.append((num, chunk))
    return parts


def build_chunks(text, law_name, abbr, effective_date, source_url, doc_type, max_chars):
    text = cut_appendix(text)
    chunks = []
    for art in split_articles(text):
        if art["deleted"]:
            continue
        article_no = f"제{art['no']}조" + (f"의{art['sub']}" if art["sub"] else "")
        art_key = f"{art['no']}" + (f"_{art['sub']}" if art["sub"] else "")
        head = f"[{law_name} {article_no}({art['title']})]"
        paras = split_paragraphs(art["body"]) if len(art["body"]) > max_chars else None

        pieces = paras if paras else [(0, art["body"])]
        for num, piece in pieces:
            meta = {
                "law_name": law_name,
                "article_no": article_no,
                "article_title": art["title"],
                "paragraph": str(num) if num else "",
                "effective_date": effective_date,
                "source_url": source_url,
                "doc_type": doc_type,
                "chunk_id": f"{abbr}-{art_key}-{num}",
            }
            # 임베딩은 page_content만 보므로, 법령명·조·제목을 본문 앞에 붙인다.
            content = f"{head}\n{piece}"
            chunks.append({"page_content": content, "metadata": meta})
    return chunks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="법령 .txt 또는 .pdf")
    ap.add_argument("--law-name", required=True)
    ap.add_argument("--abbr", required=True, help="chunk_id용 약칭 (영문 소문자, 예: chemact)")
    ap.add_argument("--effective-date", default="", help="YYYY-MM-DD")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--doc-type", default="law", choices=["law", "guide", "web"])
    ap.add_argument("--max-chars", type=int, default=1200, help="이보다 긴 조는 항(①②) 단위로 분할")
    ap.add_argument("--out", default="faiss_db/pdf", help="서버가 읽는 경로(기본 faiss_db/pdf)")
    ap.add_argument("--append", action="store_true", help="기존 인덱스에 추가")
    ap.add_argument("--dry-run", action="store_true", help="청킹 결과만 출력, 임베딩/저장 안 함")
    args = ap.parse_args()

    text = read_input(Path(args.input))
    chunks = build_chunks(
        text, args.law_name, args.abbr, args.effective_date,
        args.source_url, args.doc_type, args.max_chars,
    )
    if not chunks:
        sys.exit("조(條)를 하나도 찾지 못했습니다. 텍스트에 '제N조(제목)' 형식이 있는지 확인하세요.")

    ids = [c["metadata"]["chunk_id"] for c in chunks]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        print(f"[경고] chunk_id 중복: {sorted(dup)}", file=sys.stderr)

    print(f"조 단위 청크 {len(chunks)}개 생성")
    for c in chunks[:5 if not args.dry_run else len(chunks)]:
        print("-" * 60)
        print(json.dumps(c["metadata"], ensure_ascii=False))
        print(c["page_content"][:200].replace("\n", " ⏎ ") + (" ..." if len(c["page_content"]) > 200 else ""))

    if args.dry_run:
        print("\n(dry-run: 저장하지 않았습니다)")
        return

    from dotenv import load_dotenv
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    from langchain_openai import OpenAIEmbeddings

    load_dotenv(Path(__file__).resolve().parent / ".env")
    docs = [Document(page_content=c["page_content"], metadata=c["metadata"]) for c in chunks]
    emb = OpenAIEmbeddings()

    if args.append and os.path.exists(os.path.join(args.out, "index.faiss")):
        store = FAISS.load_local(args.out, emb, allow_dangerous_deserialization=True)
        store.add_documents(docs)
    else:
        store = FAISS.from_documents(docs, emb)
    os.makedirs(args.out, exist_ok=True)
    store.save_local(args.out)
    print(f"\n저장 완료: {args.out} (이번에 {len(docs)}개 청크). 서버를 재시작하면 반영됩니다.")


if __name__ == "__main__":
    main()
