import { useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import type { VideoDigestResult } from '@/types/result';
import type { Chapter, Depth } from '@/lib/digest';
import { chapterColor } from '@/lib/chapterColors';
import { formatTimecode } from '@/lib/timecode';
import { extrasNav } from '@/lib/extras';
import { S } from '@/strings';

interface TocProps {
  chapters: Chapter[];
  depths: Depth[];
  /** index of the chapter being read (scrollspy) – the primary position on the axis */
  reading: number;
  /** player position, seconds */
  time: number;
  /** index of the chapter the player is in */
  current: number;
  /** show the player mark (only after the first play or seek) */
  mark: boolean;
  /** a chapter was picked: the caller pins the reading position and closes the sheet on mobile */
  onPick?: (index: number) => void;
}

/**
 * The document axis: one item per chapter, height proportional to its length, bar thickness
 * following the reading depth. Two positions: the chapter being read is highlighted (label,
 * a ring around its segment), the player is a line with a pointer across the bar, shown once the
 * player has started. Shared by the desktop sidebar and the mobile sheet (turn 4c).
 */
export function Toc({ chapters, depths, reading, time, current, mark, onPick }: TocProps) {
  const items = useRef<(HTMLAnchorElement | null)[]>([]);
  const [markTop, setMarkTop] = useState<number | null>(null);

  useLayoutEffect(() => {
    const chapter = chapters[current];
    const el = items.current[current];
    if (!mark || !chapter || !el) {
      setMarkTop(null);
      return;
    }
    const f = chapter.seconds > 0 ? (time - chapter.part.start) / chapter.seconds : 0;
    setMarkTop(el.offsetTop + Math.min(1, Math.max(0, f)) * el.offsetHeight);
  }, [chapters, current, time, depths, mark]);

  return (
    <nav className="toc" aria-label={S.toc}>
      {markTop !== null && <span className="toc__mark" style={{ top: markTop }} aria-hidden />}
      {chapters.map((c) => {
        const depth = depths[c.index];
        const read = c.index === reading;
        return (
          <a
            key={c.index}
            ref={(el) => {
              items.current[c.index] = el;
            }}
            href={`#chapter-${c.index}`}
            className={`toc__item ${depth > 1 || read ? 'toc__item--deep' : ''} ${read ? 'toc__item--read' : ''}`}
            style={
              { flexGrow: Math.max(c.seconds, 1), '--c': chapterColor(c.index) } as CSSProperties
            }
            aria-current={read ? 'true' : undefined}
            onClick={() => onPick?.(c.index)}
          >
            <span className="toc__axis">
              <span className={`toc__bar toc__bar--d${depth}`} />
            </span>
            <span className="toc__label">
              <span className="toc__time">{formatTimecode(c.part.start)}</span> {c.part.title}
            </span>
          </a>
        );
      })}
    </nav>
  );
}

/** «Дополнительно»: anchors to the extras sections with their counts. */
export function ExtrasNav({ result, onPick }: { result: VideoDigestResult; onPick?: () => void }) {
  const extras = extrasNav(result);
  if (extras.length === 0) return null;
  return (
    <div className="side__extras">
      <div className="eyebrow">{S.extras}</div>
      <div className="side__extras-list">
        {extras.map((e) => (
          <a key={e.key} href={`#extras-${e.key}`} className="side__extras-item" onClick={onPick}>
            <span>{e.title}</span>
            <span className="side__extras-count">{e.count}</span>
          </a>
        ))}
      </div>
    </div>
  );
}
