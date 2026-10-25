import { availableProducts, equipmentFor, equipmentLabel, productLabel } from './scope.js'
import { questionCopy } from '../locales/questions.js'
import { equipmentChecks, productChecks } from '../locales/question-checks.js'
const phases = ['before','handling','storage','during','after','emergency']
const languages = ['ko','zh','vi','en','km']
const format = (template, values) => template.replace(/\{(\w+)\}/g, (_match, key) => values[key] || '')
function particle(word, consonant, vowel) {
 const last=word.charCodeAt(word.length-1)
 return word+(last>=0xac00 && last<=0xd7a3 && (last-0xac00)%28 ? consonant : vowel)
}
// 보호구 질문은 '어떤 자료에서 확인하나요' 대신 '무엇을 착용하나요'로 묻는다. 위치를 묻는 질문은 답변 AI 가
// '이 자료에는 ~가 없어요'를 덧붙여 검증에서 보류되는 일이 잦았다 (김규빈 2026-10-25, 추천 질문 14개 평가).
const koEquipment=[
 '{equipment}에서 {object} 사용하기 전, {checkTopic} 어떻게 점검하나요?',
 '{equipment}에서 {object} 취급할 때, {check}에 대비해 어떤 보호구를 착용해야 하나요?',
 '{equipment}에 사용할 {object} 보관할 때, {checkTopic} 어떻게 확인하나요?',
 '{equipment}에서 {object} 사용하는 중, {check}에 이상이 있으면 어떤 절차를 확인해야 하나요?',
 '{equipment}에서 {object} 사용하는 작업을 마친 뒤, {checkObject} 어떻게 정리하나요?',
 '{equipment}의 {product} 관련 {checkTopic} 어느 현장 지침에 나와 있나요?',
]
const koProduct=[
 '{product} 사용 전에 {checkObject} 어디서 확인하나요?',
 '{product} 취급 시 {check}에 대비해 어떤 보호구를 착용해야 하나요?',
 '{product} 보관 시 {checkObject} 어디서 확인하나요?',
 '{product} 작업 중 {checkObject} 어떻게 점검하나요?',
 '{product} 사용 후 {checkObject} 어떻게 처리해야 하나요?',
 '{product} {checkTopic} 어느 자료에서 확인하나요?',
]
export function suggestedQuestions({ situation, language, equipmentId, productId }) {
 const text = questionCopy[language] || questionCopy.ko
 const localeIndex = Math.max(0,languages.indexOf(language))
 const equipment = equipmentFor(equipmentId)
 const product = availableProducts.find(item=>item.product_id === productId)
 const equipmentName = equipment ? equipmentLabel(equipment,language,'').replace(/ · $/,'') : ''
 // Display names in prose; product IDs remain separate API fields.
 const productName = product ? productLabel(product,language).split(' · ')[0] : text.generic
 const index = Math.max(0,phases.indexOf(situation))
 const context = equipment ? format(text.context,{equipment:equipmentName,product:productName}) : productName
 if(!equipment && !product) return (situation==='free'?text.free:[text.primary[index],text.detail[index]]).map(template=>format(template,{context:text.generic,detail:['누출과 오염','泄漏与污染','rò rỉ và nhiễm bẩn','leaks and contamination','ការលេចធ្លាយ និងការបំពុល'][localeIndex]}))
 const render=(check,isEquipment)=>{
  const values={equipment:equipmentName,product:productName,object:particle(productName,'을','를'),check,checkObject:particle(check,'을','를'),checkTopic:particle(check,'은','는'),context,detail:check}
  if(language==='ko') return format((isEquipment?koEquipment:koProduct)[index],values)
  return format(isEquipment ? text.detail[index] : text.productDetail[index],{...values,context:isEquipment?context:productName})
 }
 const equipmentCheck=equipmentChecks[equipment?.process]?.[index]?.[localeIndex]
 const productCheck=productChecks[product?.product_id]?.[index]?.[localeIndex]
 const primary=render(equipmentCheck||productCheck,Boolean(equipment))
 const secondary=productCheck ? render(productCheck,false) : language==='ko' ? `${equipmentName} 관련 자료 중 ${particle(equipmentCheck,'을','를')} 다룬 문서는 무엇인가요?` : format(text.free[1],{context,detail:equipmentCheck})
 if(primary!==secondary)return [primary,secondary]
 return [primary,language==='ko' ? `${productName} MSDS의 어느 항목에서 ${particle(productCheck,'을','를')} 확인할 수 있나요?` : format(text.productFollowup,{context:productName,detail:productCheck})]
}
