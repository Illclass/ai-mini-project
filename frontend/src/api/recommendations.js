import contract from './contract.json' with {type:'json'}
import {availableProducts,equipmentFor,equipmentLabel,productLabel} from './scope.js'
import {contexts,genericNames,questions,equipmentPrechecks} from '../locales/recommendations.js'
const phases=['before','handling','storage','during','after','emergency']
const langs=['ko','zh','vi','en','km']
const section={safe:'7',hazard:'2',eye:'8',hand:'8',body:'8',respirator:'8',store:'7',container:'7',ignition:'7',ventilation:'7',reaction:'10',incompatible:'10',avoid:'10',dispose:'13',waste:'13',fire:'5',firefighter:'5'}
// Two source-backed subjects per stage; chemical differences determine the subjects.
const standard=[['safe','hazard'],['eye','hand'],['store','container'],['ventilation','respirator'],['dispose','waste'],['fire','firefighter']]
export const productSubjects={
 D1:[["safe","hazard"],["eye","hand"],["container","store"],["respirator","body"],["dispose","waste"],["fire","firefighter"]],
 D2:[["hazard","safe"],["body","hand"],["container","store"],["respirator","eye"],["waste","dispose"],["firefighter","fire"]],
 D3:[["hazard","safe"],["eye","body"],["store","container"],["ventilation","respirator"],["dispose","waste"],["fire","firefighter"]],
 D4:[["hazard","ventilation"],["respirator","eye"],["container","store"],["ventilation","body"],["waste","dispose"],["firefighter","fire"]],
 D5:[["ventilation","hazard"],["eye","body"],["store","container"],["respirator","hand"],["dispose","waste"],["fire","firefighter"]],
 D6:[["hazard","safe"],["body","hand"],["container","store"],["ventilation","respirator"],["waste","dispose"],["firefighter","fire"]],
 D7:[["safe","hazard"],["hand","eye"],["container","store"],["body","respirator"],["dispose","waste"],["fire","firefighter"]],
 D8:[["hazard","safe"],["body","eye"],["store","container"],["hand","ventilation"],["waste","dispose"],["firefighter","fire"]],
 D9:[["ignition","safe"],["eye","hand"],["store","container"],["ventilation","ignition"],["dispose","waste"],["fire","firefighter"]],
 D10:[["hazard","ignition"],["hand","respirator"],["container","store"],["ventilation","body"],["waste","dispose"],["firefighter","fire"]],
 D11:[["ignition","ventilation"],["eye","hand"],["store","container"],["ignition","ventilation"],["dispose","waste"],["fire","firefighter"]],
 D12:[["ignition","safe"],["hand","eye"],["container","store"],["ventilation","body"],["waste","dispose"],["firefighter","fire"]],
 D13:[["safe","hazard"],["body","hand"],["container","store"],["respirator","eye"],["dispose","waste"],["fire","firefighter"]],
}
// Some registered MSDS sections are excluded by the current retriever's warning-context check.
// Use a relevant registered general guide for those subjects; never bypass that check.
const alternatives={
 D1:{hazard:['S1','2.4','label']},
 D2:{hazard:['S1','2.4','label'],safe:['D2','8','respirator'],container:['K1','4.2','indoor'],store:['K1','4.1','outdoor'],firefighter:['S1','15.1','stop']},
 D3:{ventilation:['D3','7','safe'],firefighter:['S1','15.1','stop']},
 D4:{hazard:['S1','2.4','label'],store:['K1','4.2','indoor']},
 D5:{ventilation:['S1','2.1','permit'],hazard:['S1','2.4','label'],store:['K1','4.1','outdoor'],container:['K1','4.2','indoor']},
 D6:{hazard:['S1','2.4','label'],hand:['D6','8','eye']},
 D7:{hazard:['S1','2.4','label']},
 D8:{hazard:['S1','2.4','label'],firefighter:['S1','15.1','stop']},
 D10:{hazard:['S1','2.4','label']},
 D13:{hazard:['S1','2.4','label']},
}
export const genericTargets={
 before:[['S1','2.4','label'],['S1','2.1','permit']],
 handling:[['K3','6.3','gloveTypes'],['K3','6.10','goggles']],
 storage:[['K1','4.1','outdoor'],['K1','4.2','indoor']],
 during:[['K1','6.7','worker'],['K7','5.3','msdsUse']],
 after:[['S1','2.5','cleanup'],['K3','9','maintenance']],
 emergency:[['S1','15.1','stop'],['K8','8.1','training']],
 free:[['K1','5.1','packing'],['K1','6.5','msdsPosting']],
}
const equipmentChapters={cleaning:'3',photo:'4',etch_wet:'5',cmp:'7',solvent:'11',utility:'12'}
const equipmentTargets=[['2.1','permit'],['2.3','ppeReference'],['14.1','separation'],['2.2','isolation'],['2.5','cleanup'],['15.1','stop']]
const format=(s,values)=>s.replace(/\{(\w+)\}/g,(_,k)=>values[k]??'')
function settings(language){const code=langs.includes(language)?language:'ko';return {code,i:langs.indexOf(code)}}
function particle(word,consonant,vowel){const n=word.charCodeAt(word.length-1);return word+(n>=0xac00&&n<=0xd7a3&&(n-0xac00)%28?consonant:vowel)}
export function recommendationEntries({situation='free',language='ko',equipmentId,productId}={}){
 const {code,i}=settings(language)
 const equipment=equipmentFor(equipmentId)
 const product=availableProducts.find(p=>p.product_id===productId && (!equipment||equipment.product_ids.includes(productId)))
 const name=product?productLabel(product,code).split(' · ')[0]:''
 const equipmentName=equipment?equipmentLabel(equipment,code,'').replace(/ · $/,''):''
 const context=equipment?format(contexts[code],{equipment:equipmentName,product:name||genericNames[i]}):name||genericNames[i]
 const index=phases.includes(situation)?phases.indexOf(situation):0
 const make=(doc_id,no,key,extra={})=>({q:format((key==='precheck'&&equipmentPrechecks[equipment?.process]||questions[key])[i],{context,object:particle(context,'을','를'),topic:particle(context,'은','는')}),targets:[{doc_id,section:no}],...extra})
 if(!equipment&&!product)return (genericTargets[situation]||genericTargets.free).map(([id,no,key])=>make(id,no,key))
 if(product){
  const ids=(productSubjects[product.doc_id]||standard)[index]
  const productEntries=ids.map(key=>{const [doc,no,subject]=(key==='firefighter'?['S1','15.1','stop']:alternatives[product.doc_id]?.[key])||[product.doc_id,section[key],key];return make(doc,no,subject,{product_id:product.product_id})})
  const entries=productEntries.slice()
  if(equipment){
   // S1 describes demo procedures only; never invent device-specific chemistry or limits.
   const [no,key]=situation==='before'||situation==='free'?(equipment.process==='cmp'?['2.1','permit']:[`${equipmentChapters[equipment.process]}.3`,'precheck']):equipmentTargets[index]
   const emergencyHF=situation==='emergency' && product.doc_id==='D2'
   entries[0]=make('S1',emergencyHF?`${equipmentChapters[equipment.process]}.${equipment.process==='cleaning'?'5':'4'}`:no,emergencyHF?'emergencyReferences':key,{equipment_id:equipment.equipment_id,product_id:product.product_id})
  }
  if(entries[0].q===entries[1].q)entries[1]=productEntries[0]
  return entries
 }
 const [no,key]=situation==='before'||situation==='free'?(equipment.process==='cmp'?['2.1','permit']:[`${equipmentChapters[equipment.process]}.3`,'precheck']):equipmentTargets[index]
 const other=situation==='emergency'?['15.3','communication']:['2.4','label']
 return [[no,key],other].map(([n,k])=>make('S1',n,k,{equipment_id:equipment.equipment_id}))
}
export function lawRecommendations(language){
 const {i}=settings(language)
 return [['L2','제2조','lawDefinition'],['L1','제52조','lawStop']].map(([id,no,key])=>({q:questions[key][i],targets:[{doc_id:id,section:no}]}))
}
const faqChoice={D1:['handling',0],D2:['handling',0],D3:['storage',0],D4:['handling',0],D5:['during',1],D6:['emergency',1],D7:['storage',0],D8:['handling',0],D9:['before',0],D10:['after',0],D11:['storage',0],D12:['after',1],D13:['during',1]}
export function faqRecommendations(language,topic){
 if(topic===contract.topics.law)return lawRecommendations(language).map(x=>({...x,g:'law'}))
 return [
  ...availableProducts.map(p=>{const [situation,index]=faqChoice[p.doc_id];return {...recommendationEntries({language,situation,productId:p.product_id})[index],g:'substance'}}),
  ...['before','handling','storage','during','after','free'].flatMap(situation=>recommendationEntries({language,situation}).map(x=>({...x,g:'common'}))),
  ...recommendationEntries({language,situation:'emergency'}).map(x=>({...x,g:'incident'})),
 ]
}
