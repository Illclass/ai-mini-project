import { copy } from '../locales'
const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms))
export async function login() { await wait(450); return { ok: true, user: { id: 'demo', username: 'Demo worker' } } }
// Mirrors rag-service/rag/schema.py. No network or credentials are used.
export async function ask({ question, topic, product_id = null, language = 'ko' }, { situation = 'free' } = {}) {
  await wait(1100)
  const urgent = situation === 'emergency' || /누출|피부에|사고|泄漏|rò rỉ/i.test(question)
  const review = !urgent && (['storage', 'handling', 'during'].includes(situation) || /기한|몇 분|장갑|有效期|hạn sử dụng/i.test(question))
  const kind = urgent ? 2 : review ? 1 : 0
  return { answer: copy[language].answers[kind], sources: [{ doc_id: 'DEMO-01', title: `${copy[language].demoAnswer} · ChemBridge`, section: copy[language].sourceNote, url: '' }], needs_review: review || urgent, handoff: urgent, latency_ms: 1100 }
}
export async function transcribe({ language, situationIndex }) { await wait(850); return { text: copy[language].questions[Math.max(0, situationIndex)] } }
