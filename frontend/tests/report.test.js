import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createReportSession, reportRequest, reportText, sourceUrl } from '../src/api/report.js'
import { guideFor, guides } from '../src/api/guides.js'
import { clean } from '../src/locales/clean.js'
import contract from '../src/api/contract.json' with { type: 'json' }
const response = { answer: '답변 [1] [2]', sources: [{ doc_id: 'one', title: '원문', section: '1절', url: 'https://example.org/1' }, { doc_id: 'one', title: '원문', section: '2절', url: 'https://example.org/2' }], handoff: true, needs_review: true, latency_ms: 10 }
const message = { question: '황산 보관 조건은?', topic: contract.topics.chemical, equipment_id: 'wet-bench', product_id: 'sigma-339741', language: 'ko', response }

test('report regeneration sends the original question, topic, equipment and product with target language', async () => {
 const calls = []
 const session = createReportSession(message, async body => { calls.push(body); return response })
 assert.deepEqual(await session.choose('ko'), response)
 assert.equal(calls.length, 0)
 assert.deepEqual(await session.choose('en'), response)
 assert.deepEqual(calls, [reportRequest(message, 'en')])
 assert.deepEqual(calls[0], { question: message.question, topic: message.topic, equipment_id: 'wet-bench', product_id: 'sigma-339741', language: 'en' })
 await session.choose('en'); assert.equal(calls.length, 1)
})
test('report keeps all ordered citations, URLs and review warning in shared text', () => {
 const text = reportText(message, response, { ...clean.ko, review: '담당자 확인이 필요합니다' }, 'Wet Bench / 황산')
 for (const value of ['Wet Bench / 황산', '[1] 원문 · 1절', '[2] 원문 · 2절', 'https://example.org/1', 'https://example.org/2', '담당자 확인이 필요합니다']) assert.ok(text.includes(value))
 assert.ok(text.indexOf('[1] 원문') < text.indexOf('[2] 원문'))
 assert.equal(sourceUrl('javascript:alert(1)'), null)
 assert.equal(sourceUrl('data:text/html,test'), null)
})
test('switching report language or closing cancels pending requests and ignores late results', async () => {
 const tasks = []
 const session = createReportSession(message, (body, { signal }) => new Promise(resolve => tasks.push({ body, signal, resolve })))
 const first = session.choose('en')
 const second = session.choose('vi')
 assert.ok(tasks[0].signal.aborted)
 tasks[0].resolve(response); assert.equal(await first, null)
 session.cancel(); assert.ok(tasks[1].signal.aborted)
 tasks[1].resolve(response); assert.equal(await second, null)
})
test('report propagates 401, supports retry after failure, and never caches errors', async () => {
 let count = 0
 const session = createReportSession(message, async () => { if (++count === 1) throw Object.assign(new Error('expired'), { status: 401 }); return response })
 await assert.rejects(session.choose('zh'), e => e.status === 401)
 assert.deepEqual(await session.choose('zh'), response)
 assert.equal(count, 2)
})
test('all guides are real PDF assets; HF-only and demo documents retain their identity', () => {
 for (const key of Object.keys(guides)) assert.equal(readFileSync(new URL(`../public/guides/${key}.pdf`, import.meta.url)).subarray(0, 5).toString(), '%PDF-')
 assert.equal(guideFor('emergency', contract.topics.chemical, 'sigma-339741'), null)
 assert.ok(guideFor('emergency', contract.topics.chemical, 'sigma-695068').source.includes('HF'))
 assert.ok(guideFor('after', contract.topics.chemical).source.includes('DEMO'))
 assert.equal(guideFor('free', contract.topics.law).url, '/guides/law.pdf')
})
test('new guide, report and emergency controls are localized in all contract languages', () => {
 for (const lang of Object.values(contract.languages)) {
   const labels = clean[lang]
   for (const key of ['retry', 'regeneration', 'shareFailed', 'originalKo', 'makeReport', 'reportTitle', 'printHint', 'download']) assert.ok(labels[key], `${lang}.${key}`)
   for (const key of Object.keys(clean.ko.em)) assert.ok(labels.em[key], `${lang}.em.${key}`)
 }
 assert.notEqual(clean.km.reportTitle, clean.en.reportTitle)
})

// The site guide is also shown as a static downloadable PDF. Keep the copies identical.
test('work cleanup PDF matches the current S1 source document', () => {
 assert.deepEqual(readFileSync(new URL('../public/guides/after.pdf', import.meta.url)), readFileSync(new URL('../../rag-service/data/site/S1_가상현장안전지침.pdf', import.meta.url)))
})

test('report situation, legal topic and scope labels follow all five report languages', async()=>{
 const {reportLabels}=await import('../src/api/report.js')
 const {copy}=await import('../src/locales/index.js')
 const {apiCopy}=await import('../src/locales/api.js')
 const {scopeCopy}=await import('../src/locales/scope.js')
 for(const lang of contract.languages){
  for(const [index,situation]of ['before','handling','storage','during','after','emergency'].entries()){
   const labels=reportLabels({...message,situation,equipment_id:'DEMO-WET-01'},lang)
   assert.equal(labels.title,copy[lang].topicTitles[index])
   assert.ok(labels.scope.includes(scopeCopy[lang].demo))
   assert.ok(labels.scope.includes('sigma-339741'))
   if(lang!=='ko')assert.ok(!labels.scope.includes('시연용')&&!labels.scope.includes('황산'))
  }
  assert.equal(reportLabels({...message,situation:'free'},lang).title,copy[lang].free)
  assert.deepEqual(reportLabels({...message,topic:contract.topics.law},lang),{title:apiCopy[lang].law,scope:''})
 }
})
test('report localization leaves the original question, IDs, language and API payload intact',async()=>{
 const {reportLabels}=await import('../src/api/report.js')
 const snapshot=structuredClone(message),before=reportRequest(message,'en')
 reportLabels(message,'en');reportLabels(message,'zh')
 assert.deepEqual(message,snapshot);assert.deepEqual(reportRequest(message,'en'),before)
})
