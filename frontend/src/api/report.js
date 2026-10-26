import contract from './contract.json' with { type: 'json' }

export function reportRequest(message, language) {
  return Object.fromEntries(contract.requestFields.map(key => [key, key === 'language' ? language : message[key] ?? null]))
}
export function sourceUrl(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : null } catch { return null }
}
export function reportText(message, response, labels, scope = '') {
  const sources = response.sources.map((s, i) => `[${i + 1}] ${s.title}${s.section ? ` · ${s.section}` : ''}${sourceUrl(s.url) ? `\n${sourceUrl(s.url)}` : ''}`).join('\n')
  return [labels.reportTitle, scope, `${labels.question}: ${message.question}`,
    (response.handoff || response.needs_review) ? labels.review : '', response.answer,
    sources ? `${labels.sources}\n${sources}` : '', labels.disclaimer].filter(Boolean).join('\n\n')
}

// Each report retains the original query scope. Closing or switching language
// aborts work and prevents a late response from replacing a newer report.
export function createReportSession(message, ask) {
  const cache = new Map([[message.language, structuredClone(message.response)]])
  let controller, version = 0
  return {
    cancel() { version++; controller?.abort() },
    async choose(language) {
      const id = ++version
      controller?.abort()
      if (cache.has(language)) return cache.get(language)
      controller = new AbortController()
      const result = await ask(reportRequest(message, language), { signal: controller.signal })
      if (version !== id) return null
      cache.set(language, result)
      return result
    },
  }
}
