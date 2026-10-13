#!/usr/bin/env node
// Replay recorded llm-call executions through the current Validate 1 script of workflows/llm-call.json,
// without calling the model: the state comes from the recorded Prepare node, the answer from the recorded
// LLM request 1 node. This is how a validator change is checked before it goes into the instance – on the
// chunks of real runs, at no cost (a lost run on 2026-09-17 paid a transcription to find a declaration-order
// bug that this replay reproduces in a second). See validator-harness.md.
//
// Usage: node scripts/validator_harness.js <executions.json> [kind] [--diff]
//   executions.json – GET /api/v1/executions?workflowId=<llm-call id>&includeData=true (scripts/fetch_executions.sh),
//                     or a single execution from GET /api/v1/executions/<id>?includeData=true
//   kind            – clean | map | digest | critique | glossary | ... (default: every kind)
//   --diff          – also print the verdict the instance gave at the time (recorded Validate 1 output)
//   --attempt2      – replay Validate 2 instead: state from the recorded Retry node, answer from LLM request 2
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const flags = args.filter((a) => a.startsWith('--'));
const [file, kindFilter] = args.filter((a) => !a.startsWith('--'));
if (!file) { console.error('usage: validator_harness.js <executions.json> [kind] [--diff]'); process.exit(2); }
const wf = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'workflows', 'llm-call.json'), 'utf8'));
const attempt2 = process.argv.includes('--attempt2');
const js = wf.nodes.find((n) => n.name === (attempt2 ? 'Validate 2' : 'Validate 1')).parameters.jsCode;
// The Code node reads $('Prepare') and $input; both become stubs that hand back the recorded items.
// $runIndex = 0 and an empty .all(): the replay is always the first transport attempt of a call.
const script = new Function('$', '$input', '$runIndex', js.replace(/\$\('[^']+'\)/g, "$('x')"));
const run = (state, resp) => script(() => ({ first: () => ({ json: state }), all: () => [] }), { first: () => ({ json: resp }) }, 0)[0].json;

const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
const executions = Array.isArray(raw.data) ? raw.data : [raw];
const first = (rd, name) => (((rd[name] || [])[0] || {}).data || {}).main;
let n = 0, ok = 0, soft = 0, hard = 0;
for (const e of executions) {
  const rd = ((e.data || {}).resultData || {}).runData || {};
  const prep = first(rd, attempt2 ? 'Retry' : 'Prepare'), req = first(rd, attempt2 ? 'LLM request 2' : 'LLM request 1');
  if (!prep || !req) continue;
  const state = prep[0][0].json, resp = req[0][0].json;
  if (kindFilter && state.kind !== kindFilter) continue;
  n++;
  let out;
  try { out = run(state, resp); } catch (err) { console.log(`${e.id} ${state.label}: SCRIPT ERROR ${err.message}`); process.exitCode = 1; continue; }
  const verdict = out.ok ? 'ok' : out.soft ? 'soft' : 'hard';
  if (out.ok) ok++; else if (out.soft) soft++; else hard++;
  let line = `${e.id} ${state.label} [${state.model}]: ${verdict}${out.error ? ' – ' + String(out.error).slice(0, 160) : ''}${out.warnings && out.warnings.length ? ' – warnings: ' + out.warnings.map((w) => String(w).slice(0, 140)).join(' | ') : ''}`;
  if (flags.includes('--diff')) {
    const then = ((first(rd, attempt2 ? 'Validate 2' : 'Validate 1') || [[{}]])[0][0] || {}).json || {};
    const thenVerdict = then.ok ? 'ok' : then.soft ? 'soft' : then.error ? 'hard' : '?';
    if (thenVerdict !== verdict) line += `   (instance said: ${thenVerdict}${then.error ? ' – ' + String(then.error).slice(0, 80) : ''})`;
  }
  console.log(line);
}
console.log(`\n${n} answers: ok ${ok}, soft ${soft}, hard ${hard}`);
