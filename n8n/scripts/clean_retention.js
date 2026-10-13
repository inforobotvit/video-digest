// Retention of a clean answer (docs/result-schema.md section 9, rule 10): the measuring instrument, kept apart
// from the pipeline so it can be calibrated with scripts/validator_harness.js and scripts/clean_retention_report.js
// on n8n/fixtures/clean-calibration/ without the model and without a paid run.
// Functions, not top-level consts: the validator's main code runs before this text, and a const declared here
// would still be in its temporal dead zone when validate() is called (j_0zijqp fell on exactly that).
//
// The unit (2026-09-20, step B of the clean fix). The old unit came from the shape of the input – one "[t] text"
// line split at sentence punctuation – and whisper segments, Deepgram utterances and subtitle cues all cut speech
// mid-sentence, so a "unit" was a 4–6 word fragment and a rephrased fragment counted as a loss. Now the texts of
// every line of the chunk are joined into one stream of words, each word remembers the timestamp of the segment
// it came from, and the stream is cut at sentence punctuation. A unit's timestamp is the start of the segment
// holding its first word. Roll-up subtitle cues repeat the tail of the previous cue at the start of the next one
// (VK: "A", "A B", "B", "B C", …); a prefix of at least 3 words that equals the tail of what was already joined is
// dropped, so the joined text reads once.
function cleanFillers(lang) {
  const RU = ['да', 'вот', 'ну', 'значит', 'э', 'ээ', 'эм', 'мм', 'ага', 'угу', 'собственно', 'как', 'бы', 'так', 'сказать', 'в', 'общем', 'то', 'есть', 'типа', 'короче', 'вообще', 'просто', 'тут', 'там', 'это', 'этот', 'эта', 'ладно'];
  // Contractions of the fillers stay fillers ("I've", "you're"): apostrophes are part of a token now, so "I've" no
  // longer splits into the filler "i" and a junk content word "ve" (that junk made "I've I've seen that sort of
  // ratio" a six-word unit on 2026-09-20).
  const EN = ['okay', 'ok', 'um', 'uh', 'er', 'hmm', 'like', 'so', 'well', 'yeah', 'right', 'actually', 'basically', 'literally', 'mean', 'kind', 'sort', 'you', 'know', 'i', "i'm", "i've", "i'll", "i'd", "you're", "you've", "you'll", "you'd"];
  // A language without a list (de, …) strips nothing: the minimum then applies to every word.
  return new Set(lang === 'ru' ? RU : lang === 'en' ? EN : []);
}
// Minimum content words in a unit: 6 by default (was 4 until 2026-09-20), 5 for Russian – calibration of 2026-09-20:
// short Russian sentences carry content at five words, for example «Фрейда ему тоже удалось обворожить» and «Он сумел
// предсказать американские ландшафты» (the public Cosmoscow lecture, n8n/fixtures/real/cosmoscow-lecture-notices.json).
function cleanMinContent(lang) { const BY_LANG = { ru: 5 }; return BY_LANG[lang] || 6; }
function contentTokens(t, F) { return String(t).toLowerCase().replace(/ё/g, 'е').replace(/[’‘]/g, "'").replace(/[^\p{L}\p{N}\s'-]+/gu, ' ').split(/\s+/).map((w) => w.replace(/^'+|'+$/g, '')).filter((w) => w && !F.has(w)); }
// `min` overrides the content-word minimum (calibration report only; the validator passes nothing).
function cleanUnits(userText, lang, min) {
  const F = cleanFillers(lang), MIN = min || cleanMinContent(lang);
  const src = String(userText || '').split('\nTRANSCRIPT\n').pop();
  const norm = (w) => w.toLowerCase().replace(/ё/g, 'е').replace(/[^\p{L}\p{N}]+/gu, '');
  const words = []; // { s: surface word, t: segment start, n: normalized }
  let overlapDropped = 0, prevLen = 0;
  for (const ln of src.split('\n')) {
    const m = ln.match(/^\[(\d+(?:\.\d+)?)\]\s*(.*)$/);
    if (!m) continue;
    const t = Number(m[1]);
    const ws = m[2].split(/\s+/).filter(Boolean).map((s) => ({ s, t, n: norm(s) }));
    // Roll-up overlap: the longest prefix of this line equal to the tail of the stream, when it is at least 3 words,
    // or the whole line, or exactly the whole previous line (VK cues come in pairs: "A", "A B", "B", "B C", …).
    let cut = 0;
    for (let k = Math.min(ws.length, words.length, 40); k >= 1; k--) {
      if (!(k >= 3 || k === ws.length || k === prevLen)) continue;
      let same = true;
      for (let i = 0; i < k; i++) if (ws[i].n !== words[words.length - k + i].n) { same = false; break; }
      if (same) { cut = k; break; }
    }
    overlapDropped += cut;
    prevLen = ws.length;
    for (let i = cut; i < ws.length; i++) words.push(ws[i]);
  }
  const isEnd = (w) => /[.!?…]+["»”')\]]*$/.test(w.s);
  // Rule 2: fewer than one sentence end per 40 words means the input carries no punctuation to cut by (some
  // subtitles): cut windows of about 15 content words instead and mark the chunk.
  const ends = words.filter(isEnd).length;
  const windowed = words.length >= 40 && ends < words.length / 40;
  const units = [];
  let cur = [], content = 0;
  const flush = () => {
    if (!cur.length) return;
    const text = cur.map((w) => w.s).join(' ');
    const w = contentTokens(text, F);
    if (w.length >= MIN) units.push({ t: cur[0].t, text, w });
    cur = []; content = 0;
  };
  for (const w of words) {
    cur.push(w);
    if (windowed) { if (w.n && !F.has(w.n)) content++; if (content >= 15) flush(); }
    else if (isEnd(w)) flush();
  }
  flush();
  return { units, windowed, words: words.length, overlapDropped };
}
function cleanRetention(userText, paragraphs, lang, min) {
  const F = cleanFillers(lang);
  const cu = cleanUnits(userText, lang, min);
  const units = cu.units;
  const cw = contentTokens((paragraphs || []).map((p) => (p && p.text) || '').join(' '), F);
  const sh = new Set(); for (let i = 0; i + 2 < cw.length; i++) sh.add(cw[i] + ' ' + cw[i + 1] + ' ' + cw[i + 2]);
  const lost = units.filter((u) => { let n = 0, k = 0; for (let i = 0; i + 2 < u.w.length; i++) { n++; if (sh.has(u.w[i] + ' ' + u.w[i + 1] + ' ' + u.w[i + 2])) k++; } return n > 0 && k / n < 0.34; });
  return { total: units.length, kept: units.length - lost.length, lost, cw, windowed: cu.windowed, overlapDropped: cu.overlapDropped };
}
// lostKey: the strict «lost after the correction» key – timestamp and content tokens.
function lostKey(u) { return `${u.t}|${u.w.join(' ')}`; }
// Coverage of a unit's content words in the best window of 1.5× its length over the answer's content tokens.
function unitCoverage(u, cw) {
  const need = new Set(u.w); if (!need.size) return 1;
  const len = Math.ceil(1.5 * u.w.length);
  let best = 0;
  for (let i = 0; i <= Math.max(0, cw.length - 1); i += 1) {
    const seen = new Set();
    for (let j = i; j < Math.min(cw.length, i + len); j++) if (need.has(cw[j])) seen.add(cw[j]);
    if (seen.size > best) best = seen.size;
    if (best === need.size) break;
  }
  return best / need.size;
}
// Rule 5 (2026-09-20): a unit is «lost after the correction» only if it failed the shingle check against the
// second answer AND fewer than 60% of its content words occur in one window of 1.5× its length there – a
// re-punctuated or merged sentence keeps its words and is not a loss. `prev` is the retention of the first answer
// (same input), `r` that of the second.
function lostAfterFix(prev, r) {
  const before = new Set(prev.lost.map(lostKey));
  const candidates = r.lost.filter((u) => !before.has(lostKey(u)));
  const gone = candidates.filter((u) => unitCoverage(u, r.cw) < 0.6);
  return { gone, merged: candidates.length - gone.length };
}
// Rule 10 thresholds (calibration of 2026-09-20 on j_0km8l8, j_4ac6yf, j_7etqho, j_d5fnkh, see docs/result-schema.md):
// a chunk goes back for correction when fewer than 92% of its units survive OR a lost unit has 10 or more content
// words; a chunk under 10 units is not judged.
// Known false positive, not treated: spelled-out addresses, abbreviations and numerals that the model normalizes
// as the prompt asks («work o s dot com» → «workos.com», «двадцатого» → «20-го» with smart_format) share no shingles
// with the input and count as lost – one correction call per case.
function cleanThresholds() { return { minRetention: 0.92, longUnitWords: 10, minUnits: 10 }; }
// --- module boundary: everything above is inserted verbatim into the Validate nodes of llm-call by
// scripts/build_workflows.py (Code nodes cannot require); below is for node (harness, calibration) only.
module.exports = { cleanFillers, cleanMinContent, contentTokens, cleanUnits, cleanRetention, lostKey, unitCoverage, lostAfterFix, cleanThresholds };
