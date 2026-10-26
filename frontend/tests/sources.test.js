import assert from 'node:assert/strict'
import test from 'node:test'
import { answerLines, groupSources } from '../src/api/sources.js'

const msds = (section, url = 'https://example.com/msds') => ({ doc_id: 'D2', title: 'Hydrofluoric acid MSDS', section, url })

test('같은 문서 출처는 한 줄로 묶고 본문 번호는 그대로 쓴다', () => {
  const groups = groupSources([
    { doc_id: 'K3', title: '불산 취급 지침', section: '4. 안전조치', url: null },
    msds('8. 노출방지 및 개인보호구'), msds('1. 화학제품과 회사에 관한 정보'), msds('3. 구성성분'),
  ])
  assert.equal(groups.length, 2)
  assert.deepEqual(groups[0], { key: groups[0].key, title: '불산 취급 지침', url: null, label: '1', sections: ['4. 안전조치'] })
  assert.equal(groups[1].label, '2~4')
  assert.deepEqual(groups[1].sections, ['8항', '1항', '3항'])
})

test('떨어진 번호는 가운데점으로 잇고, 항목이 하나면 제목을 줄이지 않는다', () => {
  const guide = section => ({ doc_id: 'K3', title: '불산 취급 지침', section, url: null })
  const groups = groupSources([msds('8. 노출방지 및 개인보호구'), guide('4. 안전조치'), msds('8. 노출방지 및 개인보호구'), guide('5. 비상조치')])
  assert.equal(groups[0].label, '1·3')
  assert.deepEqual(groups[0].sections, ['8. 노출방지 및 개인보호구'])
  assert.deepEqual(groups[1].sections, ['4. 안전조치', '5. 비상조치'])   // 지침 장은 "4항"으로 줄이지 않는다
})

test('소제목 줄과 출처 번호를 나눈다', () => {
  const lines = answerLines('권고사항 (법적 의무 아님)\n- 도구를 구비해 두세요. [1] [2]\n  적용 조건: 누출 시 [1]\n근거 MSDS: Methanol (제품번호 34860)')
  assert.deepEqual(lines.map(l => l.heading), [true, false, false, false])
  assert.deepEqual(lines[1].parts, [{ text: '- 도구를 구비해 두세요.' }, { mark: '1' }, { mark: '2' }])
  assert.equal(lines[2].parts.at(-1).mark, '1')
})

test('번역 경고 아래 원문 줄은 원문 줄로 표시한다', () => {
  const lines = answerLines('⚠ ការប្រុងប្រយ័ត្ន\n- កុំទុកនៅជិតសារធាតុងាយឆេះ។ [1]\n  អត្ថបទដើម: 가연성 물질 근처에 보관하지 마십시오.')
  assert.deepEqual(lines.map(l => l.original), [false, false, true])
})

test('긴 목록은 앞의 3개만 남기고 접되, 주의사항은 접지 않는다', async () => {
  const { foldAnswer } = await import('../src/api/sources.js')
  const items = n => Array.from({ length: n }, (_, i) => `- 항목 ${i + 1}. [1]`).join('\n')
  const lines = foldAnswer(answerLines(`알아둘 내용\n${items(6)}\n  적용 조건(위 6개 공통): 누출 시 [1]\n\n⚠ 주의사항\n${items(6)}\n\n근거 MSDS: 불산`))
  const shown = lines.filter(l => !l.extra)
  assert.equal(lines.filter(l => l.extra).length, 4)            // 항목 4~6 + 그 아래 조건 줄
  assert.equal(lines.find(l => l.more).more, 3)
  assert.equal(shown.length, lines.length - 4)
  const short = foldAnswer(answerLines(`알아둘 내용\n${items(4)}`))
  assert.equal(short.filter(l => l.extra).length, 0)            // 1개만 숨길 거면 접지 않는다
})
