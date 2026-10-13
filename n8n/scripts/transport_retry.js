// Transport retry of a provider call (docs/contract-api.md, events provider_retry; decision 2026-09-20, step C):
// the verdict «retry or not» for one HTTP answer, shared by the Validate nodes of llm-call and the STT transport
// check of the pipeline. Inserted verbatim into those Code nodes at build time (they cannot require); the text
// up to the module boundary is the insert. Functions, not consts: the node's main code runs first.
//
// The provider nodes answer with neverError + fullResponse, so 429 and 5xx arrive as ordinary items with a
// statusCode – n8n's own retryOnFail never saw them (found 2026-09-20: the "one retry after 5 s" of 15/16
// September existed only for exceptions). A node exception (timeout, connection reset) becomes an item with
// `error` and no statusCode through onError: continueRegularOutput.
//
// Retried: 429 without insufficient_quota, 500, 502, 503, 504 – up to 3 attempts in total, 25 s apart or the
// provider's Retry-After when it is at most 60 s; a transport exception – one retry (a 600 s STT timeout twice is
// already the chunk's budget). Never retried: 400 and everything else; 401, 403, 402 (Deepgram: credit exhausted,
// err_code ASR_PAYMENT_REQUIRED) and 429 insufficient_quota (OpenAI: balance exhausted) are provider_auth.
function transportVerdict(resp, attempt, opts) {
  const o = Object.assign({ maxAttempts: 3, exceptionAttempts: 2, defaultWait: 25, maxRetryAfter: 60 }, opts || {});
  const r = resp || {};
  const status = Number(r.statusCode) || 0;
  const body = r.body;
  const text = typeof body === 'string' ? body : JSON.stringify(body || {});
  const err = body && typeof body === 'object' && body.error && typeof body.error === 'object' ? body.error : {};
  const code = String(err.code || err.type || (body && typeof body === 'object' && body.err_code) || '').trim();
  const v = { status, code, attempt, max: o.maxAttempts, retry: false, auth: false, wait_sec: o.defaultWait, wait_from: 'default', reason: '' };
  if (!status) {
    v.max = o.exceptionAttempts;
    v.reason = 'no answer: ' + String(r.error && r.error.message ? r.error.message : r.error || 'empty response').slice(0, 120);
    v.retry = attempt < o.exceptionAttempts;
    return v;
  }
  v.reason = `${status}${code ? ' ' + code : ''}`;
  if (status === 401 || status === 403 || status === 402) { v.auth = true; return v; }
  if (status === 429 && /insufficient_quota/i.test(code + ' ' + text)) { v.auth = true; v.reason = '429 insufficient_quota'; return v; }
  if (status === 429 || status === 500 || status === 502 || status === 503 || status === 504) {
    v.retry = attempt < o.maxAttempts;
    const h = r.headers || {};
    const ra = h['retry-after'] !== undefined ? h['retry-after'] : h['Retry-After'];
    if (ra !== undefined && ra !== null && String(ra).trim() !== '') {
      let sec = Number(ra);
      if (!Number.isFinite(sec)) { const t = Date.parse(String(ra)); sec = Number.isFinite(t) ? Math.ceil((t - Date.now()) / 1000) : NaN; }
      if (Number.isFinite(sec) && sec > 0 && sec <= o.maxRetryAfter) { v.wait_sec = Math.ceil(sec); v.wait_from = 'retry-after'; }
      else if (Number.isFinite(sec)) v.wait_from = `default (retry-after ${Math.ceil(sec)} s ignored)`;
    }
  }
  return v;
}
// The events row for one retry (contract section 4): stage, provider, code, attempt number, pause and its source.
function transportEvent(stage, provider, label, v) {
  return { type: 'provider_retry', level: 'warn', stage, provider: provider || null, http_status: v.status || null, body: `${label}: attempt ${v.attempt + 1} of ${v.max} after ${v.reason}, waiting ${v.wait_sec} s (${v.wait_from})` };
}
// --- module boundary: everything above is inserted verbatim into Code nodes by scripts/build_workflows.py;
// below is for node only.
module.exports = { transportVerdict, transportEvent };
