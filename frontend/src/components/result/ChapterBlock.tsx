import { memo } from 'react';
import { ChevronDown, ChevronUp, Play, TriangleAlert } from 'lucide-react';
import type { VideoDigestResult } from '@/types/result';
import {
  findQuoteInParagraph,
  objectionForQuote,
  paragraphGroups,
  type Chapter,
  type Depth,
  type Objection,
  type Paragraph,
  type Quote,
} from '@/lib/digest';
import { chapterColor, chapterTint } from '@/lib/chapterColors';
import { formatTimecode, minutesRounded, platformUrlAt } from '@/lib/timecode';
import { S } from '@/strings';
import { Timecode } from './Timecode';
import { MarginLayer, type MarginCard } from './MarginLayer';

interface Props {
  chapter: Chapter;
  result: VideoDigestResult;
  depth: Depth;
  globalDepth: Depth;
  /** data-row of the row the player is in, when it is in this chapter */
  nowRow: string | null;
  onDepth: (index: number, d: Depth | null) => void;
  onSeek: (seconds: number) => void;
  /** mobile (turn 4): the depth toggle moves below the text */
  mobile: boolean;
  /** no margin column (up to 1100px): sidenotes become insets under their row */
  insets: boolean;
}

/** Index of the last key point that starts at or before `t`; -1 means "the title row". */
function rowFor(starts: number[], t: number): number {
  let row = -1;
  for (let i = 0; i < starts.length; i++) if (t >= starts[i] - 0.001) row = i;
  return row;
}

/** At full depth a card sits next to the last paragraph starting at or before its moment. */
function paraAnchor(chapter: Chapter, t: number, pointStarts: number[]): string {
  let best: Paragraph | null = null;
  for (const p of chapter.paragraphs) if (p.start <= t + 0.001) best = p;
  if (best) return `para-${best.start}`;
  const row = rowFor(pointStarts, t);
  return row < 0 ? 'title' : `point-${row}`;
}

/** Memoised: the player updates the page several times a second, only the current chapter re-renders. */
export const ChapterBlock = memo(function ChapterBlock({
  chapter,
  result,
  depth,
  globalDepth,
  nowRow,
  onDepth: onDepthAt,
  onSeek,
  mobile,
  insets,
}: Props) {
  const onDepth = (d: Depth | null) => onDepthAt(chapter.index, d);
  const color = chapterColor(chapter.index);
  const nowClass = (row: string) => (row === nowRow ? 'tc--now' : '');
  const { part, points, quotes, objections } = chapter;
  const platformUrl = platformUrlAt(result.source.platform, result.source.url, part.start);

  // A quote and an objection about the same place form one card (mockup: dashed divider).
  const paired = new Map<Quote, Objection | undefined>(
    quotes.map((q) => [q, objectionForQuote(q, objections)]),
  );
  const loneObjections = objections.filter((o) => ![...paired.values()].includes(o));

  // At full depth a quote found verbatim in a paragraph is highlighted there, not carded.
  const groups = depth === 3 ? paragraphGroups(chapter) : new Map<number, Paragraph[]>();
  const inline = new Map<Quote, Paragraph>();
  if (depth === 3) {
    for (const q of quotes) {
      const para = chapter.paragraphs.find((p) => findQuoteInParagraph(q, p));
      if (para) inline.set(q, para);
    }
  }

  const pointStarts = points.map((p) => p.start);
  const rowKey = (row: number) => (row < 0 ? 'title' : `point-${row}`);
  const anchorFor = (t: number) =>
    depth === 3 ? paraAnchor(chapter, t, pointStarts) : rowKey(rowFor(pointStarts, t));

  // Margin cards live in their own layer (MarginLayer) and never widen a text row.
  const cards: MarginCard[] = [];
  if (depth >= 2) {
    // Keys carry the index: two quotes can share a start (event-driven-architecture fixture).
    quotes.forEach((q, qi) => {
      const para = inline.get(q);
      const objection = paired.get(q);
      cards.push(
        para
          ? {
              key: `iq${qi}-${q.start}`,
              anchor: `para-${para.start}`,
              moment: q.start,
              node: (
                <div className="mcard" style={{ borderColor: color }}>
                  <button
                    type="button"
                    className="mcard__link"
                    style={{ color }}
                    onClick={() => onSeek(q.start)}
                  >
                    <Play size={11} />
                    {S.quoteLink} · <span className="tc tc--inline">{formatTimecode(q.start)}</span>
                  </button>
                  {objection && <ObjectionBody objection={objection} withTop onSeek={onSeek} />}
                </div>
              ),
            }
          : {
              key: `q${qi}-${q.start}`,
              anchor: anchorFor(q.start),
              moment: q.start,
              node: <QuoteCard quote={q} objection={objection} color={color} onSeek={onSeek} />,
            },
      );
    });
    loneObjections.forEach((o, oi) => {
      cards.push({
        key: `o${oi}-${o.start}`,
        anchor: anchorFor(o.start),
        moment: o.start,
        node: <ObjectionCard objection={o} onSeek={onSeek} />,
      });
    });
    cards.sort((a, b) => a.moment - b.moment);
  }

  // Without a margin column every card sits right under its row, in the text column (turn 4a/4b).
  const byAnchor = new Map<string, MarginCard[]>();
  if (insets) for (const c of cards) byAnchor.set(c.anchor, [...(byAnchor.get(c.anchor) ?? []), c]);
  const inset = (anchor: string) => {
    const list = byAnchor.get(anchor);
    if (!list) return null;
    return (
      <div className="row row--inset">
        <div className="row__gutter" />
        <div className="row__text">
          {list.map((c) => (
            <div key={c.key} className="inset">
              {c.node}
            </div>
          ))}
        </div>
      </div>
    );
  };

  const minutes = minutesRounded(chapter.seconds);
  const toggle = () => {
    if (depth === 1) onDepth(points.length > 0 ? 2 : 3);
    else if (depth === 2) onDepth(3);
    else onDepth(globalDepth < 3 ? globalDepth : 1);
  };
  const toggleLabel =
    depth === 1
      ? points.length > 0
        ? S.showPoints(points.length)
        : S.showTranscript(minutes)
      : depth === 2
        ? S.showTranscript(minutes)
        : S.collapse;

  const toggleButton = (
    <button type="button" className="chapter__toggle" onClick={toggle}>
      {depth === 3 && mobile && <ChevronUp size={12} />}
      {toggleLabel}
      {depth === 3 ? !mobile && <ChevronUp size={12} /> : <ChevronDown size={12} />}
    </button>
  );

  return (
    <section className="chapter" id={`chapter-${chapter.index}`} data-depth={depth}>
      {!insets && <MarginLayer cards={cards} />}

      <div className="row row--title" data-row="title">
        <div className="row__gutter">
          <Timecode
            seconds={part.start}
            color={depth > 1 ? color : undefined}
            className={nowClass('title')}
            onSeek={onSeek}
          />
          <span className="dot dot--square" style={{ background: color }} />
        </div>
        <div className="row__text">
          <div className="chapter__head">
            <div className="chapter__title-wrap">
              <button type="button" className="chapter__title" onClick={() => onSeek(part.start)}>
                {part.title}
              </button>
              {platformUrl && (
                <a
                  className="chapter__ext"
                  href={platformUrl}
                  target="_blank"
                  rel="noreferrer"
                  title={S.openOnPlatform}
                  style={{ color }}
                >
                  <Play size={14} />
                </a>
              )}
            </div>
            {!mobile && toggleButton}
          </div>
          {depth === 1 && (
            <p className="chapter__summary">
              {part.summary}
              {objections.length > 0 && (
                <span className="chapter__badge">
                  <TriangleAlert size={12} />
                  {S.objectionsBadge(objections.length)}
                </span>
              )}
            </p>
          )}
          {depth === 2 && points.length === 0 && (
            <p className="chapter__summary">
              {part.summary} <span className="chapter__none">{S.noPoints}</span>
            </p>
          )}
        </div>
      </div>
      {inset('title')}

      {depth === 3 &&
        (groups.get(-1) ?? []).map((p) => (
          <ParagraphRow
            key={p.start}
            paragraph={p}
            inline={inline}
            color={color}
            now={nowRow === `para-${p.start}`}
            onSeek={onSeek}
            inset={inset(`para-${p.start}`)}
          />
        ))}

      {depth >= 2 &&
        points.map((kp, i) => (
          <div key={`${i}-${kp.start}`} className="point-group">
            <div className="row row--point" data-row={rowKey(i)}>
              <div className="row__gutter">
                <Timecode
                  seconds={kp.start}
                  color={color}
                  className={nowClass(rowKey(i))}
                  onSeek={onSeek}
                />
                <span className="dot dot--round" style={{ background: color }} />
              </div>
              <div className="row__text">
                <p className="point">
                  <b>{kp.text}</b> {kp.detail}
                </p>
              </div>
            </div>
            {inset(rowKey(i))}
            {depth === 3 &&
              (groups.get(i) ?? []).map((p) => (
                <ParagraphRow
                  key={p.start}
                  paragraph={p}
                  inline={inline}
                  color={color}
                  now={nowRow === `para-${p.start}`}
                  onSeek={onSeek}
                  inset={inset(`para-${p.start}`)}
                />
              ))}
          </div>
        ))}

      {mobile && (
        <div className="row row--collapse row--toggle">
          <div className="row__gutter" />
          <div className="row__text">{toggleButton}</div>
        </div>
      )}
      {depth > 1 && depth !== globalDepth && (
        <div className="row row--collapse">
          <div className="row__gutter" />
          <div className="row__text">
            <button type="button" className="chapter__toggle" onClick={() => onDepth(1)}>
              <ChevronUp size={12} />
              {S.collapseToTitle}
            </button>
          </div>
        </div>
      )}
    </section>
  );
});

function ParagraphRow({
  paragraph,
  inline,
  color,
  now,
  onSeek,
  inset,
}: {
  paragraph: Paragraph;
  inline: Map<Quote, Paragraph>;
  color: string;
  now: boolean;
  onSeek: (s: number) => void;
  inset?: React.ReactNode;
}) {
  const quotes = [...inline.entries()].filter(([, p]) => p === paragraph).map(([q]) => q);
  const highlighted = quotes.length > 0;
  return (
    <>
      <div
        className={`row row--para ${highlighted ? 'row--para-marked' : ''}`}
        data-row={`para-${paragraph.start}`}
      >
        <div className="row__gutter">
          <Timecode
            seconds={paragraph.start}
            className={`${highlighted ? 'tc--chip' : ''} ${now ? 'tc--now' : ''}`}
            onSeek={onSeek}
          />
          <span className="dot dot--hollow" style={{ borderColor: color }} />
        </div>
        <div className="row__text">
          <p className="para">{renderWithMarks(paragraph, quotes, color)}</p>
        </div>
      </div>
      {inset}
    </>
  );
}

function renderWithMarks(paragraph: Paragraph, quotes: Quote[], color: string): React.ReactNode {
  const ranges = quotes
    .map((q) => findQuoteInParagraph(q, paragraph))
    .filter((r): r is [number, number] => r !== null)
    .sort((a, b) => a[0] - b[0]);
  if (ranges.length === 0) return paragraph.text;
  const out: React.ReactNode[] = [];
  let pos = 0;
  ranges.forEach(([a, b], i) => {
    if (a < pos) return;
    out.push(paragraph.text.slice(pos, a));
    out.push(
      <mark key={i} className="quote-mark" style={{ background: chapterTint(color) }}>
        {paragraph.text.slice(a, b)}
      </mark>,
    );
    pos = b;
  });
  out.push(paragraph.text.slice(pos));
  return out;
}

function QuoteCard({
  quote,
  objection,
  color,
  onSeek,
}: {
  quote: Quote;
  objection?: Objection;
  color: string;
  onSeek: (s: number) => void;
}) {
  return (
    <div className="mcard" style={{ borderColor: color }}>
      <div className="mcard__head" style={{ color }}>
        <span>{S.quote}</span>
        <button
          type="button"
          className="mcard__link"
          style={{ color }}
          onClick={() => onSeek(quote.start)}
        >
          <Play size={11} />
          <span className="tc tc--inline">{formatTimecode(quote.start)}</span>
        </button>
      </div>
      <p className="mcard__quote">«{quote.text.replace(/[.]$/u, '')}».</p>
      {quote.translation && <p className="mcard__translation">{quote.translation}</p>}
      {objection && <ObjectionBody objection={objection} withTop onSeek={onSeek} />}
    </div>
  );
}

function ObjectionCard({
  objection,
  onSeek,
}: {
  objection: Objection;
  onSeek: (s: number) => void;
}) {
  return (
    <div className="mcard mcard--objection">
      <ObjectionBody objection={objection} withClaim onSeek={onSeek} />
    </div>
  );
}

function ObjectionBody({
  objection,
  withTop,
  withClaim,
  onSeek,
}: {
  objection: Objection;
  withTop?: boolean;
  withClaim?: boolean;
  onSeek: (s: number) => void;
}) {
  return (
    <div className={`objection ${withTop ? 'objection--top' : ''}`}>
      <div className="objection__head">
        <span className="objection__label">
          <TriangleAlert size={11} />
          {S.objection}
        </span>
        {withClaim && <Timecode seconds={objection.start} className="tc--faint" onSeek={onSeek} />}
      </div>
      {withClaim && <p className="objection__claim">{objection.claim}</p>}
      <p className="objection__issue">{objection.issue}</p>
    </div>
  );
}
