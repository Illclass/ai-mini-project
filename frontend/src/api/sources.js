// 답변 화면 정리용 (김규빈 2026-10-25). 서버 응답은 그대로 두고 보여 주는 모양만 바꾼다.

// 같은 문서의 출처를 한 줄로 묶는다. 같은 MSDS 의 8항·1항·3항·16항이 출처 4줄로 따로 나오던 것을
// "[2~5] Hydrofluoric acid MSDS · 8항 · 1항 · 3항 · 16항" 한 줄로. 번호는 본문 [n] 과 같은 번호를 그대로 쓴다.
export function groupSources(sources = []) {
  const groups = []
  sources.forEach((source, i) => {
    const key = `${source.doc_id}\u0000${source.title}`
    let group = groups.find(g => g.key === key)
    if (!group) groups.push(group = { key, title: source.title, url: source.url, numbers: [], sections: [] })
    group.numbers.push(i + 1)
    if (source.section && !group.sections.includes(source.section)) group.sections.push(source.section)
    if (!group.url && source.url) group.url = source.url
  })
  return groups.map(({ key, title, url, numbers, sections }) => ({
    key, title, url, label: numberLabel(numbers),
    // MSDS 항목이 여럿이면 "8. 노출방지 및 개인보호구" → "8항"처럼 짧게. 지침·법령이나 항목이 하나면 원래 제목 그대로.
    sections: sections.length > 1 && /MSDS/i.test(title) ? sections.map(shortSection) : sections,
  }))
}

function numberLabel(numbers) {
  const contiguous = numbers.every((n, i) => i === 0 || n === numbers[i - 1] + 1)
  if (numbers.length === 1) return String(numbers[0])
  return contiguous ? `${numbers[0]}~${numbers.at(-1)}` : numbers.join('·')
}

function shortSection(section) {
  const msds = /^(\d{1,2})\.\s/.exec(section)
  return msds ? `${msds[1]}항` : section
}

// 답변 글을 줄 단위로 나눠, 소제목 줄은 굵게, 출처 번호 [n] 은 작고 흐리게 보여 줄 수 있게 조각낸다.
// 소제목 = 목록(- )·들여쓰기가 아니고, 40자 이하, 쌍점(:)이 없고, 문장부호나 출처 번호로 끝나지 않는 줄 ("알아둘 내용", "⚠ 주의사항").
export function answerLines(answer = '') {
  return String(answer).split('\n').map(line => {
    const heading = !!line.trim() && !/^\s|^- /.test(line) && line.length <= 40 && !/[:：]/.test(line) && !/[.!?。！？។\]]$/.test(line.trim())
    const parts = []
    let last = 0
    for (const match of line.matchAll(/\s*\[(\d+)\]/g)) {
      if (match.index > last) parts.push({ text: line.slice(last, match.index) })
      parts.push({ mark: match[1] })
      last = match.index + match[0].length
    }
    if (last < line.length) parts.push({ text: line.slice(last) })
    // 번역 경고 아래 원문 줄 ("  원문: …", "  អត្ថបទដើម: …"): 번역을 대조하라고 일부러 싣는 한국어라 작고 흐리게 보여 준다
    const original = /^\s+(?:원문|原文|Bản gốc|Original|អត្ថបទដើម)\s*[:：]/.test(line)
    return { heading, original, parts }
  })
}

// 긴 답변 접기: 소제목 하나(또는 빈 줄까지의 문단) 안에서 목록 항목이 limit + 2 개 이상이면
// 앞의 limit 개만 보이고 나머지는 extra 로 표시한다. 들여쓴 줄(적용 조건·원문)은 바로 위 항목을 따라간다.
// ⚠ 주의사항 묶음은 안전 경고라 접지 않는다. 마지막으로 보이는 줄에 more = 숨긴 항목 수를 단다.
export function foldAnswer(lines, limit = 3) {
  const out = lines.map(line => ({ ...line, extra: false, more: 0 }))
  let section = null
  const close = () => {
    if (!section || section.warn || section.items.length < limit + 2) return
    section.items.slice(limit).flat().forEach(i => { out[i].extra = true })
    out[section.items[limit - 1].at(-1)].more = section.items.length - limit
  }
  out.forEach((line, i) => {
    const text = line.parts.map(p => p.text || '').join('')
    if (line.heading || !text.trim()) {
      close()
      section = { warn: line.heading && text.trim().startsWith('⚠'), items: [] }
    } else if (text.startsWith('- ')) {
      if (!section) section = { warn: false, items: [] }
      section.items.push([i])
    } else if (/^\s/.test(text) && section?.items.length) {
      section.items.at(-1).push(i)
    } else {
      close()
      section = null
    }
  })
  close()
  return out
}
