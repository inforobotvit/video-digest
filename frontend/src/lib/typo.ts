import Typograf from 'typograf';
import type { VideoDigestResult } from '@/types/result';

/**
 * Russian typography for everything the reader sees: interface strings and the text fields of a
 * result (tldr, points, summaries, transcript, extras). Runs once per string, output is cached.
 * Quotes and the transcript go through the same pass, so verbatim quote lookup keeps working
 * (see foldTypo / findQuoteInParagraph).
 */
const tp = new Typograf({ locale: ['ru', 'en-US'] });
// Labels like TL;DR must not become "TL; DR".
tp.disableRule('common/space/afterSemicolon');
// Typograf's Russian dash is the em dash; the brief and the pipeline use « – ».
const cache = new Map<string, string>();

export function typo(s: string): string {
  const hit = cache.get(s);
  if (hit !== undefined) return hit;
  const out = tp.execute(s).replace(/—/g, '–');
  cache.set(s, out);
  return out;
}

/**
 * Typography without non-breaking spaces, for short texts in narrow boxes (preset cards, option
 * descriptions): with nbsp after prepositions Chrome runs out of break points and hyphenates
 * words like "са-мопроверки" instead.
 */
export function typoShort(s: string): string {
  return typo(s).replace(/[\u00A0\u202F]/g, ' ');
}

/** Deep copy of an object where every string value (and every string a function returns) is typeset. */
export function typoDeep<T>(value: T, set: (s: string) => string = typo): T {
  if (typeof value === 'string') return set(value) as T;
  if (typeof value === 'function') {
    const fn = value as unknown as (...a: unknown[]) => unknown;
    return ((...a: unknown[]) => {
      const r = fn(...a);
      return typeof r === 'string' ? set(r) : r;
    }) as T;
  }
  if (Array.isArray(value)) return value.map((v) => typoDeep(v, set)) as T;
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>))
      out[k] = typoDeep(v, set);
    return out as T;
  }
  return value;
}

/** Result fields that hold prose; ids, codes, urls, dates and enums stay untouched. */
const TEXT_KEYS = new Set([
  'text',
  'detail',
  'note',
  'claim',
  'title',
  'summary',
  'tldr',
  'term',
  'definition',
  'question',
  'answer',
  'issue',
  'disclaimer',
  'translation',
  'speaker',
  'owner',
  'due',
  'strong',
  'missing',
]);

function walk(value: unknown, key: string | null): unknown {
  if (typeof value === 'string') return key !== null && TEXT_KEYS.has(key) ? typo(value) : value;
  if (Array.isArray(value)) return value.map((v) => walk(v, key));
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = walk(v, k);
    return out;
  }
  return value;
}

export function typoResult(result: VideoDigestResult): VideoDigestResult {
  return walk(result, null) as VideoDigestResult;
}

/**
 * One-to-one character folding for substring search after typesetting: every kind of space,
 * dash and quote maps to one plain character, so indexes in the folded string equal indexes in
 * the original.
 */
export function foldTypo(s: string): string {
  return s
    .toLowerCase()
    .replace(/[\u00A0\u2007\u2009\u202F]/g, ' ')
    .replace(/[\u2010-\u2015\u2212]/g, '-')
    .replace(/[\u00AB\u00BB\u201E\u201C\u201D"\u2018\u2019']/g, '"');
}
