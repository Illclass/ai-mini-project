import documents from './source-pages.json' with { type: 'json' }

// Resolve only registered IDs and exact structural addresses. Never guess a page.
export function locateSource(source) {
 const doc = documents[source?.doc_id]
 if (!doc) return null
 const raw = source?.section || ''
 const no = doc.kind === 'law'
  ? /^(제\d+조(?:의\d+)?(?:\s*제\d+항)?(?:\s*제\d+호)?)(?:\s|$)/.exec(raw)?.[1]?.replace(/\s+/g,'')
  : /^(\d{1,2}(?:\.\d{1,2})?)(?:\.(?!\d)|항(?:\s|$)|\s|$)/.exec(raw)?.[1]
 const section = doc.sections[no]
 return section ? { docId: source.doc_id, file: doc.file, title: doc.title,
  sectionNo: no, section: doc.kind === 'law' ? section.label : section.heading, heading: section.heading,
  label: section.label, kind: doc.kind, page: section.page, pageCount: doc.pageCount } : null
}
