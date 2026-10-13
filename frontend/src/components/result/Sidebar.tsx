import { useState } from 'react';
import type { Job } from '@/api/types';
import type { VideoDigestResult } from '@/types/result';
import type { Chapter, Depth } from '@/lib/digest';
import { formatDuration, formatTimecode } from '@/lib/timecode';
import { S } from '@/strings';
import { ExtrasNav, Toc } from './Toc';

interface Props {
  job: Job;
  result: VideoDigestResult;
  chapters: Chapter[];
  depths: Depth[];
  /** index of the chapter being read */
  reading: number;
  /** player position, seconds */
  time: number;
  /** index of the chapter the player is in */
  current: number;
  /** the player has started: its mark is on the axis */
  mark: boolean;
  onPick: (index: number) => void;
}

export function Sidebar({ result, chapters, depths, reading, time, current, mark, onPick }: Props) {
  const src = result.source;
  const processed =
    (Date.parse(result.meta.finished_at) - Date.parse(result.meta.created_at)) / 1000;
  const languageName = S.languages[src.language] ?? src.language.toUpperCase();
  const marked = mark && chapters[current] !== undefined;

  return (
    <aside className="side">
      <div className="side__source">
        <Cover url={src.thumbnail_url} />
        <div className="side__title" title={src.title}>
          {src.title}
        </div>
        <div className="side__meta">
          <span className="mono">{formatTimecode(src.duration_sec)}</span>
          <span>{S.platforms[src.platform] ?? src.platform}</span>
          <span>{languageName}</span>
          <span>{S.presets[result.preset]}</span>
        </div>
        {Number.isFinite(processed) && processed > 0 && (
          <div className="side__processed">{S.processedIn(formatDuration(processed))}</div>
        )}
      </div>

      <Toc
        chapters={chapters}
        depths={depths}
        reading={reading}
        time={time}
        current={current}
        mark={mark}
        onPick={onPick}
      />
      <div className="side__legend">
        <div className="side__legend-row">
          <span className="side__legend-swatch" />
          {S.axisLegend}
        </div>
        {marked && (
          <div className="side__legend-row">
            <span className="side__legend-line" />
            {S.playerLegend} · <span className="mono">{formatTimecode(time)}</span>
          </div>
        )}
      </div>

      <ExtrasNav result={result} />
    </aside>
  );
}

/** Thumbnail with a neutral placeholder when the URL is missing or fails to load (brief: no fake covers). */
export function Cover({
  url,
  className = 'side__cover',
}: {
  url: string | null;
  className?: string;
}) {
  const [broken, setBroken] = useState(false);
  if (!url || broken) return <div className={`${className} ${className}--empty`} />;
  return <img className={className} src={url} alt="" onError={() => setBroken(true)} />;
}
