import test from 'node:test'
import assert from 'node:assert/strict'
import { suggestedQuestions } from '../src/api/suggestions.js'
import { availableEquipment, availableProducts, productsFor, productLabel, equipmentLabel } from '../src/api/scope.js'
import { questionCopy } from '../src/locales/questions.js'
import { equipmentChecks, productChecks } from '../src/locales/question-checks.js'
import { feedbackCopy } from '../src/locales/feedback.js'
import contract from '../src/api/contract.json' with {type:'json'}
const situations=['before','handling','storage','during','after','emergency']
test('six cards provide distinct relevant questions, with no shared expiry suggestion',()=>{
 for(const language of contract.languages){
  const sets=situations.map(situation=>suggestedQuestions({situation,language}))
  const all=sets.flat()
  assert.equal(new Set(all).size,12)
  assert(sets.every(questions=>questions.length===2))
  for(const question of all)assert(question.length>=2 && Array.from(question).length<=contract.question.maxLength)
 }
 assert(suggestedQuestions({situation:'handling',language:'ko'})[0].includes('착용'))   // 보호구 질문은 '무엇을 착용하나요'로 묻는다
 assert(suggestedQuestions({situation:'storage',language:'ko'})[0].includes('보관'))
 assert(suggestedQuestions({situation:'after',language:'ko'})[0].includes('잔여물'))
})
test('each equipment/product changes suggestions in all six cards and all languages',()=>{
 for(const language of contract.languages){
  for(const equipment of availableEquipment){
   for(const situation of [...situations,'free']){
    const equipmentOnly=suggestedQuestions({situation,language,equipmentId:equipment.equipment_id})
    assert(equipmentOnly[0].includes(equipmentLabel(equipment,language,'').replace(/ · $/,'')))
    const products=productsFor(equipment.equipment_id)
    for(const product of products){
     const questions=suggestedQuestions({situation,language,equipmentId:equipment.equipment_id,productId:product.product_id})
     assert(questions.every(q=>q.includes(productLabel(product,language).split(' · ')[0])))
     assert.notDeepEqual(questions,equipmentOnly)
     assert(questions.every(q=>!q.includes('{') && !/sigma-|merck-/i.test(q) && Array.from(q).length<=contract.question.maxLength))
    }
    assert(new Set(products.map(product=>suggestedQuestions({situation,language,equipmentId:equipment.equipment_id,productId:product.product_id})[1])).size===products.length)
   }
  }
 }
})
test('context dictionaries cover every supported language and selectable item',()=>{
 for(const language of contract.languages){
  assert.equal(questionCopy[language].primary.length,6)
  assert.equal(questionCopy[language].detail.length,6)
  assert.deepEqual(Object.keys(feedbackCopy[language]).sort(),Object.keys(feedbackCopy.ko).sort())
 }
 for(const equipment of availableEquipment){
  assert.equal(equipmentChecks[equipment.process].length,6)
  assert(equipmentChecks[equipment.process].every(stage=>stage.length===5))
  for(const product of productsFor(equipment.equipment_id)) assert.equal(productChecks[product.product_id].length,6)
 }
})

test('equipment and product choices change the subject matter, not just names',()=>{
 const ask=(equipmentId,productId,situation='before')=>suggestedQuestions({equipmentId,productId,situation,language:'ko'})
 const sulfuric=ask('DEMO-WET-01','sigma-339741')
 const hf=ask('DEMO-WET-01','sigma-695068')
 assert(sulfuric[0].includes('공급라인'))
 assert(sulfuric[1].includes('발열'))
 assert(hf[1].includes('비상 연락망'))
 assert(ask('DEMO-WETETCH-01','sigma-695068')[0].includes('식각조'))
 assert(ask('DEMO-CMP-01','merck-8.22287')[0].includes('슬러리'))
 assert(ask('DEMO-CMP-01','merck-8.22287')[1].includes('분해'))
 assert(ask('DEMO-SOLV-01','sigma-563935','after')[0].includes('걸레'))
 assert(ask('DEMO-UTIL-01','sigma-221465','during')[0].includes('중화조'))
 assert(ask('DEMO-WET-01','sigma-339741','storage')[1].includes('용기 재질'))
})

// Include product-only selections: the duplicate HF emergency sentence was hidden
// by the old test matrix, which covered only equipment/product combinations.
test('all selectable contexts, stages and languages avoid repeated names and broken sentence joins',()=>{
 const contexts=[{},...availableEquipment.map(e=>({equipmentId:e.equipment_id})),...availableProducts.map(p=>({productId:p.product_id})),...availableEquipment.flatMap(e=>productsFor(e.equipment_id).map(p=>({equipmentId:e.equipment_id,productId:p.product_id}))) ]
 let checked=0
 for(const language of contract.languages)for(const situation of [...situations,'free'])for(const context of contexts){
  const questions=suggestedQuestions({language,situation,...context})
  assert.equal(questions.length,2)
  assert.equal(new Set(questions).size,2)
  const product=availableProducts.find(p=>p.product_id===context.productId)
  const name=product && productLabel(product,language).split(' · ')[0]
  for(const question of questions){
   const details=JSON.stringify({language,situation,...context,question})
   assert(question.trim()===question && !/\s{2,}|undefined|null|[{}]|sigma-|merck-/i.test(question),details)
   assert(Array.from(question).length>=contract.question.minLength && Array.from(question).length<=contract.question.maxLength,details)
   if(name)assert.equal(question.toLocaleLowerCase().split(name.toLocaleLowerCase()).length-1,1,details)
   if(language==='ko'){
    assert(!/(사고 시.*접촉 시|사고 시.*노출 시|시.*시.*절차|의\s+의|에서.*작업에서|절차.*절차|응급조치.*응급조치)/.test(question),details)
   }
   checked++
  }
 }
 assert.equal(checked,contexts.length*contract.languages.length*7*2)
})
test('HF product-only emergency prompts do not repeat the chemical or incident preamble',()=>{
 const questions=suggestedQuestions({situation:'emergency',language:'ko',productId:'sigma-695068'})
 assert.deepEqual(questions,[
  '불산 접촉 후 전문 응급대응 절차는 어느 자료에서 확인하나요?',
  '불산 MSDS의 어느 항목에서 접촉 후 전문 응급대응 절차를 확인할 수 있나요?',
 ])
})
