import test from 'node:test'
import assert from 'node:assert/strict'
import { createVoice, speechText, pickRecordingType } from '../src/api/voice.js'

test('speech text drops citation numbers, headings and source quote lines but keeps warnings',()=>{
 const answer='자료에 근거한 일반 정보\n\n보호장갑을 착용해야 합니다. [1]\n\n적용 조건 (실제 현장 해당 여부는 별도 확인):\n\n중요 경고·적용 조건 (원문 기준)\n\n- 피부에 묻으면 즉시 물로 씻으시오. [2]\n  원문: 피부에 묻으면 즉시 물로 씻으시오.'
 assert.equal(speechText(answer,'화면에서 확인하세요.'),'보호장갑을 착용해야 합니다. 피부에 묻으면 즉시 물로 씻으시오.')
})
test('product info line is not read aloud',()=>{
 assert.equal(speechText('보호구를 착용하세요. [1]\n\n근거 MSDS: Sulfuric acid · 제품번호 339741 [2]'),'보호구를 착용하세요.')
})
test('long speech is cut at a sentence end and points to the screen',()=>{
 const text=speechText(Array(60).fill('보호구를 착용해야 합니다.').join(' '),'화면에서 확인하세요.')
 assert(text.length<=430);assert(text.endsWith('다. 화면에서 확인하세요.'))
})
test('recording type falls back to Safari mp4',()=>{
 assert.deepEqual(pickRecordingType(t=>t==='audio/mp4'),{mime:'audio/mp4',ext:'.mp4'})
 assert.equal(pickRecordingType(()=>true).ext,'.webm')
})
test('transcribe posts audio with language and cookies; empty text is an error',async()=>{
 let sent
 const voice=createVoice(async(path,options)=>{sent={path,...options};return new Response(JSON.stringify({text:' 불산 보호구는? '}),{headers:{'Content-Type':'application/json'}})})
 assert.deepEqual(await voice.transcribe({blob:new Blob(['a']),ext:'.mp4',language:'vi'}),{text:'불산 보호구는?'})
 assert.equal(sent.path,'/voice/stt');assert.equal(sent.credentials,'include')
 assert.equal(sent.body.get('language'),'vi');assert.equal(sent.body.get('audio').name,'question.mp4')
 await assert.rejects(createVoice(async()=>new Response(JSON.stringify({text:''}))).transcribe({blob:new Blob(['a']),language:'ko'}),e=>e.code==='VOICE_EMPTY')
})
test('speak returns audio and keeps HTTP status for 401 handling',async()=>{
 const blob=await createVoice(async(path,o)=>{assert.equal(path,'/voice/tts');assert.deepEqual(JSON.parse(o.body),{text:'안녕',language:'ko'});return new Response(new Blob(['ID3'],{type:'audio/mpeg'}))}).speak({text:'안녕',language:'ko'})
 assert.equal(await blob.text(),'ID3')
 await assert.rejects(createVoice(async()=>new Response('',{status:401})).speak({text:'a',language:'ko'}),e=>e.status===401)
})
