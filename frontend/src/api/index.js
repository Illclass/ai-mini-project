import { createApi } from './client.js'
export { ApiError } from './client.js'
export { default as contract } from './contract.json' with { type: 'json' }
export const { login, signup, logout, checkSession, ask } = createApi()
import { createVoice } from './voice.js'
export { startRecording, speechText, VOICE_LANGUAGES } from './voice.js'
export const { transcribe, speak } = createVoice()
export { startListening, voiceCommand } from './listener.js'
