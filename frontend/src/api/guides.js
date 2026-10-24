import contract from './contract.json' with { type: 'json' }
export const guides = {
  before: { title: '위험표시', source: 'KOSHA GUIDE' },
  handling: { title: '개인보호구', source: 'KOSHA GUIDE' },
  storage: { title: '화학물질 저장', source: 'KOSHA GUIDE' },
  during: { title: '리스크 관리', source: 'KOSHA GUIDE' },
  after: { title: '가상 현장 안전지침', source: 'ChemBridge · DEMO' },
  emergency: { title: '불산·불화수소 응급대응 지침', source: 'KOSHA GUIDE · HF' },
  law: { title: '중대재해 처벌 등에 관한 법률', source: '국가법령정보센터' },
}
export function guideFor(situation, topic, productId) {
  const key = topic === contract.topics.law ? 'law' : situation
  if (!guides[key] || (key === 'emergency' && productId && productId !== 'sigma-695068')) return null
  return { ...guides[key], url: `/guides/${key}.pdf` }
}
