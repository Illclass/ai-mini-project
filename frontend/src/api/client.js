import contract from './contract.json' with { type: 'json' }

export class ApiError extends Error {
  constructor(code, status = 0, diagnostic = null) {
    super(code)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.diagnostic = diagnostic
  }
}

// Optional response headers keep the shared JSON contract unchanged. Only
// known categories/reasons are used for UI copy; never display raw error text.
const outcomes = new Set(['answer','review_required','provider_error','experiment_stopped','verification_failed','verifier_unavailable','insufficient_evidence','product_unverified','generation_error'])
function readDiagnostic(headers) {
  const outcome=headers.get('X-ChemBridge-Outcome')
  if(!outcomes.has(outcome))return null
  const status=Number(headers.get('X-ChemBridge-Provider-Status'))
  const reason=headers.get('X-ChemBridge-Reason')
  const requestId=headers.get('X-ChemBridge-Request-Id')
  return {outcome,providerStatus:Number.isInteger(status)&&status>=100&&status<=599?status:null,
    reason:['provider_halted','experiment_scope','unapproved_request','unapproved_source','unapproved_destination','unapproved_model_or_stream','llm_timeout'].includes(reason)?reason:null,
    requestId:/^[a-f0-9]{32}$/.test(requestId||'')?requestId:null}
}

export function failureKey(value) {
  const d=value?.diagnostic
  if(d?.outcome==='provider_error')return d.providerStatus===429?'providerLimited':'providerError'
  if(d?.outcome==='experiment_stopped')return ['experiment_scope','unapproved_request','unapproved_source','unapproved_destination','unapproved_model_or_stream'].includes(d.reason)?'experimentScope':'experimentStopped'
  return ({verification_failed:'evidenceFailed',verifier_unavailable:'verificationUnavailable',insufficient_evidence:'evidenceMissing',product_unverified:'productUnverified',generation_error:'generationError'})[d?.outcome]||null
}

// Same-origin routes are forwarded by Vite (and the deployment reverse proxy).
// JWT stays in HttpOnly cookies; the frontend never reads or stores tokens.
export function createApi(fetcher = (...args) => fetch(...args), { timeoutMs = 90000 } = {}) {
  async function request(path, { signal, json = true, timeout = timeoutMs, ...options } = {}) {
    const controller = new AbortController()
    let timedOut = false
    const cancel = () => controller.abort()
    if (signal?.aborted) cancel()
    signal?.addEventListener('abort', cancel, { once: true })
    const timer = setTimeout(() => { timedOut = true; controller.abort() }, timeout)
    try {
      const response = await fetcher(path, { ...options, credentials: 'include', signal: controller.signal })
      const diagnostic=readDiagnostic(response.headers)
      if (!response.ok) throw new ApiError(`HTTP_${response.status}`, response.status, diagnostic)
      if (!json || response.status === 204) return null
      const type = response.headers.get('content-type') || ''
      if (!type.includes('application/json')) throw new ApiError('INVALID_RESPONSE')
      try {
        const data=await response.json()
        // Frontend-only, non-serialized metadata; no response field is added.
        if(data&&typeof data==='object')Object.defineProperty(data,'diagnostic',{value:diagnostic,configurable:true})
        return data
      } catch (error) {
        if (error instanceof SyntaxError) throw new ApiError('INVALID_RESPONSE')
        throw error
      }
    } catch (error) {
      if (error instanceof ApiError) throw error
      if (timedOut) throw new ApiError('TIMEOUT')
      if (signal?.aborted) throw new ApiError('CANCELLED')
      throw new ApiError('NETWORK')
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', cancel)
    }
  }

  async function checkSession(options = {}) {
    try {
      const data = await request('/api/auth/check', { ...options, timeout: 8000 })
      if (data?.ok !== true) throw new ApiError('INVALID_RESPONSE')
      return data
    } catch (error) {
      if (error.status === 401) return null
      throw error
    }
  }

  async function login({ username, password }) {
    const data = await request('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
      body: new URLSearchParams({ username: username.trim(), password }),
      timeout: 15000,
    })
    if (data?.ok !== true) throw new ApiError('INVALID_RESPONSE')
    // Ignore the legacy voice-demo redirect; keep navigation inside Vue.
    const session = await checkSession()
    if (!session) throw new ApiError('AUTH_COOKIE', 401)
    return session
  }

  async function signup({ username, password }) {
    await request('/api/signup', {
      method: 'POST', json: false,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
      body: new URLSearchParams({ username: username.trim(), password }), timeout: 15000,
    })
  }

  async function logout() {
    // Java clears cookies then redirects to /login; a final HTML response is valid.
    await request('/api/logout', { method: 'POST', json: false, timeout: 15000 })
    if (await checkSession()) throw new ApiError('LOGOUT_FAILED')
  }

  async function ask(body, options = {}) {
    const payload = Object.fromEntries(contract.requestFields.map(key => [key, body[key] ?? (contract.nullableFields.includes(key) ? null : undefined)]))
    const data = await request('/rag-query', {
      ...options,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!data || typeof data !== 'object' || Array.isArray(data) || contract.responseFields.some(key => !(key in data)) ||
        typeof data.answer !== 'string' || !Array.isArray(data.sources) ||
        typeof data.needs_review !== 'boolean' || typeof data.handoff !== 'boolean' ||
        typeof data.latency_ms !== 'number' || data.sources.some(source => !source || contract.sourceFields.some(key => typeof source[key] !== 'string'))) {
      throw new ApiError('INVALID_RESPONSE')
    }
    return data
  }

  return { login, signup, logout, checkSession, ask }
}
