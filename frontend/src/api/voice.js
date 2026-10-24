// 음성 모드 — 녹음(MediaRecorder) → /voice/stt → 질문 확인·전송 → RAG → /voice/tts → 재생
// /voice 는 Vite 프록시(또는 배포 리버스 프록시)가 음성 서비스(:8008)로 넘긴다. 로그인 쿠키를 그대로 보낸다.
import { ApiError } from './client.js'

const MAX_SPEECH_CHARS = 400   // 읽기용 문장 상한 (약 50초. 700자는 1분 30초라 너무 길었다)
// 크메르어는 Whisper·OpenAI TTS 모두 알아들을 수 있는 품질이 아니라(합성 음성을 다시 인식해도 엉뚱한 문장) 음성 모드에서 뺀다
export const VOICE_LANGUAGES = ['ko', 'zh', 'vi', 'en']

// 녹음 형식: Chrome·Firefox 는 webm/opus, Safari 는 mp4. 서버(ffmpeg)는 둘 다 변환한다.
export function pickRecordingType(isSupported = type => globalThis.MediaRecorder?.isTypeSupported?.(type)) {
  for (const [mime, ext] of [['audio/webm;codecs=opus', '.webm'], ['audio/webm', '.webm'], ['audio/mp4', '.mp4'], ['audio/ogg;codecs=opus', '.ogg']]) {
    if (isSupported(mime)) return { mime, ext }
  }
  return { mime: '', ext: '.webm' }
}

export async function startRecording({ media = globalThis.navigator?.mediaDevices } = {}) {
  if (!media?.getUserMedia || !globalThis.MediaRecorder) throw new ApiError('VOICE_UNSUPPORTED')
  let stream
  try { stream = await media.getUserMedia({ audio: true }) }
  catch { throw new ApiError('MIC_DENIED') }
  const { mime, ext } = pickRecordingType()
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
  const chunks = []
  recorder.ondataavailable = event => { if (event.data?.size) chunks.push(event.data) }
  recorder.start()
  const release = () => stream.getTracks().forEach(track => track.stop())
  return {
    // 녹음을 끝내고 { blob, ext } 를 돌려준다
    stop: () => new Promise(resolve => {
      recorder.onstop = () => { release(); resolve({ blob: new Blob(chunks, { type: mime || 'audio/webm' }), ext }) }
      recorder.state === 'inactive' ? recorder.onstop() : recorder.stop()
    }),
    cancel: () => { recorder.onstop = null; if (recorder.state !== 'inactive') recorder.stop(); release() },
  }
}

// 화면용 답변 → 읽기용 문장: 출처 번호 [1]·원문 인용 줄·제목 줄을 빼고, 길면 문장 경계에서 자른 뒤 "화면에서 확인" 안내를 붙인다.
// 경고 문장(- 로 시작하는 목록)은 남긴다. 잘라도 화면 답변은 그대로라 안내 문구로 화면 확인을 유도한다.
export function speechText(answer, tail = '') {
  const lines = String(answer || '').split('\n').map(line => line.replace(/\s*\[\d+\]/g, '').trim())
  const kept = lines.filter(line => line &&
    !/^(원문|原文|Bản gốc|Original|អត្ថបទដើម)\s*[:：]/i.test(line) &&      // 원문 인용 (번역 답변 아래 붙는 줄)
    !/[:：]$/.test(line) &&                                                // "적용 조건 (…):" 같은 제목
    !(line.length <= 40 && !/[.!?。！？។]$/.test(line)))                    // 짧은 제목 줄 ("자료에 근거한 일반 정보")
    .map(line => line.replace(/^[-•·]\s*/, ''))
  let text = kept.join(' ').replace(/\s+/g, ' ').trim()
  if (text.length > MAX_SPEECH_CHARS) {
    const cut = text.slice(0, MAX_SPEECH_CHARS)
    const end = Math.max(...['. ', '。', '！', '？', '? ', '! ', '។'].map(mark => cut.lastIndexOf(mark)))
    text = (end > MAX_SPEECH_CHARS / 2 ? cut.slice(0, end + 1) : cut).trim()
    if (tail) text += ' ' + tail
  }
  return text
}

export function createVoice(fetcher = (...args) => fetch(...args), { timeoutMs = 60000 } = {}) {
  async function call(path, options, { signal } = {}) {
    const controller = new AbortController()
    const cancel = () => controller.abort()
    signal?.addEventListener('abort', cancel, { once: true })
    const timer = setTimeout(cancel, timeoutMs)
    try {
      const response = await fetcher(path, { ...options, credentials: 'include', signal: controller.signal })
      if (!response.ok) throw new ApiError(`HTTP_${response.status}`, response.status)
      return response
    } catch (error) {
      if (error instanceof ApiError) throw error
      throw new ApiError(signal?.aborted ? 'CANCELLED' : 'NETWORK')
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', cancel)
    }
  }

  async function transcribe({ blob, ext = '.webm', language }, options) {
    const form = new FormData()
    form.append('audio', blob, `question${ext}`)
    form.append('language', language)
    const data = await (await call('/voice/stt', { method: 'POST', body: form }, options)).json()
    if (typeof data?.text !== 'string' || !data.text.trim()) throw new ApiError('VOICE_EMPTY', 422)
    return { text: data.text.trim() }
  }

  async function speak({ text, language }, options) {
    const response = await call('/voice/tts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, language }),
    }, options)
    return response.blob()   // audio/mpeg
  }

  return { transcribe, speak }
}
