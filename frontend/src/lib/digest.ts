import { foldTypo } from './typo';
import type { Digest, Extras, Transcript, VideoDigestResult } from '@/types/result';

export type Depth = 1 | 2 | 3;

export type KeyPoint = Digest['key_points'][number];
export type Quote = Digest['quotes'][number];
export type Part = Digest['structure'][number];
export type Paragraph = Transcript['clean'][number];
export type Objection = NonNullable<Extras['critique']>['weak'][number];

/** Everything the page needs about one structure part, bound by `start` (result-schema.md, section 4). */
export interface Chapter {
  index: number;
  part: Part;
  points: KeyPoint[];
  quotes: Quote[];
  objections: Objection[];
  paragraphs: Paragraph[];
  /** seconds of transcript covered by the part */
  seconds: number;
}

/** Index of the part whose [start, end) contains `t`; the last part also takes t == end. */
export function partIndexAt(structure: Part[], t: number): number {
  if (structure.length === 0) return -1;
  for (let i = 0; i < structure.length; i++) {
    const p = structure[i];
    const last = i === structure.length - 1;
    if (t >= p.start && (t < p.end || (last && t <= p.end))) return i;
  }
  // Timecodes before the first part or after the last one snap to the nearest edge.
  return t < structure[0].start ? 0 : structure.length - 1;
}

export function buildChapters(result: VideoDigestResult): Chapter[] {
  const { structure, key_points, quotes } = result.digest;
  const weak = result.extras.critique?.weak ?? [];
  const chapters: Chapter[] = structure.map((part, index) => ({
    index,
    part,
    points: [],
    quotes: [],
    objections: [],
    paragraphs: [],
    seconds: Math.max(0, part.end - part.start),
  }));
  const byStart = <T extends { start: number }>(
    items: T[],
    push: (c: Chapter, item: T) => void,
  ) => {
    for (const item of [...items].sort((a, b) => a.start - b.start)) {
      const i = partIndexAt(structure, item.start);
      if (i >= 0) push(chapters[i], item);
    }
  };
  byStart(key_points, (c, p) => c.points.push(p));
  byStart(quotes, (c, q) => c.quotes.push(q));
  byStart(weak, (c, w) => c.objections.push(w));
  byStart(result.transcript.clean, (c, p) => c.paragraphs.push(p));
  return chapters;
}

/** Objection about the same place as a quote: within a second, or the claim is the quote's text. */
export function objectionForQuote(quote: Quote, objections: Objection[]): Objection | undefined {
  const norm = (s: string) =>
    s
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, ' ')
      .trim();
  return objections.find(
    (o) => Math.abs(o.start - quote.start) < 1 || norm(o.claim) === norm(quote.text),
  );
}

/** Effective depth of a chapter: the global depth unless the reader changed this chapter. */
export function effectiveDepth(
  global: Depth,
  overrides: ReadonlyMap<number, Depth>,
  index: number,
): Depth {
  return overrides.get(index) ?? global;
}

/** Split a chapter's paragraphs into groups following each key point (paragraphs before the first point form group -1). */
export function paragraphGroups(chapter: Chapter): Map<number, Paragraph[]> {
  const groups = new Map<number, Paragraph[]>();
  const starts = chapter.points.map((p) => p.start);
  for (const para of chapter.paragraphs) {
    let g = -1;
    for (let i = 0; i < starts.length; i++) if (para.start >= starts[i]) g = i;
    const list = groups.get(g) ?? [];
    list.push(para);
    groups.set(g, list);
  }
  return groups;
}

/** Position of a verbatim quote inside a paragraph, case-insensitive; null when not there. */
export function findQuoteInParagraph(quote: Quote, paragraph: Paragraph): [number, number] | null {
  const hay = foldTypo(paragraph.text);
  const needle = foldTypo(quote.text.trim().replace(/[.!?…]+$/u, ''));
  if (!needle) return null;
  const i = hay.indexOf(needle);
  return i >= 0 ? [i, i + needle.length] : null;
}

/**
 * data-row key of the row the player is in: the last title / key point / paragraph (whichever
 * the depth shows) that starts at or before `t`. Null when `t` is before the chapter.
 */
export function currentRowKey(chapter: Chapter, depth: Depth, t: number): string | null {
  if (t < chapter.part.start - 0.001) return null;
  let key = 'title';
  let best = chapter.part.start;
  if (depth >= 2)
    chapter.points.forEach((p, i) => {
      if (p.start <= t + 0.001 && p.start >= best) {
        best = p.start;
        key = `point-${i}`;
      }
    });
  if (depth === 3)
    for (const p of chapter.paragraphs)
      if (p.start <= t + 0.001 && p.start >= best) {
        best = p.start;
        key = `para-${p.start}`;
      }
  return key;
}

export function wordCount(paragraphs: Paragraph[]): number {
  return paragraphs.reduce((n, p) => n + p.text.trim().split(/\s+/).filter(Boolean).length, 0);
}
