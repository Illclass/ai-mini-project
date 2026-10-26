import test from 'node:test'
import assert from 'node:assert/strict'
import { createDetector, voiceCommand, TIMING } from '../src/api/listener.js'

function feed(detector, level, ms, step = 50) {
  const events = []
  for (let t = 0; t < ms; t += step) { const e = detector.push(level, step); if (e) events.push(e) }
  return events
}

test('speech starts after loud frames and ends after silence',()=>{
 const d=createDetector()
 assert.deepEqual(feed(d,0.005,TIMING.CALIBRATE_MS),[])          // 주변 소음으로 기준 잡기
 assert.deepEqual(feed(d,0.2,1200),['start'])                     // 말 시작
 assert.deepEqual(feed(d,0.004,TIMING.SILENCE_MS-100),[])         // 잠깐 쉬는 것은 끝이 아님
 assert.deepEqual(feed(d,0.2,300),[])
 assert.deepEqual(feed(d,0.004,TIMING.SILENCE_MS+50),['end'])     // 1.5초 조용하면 끝
})
test('short click is discarded and loud background raises the threshold',()=>{
 const d=createDetector()
 feed(d,0.005,TIMING.CALIBRATE_MS)
 assert.deepEqual([...feed(d,0.2,150),...feed(d,0.004,TIMING.SILENCE_MS+50)],['start','discard'])
 const noisy=createDetector()
 feed(noisy,0.05,TIMING.CALIBRATE_MS)                             // 공장 소음 0.05
 assert(noisy.threshold>=0.15)
 assert.deepEqual(feed(noisy,0.06,1000),[])                       // 소음 수준 소리는 말로 보지 않음
})
test('very long speech is cut at the maximum length',()=>{
 const d=createDetector()
 feed(d,0.005,TIMING.CALIBRATE_MS)
 assert.deepEqual(feed(d,0.2,TIMING.MAX_MS+200),['start','end','start'])   // 15초에서 끊고, 계속 말하면 다음 녹음으로 이어 받음
})
test('voice commands: cancel and exit in several languages, normal questions untouched',()=>{
 for(const t of ['취소','그만.','cancel','取消','hủy'])assert.equal(voiceCommand(t),'cancel',t)
 for(const t of ['대화 종료','음성 종료해줘','End conversation','结束对话','kết thúc trò chuyện'])assert.equal(voiceCommand(t),'exit',t)
 for(const t of ['불산 보호구는 무엇인가요?','작업을 그만해도 되나요?','취소된 작업은 어떻게 하나요?'])assert.equal(voiceCommand(t),null,t)
})
