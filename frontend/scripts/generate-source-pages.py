"""Map registered original PDFs to physical pages. No embeddings or LLM calls."""
import bisect, hashlib, json, re, shlex, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'rag-service'))
from ingest_law import numbered_sections, clean_noise, cut_appendix, ARTICLE_RE, CIRCLED, split_ho
result = {}
for line in (root / 'rag-service/ingest_all.sh').read_text().splitlines():
    if not re.match(r'^(msds D|law L|guide data/)', line): continue
    a = shlex.split(line)
    kind, doc_id = a[0], a[2]
    file = ('msds/' if kind == 'msds' else 'laws/' if kind == 'law' else '') + a[1].removeprefix('data/')
    title = a[8] if kind == 'msds' else a[3]
    path = root / 'rag-service/data' / file
    raw = subprocess.check_output(['pdftotext'] + (['-layout'] if kind == 'msds' else []) + [str(path), '-'], text=True)
    pages = raw.split('\f')
    if not pages[-1].strip(): pages.pop()
    if kind != 'msds': pages = [clean_noise(p) for p in pages]
    starts, offset = [], 0
    for p in pages: starts.append(offset); offset += len(p) + 1
    text = '\n'.join(pages)
    sections = {}
    def add(key, heading, pos, label):
        sections.setdefault(key, {'heading': heading, 'page': bisect.bisect_right(starts, pos), 'label': label})
    if kind != 'law':
        for n, heading, pos in numbered_sections(text, max_top=16 if kind == 'msds' else 30, allow_sub=kind != 'msds'):
            add(n, text[pos:].splitlines()[0].strip(), pos, f'{n}항' if kind == 'msds' else n)
        if kind == 'msds': assert list(sections) == [str(n) for n in range(1,17)], doc_id
    else:
        text = cut_appendix(text)
        heads = list(ARTICLE_RE.finditer(text))
        seen = set()
        for i, m in enumerate(heads):
            no = f'제{m[1]}조' + (f'의{m[2]}' if m[2] else '')
            if no in seen or m[4]: continue
            seen.add(no)
            end = heads[i+1].start() if i+1<len(heads) else len(text)
            body = text[m.start():end]
            add(no, m[0].strip(), m.start(), no)
            # Circled paragraph markers are matched as in the ingestion parser.
            paras = list(re.finditer(f'[{CIRCLED}]', body))
            spans = [(no, 0, len(body))]
            for j,p in enumerate(paras):
                pn = CIRCLED.index(p[0])+1
                stop = paras[j+1].start() if j+1<len(paras) else len(body)
                key = f'{no}제{pn}항'
                add(key, body[p.start():stop].splitlines()[0].strip(), m.start()+p.start(), f'{no} 제{pn}항')
                spans.append((key,p.start(),stop))
            for key,begin,stop in spans:
                piece = body[begin:stop]
                ho = split_ho(piece)
                if not ho: continue
                for hn,content in ho[1]:
                    pos = piece.find(content)
                    label = sections[key]['label']+f' 제{hn}호'
                    add(key+f'제{hn}호',content.splitlines()[0].strip(),m.start()+begin+pos,label)
    result[doc_id] = {'file': file, 'title': title, 'kind': kind,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'pageCount': len(pages), 'sections': sections}
output = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
target = root / 'frontend/src/api/source-pages.json'
if '--check' in sys.argv:
    if not target.exists() or target.read_text()!=output: raise SystemExit('Original PDFs changed: regenerate source pages')
else: target.write_text(output)
print(f'Original PDF map: {len(result)} documents, {sum(len(d["sections"]) for d in result.values())} locations')
