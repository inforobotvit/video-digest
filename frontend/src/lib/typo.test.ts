import { describe, expect, it } from 'vitest';
import sample from '@fixtures/result-sample.json';
import type { VideoDigestResult } from '@/types/result';
import { typo, typoResult, typoShort } from './typo';
import { buildChapters, findQuoteInParagraph } from './digest';

const real = import.meta.glob<VideoDigestResult>('@fixtures/real/*.json', {
  eager: true,
  import: 'default',
});
const fixtures: [string, VideoDigestResult][] = [
  ['sample', sample as unknown as VideoDigestResult],
  ...Object.entries(real),
];

/** Quotes located in some transcript paragraph, per fixture. */
function foundQuotes(result: VideoDigestResult): number {
  let n = 0;
  for (const ch of buildChapters(result))
    for (const q of ch.quotes)
      if (result.transcript.clean.some((p) => findQuoteInParagraph(q, p))) n += 1;
  return n;
}

describe('typo', () => {
  it('sets Russian typography: hanging prepositions, quotes and dashes', () => {
    const out = typo('Видео в конспект - "быстро"');
    expect(out.replace(/[\u00a0\u202f]/g, ' ')).toBe('Видео в конспект – «быстро»');
    expect(out).toContain('в\u00a0конспект\u00a0–');
  });

  it('typoShort keeps the typography but drops non-breaking spaces', () => {
    expect(typoShort('Вопросы для самопроверки - "быстро"')).toBe(
      'Вопросы для самопроверки – «быстро»',
    );
  });

  it('leaves ids, codes and urls of a result untouched', () => {
    const r = typoResult(sample as unknown as VideoDigestResult);
    expect(r.job_id).toBe(sample.job_id);
    expect(r.source.url).toBe(sample.source.url);
    expect(r.meta.stages).toEqual(sample.meta.stages);
  });

  for (const [name, result] of fixtures) {
    it(`keeps every transcript quote findable after typesetting (${name})`, () => {
      const before = foundQuotes(result);
      expect(before).toBeGreaterThan(0);
      expect(foundQuotes(typoResult(result))).toBe(before);
    });
  }
});
