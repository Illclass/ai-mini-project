import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createHash} from 'node:crypto'
import {locateSource} from '../src/api/source-pages.js'
import documents from '../src/api/source-pages.json' with {type:'json'}
import {sourceCopy} from '../src/locales/sources.js'
test('MSDS citations retain exact section page navigation',()=>{
 const t=locateSource({doc_id:'D1',section:'8. 노출방지 및 개인보호구'})
 assert.equal(t.page,6);assert.equal(t.file,'msds/D1_황산.pdf');assert.equal(t.sectionNo,'8')
})
test('KOSHA, site and law references resolve distinct subsection and clause addresses',()=>{
 for(const [doc_id,section,page] of [['K1','4.1 옥외저장',5],['S1','3.4 약품 공급 용기 교체',3],['L2','제2조 제2호',1]]){
  const target=locateSource({doc_id,section});assert.ok(target);assert.equal(target.page,page)
 }
 assert.notEqual(locateSource({doc_id:'K1',section:'4 화학물질의 저장'}).sectionNo,locateSource({doc_id:'K1',section:'4.1 옥외저장'}).sectionNo)
 assert.match(locateSource({doc_id:'L2',section:'제2조 제2호'}).heading,/^2\./)
})
test('unknown documents, missing sections and non-address text do not guess pages',()=>{
 for(const s of [null,{}, {doc_id:'unknown',section:'8.'},{doc_id:'D1',section:'17. 없음'},{doc_id:'D1',section:'본문에 8항이 있음'},{doc_id:'K1',section:'4.99 없음'},{doc_id:'L2',section:'제999조'}])assert.equal(locateSource(s),null)
})
test('all 27 registered originals match fingerprints and every target resolves within PDF bounds',()=>{
 assert.equal(Object.keys(documents).length,27)
 for(const [id,doc]of Object.entries(documents)){
  const bytes=readFileSync(new URL(`../../rag-service/data/${doc.file}`,import.meta.url))
  assert.equal(createHash('sha256').update(bytes).digest('hex'),doc.sha256,id)
  if(doc.kind==='msds')assert.equal(Object.keys(doc.sections).length,16)
  for(const [key,section]of Object.entries(doc.sections)){
   const t=locateSource({doc_id:id,section:doc.kind==='law'?section.label:`${key} ${section.heading}`})
   assert.ok(t,`${id} ${key}`);assert.ok(t.page>=1 && t.page<=doc.pageCount)
  }
 }
})
test('all five source interface translations are complete',()=>{
 for(const code of ['ko','zh','vi','en','km'])for(const key of Object.keys(sourceCopy.ko))assert.ok(sourceCopy[code][key])
})
