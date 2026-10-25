import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { parse } from '@vue/compiler-sfc'
import { baseParse } from '@vue/compiler-dom'
import { compile } from '@vue/compiler-ssr'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createApi, failureKey } from '../src/api/client.js'
import { apiCopy } from '../src/locales/api.js'
import contract from '../src/api/contract.json' with {type:'json'}

const request={question:'가상 테스트 자료',topic:contract.topics.law,product_id:null,equipment_id:null,language:'ko'}
const held={answer:'가상 보류 안내',sources:[],needs_review:true,handoff:true,latency_ms:0}
const reply=(outcome,status=503,extras={})=>new Response(JSON.stringify(status===200?held:{detail:'잠시 후 다시 시도해 주세요.'}),{status,headers:{'Content-Type':'application/json','X-ChemBridge-Outcome':outcome,'X-ChemBridge-Request-Id':'0123456789abcdef0123456789abcdef',...extras}})

for(const [outcome,headers,key] of [
 ['provider_error',{'X-ChemBridge-Provider-Status':'429'},'providerLimited'],
 ['provider_error',{'X-ChemBridge-Provider-Status':'500'},'providerError'],
 ['experiment_stopped',{'X-ChemBridge-Reason':'provider_halted'},'experimentStopped'],
 ['experiment_stopped',{'X-ChemBridge-Reason':'experiment_scope'},'experimentScope'],
 ['generation_error',{},'generationError'],
])test(`HTTP errors distinguish ${key} without displaying raw detail`,async()=>{
 await assert.rejects(createApi(async()=>reply(outcome,503,headers)).ask(request),error=>{
  assert.equal(error.status,503);assert.equal(failureKey(error),key)
  assert.equal(error.diagnostic.requestId,'0123456789abcdef0123456789abcdef')
  assert(!error.message.includes('잠시 후'));return true
 })
})

for(const [outcome,key] of [['verification_failed','evidenceFailed'],['verifier_unavailable','verificationUnavailable'],['insufficient_evidence','evidenceMissing'],['product_unverified','productUnverified']])test(`200 deferral preserves flags/sources and distinguishes ${key}`,async()=>{
 const result=await createApi(async()=>reply(outcome,200)).ask(request)
 assert.deepEqual(result,held)
 assert.equal(failureKey(result),key)
 assert.equal(JSON.stringify(result),JSON.stringify(held))
 assert.deepEqual(Object.keys(result).sort(),contract.responseFields.slice().sort())
})

test('old servers and unknown/malicious headers use generic fallback',async()=>{
 for(const outcome of ['', 'sk-secret', 'not_a_known_outcome']){
  await assert.rejects(createApi(async()=>reply(outcome)).ask(request),error=>{
   assert.equal(failureKey(error),null);assert.equal(error.diagnostic,null);return true
  })
 }
})

test('five languages have distinct provider, pause and validation messages',()=>{
 for(const language of contract.languages){
  const t=apiCopy[language]
  const keys=['providerLimited','experimentStopped','evidenceFailed','evidenceMissing']
  assert.equal(new Set(keys.map(k=>t[k])).size,keys.length)
  assert.equal(new Set(keys.map(k=>t[k+'Title'])).size,keys.length)
  assert(t.errorReference)
 }
})

// Compile the real answer section, not a duplicate test-only component.
const source=readFileSync(new URL('../src/App.vue',import.meta.url),'utf8')
const ast=baseParse(parse(source).descriptor.template.content)
function answerNode(node){
 if(node.props?.some(p=>p.name==='class'&&p.value?.content==='clear-answer'))return node
 for(const child of node.children||[]){const match=answerNode(child);if(match)return match}
}
const section=answerNode(ast)
assert(section,'actual answer section exists')
const ssrRender=new Function('require',compile(section.loc.source,{mode:'function'}).code)(createRequire(import.meta.url))
async function renderAnswer(message,language){
 const app=createSSRApp({ssrRender,data:()=>({message,a:apiCopy[language],failureKey,busy:false,playing:null,
  feedback:{failed:'fallback',edit:'edit'},t:{stop:'stop'},c:{makeReport:'report',emergency:'emergency'},sourceUrl:()=>null,
  isEmergency:()=>false,contacts:false,api:{VOICE_LANGUAGES:[]}})})   // dev 의 긴급 배지 판별 (이 테스트는 보류 이유만 확인)
 app.component('Icon',{render:()=>null})
 app.directive('spring',{getSSRProps:()=>({})})
 return renderToString(app)
}
for(const language of contract.languages)test(`actual answer template renders three distinct failure causes in ${language}`,async()=>{
 const t=apiCopy[language]
 for(const key of ['providerLimited','experimentStopped']){
  const html=await renderAnswer({id:1,error:key,diagnostic:{requestId:'0123456789abcdef0123456789abcdef'}},language)
  assert(html.includes(t[key+'Title'])&&html.includes(t[key]))
  if(key==='experimentStopped')assert(!html.includes(t.retry))
 }
 const html=await renderAnswer({id:1,response:{...held,diagnostic:{outcome:'verification_failed'}}},language)
 assert(html.includes(t.evidenceFailedTitle)&&html.includes(t.evidenceFailed))
 assert(html.includes(held.answer))
 const normal=await renderAnswer({id:1,response:{...held,handoff:false,diagnostic:{outcome:'review_required'}}},language)
 assert(normal.includes(t.answerNote)&&!normal.includes(t.evidenceFailedTitle))
})
