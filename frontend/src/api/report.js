import contract from './contract.json' with { type: 'json' }
import { copy } from '../locales/index.js'
import { apiCopy } from '../locales/api.js'
import { scopeCopy } from '../locales/scope.js'
import { catalog, equipmentFor, equipmentLabel, productLabel } from './scope.js'

// UI labels follow the report language; source titles and the original question stay intact.
export function reportLabels(message, language) {
 const code = copy[language] ? language : 'ko'
 const index = ['before', 'handling', 'storage', 'during', 'after', 'emergency'].indexOf(message.situation)
 const title = message.topic === contract.topics.law ? apiCopy[code].law : index < 0 ? copy[code].free : copy[code].topicTitles[index]
 const equipment = equipmentFor(message.equipment_id)
 const product = catalog.products.find(item => item.product_id === message.product_id)
 const scope = message.topic === contract.topics.law ? '' : [
  equipment ? equipmentLabel(equipment, code, scopeCopy[code].demo) : '',
  product ? productLabel(product, code) : '',
 ].filter(Boolean).join(' / ')
 return { title, scope }
}

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
