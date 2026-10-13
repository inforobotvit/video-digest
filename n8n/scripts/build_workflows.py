"""Development tool: regenerate n8n/workflows/*.json from Python.

The exported JSON in n8n/workflows/ is the source of truth (see n8n/CLAUDE.md). Use this script
when a change is easier to express here than in the JSON, then run scripts/import.sh and
scripts/export.sh so the committed files come from the instance.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "workflows"
PG_CRED = {"postgres": {"name": "VideoDigest Postgres"}}
MEDIA_CRED = {"httpHeaderAuth": {"name": "Media Service API"}}

def node(name, type_, version, params, x, y, **extra):
    n = {"name": name, "type": type_, "typeVersion": version, "position": [x, y], "parameters": params}
    n.update(extra)
    return n

def pg(name, query, params_expr, x, y, **extra):
    p = {"operation": "executeQuery", "query": query, "options": {}}
    if params_expr:
        p["options"]["queryReplacement"] = "=" + params_expr
    return node(name, "n8n-nodes-base.postgres", 2.7, p, x, y, credentials=PG_CRED, **extra)

def code(name, js, x, y):
    return node(name, "n8n-nodes-base.code", 2, {"jsCode": js}, x, y)

def if_bool(name, expr, x, y):
    return node(name, "n8n-nodes-base.if", 2.3, {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
            "conditions": [{"id": "c1", "leftValue": "=" + expr, "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
            "combinator": "and"},
        "options": {}}, x, y)

def respond(name, body_expr, code_expr, x, y, no_store=False):
    opts = {"responseCode": code_expr}
    if no_store:
        opts["responseHeaders"] = {"entries": [{"name": "Cache-Control", "value": "no-store"}]}
    return node(name, "n8n-nodes-base.respondToWebhook", 1.5, {"respondWith": "json", "responseBody": "=" + body_expr, "options": opts}, x, y)

def http(name, method, url_expr, x, y, json_body=None, multipart=False):
    p = {"method": method, "url": "=" + url_expr, "authentication": "predefinedCredentialType", "nodeCredentialType": "httpHeaderAuth",
         "options": {"response": {"response": {"fullResponse": True, "neverError": True, "responseFormat": "json"}}}}
    if json_body is not None:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": "=" + json_body})
    if multipart:
        p.update({"sendBody": True, "contentType": "multipart-form-data",
                  "bodyParameters": {"parameters": [{"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "={{ Object.keys($binary)[0] }}"}]}})
    return node(name, "n8n-nodes-base.httpRequest", 4.5, p, x, y, credentials=MEDIA_CRED)

def wire(conns, src, dst, out=0, inp=0):
    conns.setdefault(src, {"main": []})
    outs = conns[src]["main"]
    while len(outs) <= out:
        outs.append([])
    outs[out].append({"node": dst, "type": "main", "index": inp})

def log_events(name, x, y):
    # Fire-and-forget call of log-events: with waitForSubWorkflow off the node passes its input items through,
    # so the chain after it still sees the state; an insert failure stays inside the sub-workflow.
    return node(name, "n8n-nodes-base.executeWorkflow", 1.3, {
        "workflowId": {"__rl": True, "value": "", "mode": "list", "cachedResultName": "log-events"},
        "workflowInputs": {"mappingMode": "defineBelow", "value": {"job_id": "={{ $json.job_id || ($json.job && $json.job.id) || '' }}", "events": "={{ $json.events || [] }}"}, "matchingColumns": [],
                           "schema": [{"id": "job_id", "displayName": "job_id", "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "string", "removed": False},
                                      {"id": "events", "displayName": "events", "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "array", "removed": False}],
                           "attemptToConvertTypes": False, "convertFieldsToString": False},
        "options": {"waitForSubWorkflow": False}}, x, y)

# ----------------------------------------------------------------- jobs-api
VALIDATE_JS = r"""// Validate POST /api/jobs body per docs/contract-api.md section 2.
const body = $input.first().json.body || {};
const PRESETS = ['lecture', 'meeting', 'talk', 'interview', 'plain'];
// transcript_translation was accepted here from 2026-09-04 and never produced anything (translated: null in every
// result); removed 2026-09-17, an old client sending it gets validation_error instead of a silent nothing.
// fact_check followed on 2026-09-17: accepted, shown as «experimental», three minutes in the estimate, never run.
const OPTIONS = ['glossary', 'critique', 'self_check', 'action_items', 'decisions', 'questions'];
const fail = (code, message) => [{ json: { ok: false, statusCode: 400, body: { error: { code, message } } } }];
const lang = /^[a-z]{2}$/;

if (!/^[0-9a-f]{12}$/.test(String(body.source_id || ''))) return fail('validation_error', 'source_id must be 12 hex chars from /api/probe');
if (!PRESETS.includes(body.preset)) return fail('validation_error', `preset must be one of: ${PRESETS.join(', ')}`);
if (!lang.test(String(body.source_language || ''))) return fail('validation_error', 'source_language must be an ISO 639-1 code');
const output_language = body.output_language || body.source_language;
if (!lang.test(String(output_language))) return fail('validation_error', 'output_language must be an ISO 639-1 code');
const options = Array.isArray(body.options) ? [...new Set(body.options)] : [];
const unknown = options.filter((o) => !OPTIONS.includes(o));
if (unknown.length) return fail('validation_error', `unknown options: ${unknown.join(', ')}`);
let email = null;
if (body.email) {
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(body.email))) return fail('validation_error', 'email is invalid');
  if (body.consent_152fz !== true) return fail('consent_required', 'consent_152fz must be true when email is given');
  email = String(body.email).trim().toLowerCase();
}
// Turnstile token (contract section 2, step E3): passed through as is, checked after the budget in Turnstile decide.
const turnstile_token = typeof body.turnstile_token === 'string' && body.turnstile_token.length <= 4096 ? body.turnstile_token : null;
return [{ json: { ok: true, source_id: body.source_id, preset: body.preset, source_language: body.source_language, output_language, options, email, consent_152fz: body.consent_152fz === true, turnstile_token } }];
"""

TOO_LONG_JS = r"""// too_long answer (contract section 6): the limit travels in max_duration_sec so the front never hardcodes it.
const tooLong = (durationSec, maxSec) => ({ statusCode: 400, body: { error: { code: 'too_long', message: `video is ${Math.round(durationSec / 60)} min, maximum is ${Math.round(maxSec / 60)} min`, max_duration_sec: maxSec } } });
// Missing or zero duration (media-service falls back to 0.0 when the extractor has none) is a refusal:
// such a source would pass the duration cap and get a zero cost estimate, so it would bypass the budget too.
const unknownDuration = () => ({ statusCode: 400, body: { error: { code: 'unknown_duration', message: 'could not determine the video duration; try another source or upload the file' } } });
"""

BUILD_ROW_JS = TOO_LONG_JS + r"""// Turn the media-service source lookup into a jobs row (contract section 4, result-schema source block).
const req = $('Validate job request').first().json;
const resp = $('Media source').first().json;
const pricing = $('Parse pricing').first().json.data || {};
if (resp.statusCode !== 200) {
  const err = (resp.body && resp.body.error) || { code: 'media_error', message: `media service returned ${resp.statusCode}` };
  const notFound = resp.statusCode === 404;
  return [{ json: { ok: false, statusCode: notFound ? 404 : 502, body: { error: { code: notFound ? 'unknown_source' : err.code, message: err.message } } } }];
}
const src = resp.body;
const probe = src.probe;
// The source is registered in the Media Service even when /api/probe answered too_long, so the duration cap is
// checked again on creation – in Check budget, where the effective MAX_DURATION_SEC arrives with the budget row
// (settings table first, variable second). Only the zero-duration refusal stays here.
if (!(Number(probe.duration_sec) > 0)) return [{ json: { ok: false, ...unknownDuration() } }];
// Rule 1.1 of docs/result-schema.md, the same guard as in /api/probe: the subtitles branch reads
// subs.<source_language>.json, so a language outside the manual tracks cannot be processed.
const manual = ((probe.subtitles || {}).manual) || [];
let sourceLanguage = req.source_language;
let languageOverride = null;
if (probe.recommended === 'subtitles_manual' && manual.length && !manual.includes(sourceLanguage)) {
  languageOverride = { requested: sourceLanguage, used: manual[0], reason: 'manual subtitles' };
  sourceLanguage = manual[0];
}
const ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789';
const id = 'j_' + Array.from({ length: 6 }, () => ALPHABET[Math.floor(Math.random() * ALPHABET.length)]).join('');

function playbackFor() {
  if (src.kind === 'upload') return { kind: 'audio', url: `/api/jobs/${id}/media`, has_video: false };
  const url = src.url || '';
  if (probe.platform === 'youtube') {
    const m = url.match(/(?:v=|youtu\.be\/|shorts\/|embed\/)([A-Za-z0-9_-]{11})/);
    return { kind: 'youtube', url: m ? `https://www.youtube.com/embed/${m[1]}` : url, has_video: true };
  }
  if (probe.platform === 'vk' || probe.platform === 'rutube') return { kind: probe.platform, url, has_video: true };
  return { kind: 'direct', url, has_video: /\.(mp4|webm|mov|mkv)(\?|$)/i.test(url) };
}

const source = {
  type: src.kind === 'upload' ? 'upload' : 'url',
  url: src.url,
  platform: probe.platform,
  title: probe.title,
  duration_sec: probe.duration_sec,
  thumbnail_url: probe.thumbnail_url,
  language: sourceLanguage,
  language_detected_by: manual.length ? 'subtitles' : null,
  language_confidence: null,
  playback: playbackFor(),
};
const stages = ['probe', 'download', 'transcribe', 'clean', 'digest', 'extras'].map((name) => ({ name, status: 'pending' }));
// estimate_sec: the same arithmetic the front does on the form (contract section 2, /api/probe).
// The preset only sets the defaults of the checkboxes on the front (2026-09-30, step E4): `options` is the final
// list of extras blocks, a preset adds nothing on its own – `preset: lecture, options: []` runs without a glossary.
const PER_OPTION = { glossary: 15, critique: 30, self_check: 15, action_items: 15, decisions: 15, questions: 15 };
const d = probe.duration_sec || 0;
let estimate = probe.recommended === 'subtitles_manual' ? 60 : Math.round(d * 0.08 + 60);
for (const b of new Set(req.options)) estimate += PER_OPTION[b] || 0;
// estimated_cost_usd (contract section 7, DAILY_BUDGET_USD): STT at the STT_MODEL price from pricing.json,
// zero when manual subtitles replace transcription, plus a flat LLM allowance per minute of video.
// LLM_EST_USD_PER_MIN from the measured runs (2026-09-16): the LLM share (clean, digest, extras) per minute
// of video was 0.00043 USD with gpt-5.6-luna on reduce and 0.00124 with gpt-4.1 (lecture + critique),
// 0.00076 for a 72-minute podcast with translation; 0.0015 keeps 1.2x headroom over the dearest case.
// Short videos break the proportion (fixed prompt overhead: a 5-minute job cost 0.0164), hence the floor.
// The constant will have to depend on the model once more than one reduce model is in use (debt).
// A wrong estimate corrects itself: the estimate is only reserved while the job is queued/processing;
// once it is done the budget counts the real total_cost_usd instead.
const LLM_EST_USD_PER_MIN = 0.0015;
const LLM_EST_MIN_USD = 0.02;
// pricing.json is read with onError = continueRegularOutput: a missing or broken price file must not stop
// the service from accepting jobs, a rough estimate is enough for the budget check. Without the file, or
// for a model the file does not know, the STT price is the dearest known one (whisper-1), so the estimate
// errs on the side of the budget. Degrading beats refusing: an over-estimate frees itself when the job is done.
const STT_FALLBACK_USD_PER_MIN = 0.006;
const sttModel = String($env.STT_MODEL || 'whisper-1');
const sttPrices = pricing.stt || {};
const knownStt = Object.values(sttPrices).map((x) => Number((x || {}).per_minute) || 0).filter((x) => x > 0);
const sttPerMin = (sttPrices[sttModel] || {}).per_minute || (knownStt.length ? Math.max(...knownStt) : STT_FALLBACK_USD_PER_MIN);
const minutes = d / 60;
const sttCost = probe.recommended === 'subtitles_manual' ? 0 : minutes * sttPerMin;
const estimatedCost = Math.round((sttCost + Math.max(LLM_EST_MIN_USD, minutes * LLM_EST_USD_PER_MIN)) * 10000) / 10000;
const meta = { created_at: new Date().toISOString(), estimate_sec: estimate, estimated_cost_usd: estimatedCost, stages: [], probe: { recommended: probe.recommended, subtitles: probe.subtitles, language: probe.language } };
// Versions of the tools behind the probe (media service /sources/{id}, 2026-09-21): when an extractor breaks, old
// jobs must tell "yt-dlp broke" from "we broke" – yt-dlp, its EJS solver, the JS runtime and ffmpeg.
if (src.tools) meta.tools = src.tools;
if (languageOverride) meta.language_override = languageOverride;
return [{ json: {
  ok: true, id, duration_sec: probe.duration_sec,
  p_stages: JSON.stringify(stages), p_source: JSON.stringify(source), p_options: JSON.stringify(req.options), p_meta: JSON.stringify(meta),
  source_id: req.source_id, source_language: sourceLanguage, preset: req.preset, output_language: req.output_language,
  email: req.email || '-', // '-' = no email: the Postgres node drops empty query parameters
  consent: req.consent_152fz,
  estimated_cost_usd: estimatedCost,
} }];
"""

# Daily budget (contract sections 2, 7). One row: money spent in the last 24 hours plus money reserved by
# running jobs. "Running" = queued/processing created within MAX_JOB_MINUTES: nothing closes a job stuck in
# processing (no maintenance flow yet), so without the window one stuck job would hold its reserve forever.
# Spent counts every non-running job of the day as coalesce(total_cost_usd, sum of meta.stages[].cost_usd):
# a failed job has no total_cost_usd, only the stage costs it did pay (decision of 2026-09-09, j_hpopim) -
# this is the budget side of that debt. Running jobs count only their estimate, never their partial stage
# costs, so nothing is counted twice.
# Limits as data (infra/sql/003_settings.sql, decision 2026-09-16): a numeric row in settings wins over the
# variable passed as the parameter; no row, or a row that is not a number, means the variable. One helper per
# key, inlined into the queries that already run, so a limit change is one statement and needs no restart.
def setting_sql(key, param):
    return f"coalesce((select value::numeric from settings where key = '{key}' and value ~ '^[0-9]+(\\.[0-9]+)?$'), {param}::numeric)"

BUDGET_SQL = f"""with lim as (
  select {setting_sql('MAX_JOB_MINUTES', '$1')} as max_job_minutes,
         {setting_sql('DAILY_BUDGET_USD', '$2')} as budget_usd,
         {setting_sql('MAX_CONCURRENT_JOBS', '$3')} as max_concurrent,
         {setting_sql('MAX_DURATION_SEC', '$4')} as max_duration_sec,
         coalesce((select value from settings where key = 'TURNSTILE_MODE' and value in ('enforce', 'monitor', 'off')), $5::text) as turnstile_mode
), running as (
  select id from jobs
  where status in ('queued', 'processing') and created_at > now() - ((select max_job_minutes from lim) * interval '1 minute')
)
select
  coalesce(sum(case when j.id not in (select id from running) then coalesce(j.total_cost_usd,
    (select sum((s->>'cost_usd')::numeric) from jsonb_array_elements(coalesce(j.meta->'stages', '[]'::jsonb)) s)) end), 0) as spent_usd,
  coalesce(sum(case when j.id in (select id from running) then (j.meta->>'estimated_cost_usd')::numeric end), 0) as reserved_usd,
  (select count(*) from running) as running_jobs,
  (select budget_usd from lim) as budget_usd,
  (select max_concurrent from lim) as max_concurrent,
  (select max_duration_sec from lim) as max_duration_sec,
  (select max_job_minutes from lim) as max_job_minutes,
  (select turnstile_mode from lim) as turnstile_mode
from jobs j
where j.created_at > now() - interval '24 hours' or j.id in (select id from running)"""
BUDGET_PARAMS = "{{ [Number($env.MAX_JOB_MINUTES || 60), Number($env.DAILY_BUDGET_USD || 6), Number($env.MAX_CONCURRENT_JOBS || 2), Number($env.MAX_DURATION_SEC || 5400), ['enforce', 'monitor', 'off'].includes(String($env.TURNSTILE_MODE || '')) ? String($env.TURNSTILE_MODE) : 'monitor'] }}"
# /api/probe has no other query: one small read of the duration cap so the card honours a raised limit too.
LIMITS_SQL = f"select {setting_sql('MAX_DURATION_SEC', '$1')} as max_duration_sec"
LIMITS_PARAMS = "{{ [Number($env.MAX_DURATION_SEC || 5400)] }}"

CHECK_BUDGET_JS = TOO_LONG_JS + r"""// Duration cap, daily budget and concurrency checks, before the job is inserted (contract section 2).
// Order of refusals on creation: unknown_duration (Build job row) -> too_long -> daily_limit -> busy (here).
// daily_limit before busy: with the budget gone, "try again in a few minutes" would be misleading.
// The limits arrive with the budget row: settings table first, the variable second (Load budget).
const row = $('Build job row').first().json;
const sums = $input.first().json || {};
const maxSec = Number(sums.max_duration_sec) || Number($env.MAX_DURATION_SEC || 5400);
if (Number(row.duration_sec) > maxSec) return [{ json: { ok: false, ...tooLong(row.duration_sec, maxSec) } }];
const budget = Number(sums.budget_usd) || Number($env.DAILY_BUDGET_USD || 6);
const spent = Number(sums.spent_usd) || 0;
const reserved = Number(sums.reserved_usd) || 0;
const estimate = Number(row.estimated_cost_usd) || 0;
// The check and the insert are two statements, so two requests arriving together can both pass:
// the overrun is bounded by one job estimate. Accepted, an advisory lock is not worth it yet.
if (spent + reserved + estimate > budget) {
  return [{ json: { ok: false, statusCode: 429, body: { error: { code: 'daily_limit', message: `daily budget of the service is exhausted (spent ${spent.toFixed(2)} + reserved ${reserved.toFixed(2)} + this job ${estimate.toFixed(2)} > ${budget.toFixed(2)} USD); try again tomorrow` } } } }];
}
// Concurrency: running_jobs uses the same MAX_JOB_MINUTES window as the reserve, a job stuck in processing
// must not hold a slot forever. Same race as above: two requests together may both pass, one job over.
const maxConcurrent = sums.max_concurrent !== undefined && sums.max_concurrent !== null ? Number(sums.max_concurrent) : Number($env.MAX_CONCURRENT_JOBS || 2);
const running = Number(sums.running_jobs) || 0;
if (running >= maxConcurrent) {
  return [{ json: { ok: false, statusCode: 429, body: { error: { code: 'busy', message: `${running} of ${maxConcurrent} job slots are taken; try again in a few minutes` } } } }];
}
// The token travels with the row from here on (Build job row keeps only what the jobs row needs).
return [{ json: { ...row, turnstile_mode: ['enforce', 'monitor', 'off'].includes(String(sums.turnstile_mode)) ? String(sums.turnstile_mode) : 'monitor', turnstile_token: $('Validate job request').first().json.turnstile_token || null } }];
"""

# Turnstile (step E3, 2026-09-29): the token is verified after the budget and before the insert. Modes from the
# settings table (TURNSTILE_MODE, fallback the variable, default monitor): off – nothing checked, no events;
# monitor – the job is always created, a missing token or a refusal only writes an event; enforce – missing or
# refused is 403 bot_check_failed. In every mode an unreachable siteverify (no answer in 5 s) creates the job and
# writes turnstile_unreachable: a script cannot cause that, Cloudflare or our egress can. The secret comes from
# the Turnstile credential (custom auth, body.secret); remoteip is never sent – we do not process addresses.
TURNSTILE_SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
# Our replay guard (005_turnstile_used.sql): the hash is computed in SQL, the token itself never lands in a table.
# on conflict do nothing + alwaysOutputData: a duplicate yields an item without token_hash, not an empty branch.
TURNSTILE_USED_SQL = "with gc as (delete from turnstile_used where used_at < now() - interval '10 minutes') insert into turnstile_used (token_hash) values (encode(sha256(convert_to($1, 'utf8')), 'hex')) on conflict (token_hash) do nothing returning token_hash"
TURNSTILE_DECIDE_JS = r"""// Verdict on the Turnstile token: events for the table, and the 403 body in enforce mode.
const row = $('Check budget').first().json;
const mode = row.turnstile_mode || 'monitor';
const token = row.turnstile_token || null;
const HOSTS = String($env.TURNSTILE_HOSTNAMES || 'digest.inforobot.space,localhost,127.0.0.1').split(',').map((h) => h.trim().toLowerCase()).filter(Boolean);
let verify = null;
try { if ($('Turnstile verify').isExecuted) verify = $('Turnstile verify').first().json; } catch (e) { verify = null; }
// Our replay guard: Mark token used ran and returned no token_hash – the same token was verified before.
let duplicate = false;
try { if ($('Mark token used').isExecuted) duplicate = !(($('Mark token used').first().json || {}).token_hash); } catch (e) { duplicate = false; }
const events = [];
let refuse = null; // { code, message } for enforce
const ev = (type, body) => events.push({ type, level: 'warn', stage: 'create', provider: 'cloudflare', body: String(body).slice(0, 280) });
if (mode !== 'off') {
  // Wording: log-events masks «token <word>» as a credential, so these bodies avoid the word.
  if (!token) {
    ev('turnstile_missing', `Turnstile: POST /api/jobs without a response (mode ${mode}, source ${row.source_id})`);
    refuse = { code: 'bot_check_failed', message: 'the browser check did not complete; reload the page and try again' };
  } else if (duplicate) {
    ev('turnstile_failed', `Turnstile: the same response was verified before (mode ${mode}), error-codes=duplicate`);
    refuse = { code: 'bot_check_failed', message: 'the browser check was already used; reload the page and try again' };
  } else if (!verify || !verify.statusCode) {
    ev('turnstile_unreachable', `siteverify gave no answer (mode ${mode}): ${String((verify && (verify.error && verify.error.message || verify.error)) || 'no response').slice(0, 160)}`);
  } else if (verify.statusCode !== 200) {
    ev('turnstile_unreachable', `siteverify answered HTTP ${verify.statusCode} (mode ${mode})`);
  } else {
    const b = verify.body || {};
    const hostOk = HOSTS.includes(String(b.hostname || '').toLowerCase());
    const actionOk = b.action === 'create_job';
    if (b.success === true && hostOk && actionOk) {
      // accepted
    } else {
      const codes = Array.isArray(b['error-codes']) ? b['error-codes'].join(',') : '';
      ev('turnstile_failed', `siteverify refused (mode ${mode}): success=${b.success === true}, action=${b.action || '-'}, hostname=${b.hostname || '-'}, error-codes=${codes || '-'}`);
      refuse = { code: 'bot_check_failed', message: 'the browser check failed; reload the page and try again' };
    }
  }
}
const ok = mode !== 'enforce' || !refuse;
// Events of a created job carry its id (the day-of-post analysis joins them to jobs); a refusal has no job.
return [{ json: { ...row, ok, statusCode: ok ? undefined : 403, body: ok ? undefined : { error: refuse }, events, job_id: ok ? row.id : '-' } }];
"""
def turnstile_verify_node(x, y):
    return node("Turnstile verify", "n8n-nodes-base.httpRequest", 4.5, {
        "method": "POST", "url": TURNSTILE_SITEVERIFY,
        "authentication": "genericCredentialType", "genericAuthType": "httpCustomAuth",
        "sendBody": True, "contentType": "form-urlencoded", "specifyBody": "keypair",
        "bodyParameters": {"parameters": [{"name": "response", "value": "={{ $('Check budget').first().json.turnstile_token }}"}]},
        "options": {"timeout": 5000, "response": {"response": {"fullResponse": True, "neverError": True, "responseFormat": "json"}}},
    }, x, y, credentials={"httpCustomAuth": {"name": "Turnstile"}}, onError="continueRegularOutput")

FORMAT_STATUS_JS = r"""// GET /api/jobs/{job_id} response (contract section 2).
const row = $input.first().json;
if (!row || !row.id) return [{ json: { statusCode: 404, body: { error: { code: 'not_found', message: 'job not found' } } } }];
const s = row.source || {};
const meta = row.meta || {};
const ms = Object.fromEntries((meta.stages || []).map((st) => [st.name, st.ms]));
const stages = (row.stages || []).map((st) => (st.status === 'done' && ms[st.name] !== undefined ? { ...st, ms: ms[st.name] } : st));
const iso = (t) => (t ? new Date(t).toISOString() : null);
return [{ json: { statusCode: 200, body: {
  job_id: row.id, status: row.status, created_at: iso(row.created_at), finished_at: iso(row.finished_at),
  estimate_sec: meta.estimate_sec ?? null, preset: row.preset, options: row.options || [], email: row.email || null,
  stages,
  source: { title: s.title, duration_sec: s.duration_sec, thumbnail_url: s.thumbnail_url, platform: s.platform, language: s.language, url: s.url || null },
  result: row.result, error: row.error,
} } }];
"""

ESTIMATE_JS = TOO_LONG_JS + r"""// Pass the media-service answer through and add the estimate (contract section 2).
// The item in hand is the Load limits row (duration cap: settings table first, variable second, and the variable
// again when the read failed – the row then carries an error and no value); the media answer is one node back, on
// whichever branch ran (a reference to the branch that did not run throws).
const maxSec = Number(($input.first().json || {}).max_duration_sec) || Number($env.MAX_DURATION_SEC || 5400);
let resp;
try { resp = $('Media upload').first().json; } catch (e) { resp = $('Media probe').first().json; }
if (resp.statusCode !== 200) return [{ json: { statusCode: resp.statusCode, body: resp.body } }];
const p = resp.body;
if (!(Number(p.duration_sec) > 0)) return [{ json: unknownDuration() }];
if (p.duration_sec > maxSec) return [{ json: tooLong(p.duration_sec, maxSec) }];
// Rule 1.1 of docs/result-schema.md: with manual subtitles their language is the video language.
// yt-dlp metadata said "en" for a video whose only manual track is "ru"; the pipeline then asked
// for en subtitles and failed. The card shows the corrected language.
const manual = ((p.subtitles || {}).manual) || [];
if (manual.length && !manual.includes(p.language)) p.language = manual[0];
const strategy = p.recommended === 'subtitles_manual' ? 'subtitles' : 'transcribe';
const d = p.duration_sec || 0;
const seconds = strategy === 'subtitles' ? 60 : Math.round(d * 0.08 + 60);
// Per-option additions measured on the 2026-09-06 runs (gpt-4o-mini ~15 s per extraction block,
// gpt-4.1 critique ~30 s).
const per_option = { glossary: 15, critique: 30, self_check: 15, action_items: 15, decisions: 15, questions: 15 };
return [{ json: { statusCode: 200, body: { ...p, estimate: { seconds, strategy, per_option } } } }];
"""

INSERT_SQL = """insert into jobs (id, status, stages, source_id, source, source_language, preset, output_language, options, email, consent_152fz, meta)
values ($1, 'queued', $2::jsonb, $3, $4::jsonb, $5, $6, $7, array(select jsonb_array_elements_text($8::jsonb)), nullif($9, '-'), $10::boolean, $11::jsonb)
returning id"""
# GET /api/limits (contract section 2, step E4, 2026-09-30): the numbers the form prints and checks before an upload.
# max_duration_sec – settings table first, variable second (the same LIMITS_SQL as /api/probe); upload_max_mb – the
# variable only: nginx reads it from .env, a settings row would show a number nginx does not enforce. A failed
# read (database down) still answers with the variables: the form must not depend on this call.
LIMITS_BODY_JS = r"""const row = $input.first().json || {};
const max_duration_sec = Number(row.max_duration_sec) || Number($env.MAX_DURATION_SEC || 5400);
const upload_max_mb = Number($env.UPLOAD_MAX_MB || 200);
return [{ json: { statusCode: 200, body: { max_duration_sec, upload_max_mb } } }];
"""

INSERT_PARAMS = "{{ [$json.id, $json.p_stages, $json.source_id, $json.p_source, $json.source_language, $json.preset, $json.output_language, $json.p_options, $json.email, $json.consent, $json.p_meta] }}"

jobs_nodes = [
    # --- POST /probe
    node("Webhook probe", "n8n-nodes-base.webhook", 2.1, {"httpMethod": "POST", "path": "probe", "responseMode": "responseNode", "options": {}}, 0, 0, webhookId="6f1c5a1e-probe-0000-0000-000000000001"),
    if_bool("Has file?", "{{ Object.keys($binary || {}).length > 0 }}", 220, 0),
    http("Media upload", "POST", "{{ $env.MEDIA_URL }}/upload", 460, -100, multipart=True),
    http("Media probe", "POST", "{{ $env.MEDIA_URL }}/probe", 460, 100, json_body="{{ JSON.stringify({ url: $json.body.url }) }}"),
    # /api/probe never depended on the database before this node: a failed read (table missing, database down)
    # must not fail the probe – onError turns it into an item without max_duration_sec and Add estimate falls
    # back to the variable.
    pg("Load limits", LIMITS_SQL, LIMITS_PARAMS, 700, 0, onError="continueRegularOutput"),
    code("Add estimate", ESTIMATE_JS, 920, 0),
    respond("Respond probe", "{{ $json.body }}", "={{ $json.statusCode }}", 1140, 0),
    # --- POST /jobs
    node("Webhook jobs", "n8n-nodes-base.webhook", 2.1, {"httpMethod": "POST", "path": "jobs", "responseMode": "responseNode", "options": {}}, 0, 400, webhookId="6f1c5a1e-jobs0-0000-0000-000000000002"),
    code("Validate job request", VALIDATE_JS, 220, 400),
    if_bool("Request valid?", "{{ $json.ok }}", 440, 400),
    http("Media source", "GET", "{{ $env.MEDIA_URL }}/sources/{{ $json.source_id }}", 660, 400),
    # pricing.json is mounted into the container (compose); the same file the pipeline uses for meta.stages.
    # A missing or broken price file degrades the estimate (see Build job row), it does not block job creation:
    # alwaysOutputData because a selector that matches no file yields zero items (not an error) and would end
    # the run silently; onError for an unreadable or invalid file.
    node("Read pricing", "n8n-nodes-base.readWriteFile", 1, {"operation": "read", "fileSelector": "/data/pricing.json", "options": {}}, 880, 400, alwaysOutputData=True, onError="continueRegularOutput"),
    node("Parse pricing", "n8n-nodes-base.extractFromFile", 1, {"operation": "fromJson", "binaryPropertyName": "data", "options": {}}, 1100, 400, alwaysOutputData=True, onError="continueRegularOutput"),
    code("Build job row", BUILD_ROW_JS, 1320, 400),
    if_bool("Source known?", "{{ $json.ok }}", 1540, 400),
    pg("Load budget", BUDGET_SQL, BUDGET_PARAMS, 1760, 400),
    code("Check budget", CHECK_BUDGET_JS, 1980, 400),
    if_bool("Budget ok?", "{{ $json.ok }}", 2200, 400),
    if_bool("Verify needed?", "{{ $json.turnstile_mode !== 'off' && !!$json.turnstile_token }}", 2420, 200),
    pg("Mark token used", TURNSTILE_USED_SQL, "{{ [$json.turnstile_token] }}", 2640, 0, alwaysOutputData=True),
    if_bool("Token new?", "{{ !!$json.token_hash }}", 2860, 0),
    turnstile_verify_node(3080, -100),
    code("Turnstile decide", TURNSTILE_DECIDE_JS, 2860, 200),
    log_events("Log turnstile", 3080, 200),
    if_bool("Turnstile ok?", "{{ $json.ok }}", 3300, 200),
    pg("Insert job", INSERT_SQL, INSERT_PARAMS, 2420, 400),
    respond("Respond 202", "{{ { job_id: $json.id, status: 'queued', url: '/jobs/' + $json.id } }}", 202, 2640, 400),
    node("Start pipeline", "n8n-nodes-base.executeWorkflow", 1.3, {
        "workflowId": {"__rl": True, "value": "", "mode": "list", "cachedResultName": "pipeline"},
        "workflowInputs": {"mappingMode": "defineBelow", "value": {"job_id": "={{ $json.id }}"}, "matchingColumns": ["job_id"],
                           "schema": [{"id": "job_id", "displayName": "job_id", "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "string", "removed": False}],
                           "attemptToConvertTypes": False, "convertFieldsToString": True},
        "options": {"waitForSubWorkflow": False}}, 2860, 400),
    respond("Respond error", "{{ $json.body }}", "={{ $json.statusCode }}", 2200, 620),
    # --- GET /jobs/:job_id
    # Static path on purpose: n8n prefixes paths with ':params' by the node's webhookId, which breaks /api/jobs/{id}.
    node("Webhook job status", "n8n-nodes-base.webhook", 2.1, {"httpMethod": "GET", "path": "job-status", "responseMode": "responseNode", "options": {}}, 0, 900, webhookId="6f1c5a1e-jobs1-0000-0000-000000000003"),
    pg("Load job", "select j.id, j.status, j.stages, j.source, j.result, j.error, j.meta, j.preset, j.options, j.email, j.created_at, j.finished_at from (select 1) one left join jobs j on j.id = $1", "{{ $json.query.job_id || '-' }}", 220, 900),
    code("Format status", FORMAT_STATUS_JS, 440, 900),
    respond("Respond status", "{{ $json.body }}", "={{ $json.statusCode }}", 660, 900, no_store=True),
    # --- GET /limits
    node("Webhook limits", "n8n-nodes-base.webhook", 2.1, {"httpMethod": "GET", "path": "limits", "responseMode": "responseNode", "options": {}}, 0, 4100, webhookId="6f1c5a1e-limit-0000-0000-000000000008"),
    pg("Load limits for page", LIMITS_SQL, LIMITS_PARAMS, 220, 4100, onError="continueRegularOutput"),
    code("Limits body", LIMITS_BODY_JS, 440, 4100),
    respond("Respond limits", "{{ $json.body }}", 200, 660, 4100, no_store=True),
]
jc = {}
wire(jc, "Webhook probe", "Has file?")
wire(jc, "Has file?", "Media upload", 0)
wire(jc, "Has file?", "Media probe", 1)
wire(jc, "Media upload", "Load limits")
wire(jc, "Media probe", "Load limits")
wire(jc, "Load limits", "Add estimate")
wire(jc, "Add estimate", "Respond probe")
wire(jc, "Webhook limits", "Load limits for page"); wire(jc, "Load limits for page", "Limits body"); wire(jc, "Limits body", "Respond limits")
wire(jc, "Webhook jobs", "Validate job request")
wire(jc, "Validate job request", "Request valid?")
wire(jc, "Request valid?", "Media source", 0)
wire(jc, "Request valid?", "Respond error", 1)
wire(jc, "Media source", "Read pricing")
wire(jc, "Read pricing", "Parse pricing")
wire(jc, "Parse pricing", "Build job row")
wire(jc, "Build job row", "Source known?")
wire(jc, "Source known?", "Load budget", 0)
wire(jc, "Load budget", "Check budget")
wire(jc, "Check budget", "Budget ok?")
wire(jc, "Budget ok?", "Verify needed?", 0)
wire(jc, "Budget ok?", "Respond error", 1)
wire(jc, "Verify needed?", "Mark token used", 0); wire(jc, "Verify needed?", "Turnstile decide", 1); wire(jc, "Mark token used", "Token new?")
wire(jc, "Token new?", "Turnstile verify", 0); wire(jc, "Token new?", "Turnstile decide", 1); wire(jc, "Turnstile verify", "Turnstile decide")
wire(jc, "Turnstile decide", "Log turnstile"); wire(jc, "Log turnstile", "Turnstile ok?"); wire(jc, "Turnstile ok?", "Insert job", 0); wire(jc, "Turnstile ok?", "Respond error", 1)
wire(jc, "Source known?", "Respond error", 1)
wire(jc, "Insert job", "Respond 202")
wire(jc, "Respond 202", "Start pipeline")
wire(jc, "Webhook job status", "Load job")
wire(jc, "Load job", "Format status")
wire(jc, "Format status", "Respond status")

# --- GET /api/jobs/{id}/export/{format} and GET /api/jobs/{id}/media (nginx rewrites to static webhooks)
EXPORT_PREPARE_JS = r"""// Build md / srt / html from jobs.result (docs/result-schema.md section 8).
const q = $('Webhook export').first().json.query || {};
const row = $input.first().json;
const fmt = String(q.format || '');
const FORMATS = ['digest.md', 'transcript.md', 'transcript.srt', 'digest.html', 'digest.pdf', 'all.zip'];
if (!row || !row.id) return [{ json: { error: true, statusCode: 404, body: { error: { code: 'not_found', message: 'job not found' } } } }];
if (!FORMATS.includes(fmt)) return [{ json: { error: true, statusCode: 400, body: { error: { code: 'bad_format', message: `format must be one of ${FORMATS.join(', ')}` } } } }];
// done without a result: expired by the maintenance flow (contract section 4); 410, not 409, the file will not come back.
if (row.status === 'done' && !row.result) return [{ json: { error: true, statusCode: 410, body: { error: { code: 'gone', message: 'result removed after the retention period' } } } }];
if (row.status !== 'done') return [{ json: { error: true, statusCode: 409, body: { error: { code: 'not_ready', message: `job is ${row.status}` } } } }];
const r = row.result;
const src = r.source;
const hms = (t) => { t = Math.max(0, Math.round(Number(t))); const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60; return (h ? `${h}:` : '') + `${h ? String(m).padStart(2, '0') : m}:${String(s).padStart(2, '0')}`; };
const link = (t) => {
  const sec = Math.max(0, Math.floor(Number(t)));
  if (src.platform === 'youtube' && src.url) return `[${hms(t)}](${src.url}${src.url.includes('?') ? '&' : '?'}t=${sec}s)`;
  if ((src.platform === 'vk' || src.platform === 'rutube') && src.url) return `[${hms(t)}](${src.url}${src.url.includes('?') ? '&' : '?'}t=${sec})`;
  return `[${hms(t)}]`;
};
const esc = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const EXTRAS_TITLES = { glossary: 'Глоссарий', self_check: 'Вопросы для самопроверки', critique: 'Критика аргументации', decisions: 'Решения', action_items: 'Задачи', questions: 'Открытые вопросы' };
const ex = r.extras || {};
const md = [];
md.push(`# ${r.source.title}`, '', `Источник: ${src.url ? src.url : 'загруженный файл'} · ${hms(src.duration_sec)} · ${src.platform}`, '', '## Коротко', '', r.digest.tldr, '', '## Структура', '');
for (const p of r.digest.structure) md.push(`- ${link(p.start)} **${p.title}** — ${p.summary}`);
md.push('', '## Тезисы', '');
r.digest.key_points.forEach((k, i) => md.push(`${i + 1}. **${k.text}** ${link(k.start)}`, `   ${k.detail}`, ''));
md.push('## Цитаты', '');
for (const qt of r.digest.quotes) md.push(`> ${qt.text}${qt.translation ? `\n> — ${qt.translation}` : ''} ${link(qt.start)}`, '');
for (const key of Object.keys(EXTRAS_TITLES)) {
  const v = ex[key]; if (!v) continue;
  md.push(`## ${EXTRAS_TITLES[key]}`, '');
  if (key === 'glossary') for (const g of v) md.push(`- **${g.term}** — ${g.definition} ${link(g.start)}`);
  else if (key === 'self_check') v.forEach((s, i) => md.push(`${i + 1}. ${s.question} ${link(s.start)}`, `   *${s.answer}*`, ''));
  else if (key === 'critique') { md.push('**Сильные стороны**', ''); for (const x of v.strong) md.push(`- ${x}`); md.push('', '**Слабые места**', ''); for (const w of v.weak) md.push(`- ${w.claim} ${link(w.start)}`, `  ${w.issue}`); md.push('', '**Чего не хватает**', ''); for (const x of v.missing) md.push(`- ${x}`); }
  else if (key === 'action_items') for (const a of v) md.push(`- ${a.text}${a.owner ? ` — ${a.owner}` : ''}${a.due ? `, ${a.due}` : ''} ${link(a.start)}`);
  else for (const x of v) md.push(`- ${x.text} ${link(x.start)}`);
  md.push('');
}
const finishedText = new Date(r.meta.finished_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).replace(/\s*г\.$/, '');
// result.notices, the same wording as the page: number and places, never the text of what was lost.
const NOTICE = { transcript_shortened: (n) => `Транскрипт мог быть сокращён: при очистке речи модель местами убирает больше, чем слова-паразиты; в ${n} ${n % 10 === 1 && n % 100 !== 11 ? 'месте' : 'местах'} текст мог остаться короче сказанного`, clean_fallback: (n) => `На ${n} ${n === 1 ? 'участке' : 'участках'} речь очищена программно, без модели: слова-паразиты убраны, предложения могли остаться менее гладкими` };
const noticeLines = (r.notices || []).map((n) => `> ${(NOTICE[n.kind] || ((k) => `${n.kind}: ${k}`))(n.places)}. Места: ${n.starts.map((t) => link(t)).join(' ')}`);
if (noticeLines.length) md.push('', ...noticeLines.flatMap((l) => [l, '']));
md.push('---', `Video Digest · ${finishedText}`);
const digestMd = md.join('\n') + '\n';
const transcriptMd = [`# ${r.source.title} — транскрипт`, '', ...noticeLines.flatMap((l) => [l, '']), ...r.transcript.clean.map((p) => `**[${hms(p.start)}]** ${p.text}\n`)].join('\n');
const srtTime = (t) => { const ms = Math.round(Number(t) * 1000); const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000), s = Math.floor((ms % 60000) / 1000), f = ms % 1000; return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(f).padStart(3, '0')}`; };
const srt = r.transcript.segments.map((sg, i) => `${i + 1}\n${srtTime(sg.start)} --> ${srtTime(sg.end)}\n${sg.text}\n`).join('\n') + '\n';
// html: a small markdown-to-html for the subset we emit (headings, lists, bold, blockquote, links)
const inline = (t) => esc(t).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>').replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2">$1</a>');
const htmlBody = [];
let list = null;
const closeList = () => { if (list) { htmlBody.push(`</${list}>`); list = null; } };
for (const line of digestMd.split('\n')) {
  if (/^# /.test(line)) { closeList(); htmlBody.push(`<h1>${inline(line.slice(2))}</h1>`); }
  else if (/^## /.test(line)) { closeList(); htmlBody.push(`<h2>${inline(line.slice(3))}</h2>`); }
  else if (/^- /.test(line)) { if (list !== 'ul') { closeList(); htmlBody.push('<ul>'); list = 'ul'; } htmlBody.push(`<li>${inline(line.slice(2))}</li>`); }
  else if (/^\d+\. /.test(line)) { if (list !== 'ol') { closeList(); htmlBody.push('<ol>'); list = 'ol'; } htmlBody.push(`<li>${inline(line.replace(/^\d+\. /, ''))}</li>`); }
  else if (/^   /.test(line) && list) { htmlBody[htmlBody.length - 1] = htmlBody[htmlBody.length - 1].replace(/<\/li>$/, `<br><span class="detail">${inline(line.trim())}</span></li>`); }
  else if (/^> /.test(line)) { closeList(); htmlBody.push(`<blockquote>${inline(line.slice(2))}</blockquote>`); }
  else if (line === '---') { closeList(); htmlBody.push('<hr>'); }
  else if (line.trim()) { closeList(); htmlBody.push(`<p>${inline(line)}</p>`); }
}
closeList();
const html = `<!doctype html><html lang="${r.output_language}"><head><meta charset="utf-8"><title>${esc(r.source.title)}</title><style>body{font-family:Georgia,serif;max-width:760px;margin:40px auto;padding:0 20px;line-height:1.5;color:#222}h1{font-size:1.6em}h2{font-size:1.2em;margin-top:1.6em;border-bottom:1px solid #ddd}blockquote{border-left:3px solid #999;margin:0.6em 0;padding:0.2em 1em;color:#444}a{color:#1a5fb4;text-decoration:none}.detail{color:#555}hr{border:0;border-top:1px solid #ddd;margin-top:2em}</style></head><body>${htmlBody.join('\n')}</body></html>`;
// result.json: speaker numbers are local to a 600-second chunk (19 numbers on a meeting of fewer than ten people,
// a new number for the same voice at every boundary) – labels that look like attribution and are not are worse
// than none, so the export carries speaker: null until the numbering is continuous (decision 2026-09-17).
const tr = r.transcript || {};
const exported = { ...r, transcript: { ...tr, segments: (tr.segments || []).map((sg) => ({ ...sg, speaker: null })) } };
return [{ json: { error: false, format: fmt, job_id: row.id, digest_md: digestMd, transcript_md: transcriptMd, srt, html, result_json: JSON.stringify(exported, null, 2) } }];
"""

FILES_JS = r"""// Build the export files as binaries (Convert to File drops the item json, a Code node keeps both).
const p = $('Export prepare').first().json;
const bin = (text, fileName, mimeType) => ({ data: Buffer.from(String(text), 'utf8').toString('base64'), fileName, mimeType, fileExtension: fileName.split('.').pop() });
return [{ json: { job_id: p.job_id, format: p.format }, binary: {
  md: bin(p.digest_md, 'digest.md', 'text/markdown; charset=utf-8'),
  tmd: bin(p.transcript_md, 'transcript.md', 'text/markdown; charset=utf-8'),
  srt: bin(p.srt, 'transcript.srt', 'application/x-subrip; charset=utf-8'),
  html: bin(p.html, 'index.html', 'text/html; charset=utf-8'),   // Gotenberg needs index.html
  dhtml: bin(p.html, 'digest.html', 'text/html; charset=utf-8'),
  json: bin(p.result_json, 'result.json', 'application/json; charset=utf-8'),
} }];
"""

def to_file(name, source, binary, file_name, x, y):
    return code(name, FILES_JS, x, y)

def respond_file(name, prop, x, y):
    return node(name, "n8n-nodes-base.respondToWebhook", 1.5, {"respondWith": "binary", "responseDataSource": "set", "inputFieldName": prop,
        "options": {"responseHeaders": {"entries": [
            {"name": "Content-Disposition", "value": "=attachment; filename=\"{{ $('Export prepare').first().json.job_id }}-{{ $('Export prepare').first().json.format }}\""},
            {"name": "Content-Type", "value": "={{ $binary['" + prop + "'].mimeType }}"}]}}}, x, y)

MEDIA_ROUTE_JS = r"""// Playback for uploads only: hand the file over to nginx via X-Accel-Redirect (Range stays native).
const row = $input.first().json;
if (!row || !row.id) return [{ json: { statusCode: 404, body: { error: { code: 'not_found', message: 'job not found' } } } }];
const pb = ((row.source || {}).playback) || {};
if (pb.kind !== 'audio') return [{ json: { statusCode: 404, body: { error: { code: 'no_media', message: 'playback is served by the platform player; use source.playback.url' } } } }];
return [{ json: { statusCode: 200, redirect: `/media-internal/${row.source_id}/playback.mp3` } }];
"""

RETRY_PREPARE_JS = r"""// POST /api/jobs/{id}/retry: same parameters, new job (contract section 2).
const row = $input.first().json;
if (!row || !row.id) return [{ json: { ok: false, statusCode: 404, body: { error: { code: 'not_found', message: 'job not found' } } } }];
const src = row.source || {};
if (row.status !== 'failed' && !(row.status === 'done' && !row.result)) return [{ json: { ok: false, statusCode: 409, body: { error: { code: 'not_retryable', message: `job is ${row.status}` } } } }];
if (!src.url) return [{ json: { ok: false, statusCode: 410, body: { error: { code: 'source_gone', message: 'uploaded file is no longer available; upload it again' } } } }];
return [{ json: { ok: true, url: src.url, source_id: row.source_id, preset: row.preset, source_language: row.source_language, output_language: row.output_language, options: row.options || [], email: row.email || null, consent_152fz: row.consent_152fz === true } }];
"""

RETRY_BODY_JS = r"""// Re-probe done: build the POST /api/jobs body the regular validation understands.
const prev = $('Retry prepare').first().json;
const resp = $input.first().json;
if (resp.statusCode !== 200) {
  const err = (resp.body && resp.body.error) || { code: 'probe_failed', message: `probe returned ${resp.statusCode}` };
  return [{ json: { ok: false, statusCode: resp.statusCode === 403 ? 403 : 502, body: { error: err } } }];
}
const body = { source_id: resp.body.source_id, source_language: prev.source_language, preset: prev.preset, output_language: prev.output_language, options: prev.options };
if (prev.email) { body.email = prev.email; body.consent_152fz = prev.consent_152fz; }
return [{ json: { body } }];
"""

jobs_nodes += [
    node("Webhook retry", "n8n-nodes-base.webhook", 2.1, {"httpMethod": "POST", "path": "job-retry", "responseMode": "responseNode", "options": {}}, 0, 2700, webhookId="6f1c5a1e-retry-0000-0000-000000000007"),
    pg("Load job for retry", "select j.id, j.status, j.result, j.source, j.source_id, j.preset, j.source_language, j.output_language, j.options, j.email, j.consent_152fz from (select 1) one left join jobs j on j.id = $1", "{{ $json.query.job_id || '-' }}", 220, 2700),
    code("Retry prepare", RETRY_PREPARE_JS, 440, 2700),
    if_bool("Retryable?", "{{ $json.ok }}", 660, 2700),
    http("Media re-probe", "POST", "{{ $env.MEDIA_URL }}/probe", 880, 2700, json_body="{{ JSON.stringify({ url: $json.url }) }}"),
    code("Retry body", RETRY_BODY_JS, 1100, 2700),
    if_bool("Re-probe ok?", "{{ $json.ok !== false }}", 1320, 2700),
    respond("Respond retry error", "{{ $json.body }}", "={{ $json.statusCode }}", 880, 2900),
]
wire(jc, "Webhook retry", "Load job for retry"); wire(jc, "Load job for retry", "Retry prepare"); wire(jc, "Retry prepare", "Retryable?")
wire(jc, "Retryable?", "Media re-probe", 0); wire(jc, "Retryable?", "Respond retry error", 1)
wire(jc, "Media re-probe", "Retry body"); wire(jc, "Retry body", "Re-probe ok?")
wire(jc, "Re-probe ok?", "Validate job request", 0); wire(jc, "Re-probe ok?", "Respond retry error", 1)

jobs_nodes += [
    node("Webhook export", "n8n-nodes-base.webhook", 2.1, {"httpMethod": "GET", "path": "job-export", "responseMode": "responseNode", "options": {}}, 0, 1300, webhookId="6f1c5a1e-expo0-0000-0000-000000000005"),
    pg("Load job for export", "select j.id, j.status, j.result from (select 1) one left join jobs j on j.id = $1", "{{ $json.query.job_id || '-' }}", 220, 1300),
    code("Export prepare", EXPORT_PREPARE_JS, 440, 1300),
    if_bool("Export error?", "{{ $json.error }}", 660, 1300),
    code("Export files", FILES_JS, 1100, 1300),
    node("Export by format", "n8n-nodes-base.switch", 3.4, {"rules": {"values": [
        {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2}, "conditions": [{"id": "g1", "leftValue": "={{ $json.format }}", "rightValue": "digest.md", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}, "renameOutput": True, "outputKey": "digest.md"},
        {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2}, "conditions": [{"id": "g2", "leftValue": "={{ $json.format }}", "rightValue": "transcript.md", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}, "renameOutput": True, "outputKey": "transcript.md"},
        {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2}, "conditions": [{"id": "g3", "leftValue": "={{ $json.format }}", "rightValue": "transcript.srt", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}, "renameOutput": True, "outputKey": "transcript.srt"},
        {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2}, "conditions": [{"id": "g4", "leftValue": "={{ $json.format }}", "rightValue": "digest.html", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}, "renameOutput": True, "outputKey": "digest.html"},
        {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2}, "conditions": [{"id": "g5", "leftValue": "={{ $json.format }}", "rightValue": "digest.pdf", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}, "renameOutput": True, "outputKey": "digest.pdf"},
        {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2}, "conditions": [{"id": "g6", "leftValue": "={{ $json.format }}", "rightValue": "all.zip", "operator": {"type": "string", "operation": "equals"}}], "combinator": "and"}, "renameOutput": True, "outputKey": "all.zip"},
    ]}, "options": {}}, 1320, 1300),
    respond_file("Respond digest.md", "md", 1540, 1000), respond_file("Respond transcript.md", "tmd", 1540, 1150),
    respond_file("Respond transcript.srt", "srt", 1540, 1300), respond_file("Respond digest.html", "dhtml", 1540, 1450),
    node("Gotenberg pdf", "n8n-nodes-base.httpRequest", 4.5, {"method": "POST", "url": "={{ $env.GOTENBERG_URL || 'http://gotenberg:3000' }}/forms/chromium/convert/html",
        "sendBody": True, "contentType": "multipart-form-data", "bodyParameters": {"parameters": [{"parameterType": "formBinaryData", "name": "files", "inputDataFieldName": "html"}, {"name": "marginTop", "value": "0.6"}, {"name": "marginBottom", "value": "0.6"}]},
        "options": {"timeout": 60000, "response": {"response": {"responseFormat": "file", "outputPropertyName": "pdf"}}}}, 1320, 1700),
    respond_file("Respond digest.pdf", "pdf", 1760, 1700),
    # zip: all text files + pdf + result.json
    node("Zip pdf", "n8n-nodes-base.httpRequest", 4.5, {"method": "POST", "url": "={{ $env.GOTENBERG_URL || 'http://gotenberg:3000' }}/forms/chromium/convert/html",
        "sendBody": True, "contentType": "multipart-form-data", "bodyParameters": {"parameters": [{"parameterType": "formBinaryData", "name": "files", "inputDataFieldName": "html"}, {"name": "marginTop", "value": "0.6"}, {"name": "marginBottom", "value": "0.6"}]},
        "options": {"timeout": 60000, "response": {"response": {"responseFormat": "file", "outputPropertyName": "pdf"}}}}, 2200, 1900),
    node("Zip files + pdf", "n8n-nodes-base.merge", 3.2, {"mode": "combine", "combineBy": "combineByPosition", "options": {"includeUnpaired": False}}, 2420, 1980),
    code("Name pdf", "// Gotenberg names the pdf with a uuid; the archive needs digest.pdf.\nconst items = $input.all();\nif (items[0].binary && items[0].binary.pdf) items[0].binary.pdf.fileName = 'digest.pdf';\nreturn items;", 2540, 1980),
    node("Make zip", "n8n-nodes-base.compression", 1.1, {"operation": "compress", "binaryPropertyName": "md,tmd,srt,dhtml,json,pdf", "outputFormat": "zip", "fileName": "={{ $('Export prepare').first().json.job_id }}-all.zip", "binaryPropertyOutput": "zip"}, 2700, 1980),
    respond_file("Respond all.zip", "zip", 2860, 1980),
    respond("Respond export error", "{{ $json.body }}", "={{ $json.statusCode }}", 880, 1500),
    # media
    node("Webhook media", "n8n-nodes-base.webhook", 2.1, {"httpMethod": "GET", "path": "job-media", "responseMode": "responseNode", "options": {}}, 0, 2300, webhookId="6f1c5a1e-media-0000-0000-000000000006"),
    pg("Load job for media", "select j.id, j.source_id, j.source from (select 1) one left join jobs j on j.id = $1", "{{ $json.query.job_id || '-' }}", 220, 2300),
    code("Media route", MEDIA_ROUTE_JS, 440, 2300),
    if_bool("Media available?", "{{ $json.statusCode === 200 }}", 660, 2300),
    node("Respond media redirect", "n8n-nodes-base.respondToWebhook", 1.5, {"respondWith": "noData", "options": {"responseCode": 200, "responseHeaders": {"entries": [{"name": "X-Accel-Redirect", "value": "={{ $json.redirect }}"}, {"name": "Content-Type", "value": "audio/mpeg"}]}}}, 880, 2200),
    respond("Respond media error", "{{ $json.body }}", "={{ $json.statusCode }}", 880, 2400),
]
wire(jc, "Webhook export", "Load job for export"); wire(jc, "Load job for export", "Export prepare"); wire(jc, "Export prepare", "Export error?")
wire(jc, "Export error?", "Respond export error", 0); wire(jc, "Export error?", "Export files", 1); wire(jc, "Export files", "Export by format")
for i, (fmt, prop) in enumerate([("digest.md", "md"), ("transcript.md", "tmd"), ("transcript.srt", "srt"), ("digest.html", "html")]):
    wire(jc, "Export by format", f"Respond {fmt}", i)
wire(jc, "Export by format", "Gotenberg pdf", 4); wire(jc, "Gotenberg pdf", "Respond digest.pdf")
wire(jc, "Export by format", "Zip files + pdf", 5, 0); wire(jc, "Export by format", "Zip pdf", 5); wire(jc, "Zip pdf", "Zip files + pdf", 0, 1); wire(jc, "Zip files + pdf", "Name pdf"); wire(jc, "Name pdf", "Make zip"); wire(jc, "Make zip", "Respond all.zip")
wire(jc, "Webhook media", "Load job for media"); wire(jc, "Load job for media", "Media route"); wire(jc, "Media route", "Media available?")
wire(jc, "Media available?", "Respond media redirect", 0); wire(jc, "Media available?", "Respond media error", 1)

# --- POST /api/feedback (2026-09-23, step E2): UMUX-Lite, one answer per job, see docs/contract-api.md section 2.
VALIDATE_FEEDBACK_JS = r"""// Validate POST /api/feedback per docs/contract-api.md section 2.
const body = $input.first().json.body || {};
const fail = (code, message, status = 400) => [{ json: { ok: false, statusCode: status, body: { error: { code, message } } } }];
const score = (v) => Number.isInteger(v) && v >= 1 && v <= 5;
if (!/^j_[a-z0-9]{6}$/.test(String(body.job_id || ''))) return fail('validation_error', 'job_id must be a job id like j_abc123');
if (!score(body.fits)) return fail('validation_error', 'fits must be an integer from 1 to 5');
if (!score(body.easy)) return fail('validation_error', 'easy must be an integer from 1 to 5');
const comment = body.comment === undefined || body.comment === null ? '' : String(body.comment).trim();
if (comment.length > 500) return fail('validation_error', 'comment must be at most 500 characters');
const via = body.via === undefined ? 'button' : String(body.via);
if (!['timer', 'button'].includes(via)) return fail('validation_error', "via must be 'timer' or 'button'");
// '-' stands for an empty comment: the Postgres node drops empty query parameters.
return [{ json: { ok: true, job_id: body.job_id, fits: body.fits, easy: body.easy, comment: comment || '-', via } }];
"""
FEEDBACK_CHECK_JS = r"""// The job behind the answer: it must exist and be done, and it must not be rated yet – a second answer is a
// refusal with its own code, never a silent overwrite.
const v = $('Validate feedback').first().json;
const row = $input.first().json || {};
const fail = (code, message, status) => [{ json: { ok: false, statusCode: status, body: { error: { code, message } } } }];
if (!row.id) return fail('not_found', 'job not found', 404);
if (row.status !== 'done') return fail('not_ready', `job is ${row.status}: only a finished job can be rated`, 409);
if (row.rated) return fail('already_rated', 'this job has already been rated', 409);
return [{ json: { ...v } }];
"""
FEEDBACK_SAVED_JS = r"""// on conflict do nothing: two answers arriving together – the second sees no returned row and gets 409 too.
const row = $input.first().json || {};
if (!row.job_id) return [{ json: { statusCode: 409, body: { error: { code: 'already_rated', message: 'this job has already been rated' } } } }];
return [{ json: { statusCode: 201, body: { ok: true, job_id: row.job_id } } }];
"""
FEEDBACK_LOAD_SQL = "select j.id, j.status, (f.job_id is not null) as rated from (select 1) one left join jobs j on j.id = $1 left join feedback f on f.job_id = j.id"
FEEDBACK_INSERT_SQL = "insert into feedback (job_id, fits, easy, comment, via) values ($1, $2::int, $3::int, nullif($4, '-'), $5) on conflict (job_id) do nothing returning job_id"
jobs_nodes += [
    node("Webhook feedback", "n8n-nodes-base.webhook", 2.1, {"httpMethod": "POST", "path": "feedback", "responseMode": "responseNode", "options": {}}, 0, 3700, webhookId="6f1c5a1e-feedb-0000-0000-000000000007"),
    code("Validate feedback", VALIDATE_FEEDBACK_JS, 220, 3700),
    if_bool("Feedback valid?", "{{ $json.ok }}", 440, 3700),
    pg("Load job for feedback", FEEDBACK_LOAD_SQL, "{{ [$json.job_id] }}", 660, 3700),
    code("Feedback check", FEEDBACK_CHECK_JS, 880, 3700),
    if_bool("Feedback ok?", "{{ $json.ok }}", 1100, 3700),
    # alwaysOutputData: with the row already there the insert returns nothing, and an empty output would end the
    # branch with 200 and no body (audit 2026-09-20); Feedback saved turns the empty item into 409.
    pg("Insert feedback", FEEDBACK_INSERT_SQL, "{{ [$json.job_id, $json.fits, $json.easy, $json.comment, $json.via] }}", 1320, 3700, alwaysOutputData=True),
    code("Feedback saved", FEEDBACK_SAVED_JS, 1540, 3700),
    respond("Respond feedback", "{{ $json.body }}", "={{ $json.statusCode }}", 1760, 3700),
]
wire(jc, "Webhook feedback", "Validate feedback"); wire(jc, "Validate feedback", "Feedback valid?"); wire(jc, "Feedback valid?", "Load job for feedback", 0); wire(jc, "Feedback valid?", "Respond feedback", 1)
wire(jc, "Load job for feedback", "Feedback check"); wire(jc, "Feedback check", "Feedback ok?"); wire(jc, "Feedback ok?", "Insert feedback", 0); wire(jc, "Feedback ok?", "Respond feedback", 1)
wire(jc, "Insert feedback", "Feedback saved"); wire(jc, "Feedback saved", "Respond feedback")

# Internal failures answer 500 (2026-09-20): a node that throws before the Respond node made n8n answer the webhook
# with 200 and an empty body – a Postgres outage on Load budget looked like success and created nothing. Every
# Postgres, HTTP and Code node on a response path gets an error output wired to one Respond 500 with the contract
# code internal_error. Nodes that degrade on purpose (pricing file, Load limits) keep continueRegularOutput. The
# job lookups answer "not found" through a left join (one row of nulls), not alwaysOutputData: alwaysOutputData also
# emits an empty item on the regular output when the query fails, and the 404 branch answered before the 500 one.
INTERNAL_ERROR_JS = r"""// The error output item of the failed node: {error: message} or {error: {message}}; secrets masked as elsewhere.
const it = $input.first().json || {};
const raw = it.message || (it.error && typeof it.error === 'object' ? (it.error.message || it.error.description || JSON.stringify(it.error)) : (it.error || 'unknown failure'));
const mask = (t) => String(t).replace(/\b(sk|gsk|rk|xai)[-_][^\s"'\\]{6,}/g, (m) => m.slice(0, 3) + '***').replace(/\b[A-Za-z0-9_-]{32,}\b/g, '***').replace(/(Bearer|Token)\s+[^\s"']+/gi, '$1 ***');
const where = $prevNode.name;
// Which endpoint ran (one webhook per execution) and its job id, for the event; the client gets a neutral body:
// in a few days this is a public page, node names, tables and addresses stay in events and docker logs.
const HOOKS = { 'Webhook probe': 'probe', 'Webhook jobs': 'create', 'Webhook job status': 'status', 'Webhook retry': 'retry', 'Webhook export': 'export', 'Webhook media': 'media', 'Webhook feedback': 'feedback', 'Webhook limits': 'limits' };
let endpoint = 'api', job_id = '-';
for (const [name, ep] of Object.entries(HOOKS)) { try { if ($(name).isExecuted) { endpoint = ep; job_id = String((($(name).first().json || {}).query || {}).job_id || '-'); break; } } catch (e) { /* not this one */ } }
const detail = `${endpoint} at ${where}: ${mask(raw).slice(0, 240)}`;
console.log(`[video-digest] internal_error ${detail}`);
return [{ json: { statusCode: 500, body: { error: { code: 'internal_error', message: 'internal error on our side, try again later' } }, job_id, events: [{ type: 'internal_error', level: 'error', stage: endpoint, body: detail }] } }];
"""
GUARDED = ["Media upload", "Media probe", "Add estimate", "Validate job request", "Media source", "Build job row", "Load budget", "Check budget", "Insert job",
           "Load job", "Format status", "Load job for retry", "Retry prepare", "Media re-probe", "Retry body",
           "Load job for export", "Export prepare", "Export files", "Gotenberg pdf", "Zip pdf", "Load job for media", "Media route",
           "Validate feedback", "Load job for feedback", "Feedback check", "Insert feedback", "Feedback saved", "Turnstile decide", "Mark token used", "Limits body"]
jobs_nodes += [code("Internal error", INTERNAL_ERROR_JS, 2860, 3300), log_events("Log internal error", 3080, 3300), respond("Respond 500", "{{ $json.body }}", 500, 3300, 3300)]
_names = {n["name"] for n in jobs_nodes}
for _g in GUARDED:
    assert _g in _names, _g
for n in jobs_nodes:
    if n["name"] in GUARDED:
        n["onError"] = "continueErrorOutput"
        wire(jc, n["name"], "Internal error", 1)
wire(jc, "Internal error", "Log internal error"); wire(jc, "Log internal error", "Respond 500")
jobs_api = {"name": "jobs-api", "nodes": jobs_nodes, "connections": jc, "settings": {"executionOrder": "v1"}}

# ----------------------------------------------------------------- shared JS helpers
JS_HELPERS = r"""
const fill = (tpl, vars) => String(tpl).replace(/<<([A-Z_]+)>>/g, (m, k) => (vars[k] !== undefined && vars[k] !== null ? String(vars[k]) : m));
const stripHeader = (md) => { const i = String(md).indexOf('\n---\n'); return i >= 0 ? String(md).slice(i + 5).trim() : String(md).trim(); };
const wordsOf = (t) => String(t || '').trim().split(/\s+/).filter(Boolean).length;
const fmtStart = (x) => (Math.round(Number(x) * 10) / 10).toFixed(1);
const llmCost = (pricing, model, usage) => { const pr = ((pricing || {}).llm || {})[model]; if (!pr) return 0; return (usage.in / 1e6) * pr.input_per_1m + (usage.out / 1e6) * pr.output_per_1m; };
const round4 = (x) => Math.round(x * 10000) / 10000;
const setStage = (stages, name, patch) => stages.map((s) => (s.name === name ? { ...s, ...patch } : s));
// Secrets never reach jobs.error or the logs: OpenAI echoes the prefix and tail of a rejected key, so anything
// shaped like a key (sk-…, gsk_…, long tokens, Bearer/Token headers) becomes stars before it is stored.
const maskSecrets = (t) => String(t).replace(/\b(sk|gsk|rk|xai)[-_][^\s"'\\]{6,}/g, (m) => m.slice(0, 3) + '***').replace(/\b[A-Za-z0-9_-]{32,}\b/g, '***').replace(/(Bearer|Token)\s+[^\s"']+/gi, '$1 ***');
const isAuthStatus = (code) => Number(code) === 401 || Number(code) === 403;
// One line per provider refusal for docker logs (jobs.error keeps the short version).
const logAuth = (S, stage, provider, status, body, note) => console.log(`[video-digest] provider_auth job=${(S.job || {}).id || S.job_id} stage=${stage} provider=${provider} status=${status}${note ? ' ' + note : ''} body=${maskSecrets(JSON.stringify(body)).slice(0, 200)}`);
// Events for the events table (contract section 4), flushed by the "Log events" nodes through the
// log-events sub-workflow: fire-and-forget, an insert failure never touches the job.
const retryEvents = (items, stage, labelOf) => items.filter((i) => (i.attempts || 1) > 1).map((i) => ({ type: 'validator_retry', level: 'warn', stage, model: i.model || null, body: `${labelOf(i)}: ${i.retry_error || 'first answer rejected'}` }));
const failItem = (S, stage, code, message) => ({ ...S, failed: true, fail: { stage, code, message: maskSecrets(message).slice(0, 500) } });
const withDb = (S) => ({ ...S, job_id: S.job.id, p_stages: JSON.stringify(S.stages), p_meta: JSON.stringify(S.meta) });
// Failure item inside a progress loop: it still carries job_id/p_stages, so the Postgres progress node that
// follows keeps its parameters instead of dying with "there is no parameter $1" and leaving the job in
// processing forever. The loop's done branch turns the first failed item into the job failure.
const loopFail = (S, item, stage, code, message) => ({ ...item, failed: true, fail: { stage, code, message: maskSecrets(message).slice(0, 500) }, job_id: S.job.id, p_stages: JSON.stringify(S.stages) });
"""

# ----------------------------------------------------------------- llm-call (sub-workflow)
PREPARE_JS = r"""// Build the chat-completions request for the configured provider.
const inp = $('When called').first().json;
// pricing.json is also the model catalogue: supports_temperature: false means the model accepts only its
// default temperature (gpt-5.6-luna rejects 0.2 with 400), so the parameter is not sent at all. No flag: sent as before.
const pricing = $('Parse pricing').first().json.data || {};
const provider = String($env.LLM_PROVIDER || 'openai').toLowerCase();
const BASES = { openai: 'https://api.openai.com/v1', groq: 'https://api.groq.com/openai/v1', openrouter: 'https://openrouter.ai/api/v1' };
const base_url = BASES[provider] || $env.LLM_BASE_URL || 'http://localhost:8080/v1';
// Cheap model for clean and map, a rule-abiding one for reduce (LLM_MODEL is the fallback for both).
// digest-reduce and critique are judgement, the rest is extraction.
const JUDGEMENT = ['digest', 'critique'];
const model = String(JUDGEMENT.includes(inp.kind) ? ($env.LLM_MODEL_REDUCE || $env.LLM_MODEL || 'gpt-4o-mini') : ($env.LLM_MODEL_MAP || $env.LLM_MODEL || 'gpt-4o-mini'));
const body = {
  model, response_format: { type: 'json_object' },
  messages: [{ role: 'system', content: inp.system }, { role: 'user', content: inp.user }],
};
if ((((pricing.llm || {})[model]) || {}).supports_temperature !== false) body.temperature = 0.2;
return [{ json: { kind: inp.kind, label: inp.label || inp.kind, context: inp.context || {}, system: inp.system, user: inp.user, base_url, model, body, started: Date.now(), attempt: 1 } }];
"""

RETRY_JS = r"""// Second and last attempt: a correction of the first answer, not a fresh one. The rejected answer goes
// back as the assistant turn together with the validation error; the model fixes what the error names
// and keeps the rest as it was. A fresh answer re-rolls every field: j_hpopim (map, 41 min) had every
// timestamp right and one non-verbatim quote in attempt 1, the fresh attempt 2 fixed the quote and
// invented key_points[5].start, and nothing could retry that any more. Temperature stays at 0.2: low
// temperature is what keeps the untouched fields identical (the old fresh retry needed 0.6 so as not to
// repeat the first answer verbatim; a correction request has no such problem).
const state = $('Prepare').first().json;
const v = $input.first().json;
let messages;
if (v.data) {
  const fix = 'VALIDATION ERROR\nThe answer above was rejected: ' + v.error + '\nReturn the full JSON object again: fix every problem the error names, change nothing else and keep everything else exactly as it was, timestamps included.';
  messages = [...state.body.messages, { role: 'assistant', content: JSON.stringify(v.data) }, { role: 'user', content: fix }];
} else {
  // Not JSON at all: nothing to correct, ask again with the error attached.
  const user = state.user + '\n\nVALIDATION ERROR\nYour previous answer was rejected: ' + v.error + '\nReturn the corrected full JSON object.';
  messages = [{ role: 'system', content: state.system }, { role: 'user', content: user }];
}
const body = { ...state.body, messages };
return [{ json: { ...state, body, attempt: 2, usage1: v.usage, error1: v.error, events1: v.events || [] } }];
"""

# The retention functions live in scripts/clean_retention.js (module for node, verbatim insert for the Code
# sandbox); the text up to the module boundary is pasted where __CLEAN_RETENTION__ stands.
CLEAN_RETENTION_JS = (Path(__file__).resolve().parent / "clean_retention.js").read_text(encoding="utf-8").split("\n// --- module boundary")[0]
CLEAN_RETENTION_JS = CLEAN_RETENTION_JS[CLEAN_RETENTION_JS.index("function cleanFillers"):].rstrip("\n")
# Transport verdict (scripts/transport_retry.js): pasted into the Validate nodes of llm-call and the STT transport
# check of the pipeline; the text from the first function up to the module boundary.
TRANSPORT_JS = (Path(__file__).resolve().parent / "transport_retry.js").read_text(encoding="utf-8").split("\n// --- module boundary")[0]
TRANSPORT_JS = TRANSPORT_JS[TRANSPORT_JS.index("function transportVerdict"):].rstrip("\n")

VALIDATE_JS = r"""// Parse the LLM answer and validate it for the given kind (mirrors schemas/result.schema.json;
// ajv cannot run in the Code sandbox, so the rules are written out by hand).
const attempt = __ATTEMPT__;
const state = $('__STATE__').first().json;
const resp = $input.first().json;
// Transport (2026-09-20): 429 and 5xx come as items (neverError), a node exception as an item with `error`.
// This node runs once per transport attempt ($runIndex); a retry verdict sends the item to Wait and back to the
// request node, the final verdict carries the events of the earlier attempts of this call.
const earlierEvents = [];
try { for (let i = 0; i < $runIndex; i++) for (const it of $('Validate __ATTEMPT__').all(0, i)) if (it.json && it.json.event) earlierEvents.push(it.json.event); } catch (e) { /* first run, or no earlier data */ }
const tv = transportVerdict(resp, $runIndex + 1);
const stageOf = { clean: 'clean', map: 'digest', digest: 'digest' };
if (tv.retry) return [{ json: { transport_retry: true, wait_sec: tv.wait_sec, event: transportEvent(stageOf[state.kind] || 'extras', String(state.base_url || '').replace(/^https?:\/\//, '').split('/')[0] || null, state.label, tv) } }];
const out = { ok: false, attempt, error: null, data: null, usage: { in: 0, out: 0 }, events: earlierEvents };
const SOFT = [];
const mask = (t) => String(t).replace(/\b(sk|gsk|rk|xai)[-_][^\s"'\\]{6,}/g, (m) => m.slice(0, 3) + '***').replace(/\b[A-Za-z0-9_-]{32,}\b/g, '***');
if (resp.statusCode !== 200) {
  out.error = `llm_http_${resp.statusCode || 0}: ${mask(resp.statusCode ? JSON.stringify(resp.body) : String(resp.error && resp.error.message ? resp.error.message : resp.error || 'no answer')).slice(0, 300)}`;
  // 401/403, 402 and 429 insufficient_quota: the provider refused the key or the balance, a retry cannot help;
  // the pipeline turns this into provider_auth.
  if (tv.auth) { out.auth = true; out.terminal = true; }
  return [{ json: out }];
}
const body = resp.body || {};
// The model id the provider actually served (a dated snapshot behind the alias we asked for): providers
// move aliases silently, and without it a comparison cannot be reproduced later.
out.model_actual = typeof body.model === 'string' ? body.model : null;
const u = body.usage || {};
out.usage = { in: u.prompt_tokens || 0, out: u.completion_tokens || 0 };
const choice = (body.choices || [])[0] || {};
if (choice.finish_reason === 'content_filter') { out.error = 'content_filter: the provider refused to reproduce this text'; out.terminal = true; return [{ json: out }]; }
if (choice.finish_reason === 'length') { out.error = 'truncated: the answer hit the output token limit'; out.terminal = true; return [{ json: out }]; }
let text = (choice.message || {}).content || '';
text = String(text).trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
let data;
try { data = JSON.parse(text); } catch (e) { out.error = 'response is not valid JSON: ' + e.message; return [{ json: out }]; }
if ((state.context || {}).output_language === 'ru') data = fixRuDashes(data);
const err = validate(state.kind, data, state.context || {});
out.data = data;
if (err) { out.error = err; return [{ json: out }]; }
// Style rules of docs/result-schema.md section 9 are soft: one retry, then the answer is accepted
// and the violations travel as warnings (jobs.meta.quality_warnings). Structural rules stay hard.
if (SOFT.length && attempt === 1) { out.error = SOFT[0]; out.soft = true; return [{ json: out }]; }
out.warnings = SOFT.slice();
out.ok = true;
return [{ json: out }];

// Russian typography: the model likes the em dash; the brief wants « – ». Verbatim quote text is exempt.
function fixRuDashes(node, key, parent) {
  if (typeof node === 'string') {
    if (key === 'text' && parent && parent.translation !== undefined) return node;
    return node.replace(/\s+—\s+/g, ' – ').replace(/—/g, '–');
  }
  if (Array.isArray(node)) return node.map((v) => fixRuDashes(v, null, null));
  if (node && typeof node === 'object') { const o = {}; for (const [k, v] of Object.entries(node)) o[k] = fixRuDashes(v, k, node); return o; }
  return node;
}
function isNum(x) { return typeof x === 'number' && Number.isFinite(x); }
// Content-sentence retention of a clean answer (rule 10), scripts/clean_retention.js pasted here at build time
// (Code nodes cannot require). Units: the lines of the input after CONTEXT joined into one text and cut at sentence
// punctuation (windows of ~15 content words when the input has no punctuation), at least 6 content words, fillers
// of the output language stripped on both sides so "да, вот, ну" and "um, you know" removed by the model are not
// losses; a unit survives when at least a third of its 3-word shingles occur in the answer.
__CLEAN_RETENTION__
__TRANSPORT__
function isStr(x, min = 1) { return typeof x === 'string' && x.trim().length >= min; }
function words(s) { return String(s).trim().split(/\s+/).filter(Boolean).length; }
function normalize(s) { return String(s).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim(); }
function bigrams(s) { const b = new Set(); for (let i = 0; i < s.length - 1; i++) b.add(s.slice(i, i + 2)); return b; }
function dice(a, b) { const A = bigrams(a), B = bigrams(b); if (!A.size || !B.size) return 0; let n = 0; for (const x of A) if (B.has(x)) n++; return (2 * n) / (A.size + B.size); }
function quoteFound(q, cleanText, sentences) { const nq = normalize(q); if (!nq) return false; if (cleanText.includes(nq)) return true; return sentences.some((s) => dice(nq, s) >= 0.9); }
function nearest(pool, v) { return pool.reduce((b, x) => (Math.abs(x - v) < Math.abs(b - v) ? x : b), pool[0]); }
// Timestamps are honest only when they come from the input: a value the model returns must match one
// of the input timestamps (tolerance covers the one-decimal formatting of the prompt lines); it is
// snapped to the exact value, anything further off was invented and is rejected.
function snapTo(pool, v, tol) { if (!pool.length || !isNum(v)) return null; const n = nearest(pool, v); return Math.abs(n - v) <= tol ? n : null; }
// Parts (map sections, digest structure) form a partition of [first, last]: sorted by start, each part
// starts where the previous one ends, the first at `first`, the last at `last`. Returns every violation
// with the edit that fixes it, all at once: the single correction attempt has to fix all of them.
// Naming only the first one (j_wrvonm, execution 623: a «Реклама» part nested in the part it
// interrupts, three holes further on) got a literal fix, start := previous end, i.e. an empty part,
// with three holes left and no attempt left. Parts are named by title and timestamps, not by index:
// the list is sorted here and the model sees its own order.
function partitionProblems(parts, first, last, tol, name, maxParts) {
  const out = [];
  const lab = (p) => `${name} "${String(p.title || '').slice(0, 40)}" ${p.start}–${p.end}`;
  // "Add a part" is offered only for a hole of a minute or more and while the count allows it: told to
  // add one for every hole, gpt-4.1 made a 20-second "transition" part for the last paragraph of a
  // chunk and went past ten parts.
  const full = isNum(maxParts) && parts.length >= maxParts;
  const addOption = (lo, hi) => (hi - lo >= 60 && !full) ? `, or add a part for ${lo}–${hi}` : '';
  for (const p of parts) if (p.end <= p.start) out.push(`${lab(p)} is empty: a part spans at least one paragraph, so start < end (a part inside another one is not nested: it cuts the outer part)`);
  for (let i = 1; i < parts.length; i++) {
    const a = parts[i - 1], b = parts[i];
    if (b.end <= b.start) continue;
    if (b.start < a.end - tol) {
      if (b.end <= a.end + tol) out.push(`${lab(b)} lies inside ${lab(a)}: parts do not nest, end the outer part at ${b.start}` + (a.end > b.end + tol ? `; ${b.end}–${a.end} then belongs to the part after the inner one (start it at ${b.end}${full ? '' : ', or add a part for that span'})` : ''));
      else out.push(`${lab(b)} starts before ${lab(a)} ends: parts do not overlap, give both the same boundary timestamp`);
    } else if (b.start > a.end + tol) out.push(`nothing covers ${a.end}–${b.start} between ${lab(a)} and ${lab(b)}: every second belongs to a part, extend the earlier part to ${b.start} or start the later one at ${a.end}${addOption(a.end, b.start)}`);
  }
  if (parts.length && isNum(first) && parts[0].start > first + tol) out.push(`nothing covers ${first}–${parts[0].start} before ${lab(parts[0])}: start the first part at ${first}${addOption(first, parts[0].start)}`);
  const z = parts[parts.length - 1];
  if (parts.length && isNum(last) && z.end < last - tol) out.push(`nothing covers ${z.end}–${last} after ${lab(z)}: extend the last part to ${last}${addOption(z.end, last)}`);
  return out;
}
// Deterministic repair of candidate sections after a failed correction: sweep the elementary
// intervals between all boundaries, give each to the innermost part containing it, a hole to the part
// before it, merge neighbours of the same part, clamp to the chunk. A part cut by an advertisement
// repeats its title: the notes are raw material, reduce writes its own titles.
function repairPartition(parts, first, last) {
  const real = parts.filter((p) => isNum(p.start) && isNum(p.end) && p.end > p.start);
  if (!real.length) return [];
  const bounds = [...new Set(real.flatMap((p) => [p.start, p.end]).concat([first, last]))].filter((b) => isNum(b) && b >= first && b <= last).sort((a, b) => a - b);
  const pieces = [];
  let owner = null;
  for (let i = 0; i + 1 < bounds.length; i++) {
    const lo = bounds[i], hi = bounds[i + 1];
    const inside = real.filter((p) => p.start <= lo && p.end >= hi);
    if (inside.length) owner = inside.reduce((b, p) => (p.end - p.start < b.end - b.start ? p : b));
    if (!owner) owner = real[0];
    const prev = pieces[pieces.length - 1];
    if (prev && prev.src === owner) prev.end = hi; else pieces.push({ src: owner, start: lo, end: hi });
  }
  return pieces.map((x) => ({ ...x.src, start: x.start, end: x.end }));
}

// Hard rule for every kind: a word mixing Cyrillic and Latin letters ("неvisualьный", seen twice from
// gpt-5.6-luna on 2026-09-16, but the rule is general). Appended to the kind's own errors so that one
// problem does not hide the next. clean is exempt (its text comes from STT), quotes are exempt (verbatim).
function mixedScriptWords(node, path, out) {
  if (typeof node === 'string') {
    if (/(^|\.)quotes\[/.test(path)) return out;
    for (const w of node.match(/[\p{Script=Cyrillic}\p{Script=Latin}]+/gu) || []) {
      if (/\p{Script=Cyrillic}/u.test(w) && /\p{Script=Latin}/u.test(w)) out.push(`${path}: "${w}"`);
    }
  } else if (Array.isArray(node)) node.forEach((v, i) => mixedScriptWords(v, `${path}[${i}]`, out));
  else if (node && typeof node === 'object') for (const [k, v] of Object.entries(node)) mixedScriptWords(v, path ? `${path}.${k}` : k, out);
  return out;
}
function validate(kind, d, ctx) {
  const err = validateKind(kind, d, ctx);
  if (kind === 'clean' || !d || typeof d !== 'object') return err;
  const mixed = mixedScriptWords(d, '', []);
  if (!mixed.length) return err;
  const msg = `${mixed.length} word(s) mix Cyrillic and Latin letters inside one word, rewrite each in a single alphabet and keep everything else unchanged: ${mixed.slice(0, 8).join('; ')}`;
  return err ? `${err}; ${msg}` : msg;
}
function validateKind(kind, d, ctx) {
  if (!d || typeof d !== 'object' || Array.isArray(d)) return 'top level must be a JSON object';
  if (kind === 'clean') {
    if (!Array.isArray(d.paragraphs)) return 'paragraphs must be an array';
    // Empty answer (2026-09-20, j_jppvgs): the prompt allows paragraphs: [] on a chunk without speech, so an empty
    // answer is invalid only when the input holds speech – at least 20 words after CONTEXT, about one sentence
    // (the STT guard already refuses transcripts under 20 words a minute). Hard on attempt 1 (correction); on
    // attempt 2 the rule-based fallback of Clean chunk done takes over, the job goes on.
    const inputWords = words(String(state.user || '').split('\nTRANSCRIPT\n').pop().replace(/^\[[^\]]*\]\s*/gm, ''));
    if (d.paragraphs.length === 0 && inputWords >= 20) return `paragraphs is empty for a chunk with ${inputWords} words of speech: a transcript cleanup keeps every sentence, return the cleaned text as paragraphs`;
    const starts = (ctx.starts || []).map(Number);
    const maxWords = Number(ctx.max_words || 250);
    let prev = -1;
    for (const [i, p] of d.paragraphs.entries()) {
      if (!p || !isNum(p.start) || p.start < 0) return `paragraphs[${i}].start must be a number >= 0`;
      if (!isStr(p.text)) return `paragraphs[${i}].text must be a non-empty string`;
      if (starts.length) {
        // A miscopied digit lands a few seconds off; the pipeline re-aligns the start by the paragraph's
        // first words afterwards. Anything further off is an invented number.
        const s = snapTo(starts, p.start, 5.0);
        if (s === null) return `paragraphs[${i}].start ${p.start} is not a start_seconds value from the input: copy the timestamp of the first segment of the paragraph exactly`;
        p.start = s;
      }
      if (p.start < prev) return `paragraphs[${i}].start ${p.start} goes backwards: paragraphs must be in chronological order`;
      prev = p.start;
      const w = words(p.text);
      if (w > maxWords) return `paragraphs[${i}] has ${w} words: split the text into paragraphs of 3-8 sentences (at most ${maxWords} words each), each with the start_seconds of its first segment`;
    }
    // Retention (soft, docs/result-schema.md section 9 rule 10): the share of input units that survive in the
    // answer, counted on content words so the removal of fillers does not count as a loss. Found 2026-09-17 on
    // Cosmoscow: gpt-4o-mini quietly dropped 29–44% of the sentences of every run since 2026-09-08 while the
    // paragraph rules passed. Two conditions since 2026-09-20 (cleanThresholds in clean_retention.js): fewer than
    // 92% of the units survive, OR a lost unit has 10+ content words – every defective chunk on record lost such a
    // unit while the noise of honest chunks (stutters, paraphrases, chunk-boundary fragments) stayed under 10; the
    // percentage is a net for many short losses. Separate prefixes (clean_retention, clean_lost_long) so the events
    // and the result page show which condition fired. A false alarm costs one correction call, a miss costs content.
    // A tail chunk under 10 units is not judged.
    const TH = cleanThresholds();
    const r = cleanRetention(state.user, d.paragraphs, ctx.output_language);
    // Attempt 2: what the correction dropped that the first answer had. The soft retry is not safe – it gives a
    // large plus (55% -> 91% on a meeting) and a small minus, and the minus must be visible (decision 2026-09-17:
    // five content sentences vanished in one chunk while 41 came back). Always a warning, even above threshold.
    if (attempt === 2) {
      try {
        const msgs = ((state.body || {}).messages || []);
        const prev = msgs.length >= 2 ? JSON.parse(msgs[msgs.length - 2].content) : null;
        if (prev && Array.isArray(prev.paragraphs)) {
          // lostAfterFix (clean_retention.js): keyed by timestamp and content tokens, and counted by content – a
          // unit whose words survive re-punctuated or merged into a neighbour is not a loss.
          const gone = lostAfterFix(cleanRetention(state.user, prev.paragraphs, ctx.output_language), r).gone;
          if (gone.length) SOFT.push(`clean_lost_after_fix: ${gone.length} sentence(s) present in the first answer are missing after the correction: ${gone.slice(0, 8).map((u) => `[${u.t}] ${u.text.slice(0, 80)}`).join('; ')}`);
        }
      } catch (e) { /* the first answer was not JSON: nothing to compare */ }
    }
    if (r.total >= TH.minUnits && r.kept / r.total < TH.minRetention) {
      // Longest first: the correction is a single attempt and a loss the model was not told about will not survive
      // it (the digest rule after j_72549q); the 15 shown must be the ones that matter.
      const list = r.lost.slice().sort((a, b) => b.w.length - a.w.length).slice(0, 15).map((u) => `[${u.t}] ${u.text.slice(0, 90)}`).join('; ');
      SOFT.push(`clean_retention: only ${r.kept} of ${r.total} sentences of the input survive in your text (${Math.round(100 * r.kept / r.total)}%, ${r.lost.length} missing); a transcript cleanup keeps every sentence and removes only fillers, false starts and repetitions, never content. Put the missing sentences back where they were said, keep the paragraph split and the timestamps${r.lost.length > 15 ? `, first 15 of ${r.lost.length}` : ''}: ${list}`);
    }
    // Known false positive of both conditions, not treated: a spelled-out address, abbreviation or numeral that the
    // model normalizes as the prompt asks («work o s dot com» → «workos.com») shares no shingles with the input.
    const long = r.total >= TH.minUnits ? r.lost.filter((u) => u.w.length >= TH.longUnitWords) : [];
    if (long.length) {
      const list = long.slice().sort((a, b) => b.w.length - a.w.length).slice(0, 10).map((u) => `[${u.t}] ${u.text.slice(0, 120)}`).join('; ');
      // Short head: «clean N/M: » plus this text must leave room for the first timestamp in the 240-char event body.
      SOFT.push(`clean_lost_long: ${long.length} whole sentence(s) of ${TH.longUnitWords}+ content words are missing from your text; a cleanup never drops a sentence, put them back where they were said with their timestamps${long.length > 10 ? ` (first 10 of ${long.length})` : ''}: ${list}`);
    }
    // Places for the reader (result.notices, 2026-09-23): the timecodes of the lost units when any clean_* rule
    // fired on this answer – timecodes only, never text (the messages above carry text and stay in meta/events).
    if (SOFT.some((w) => /^clean_/.test(String(w)))) out.lost_starts = [...new Set(r.lost.map((u) => Number(u.t)))].sort((a, b) => a - b);
    return null;
  }
  if (kind === 'map') {
    // Every hard violation in one message, as in digest: the correction is a single attempt, and an
    // error named alone hides the next one (j_72549q, execution 860: attempt 1 had a hole in the
    // sections and five paraphrased quotes, the model was told about the hole only, attempt 2 fell on
    // the quotes it had never been asked to fix).
    const HARD = [];
    if (!isStr(d.summary)) HARD.push('summary must be a non-empty string');
    for (const k of ['key_points', 'sections', 'quotes', 'terms']) if (!Array.isArray(d[k])) { HARD.push(`${k} must be an array`); d[k] = []; }
    const starts = (ctx.starts || []).map(Number);
    const ends = starts.concat(isNum(ctx.chunk_end) ? [ctx.chunk_end] : []);
    const notInput = (where, v) => `${where} ${v} is not a paragraph start_seconds value from the input: copy timestamps exactly, never invent or round them`;
    for (const [i, k] of d.key_points.entries()) {
      if (!k || !isStr(k.text) || !isNum(k.start)) { HARD.push(`key_points[${i}] needs text and a numeric start`); continue; }
      if (starts.length) { const s = snapTo(starts, k.start, 1.0); if (s === null) HARD.push(notInput(`key_points[${i}].start`, k.start)); else k.start = s; }
    }
    let sectionsOk = true;
    for (const [i, x] of d.sections.entries()) {
      if (!x || !isStr(x.title) || !isNum(x.start) || !isNum(x.end)) { HARD.push(`sections[${i}] needs title, numeric start and end`); sectionsOk = false; continue; }
      if (starts.length) {
        const s = snapTo(starts, x.start, 1.0); if (s === null) { HARD.push(notInput(`sections[${i}].start`, x.start)); sectionsOk = false; } else x.start = s;
        const e = snapTo(ends, x.end, 1.0); if (e === null) { HARD.push(`sections[${i}].end ${x.end} must be the start_seconds of the next part or the chunk end (${ctx.chunk_end}), copied from the input`); sectionsOk = false; } else x.end = e;
      }
    }
    // Candidate sections are a partition of the chunk. gpt-4o-mini lists topics as highlights, nests an
    // advertisement inside the topic it interrupts and leaves minutes uncovered (j_wrvonm: «Реклама»
    // 119.6–154.32 inside 0–154.32, seven minutes of chunk 3 in no section); reduce copied the nesting
    // and the holes into structure, and the digest fell on rule 7. One correction with the full list;
    // after a failed one the sections are repaired programmatically and the job carries a warning: the
    // notes are raw material, the partition that matters, structure, stays a hard rule.
    if (sectionsOk && starts.length && isNum(ctx.chunk_end) && d.sections.length) {
      d.sections.sort((a, b) => a.start - b.start);
      // The last paragraph of the chunk has no next paragraph inside the chunk to end at, so a last
      // section ending at its start owns it: extended to the chunk end here, nothing else could.
      const z = d.sections[d.sections.length - 1];
      if (z.end === starts[starts.length - 1] && z.end < ctx.chunk_end) z.end = ctx.chunk_end;
      const problems = partitionProblems(d.sections, starts[0], ctx.chunk_end, 1.0, 'section', 6);
      if (problems.length) {
        if (attempt === 1) HARD.push(`sections must be consecutive parts covering the chunk from ${starts[0]} to ${ctx.chunk_end} without gaps, overlaps or nesting (an advertisement inside a topic cuts it into topic, advertisement, topic again; all timestamps from the input): ${problems.join('; ')}`);
        else {
          SOFT.push(`map sections did not form a partition of the chunk ${starts[0]}–${ctx.chunk_end} after the correction and were repaired programmatically: ${problems.join('; ')}`);
          d.sections = repairPartition(d.sections, starts[0], ctx.chunk_end);
        }
      }
    }
    let quotesOk = true;
    for (const [i, q] of d.quotes.entries()) {
      if (!q || !isStr(q.text) || !isNum(q.start)) { HARD.push(`quotes[${i}] needs text and a numeric start`); quotesOk = false; continue; }
      if (starts.length) { const s = snapTo(starts, q.start, 1.0); if (s === null) HARD.push(notInput(`quotes[${i}].start`, q.start)); else q.start = s; }
    }
    for (const t of d.terms) if (t && isNum(t.start) && starts.length) { const s = snapTo(starts, t.start, 1.0); if (s !== null) t.start = s; }
    // Candidate quotes must be verbatim: reduce can only pick from them, and with too few candidates
    // it writes quotes from memory (Arzamas: one candidate for the whole video, three invented quotes).
    if (quotesOk && typeof ctx.chunk_text === 'string') {
      const chunkText = normalize(ctx.chunk_text);
      const sentences = ctx.chunk_text.split(/(?<=[.!?…])\s+/).map(normalize).filter(Boolean);
      const bad = d.quotes.filter((q) => !quoteFound(q.text, chunkText, sentences));
      const good = d.quotes.filter((q) => !bad.includes(q));
      const min = Number(ctx.min_quotes || 0);
      if (good.length < min) {
        // gpt-4o-mini sometimes writes the quotes in the output language (j_72549q, execution 860: five
        // Russian paraphrases of an English podcast) and, corrected, translates them again: the error
        // names the transcript language and shows one verbatim sentence from the input to anchor on.
        const lang = ctx.source_language ? ` in ${ctx.source_language}, the language of the transcript${ctx.output_language && ctx.output_language !== ctx.source_language ? `, never translated into ${ctx.output_language}` : ''}` : '';
        const raw = ctx.chunk_text.split(/(?<=[.!?…])\s+/).map((x) => x.trim());
        const example = raw.find((x) => { const n = words(x); return n >= 10 && n <= 25; }) || raw.find((x) => words(x) >= 8) || '';
        HARD.push(`only ${good.length} of ${d.quotes.length} quotes are verbatim fragments of the input, at least ${min} are needed: replace them with whole sentences copied character for character from the input paragraphs${lang}; do not edit or shorten them. ${example ? `For example this sentence is a verbatim fragment: "${example}". ` : ''}Not verbatim: ${bad.map((q) => `"${String(q.text).slice(0, 60)}"`).join('; ') || 'none'}`);
      } else d.quotes = good;
    }
    if (HARD.length) return (HARD.length > 1 ? `${HARD.length} problems, fix all of them. ` : '') + HARD.join('; ');
    return null;
  }
  if (kind === 'digest') {
    // Every hard violation is collected and reported at once, each with its fix: the correction is a
    // single attempt, and an error named alone hides the next one behind it (j_wrvonm, execution 623:
    // the structure error was fixed in 3 of 3 replays, and every replay then fell on the quotes without
    // translation that the first check had never reached).
    const HARD = [];
    const dur = Number(ctx.duration_sec || 0);
    const tol = 1.0;
    if (!isStr(d.tldr)) HARD.push('tldr must be a non-empty string');
    else if (words(d.tldr) > 80) HARD.push(`tldr has ${words(d.tldr)} words, the maximum is 80`);
    // Rule 9: the tldr states the subject and the conclusion, not that "this video is about".
    const META_TLDR = /^\s*[«"“]?\s*(в\s+(этом|данном|нашем|сегодняшнем)\s+(видео|ролике|выпуске|подкасте|докладе|разговоре|материале)|в\s+(этой|данной|сегодняшней)\s+(лекции|беседе|записи|встрече)|(это|данное)\s+видео|(видео|лекция|доклад|ролик|выпуск|подкаст|беседа|встреча|запись)[^.]{0,40}?\s(посвящен[аоы]?|посвящён|рассказывает|расскажет|разбирает|объясняет|показывает|знакомит)|in\s+this\s+(video|talk|lecture|episode|podcast|speech|session|recording)|(this|the)\s+(video|talk|lecture|episode|podcast|speech|session|recording)[^.]{0,30}?\s(is\s+about|covers|discusses|explores|presents|explains|focuses|describes|examines|tells|shows|walks|introduces))/iu;
    if (isStr(d.tldr) && META_TLDR.test(String(d.tldr))) SOFT.push(`tldr starts with a meta opening ("${String(d.tldr).slice(0, 50)}…"): start with the subject itself and its main conclusion, not with "В этом видео" / "This video"`);
    // Every timestamp in the digest is a paragraph timestamp of transcript.clean (PARAGRAPHS in the
    // prompt); part boundaries may also be 0 and the duration. Anything else was invented.
    const pStarts = (ctx.starts || []).map(Number);
    const bounds = pStarts.concat([0, dur]);
    const notParagraph = (where, v) => `${where} ${v} is not a paragraph start_seconds value from the PARAGRAPHS list: copy timestamps exactly, never invent or round them`;
    // Minimums by duration (2026-09-21, same ladder as structure): on a 19-second clip five theses were one fact
    // split five ways and three quotes were one sentence three times; on record the model gives 5+ theses and
    // 3+ distinct quotes from 2.6 minutes on its own.
    const minKeyPoints = dur < 120 ? 1 : dur < 240 ? 3 : 5;
    const minQuotes = dur < 120 ? 1 : dur < 240 ? 2 : 3;
    if (!Array.isArray(d.key_points) || d.key_points.length < minKeyPoints || d.key_points.length > 12) { HARD.push(`key_points must have ${minKeyPoints}-12 items for a ${Math.round(dur)} s video (got ${Array.isArray(d.key_points) ? d.key_points.length : 'none'})`); d.key_points = Array.isArray(d.key_points) ? d.key_points : []; }
    for (const [i, k] of d.key_points.entries()) {
      if (!k || typeof k !== 'object') { HARD.push(`key_points[${i}] must be an object with text, detail and start`); continue; }
      if (!isStr(k.text)) HARD.push(`key_points[${i}].text must be a non-empty string`);
      if (typeof k.detail !== 'string') HARD.push(`key_points[${i}].detail must be a string`);
      if (!isNum(k.start) || k.start < 0 || k.start > dur + tol) { HARD.push(`key_points[${i}].start must be a number between 0 and ${dur}`); continue; }
      if (pStarts.length) { const s = snapTo(pStarts, k.start, tol); if (s === null) HARD.push(notParagraph(`key_points[${i}].start`, k.start)); else k.start = s; }
    }
    let structureOk = true;
    // Minimum parts by duration (2026-09-21): three parts need three topic shifts, and a video under two minutes
    // has one topic – a 19-second clip fell twice on «3-10 items (got 1)» after a paid transcription. On record the
    // model gave three parts from 2.6 minutes (0.9 min each); under four minutes two are enough, above it three.
    const minParts = dur < 120 ? 1 : dur < 240 ? 2 : 3;
    if (!Array.isArray(d.structure) || d.structure.length < minParts || d.structure.length > 10) { HARD.push(`structure must have ${minParts}-10 items for a ${Math.round(dur)} s video (got ${Array.isArray(d.structure) ? d.structure.length : 'none'})`); d.structure = Array.isArray(d.structure) ? d.structure : []; structureOk = d.structure.length > 0; }
    for (const [i, x] of d.structure.entries()) {
      if (!x || typeof x !== 'object') { HARD.push(`structure[${i}] must be an object with title, start, end and summary`); structureOk = false; continue; }
      if (!isStr(x.title)) HARD.push(`structure[${i}].title must be a non-empty string`);
      if (typeof x.summary !== 'string') HARD.push(`structure[${i}].summary must be a string`);
      if (!isNum(x.start) || !isNum(x.end) || x.start < 0 || x.end > dur + tol) { HARD.push(`structure[${i}] "${x.title}" needs numeric start and end between 0 and ${dur}`); structureOk = false; continue; }
      if (pStarts.length) {
        const s = snapTo(bounds, x.start, tol); if (s === null) { HARD.push(notParagraph(`structure[${i}].start`, x.start)); structureOk = false; } else x.start = s;
        const e = snapTo(bounds, x.end, tol); if (e === null) { HARD.push(notParagraph(`structure[${i}].end`, x.end)); structureOk = false; } else x.end = e;
      }
    }
    if (structureOk) {
      // Rule 7: sorted, consecutive, 0 to duration. Sorting is lossless and done here; every hole,
      // overlap, nested or empty part is reported at once with its fix (partitionProblems), so that the
      // one correction attempt can close all of them. The first part may start with the first spoken
      // words and the last may stop at the last ones: both are snapped to 0 and duration afterwards.
      d.structure.sort((a, b) => a.start - b.start);
      const problems = partitionProblems(d.structure, null, null, tol, 'part', 10);
      if (d.structure[0].start > 60) problems.push('structure[0].start must be 0 (the first part starts at the beginning of the video)');
      if (d.structure[d.structure.length - 1].end < dur - 60) problems.push(`the last part must end at ${dur} (the end of the video)`);
      if (problems.length) HARD.push(`structure must be consecutive parts from 0 to ${dur} without gaps, overlaps or nesting (an advertisement inside a topic cuts it into topic, advertisement, topic again; take boundaries for uncovered spans from PARAGRAPHS): ${problems.join('; ')}`);
    }
    // Style rules from docs/result-schema.md section 9: claims, not topics; content titles and summaries.
    const META_SUMMARY = /^(обсужда|рассматрива|объясня|разбира|описыва|представля|подводится|подведение|обзор|discuss|overview|explain|describ|present|summing up|summar|cover)/i;
    const LIST_OR_POPULAR = /(включа(ет|ют)|includ(e|es)|такие как|such as|являются? (популярн|известн|распространённ)|(is|are) (a )?(popular|well-known|widely used))/i;
    const GENERIC_TITLE = /^(введение|заключение|вступление|основная часть|итоги|выводы|introduction|conclusion|main part|summary|overview|intro|outro)\.?$/i;
    const ALLOWED_TITLE = /^(реклама|вступление канала|advertisement|channel intro)$/i;
    for (const [i, x] of d.structure.entries()) {
      if (!x || typeof x !== 'object') continue;
      if (META_SUMMARY.test(String(x.summary).trim())) SOFT.push(`structure[${i}].summary starts with a meta verb ("${String(x.summary).slice(0, 40)}…"): state what the part claims, not what it discusses`);
      if (GENERIC_TITLE.test(String(x.title).trim()) && !ALLOWED_TITLE.test(String(x.title).trim())) SOFT.push(`structure[${i}].title "${x.title}" is a generic label: name what the part is about`);
    }
    // \b is ASCII-only in JS regexes: after a Cyrillic letter it never matches, so these rules use an
    // explicit "not followed by a letter" lookahead with the u flag.
    const RETELL = /^\s*(спикер|автор|лектор|докладчик|ведущий|он|она|[А-ЯЁ][а-яё]+(\s[А-ЯЁ][а-яё]+)?)\s+(отмечает|подч[её]ркивает|призывает|говорит|рассказывает|объясняет|утверждает|считает|заявляет|делится|описывает|советует|напоминает)(?!\p{L})|^\s*(the\s+)?(speaker|author|lecturer|presenter|he|she|[A-Z][a-z]+(\s[A-Z][a-z]+)?)\s+(notes|emphasi[sz]es|urges|says|explains|argues|states|claims|shares|describes|advises|reminds|points out|stresses)(?!\p{L})/u;
    const NOT_A_CLAIM = /(являются?|служат?|стали?|стал[аи]?)\s+(напутствием|призывом|советом|наставлением|лозунгом|девизом)|(?<!\p{L})(serves?|served|is|are|became|remains?)\s+(as\s+)?(a|an|the)?\s*(parting\s+(word|advice)|call to action|motto|slogan|reminder)(?!\p{L})/iu;
    for (const [i, k] of d.key_points.entries()) {
      if (!k || typeof k !== 'object') continue;
      if (LIST_OR_POPULAR.test(String(k.text))) SOFT.push(`key_points[${i}].text is a property list or a popularity statement ("${String(k.text).slice(0, 60)}…"): one claim with its reason`);
      if (NOT_A_CLAIM.test(String(k.text))) SOFT.push(`key_points[${i}].text describes the words as a message ("${String(k.text).slice(0, 60)}…"): state the claim itself, what is true and why`);
      if (RETELL.test(String(k.detail))) SOFT.push(`key_points[${i}].detail retells the speaker ("${String(k.detail).slice(0, 50)}…"): give the reason or example directly, "X, because Y", without "the speaker notes that"`);
    }
    if (!Array.isArray(d.quotes)) { HARD.push('quotes must be an array'); d.quotes = []; }
    if (d.quotes.length > 8) HARD.push(`quotes must have 3-8 items (got ${d.quotes.length})`);
    const translate = ctx.output_language && ctx.source_language && ctx.output_language !== ctx.source_language;
    let quotesOk = true;
    const untranslated = [];
    for (const [i, q] of d.quotes.entries()) {
      if (!q || !isStr(q.text)) { HARD.push(`quotes[${i}].text must be a non-empty string`); quotesOk = false; continue; }
      if (!isNum(q.start) || q.start < 0 || q.start > dur + tol) { HARD.push(`quotes[${i}].start must be a number between 0 and ${dur}`); quotesOk = false; }
      if (q.translation !== null && q.translation !== undefined && typeof q.translation !== 'string') HARD.push(`quotes[${i}].translation must be a string or null`);
      else if (translate && !(typeof q.translation === 'string' && q.translation.trim())) untranslated.push(i);
      else if (!translate && q.translation) HARD.push(`quotes[${i}].translation must be null: output and source language are the same`);
    }
    if (untranslated.length) HARD.push(`quotes[${untranslated.join(', ')}].translation is required: the output language ${ctx.output_language} differs from the source language ${ctx.source_language}, give each quote its translation into ${ctx.output_language}`);
    if (quotesOk) {
      // Quotes are pruned, not retried: a quote that is not verbatim, starts with a demonstrative word
      // or duplicates a key point is dropped (docs/result-schema.md section 4: "иначе выкидывается");
      // the answer is rejected only when fewer than 3 quotes survive.
      const DEMONSTRATIVE = /^[«"'“(]?\s*(это|этот|эта|эти|этим|этому|той|тот|та|те|this|that|these|those|it)(?!\p{L})/iu;
      const cleanText = normalize(ctx.clean_text || '');
      const sentences = String(ctx.clean_text || '').split(/(?<=[.!?…])\s+/).map(normalize).filter(Boolean);
      const dropped = [];
      const kept = [];
      for (const [j, q] of d.quotes.entries()) {
        let why = null;
        if (!quoteFound(q.text, cleanText, sentences)) why = 'not a verbatim fragment of the transcript';
        else if (DEMONSTRATIVE.test(String(q.text).trim())) why = 'starts with a demonstrative word, not understandable on its own';
        else {
          const dup = d.key_points.findIndex((k) => k && [q.text, q.translation].some((cand) => cand && dice(normalize(String(k.text)), normalize(cand)) >= 0.8));
          if (dup >= 0) why = `repeats key_points[${dup}]`;
        }
        // The same sentence twice counts once (a 19-second clip answered with one quote three times, 2026-09-21).
        if (!why && kept.some((k) => dice(normalize(String(k.text)), normalize(String(q.text))) >= 0.9)) why = 'repeats an earlier quote';
        if (why) dropped.push(`quotes[${j}] "${String(q.text).slice(0, 60)}": ${why}`); else kept.push(q);
      }
      if (kept.length < minQuotes) HARD.push(`only ${kept.length} of ${d.quotes.length} quotes are acceptable, at least ${minQuotes} are needed for a ${Math.round(dur)} s video. Choose only from the candidate quotes in the notes and copy them character for character; a quote must not repeat a key point and must not start with "Это"/"This". Dropped: ${dropped.join('; ') || 'none'}`);
      else { d.quotes = kept; if (dropped.length) d._dropped_quotes = dropped; }
    }
    if (HARD.length) return (HARD.length > 1 ? `${HARD.length} problems, fix all of them. ` : '') + HARD.join('; ');
    return null;
  }
  // ---- extras blocks (docs/result-schema.md section 5)
  const dur = Number(ctx.duration_sec || 0) + 1.0;
  const tc = (v, where) => (!isNum(v) || v < 0 || v > dur) ? `${where}.start must be a number between 0 and ${Math.round(dur)}` : null;
  const strOrNull = (v) => v === null || v === undefined || typeof v === 'string';
  if (kind === 'glossary') {
    if (!Array.isArray(d.glossary) || d.glossary.length < 3 || d.glossary.length > 20) return `glossary must have 3-20 entries (got ${Array.isArray(d.glossary) ? d.glossary.length : 'none'})`;
    for (const [i, g] of d.glossary.entries()) { if (!isStr(g.term)) return `glossary[${i}].term must be a non-empty string`; if (!isStr(g.definition)) return `glossary[${i}].definition must be a non-empty string`; const e = tc(g.start, `glossary[${i}]`); if (e) return e; }
    return null;
  }
  if (kind === 'critique') {
    const c = d.critique;
    if (!c || typeof c !== 'object') return 'critique must be an object';
    for (const k of ['strong', 'missing']) { if (!Array.isArray(c[k]) || !c[k].every((x) => isStr(x))) return `critique.${k} must be an array of non-empty strings`; }
    if (!Array.isArray(c.weak) || c.weak.length < 1 || c.weak.length > 8) return `critique.weak must have 1-8 items (got ${Array.isArray(c.weak) ? c.weak.length : 'none'})`;
    for (const [i, w] of c.weak.entries()) { if (!isStr(w.claim)) return `critique.weak[${i}].claim must be a non-empty string`; if (!isStr(w.issue)) return `critique.weak[${i}].issue must be a non-empty string`; const e = tc(w.start, `critique.weak[${i}]`); if (e) return e; }
    const GENERIC_ISSUE = /^(нет доказательств|нет примеров|логический скачок|обобщение|no evidence|logical leap|unsupported|overgeneralization)\.?$/i;
    for (const [i, w] of c.weak.entries()) if (GENERIC_ISSUE.test(String(w.issue).trim())) SOFT.push(`critique.weak[${i}].issue is a generic label ("${w.issue}"): name what exactly is missing for this claim`);
    return null;
  }
  if (kind === 'self_check') {
    if (!Array.isArray(d.self_check) || d.self_check.length < 3 || d.self_check.length > 12) return `self_check must have 3-12 items (got ${Array.isArray(d.self_check) ? d.self_check.length : 'none'})`;
    for (const [i, q] of d.self_check.entries()) { if (!isStr(q.question)) return `self_check[${i}].question must be a non-empty string`; if (!isStr(q.answer)) return `self_check[${i}].answer must be a non-empty string`; const e = tc(q.start, `self_check[${i}]`); if (e) return e; }
    return null;
  }
  if (kind === 'action_items') {
    if (!Array.isArray(d.action_items)) return 'action_items must be an array (empty when nothing was assigned)';
    for (const [i, a] of d.action_items.entries()) { if (!isStr(a.text)) return `action_items[${i}].text must be a non-empty string`; if (!strOrNull(a.owner) || !strOrNull(a.due)) return `action_items[${i}].owner and due must be strings or null`; const e = tc(a.start, `action_items[${i}]`); if (e) return e; }
    return null;
  }
  if (kind === 'decisions' || kind === 'questions') {
    if (!Array.isArray(d[kind])) return `${kind} must be an array (empty when there are none)`;
    for (const [i, x] of d[kind].entries()) { if (!isStr(x.text)) return `${kind}[${i}].text must be a non-empty string`; const e = tc(x.start, `${kind}[${i}]`); if (e) return e; }
    return null;
  }
  return null;
}
"""

DONE_JS = r"""// Uniform output of llm-call: {ok, data, error, usage, attempts, ms, model, model_actual, kind, label}.
// model = the name requested in Prepare, model_actual = the id the provider reported in the answer.
const v = $input.first().json;
const state = v.attempt === 2 ? $('Retry').first().json : $('Prepare').first().json;
const prev = (state.usage1 || { in: 0, out: 0 });
const usage = { in: (v.usage.in || 0) + (prev.in || 0), out: (v.usage.out || 0) + (prev.out || 0) };
// events: provider_retry rows of both attempts (attempt 1's rows travel in the Retry state).
const events = [...((state.events1 || [])), ...(v.events || [])];
return [{ json: { ok: !!v.ok, error: v.error || null, terminal: !!v.terminal, data: v.data || null, warnings: v.warnings || [], lost_starts: v.lost_starts || [], usage, attempts: v.attempt, ms: Date.now() - state.started, model: state.model, model_actual: v.model_actual || null, auth: !!v.auth, retry_error: state.error1 || null, kind: state.kind, label: state.label, events } }];
"""

def llm_http(name, state, x, y):
    # No retryOnFail: it is blind to the status code (and never fired on 429/5xx anyway, neverError makes them items).
    # The transport loop after Validate re-runs this node; the body comes from the state node, not from the loop item.
    return node(name, "n8n-nodes-base.httpRequest", 4.5, {
        "method": "POST", "url": f"={{{{ $('{state}').first().json.base_url }}}}/chat/completions",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json", "jsonBody": f"={{{{ JSON.stringify($('{state}').first().json.body) }}}}",
        "options": {"timeout": 300000, "response": {"response": {"fullResponse": True, "neverError": True, "responseFormat": "json"}}},
    }, x, y, credentials={"httpHeaderAuth": {"name": "LLM API"}}, onError="continueRegularOutput")

def wait_node(name, amount_expr, x, y):
    # webhookId is assigned by n8n on import and copied back from the export by name (see the write loop below).
    return node(name, "n8n-nodes-base.wait", 1.1, {"amount": "=" + amount_expr, "unit": "seconds"}, x, y)

llm_nodes = [
    node("When called", "n8n-nodes-base.executeWorkflowTrigger", 1.2, {"inputSource": "workflowInputs", "workflowInputs": {"values": [
        {"name": "system", "type": "string"}, {"name": "user", "type": "string"}, {"name": "kind", "type": "string"},
        {"name": "context", "type": "object"}, {"name": "label", "type": "string"}]}}, 0, 0),
    # Same price file as the pipeline; a missing or broken file must not block the call (see jobs-api).
    node("Read pricing", "n8n-nodes-base.readWriteFile", 1, {"operation": "read", "fileSelector": "/data/pricing.json", "options": {}}, 220, 0, alwaysOutputData=True, onError="continueRegularOutput"),
    node("Parse pricing", "n8n-nodes-base.extractFromFile", 1, {"operation": "fromJson", "binaryPropertyName": "data", "options": {}}, 440, 0, alwaysOutputData=True, onError="continueRegularOutput"),
    code("Prepare", PREPARE_JS, 660, 0),
    llm_http("LLM request 1", "Prepare", 880, 0),
    code("Validate 1", VALIDATE_JS.replace("__CLEAN_RETENTION__", CLEAN_RETENTION_JS).replace("__TRANSPORT__", TRANSPORT_JS).replace("__ATTEMPT__", "1").replace("__STATE__", "Prepare"), 1100, 0),
    if_bool("Transport retry 1?", "{{ $json.transport_retry === true }}", 1320, -200),
    wait_node("Wait 1", "{{ $json.wait_sec }}", 1100, -400),
    if_bool("Valid 1?", "{{ $json.ok || $json.terminal === true }}", 1320, 0),
    code("Retry", RETRY_JS, 1540, 200),
    llm_http("LLM request 2", "Retry", 1760, 200),
    if_bool("Transport retry 2?", "{{ $json.transport_retry === true }}", 2200, 400),
    wait_node("Wait 2", "{{ $json.wait_sec }}", 1980, 600),
    code("Validate 2", VALIDATE_JS.replace("__CLEAN_RETENTION__", CLEAN_RETENTION_JS).replace("__TRANSPORT__", TRANSPORT_JS).replace("__ATTEMPT__", "2").replace("__STATE__", "Retry"), 1980, 200),
    code("Done", DONE_JS, 2200, 0),
]
lc = {}
wire(lc, "When called", "Read pricing"); wire(lc, "Read pricing", "Parse pricing"); wire(lc, "Parse pricing", "Prepare"); wire(lc, "Prepare", "LLM request 1"); wire(lc, "LLM request 1", "Validate 1")
wire(lc, "Validate 1", "Transport retry 1?"); wire(lc, "Transport retry 1?", "Wait 1", 0); wire(lc, "Wait 1", "LLM request 1"); wire(lc, "Transport retry 1?", "Valid 1?", 1)
wire(lc, "Valid 1?", "Done", 0); wire(lc, "Valid 1?", "Retry", 1)
wire(lc, "Retry", "LLM request 2"); wire(lc, "LLM request 2", "Validate 2"); wire(lc, "Validate 2", "Transport retry 2?"); wire(lc, "Transport retry 2?", "Wait 2", 0); wire(lc, "Wait 2", "LLM request 2"); wire(lc, "Transport retry 2?", "Done", 1)
llm_call = {"name": "llm-call", "nodes": llm_nodes, "connections": lc, "settings": {"executionOrder": "v1"}}

# ----------------------------------------------------------------- log-events (sub-workflow)
EVENT_ROWS_JS = r"""// One row per event (contract section 4), over every input item: the caller may hand over several jobs at
// once (maintenance expiring a batch); reading only the first item lost the rest (found 2026-09-17).
// Masking is repeated here: nothing key-shaped reaches the table.
const mask = (t) => String(t).replace(/\b(sk|gsk|rk|xai)[-_][^\s"'\\]{6,}/g, (m) => m.slice(0, 3) + '***').replace(/\b[A-Za-z0-9_-]{32,}\b/g, '***').replace(/(Bearer|Token)\s+[^\s"']+/gi, '$1 ***');
// '-' and 0 stand for null: the Postgres node drops empty query parameters.
return $input.all().flatMap((item) => {
  const inp = item.json || {};
  const events = Array.isArray(inp.events) ? inp.events : [];
  return events.filter((e) => e && e.type).map((e) => ({ json: {
    job_id: String(inp.job_id || '-'), stage: String(e.stage || '-'), type: String(e.type), level: String(e.level || 'info'),
    provider: String(e.provider || '-'), model: String(e.model || '-'), http_status: Number(e.http_status) || 0,
    body: mask(e.body || '').slice(0, 300) || '-', retention_days: Number($env.EVENTS_RETENTION_DAYS || 7),
  } }));
});
"""

EVENT_INSERT_SQL = """with gc as (delete from events where ts < now() - ($9::int * interval '1 day'))
insert into events (job_id, stage, type, level, provider, model, http_status, body)
values (nullif($1, '-'), nullif($2, '-'), $3, $4, nullif($5, '-'), nullif($6, '-'), nullif($7::int, 0), nullif($8, '-'))"""
# One array expression, not a comma list: the Postgres node splits a plain list on commas, and event bodies contain them.
EVENT_INSERT_P = "{{ [$json.job_id, $json.stage, $json.type, $json.level, $json.provider, $json.model, $json.http_status, $json.body, $json.retention_days] }}"

log_nodes = [
    node("When events arrive", "n8n-nodes-base.executeWorkflowTrigger", 1.2, {"inputSource": "workflowInputs", "workflowInputs": {"values": [
        {"name": "job_id", "type": "string"}, {"name": "events", "type": "array"}]}}, 0, 0),
    code("Event rows", EVENT_ROWS_JS, 220, 0),
    # An insert failure is swallowed: the events table must never become a dependency of a job.
    pg("Insert event", EVENT_INSERT_SQL, EVENT_INSERT_P, 440, 0, onError="continueRegularOutput"),
]
lg = {}
wire(lg, "When events arrive", "Event rows"); wire(lg, "Event rows", "Insert event")
log_events_wf = {"name": "log-events", "nodes": log_nodes, "connections": lg, "settings": {"executionOrder": "v1"}}

# ----------------------------------------------------------------- pipeline (real, up to digest)
COLLECT_EXTRAS_JS = r"""// Pair each extracted text with its file name (Extract From File drops the input json).
const files = $('Read extras prompts').all();
const texts = $input.all();
const prompts = {};
texts.forEach((t, i) => {
  const name = String(((files[i] || {}).json || {}).fileName || '').replace(/\.md$/, '');
  if (name && !name.startsWith('_')) prompts[name] = t.json.data;
});
return [{ json: { extras_prompts: prompts } }];
"""

INIT_JS = JS_HELPERS + r"""
// Assemble the pipeline state S: job row, prompts, pricing, stage plan. S travels through the flow.
// Postgres status writes sit in the main chain (dead-end branches run last in n8n and would
// overwrite the final state); the node after a write takes S from the named Code node before it.
const job = $('Load job').first().json;
const meta = job.meta || {};
const probe = meta.probe || {};
const useSubs = probe.recommended === 'subtitles_manual';
// Pre-start key check (contract section 5, step 0): a cheap authenticated GET /models through the same
// credentials the stages use. Only providers with such an endpoint are checked; nothing is invented.
// Deepgram: GET /v1/auth/token (answers 401 with a plain-text body, hence the autodetect response format on its node).
const LLM_CHECK = { openai: 'https://api.openai.com/v1/models', groq: 'https://api.groq.com/openai/v1/models' };
const STT_CHECK = { ...LLM_CHECK, deepgram: 'https://api.deepgram.com/v1/auth/token' };
const sttProvider = String($env.STT_PROVIDER || 'openai').toLowerCase();
const llmProvider = String($env.LLM_PROVIDER || 'openai').toLowerCase();
const authChecks = { llm: LLM_CHECK[llmProvider] || null, stt: !useSubs ? (STT_CHECK[sttProvider] || null) : null, stt_deepgram: sttProvider === 'deepgram' };
// Extras blocks come from `options` alone (2026-09-30, step E4): the preset sets the checkbox defaults on the
// front and steers the digest prompts, it no longer adds blocks by itself, so a default can be unchecked.
const extrasBlocks = [...new Set(job.options || [])];
const stages = ['probe', 'download', 'transcribe', 'clean', 'digest', 'extras'].map((name) => ({
  name,
  status: name === 'probe' ? 'done' : (name === 'transcribe' && useSubs) ? 'skipped' : (name === 'extras' && extrasBlocks.length === 0) ? 'skipped' : 'pending',
}));
delete meta.fake;
meta.stages = [{ name: 'probe', status: 'done', ms: 0, cost_usd: 0 }];
meta.providers = { stt: sttProvider, stt_model: String($env.STT_MODEL || (sttProvider === 'deepgram' ? 'nova-3' : 'whisper-1')), llm: String($env.LLM_PROVIDER || 'openai'), llm_model_map: String($env.LLM_MODEL_MAP || $env.LLM_MODEL || 'gpt-4o-mini'), llm_model_reduce: String($env.LLM_MODEL_REDUCE || $env.LLM_MODEL || 'gpt-4o-mini') };
meta.tokens = { in: 0, out: 0 };
meta.pipeline_started_at = new Date().toISOString();
// The n8n execution behind this job (2026-09-21): the on-error workflow finds the job by it when a node throws, and
// a complaint on the day of the post can be traced to its execution: select meta->>'execution_id' from jobs where id = …
meta.execution_id = String($execution.id);
const src = job.source || {};
const S = {
  job, stages, meta, use_subs: useSubs, source_id: job.source_id, lang: job.source_language, out_lang: job.output_language,
  preset: job.preset, title: src.title || '', duration: Number(src.duration_sec || 0),
  prompts: { clean: stripHeader($('Text clean').first().json.data), map: stripHeader($('Text map').first().json.data), reduce: stripHeader($('Text reduce').first().json.data) },
  extras_prompts: Object.fromEntries(Object.entries($('Collect extras prompts').first().json.extras_prompts || {}).map(([k, v]) => [k, stripHeader(v)])),
  extras_blocks: extrasBlocks,
  pricing: $('Parse pricing').first().json.data || {},
  auth_checks: authChecks,
  failed: false,
};
// A prompt file that did not load (mount missing, file renamed) must refuse the job here, before anything is paid
// for, not hang it: the read nodes degrade to an item without data (see read_text).
for (const [k, v] of Object.entries(S.prompts)) if (!v || v === 'undefined' || v.length < 50) return [{ json: withDb(failItem(S, 'probe', 'internal_error', `prompt file for ${k} is missing or empty under /data/prompts: check the prompts mount`)) }];
return [{ json: withDb(S) }];
"""

AUTH_CHECK_JS = JS_HELPERS + r"""// Pre-start key check (contract section 5, step 0). Only an explicit 401/403 may stop the job: a timeout,
// a 5xx, a network error or an empty answer is logged and the job goes on – a service check must not
// become a hard dependency of the start (the pricing.json lesson). Nothing has been paid for yet here.
const S = $('Init').first().json;
const results = [];
S.events = [];
const checks = S.auth_checks || {};
if (!checks.llm) S.events.push({ type: 'key_check_skipped', level: 'info', stage: 'clean', provider: S.meta.providers.llm, body: 'no cheap authenticated endpoint for this provider' });
if (!checks.stt) S.events.push({ type: 'key_check_skipped', level: 'info', stage: 'transcribe', provider: S.meta.providers.stt, body: S.use_subs ? 'subtitles, no STT' : 'no cheap authenticated endpoint for this provider' });
const take = (name, stage, provider) => {
  let r = null;
  try { if ($(name).isExecuted) r = $(name).first().json; } catch (e) { r = { statusCode: 0, body: String(e.message) }; }
  if (r) results.push({ name, stage, provider, status: Number(r.statusCode) || 0, body: r.body });
};
take('Check LLM key', 'clean', S.meta.providers.llm);
take('Check STT key', 'transcribe', S.meta.providers.stt);
take('Check Deepgram key', 'transcribe', S.meta.providers.stt);
for (const r of results) {
  if (isAuthStatus(r.status)) {
    logAuth(S, r.stage, r.provider, r.status, r.body, 'pre-start key check, nothing spent');
    const body = maskSecrets(JSON.stringify(r.body)).slice(0, 300);
    S.events.push({ type: 'key_check_failed', level: 'error', stage: r.stage, provider: r.provider, http_status: r.status, body });
    S.events.push({ type: 'provider_auth', level: 'error', stage: r.stage, provider: r.provider, http_status: r.status, body: 'pre-start key check, nothing spent: ' + body });
    S.prestart_auth = true;
    return [{ json: failItem(S, r.stage, 'provider_auth', `${r.provider} rejected the key before start (HTTP ${r.status}): ${JSON.stringify(r.body).slice(0, 200)}`) }];
  }
  if (r.status !== 200) {
    console.log(`[video-digest] key check inconclusive job=${S.job.id} stage=${r.stage} provider=${r.provider} status=${r.status}: job continues`);
    S.events.push({ type: 'key_check_skipped', level: 'warn', stage: r.stage, provider: r.provider, http_status: r.status, body: 'inconclusive, job continues: ' + maskSecrets(JSON.stringify(r.body)).slice(0, 200) });
  } else S.events.push({ type: 'key_check_ok', level: 'info', stage: r.stage, provider: r.provider, http_status: 200 });
}
return [{ json: withDb(S) }];
"""

DOWNLOAD_START_JS = JS_HELPERS + r"""
const S = $('Init').first().json;
S.stages = setStage(S.stages, 'download', { status: 'running' });
S.t_download = Date.now();
const probe = (S.meta.probe || {});
S.download_body = S.use_subs ? { source_id: S.source_id, mode: 'subtitles_manual', lang: S.lang } : { source_id: S.source_id, mode: 'audio' };
return [{ json: withDb(S) }];
"""

DOWNLOAD_DONE_JS = JS_HELPERS + r"""
const S = $('Download start').first().json;
const resp = $input.first().json;
if (resp.statusCode !== 200) {
  const err = (resp.body && resp.body.error) || { code: 'download_failed', message: `media service returned ${resp.statusCode}` };
  return [{ json: failItem(S, 'download', err.code || 'download_failed', err.message) }];
}
const ms = Date.now() - S.t_download;
S.download = resp.body;
S.stages = setStage(S.stages, 'download', { status: 'done' });
S.meta.stages.push({ name: 'download', status: 'done', ms, cost_usd: 0 });
return [{ json: withDb(S) }];
"""

SUBS_SEGMENTS_JS = JS_HELPERS + r"""
const S = $('Download done').first().json;
const resp = $input.first().json;
if (resp.statusCode !== 200 || !Array.isArray(resp.body)) return [{ json: failItem(S, 'download', 'download_failed', `cannot read subtitles: HTTP ${resp.statusCode}`) }];
// Subtitle cues can run past the video (VK: a cue ending 1.25 s after the duration, j_7etqho); rule 2 of the schema
// allows no segment beyond duration_sec, so ends are clamped to the duration and starts to their ends.
const dur = Number(S.duration || 0);
S.segments = resp.body.map((s) => { const end = dur > 0 ? Math.min(Number(s.end), dur) : Number(s.end); return { start: Math.min(Number(s.start), end), end, text: String(s.text), speaker: null }; });
S.origin = 'subtitles_manual';
S.language_detected_by = 'subtitles';
S.language_confidence = 1.0;
S.meta.stages.push({ name: 'transcribe', status: 'skipped', ms: 0, cost_usd: 0 });
return [{ json: withDb(S) }];
"""

TRANSCRIBE_START_JS = JS_HELPERS + r"""
const S = $input.first().json;
// No progress until the chunk count is known: the front shows «подготовка» instead of 0/0.
S.stages = setStage(S.stages, 'transcribe', { status: 'running' });
S.t_transcribe = Date.now();
const provider = String($env.STT_PROVIDER || 'openai').toLowerCase();
// OpenAI-compatible providers share one node and differ by base URL; Deepgram has its own API
// (POST /v1/listen, binary body, Token header, another response shape), so the loop routes to a separate node.
const BASES = { openai: 'https://api.openai.com/v1', groq: 'https://api.groq.com/openai/v1' };
S.stt_provider = provider;
S.stt_base_url = BASES[provider] || $env.STT_BASE_URL || 'http://localhost:8080/v1';
S.stt_model = String($env.STT_MODEL || (provider === 'deepgram' ? 'nova-3' : 'whisper-1'));
S.split_body = { source_id: S.source_id };
return [{ json: withDb(S) }];
"""

CHUNKS_JS = JS_HELPERS + r"""
// One item per audio chunk for the STT loop.
const S = $('Transcribe start').first().json;
const resp = $input.first().json;
if (resp.statusCode !== 200) {
  const err = (resp.body && resp.body.error) || {};
  // source_busy (409) keeps its own code: the source is held by another job, a retry later will work.
  return [{ json: loopFail(S, {}, 'transcribe', err.code === 'source_busy' ? 'source_busy' : 'stt_failed', `split failed: ${err.code || resp.statusCode} ${err.message || ''}`) }];
}
const chunks = resp.body.chunks || [];
// Zero chunks would give Loop chunks nothing, the branch would end and the job stay in processing (audit 2026-09-20).
if (!chunks.length) return [{ json: loopFail(S, {}, 'transcribe', 'stt_failed', 'split returned no chunks') }];
return chunks.map((c) => ({ json: { index: c.index, start: c.start, end: c.end, total: chunks.length, source_id: S.source_id, lang: S.lang, failed: false } }));
"""

CHUNK_TRANSCRIBED_JS = JS_HELPERS + r"""
// Shift the chunk's segments by chunk.start, report progress after every chunk. Two response shapes:
// OpenAI-compatible verbose_json (segments[]) and Deepgram (results.utterances[], metadata).
const chunk = $('Loop chunks').first().json;
const S = $('Transcribe start').first().json;
const resp = $input.first().json;
if (chunk.failed) return [{ json: chunk }];
if (resp && resp.skipped) return [{ json: resp }]; // an earlier chunk failed: this one was not requested (Chunk pending)
const dg = S.stt_provider === 'deepgram';
const transportRetries = resp.transport_events || [];
const bodyText = maskSecrets(resp.statusCode ? (typeof resp.body === 'string' ? resp.body : JSON.stringify(resp.body || {})) : String(resp.error && resp.error.message ? resp.error.message : resp.error || 'no answer'));
if (resp.statusCode !== 200) {
  // provider_auth also on 402 (Deepgram: credit exhausted) and 429 insufficient_quota – transport_auth from the check.
  const code = (isAuthStatus(resp.statusCode) || resp.transport_auth) ? 'provider_auth' : 'stt_failed';
  if (code === 'provider_auth') logAuth(S, 'transcribe', S.meta.providers.stt, resp.statusCode, resp.body);
  // Deepgram refuses an unknown model/language pair with 400 "No such model/language/tier combination found"
  // (fixtures/deepgram/400-language.json). The code goes as is, no silent fallback to "multi": the job
  // fails with a plain message and the language lands in events, so in a month we know what people bring.
  if (dg && resp.statusCode === 400 && /language/i.test(bodyText)) {
    const item = loopFail(S, chunk, 'transcribe', 'stt_failed', `Deepgram does not support language "${chunk.lang}" for ${S.stt_model}: ${bodyText.slice(0, 200)}`);
    item.fail.events = [{ type: 'stt_language_rejected', level: 'warn', stage: 'transcribe', provider: S.meta.providers.stt, model: S.stt_model, http_status: 400, body: `language ${chunk.lang}: ${bodyText.slice(0, 200)}` }];
    return [{ json: item }];
  }
  const item = loopFail(S, chunk, 'transcribe', code, `STT HTTP ${resp.statusCode || 0}: ${bodyText.slice(0, 300)}`);
  if (transportRetries.length) item.fail.events = [...(item.fail.events || []), ...transportRetries];
  return [{ json: item }];
}
const b = (resp.body && typeof resp.body === 'object') ? resp.body : {};
const shift = (t) => Math.round((chunk.start + Number(t)) * 1000) / 1000;
// Timestamps stay inside the chunk: Deepgram's last utterance can end past the audio (597.3 on a 596.1 s file),
// and rule 2 of the schema allows no segment beyond duration_sec.
const chunkEnd = Math.round(Number(chunk.end) * 1000) / 1000;
const span = (a, b) => { const end = Math.min(shift(b), chunkEnd); return { start: Math.min(shift(a), end), end }; };
let segments, language = null, duration, model_actual = null;
if (dg) {
  // speaker "<chunk>:<n>": Deepgram numbers speakers within one request, so "0" of chunk 2 is not
  // necessarily "0" of chunk 1. The chunk index keeps that visible instead of pretending otherwise.
  const r = b.results || {};
  segments = (r.utterances || []).map((u) => ({ ...span(u.start, u.end), text: String(u.transcript || '').trim(), speaker: u.speaker === undefined || u.speaker === null ? null : `${chunk.index}:${u.speaker}` }));
  const md = b.metadata || {};
  duration = Number(md.duration || (chunk.end - chunk.start));
  // metadata.model_info: {uuid: {name, version, arch}} – the released model behind the alias, for meta.stages.model_actual.
  const info = (md.model_info || {})[(md.models || [])[0]] || null;
  if (info) model_actual = [info.name, info.version].filter(Boolean).join(' ');
} else {
  segments = (b.segments || []).map((s) => ({ ...span(s.start, s.end), text: String(s.text || '').trim(), speaker: null }));
  language = b.language || null;
  duration = Number(b.duration || (chunk.end - chunk.start));
}
segments = segments.filter((s) => s.text);
const done = $runIndex + 1;
const stages = setStage(S.stages, 'transcribe', { status: 'running', progress: { done, total: chunk.total } });
return [{ json: { ...chunk, segments, language, duration, model_actual, events: transportRetries, job_id: S.job.id, p_stages: JSON.stringify(stages) } }];
"""

TRANSCRIBE_DONE_JS = JS_HELPERS + r"""
const S = $('Transcribe start').first().json;
const items = $input.all().map((i) => i.json);
const bad = items.find((i) => i.failed);
const transcribeEvents = items.flatMap((i) => (i.events || []).concat((i.fail && i.fail.events) || []));
if (bad) { const out = failItem(S, 'transcribe', bad.fail.code || 'stt_failed', bad.fail.message); if (transcribeEvents.length) out.fail.events = transcribeEvents; return [{ json: out }]; }
items.sort((a, b) => a.index - b.index);
const dg = S.stt_provider === 'deepgram';
// provider_retry rows of transcribe ride in the state until Clean done writes S.events (no log node after transcribe).
S.transcribe_events = transcribeEvents;
S.segments = items.flatMap((i) => i.segments);
const minutes = items.reduce((a, i) => a + (i.duration || 0), 0) / 60;
const price = (((S.pricing || {}).stt || {})[S.stt_model] || {}).per_minute || 0;
const cost = round4(minutes * price);
const modelActual = [...new Set(items.map((i) => i.model_actual).filter(Boolean))].join(', ') || null;
const record = { name: 'transcribe', status: 'done', ms: Date.now() - S.t_transcribe, cost_usd: cost, provider: `${S.meta.providers.stt}/${S.stt_model}`, minutes: Math.round(minutes * 100) / 100 };
if (modelActual) record.model_actual = modelActual;
// Empty-result guard, for every provider: a language the provider formally accepts but cannot transcribe
// comes back as 200 with an empty transcript (Deepgram nova-3, language=el on a Russian clip), and clean,
// digest and critique would then run on nothing, paid for, and hand the reader a document made of nothing
// without one error anywhere. Speech runs at about 110 words a minute; below STT_MIN_WORDS_PER_MIN the
// transcript is "nothing", not "little". Coarse on purpose: a false alarm costs a retry, a miss costs a
// document out of nothing, and a tight threshold would start refusing quiet lectures.
const STT_MIN_WORDS_PER_MIN = 20;
const words = S.segments.reduce((a, s) => a + wordsOf(s.text), 0);
const wpm = minutes > 0 ? words / minutes : 0;
if (minutes > 0 && wpm < STT_MIN_WORDS_PER_MIN) {
  const min1 = Math.round(minutes * 10) / 10;
  const out = failItem(S, 'transcribe', 'stt_failed', `transcript is empty: ${words} words in ${min1} minutes (${Math.round(wpm)} words/min, speech runs at about 110) for language "${S.lang}" on ${record.provider}; the model may not support this language`);
  out.fail.events = [{ type: 'stt_empty_result', level: 'error', stage: 'transcribe', provider: S.meta.providers.stt, model: S.stt_model, body: `${words} words, ${min1} min, ${Math.round(wpm)} words/min, language ${S.lang}` }];
  out.fail.stage_record = { ...record, status: 'failed', error: 'stt_failed' }; // the minutes were paid for: keep cost and model
  return [{ json: out }];
}
const langs = dg ? [] : [...new Set(items.map((i) => i.language).filter(Boolean))];
const detected = langs[0] || null;
S.origin = dg ? 'deepgram' : 'whisper';
// Deepgram takes the language code from the job and detects nothing; whisper reports what it heard.
S.language_detected_by = dg ? 'request' : 'whisper';
S.language_confidence = null; // neither OpenAI whisper-1 nor a Deepgram request with a fixed language reports a probability
if (detected && detected !== S.lang) S.meta.language_mismatch = { source_language: S.lang, whisper: detected };
S.stages = setStage(S.stages, 'transcribe', { status: 'done', progress: { done: items.length, total: items.length } });
S.meta.stages.push(record);
return [{ json: withDb(S) }];
"""

SEGMENTS_READY_JS = JS_HELPERS + r"""
// Both transcript branches arrive here. A transcript without segments (an empty subtitle track; the STT path is
// already guarded by words per minute) would give Clean chunks nothing to cut, Loop clean no item, and the job
// would stay in processing – so it fails here instead (audit of empty outputs, 2026-09-20).
const S = $input.first().json;
if (!S.failed && !((S.segments || []).length)) return [{ json: failItem(S, 'transcribe', 'stt_failed', `transcript has no segments (${S.origin || 'stt'}): nothing to clean`) }];
return [{ json: S }];
"""

CLEAN_START_JS = JS_HELPERS + r"""
const S = $input.first().json;
// No progress until the chunk count is known: the front shows «подготовка» instead of 0/0.
S.stages = setStage(S.stages, 'clean', { status: 'running' });
S.t_clean = Date.now();
return [{ json: withDb(S) }];
"""

CLEAN_CHUNKS_JS = JS_HELPERS + r"""
// Group raw segments into ~1000-word chunks; each item is one LLM call. On longer chunks
// gpt-4o-mini returns the whole chunk as one barely edited paragraph (a 59-minute lecture came
// back as 3 paragraphs at 4000 words; a 2300-word chunk collapsed twice in a row at 2000).
const S = $('Clean start').first().json;
const LIMIT = 1000;
const chunks = [];
let cur = [], n = 0;
for (const seg of S.segments) {
  const w = wordsOf(seg.text);
  if (n + w > LIMIT && cur.length) { chunks.push(cur); cur = []; n = 0; }
  cur.push(seg); n += w;
}
if (cur.length) chunks.push(cur);
if (!chunks.length) chunks.push([]);
return chunks.map((segs, i) => {
  const prev = i > 0 ? chunks[i - 1] : [];
  const contextWords = prev.map((s) => s.text).join(' ').split(/\s+/).slice(-80).join(' ');
  const words = segs.reduce((a, s) => a + wordsOf(s.text), 0);
  return { json: { index: i, total: chunks.length, lines: segs.map((s) => `[${fmtStart(s.start)}] ${s.text}`).join('\n'), context: contextWords, segments: segs, starts: segs.map((s) => s.start), words, failed: false } };
});
"""

CLEAN_REQUEST_JS = JS_HELPERS + r"""
const S = $('Clean start').first().json;
const c = $input.first().json;
// Concrete numbers for the paragraph split: a small model given "3-8 sentences" alone tends to return
// a long chunk as a single paragraph. Expected count = about one paragraph per 100 words.
const words = Number(c.words || 0);
const system = fill(S.prompts.clean, { SOURCE_LANGUAGE: S.lang, TITLE: S.title, CHUNK_INDEX: c.index + 1, CHUNK_TOTAL: c.total, CHUNK_WORDS: words, MIN_PARAGRAPHS: Math.max(1, Math.floor(words / 250)), EXPECTED_PARAGRAPHS: Math.max(1, Math.round(words / 100)) });
const user = (c.context ? `CONTEXT\n${c.context}\n\nTRANSCRIPT\n` : 'TRANSCRIPT\n') + (c.lines || '(no speech)');
// starts: the segment timestamps of this chunk; every paragraph start must be one of them.
return [{ json: { system, user, kind: 'clean', context: { output_language: S.lang, starts: c.starts || [], max_words: 250 }, label: `clean ${c.index + 1}/${c.total}` } }];
"""

CLEAN_CHUNK_DONE_JS = JS_HELPERS + r"""
const c = $('Loop clean').first().json;
const S = $('Clean start').first().json;
const r = $input.first().json;
let paragraphs, fallback = null;
if (r && r.ok) {
  paragraphs = r.data.paragraphs;
} else if (r && typeof r.error === 'string' && r.error.startsWith('content_filter')) {
  // The provider refuses to reproduce this text verbatim (famous speeches, lyrics). Fall back to a
  // rule-based clean so the job still completes; the stage is marked in meta.
  paragraphs = ruleClean(c.segments || []);
  fallback = 'content_filter';
} else if (r && r.data && typeof r.error === 'string') {
  // The model answered twice and both answers broke the rules (collapsed paragraphs, invented
  // timestamps). Rule-based clean keeps the timestamps honest; the stage is marked in meta.
  paragraphs = ruleClean(c.segments || []);
  fallback = 'validation: ' + r.error.slice(0, 160);
} else {
  if (r && r.auth) logAuth(S, 'clean', S.meta.providers.llm, 'llm', r.error);
  const item = loopFail(S, c, 'clean', r && r.auth ? 'provider_auth' : 'llm_failed', (r && (r.error || r.message)) || 'llm-call returned no data');
  item.fail.events = (r && r.events) || [];
  return [{ json: item }];
}
if (!fallback) alignStarts(paragraphs, c.segments || []);
const done = $runIndex + 1;
const stages = setStage(S.stages, 'clean', { status: 'running', progress: { done, total: c.total } });
return [{ json: { index: c.index, total: c.total, paragraphs, usage: (r && r.usage) || { in: 0, out: 0 }, model: (r && r.model) || null, model_actual: (r && r.model_actual) || null, attempts: (r && r.attempts) || 1, retry_error: (r && r.retry_error) || null, warnings: (r && r.warnings) || [], fallback, failed: false, job_id: S.job.id, p_stages: JSON.stringify(stages) , events: (r && r.events) || [] , lost_starts: (r && r.lost_starts) || [], chunk_start: ((c.segments || [])[0] || {}).start ?? null } }];

// The paragraph start comes from the transcript, not from the model: find the paragraph's first
// words in the segment stream near the timestamp the model gave and take that segment's start.
// The model copies timestamps almost always, but "almost" showed up as 3158.5 -> 3161.3.
function alignStarts(paragraphs, segments) {
  const norm = (t) => String(t).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim().split(' ').filter(Boolean);
  const stream = [];
  for (const s of segments) for (const w of norm(s.text)) stream.push({ w, start: s.start });
  if (!stream.length) return;
  let cursor = 0;
  for (const p of paragraphs) {
    const head = norm(p.text).slice(0, 8);
    if (head.length < 3) continue;
    const need = Math.min(3, head.length);
    let best = -1, bestScore = 0;
    for (let i = cursor; i < stream.length; i++) {
      if (Math.abs(stream[i].start - p.start) > 30) { if (stream[i].start > p.start) break; continue; }
      if (stream[i].w !== head[0] && stream[i].w !== head[1]) continue;
      const win = new Set(stream.slice(i, i + 12).map((x) => x.w));
      let score = 0;
      for (const h of head) if (win.has(h)) score++;
      if (score > bestScore) { bestScore = score; best = i; if (score === head.length) break; }
    }
    if (best >= 0 && bestScore >= need) { p.start = stream[best].start; cursor = best + 1; }
  }
}

function ruleClean(segments) {
  const FILLERS = /\b(um+|uh+|erm|hmm|э-?э+|ээ|мм+|ну вот|как бы|типа|значит|короче)\b[,\s]*/giu;
  const norm = (t) => String(t).replace(/\[[^\]]*\]|♪+/g, ' ').replace(/\s+/g, ' ').replace(FILLERS, '').replace(/\s+([,.!?;:])/g, '$1').trim();
  const out = [];
  let cur = null, words = 0, prevEnd = null;
  for (const s of segments) {
    const text = norm(s.text);
    if (!text) continue;
    const gap = prevEnd === null ? 0 : s.start - prevEnd;
    const endsSentence = cur && /[.!?…]$/.test(cur.text);
    if (!cur || (endsSentence && (gap > 2.0 || words >= 120))) {
      if (cur) out.push(cur);
      cur = { start: s.start, text }; words = text.split(/\s+/).length;
    } else {
      cur.text += ' ' + text; words += text.split(/\s+/).length;
    }
    prevEnd = s.end;
  }
  if (cur) out.push(cur);
  return out;
}
"""

CLEAN_DONE_JS = JS_HELPERS + r"""
const S = $('Clean start').first().json;
const items = $input.all().map((i) => i.json);
const bad = items.find((i) => i.failed);
if (bad) { const out = failItem(S, 'clean', bad.fail.code || 'llm_failed', bad.fail.message); out.fail.events = [...(S.transcribe_events || []), ...(bad.fail.events || [])]; return [{ json: out }]; }
S.events = [...(S.transcribe_events || []), ...retryEvents(items, 'clean', (i) => `clean ${i.index + 1}/${i.total}`), ...items.flatMap((i) => i.events || [])];
items.sort((a, b) => a.index - b.index);
// Rule 10 (retention) is soft: after the correction attempt the shorter text is accepted – worse than the full
// one, better than no result – and the loss is visible in quality_warnings and the events table.
for (const i of items) if (Array.isArray(i.warnings) && i.warnings.length) {
  // The retention message lists up to 15 sentences for the model; meta keeps the head of it, the events row the rest.
  S.meta.quality_warnings = [...(S.meta.quality_warnings || []), ...i.warnings.map((w) => ({ stage: 'clean', message: `clean ${i.index + 1}/${i.total}: ${String(w).slice(0, 300)}` }))];
  for (const w of i.warnings) if (String(w).startsWith('clean_retention') || String(w).startsWith('clean_lost_long') || String(w).startsWith('clean_lost_after_fix')) S.events.push({ type: 'clean_retention_low', level: 'warn', stage: 'clean', model: i.model || null, body: `clean ${i.index + 1}/${i.total}: ${String(w).slice(0, 240)}` });
}
S.clean = items.flatMap((i) => i.paragraphs).map((p) => ({ start: Number(p.start), text: String(p.text).trim() })).filter((p) => p.text);
// Empty clean (2026-09-20, j_jppvgs): with S.clean empty, Map chunks emits no item and the execution ends as a
// success without touching the job – it hung in processing until MAX_JOB_MINUTES. Fail loudly instead.
if (!S.clean.length) { const spoken = (S.segments || []).reduce((a, s) => a + wordsOf(s.text), 0); return [{ json: failItem(S, 'clean', 'llm_failed', `clean produced no text for ${items.length} chunk(s), ${spoken} words of transcript`) }]; }
const usage = items.reduce((a, i) => ({ in: a.in + (i.usage.in || 0), out: a.out + (i.usage.out || 0) }), { in: 0, out: 0 });
const model = (items.find((i) => i.model) || {}).model || S.meta.providers.llm_model_map;
const modelActual = [...new Set(items.map((i) => i.model_actual).filter(Boolean))].join(', ') || null;
const cost = round4(items.reduce((a, i) => a + llmCost(S.pricing, i.model || model, i.usage), 0));
S.meta.tokens = { in: S.meta.tokens.in + usage.in, out: S.meta.tokens.out + usage.out };
S.stages = setStage(S.stages, 'clean', { status: 'done', progress: { done: items.length, total: items.length } });
const fallbacks = items.filter((i) => i.fallback);
// result.notices (2026-09-23): places where the accepted text is shorter than the rule allows, and chunks cleaned
// by rules without the model – timecodes only, the reader's band is built from these on finalize.
S.clean_notices = {
  lost_starts: [...new Set(items.flatMap((i) => i.lost_starts || []).map(Number))].sort((a, b) => a - b),
  fallback_starts: fallbacks.map((i) => Number(i.chunk_start)).filter((x) => Number.isFinite(x)).sort((a, b) => a - b),
};
const entry = { name: 'clean', status: 'done', ms: Date.now() - S.t_clean, cost_usd: cost, model, model_actual: modelActual, tokens: usage, retries: items.reduce((a, i) => a + ((i.attempts || 1) - 1), 0) };
if (fallbacks.length) entry.note = `rule-based fallback for ${fallbacks.length}/${items.length} chunk(s): ${[...new Set(fallbacks.map((i) => i.fallback))].join('; ')}`;
S.meta.stages.push(entry);
return [{ json: withDb(S) }];
"""

DIGEST_START_JS = JS_HELPERS + r"""
const S = $input.first().json;
// No progress until the chunk count is known: the front shows «подготовка» instead of 0/0.
S.stages = setStage(S.stages, 'digest', { status: 'running' });
S.t_digest = Date.now();
return [{ json: withDb(S) }];
"""

MAP_CHUNKS_JS = JS_HELPERS + r"""
// Group clean paragraphs into ~4000-word chunks for digest-map.
const S = $('Digest start').first().json;
const LIMIT = 4000;
const chunks = [];
let cur = [], n = 0;
for (const p of S.clean) {
  const w = wordsOf(p.text);
  if (n + w > LIMIT && cur.length) { chunks.push(cur); cur = []; n = 0; }
  cur.push(p); n += w;
}
if (cur.length) chunks.push(cur);
return chunks.map((ps, i) => ({ json: {
  index: i, total: chunks.length,
  chunk_start: ps[0].start, chunk_end: i + 1 < chunks.length ? chunks[i + 1][0].start : S.duration,
  lines: ps.map((p) => `[${fmtStart(p.start)}] ${p.text}`).join('\n\n'), starts: ps.map((p) => p.start), chunk_text: ps.map((p) => p.text).join(' '), failed: false,
} }));
"""

MAP_REQUEST_JS = JS_HELPERS + r"""
const S = $('Digest start').first().json;
const c = $input.first().json;
const system = fill(S.prompts.map, { SOURCE_LANGUAGE: S.lang, OUTPUT_LANGUAGE: S.out_lang, PRESET: S.preset, TITLE: S.title, DURATION_SEC: S.duration, CHUNK_INDEX: c.index + 1, CHUNK_TOTAL: c.total, CHUNK_START: fmtStart(c.chunk_start), CHUNK_END: fmtStart(c.chunk_end) });
// starts: paragraph timestamps of this chunk; every start the model returns must be one of them.
// chunk_text / min_quotes: candidate quotes are checked verbatim against the chunk; a one-chunk video
// needs 3 verbatim candidates (the digest needs 3 quotes), longer videos 2 per chunk, tiny chunks none.
const words = wordsOf(c.chunk_text || '');
const min_quotes = words < 150 ? 0 : c.total === 1 ? 3 : 2;
return [{ json: { system, user: c.lines, kind: 'map', context: { source_language: S.lang, output_language: S.out_lang, starts: c.starts || [], chunk_end: c.chunk_end, chunk_text: c.chunk_text || '', min_quotes }, label: `map ${c.index + 1}/${c.total}` } }];
"""

MAP_CHUNK_DONE_JS = JS_HELPERS + r"""
const c = $('Loop map').first().json;
const S = $('Digest start').first().json;
const r = $input.first().json;
if (r && r.auth) logAuth(S, 'digest', S.meta.providers.llm, 'llm', r.error);
if (!r || !r.ok) { const item = loopFail(S, c, 'digest', r && r.auth ? 'provider_auth' : 'llm_failed', (r && (r.error || r.message)) || 'llm-call returned no data'); item.fail.events = (r && r.events) || []; return [{ json: item }]; }
const done = $runIndex + 1;
const stages = setStage(S.stages, 'digest', { status: 'running', progress: { done, total: c.total + 1 } });
return [{ json: { index: c.index, total: c.total, chunk_start: c.chunk_start, chunk_end: c.chunk_end, notes: r.data, warnings: r.warnings || [], usage: r.usage, model: r.model, model_actual: r.model_actual || null, attempts: r.attempts, retry_error: r.retry_error || null, failed: false, job_id: S.job.id, p_stages: JSON.stringify(stages) , events: r.events || [] } }];
"""

REDUCE_REQUEST_JS = JS_HELPERS + r"""
// Assemble the notes of all chunks into the digest-reduce user message.
const S = $('Digest start').first().json;
const items = $input.all().map((i) => i.json);
const bad = items.find((i) => i.failed);
if (bad) { const out = failItem(S, 'digest', bad.fail.code || 'llm_failed', bad.fail.message); out.fail.events = [...items.flatMap((i) => i.events || []), ...(bad.fail.events || [])]; return [{ json: out }]; }
items.sort((a, b) => a.index - b.index);
const usage = items.reduce((a, i) => ({ in: a.in + (i.usage.in || 0), out: a.out + (i.usage.out || 0) }), { in: 0, out: 0 });
S.map_usage = usage;
S.map_cost = items.reduce((a, i) => a + llmCost(S.pricing, i.model || S.meta.providers.llm_model_map, i.usage), 0);
S.map_model = (items.find((i) => i.model) || {}).model || S.meta.providers.llm_model_map;
S.map_model_actual = [...new Set(items.map((i) => i.model_actual).filter(Boolean))].join(', ') || null;
S.map_retries = items.reduce((a, i) => a + ((i.attempts || 1) - 1), 0);
S.map_retry_events = [...retryEvents(items, 'digest', (i) => `map ${i.index + 1}/${i.total}`), ...items.flatMap((i) => i.events || [])];
S.map_notes = items.map((i) => i.notes);
for (const i of items) if (Array.isArray(i.warnings) && i.warnings.length) S.meta.quality_warnings = [...(S.meta.quality_warnings || []), ...i.warnings.map((w) => ({ stage: 'digest', message: `map ${i.index + 1}/${i.total}: ${w}` }))];
const blocks = items.map((i) => {
  const n = i.notes;
  const kp = (n.key_points || []).map((k) => `- [${fmtStart(k.start)}] ${k.text}${k.detail ? ' — ' + k.detail : ''}`).join('\n');
  const sec = (n.sections || []).map((s) => `- [${fmtStart(s.start)}–${fmtStart(s.end)}] ${s.title}: ${s.summary || ''}`).join('\n');
  const q = (n.quotes || []).map((x) => `- [${fmtStart(x.start)}] "${x.text}"`).join('\n');
  const t = (n.terms || []).map((x) => `- ${x.term}: ${x.meaning || ''}`).join('\n');
  return `## Chunk ${i.index + 1}/${i.total} (${fmtStart(i.chunk_start)}–${fmtStart(i.chunk_end)} s)\n\nSummary: ${n.summary}\n\nKey points:\n${kp}\n\nSections:\n${sec}\n\nQuotes:\n${q}\n\nTerms:\n${t}`;
});
const system = fill(S.prompts.reduce, { SOURCE_LANGUAGE: S.lang, OUTPUT_LANGUAGE: S.out_lang, PRESET: S.preset, TITLE: S.title, DURATION_SEC: S.duration });
const clean_text = S.clean.map((p) => p.text).join(' ');
// Paragraph outline: timestamps the model can cut structure at when the map sections are coarse.
const outline = S.clean.map((p) => `[${fmtStart(p.start)}] ${p.text.split(/\s+/).slice(0, 12).join(' ')}…`).join('\n');
const user = blocks.join('\n\n') + '\n\nPARAGRAPHS\n' + outline;
return [{ json: { ...S, system, user, kind: 'digest', context: { duration_sec: S.duration, clean_text, starts: S.clean.map((p) => p.start), source_language: S.lang, output_language: S.out_lang }, label: 'digest-reduce' } }];
"""

DIGEST_DONE_JS = JS_HELPERS + r"""
// Whitelist fields (the result schema forbids extras), snap boundaries, account cost.
const S = $('Reduce request').first().json;
const r = $input.first().json;
if (r && r.auth) logAuth(S, 'digest', S.meta.providers.llm, 'llm', r.error);
if (!r || !r.ok) { const out = failItem(S, 'digest', r && r.auth ? 'provider_auth' : 'llm_failed', (r && (r.error || r.message)) || 'llm-call returned no data'); out.fail.events = [...(S.map_retry_events || []), ...((r && r.events) || [])]; return [{ json: out }]; }
S.events = [...(S.map_retry_events || []), ...retryEvents([{ ...r, index: 0, total: 1 }], 'digest', () => 'digest-reduce'), ...(r.events || [])];
const d = r.data;
const dur = S.duration;
const clamp = (x) => Math.min(Math.max(Number(x), 0), dur);
const structure = d.structure.map((s) => ({ title: String(s.title).trim(), start: clamp(s.start), end: clamp(s.end), summary: String(s.summary || '').trim() }));
structure[0].start = 0;
structure[structure.length - 1].end = dur;
for (let i = 1; i < structure.length; i++) structure[i].start = structure[i - 1].end;
// quotes[].start comes from the transcript: the paragraph in which the quote is found (exact
// normalized inclusion first, then the sentence with the best bigram similarity), not from the model.
const norm = (s) => String(s).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
const bigrams = (s) => { const b = new Set(); for (let i = 0; i < s.length - 1; i++) b.add(s.slice(i, i + 2)); return b; };
const dice = (a, b) => { const A = bigrams(a), B = bigrams(b); if (!A.size || !B.size) return 0; let n = 0; for (const x of A) if (B.has(x)) n++; return (2 * n) / (A.size + B.size); };
const paras = S.clean.map((p) => ({ start: p.start, text: norm(p.text), sentences: String(p.text).split(/(?<=[.!?…])\s+/).map(norm).filter(Boolean) }));
const quoteParagraph = (text) => {
  const nq = norm(text);
  if (!nq) return null;
  const exact = paras.find((p) => p.text.includes(nq));
  if (exact) return exact.start;
  let best = null, bestScore = 0;
  for (const p of paras) for (const s of p.sentences) { const sc = dice(nq, s); if (sc > bestScore) { bestScore = sc; best = p.start; } }
  return bestScore >= 0.9 ? best : null;
};
const digest = {
  tldr: String(d.tldr).trim(),
  key_points: d.key_points.map((k) => ({ text: String(k.text).trim(), detail: String(k.detail || '').trim(), start: clamp(k.start) })),
  structure,
  quotes: d.quotes.map((q) => { const found = quoteParagraph(q.text); return { text: String(q.text).trim(), translation: q.translation ? String(q.translation) : null, start: found === null ? clamp(q.start) : found, speaker: null }; }),
};
const usage = { in: (S.map_usage.in || 0) + (r.usage.in || 0), out: (S.map_usage.out || 0) + (r.usage.out || 0) };
const reduceModel = r.model || S.meta.providers.llm_model_reduce;
const model = S.map_model === reduceModel ? reduceModel : `map: ${S.map_model}, reduce: ${reduceModel}`;
const reduceActual = r.model_actual || null;
const modelActual = S.map_model_actual === reduceActual ? reduceActual : `map: ${S.map_model_actual}, reduce: ${reduceActual}`;
const cost = round4((S.map_cost || 0) + llmCost(S.pricing, reduceModel, r.usage));
S.meta.tokens = { in: S.meta.tokens.in + usage.in, out: S.meta.tokens.out + usage.out };
S.digest = digest;
// Style-rule violations left after the retry (section 9): kept in jobs.meta, the job goes on.
if (Array.isArray(r.warnings) && r.warnings.length) S.meta.quality_warnings = [...(S.meta.quality_warnings || []), ...r.warnings.map((w) => ({ stage: 'digest', message: w }))];
S.stages = setStage(S.stages, 'digest', { status: 'done', progress: { done: S.map_notes.length + 1, total: S.map_notes.length + 1 } });
S.meta.stages.push({ name: 'digest', status: 'done', ms: Date.now() - S.t_digest, cost_usd: cost, model, model_actual: modelActual, tokens: usage, map_tokens: S.map_usage, reduce_tokens: r.usage, retries: (S.map_retries || 0) + ((r.attempts || 1) - 1), dropped_quotes: d._dropped_quotes || [] });
delete S.system; delete S.user; delete S.context;
return [{ json: withDb(S) }];
"""

EXTRAS_START_JS = JS_HELPERS + r"""
const S = $input.first().json;
S.t_extras = Date.now();
if (!S.extras_blocks || S.extras_blocks.length === 0) { S.extras = {}; return [{ json: withDb(S) }]; }
S.stages = setStage(S.stages, 'extras', { status: 'running', progress: { done: 0, total: S.extras_blocks.length } });
return [{ json: withDb(S) }];
"""

EXTRAS_ITEMS_JS = JS_HELPERS + r"""
const S = $('Extras start').first().json;
return (S.extras_blocks || []).map((name, i) => ({ json: { block: name, index: i, total: S.extras_blocks.length } }));
"""

EXTRAS_REQUEST_JS = JS_HELPERS + r"""
// One llm-call per block: shared input = digest structure + cleaned transcript.
const S = $('Extras start').first().json;
const c = $input.first().json;
const tpl = (S.extras_prompts || {})[c.block];
if (!tpl) return [{ json: { system: '', user: '', kind: c.block, context: {}, label: `extras ${c.block}`, missing_prompt: true } }];
const system = fill(tpl, { SOURCE_LANGUAGE: S.lang, OUTPUT_LANGUAGE: S.out_lang, PRESET: S.preset, TITLE: S.title, DURATION_SEC: S.duration });
const structure = (S.digest.structure || []).map((p) => `[${fmtStart(p.start)}–${fmtStart(p.end)}] ${p.title}`).join('\n');
const transcript = S.clean.map((p) => `[${fmtStart(p.start)}] ${p.text}`).join('\n\n');
return [{ json: { system, user: `STRUCTURE\n${structure}\n\nTRANSCRIPT\n${transcript}`, kind: c.block, context: { duration_sec: S.duration, output_language: S.out_lang }, label: `extras ${c.block}` } }];
"""

EXTRAS_BLOCK_DONE_JS = JS_HELPERS + r"""
// A failed block is dropped from the result and noted in meta; the job goes on.
const c = $('Loop extras').first().json;
const S = $('Extras start').first().json;
const r = $input.first().json;
const ok = !!(r && r.ok && r.data && r.data[c.block] !== undefined);
const done = $runIndex + 1;
const stages = setStage(S.stages, 'extras', { status: 'running', progress: { done, total: c.total } });
return [{ json: { block: c.block, index: c.index, ok, warnings: (r && r.warnings) || [], data: ok ? r.data[c.block] : null, error: ok ? null : (r && r.auth ? `provider_auth: ${r.error}` : ((r && (r.error || r.message)) || 'llm-call returned no data')), usage: (r && r.usage) || { in: 0, out: 0 }, model: (r && r.model) || null, model_actual: (r && r.model_actual) || null, attempts: (r && r.attempts) || 1, retry_error: (r && r.retry_error) || null, ms: (r && r.ms) || 0, job_id: S.job.id, p_stages: JSON.stringify(stages) , events: (r && r.events) || [] } }];
"""

EXTRAS_DONE_JS = JS_HELPERS + r"""
// Assemble result.extras (schema shapes only) and the extras stage entry with per-block accounting.
const S = $('Extras start').first().json;
const items = $input.all().map((i) => i.json).filter((i) => i && i.block).sort((a, b) => a.index - b.index);
S.events = [
  ...retryEvents(items, 'extras', (i) => `extras ${i.block}`),
  ...items.flatMap((i) => i.events || []),
  ...items.filter((i) => !i.ok).map((i) => ({ type: 'extras_block_skipped', level: 'warn', stage: 'extras', model: i.model || null, body: `${i.block}: ${i.error || ''}` })),
  ...items.filter((i) => !i.ok && String(i.error || '').startsWith('provider_auth')).map((i) => ({ type: 'provider_auth', level: 'error', stage: 'extras', provider: S.meta.providers.llm, model: i.model || null, body: `${i.block}: ${i.error}` })),
];
const dur = S.duration;
const clamp = (x) => Math.min(Math.max(Number(x) || 0, 0), dur);
const str = (x) => (x === null || x === undefined) ? null : String(x);
// Timestamps come from the transcript: a start within 1 s of a paragraph start is that paragraph
// (the prompt prints one decimal); critique claims are located by their content words instead,
// the model's start is kept only when no paragraph matches well enough.
const pStarts = S.clean.map((p) => p.start);
const snap = (x) => { const v = clamp(x); if (!pStarts.length) return v; const n = pStarts.reduce((b, s) => (Math.abs(s - v) < Math.abs(b - v) ? s : b), pStarts[0]); return Math.abs(n - v) <= 1.0 ? n : v; };
const tokens = (s) => String(s).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').split(' ').filter((w) => w.length >= 4);
const paraWords = S.clean.map((p) => ({ start: p.start, words: new Set(tokens(p.text)) }));
const claimParagraph = (claim, fallbackStart) => {
  const cw = [...new Set(tokens(claim))];
  if (cw.length < 3) return snap(fallbackStart);
  let best = null, bestScore = 0;
  for (const p of paraWords) { let n = 0; for (const w of cw) if (p.words.has(w)) n++; const sc = n / cw.length; if (sc > bestScore) { bestScore = sc; best = p.start; } }
  return bestScore >= 0.5 ? best : snap(fallbackStart);
};
const shape = {
  glossary: (v) => v.map((g) => ({ term: String(g.term).trim(), definition: String(g.definition).trim(), start: snap(g.start) })),
  decisions: (v) => v.map((x) => ({ text: String(x.text).trim(), start: snap(x.start) })),
  questions: (v) => v.map((x) => ({ text: String(x.text).trim(), start: snap(x.start) })),
  action_items: (v) => v.map((a) => ({ text: String(a.text).trim(), owner: str(a.owner), due: str(a.due), start: snap(a.start) })),
  self_check: (v) => v.map((q) => ({ question: String(q.question).trim(), answer: String(q.answer).trim(), start: snap(q.start) })),
  critique: (v) => ({ strong: (v.strong || []).map(String), weak: (v.weak || []).map((w) => ({ claim: String(w.claim).trim(), issue: String(w.issue).trim(), start: claimParagraph(w.claim, w.start) })), missing: (v.missing || []).map(String) }),
};
const extras = {};
const blocks = {};
let cost = 0;
const usage = { in: 0, out: 0 };
for (const it of items) {
  const c = it.model ? llmCost(S.pricing, it.model, it.usage) : 0;
  cost += c; usage.in += it.usage.in || 0; usage.out += it.usage.out || 0;
  blocks[it.block] = { status: it.ok ? 'done' : 'failed', model: it.model, model_actual: it.model_actual || null, tokens: it.usage, cost_usd: round4(c), attempts: it.attempts, ms: it.ms, error: it.ok ? undefined : it.error };
  if (it.ok && shape[it.block]) extras[it.block] = shape[it.block](it.data);
  if (Array.isArray(it.warnings) && it.warnings.length) S.meta.quality_warnings = [...(S.meta.quality_warnings || []), ...it.warnings.map((w) => ({ stage: 'extras', block: it.block, message: w }))];
}
const okCount = items.filter((i) => i.ok).length;
const status = items.length === 0 ? 'skipped' : okCount > 0 ? 'done' : 'failed';
S.extras = extras;
S.meta.tokens = { in: S.meta.tokens.in + usage.in, out: S.meta.tokens.out + usage.out };
S.stages = setStage(S.stages, 'extras', { status, progress: { done: items.length, total: items.length } });
const model = [...new Set(items.filter((i) => i.model).map((i) => `${i.block}: ${i.model}`))].join(', ');
const modelActual = [...new Set(items.filter((i) => i.model_actual).map((i) => `${i.block}: ${i.model_actual}`))].join(', ') || null;
S.meta.stages.push({ name: 'extras', status, ms: Date.now() - S.t_extras, cost_usd: round4(cost), model, model_actual: modelActual, tokens: usage, blocks, retries: items.reduce((a, i) => a + ((i.attempts || 1) - 1), 0) });
return [{ json: withDb(S) }];
"""

RESULT_SCHEMA_JSON = json.dumps(json.loads((Path(__file__).resolve().parents[2] / "schemas" / "result.schema.json").read_text(encoding="utf-8")), ensure_ascii=False, separators=(",", ":"))
# Result check before done (decision 2026-09-17): the schema (embedded at build time, the same file the tests use)
# plus rules 2 and 7 of docs/result-schema.md section 9, written for the Code sandbox where ajv cannot run.
# Soft: violations become quality_warnings and one schema_violation event; the job still finishes. Two runs in a row
# (VK, Rutube) had violations that only the manual validate_result.py found – in production nobody would have.
RESULT_CHECK_JS = r"""
const RESULT_SCHEMA = __SCHEMA__;
function checkResult(result) {
  const errors = [];
  const push = (m) => { if (errors.length < 20) errors.push(m); };
  const deref = (s) => (s && s.$ref ? RESULT_SCHEMA.$defs[s.$ref.split('/').pop()] : s);
  const typeOf = (v) => (v === null ? 'null' : Array.isArray(v) ? 'array' : Number.isInteger(v) ? 'integer' : typeof v);
  const typeOk = (t, v) => t === typeOf(v) || (t === 'number' && typeOf(v) === 'integer');
  const validate = (schema, v, path) => {
    schema = deref(schema);
    if (!schema) return;
    if (schema.oneOf) { if (!schema.oneOf.some((alt) => { const e = errors.length; validate(alt, v, path); const ok = errors.length === e; errors.length = e; return ok; })) push(`${path}: matches none of the allowed shapes`); return; }
    if (schema.const !== undefined && v !== schema.const) return push(`${path}: must be ${JSON.stringify(schema.const)}`);
    if (schema.enum && !schema.enum.includes(v)) return push(`${path}: ${JSON.stringify(v)} not in ${schema.enum.join('|')}`);
    if (schema.type) { const types = Array.isArray(schema.type) ? schema.type : [schema.type]; if (!types.some((t) => typeOk(t, v))) return push(`${path}: expected ${types.join('|')}, got ${typeOf(v)}`); }
    if (typeof v === 'number') { if (schema.minimum !== undefined && v < schema.minimum) push(`${path}: ${v} < ${schema.minimum}`); if (schema.maximum !== undefined && v > schema.maximum) push(`${path}: ${v} > ${schema.maximum}`); if (schema.exclusiveMinimum !== undefined && v <= schema.exclusiveMinimum) push(`${path}: ${v} must be > ${schema.exclusiveMinimum}`); }
    if (typeof v === 'string') { if (schema.minLength !== undefined && v.length < schema.minLength) push(`${path}: empty string`); if (schema.pattern && !new RegExp(schema.pattern).test(v)) push(`${path}: does not match ${schema.pattern}`); }
    if (Array.isArray(v)) { if (schema.minItems !== undefined && v.length < schema.minItems) push(`${path}: ${v.length} items, at least ${schema.minItems}`); if (schema.maxItems !== undefined && v.length > schema.maxItems) push(`${path}: ${v.length} items, at most ${schema.maxItems}`); if (schema.uniqueItems && new Set(v.map((x) => JSON.stringify(x))).size !== v.length) push(`${path}: duplicate items`); if (schema.items) v.forEach((x, i) => validate(schema.items, x, `${path}[${i}]`)); }
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const k of schema.required || []) if (!(k in v)) push(`${path}.${k}: missing`);
      for (const [k, x] of Object.entries(v)) { const sub = (schema.properties || {})[k]; if (sub) validate(sub, x, `${path}.${k}`); else if (schema.additionalProperties === false) push(`${path}.${k}: unexpected field`); }
    }
  };
  validate(RESULT_SCHEMA, result, 'result');
  // rule 2: every start/end within the video (segments may overrun by a second, subtitle cues do)
  const dur = Number(((result || {}).source || {}).duration_sec || 0);
  const walk = (node, path) => { if (Array.isArray(node)) node.forEach((x, i) => walk(x, `${path}[${i}]`)); else if (node && typeof node === 'object') for (const [k, x] of Object.entries(node)) { if ((k === 'start' || k === 'end') && typeof x === 'number' && !path.startsWith('result.transcript') && x > dur) push(`rule 2: ${path}.${k}=${x} exceeds duration_sec=${dur}`); walk(x, `${path}.${k}`); } };
  if (dur > 0 && result) { walk({ digest: result.digest, extras: result.extras }, 'result'); for (const [i, s] of ((result.transcript || {}).segments || []).entries()) if (s.end > dur + 1 || s.start > s.end) push(`rule 2: bad segment [${i}] ${s.start}-${s.end}`); }
  // rule 7: structure is a contiguous partition of 0..duration
  const st = (((result || {}).digest || {}).structure) || [];
  if (dur > 0 && st.length) { if (st[0].start !== 0) push(`rule 7: structure[0].start=${st[0].start} must be 0`); if (Math.abs(st[st.length - 1].end - dur) > 1e-6) push(`rule 7: last structure end=${st[st.length - 1].end} must equal duration_sec=${dur}`); for (let i = 0; i < st.length; i++) { if (st[i].start >= st[i].end) push(`rule 7: structure[${i}] start >= end`); if (i + 1 < st.length && Math.abs(st[i].end - st[i + 1].start) > 1e-6) push(`rule 7: structure[${i}].end=${st[i].end} != structure[${i + 1}].start=${st[i + 1].start}`); } }
  return errors;
}
""".replace("__SCHEMA__", RESULT_SCHEMA_JSON)

BUILD_RESULT_JS = JS_HELPERS + RESULT_CHECK_JS + r"""
// Assemble jobs.result per docs/result-schema.md and close the job.
const S = $input.first().json;
const job = S.job;
const finished = new Date().toISOString();
const order = ['probe', 'download', 'transcribe', 'clean', 'digest', 'extras'];
const byName = Object.fromEntries(S.meta.stages.map((s) => [s.name, s]));
// jobs.meta keeps the rich entries (tokens, retries, minutes, notes); result.meta.stages is the schema view.
const richStages = order.map((name) => byName[name] || { name, status: ((S.stages.find((s) => s.name === name) || {}).status) || 'skipped', ms: 0, cost_usd: 0 });
const stages = richStages.map((rec) => {
  const entry = { name: rec.name, status: rec.status, ms: rec.ms || 0, cost_usd: rec.cost_usd || 0 };
  if (rec.provider) entry.provider = rec.provider;
  if (rec.model) entry.model = rec.model;
  if (rec.model_actual) entry.model_actual = rec.model_actual;
  return entry;
});
const total = round4(stages.reduce((a, s) => a + (s.cost_usd || 0), 0));
const src = job.source || {};
const source = {
  type: src.type, url: src.url || null, platform: src.platform, title: src.title, duration_sec: Number(src.duration_sec), thumbnail_url: src.thumbnail_url || null,
  language: S.lang, language_detected_by: S.language_detected_by, language_confidence: S.language_confidence, playback: src.playback,
};
const result = {
  schema_version: '1.0', job_id: job.id, source, preset: job.preset, options: job.options || [], output_language: S.out_lang,
  transcript: { origin: S.origin, segments: S.segments, clean: S.clean, stats: { words: S.clean.reduce((a, p) => a + wordsOf(p.text), 0), segments: S.segments.length, speakers: null } /* not measured: whisper separates nobody, Deepgram numbers speakers per chunk */ },
  digest: S.digest, extras: S.extras || {},
  meta: { created_at: new Date(job.created_at).toISOString(), finished_at: finished, stages, total_cost_usd: total, tokens: S.meta.tokens },
  notices: [],
};
// What changes what the reader reads (docs/result-schema.md section 2, notices): timecodes only, at most 40 each.
const cn = S.clean_notices || {};
if ((cn.lost_starts || []).length) result.notices.push({ kind: 'transcript_shortened', places: cn.lost_starts.length, starts: cn.lost_starts.slice(0, 40) });
if ((cn.fallback_starts || []).length) result.notices.push({ kind: 'clean_fallback', places: cn.fallback_starts.length, starts: cn.fallback_starts.slice(0, 40) });
const meta = { ...S.meta, stages: richStages, finished_at: finished, total_cost_usd: total };
// Soft result check: the document still ships, the violations go to quality_warnings and the events table.
const violations = checkResult(result);
const events = violations.length ? [{ type: 'schema_violation', level: 'warn', stage: 'finalize', body: `${violations.length} violation(s): ${violations.join('; ')}` }] : [];
if (violations.length) meta.quality_warnings = [...(meta.quality_warnings || []), ...violations.map((v) => ({ stage: 'finalize', message: `schema: ${v}` }))];
const retentionDays = Number($env.RESULT_RETENTION_DAYS || 30);
const until = new Date(Date.now() + retentionDays * 86400000);
const untilText = until.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).replace(/\.$/, ''); // '6 октября 2026 г.' -> no trailing dot
const publicUrl = String($env.PUBLIC_URL || '').replace(/\/$/, '');
const link = `${publicUrl}/jobs/${job.id}`;
const email = job.email && job.consent_152fz !== false ? job.email : null;
const subject = `Выжимка готова: ${source.title}`;
const text = [`Выжимка готова: ${source.title}`, '', `Открыть: ${link}`, '', S.digest.tldr, '', `Тезисов: ${S.digest.key_points.length}, частей: ${S.digest.structure.length}.`, `Результат хранится ${retentionDays} дней, до ${untilText}.`].join('\n');
const esc = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const html = `<p><strong>Выжимка готова: ${esc(source.title)}</strong></p><p><a href="${link}">${link}</a></p><p>${esc(S.digest.tldr)}</p><p>Тезисов: ${S.digest.key_points.length}, частей: ${S.digest.structure.length}.</p><p>Результат хранится ${retentionDays} дней, до ${untilText}.</p>`;
return [{ json: { job_id: job.id, source_id: S.source_id, total_cost: total, p_result: JSON.stringify(result), p_meta: JSON.stringify(meta), p_stages: JSON.stringify(S.stages), email, mail_subject: subject, mail_text: text, mail_html: html, events } }];
"""

FAIL_JOB_JS = JS_HELPERS + r"""
// Any stage failure lands here: mark the stage failed, store error {stage, code, message}.
const S = $input.first().json;
const f = S.fail || { stage: 'pipeline', code: 'internal', message: 'unknown failure' };
const stages = setStage(S.stages || [], f.stage, { status: 'failed' });
const meta = S.meta || {};
// A failure after a paid call brings its own record (transcribe after the empty-result guard): cost stays counted.
meta.stages = [...(meta.stages || []), f.stage_record || { name: f.stage, status: 'failed', ms: 0, cost_usd: 0, error: f.code }];
meta.finished_at = new Date().toISOString();
// jobs.error.message is public (GET /api/jobs/{id}): a neutral sentence per code, never a node name, a path, an
// address or a provider's text (2026-09-21). The detail travels as a job_failed event, masked as everywhere.
const NEUTRAL = { stt_failed: 'speech recognition failed', llm_failed: 'text processing failed', provider_auth: 'the provider refused our request', download_failed: 'the source could not be fetched',
  source_busy: 'the source is being processed by another request, try again later', internal_error: 'internal error on our side', timeout: 'processing took too long',
  bot_check: 'the platform asked for a verification', private_or_removed: 'the video is private or removed', unsupported_url: 'this link is not supported', source_gone: 'the uploaded file is no longer available' };
const neutral = NEUTRAL[f.code] || 'processing failed';
const events = [...(f.events || []), { type: 'job_failed', level: 'error', stage: f.stage, body: `${f.code}: ${maskSecrets(String(f.message || '')).slice(0, 280)}` },
  ...(f.code === 'source_busy' ? [{ type: 'source_busy', level: 'warn', stage: f.stage, body: f.message }] : []), ...(f.code === 'provider_auth' && !S.prestart_auth
  ? [{ type: 'provider_auth', level: 'error', stage: f.stage, provider: f.stage === 'transcribe' ? (meta.providers || {}).stt : (meta.providers || {}).llm, body: f.message }]
  : [])];
return [{ json: { job_id: (S.job || {}).id || S.job_id, p_error: JSON.stringify({ stage: f.stage, code: f.code, message: neutral }), p_stages: JSON.stringify(stages), p_meta: JSON.stringify(meta), events } }];
"""

def read_text(name, path, x, y):
    # A selector that matches no file yields zero items, not an error, and the branch would end with the job in
    # processing (audit 2026-09-20): alwaysOutputData hands an empty item on, the text node then fails softly into an
    # item without `data`, and Init refuses the job with a message that names the missing file.
    return [node(name, "n8n-nodes-base.readWriteFile", 1, {"operation": "read", "fileSelector": path, "options": {}}, x, y, alwaysOutputData=True, onError="continueRegularOutput"),
            node("Text " + name.split()[-1], "n8n-nodes-base.extractFromFile", 1, {"operation": "text", "binaryPropertyName": "data", "options": {}}, x + 160, y, alwaysOutputData=True, onError="continueRegularOutput")]

def pg_side(name, x, y, sql, params):
    return pg(name, sql, params, x, y)

STAGES_SQL = "update jobs set stages = $2::jsonb, meta = $3::jsonb, updated_at = now() where id = $1"
# Array expressions everywhere: a plain comma list is split on commas of the resolved values (see log-events).
STAGES_P = "{{ [$json.job_id, $json.p_stages, $json.p_meta] }}"
PROGRESS_SQL = "update jobs set stages = $2::jsonb, updated_at = now() where id = $1"
PROGRESS_P = "{{ [$json.job_id, $json.p_stages] }}"

# (log_events is defined above, next to the jobs-api nodes that use it)

def key_check_http(name, url_expr, cred_name, x, y, response_format="json"):
    # GET through the stage's own credential; neverError so 401/403 reach the Code node; onError for network failures.
    # Deepgram answers 401 with plain text, so its node autodetects: with "json" the node would raise its own
    # parse error, the Code node would read no status and let the job go on.
    return node(name, "n8n-nodes-base.httpRequest", 4.5, {
        "method": "GET", "url": "=" + url_expr, "authentication": "predefinedCredentialType", "nodeCredentialType": "httpHeaderAuth",
        "options": {"timeout": 10000, "response": {"response": {"fullResponse": True, "neverError": True, "responseFormat": response_format}}},
    }, x, y, credentials={"httpHeaderAuth": {"name": cred_name}}, onError="continueRegularOutput", alwaysOutputData=True)

def media_http(name, method, url_expr, x, y, json_body=None, file_response=False, timeout=1800000, on_error=False):
    p = {"method": method, "url": "=" + url_expr, "authentication": "predefinedCredentialType", "nodeCredentialType": "httpHeaderAuth", "options": {"timeout": timeout}}
    if json_body is not None:
        p.update({"sendBody": True, "specifyBody": "json", "jsonBody": "=" + json_body})
    if file_response:
        p["options"]["response"] = {"response": {"responseFormat": "file", "outputPropertyName": "data"}}
    else:
        p["options"]["response"] = {"response": {"fullResponse": True, "neverError": True, "responseFormat": "json"}}
    extra = {"onError": "continueRegularOutput"} if (file_response or on_error) else {}
    return node(name, "n8n-nodes-base.httpRequest", 4.5, p, x, y, credentials=MEDIA_CRED, **extra)

def call_llm(name, x, y):
    return node(name, "n8n-nodes-base.executeWorkflow", 1.3, {
        "workflowId": {"__rl": True, "value": "", "mode": "list", "cachedResultName": "llm-call"},
        "workflowInputs": {"mappingMode": "defineBelow", "value": {"system": "={{ $json.system }}", "user": "={{ $json.user }}", "kind": "={{ $json.kind }}", "context": "={{ $json.context }}", "label": "={{ $json.label }}"},
                           "matchingColumns": [], "schema": [
                               {"id": "system", "displayName": "system", "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "string", "removed": False},
                               {"id": "user", "displayName": "user", "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "string", "removed": False},
                               {"id": "kind", "displayName": "kind", "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "string", "removed": False},
                               {"id": "context", "displayName": "context", "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "object", "removed": False},
                               {"id": "label", "displayName": "label", "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "string", "removed": False}],
                           "attemptToConvertTypes": False, "convertFieldsToString": False},
        "options": {"waitForSubWorkflow": True}}, x, y, onError="continueRegularOutput")

def loop(name, x, y):
    return node(name, "n8n-nodes-base.splitInBatches", 3, {"batchSize": 1, "options": {}}, x, y)

STT_NODE = node("STT request", "n8n-nodes-base.httpRequest", 4.5, {
    "method": "POST", "url": "={{ $('Transcribe start').first().json.stt_base_url }}/audio/transcriptions",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "httpHeaderAuth",
    "sendBody": True, "contentType": "multipart-form-data",
    "bodyParameters": {"parameters": [
        {"parameterType": "formBinaryData", "name": "file", "inputDataFieldName": "data"},
        {"name": "model", "value": "={{ $('Transcribe start').first().json.stt_model }}"},
        {"name": "response_format", "value": "verbose_json"},
        {"name": "timestamp_granularities[]", "value": "segment"},
        {"name": "language", "value": "={{ $('Loop chunks').first().json.lang }}"}]},
    "options": {"timeout": 600000, "response": {"response": {"fullResponse": True, "neverError": True, "responseFormat": "json"}}},
}, 1560, 500, credentials={"httpHeaderAuth": {"name": "STT API"}}, onError="continueRegularOutput")

# Deepgram: the chunk goes as the raw request body, options as query parameters, "Authorization: Token" from its
# own credential. smart_format stays off: on Russian it turns numerals into digits. Response format autodetect,
# as the 401 body is plain text.
DEEPGRAM_NODE = node("Deepgram request", "n8n-nodes-base.httpRequest", 4.5, {
    "method": "POST", "url": "https://api.deepgram.com/v1/listen",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "httpHeaderAuth",
    "sendQuery": True, "queryParameters": {"parameters": [
        {"name": "model", "value": "={{ $('Transcribe start').first().json.stt_model }}"},
        {"name": "language", "value": "={{ $('Loop chunks').first().json.lang }}"},
        {"name": "diarize", "value": "true"},
        {"name": "punctuate", "value": "true"},
        {"name": "smart_format", "value": "false"},
        {"name": "utterances", "value": "true"}]},
    "sendBody": True, "contentType": "binaryData", "inputDataFieldName": "data",
    "options": {"timeout": 600000, "response": {"response": {"fullResponse": True, "neverError": True, "responseFormat": "autodetect"}}},
}, 1560, 900, credentials={"httpHeaderAuth": {"name": "Deepgram API"}}, onError="continueRegularOutput")

# Money guard (2026-09-20, found with the stub: after chunk 1 failed for good, chunks 2..n were still sent and
# would have been paid for). Once a chunk has failed, the remaining ones skip the download and the request and
# go straight to Chunk transcribed as failed copies; Transcribe done then fails the job on the first failure.
CHUNK_PENDING_JS = JS_HELPERS + r"""
const chunk = $('Loop chunks').first().json;
let earlier = null;
try { for (let i = 0; i < $runIndex; i++) for (const it of $('Chunk transcribed').all(0, i)) if (it.json && it.json.failed && !earlier) earlier = it.json; } catch (e) { /* no earlier run */ }
// The copy carries the failure's stage, code and message, not its events: those belong to the chunk that failed.
if (earlier) return [{ json: { ...chunk, failed: true, skipped: true, fail: { stage: earlier.fail.stage, code: earlier.fail.code, message: earlier.fail.message }, job_id: earlier.job_id, p_stages: earlier.p_stages } }];
return [{ json: chunk }];
"""

# Transport loop of the STT call (2026-09-20): the verdict on the answer of either provider node; a retry goes
# through Wait back to Media chunk (a plain artifact GET, no lock and no download – see media-service README) and
# from there to the same request; the attempt number comes from this node's previous run for the same chunk.
STT_TRANSPORT_JS = JS_HELPERS + "\n" + TRANSPORT_JS + r"""
const chunk = $('Loop chunks').first().json;
const S = $('Transcribe start').first().json;
const resp = $input.first().json;
// The previous run of this node, when it belongs to the same chunk and was a retry, carries the attempt count and
// the events so far. If that lookup ever fails, the answer is "no retry": an unknown attempt number must not loop.
let attempt = 1, events = [], lookupFailed = false;
try {
  if ($runIndex > 0) {
    const prev = (($('STT transport check').all(0, $runIndex - 1) || [])[0] || {}).json || {};
    if (prev.transport && prev.transport.retry && prev.index === chunk.index) { attempt = prev.transport.attempt + 1; events = prev.transport.events || []; }
  }
} catch (e) { lookupFailed = true; }
const tv = transportVerdict(resp, attempt);
const label = `transcribe chunk ${chunk.index + 1}/${chunk.total}`;
if (tv.retry && !lookupFailed) {
  const ev = transportEvent('transcribe', S.meta.providers.stt, label, tv);
  return [{ json: { ...chunk, transport: { retry: true, attempt, wait_sec: tv.wait_sec, events: [...events, ev] } } }];
}
return [{ json: { ...resp, transport_events: events, transport_auth: tv.auth, transport_lookup_failed: lookupFailed } }];
"""

pipe_nodes = [
    node("When called by jobs-api", "n8n-nodes-base.executeWorkflowTrigger", 1.2, {"inputSource": "workflowInputs", "workflowInputs": {"values": [{"name": "job_id", "type": "string"}]}}, 0, 0),
    pg("Load job", "select id, status, stages, meta, options, preset, output_language, source, source_id, source_language, email, created_at from jobs where id = $1", "{{ $json.job_id }}", 200, 0),
    *read_text("Read prompt clean", "/data/prompts/clean.md", 400, 0),
    *read_text("Read prompt map", "/data/prompts/digest-map.md", 720, 0),
    *read_text("Read prompt reduce", "/data/prompts/digest-reduce.md", 1040, 0),
    node("Read pricing", "n8n-nodes-base.readWriteFile", 1, {"operation": "read", "fileSelector": "/data/pricing.json", "options": {}}, 1360, 0, alwaysOutputData=True, onError="continueRegularOutput"),
    node("Parse pricing", "n8n-nodes-base.extractFromFile", 1, {"operation": "fromJson", "binaryPropertyName": "data", "options": {}}, 1520, 0, alwaysOutputData=True, onError="continueRegularOutput"),
    node("Read extras prompts", "n8n-nodes-base.readWriteFile", 1, {"operation": "read", "fileSelector": "/data/prompts/extras/*.md", "options": {}}, 1360, 160, alwaysOutputData=True, onError="continueRegularOutput"),
    node("Text extras", "n8n-nodes-base.extractFromFile", 1, {"operation": "text", "binaryPropertyName": "data", "options": {}}, 1520, 160, alwaysOutputData=True, onError="continueRegularOutput"),
    code("Collect extras prompts", COLLECT_EXTRAS_JS, 1600, 160),
    code("Init", INIT_JS, 1700, 0),
    if_bool("Check LLM key?", "{{ !!$('Init').first().json.auth_checks.llm }}", 1700, -300),
    key_check_http("Check LLM key", "{{ $('Init').first().json.auth_checks.llm }}", "LLM API", 1900, -400),
    if_bool("Check STT key?", "{{ !!$('Init').first().json.auth_checks.stt }}", 2100, -300),
    if_bool("STT via Deepgram?", "{{ !!$('Init').first().json.auth_checks.stt_deepgram }}", 2300, -500),
    key_check_http("Check STT key", "{{ $('Init').first().json.auth_checks.stt }}", "STT API", 2300, -400),
    key_check_http("Check Deepgram key", "{{ $('Init').first().json.auth_checks.stt }}", "Deepgram API", 2300, -600, response_format="autodetect"),
    code("Auth check", AUTH_CHECK_JS, 2500, -300),
    log_events("Log events auth", 2700, -420),
    if_bool("Keys ok?", "{{ !$json.failed }}", 2900, -300),
    log_events("Log events clean", 4300, -320),
    log_events("Log events digest", 5900, -520),
    log_events("Log events extras", 7300, -920),
    log_events("Log events fail", 6300, 760),
    pg_side("Mark processing", 1900, -160, "update jobs set status = 'processing', stages = $2::jsonb, meta = $3::jsonb, updated_at = now() where id = $1", STAGES_P),
    # download
    code("Download start", DOWNLOAD_START_JS, 1900, 0),
    pg_side("Stage download running", 2100, -160, STAGES_SQL, STAGES_P),
    media_http("Media download", "POST", "{{ $env.MEDIA_URL }}/download", 2300, 0, json_body="{{ JSON.stringify($('Download start').first().json.download_body) }}"),
    code("Download done", DOWNLOAD_DONE_JS, 2300, 0),
    if_bool("Download ok?", "{{ !$json.failed }}", 2500, 0),
    if_bool("Use subtitles?", "{{ $json.use_subs }}", 2700, 0),
    # subtitles branch
    media_http("Media subtitles", "GET", "{{ $env.MEDIA_URL }}/artifacts/{{ $json.source_id }}/subs.{{ $json.lang }}.json", 2900, -200),
    code("Subtitles segments", SUBS_SEGMENTS_JS, 3100, -200),
    # STT branch
    code("Transcribe start", TRANSCRIBE_START_JS, 700, 500),
    pg_side("Stage transcribe running", 900, 340, STAGES_SQL, STAGES_P),
    media_http("Media split", "POST", "{{ $env.MEDIA_URL }}/split", 1100, 500, json_body="{{ JSON.stringify($('Transcribe start').first().json.split_body) }}"),
    code("Chunks", CHUNKS_JS, 1100, 500),
    loop("Loop chunks", 1300, 500),
    media_http("Media chunk", "GET", "{{ $env.MEDIA_URL }}/artifacts/{{ $json.source_id }}/chunks/{{ String($json.index).padStart(3, '0') }}.mp3", 1560, 700, file_response=True),
    if_bool("Deepgram?", "{{ $('Transcribe start').first().json.stt_provider === 'deepgram' }}", 1400, 700),
    STT_NODE,
    DEEPGRAM_NODE,
    code("Chunk pending", CHUNK_PENDING_JS, 1400, 500),
    if_bool("Chunk skipped?", "{{ $json.skipped === true }}", 1400, 620),
    code("STT transport check", STT_TRANSPORT_JS, 1780, 900),
    if_bool("STT retry?", "{{ !!($json.transport && $json.transport.retry === true) }}", 2000, 900),
    wait_node("Wait STT", "{{ $json.transport.wait_sec }}", 1400, 900),
    code("Chunk transcribed", CHUNK_TRANSCRIBED_JS, 1780, 500),
    pg_side("Progress transcribe", 1780, 700, PROGRESS_SQL, PROGRESS_P),
    code("Restore chunk", "// Postgres replaced the item; put the chunk result back for the loop.\nreturn [{ json: $('Chunk transcribed').first().json }];", 1980, 700),
    code("Transcribe done", TRANSCRIBE_DONE_JS, 1560, 300),
    # join
    code("Segments ready", SEGMENTS_READY_JS, 3300, 0),
    if_bool("Transcript ok?", "{{ !$json.failed }}", 3500, 0),
    # clean
    code("Clean start", CLEAN_START_JS, 3700, 0),
    pg_side("Stage clean running", 3900, -160, STAGES_SQL, STAGES_P),
    code("Clean chunks", CLEAN_CHUNKS_JS, 3900, 0),
    loop("Loop clean", 4100, 0),
    code("Clean request", CLEAN_REQUEST_JS, 4300, 200),
    call_llm("LLM clean", 4500, 200),
    code("Clean chunk done", CLEAN_CHUNK_DONE_JS, 4700, 200),
    pg_side("Progress clean", 4900, 340, PROGRESS_SQL, PROGRESS_P),
    code("Restore clean", "return [{ json: $('Clean chunk done').first().json }];", 5100, 340),
    code("Clean done", CLEAN_DONE_JS, 4300, -200),
    if_bool("Clean ok?", "{{ !$json.failed }}", 4500, -200),
    # digest
    code("Digest start", DIGEST_START_JS, 4700, -200),
    pg_side("Stage digest running", 4900, -360, STAGES_SQL, STAGES_P),
    code("Map chunks", MAP_CHUNKS_JS, 4900, -200),
    loop("Loop map", 5100, -200),
    code("Map request", MAP_REQUEST_JS, 5300, 0),
    call_llm("LLM map", 5500, 0),
    code("Map chunk done", MAP_CHUNK_DONE_JS, 5700, 0),
    pg_side("Progress digest", 5900, 140, PROGRESS_SQL, PROGRESS_P),
    code("Restore map", "return [{ json: $('Map chunk done').first().json }];", 6100, 140),
    code("Reduce request", REDUCE_REQUEST_JS, 5300, -400),
    if_bool("Map ok?", "{{ !$json.failed }}", 5500, -400),
    call_llm("LLM reduce", 5700, -400),
    code("Digest done", DIGEST_DONE_JS, 5900, -400),
    if_bool("Digest ok?", "{{ !$json.failed }}", 6100, -400),
    # extras
    code("Extras start", EXTRAS_START_JS, 6300, -600),
    pg_side("Stage extras running", 6500, -760, STAGES_SQL, STAGES_P),
    if_bool("Extras ordered?", "{{ ($('Extras start').first().json.extras_blocks || []).length > 0 }}", 6700, -600),
    code("Extras items", EXTRAS_ITEMS_JS, 6900, -600),
    loop("Loop extras", 7100, -600),
    code("Extras request", EXTRAS_REQUEST_JS, 7300, -400),
    call_llm("LLM extras", 7500, -400),
    code("Extras block done", EXTRAS_BLOCK_DONE_JS, 7700, -400),
    pg_side("Progress extras", 7900, -260, PROGRESS_SQL, PROGRESS_P),
    code("Restore extras", "return [{ json: $('Extras block done').first().json }];", 8100, -260),
    code("Extras done", EXTRAS_DONE_JS, 7300, -800),
    code("Extras skipped", "// No blocks ordered: carry the state on.\nreturn [{ json: $('Extras start').first().json }];", 6900, -400),
    # finalize
    code("Build result", BUILD_RESULT_JS, 6300, -400),
    log_events("Log events finalize", 6400, -560),
    pg("Finish job", "update jobs set status = 'done', result = $2::jsonb, meta = $3::jsonb, stages = $4::jsonb, total_cost_usd = $5::numeric, finished_at = now(), updated_at = now() where id = $1 returning id",
       "{{ [$json.job_id, $json.p_result, $json.p_meta, $json.p_stages, $json.total_cost] }}", 6500, -400),
    media_http("Media cleanup", "DELETE", "{{ $env.MEDIA_URL }}/sources/{{ $('Build result').first().json.source_id }}?keep=playback", 6700, -400),
    if_bool("Email requested?", "{{ !!$('Build result').first().json.email }}", 6900, -400),
    node("Send email", "n8n-nodes-base.emailSend", 2.1, {
        "fromEmail": "={{ $env.SMTP_FROM }}", "toEmail": "={{ $('Build result').first().json.email }}",
        "subject": "={{ $('Build result').first().json.mail_subject }}", "emailFormat": "both",
        "text": "={{ $('Build result').first().json.mail_text }}", "html": "={{ $('Build result').first().json.mail_html }}",
        "options": {}}, 7100, -400, credentials={"smtp": {"name": "SMTP"}}, onError="continueRegularOutput"),
    pg("Mark email sent", "update jobs set email_sent_at = now(), updated_at = now() where id = $1 and $2 = 'ok'",
       "{{ [$('Build result').first().json.job_id, $json.error ? 'error' : 'ok'] }}", 7300, -400),
    # failure
    code("Fail job", FAIL_JOB_JS, 6300, 600),
    pg("Mark failed", "update jobs set status = 'failed', error = $2::jsonb, stages = $3::jsonb, meta = $4::jsonb, finished_at = now(), updated_at = now() where id = $1",
       "{{ [$json.job_id, $json.p_error, $json.p_stages, $json.p_meta] }}", 6500, 600),
]
pc = {}
w = lambda *a: wire(pc, *a)
w("When called by jobs-api", "Load job"); w("Load job", "Read prompt clean"); w("Read prompt clean", "Text clean"); w("Text clean", "Read prompt map"); w("Read prompt map", "Text map")
w("Text map", "Read prompt reduce"); w("Read prompt reduce", "Text reduce"); w("Text reduce", "Read pricing"); w("Read pricing", "Parse pricing"); w("Parse pricing", "Read extras prompts"); w("Read extras prompts", "Text extras"); w("Text extras", "Collect extras prompts"); w("Collect extras prompts", "Init")
w("Init", "Check LLM key?"); w("Check LLM key?", "Check LLM key", 0); w("Check LLM key?", "Check STT key?", 1); w("Check LLM key", "Check STT key?")
w("Check STT key?", "STT via Deepgram?", 0); w("Check STT key?", "Auth check", 1); w("STT via Deepgram?", "Check Deepgram key", 0); w("STT via Deepgram?", "Check STT key", 1); w("Check STT key", "Auth check"); w("Check Deepgram key", "Auth check")
w("Auth check", "Log events auth"); w("Log events auth", "Keys ok?"); w("Keys ok?", "Mark processing", 0); w("Keys ok?", "Fail job", 1); w("Mark processing", "Download start")
w("Download start", "Stage download running"); w("Stage download running", "Media download"); w("Media download", "Download done"); w("Download done", "Download ok?")
w("Download ok?", "Use subtitles?", 0); w("Download ok?", "Fail job", 1)
w("Use subtitles?", "Media subtitles", 0); w("Media subtitles", "Subtitles segments"); w("Subtitles segments", "Segments ready")
w("Use subtitles?", "Transcribe start", 1); w("Transcribe start", "Stage transcribe running"); w("Stage transcribe running", "Media split"); w("Media split", "Chunks"); w("Chunks", "Loop chunks")
w("Loop chunks", "Transcribe done", 0); w("Loop chunks", "Chunk pending", 1); w("Chunk pending", "Chunk skipped?"); w("Chunk skipped?", "Chunk transcribed", 0); w("Chunk skipped?", "Media chunk", 1); w("Media chunk", "Deepgram?"); w("Deepgram?", "Deepgram request", 0); w("Deepgram?", "STT request", 1); w("STT request", "STT transport check"); w("Deepgram request", "STT transport check")
w("STT transport check", "STT retry?"); w("STT retry?", "Wait STT", 0); w("Wait STT", "Media chunk"); w("STT retry?", "Chunk transcribed", 1)
w("Chunk transcribed", "Progress transcribe"); w("Progress transcribe", "Restore chunk"); w("Restore chunk", "Loop chunks"); w("Transcribe done", "Segments ready")
w("Segments ready", "Transcript ok?"); w("Transcript ok?", "Clean start", 0); w("Transcript ok?", "Fail job", 1)
w("Clean start", "Stage clean running"); w("Stage clean running", "Clean chunks"); w("Clean chunks", "Loop clean")
w("Loop clean", "Clean done", 0); w("Loop clean", "Clean request", 1); w("Clean request", "LLM clean"); w("LLM clean", "Clean chunk done")
w("Clean chunk done", "Progress clean"); w("Progress clean", "Restore clean"); w("Restore clean", "Loop clean"); w("Clean done", "Log events clean"); w("Log events clean", "Clean ok?"); w("Clean ok?", "Digest start", 0); w("Clean ok?", "Fail job", 1)
w("Digest start", "Stage digest running"); w("Stage digest running", "Map chunks"); w("Map chunks", "Loop map")
w("Loop map", "Reduce request", 0); w("Loop map", "Map request", 1); w("Map request", "LLM map"); w("LLM map", "Map chunk done")
w("Map chunk done", "Progress digest"); w("Progress digest", "Restore map"); w("Restore map", "Loop map")
w("Reduce request", "Map ok?"); w("Map ok?", "LLM reduce", 0); w("Map ok?", "Fail job", 1); w("LLM reduce", "Digest done"); w("Digest done", "Log events digest"); w("Log events digest", "Digest ok?")
w("Digest ok?", "Extras start", 0); w("Digest ok?", "Fail job", 1)
w("Extras start", "Stage extras running"); w("Stage extras running", "Extras ordered?"); w("Extras ordered?", "Extras items", 0); w("Extras ordered?", "Extras skipped", 1)
w("Extras items", "Loop extras"); w("Loop extras", "Extras done", 0); w("Loop extras", "Extras request", 1); w("Extras request", "LLM extras"); w("LLM extras", "Extras block done")
w("Extras block done", "Progress extras"); w("Progress extras", "Restore extras"); w("Restore extras", "Loop extras")
w("Extras done", "Log events extras"); w("Log events extras", "Build result"); w("Extras skipped", "Build result")
w("Build result", "Log events finalize"); w("Log events finalize", "Finish job"); w("Finish job", "Media cleanup"); w("Media cleanup", "Email requested?"); w("Email requested?", "Send email", 0); w("Send email", "Mark email sent")
w("Fail job", "Log events fail"); w("Log events fail", "Mark failed")
# binaryMode "separate" was written by the n8n editor on 2026-09-20 (a debug session on the instance); the public API
# neither sets nor removes the key, and the runtime treats a missing value exactly as "separate", so the generator
# carries it to keep the rebuild identical to the export.
pipeline = {"name": "pipeline", "nodes": pipe_nodes, "connections": pc, "settings": {"binaryMode": "separate", "executionOrder": "v1"}}
# ----------------------------------------------------------------- maintenance (schedule)
# Result retention (contract section 4): every hour, results of done jobs older than RESULT_RETENTION_DAYS are
# set to null (the row and its meta stay: costs, stages), the media source is deleted playback included, and
# one result_expired event per job goes to the events table. Until 2026-09-17 the variable existed and
# nothing read it: results lived forever while six places in the interface promised 30 days.
# Done and failed alike, once (meta.expired_at is the marker). What goes: result, the identifying source fields
# (title, url, thumbnail, playback), source_id (a content fingerprint for uploads), meta.quality_warnings and
# stages[].dropped_quotes (both carry transcript text), error.message (may quote a provider answer with text).
# What stays, for statistics only: duration, platform, type, languages, preset, options, cost, stages with
# statuses and models, tokens, estimates, dates, error stage and code (decision 2026-09-17).
EXPIRE_SQL = "select id, status, source_id, source, meta, error, finished_at from jobs where status in ('done', 'failed') and finished_at < now() - make_interval(days => $1) and (meta->>'expired_at') is null"
EXPIRED_ITEMS_JS = r"""// One item per expired job: reduced source/meta/error for the update, the original source_id for the media delete.
const days = Number($env.RESULT_RETENTION_DAYS || 30);
const now = new Date().toISOString();
return $input.all().map((i) => i.json).filter((r) => r && r.id).map((r) => {
  const src = r.source || {};
  const source = { type: src.type || null, platform: src.platform || null, duration_sec: src.duration_sec ?? null, language: src.language || null, title: null, url: null, thumbnail_url: null };
  const meta = { ...(r.meta || {}) };
  delete meta.quality_warnings;
  if (Array.isArray(meta.stages)) meta.stages = meta.stages.map((st) => { const { dropped_quotes, ...rest } = st || {}; return rest; });
  meta.expired_at = now;
  const error = r.error && typeof r.error === 'object' ? { stage: r.error.stage || null, code: r.error.code || null } : null;
  return { json: {
    job_id: r.id, source_id: r.source_id,
    p_source: JSON.stringify(source), p_meta: JSON.stringify(meta), p_error: JSON.stringify(error),
    events: [{ type: 'result_expired', level: 'info', stage: 'maintenance', body: `${r.status} job expired: finished ${r.finished_at}, retention ${days} days; content and identifying fields removed` }],
  } };
});
"""
# error = 'null'::jsonb for done jobs: the pg node drops empty parameters, so JSON null travels as a string.
EXPIRE_UPDATE_SQL = "update jobs set result = null, source = $2::jsonb, source_id = 'expired', meta = $3::jsonb, error = $4::jsonb, updated_at = now() where id = $1"
# Stuck jobs (decision 2026-09-17): a job in queued/processing older than MAX_JOB_MINUTES never finishes on its
# own – the n8n execution died with a container restart or an unhandled error – and the person watches the
# spinner until the tab is closed. It becomes failed with code timeout (contract section 6: a retry is offered)
# and a job_timeout event; the budget and concurrency windows never needed this, the person did.
STUCK_SQL = f"select id, stages, created_at, {setting_sql('MAX_JOB_MINUTES', '$1')} as max_job_minutes from jobs where status in ('queued', 'processing') and created_at < now() - ({setting_sql('MAX_JOB_MINUTES', '$1')} * interval '1 minute')"
TIMEOUT_ITEMS_JS = r"""// One item per stuck job: the running (or first pending) stage becomes failed, error carries the reason.
return $input.all().map((i) => i.json).filter((r) => r && r.id).map((r) => {
  const minutes = Number(r.max_job_minutes) || Number($env.MAX_JOB_MINUTES || 60);
  const stages = Array.isArray(r.stages) ? r.stages : [];
  const stuck = stages.find((s) => s.status === 'running') || stages.find((s) => s.status === 'pending') || { name: 'pipeline' };
  const newStages = stages.map((s) => (s.name === stuck.name ? { ...s, status: 'failed' } : s));
  const message = `job exceeded MAX_JOB_MINUTES=${minutes}: stuck at ${stuck.name} since ${r.created_at}`;
  return { json: {
    job_id: r.id, p_error: JSON.stringify({ stage: stuck.name, code: 'timeout', message: 'processing took too long' }), p_stages: JSON.stringify(newStages),
    events: [{ type: 'job_timeout', level: 'error', stage: stuck.name, body: message }],
  } };
});
"""
MARK_TIMEOUT_SQL = "update jobs set status = 'failed', error = $2::jsonb, stages = $3::jsonb, finished_at = now(), updated_at = now() where id = $1 and status in ('queued', 'processing')"
def maintenance_nodes(trigger):
    return [
        trigger,
        pg("Stuck jobs", STUCK_SQL, "{{ [Number($env.MAX_JOB_MINUTES || 60)] }}", 220, 300, alwaysOutputData=True),
        code("Timeout items", TIMEOUT_ITEMS_JS, 440, 300),
        pg("Mark timed out", MARK_TIMEOUT_SQL, "{{ [$json.job_id, $json.p_error, $json.p_stages] }}", 660, 300),
        code("Restore timeout item", "// Postgres replaced the items; put them all back for the events log.\nreturn $('Timeout items').all();", 880, 300),
        log_events("Log timeout", 1100, 300),
        pg("Expire results", EXPIRE_SQL, "{{ [Number($env.RESULT_RETENTION_DAYS || 30)] }}", 220, 0, alwaysOutputData=True),
        code("Expired items", EXPIRED_ITEMS_JS, 440, 0),
        # keep=playback is not passed: the player audio of an upload dies with the result it belonged to. For URL
        # jobs the source is gone already (cleanup after done) and 404 is the normal answer, hence on_error.
        media_http("Media delete expired", "DELETE", "{{ $env.MEDIA_URL }}/sources/{{ $json.source_id }}", 660, 0, timeout=60000, on_error=True),
        code("Restore expired item", "// The HTTP node replaced the items; put every job item back for the update ($('X').item in run-once mode returns one).\nreturn $('Expired items').all();", 880, 0),
        pg("Strip expired job", EXPIRE_UPDATE_SQL, "{{ [$json.job_id, $json.p_source, $json.p_meta, $json.p_error] }}", 1100, 0),
        code("Restore expired item 2", "// Postgres replaced the items; put them all back for the events log.\nreturn $('Expired items').all();", 1320, 0),
        log_events("Log expiry", 1540, 0),
    ]
def maintenance_wiring():
    mc = {}
    wire(mc, "Every hour", "Expire results"); wire(mc, "Expire results", "Expired items"); wire(mc, "Expired items", "Media delete expired")
    wire(mc, "Media delete expired", "Restore expired item"); wire(mc, "Restore expired item", "Strip expired job")
    wire(mc, "Strip expired job", "Restore expired item 2"); wire(mc, "Restore expired item 2", "Log expiry")
    wire(mc, "Every hour", "Stuck jobs"); wire(mc, "Stuck jobs", "Timeout items"); wire(mc, "Timeout items", "Mark timed out")
    wire(mc, "Mark timed out", "Restore timeout item"); wire(mc, "Restore timeout item", "Log timeout")
    return mc
# Error Workflow of the pipeline (2026-09-21): a node that throws ends the execution with an error and the job would
# stay in processing until MAX_JOB_MINUTES – one of two slots gone for an hour. The Error Trigger receives the failed
# execution's id and last node; the job is found by meta.execution_id and marked failed with the neutral message,
# only while it is still processing (a job that already failed or finished is left alone); the node name goes to
# an internal_error event. Attached to pipeline through settings.errorWorkflow (import.sh resolves it by name).
ON_ERROR_JS = r"""// Error Trigger payload: execution.id, execution.lastNodeExecuted, execution.error.message, workflow.name.
const e = $input.first().json || {};
const ex = e.execution || {};
const mask = (t) => String(t).replace(/\b(sk|gsk|rk|xai)[-_][^\s"'\\]{6,}/g, (m) => m.slice(0, 3) + '***').replace(/\b[A-Za-z0-9_-]{32,}\b/g, '***').replace(/(Bearer|Token)\s+[^\s"']+/gi, '$1 ***');
const message = mask((ex.error || {}).message || 'unknown error').slice(0, 240);
return [{ json: { execution_id: String(ex.id || ''), node: String(ex.lastNodeExecuted || '?'), workflow: String((e.workflow || {}).name || ''), message } }];
"""
ON_ERROR_MARK_JS = r"""// The job behind the execution: only a job still in processing is closed; anything else is left as it is.
const info = $('Error info').first().json;
const rows = $input.all().map((i) => i.json).filter((r) => r && r.id);
const out = [];
for (const r of rows) {
  if (r.status !== 'processing') { console.log(`[video-digest] on-error: job ${r.id} is ${r.status}, nothing to do (execution ${info.execution_id}, node ${info.node})`); continue; }
  const stages = Array.isArray(r.stages) ? r.stages : [];
  const stuck = stages.find((s) => s.status === 'running') || stages.find((s) => s.status === 'pending') || { name: 'pipeline' };
  const newStages = stages.map((s) => (s.name === stuck.name ? { ...s, status: 'failed' } : s));
  out.push({ json: {
    job_id: r.id, p_error: JSON.stringify({ stage: stuck.name, code: 'internal_error', message: 'internal error on our side' }), p_stages: JSON.stringify(newStages),
    events: [{ type: 'internal_error', level: 'error', stage: stuck.name, body: `${info.workflow} execution ${info.execution_id} failed at ${info.node}: ${info.message}` }],
  } });
}
return out;
"""
on_error_nodes = [
    node("Error Trigger", "n8n-nodes-base.errorTrigger", 1, {}, 0, 0),
    code("Error info", ON_ERROR_JS, 220, 0),
    pg("Load job by execution", "select id, status, stages from jobs where meta->>'execution_id' = $1", "{{ [$json.execution_id || '-'] }}", 440, 0, alwaysOutputData=True),
    code("Mark params", ON_ERROR_MARK_JS, 660, 0),
    pg("Mark failed by execution", "update jobs set status = 'failed', error = $2::jsonb, stages = $3::jsonb, finished_at = now(), updated_at = now() where id = $1 and status = 'processing'", "{{ [$json.job_id, $json.p_error, $json.p_stages] }}", 880, 0),
    code("Restore error item", "// Postgres replaced the item; put the event back for the log.\nreturn $('Mark params').all();", 1100, 0),
    log_events("Log internal error", 1320, 0),
]
oc = {}
wire(oc, "Error Trigger", "Error info"); wire(oc, "Error info", "Load job by execution"); wire(oc, "Load job by execution", "Mark params")
wire(oc, "Mark params", "Mark failed by execution"); wire(oc, "Mark failed by execution", "Restore error item"); wire(oc, "Restore error item", "Log internal error")
on_error = {"name": "on-error", "nodes": on_error_nodes, "connections": oc, "settings": {"executionOrder": "v1"}}
pipeline["settings"]["errorWorkflow"] = "on-error"   # a name: import.sh resolves it to the instance id, export.sh writes the name back

maintenance = {"name": "maintenance", "nodes": maintenance_nodes(node("Every hour", "n8n-nodes-base.scheduleTrigger", 1.2, {"rule": {"interval": [{"field": "hours", "hoursInterval": 1}]}}, 0, 0)), "connections": maintenance_wiring(), "settings": {"executionOrder": "v1"}}

import sys
# --provider-stub URL --out DIR: write llm-call and pipeline variants that call the stub (n8n/testing/provider-stub.json)
# instead of the providers – the transport test of 2026-09-20 (see scripts/validator-harness.md). Never committed.
if "--provider-stub" in sys.argv:
    stub = sys.argv[sys.argv.index("--provider-stub") + 1].rstrip("/")
    out_dir = Path(sys.argv[sys.argv.index("--out") + 1]); out_dir.mkdir(parents=True, exist_ok=True)
    if "--turnstile-stub" in sys.argv:
        # Replace siteverify with an address that answers nothing (a closed port): the unreachable path of Turnstile decide.
        tstub = sys.argv[sys.argv.index("--turnstile-stub") + 1]
        text = json.dumps(jobs_api, ensure_ascii=False, indent=2, sort_keys=True).replace(TURNSTILE_SITEVERIFY, tstub)
        (out_dir / "jobs-api.json").write_text(text + "\n", encoding="utf-8")
        print("wrote stub variant", out_dir / "jobs-api.json")
    if "--throw-after" in sys.argv:
        after = sys.argv[sys.argv.index("--throw-after") + 1]
        boom = code("Boom", f"// Test of the Error Workflow: an exception right after {after}.\nthrow new Error('test exception after {after}');", 0, 2000)
        pipeline["nodes"].append(boom)
        outs = pipeline["connections"].setdefault(after, {"main": [[]]})["main"]
        boom_targets = outs[0]; outs[0] = [{"node": "Boom", "type": "main", "index": 0}]
        pipeline["connections"]["Boom"] = {"main": [boom_targets]}
    for wf, fname in ((llm_call, "llm-call.json"), (pipeline, "pipeline.json")):
        text = json.dumps(wf, ensure_ascii=False, indent=2, sort_keys=True)
        text = text.replace("const base_url = BASES[provider] || $env.LLM_BASE_URL || 'http://localhost:8080/v1';", f"const base_url = '{stub}';")
        text = text.replace("https://api.deepgram.com/v1/listen", f"{stub}/listen")
        text = text.replace("S.stt_base_url = BASES[provider] || $env.STT_BASE_URL || 'http://localhost:8080/v1';", f"S.stt_base_url = '{stub}';")
        (out_dir / fname).write_text(text + "\n", encoding="utf-8")
        print("wrote stub variant", out_dir / fname)
    sys.exit(0)

for wf, fname in ((jobs_api, "jobs-api.json"), (llm_call, "llm-call.json"), (log_events_wf, "log-events.json"), (on_error, "on-error.json"), (pipeline, "pipeline.json"), (maintenance, "maintenance.json")):
    # Node ids are instance state assigned on import; keep the ones from the last export by node name, so that a
    # rebuild diffs only on real changes (2026-09-20; before that every rebuild renamed every node id).
    if (OUT / fname).exists():
        old = {n["name"]: n for n in json.loads((OUT / fname).read_text(encoding="utf-8")).get("nodes", [])}
        for n in wf["nodes"]:
            for k in ("id", "webhookId"):  # webhookId: n8n assigns one to trigger-like nodes (emailSend too)
                if n["name"] in old and k in old[n["name"]] and k not in n:
                    n[k] = old[n["name"]][k]
    (OUT / fname).write_text(json.dumps(wf, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", fname, len(wf["nodes"]), "nodes")
