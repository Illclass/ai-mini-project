import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {parse} from '@vue/compiler-sfc'
import {parse as parseScript} from '@babel/parser'
const setup=parse(readFileSync(new URL('../src/App.vue',import.meta.url),'utf8')).descriptor.scriptSetup.content
const node=parseScript(setup,{sourceType:'module'}).program.body.find(n=>n.type==='FunctionDeclaration' && n.id.name==='play')
const message={id:4,situation:'handling',question:'황산 보호구는?',topic:'chemical_safety',equipment_id:'DEMO-WET-01',product_id:'sigma-339741',language:'ko',response:{answer:'자료를 확인하세요.'}}
function player(status,{stale=false}={}){
 const playing={value:null},voiceError={value:''},expired=[]
 let stops=0
 const stop=()=>{stops++;playing.value=null}
 const api={speechText:()=>message.response.answer,speak:async()=>{if(stale)playing.value=null;throw Object.assign(new Error('test'),{status})}}
 const play=new Function('api','pending','voice','playing','voiceError','stop','expire','apiCopy',`${setup.slice(node.start,node.end)};return play`)(api,{value:false},{value:'idle'},playing,voiceError,stop,m=>expired.push(m),{ko:{speechTail:''}})
 return {play,playing,voiceError,expired,get stops(){return stops}}
}
test('actual TTS handler sends the original question/scope to login recovery on 401',async()=>{
 const p=player(401);await p.play(message)
 assert.deepEqual(p.expired,[message]);assert.equal(p.expired[0],message)
 assert.equal(p.voiceError.value,'');assert.equal(p.playing.value,null);assert.equal(p.stops,2)
})
test('TTS 503 keeps its playback error and does not trigger login recovery',async()=>{
 const p=player(503);await p.play(message)
 assert.deepEqual(p.expired,[]);assert.equal(p.voiceError.value,'speakFailed');assert.equal(p.playing.value,null)
})
test('a stale TTS 401 after playback cancellation does not navigate away',async()=>{
 const p=player(401,{stale:true});await p.play(message)
 assert.deepEqual(p.expired,[]);assert.equal(p.voiceError.value,'')
})
