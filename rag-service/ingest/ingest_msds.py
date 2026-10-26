"""MSDS → 16개 항목 단위 청킹 → 메타데이터 부착 → FAISS 적재 — 담당: 윤서진

메타데이터 키는 rag/schema.py 의 ChunkMeta (공통 + MSDS 전용) 를 따른다.
원문 PDF 는 data/msds/, 인덱스는 schema.INDEX_DIRS[TOPIC_CHEMICAL].
법령 적재는 ingest_law.py (같은 사용법, 같은 --append / --dry-run).

사용 예 (rag-service/ 에서. 먼저 --dry-run 으로 16개 항목이 모두 나뉘는지 확인)
  python ingest/ingest_msds.py --input data/msds/sulfuric_acid_339741.pdf --doc-id D1 \\
      --product-id sigma-339741 --substance 황산 --supplier "Sigma-Aldrich Korea" \\
      --cas-no 7664-93-9 --revision-date 2026-07-14 --title "Sulfuric acid 339741 MSDS" \\
      --source-url https://www.sigmaaldrich.com/ --dry-run
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

# rag-service/ 와 이 파일의 폴더를 import 경로에 넣는다 (ingest_law.py 가 어느 쪽에 있어도 동작)
_HERE = Path(__file__).resolve().parent
ROOT = _HERE if (_HERE / "rag").is_dir() else _HERE.parent
for _p in (str(ROOT), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ingest_law import clean_noise, numbered_sections, read_input, save_index  # noqa: E402
from rag.schema import DOC_TYPE_MSDS, INDEX_DIRS, TOPIC_CHEMICAL, ChunkMeta, make_chunk_id  # noqa: E402


_PAGE_FOOTER = re.compile(
    r"(?m)^[ \t]*(?P<brand>SIGALD|Aldrich|Sigma-Aldrich|Millipore)-[ \t]*"
    r"(?P<product>[0-9A-Za-z.\-]+)[ \t]+쪽[ \t]+(?P<page>\d+)[ \t]*/[ \t]*(?P<total>\d+)[ \t]*\n"
    r"(?:[ \t]*\n)*[ \t]*The life science business of Merck operates as MilliporeSigma in[ \t]*\n"
    r"[ \t]*the US and Canada[ \t]*(?:\n|$)(?:[ \t]*\n)*\Z"
)


def remove_verified_page_footers(text: str) -> str:
    """Remove only a complete, consistent footer at every physical PDF page end.

    Page breaks must still be present. Missing/duplicate counters, mixed product
    IDs, partial branding or text after the footer leave the input unchanged.
    Safety text is never reconstructed, reordered or given new punctuation.
    """
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if len(pages) < 2:
        return text
    matches = [_PAGE_FOOTER.search(page) for page in pages]
    if (not all(matches)
            or any(int(match["page"]) != i + 1 or int(match["total"]) != len(pages)
                   for i, match in enumerate(matches))
            or len({(match["brand"], match["product"]) for match in matches}) != 1):
        return text
    return "\n".join(page[:match.start()] for page, match in zip(pages, matches))


def read_msds_input(path: Path) -> str:
    """Keep physical page boundaries until verified PDF furniture is removed."""
    if path.suffix.lower() != ".pdf":
        return read_input(path, layout=True)
    if shutil.which("pdftotext"):
        result = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                                capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0 and result.stdout.strip():
            return remove_verified_page_footers(result.stdout).replace("\f", "\n")
    from pypdf import PdfReader
    pages = [page.extract_text(extraction_mode="layout") or "" for page in PdfReader(str(path)).pages]
    return remove_verified_page_footers("\f".join(pages)).replace("\f", "\n")


def split_sections(text: str) -> List[dict]:
    """MSDS 본문을 1~16 항목으로 나눈다. [{"no": 8, "title": "노출방지 및 개인보호구", "body": ...}]
    '1.' 부터 순서대로 1씩 늘어나는 번호 제목만 항목 머리말로 인정한다
    (본문의 '0.2 mg/m3' 같은 숫자나 목차 점선 줄은 걸러진다)."""
    text = clean_noise(text)
    secs = numbered_sections(text, max_top=16, allow_sub=False)
    out = []
    for i, (no, title, pos) in enumerate(secs):
        end = secs[i + 1][2] if i + 1 < len(secs) else len(text)
        out.append({"no": int(no), "title": title, "body": text[pos:end].strip()})
    return out


def build_chunks(text: str, doc_id: str, product_id: str, substance: str, supplier: str,
                 cas_no: str, revision_date: str, source_url: str, title: str = "") -> List[dict]:
    """MSDS 항목 전체와 metadata를 보존한다. 예: D1-s8.

    표·조건·공급자 정보가 문자 수 경계에서 분리되지 않도록 1~16항을
    각각 하나의 청크로 만든다. 기존 인덱스는 재적재 전까지 바뀌지 않는다.
    """
    title = title or f"{substance} MSDS ({supplier})"
    chunks = []
    for sec in split_sections(text):
        no, sec_title = sec["no"], sec["title"]
        head = f"[{title} | {substance} | {no}. {sec_title}]"
        meta: ChunkMeta = {
            "doc_id": doc_id,
            "doc_type": DOC_TYPE_MSDS,
            "topic": TOPIC_CHEMICAL,
            "title": title,
            "section": f"{no}. {sec_title}",
            "source_url": source_url,
            "chunk_id": make_chunk_id(doc_id, f"s{no}"),
            "effective_date": revision_date,
            "product_id": product_id,
            "substance": substance,
            "cas_no": cas_no,
            "supplier": supplier,
            "msds_section_no": no,
        }
        chunks.append({"page_content": f"{head}\n{sec['body']}", "metadata": meta})
    return chunks


def main() -> None:
    """argparse: --input --doc-id --product-id ... --append --dry-run (ingest_law.py 와 같은 사용법)."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="MSDS .pdf 또는 .txt")
    ap.add_argument("--doc-id", required=True, help='기획서 문서 ID 예) "D1"')
    ap.add_argument("--product-id", required=True, help='"{공급자}-{제품번호}" 예) sigma-339741')
    ap.add_argument("--substance", required=True, help="물질명(한글) 예) 황산")
    ap.add_argument("--supplier", required=True, help='예) "Sigma-Aldrich Korea"')
    ap.add_argument("--cas-no", default="", help="예) 7664-93-9")
    ap.add_argument("--revision-date", default="", help="MSDS 최종 개정일 YYYY-MM-DD")
    ap.add_argument("--source-url", default="")
    ap.add_argument("--title", default="", help='화면에 보일 문서명 예) "Sulfuric acid 339741 MSDS"')
    ap.add_argument("--out", default=None, help="기본: schema.INDEX_DIRS[chemical_safety]")
    ap.add_argument("--append", action="store_true", help="기존 인덱스에 추가")
    ap.add_argument("--dry-run", action="store_true", help="청킹 결과만 출력, 임베딩/저장 안 함")
    a = ap.parse_args()

    # MSDS 는 '항목 : 값' 표라서 layout 모드로 읽어야 값이 항목명 옆에 붙는다. 남는 공백은 줄인다.
    text = re.sub(r"[ \t]{2,}", " ", read_msds_input(Path(a.input)))
    text = re.sub(r"\n\s*\n+", "\n", text)
    chunks = build_chunks(text, a.doc_id, a.product_id, a.substance, a.supplier,
                          a.cas_no, a.revision_date, a.source_url, a.title)
    found = sorted({c["metadata"]["msds_section_no"] for c in chunks})
    if not chunks:
        sys.exit("MSDS 항목(1~16)을 하나도 찾지 못했습니다. 한국어 MSDS 인지, 텍스트가 추출되는 PDF 인지 확인하세요.")
    missing = [n for n in range(1, 17) if n not in found]
    if missing:
        print(f"[경고] 찾지 못한 항목: {missing}", file=sys.stderr)

    out_dir = Path(a.out) if a.out else ROOT / INDEX_DIRS[TOPIC_CHEMICAL]
    print(f"[msds] 항목 {len(found)}/16, 청크 {len(chunks)}개 ({a.product_id}) → 인덱스={out_dir}")
    show = chunks if a.dry_run else chunks[:3]
    for c in show:
        print("-" * 60)
        print(json.dumps(c["metadata"], ensure_ascii=False))
        print(c["page_content"][:160].replace("\n", " ⏎ ") + (" ..." if len(c["page_content"]) > 160 else ""))

    if a.dry_run:
        print("\n(dry-run: 저장하지 않았습니다)")
        return
    save_index(chunks, out_dir, a.append)
    print(f"\n저장 완료: {out_dir} (이번에 {len(chunks)}개 청크). 서버를 재시작하면 반영됩니다.")


if __name__ == "__main__":
    main()
