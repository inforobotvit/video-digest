import { describe, expect, it } from 'vitest';
import {
  buildChapters,
  findQuoteInParagraph,
  objectionForQuote,
  paragraphGroups,
  partIndexAt,
} from './digest';
import type { VideoDigestResult } from '@/types/result';

const structure = [
  { title: 'A', start: 0, end: 60, summary: '' },
  { title: 'B', start: 60, end: 120, summary: '' },
  { title: 'C', start: 120, end: 180, summary: '' },
];

describe('partIndexAt', () => {
  it('binds by [start, end) and snaps to the edges', () => {
    expect(partIndexAt(structure, 0)).toBe(0);
    expect(partIndexAt(structure, 59.9)).toBe(0);
    expect(partIndexAt(structure, 60)).toBe(1);
    expect(partIndexAt(structure, 180)).toBe(2);
    expect(partIndexAt(structure, 999)).toBe(2);
  });
});

describe('buildChapters', () => {
  const result = {
    digest: {
      structure,
      key_points: [
        { text: 'p1', detail: '', start: 10 },
        { text: 'p2', detail: '', start: 70 },
        { text: 'p0', detail: '', start: 5 },
      ],
      quotes: [{ text: 'q', translation: null, start: 130, speaker: null }],
      tldr: '',
    },
    extras: {
      critique: { strong: [], weak: [{ claim: 'q', issue: 'i', start: 130.4 }], missing: [] },
    },
    transcript: {
      clean: [
        { start: 0, text: 'one two' },
        { start: 65, text: 'three' },
      ],
    },
  } as unknown as VideoDigestResult;

  it('groups points, quotes, objections and paragraphs by chapter, sorted by start', () => {
    const ch = buildChapters(result);
    expect(ch[0].points.map((p) => p.text)).toEqual(['p0', 'p1']);
    expect(ch[1].points.map((p) => p.text)).toEqual(['p2']);
    expect(ch[2].quotes).toHaveLength(1);
    expect(ch[2].objections).toHaveLength(1);
    expect(ch[1].paragraphs.map((p) => p.text)).toEqual(['three']);
    expect(objectionForQuote(ch[2].quotes[0], ch[2].objections)?.issue).toBe('i');
  });

  it('splits paragraphs after each key point', () => {
    const ch = buildChapters(result);
    const groups = paragraphGroups(ch[0]);
    expect(groups.get(-1)?.map((p) => p.start)).toEqual([0]);
  });
});

describe('findQuoteInParagraph', () => {
  it('finds a verbatim fragment ignoring case and the final punctuation', () => {
    const para = { start: 1, text: 'Так вот, Читатели никогда не блокируют писателей. Дальше.' };
    expect(
      findQuoteInParagraph(
        {
          text: 'читатели никогда не блокируют писателей.',
          translation: null,
          start: 1,
          speaker: null,
        },
        para,
      ),
    ).toEqual([9, 48]);
    expect(
      findQuoteInParagraph(
        { text: 'нет такого', translation: null, start: 1, speaker: null },
        para,
      ),
    ).toBeNull();
  });
});
