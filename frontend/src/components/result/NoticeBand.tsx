import { useState } from 'react';
import { S } from '@/strings';
import type { VideoDigestResult } from '@/types/result';
import { Timecode } from './Timecode';

export type Notice = NonNullable<VideoDigestResult['notices']>[number];

/**
 * result.notices as the reader sees them (result-schema section 2): a quiet band next to the document –
 * the transcript may have been shortened, or part of it was cleaned by rules without the model. Number
 * and places only; the places are timecodes that seek the player like every other timecode on the page.
 * Not a modal, not a red banner: an honest caveat, not an incident.
 */
export function NoticeBand({
  notices,
  onSeek,
}: {
  notices?: Notice[];
  onSeek: (seconds: number) => void;
}) {
  if (!notices?.length) return null;
  return (
    <section className="notices" aria-label={S.notices.label}>
      {notices.map((n) => (
        <NoticeItem key={n.kind} notice={n} onSeek={onSeek} />
      ))}
    </section>
  );
}

function NoticeItem({ notice, onSeek }: { notice: Notice; onSeek: (seconds: number) => void }) {
  const [open, setOpen] = useState(false);
  const text = S.notices[notice.kind];
  const capped = notice.starts.length < notice.places;
  return (
    <div className={`notice notice--${notice.kind}`}>
      <p className="notice__text">
        <strong className="notice__title">{text.title}.</strong> {text.body(notice.places)}{' '}
        {notice.starts.length > 0 && (
          <button
            type="button"
            className="notice__toggle"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? S.notices.hide : S.notices.show}
          </button>
        )}
      </p>
      {open && (
        <div className="notice__places">
          {notice.starts.map((t) => (
            <Timecode key={t} seconds={t} className="tc--inline" onSeek={onSeek} />
          ))}
          {capped && (
            <span className="notice__capped">
              {S.notices.capped(notice.starts.length, notice.places)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
