import { ChevronDown } from 'lucide-react';
import type { VideoDigestResult } from '@/types/result';
import { type Chapter, type Depth, wordCount } from '@/lib/digest';
import { chapterColor } from '@/lib/chapterColors';
import { S } from '@/strings';

interface Props {
  depth: Depth;
  overrides: ReadonlyMap<number, Depth>;
  result: VideoDigestResult;
  chapters: Chapter[];
  /** index of the chapter the player is in; the mobile chip shows it */
  /** index of the chapter being read: the chip opens the table of contents at it */
  reading: number;
  onChange: (d: Depth) => void;
  onReset: () => void;
  /** mobile (turn 4): the chapter chip opens the table of contents sheet */
  onOpenToc: () => void;
}

export function DepthBar({
  depth,
  overrides,
  result,
  chapters,
  reading,
  onChange,
  onReset,
  onOpenToc,
}: Props) {
  const hint =
    depth === 1
      ? S.depthHint1
      : depth === 2
        ? S.depthHint5(result.digest.key_points.length)
        : S.depthHintAll(wordCount(result.transcript.clean));
  const changed = [...overrides.entries()].filter(([, d]) => d !== depth);
  const deeper = changed.every(([, d]) => d > depth);
  const first = changed[0];
  const color = first ? chapterColor(first[0]) : undefined;
  const chapter = chapters[reading] ?? chapters[0];
  const labels: Record<Depth, [string, string]> = {
    1: [S.depth1, S.depth1Short],
    2: [S.depth5, S.depth5Short],
    3: [S.depthAll, S.depthAll],
  };
  return (
    <div className="depth">
      <div className="depth__left">
        <span className="depth__label">{S.depth}</span>
        <div className="depth__switch" role="tablist" aria-label={S.depth}>
          {([1, 2, 3] as Depth[]).map((d) => (
            <button
              key={d}
              type="button"
              role="tab"
              aria-selected={d === depth}
              className={`depth__opt ${d === depth ? 'depth__opt--on' : ''}`}
              onClick={() => onChange(d)}
            >
              <span className="depth__long">{labels[d][0]}</span>
              <span className="depth__short">{labels[d][1]}</span>
            </button>
          ))}
        </div>
        <span className="depth__hint">{hint}</span>
      </div>
      {chapter && (
        <button type="button" className="depth__chapter" onClick={onOpenToc} aria-label={S.toc}>
          <span className="depth__swatch" style={{ background: chapterColor(chapter.index) }} />
          <span className="depth__chapter-title">{chapter.part.title}</span>
          <ChevronDown size={13} />
        </button>
      )}
      {changed.length > 0 && (
        <div className="depth__override" style={{ color }}>
          <span className="depth__bar" style={{ background: color }} />
          {deeper ? S.chaptersDeeper(changed.length) : S.chaptersOverridden(changed.length)}
          <button type="button" className="depth__reset" onClick={onReset}>
            {S.reset}
          </button>
        </div>
      )}
    </div>
  );
}
