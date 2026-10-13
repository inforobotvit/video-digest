#!/usr/bin/env node
// Retention report over the recorded clean runs in fixtures/clean-calibration/: no model, no cost.
// For every chunk: the unit count, first-attempt retention under the old and the new unit, whether the run
// retried, how many units the correction brought back, and «lost after the correction» old and new. Then the
// threshold arithmetic of 2026-09-20 (docs/result-schema.md, rule 10): defective chunks are those where the correction brought
// back a whole unit, honest ones where it brought back none; the threshold is the midpoint between the highest
// defective and the lowest honest retention, if the ranges do not overlap. Calibration runs: j_0km8l8 (ru lecture),
// j_d5fnkh (en podcast), j_7etqho (VK subtitles); the meeting j_4ac6yf and the German j_2fyciu are the control.
//
// Usage: node scripts/clean_retention_report.js [fixture.json ...]   (default: every file in fixtures/clean-calibration)
//   --units   also print the lost units of every chunk (attempt 1 new, lost-after-fix old and new)
//   --min=ru:5   what-if: another content-word minimum for one language (the validator keeps the module default)
//   --control=92   what a given threshold does on every run (chunks under 10 units are not judged, as in the validator)
const fs = require('fs');
const path = require('path');
const R = require('./clean_retention.js');

// ---------------------------------------------------------------------------------------------------------------
// The implementation in force until 2026-09-20 (build ad08582), kept here verbatim for the «old» columns only.
function oldFillers() { return new Set(['да', 'вот', 'ну', 'значит', 'э', 'ээ', 'эм', 'мм', 'ага', 'угу', 'собственно', 'как', 'бы', 'так', 'сказать', 'в', 'общем', 'то', 'есть', 'типа', 'короче', 'вообще', 'просто', 'тут', 'там', 'это', 'этот', 'эта', 'ладно', 'okay', 'ok', 'um', 'uh', 'er', 'hmm', 'like', 'so', 'well', 'yeah', 'right', 'actually', 'basically', 'literally', 'mean', 'kind', 'sort', 'you', 'know', 'i']); }
function oldTokens(t, F) { return String(t).toLowerCase().replace(/ё/g, 'е').replace(/[^\p{L}\p{N}\s-]+/gu, ' ').split(/\s+/).filter((w) => w && !F.has(w)); }
function oldRetention(userText, paragraphs) {
  const F = oldFillers();
  const src = String(userText || '').split('\nTRANSCRIPT\n').pop();
  const units = [];
  for (const ln of src.split('\n')) {
    const m = ln.match(/^\[(\d+(?:\.\d+)?)\]\s*(.*)$/);
    if (!m) continue;
    for (const sent of m[2].split(/(?<=[.!?…])\s+/)) { const w = oldTokens(sent, F); if (w.length >= 4) units.push({ t: Number(m[1]), text: sent.trim(), w }); }
  }
  const cw = oldTokens((paragraphs || []).map((p) => (p && p.text) || '').join(' '), F);
  const sh = new Set(); for (let i = 0; i + 2 < cw.length; i++) sh.add(cw[i] + ' ' + cw[i + 1] + ' ' + cw[i + 2]);
  const lost = units.filter((u) => { let n = 0, k = 0; for (let i = 0; i + 2 < u.w.length; i++) { n++; if (sh.has(u.w[i] + ' ' + u.w[i + 1] + ' ' + u.w[i + 2])) k++; } return n > 0 && k / n < 0.34; });
  return { total: units.length, kept: units.length - lost.length, lost };
}
const oldKey = (u) => `${u.t}|${u.w.join(' ')}`;
function oldLostAfterFix(prev, r) { const before = new Set(prev.lost.map(oldKey)); return r.lost.filter((u) => !before.has(oldKey(u))); }
// ---------------------------------------------------------------------------------------------------------------

const args = process.argv.slice(2);
const showUnits = args.includes('--units');
// --min=ru:5 – try another content-word minimum for one language (a what-if for the calibration talk; the validator keeps the module default).
const MIN_BY_LANG = {}; for (const a of args) { const m = a.match(/^--min=([a-z]{2}):(\d+)$/); if (m) MIN_BY_LANG[m[1]] = Number(m[2]); }
const minOf = (lang) => MIN_BY_LANG[lang];
let files = args.filter((a) => !a.startsWith('--'));
const FIX = path.join(__dirname, '..', 'fixtures', 'clean-calibration');
if (!files.length) files = fs.readdirSync(FIX).filter((f) => f.endsWith('.json')).sort().map((f) => path.join(FIX, f));

const CALIBRATION = ['j_0km8l8', 'j_d5fnkh', 'j_7etqho'];
const first = (rd, name) => (((rd[name] || [])[0] || {}).data || {}).main;
const answer = (resp) => {
  try {
    const body = (resp || {}).body || {};
    let text = String((((body.choices || [])[0] || {}).message || {}).content || '').trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
    const d = JSON.parse(text);
    return Array.isArray(d.paragraphs) ? d.paragraphs : null;
  } catch (e) { return null; }
};
const pct = (r) => (r.total ? Math.round(100 * r.kept / r.total) : null);

const rows = [];
for (const file of files) {
  const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
  const run = path.basename(file, '.json');
  const job = (run.match(/j_[a-z0-9]+/) || [run])[0];
  for (const e of Array.isArray(raw.data) ? raw.data : [raw]) {
    const rd = ((e.data || {}).resultData || {}).runData || {};
    const prep = first(rd, 'Prepare'), req1 = first(rd, 'LLM request 1');
    if (!prep || !req1) continue;
    const state = prep[0][0].json;
    if (state.kind !== 'clean') continue;
    const lang = (state.context || {}).output_language || '';
    const p1 = answer(req1[0][0].json);
    if (!p1) { rows.push({ run, job, label: state.label, lang, skipped: 'first answer is not JSON' }); continue; }
    const rNew1 = R.cleanRetention(state.user, p1, lang, minOf(lang)), rOld1 = oldRetention(state.user, p1);
    const row = { run, job, label: state.label, index: Number((state.label.match(/(\d+)\//) || [])[1]), lang, units: rNew1.total, retOld: pct(rOld1), retNew: pct(rNew1), windowed: rNew1.windowed, overlap: rNew1.overlapDropped, retry: false, returned: null, lostFixOld: null, lostFixNew: null, lost1: rNew1.lost, gone: null, goneOld: null, merged: null };
    const req2 = first(rd, 'LLM request 2');
    if (req2) {
      row.retry = true;
      const p2 = answer(req2[0][0].json);
      if (p2) {
        const rNew2 = R.cleanRetention(state.user, p2, lang, minOf(lang)), rOld2 = oldRetention(state.user, p2);
        const lost2 = new Set(rNew2.lost.map(R.lostKey));
        row.returned = rNew1.lost.filter((u) => !lost2.has(R.lostKey(u))).length;
        row.retNew2 = pct(rNew2); row.retOld2 = pct(rOld2);
        const laf = R.lostAfterFix(rNew1, rNew2);
        row.gone = laf.gone; row.merged = laf.merged; row.lostFixNew = laf.gone.length;
        row.goneOld = oldLostAfterFix(rOld1, rOld2); row.lostFixOld = row.goneOld.length;
      } else row.retry = 'second answer is not JSON';
    }
    rows.push(row);
  }
}
rows.sort((a, b) => a.run.localeCompare(b.run) || (a.index || 0) - (b.index || 0));

// A. Reading of the lost units of chunks without a retry (2026-09-20): the old rule let these chunks pass, so
// nobody checked them – «honest» must come from reading. verdict: noise (stutter, paraphrase kept, spelling,
// chunk-boundary fragment), content (a whole sentence dropped), disputed (neither class).
const LABELS = [
  { job: 'j_d5fnkh', label: 'clean 1/14', t: 47.3, verdict: 'noise', why: 'перефраз: в ответе «She talked about the traditional design process: prototype, mock…»' },
  { job: 'j_d5fnkh', label: 'clean 2/14', t: 538.4, verdict: 'noise', why: 'написание: в ответе «Go to workos.com to make your app enterprise-ready today»' },
  { job: 'j_d5fnkh', label: 'clean 2/14', t: 600.8, verdict: 'noise', why: 'заикание' },
  { job: 'j_d5fnkh', label: 'clean 9/14', t: 2846, verdict: 'noise', why: 'перефраз: в ответе «I just want to quickly say something»' },
  { job: 'j_d5fnkh', label: 'clean 11/14', t: 3439.7, verdict: 'noise', why: 'обрывок на границе куска (фраза продолжается в следующем)' },
  { job: 'j_7etqho', label: 'clean 6/13', t: 835.4, verdict: 'disputed', why: 'содержание («сегодня будет моноспектакль Светланы, приглашаем») на самом хвосте куска' },
];
const labelOf = (r, u) => (LABELS.find((l) => l.job === r.job && l.label === r.label && Math.abs(l.t - u.t) < 0.05) || {}).verdict || 'unlabeled';
// Class: D = the correction brought back at least one unit; H = it brought back none; without a retry the reading
// decides: H when every lost unit is noise (or nothing is lost), D* when a content unit is lost, ? when a lost unit
// is disputed or unlabeled.
for (const r of rows) {
  if (r.skipped) { r.cls = '-'; continue; }
  if (r.retry === true) { r.cls = r.returned > 0 ? 'D' : 'H'; continue; }
  if (r.retry) { r.cls = '?'; continue; }
  const v = r.lost1.map((u) => labelOf(r, u));
  r.cls = v.includes('content') ? 'D*' : v.some((x) => x === 'disputed' || x === 'unlabeled') ? '?' : 'H';
}

const col = (v, w, right = true) => { const s = v === null || v === undefined ? '' : String(v); return right ? s.padStart(w) : s.padEnd(w); };
console.log(col('run', 22, false) + col('chunk', 12, false) + col('lang', 5, false) + col('units', 6) + col('ret1 old', 9) + col('ret1 new', 9) + col('retry', 7) + col('ret2 new', 9) + col('back', 5) + col('laf old', 8) + col('laf new', 8) + col('cls', 4) + '  note');
for (const r of rows) {
  if (r.skipped) { console.log(col(r.run, 22, false) + col(r.label, 12, false) + col(r.lang, 5, false) + '  ' + r.skipped); continue; }
  const note = [r.windowed ? 'WINDOWED (no punctuation)' : '', r.overlap ? `overlap -${r.overlap}w` : '', r.merged ? `merged ${r.merged}` : ''].filter(Boolean).join(', ');
  console.log(col(r.run, 22, false) + col(r.label, 12, false) + col(r.lang, 5, false) + col(r.units, 6) + col(r.retOld === null ? '' : r.retOld + '%', 9) + col(r.retNew === null ? '' : r.retNew + '%', 9) + col(r.retry === true ? 'yes' : r.retry ? 'bad' : 'no', 7) + col(r.retNew2 === undefined ? '' : r.retNew2 + '%', 9) + col(r.returned, 5) + col(r.lostFixOld, 8) + col(r.lostFixNew, 8) + col(r.cls, 4) + '  ' + note);
  if (showUnits) {
    for (const u of r.lost1) console.log(`      lost1  (${u.w.length}w) [${u.t}] ${u.text.slice(0, 110)}`);
    for (const u of r.goneOld || []) console.log(`      lafOLD [${u.t}] ${u.text.slice(0, 110)}`);
    for (const u of r.gone || []) console.log(`      lafNEW [${u.t}] ${u.text.slice(0, 110)}`);
  }
}
console.log('cls: D defective (the correction brought back a unit), H honest (it brought back none), D*/H by reading of a chunk without retry, ? disputed or unlabeled');

// Per-run ranges of first-attempt retention, new unit.
console.log('\nfirst-attempt retention by run (new unit): min–max, chunks');
for (const run of [...new Set(rows.map((r) => r.run))]) {
  const rs = rows.filter((r) => r.run === run && !r.skipped);
  const v = rs.map((r) => r.retNew);
  console.log(`  ${run}: ${Math.min(...v)}–${Math.max(...v)}% over ${rs.length} chunks, retried ${rs.filter((r) => r.retry === true).length}`);
}

// A. The lost units of every chunk without a retry, in full, with the reading.
console.log('\nA. LOST UNITS OF CHUNKS WITHOUT A RETRY (first attempt, new unit) – read them: content or noise');
for (const r of rows.filter((r) => !r.skipped && r.retry === false)) {
  console.log(`  ${r.job} ${r.label} [${r.lang}] ret ${r.retNew}%: ${r.lost1.length ? r.lost1.length + ' lost' : 'nothing lost'}`);
  for (const u of r.lost1) console.log(`     (${u.w.length}w) [${u.t}] ${u.text}`);
}
console.log('\n  reading:');
console.log('  ' + col('chunk', 22, false) + col('t', 8, false) + col('verdict', 10, false) + 'why  |  phrase');
for (const r of rows.filter((r) => !r.skipped && r.retry === false)) for (const u of r.lost1) {
  const l = LABELS.find((l) => l.job === r.job && l.label === r.label && Math.abs(l.t - u.t) < 0.05) || { verdict: 'unlabeled', why: '' };
  console.log('  ' + col(`${r.job} ${r.label}`, 22, false) + col(u.t, 8, false) + col(l.verdict, 10, false) + `${l.why}  |  ${u.text.slice(0, 90)}`);
}

// B. The length rule: fire also when a lost unit has at least N content words. N from the English record:
// lengths of the units the correction brought back in defective chunks against the lengths of the noise units
// of honest chunks (reading A).
console.log('\nB. LENGTH RULE – content words of lost units, English record j_d5fnkh');
const en = rows.filter((r) => r.job === 'j_d5fnkh' && !r.skipped);
const backLens = [], stillLens = [], noiseLens = [];
for (const r of en) {
  if (r.cls === 'D') { const lost2 = new Set((r.gone || []).map(R.lostKey)); /* not used */ }
}
// recompute returned/still-lost per unit for the D chunks (rows keep only counts)
{
  for (const file of files) {
    if (!/j_d5fnkh/.test(file)) continue;
    const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
    for (const e of raw.data) {
      const rd = e.data.resultData.runData; const prep = first(rd, 'Prepare'), req1 = first(rd, 'LLM request 1'), req2 = first(rd, 'LLM request 2');
      if (!prep || !req1 || !req2) continue;
      const st = prep[0][0].json; const lang = st.context.output_language;
      const p1 = answer(req1[0][0].json), p2 = answer(req2[0][0].json); if (!p1 || !p2) continue;
      const r1 = R.cleanRetention(st.user, p1, lang, minOf(lang)), r2 = R.cleanRetention(st.user, p2, lang, minOf(lang));
      const lost2 = new Set(r2.lost.map(R.lostKey));
      for (const u of r1.lost) (lost2.has(R.lostKey(u)) ? stillLens : backLens).push({ n: u.w.length, label: st.label, text: u.text });
    }
  }
  for (const r of en.filter((r) => r.cls === 'H')) for (const u of r.lost1) noiseLens.push({ n: u.w.length, label: r.label, text: u.text });
}
const sorted = (xs) => xs.map((x) => x.n).sort((a, b) => a - b).join(' ');
console.log(`  defective chunks, units the correction brought back (${backLens.length}): ${sorted(backLens)}`);
console.log(`  defective chunks, units still lost after the correction (${stillLens.length}): ${sorted(stillLens)}`);
console.log(`  honest chunks (reading), lost units = noise (${noiseLens.length}): ${sorted(noiseLens)}`);
const noiseMax = noiseLens.length ? Math.max(...noiseLens.map((x) => x.n)) : null;
const backMin = backLens.length ? Math.min(...backLens.map((x) => x.n)) : null;
const stutterMax = noiseLens.filter((x) => !/work o s dot com/.test(x.text)).length ? Math.max(...noiseLens.filter((x) => !/work o s dot com/.test(x.text)).map((x) => x.n)) : null;
let N = noiseMax === null ? null : noiseMax + 1;
for (const a of args) { const m = a.match(/^--n=(\d+)$/); if (m) N = Number(m[1]); }
console.log(`  ranges overlap: brought-back units start at ${backMin} words, noise reaches ${noiseMax}; the short brought-back units are stutters the correction re-inserted (${backLens.filter((x) => x.n <= noiseMax).map((x) => `«${x.text.slice(0, 40)}»`).join(', ')})`);
console.log(`  N candidates: above every noise unit = max(noise) + 1 = ${noiseMax + 1}; above every stutter/paraphrase but under the spelled-out ad = ${stutterMax + 1} (lower edge: a false alarm costs one call, a miss costs content)`);
console.log(`  N in force for this report: ${N}${args.some((a) => /^--n=/.test(a)) ? ' (from --n)' : ' (default: max(noise) + 1)'}`);
console.log(`  at N = ${N}, chunk by chunk (max lost-unit length; fires when >= N):`);
for (const r of en) { const m = r.lost1.length ? Math.max(...r.lost1.map((u) => u.w.length)) : 0; console.log(`    ${r.label} ${r.cls} ret ${r.retNew}%: longest lost ${m}w -> ${m >= N ? 'FIRES' : 'quiet'}${r.cls === 'H' && m >= N ? ' (false alarm, one correction call)' : ''}`); }

// C. Threshold arithmetic per group, without and with the length rule (a defective chunk the length rule catches
// no longer has to be separated by the percentage).
function arithmetic(title, rs, n) {
  const caught = (r) => n !== null && r.lost1.some((u) => u.w.length >= n);
  const D = rs.filter((r) => (r.cls === 'D' || r.cls === 'D*') && !caught(r)), Dc = rs.filter((r) => (r.cls === 'D' || r.cls === 'D*') && caught(r));
  const H = rs.filter((r) => r.cls === 'H'), X = rs.filter((r) => r.cls === '?');
  const fmt = (xs) => xs.map((r) => `${r.job} ${r.label.replace('clean ', '')}=${r.retNew}%`).join(', ') || '-';
  const maxD = D.length ? Math.max(...D.map((r) => r.retNew)) : null, minH = H.length ? Math.min(...H.map((r) => r.retNew)) : null;
  console.log(`\n  ${title}${n !== null ? ` [with length rule N=${n}]` : ''}: D ${D.length}${Dc.length ? ` (+${Dc.length} caught by length: ${fmt(Dc)})` : ''}, H ${H.length}, excluded ${X.length}`);
  if (n !== null && D.length === 0 && Dc.length) { console.log('    every defective chunk on record has a lost unit of >= N words: the percentage cannot be calibrated from these records once the length rule is in force; it stays as the plain arithmetic above, a net for many short losses'); return null; }
  console.log(`    D: ${fmt(D)}`); console.log(`    H: ${fmt(H)}`); if (X.length) console.log(`    ?: ${fmt(X)}`);
  if (maxD === null || minH === null) { console.log('    not decidable (one side empty)'); return null; }
  if (maxD < minH) { const th = Math.floor((maxD + minH) / 2); console.log(`    max(D) ${maxD} < min(H) ${minH} -> threshold floor((${maxD}+${minH})/2) = ${th}%`); return th; }
  console.log(`    ranges overlap (max(D) ${maxD} >= min(H) ${minH}) – no threshold; overlapping chunks:`);
  for (const r of rs.filter((r) => ((r.cls === 'D' || r.cls === 'D*') && !caught(r) && r.retNew >= minH) || (r.cls === 'H' && r.retNew <= maxD))) { console.log(`      ${r.cls} ${r.job} ${r.label} ${r.retNew}%`); for (const u of r.lost1) console.log(`         lost1 (${u.w.length}w) [${u.t}] ${u.text.slice(0, 120)}`); }
  return null;
}
console.log('\nC. THRESHOLDS (German j_2fyciu stays out: no filler list, control only)');
const ok = rows.filter((r) => !r.skipped);
const groups = [
  ['OVERALL (lecture, meeting, VK, podcast)', ok.filter((r) => ['j_0km8l8', 'j_4ac6yf', 'j_7etqho', 'j_d5fnkh'].includes(r.job))],
  ['RU lecture + meeting (without VK)', ok.filter((r) => ['j_0km8l8', 'j_4ac6yf'].includes(r.job))],
  ['RU lecture + meeting + VK', ok.filter((r) => ['j_0km8l8', 'j_4ac6yf', 'j_7etqho'].includes(r.job))],
  ['EN podcast', ok.filter((r) => r.job === 'j_d5fnkh')],
];
const results = {};
for (const [title, rs] of groups) { results[title] = { plain: arithmetic(title, rs, null), withN: arithmetic(title, rs, N) }; }
// Hybrid: the percentage over the defective chunks that the length rule does not already have to separate, i.e.
// removing only the length-caught chunks that sit at or above min(H).
console.log('\n  hybrid: percentage over the D chunks below min(H) once the length rule takes the ones at/above it');
for (const [title, rs] of groups) {
  const H = rs.filter((r) => r.cls === 'H'); const minH = H.length ? Math.min(...H.map((r) => r.retNew)) : null;
  const caught = (r) => N !== null && r.lost1.some((u) => u.w.length >= N);
  const Dall = rs.filter((r) => r.cls === 'D' || r.cls === 'D*');
  const handed = Dall.filter((r) => minH !== null && r.retNew >= minH && caught(r)), rest = Dall.filter((r) => !handed.includes(r));
  const maxD = rest.length ? Math.max(...rest.map((r) => r.retNew)) : null;
  const fmt = (xs) => xs.map((r) => `${r.job} ${r.label.replace('clean ', '')}=${r.retNew}%`).join(', ') || '-';
  if (maxD === null || minH === null) { console.log(`    ${title}: not decidable`); continue; }
  console.log(`    ${title}: handed to length ${fmt(handed)}; max(D) ${maxD} vs min(H) ${minH} -> ${maxD < minH ? `floor((${maxD}+${minH})/2) = ${Math.floor((maxD + minH) / 2)}%` : 'still overlap'}`);
}

// Control: what a threshold would do on every run (first attempt, new unit; chunks with fewer than 10 units are
// not judged, as in the validator). --control=92 on the command line; the length rule is shown alongside.
const control = (th, label) => {
  if (th === null) return;
  console.log(`\ncontrol at ${th}%${N !== null ? ` or a lost unit of >= ${N} words` : ''} (${label}):`);
  for (const job of ['j_4ac6yf', 'j_2fyciu', 'j_0km8l8', 'j_d5fnkh', 'j_7etqho']) {
    const rs = rows.filter((r) => r.job === job && !r.skipped);
    const byPct = rs.filter((r) => r.units >= 10 && r.retNew < th), byLen = rs.filter((r) => r.units >= 10 && r.retNew >= th && N !== null && r.lost1.some((u) => u.w.length >= N));
    const small = rs.filter((r) => r.units < 10);
    console.log(`  ${job}: ${byPct.length + byLen.length} of ${rs.length} chunks would retry – ${byPct.length} by percentage (${byPct.map((r) => r.label.replace('clean ', '') + '=' + r.retNew + '%').join(', ') || '-'}), ${byLen.length} by length only (${byLen.map((r) => r.label.replace('clean ', '')).join(', ') || '-'})${small.length ? `; ${small.length} under 10 units not judged` : ''}`);
  }
};
for (const a of args) { const m = a.match(/^--control=(\d+)$/); if (m) control(Number(m[1]), 'given on the command line'); }

// The two acceptance checks of 2026-09-20.
console.log('\nCHECK 1 – English fragments and «lost after the correction» (j_d5fnkh):');
const EN_CASES = ["I've I've seen that sort of ratio", 'we see that more and more', 'You were getting, like, fifty per'];
for (const c of EN_CASES) {
  const hitsOld = rows.filter((r) => r.job === 'j_d5fnkh' && (r.goneOld || []).some((u) => u.text.includes(c)));
  const hitsNew = rows.filter((r) => r.job === 'j_d5fnkh' && (r.gone || []).some((u) => u.text.includes(c)));
  console.log(`  «${c}»: old ${hitsOld.map((r) => r.label).join(',') || '-'} -> new ${hitsNew.map((r) => r.label).join(',') || 'not a loss'}`);
}
console.log('\nCHECK 2 – the 13 Russian sentences of the meeting stay lost (j_4ac6yf, chunks 2 and 7):');
for (const r of rows.filter((r) => r.job === 'j_4ac6yf' && [2, 7].includes(r.index))) {
  const oldTexts = (r.goneOld || []).map((u) => u.text);
  const covered = oldTexts.filter((t) => { const w = R.contentTokens(t, R.cleanFillers('ru')); return (r.gone || []).some((u) => { const s = new Set(u.w); return w.filter((x) => s.has(x)).length >= Math.ceil(0.6 * w.length); }); });
  console.log(`  ${r.label}: old ${oldTexts.length} sentences, new ${r.lostFixNew} units (merged ${r.merged}); old sentences covered by new lost units: ${covered.length} of ${oldTexts.length}`);
  for (const t of oldTexts) console.log(`     ${covered.includes(t) ? 'kept-lost ' : 'NOT LOST  '} ${t.slice(0, 100)}`);
}
console.log('\nGerman (j_2fyciu, empty filler list – the minimum applies to every word):');
for (const r of rows.filter((r) => r.job === 'j_2fyciu')) console.log(`  ${r.label}: ${r.units} units, ret1 old ${r.retOld}% new ${r.retNew}%, retry ${r.retry === true ? 'yes' : 'no'}${r.retry === true ? `, ret2 new ${r.retNew2}%, back ${r.returned}, laf old ${r.lostFixOld} new ${r.lostFixNew}` : ''}`);
