import { createApi } from './client.js'
export { ApiError } from './client.js'
export { default as contract } from './contract.json' with { type: 'json' }
export const { login, signup, logout, checkSession, ask } = createApi()
// Voice integration is outside this change; these controls remain explicit previews.
export { transcribe } from '../mocks/service'
