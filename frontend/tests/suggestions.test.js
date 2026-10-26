import test from 'node:test'
import assert from 'node:assert/strict'
import {suggestedQuestions} from '../src/api/suggestions.js'
import {recommendationEntries,faqRecommendations,lawRecommendations,productSubjects} from '../src/api/recommendations.js'
import {availableEquipment,availableProducts,productsFor,productLabel} from '../src/api/scope.js'
import documents from '../src/api/source-pages.json' with {type:'json'}
import candidates from '../src/api/candidates.json' with {type:'json'}
import contract from '../src/api/contract.json' with {type:'json'}
const phases=['before','handling','storage','during','after','emergency','free']
const contexts=[{},...availableEquipment.map(e=>({equipmentId:e.equipment_id})),...availableProducts.map(p=>({productId:p.product_id})),...availableEquipment.flatMap(e=>productsFor(e.equipment_id).map(p=>({equipmentId:e.equipment_id,productId:p.product_id})))]
test('all languages, stages and selectable scopes have two bounded, distinct, source-backed questions',()=>{
 let count=0
 for(const language of contract.languages)for(const situation of phases)for(const context of contexts){
  const entries=recommendationEntries({language,situation,...context})
  assert.deepEqual(suggestedQuestions({language,situation,...context}),entries.map(e=>e.q))
  assert.equal(entries.length,2);assert.equal(new Set(entries.map(e=>e.q)).size,2)
  const product=availableProducts.find(p=>p.product_id===context.productId)
  const name=product&&productLabel(product,language).split(' · ')[0]
  for(const e of entries){
   assert(!/MSDS|KOSHA|S1|가상 현장지침|\d+\s*(항|절)|第\d+节|section\s+\d+|mục\s+\d+/i.test(e.q),e.q)
   assert(e.q.trim()===e.q&&!/\s{2,}|undefined|null|[{}]|sigma-|merck-/i.test(e.q),e.q)
   assert(Array.from(e.q).length>=contract.question.minLength&&Array.from(e.q).length<=contract.question.maxLength,e.q)
   if(name)assert.equal(e.q.toLocaleLowerCase().split(name.toLocaleLowerCase()).length-1,1,e.q)
   for(const t of e.targets)assert.ok(documents[t.doc_id]?.sections[t.section.replace(/\s/g,'')],JSON.stringify(t))
   count++
  }
 }
 assert.equal(count,contexts.length*contract.languages.length*phases.length*2)
})
test('each card has a different general subject and product choices change the subject, not just the name',()=>{
 for(const language of contract.languages){
  const all=phases.slice(0,6).flatMap(situation=>suggestedQuestions({language,situation}))
  assert.equal(new Set(all).size,12)
 }
 assert.notDeepEqual(productSubjects.D1[1],productSubjects.D2[1])
 assert.notDeepEqual(productSubjects.D3[3],productSubjects.D11[3])
 assert.equal(recommendationEntries({language:'ko',situation:'before',equipmentId:'DEMO-CMP-01'})[0].targets[0].section,'2.1')
 assert.equal(recommendationEntries({language:'ko',situation:'before',equipmentId:'DEMO-WETETCH-01'})[0].targets[0].section,'5.3')
 assert(suggestedQuestions({language:'ko',situation:'before',equipmentId:'DEMO-WET-01',productId:'sigma-339741'})[0].includes('약액 조 주변 배기'))
 assert(suggestedQuestions({language:'ko',situation:'before',equipmentId:'DEMO-PHOTO-01',productId:'sigma-328251'})[0].includes('공급라인 연결부'))
})
test('FAQ languages share complete coverage and chemical entries carry the actual selectable product ID',()=>{
 for(const language of contract.languages){
  const entries=faqRecommendations(language,contract.topics.chemical)
  assert.equal(entries.filter(e=>e.product_id).length,availableProducts.length)
  for(const e of entries.filter(e=>e.product_id)){
   const p=availableProducts.find(p=>p.product_id===e.product_id);assert.ok(p)
   assert(e.targets.some(t=>t.doc_id===p.doc_id))
  }
  assert.deepEqual(candidates[language].chemical,entries)
  assert.deepEqual(candidates[language].law,lawRecommendations(language).map(x=>({...x,g:'law'})))
  assert.equal(lawRecommendations(language).length,2)
 }
})
test('training recommendations do not present a current exposure or an unregistered equipment incident',()=>{
 for(const lang of contract.languages)for(const e of faqRecommendations(lang,contract.topics.chemical)){
  assert(!/DEMO-DRYETCH|CVD|마셨어|묻었어요|눈에 들어가|경보가 울렸|피부에 닿/i.test(e.q),e.q)
 }
})

test('actual FAQ click selects its product before creating the normal API request and does not auto-send',async()=>{
 const {readFileSync}=await import('node:fs')
 const {parse}=await import('@vue/compiler-sfc')
 const {parse:parseScript}=await import('@babel/parser')
 const {createApi}=await import('../src/api/client.js')
 const setup=parse(readFileSync(new URL('../src/App.vue',import.meta.url),'utf8')).descriptor.scriptSetup.content
 const fn=parseScript(setup,{sourceType:'module'}).program.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name==='fillFaq')
 const equipmentId={value:'DEMO-WET-01'},productId={value:''},busy={value:false};let question='',requests=0
 const fill=new Function('busy','equipmentId','productId','fill',`${setup.slice(fn.start,fn.end)};return fillFaq`)(busy,equipmentId,productId,text=>{question=text})
 const entry=faqRecommendations('ko',contract.topics.chemical).find(e=>e.product_id==='sigma-339741')
 fill(entry)
 assert.equal(productId.value,entry.product_id);assert.equal(equipmentId.value,'');assert.equal(question,entry.q);assert.equal(requests,0)
 await createApi(async(path,options)=>{requests++;const body=JSON.parse(options.body);assert.deepEqual(Object.keys(body).sort(),contract.requestFields.slice().sort());assert.equal(body.product_id,entry.product_id);assert.equal(body.question,entry.q);return new Response(JSON.stringify({answer:'test',sources:[],handoff:false,needs_review:true,latency_ms:0}),{headers:{'Content-Type':'application/json'}})}).ask({question,topic:contract.topics.chemical,language:'ko',product_id:productId.value,equipment_id:null})
 assert.equal(requests,1)
})
