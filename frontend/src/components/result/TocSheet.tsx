import { useEffect } from 'react';
import type { VideoDigestResult } from '@/types/result';
import type { Chapter, Depth } from '@/lib/digest';
import { formatDuration, formatTimecode } from '@/lib/timecode';
import { S } from '@/strings';
import { Cover } from './Sidebar';
import { ExtrasNav, Toc } from './Toc';

interface Props {
  open: boolean;
  onClose: () => void;
  result: VideoDigestResult;
  chapters: Chapter[];
  depths: Depth[];
  reading: number;
  time: number;
  current: number;
  mark: boolean;
  onPick: (index: number) => void;
}

/**
 * Bottom sheet with the table of contents on mobile (turn 4c): source card, the axis with depth
 * thickness, the reading position and the player mark, «Дополнительно». Opens from the chapter chip in the sticky bar;
 * picking an item closes it and the hash link scrolls the page.
 */
export function TocSheet({
  open,
  onClose,
  result,
  chapters,
  depths,
  reading,
  time,
  current,
  mark,
  onPick,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;
  const src = result.source;
  const processed =
    (Date.parse(result.meta.finished_at) - Date.parse(result.meta.created_at)) / 1000;
  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label={S.toc}>
      <button type="button" className="sheet__overlay" onClick={onClose} aria-label={S.close} />
      <div className="sheet__panel">
        <button type="button" className="sheet__handle" onClick={onClose} aria-label={S.close} />
        <div className="sheet__source">
          <Cover url={src.thumbnail_url} className="sheet__cover" />
          <div className="sheet__body">
            <div className="sheet__title">{src.title}</div>
            <div className="sheet__meta mono">
              {formatTimecode(src.duration_sec)} · {S.platforms[src.platform] ?? src.platform} ·{' '}
              {src.language.toUpperCase()}
              {Number.isFinite(processed) && processed > 0 && ` · ${formatDuration(processed)}`}
            </div>
          </div>
        </div>
        <div className="eyebrow sheet__eyebrow">{S.structure}</div>
        <Toc
          chapters={chapters}
          depths={depths}
          reading={reading}
          time={time}
          current={current}
          mark={mark}
          onPick={(index) => {
            onPick(index);
            onClose();
          }}
        />
        <ExtrasNav result={result} onPick={onClose} />
      </div>
    </div>
  );
}
