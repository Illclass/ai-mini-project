// 손 없이 쓰는 음성 대화 모드의 귀: 마이크를 켜 둔 채 말소리 크기를 보고 한 마디씩 잘라 보낸다.
//   말 시작(소리가 기준보다 큰 상태가 START_MS 이상) → onSpeechStart
//   말 끝(조용한 상태가 SILENCE_MS 이상, 또는 MAX_MS 초과) → 그때까지 녹음한 것을 onUtterance({ blob, ext })
// 기준 소리 크기는 처음 CALIBRATE_MS 동안의 주변 소음으로 정한다 (공장 소음이 크면 기준도 올라간다).
import { ApiError } from './client.js'
import { pickRecordingType } from './voice.js'

export const TIMING = { CALIBRATE_MS: 600, START_MS: 120, SILENCE_MS: 1500, MAX_MS: 15000, MIN_SPEECH_MS: 400 }

// 소리 크기 프레임을 받아 '말 시작/끝'을 알려 주는 상태 기계 (브라우저 없이 테스트할 수 있게 분리)
export function createDetector({ timing = TIMING, minLevel = 0.015, ratio = 3 } = {}) {
  let noise = 0, calibrated = 0, threshold = minLevel
  let speaking = false, loudFor = 0, quietFor = 0, speechFor = 0
  return {
    get speaking() { return speaking },
    get threshold() { return threshold },
    // level: 0~1 RMS, ms: 지난 프레임 이후 시간. 반환: 'start' | 'end' | 'discard'(너무 짧은 소리) | null
    push(level, ms) {
      if (calibrated < timing.CALIBRATE_MS) {
        noise = Math.max(noise * 0.9, level); calibrated += ms
        threshold = Math.max(minLevel, noise * ratio)
        return null
      }
      const loud = level >= threshold
      if (!speaking) {
        loudFor = loud ? loudFor + ms : 0
        if (loudFor >= timing.START_MS) { speaking = true; quietFor = 0; speechFor = loudFor; return 'start' }
        return null
      }
      speechFor += ms
      quietFor = loud ? 0 : quietFor + ms
      if (quietFor >= timing.SILENCE_MS || speechFor >= timing.MAX_MS) {
        speaking = false; loudFor = 0
        return speechFor - quietFor >= timing.MIN_SPEECH_MS ? 'end' : 'discard'
      }
      return null
    },
    reset() { speaking = false; loudFor = 0; quietFor = 0; speechFor = 0 },
  }
}

// 마이크를 열고 듣기 시작한다. pause()/resume() 은 답변을 읽는 동안 자기 목소리를 듣지 않게 하기 위함.
export async function startListening({ onSpeechStart, onUtterance, media = globalThis.navigator?.mediaDevices } = {}) {
  if (!media?.getUserMedia || !globalThis.MediaRecorder || !globalThis.AudioContext) throw new ApiError('VOICE_UNSUPPORTED')
  let stream
  try { stream = await media.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }) }
  catch { throw new ApiError('MIC_DENIED') }
  const ctx = new AudioContext()
  const source = ctx.createMediaStreamSource(stream)
  // 소리 크기는 오디오 처리 주기(약 46ms)마다 잰다. setTimeout 은 화면이 꺼지거나 탭이 가려지면
  // 브라우저가 1분 단위로 늦춰서 말 끝을 못 알아챈다 (실제로 확인함).
  const processor = ctx.createScriptProcessor(2048, 1, 1)
  const mute = ctx.createGain(); mute.gain.value = 0   // 처리 노드를 돌리려면 출력에 이어야 해서 소리 0 으로 연결
  source.connect(processor); processor.connect(mute); mute.connect(ctx.destination)
  const detector = createDetector()
  const { mime, ext } = pickRecordingType()
  // 녹음기는 듣는 동안 계속 켜 둔다. 말소리를 감지한 뒤에 녹음을 켜면 첫 음절이 잘려
  // "메탄올을"이 "환호를"로 인식됐다 (실제로 확인함). 말이 없으면 IDLE_RESTART_MS 마다 새로 시작해 파일이 커지지 않게 한다.
  const IDLE_RESTART_MS = 8000
  let recorder = null, chunks = [], paused = false, idleMs = 0

  function beginRecording() {
    chunks = []; idleMs = 0
    const current = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
    current.ondataavailable = event => { if (event.data?.size && recorder === current) chunks.push(event.data) }
    current.start()
    recorder = current
  }
  function finishRecording(keep) {
    const current = recorder, kept = chunks; recorder = null
    if (!current) return
    current.ondataavailable = event => { if (event.data?.size) kept.push(event.data) }
    current.onstop = () => { if (keep) onUtterance?.({ blob: new Blob(kept, { type: mime || 'audio/webm' }), ext }) }
    current.stop()
  }
  processor.onaudioprocess = event => {
    if (paused) return
    const samples = event.inputBuffer.getChannelData(0)
    const ms = samples.length / ctx.sampleRate * 1000
    let sum = 0
    for (const value of samples) sum += value * value
    const detected = detector.push(Math.sqrt(sum / samples.length), ms)
    if (detected === 'start') onSpeechStart?.()
    else if (detected === 'end') { finishRecording(true); beginRecording() }          // 이 말만 보내고 다음 말을 위해 다시 녹음
    else if (detected === 'discard') { finishRecording(false); beginRecording() }
    else if (!detector.speaking && (idleMs += ms) >= IDLE_RESTART_MS) { finishRecording(false); beginRecording() }
  }
  await ctx.resume()
  beginRecording()
  return {
    pause() { paused = true; detector.reset(); finishRecording(false) },
    resume() { paused = false; detector.reset(); beginRecording() },
    stop() { processor.onaudioprocess = null; finishRecording(false); stream.getTracks().forEach(track => track.stop()); ctx.close() },
  }
}

// 음성 명령: 인식된 문장이 짧은 명령어이면 질문으로 보내지 않는다
const CANCEL = /^(취소|그만|멈춰|아니야|다시|cancel|stop|no|取消|停止|不是|hủy|dừng|không phải)[.!?。！？\s]*$/i
const EXIT = /(대화\s*종료|음성\s*종료|대화\s*끝|end\s*(the\s*)?conversation|exit\s*voice|结束对话|退出语音|kết thúc trò chuyện|thoát giọng nói)/i
export function voiceCommand(text) {
  const value = String(text || '').trim()
  if (EXIT.test(value)) return 'exit'
  if (CANCEL.test(value)) return 'cancel'
  return null
}
