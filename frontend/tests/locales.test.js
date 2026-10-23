import test from 'node:test'
import assert from 'node:assert/strict'
import { languages, copy } from '../src/locales/index.js'
import { apiCopy } from '../src/locales/api.js'
import contract from '../src/api/contract.json' with {type:'json'}

test('every server language has a complete UI and API message dictionary',()=>{
 assert.deepEqual(Object.keys(languages),contract.languages)
 for(const language of contract.languages){
  assert(languages[language])
  assert.deepEqual(Object.keys(copy[language]).sort(),Object.keys(copy.ko).sort(),language)
  assert.deepEqual(Object.keys(apiCopy[language]).sort(),Object.keys(apiCopy.ko).sort(),language)
  for(const [key,value] of Object.entries(copy[language])){
   if(Array.isArray(value)){assert.equal(value.length,copy.ko[key].length);assert(value.every(item=>typeof item==='string'&&item.trim()))}
   else assert(typeof value==='string'&&value.trim(),`${language}.${key}`)
  }
  assert(Object.values(apiCopy[language]).every(value=>typeof value==='string'&&value.trim()))
 }
})
