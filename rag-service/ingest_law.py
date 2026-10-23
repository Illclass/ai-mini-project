#!/usr/bin/env python3
"""법령·가이드 PDF/텍스트 → 구조 단위 청킹 → 메타데이터 부착 → FAISS 적재 — 담당: 윤서진

메타데이터 키는 rag/schema.py 의 ChunkMeta 를 따른다 (이름을 바꾸지 않는다).

모드(--mode)
  law   법령. '제N조(제목)' 조 단위, 긴 조는 ①②항 단위로 분할. 부칙 제외.   → topic=serious_accident_law → faiss_db/law
  guide KOSHA GUIDE 등 지침. '5. 제목' / '5.5 제목' 번호 제목 단위.            → topic=chemical_safety     → faiss_db/msds
  (MSDS 는 ingest/ingest_msds.py)

사용 예 (rag-service/ 에서. 먼저 --dry-run 으로 청킹 결과만 확인)
  python ingest_law.py --input data/laws/중대재해처벌법.pdf --doc-id L2 \\
      --law-name "중대재해 처벌 등에 관한 법률" --effective-date 2022-01-27 \\
      --source-url https://www.law.go.kr --dry-run
  # 중대재해처벌법은 제2조(정의)를 호 단위로 (제2조 제2호 …):
  python ingest_law.py --input data/laws/L2_중대재해처벌법.pdf --doc-id L2 --law-name "중대재해 처벌 등에 관한 법률" \\
      --effective-date 2022-01-27 --split-ho 2 --dry-run
  # 산업안전보건법은 MSDS 관련 조문만 (제108~116조):
  python ingest_law.py --input data/laws/산안법.pdf --doc-id L1 --law-name 산업안전보건법 \\
      --effective-date 2026-08-01 --only 110-116 --append
  # 지침:
  python ingest_law.py --mode guide --input data/laws/K-1.pdf --doc-id K2 \\
      --law-name "KOSHA GUIDE K-1-2023" --effective-date 2023-08-01 --append
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

# rag-service/ 를 import 경로에 넣는다 (이 파일이 rag-service/ 에 있든 rag-service/ingest/ 에 있든 동작)
_HERE = Path(__file__).resolve().parent
ROOT = _HERE if (_HERE / "rag").is_dir() else _HERE.parent
sys.path.insert(0, str(ROOT))

from rag.schema import (  # noqa: E402
    DOC_TYPE_GUIDE, DOC_TYPE_LAW, INDEX_DIRS, TOPIC_CHEMICAL, TOPIC_LAW, make_chunk_id,
)

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚"

# 조 머리말: 줄 처음의 "제15조(제목)" / "제15조의2(제목)" / "제5조 삭제".
# 본문 중 "제2조제3호..." 같은 참조가 줄 처음에 와도 오인하지 않도록 (제목) 또는 '삭제'가 바로 뒤따를 때만 인정.
ARTICLE_RE = re.compile(r"^[ \t]*제(\d+)조(?:의(\d+))?[ \t]*(?:\(([^)\n]+)\)|(삭제))", re.M)
# 부칙: '부칙 <제17907호, 2021. 1. 26.>' 처럼 부칙 뒤에 '<' 또는 '(' 가 바로 오는 줄만.
# ('별표'로 자르면 본문 줄바꿈으로 줄 처음에 온 '별표 2에서…'에서 법령이 통째로 잘린다)
APPENDIX_RE = re.compile(r"^[ \t]*부칙[ \t]*[<(＜（]", re.M)
HEADER_RE = re.compile(r"^[ \t]*법제처[ \t]+\d+[ \t]+국가법령정보센터[ \t]*$")
CHAPTER_RE = re.compile(r"^[ \t]*제\d+[장절편][ \t]")
UPCOMING_RE = re.compile(r"^[ \t]*\[시행일[ \t]*:[^\]]*\][ \t]*제\d+조.*$")   # 시행 예정 개정 표시

HO_RE = re.compile(r"^[ \t]*(\d{1,2})\.[ \t]+\S")   # 호: "1. ...", "2. ..." (줄 처음, 1부터 순서대로)

DUPLICATES = []   # 같은 조가 두 번 나온 경우(현행 + 시행 예정본)


def read_input(path: Path, layout: bool = False) -> str:
    if path.suffix.lower() == ".pdf":
        # 1순위: pdftotext (poppler). 일부 KOSHA PDF 는 pypdf 로 읽으면 띄어쓰기가 사라진다.
        import shutil
        import subprocess
        if shutil.which("pdftotext"):
            cmd = ["pdftotext"] + (["-layout"] if layout else []) + [str(path), "-"]
            r = subprocess.run(cmd,
                               capture_output=True, text=True, encoding="utf-8")
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.replace("\f", "\n")
        print("[경고] pdftotext 가 없어 pypdf 로 읽습니다. 일부 PDF 는 띄어쓰기가 깨질 수 있어요 "
              "(맥: brew install poppler)", file=sys.stderr)
        from pypdf import PdfReader  # 지연 import (txt 만 쓸 땐 불필요)
        reader = PdfReader(str(path))
        return "\n".join(t for p in reader.pages if (t := p.extract_text()))
    return path.read_text(encoding="utf-8")


def clean_noise(text: str) -> str:
    """국가법령정보센터 PDF 쪽 머리글, 장·절 제목, 시행예정 표시 줄을 제거한다."""
    out, skip_next = [], False
    for ln in text.splitlines():
        if skip_next:           # 머리글 바로 다음 줄 = 반복되는 법령명
            skip_next = False
            continue
        if HEADER_RE.match(ln):
            skip_next = True
            continue
        if CHAPTER_RE.match(ln) or UPCOMING_RE.match(ln):
            continue
        out.append(ln)
    return "\n".join(out)


def cut_appendix(text: str) -> str:
    m = APPENDIX_RE.search(text)
    return text[: m.start()] if m else text


def parse_only(spec: str):
    """'31-34,299,420-515' -> [(31,34),(299,299),(420,515)]"""
    ranges = []
    for part in filter(None, (p.strip() for p in (spec or "").split(","))):
        a, _, b = part.partition("-")
        ranges.append((int(a), int(b or a)))
    return ranges


def in_ranges(no: int, ranges) -> bool:
    return not ranges or any(a <= no <= b for a, b in ranges)


def split_long(text: str, max_chars: int, overlap: int = 100):
    """max_chars 를 넘는 글을 줄바꿈 경계에서 겹침을 두고 나눈다."""
    if len(text) <= max_chars:
        return [text]
    parts, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            nl = text.rfind("\n", start + max_chars // 2, end)
            end = nl if nl != -1 else end
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]


def split_articles(text: str):
    heads = list(ARTICLE_RE.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        no, sub, title, deleted = m.group(1), m.group(2), m.group(3), m.group(4)
        yield {
            "no": int(no),
            "sub": int(sub) if sub else 0,
            "title": (title or "").strip(),
            "deleted": bool(deleted),
            "body": text[m.start():end].strip(),
        }


def split_paragraphs(body: str):
    """긴 조를 ①②③ 단위로 쪼갠다. (번호, 텍스트) 목록 반환."""
    idx = [m.start() for m in re.finditer(f"[{CIRCLED}]", body)]
    if len(idx) < 2:
        return None
    parts = []
    bounds = [0] + idx[1:] + [len(body)]
    for a, b in zip(bounds, bounds[1:]):
        chunk = body[a:b].strip()
        m = re.search(f"[{CIRCLED}]", chunk)
        num = CIRCLED.index(m.group(0)) + 1 if m else 0
        parts.append((num, chunk))
    return parts


def parse_ids(spec: str):
    """'2,5' -> {2,5}.  'all' -> None(모든 조).  빈 값 -> 빈 집합(호 분할 안 함)"""
    spec = (spec or "").strip()
    if spec.lower() == "all":
        return None
    return {int(x) for x in spec.split(",") if x.strip()}


def split_ho(text: str):
    """조/항 본문을 호 단위로 쪼갠다. 1호부터 순서대로 이어지는 '1. ' 줄만 호로 인정(본문 번호 오인 방지).
    반환: (머리말, [(호 번호, 호 본문)]) / 호가 2개 미만이면 None"""
    starts, expect, off = [], 1, 0
    for ln in text.split("\n"):
        m = HO_RE.match(ln)
        if m and int(m.group(1)) == expect:
            starts.append((expect, off))
            expect += 1
        off += len(ln) + 1
    if len(starts) < 2:
        return None
    intro = text[: starts[0][1]].strip()
    items = []
    for i, (n, st) in enumerate(starts):
        en = starts[i + 1][1] if i + 1 < len(starts) else len(text)
        items.append((n, text[st:en].strip()))
    return intro, items


def common_meta(args, section: str, chunk_id: str) -> dict:
    """schema.ChunkMeta 공통 키 (모든 청크 필수)."""
    return {
        "doc_id": args.doc_id,
        "doc_type": args.doc_type,
        "topic": args.topic,
        "title": args.law_name,
        "section": section,
        "source_url": args.source_url,
        "chunk_id": chunk_id,
        "effective_date": args.effective_date,
    }


def build_law_chunks(text, args):
    ranges = parse_only(args.only)
    ho_ids = parse_ids(args.split_ho)
    text = cut_appendix(clean_noise(text))
    seen, chunks = set(), []
    for art in split_articles(text):
        if art["deleted"] or not in_ranges(art["no"], ranges):
            continue
        key = (art["no"], art["sub"])
        article_no = f"제{art['no']}조" + (f"의{art['sub']}" if art["sub"] else "")
        if key in seen:    # 같은 조의 두 번째 등장 = 시행 예정 개정본 → 현행(첫 번째)만 사용
            DUPLICATES.append(article_no)
            continue
        seen.add(key)
        art_key = f"{art['no']}" + (f"_{art['sub']}" if art["sub"] else "")
        head = f"[{args.law_name} {article_no}({art['title']})]"
        by_ho = ho_ids is None or art["no"] in ho_ids
        paras = split_paragraphs(art["body"]) if (by_ho or len(art["body"]) > args.max_chars) else None
        for num, piece in (paras if paras else [(0, art["body"])]):
            base_section = f"{article_no} 제{num}항" if num else article_no
            base_part = f"{art_key}-{num}" if num else art_key          # 예) L2-2 (제2조), L2-4-1 (제4조 1항)
            pieces = [("", 0, piece)]
            ho = split_ho(piece) if by_ho else None
            if ho:                                                       # 호 단위: "제2조 제2호", "제4조 제1항 제3호"
                intro, items = ho
                pieces = [(f"{intro}\n" if intro else "", n, txt) for n, txt in items]
            for lead, ho_no, txt in pieces:
                section = f"{base_section} 제{ho_no}호" if ho_no else base_section
                part = f"{base_part}-h{ho_no}" if ho_no else base_part   # 예) L2-2-h2
                meta = common_meta(args, section, make_chunk_id(args.doc_id, part)) | {
                    "law_name": args.law_name,
                    "article_no": article_no,
                    "article_title": art["title"],
                    "paragraph": str(num) if num else "",
                }
                # 호 청크는 앞에 조 제목과 머리말(예: "…다음 각 목의 어느 하나에 해당하는…")을 붙여 뜻이 남게 한다
                chunks.append({"page_content": f"{head}\n{lead}{txt}", "metadata": meta})
    return chunks


def numbered_sections(text, max_top, allow_sub):
    """번호 제목 줄을 '순서대로 증가하는 것만' 머리말로 인정한다 (본문 번호목록·표 번호 오인 방지).
    목차 줄(····· 점선)은 제외한다. 반환: [(번호문자열, 제목, 시작위치)]"""
    pat = re.compile(r"^[ \t]*(\d{1,2})(?:\.(\d{1,2}))?[.\s][ \t]*((?!.*··)[^\n]{2,80}?)[ \t]*$", re.M)
    out, last_top, last_sub = [], 0, 0
    for m in pat.finditer(text):
        top, sub, title = int(m.group(1)), m.group(2), m.group(3).strip()
        if re.match(r"\s*[·․]{3,}", text[m.end(): m.end() + 80]):   # 제목 다음 줄이 점선(·····) = 목차 줄
            continue
        if sub is None:
            if top == last_top + 1 and top <= max_top:
                out.append((str(top), title, m.start()))
                last_top, last_sub = top, 0
        elif allow_sub and top == last_top and int(sub) == last_sub + 1:
            out.append((f"{top}.{int(sub)}", title, m.start()))
            last_sub = int(sub)
    return out


def build_guide_chunks(text, args):
    text = clean_noise(text)
    secs = numbered_sections(text, max_top=30, allow_sub=True) or [("전체", args.law_name, 0)]
    chunks = []
    for i, (no, title, pos) in enumerate(secs):
        end = secs[i + 1][2] if i + 1 < len(secs) else len(text)
        body = text[pos:end].strip()
        head = f"[{args.law_name} {no} {title}]"
        for j, piece in enumerate(split_long(body, args.max_chars), start=1):
            if len(piece.strip().splitlines()) <= 1 and i + 1 < len(secs):   # 제목 한 줄뿐인 상위 절은 건너뜀(하위 절이 내용을 가짐)
                continue
            part = no.replace(".", "_") + (f"-{j}" if j > 1 else "")
            meta = common_meta(args, f"{no} {title}", make_chunk_id(args.doc_id, part))
            chunks.append({"page_content": f"{head}\n{piece}", "metadata": meta})
    return chunks


def build_chunks(text, args):
    return build_guide_chunks(text, args) if args.mode == "guide" else build_law_chunks(text, args)


def save_index(chunks, out_dir: Path, append: bool):
    """청크를 FAISS 에 저장한다. --append 면 기존 인덱스에 추가(chunk_id 가 겹치면 중단)."""
    from dotenv import load_dotenv
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    from langchain_openai import OpenAIEmbeddings

    load_dotenv(ROOT / ".env")
    docs = [Document(page_content=c["page_content"], metadata=c["metadata"]) for c in chunks]
    emb = OpenAIEmbeddings()
    if append and (out_dir / "index.faiss").exists():
        store = FAISS.load_local(str(out_dir), emb, allow_dangerous_deserialization=True)
        existing = {d.metadata.get("chunk_id") for d in store.docstore._dict.values()}
        clash = sorted(existing & {d.metadata["chunk_id"] for d in docs})
        if clash:
            sys.exit(f"이미 적재된 chunk_id 와 겹칩니다 ({len(clash)}개, 예: {clash[:3]}). "
                     f"같은 문서를 다시 넣으려면 {out_dir} 를 지우고 처음부터(--append 없이) 다시 적재하세요.")
        store.add_documents(docs)
    else:
        store = FAISS.from_documents(docs, emb)
    out_dir.mkdir(parents=True, exist_ok=True)
    store.save_local(str(out_dir))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help=".txt 또는 .pdf")
    ap.add_argument("--mode", default="law", choices=["law", "guide"])
    ap.add_argument("--doc-id", required=True, help='기획서 문서 ID 예) "L2" (chunk_id 앞부분이 된다)')
    ap.add_argument("--law-name", required=True, help="화면에 보일 문서명 (법령명/지침명) → title")
    ap.add_argument("--effective-date", default="", help="YYYY-MM-DD (시행일/개정일)")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--topic", default=None, choices=[TOPIC_LAW, TOPIC_CHEMICAL],
                    help="기본: law→serious_accident_law, guide→chemical_safety")
    ap.add_argument("--only", default="", help="law 모드: 포함할 조 번호 범위 예) 31-34,299,420-515")
    ap.add_argument("--split-ho", default="", help="law 모드: 호 단위로 나눌 조 번호 예) 2 또는 2,5 (all=모든 조). 비우면 조/항 단위")
    ap.add_argument("--max-chars", type=int, default=1200, help="이보다 긴 조/절은 분할")
    ap.add_argument("--out", default=None, help="기본: schema.INDEX_DIRS[topic] (rag-service/ 기준)")
    ap.add_argument("--append", action="store_true", help="기존 인덱스에 추가")
    ap.add_argument("--dry-run", action="store_true", help="청킹 결과만 출력, 임베딩/저장 안 함")
    args = ap.parse_args()
    args.doc_type = DOC_TYPE_GUIDE if args.mode == "guide" else DOC_TYPE_LAW
    args.topic = args.topic or (TOPIC_CHEMICAL if args.mode == "guide" else TOPIC_LAW)
    out_dir = Path(args.out) if args.out else ROOT / INDEX_DIRS[args.topic]

    chunks = build_chunks(read_input(Path(args.input)), args)
    if not chunks:
        sys.exit("구조 단위를 하나도 찾지 못했습니다. --mode 가 맞는지, 텍스트에 조 머리말/번호 제목이 있는지 확인하세요.")

    ids = [c["metadata"]["chunk_id"] for c in chunks]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        print(f"[경고] chunk_id 중복: {sorted(dup)[:10]}", file=sys.stderr)
    if DUPLICATES:
        print(f"[알림] 같은 조가 2번 나와 첫 번째(현행)만 사용: {len(DUPLICATES)}개 "
              f"(시행 예정 개정본 제외) 예) {DUPLICATES[:5]}", file=sys.stderr)

    print(f"[{args.mode}] 청크 {len(chunks)}개 생성 ({args.law_name}) → topic={args.topic}, 인덱스={out_dir}")
    show = chunks if args.dry_run and len(chunks) <= 40 else chunks[:5]
    for c in show:
        print("-" * 60)
        print(json.dumps(c["metadata"], ensure_ascii=False))
        print(c["page_content"][:200].replace("\n", " ⏎ ") + (" ..." if len(c["page_content"]) > 200 else ""))

    if args.dry_run:
        print("\n(dry-run: 저장하지 않았습니다)")
        return
    save_index(chunks, out_dir, args.append)
    print(f"\n저장 완료: {out_dir} (이번에 {len(chunks)}개 청크). 서버를 재시작하면 반영됩니다.")


if __name__ == "__main__":
    main()
