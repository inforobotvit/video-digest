import { typo } from '@/lib/typo';
import { Bell, Check, Link2, Minus, RefreshCw, TriangleAlert, X } from 'lucide-react';
import type { Job } from '@/api/types';
import { useNow } from '@/lib/usePolling';
import {
  extrasBlocks,
  formatMs,
  progressText,
  remainingText,
  stageRows,
  type Row,
} from '@/lib/waiting';
import { formatTimecode } from '@/lib/timecode';
import { languageName } from '@/lib/settings';
import { shareLink } from '@/lib/exportFile';
import { listJobs } from '@/lib/jobsStore';
import { allowNotifications, declineNotifications, useShouldAsk } from '@/lib/notify';
import { S } from '@/strings';
import './job.css';

/** Compact source card for the waiting page (mockup 3.4): title, meta, preset and blocks. */
export function JobCard({ job }: { job: Job }) {
  const blocks = extrasBlocks(job);
  return (
    <div className="jcard">
      {job.source.thumbnail_url ? (
        <img className="jcard__cover" src={job.source.thumbnail_url} alt="" />
      ) : (
        <div className="jcard__cover" />
      )}
      <div className="jcard__body">
        <div className="jcard__title" title={job.source.title ?? S.expiredJobTitle}>
          {typo(job.source.title ?? S.expiredJobTitle)}
        </div>
        <div className="jcard__meta">
          <span className="mono">{formatTimecode(job.source.duration_sec)}</span>
          <span className="jcard__dot">·</span>
          <span>{S.platforms[job.source.platform] ?? job.source.platform}</span>
          <span className="jcard__dot">·</span>
          <span>{languageName(job.source.language)}</span>
          <span className="jcard__dot">·</span>
          <span>
            {S.presetNames[job.preset]}
            {blocks.length > 0 && ` · ${blocks.join(', ')}`}
          </span>
        </div>
      </div>
    </div>
  );
}

export function WaitingView({ job }: { job: Job }) {
  const now = useNow(job.status === 'queued' || job.status === 'processing');
  const rows = stageRows(job, now);
  const remaining = remainingText(job, now);
  return (
    <>
      <div className="wait__head">
        <h2 className="wait__title">{S.processing}</h2>
        {remaining && <span className="wait__remaining">{remaining}</span>}
      </div>
      <div className="stages">
        {rows.map((r) => (
          <StageRow key={r.name} row={r} />
        ))}
      </div>
      <p className="wait__note">
        {S.canClose} {S.saveLink}
      </p>
      <button
        type="button"
        className="btn btn--job wait__copy"
        onClick={() => void shareLink(job.job_id)}
      >
        <Link2 size={14} />
        {S.copyLink}
      </button>
      <NotifyPrompt job={job} />
    </>
  );
}

/**
 * Soft prompt for browser notifications: one line, shown once, only for jobs started from this
 * browser (jobsStore). «Разрешить» opens the browser dialog; either answer hides the line for good.
 */
function NotifyPrompt({ job }: { job: Job }) {
  const ask = useShouldAsk();
  if (!ask || !listJobs().some((j) => j.id === job.job_id)) return null;
  return (
    <p className="wait__notify">
      <Bell size={13} />
      <span>{S.notifyAsk}</span>
      <button type="button" className="wait__notify-btn" onClick={() => void allowNotifications()}>
        {S.notifyAllow}
      </button>
      <span className="wait__notify-dot">·</span>
      <button type="button" className="wait__notify-btn" onClick={declineNotifications}>
        {S.notifyDecline}
      </button>
    </p>
  );
}

function StageRow({ row }: { row: Row }) {
  const name = S.stageNames[row.name];
  const cls = `stage stage--${row.status}`;
  const progress = progressText(row);
  return (
    <div className={cls}>
      <span className="stage__mark">
        {row.status === 'done' && <Check size={11} strokeWidth={3} />}
        {row.status === 'running' && <span className="stage__pulse" />}
        {row.status === 'failed' && <X size={11} strokeWidth={2.5} />}
        {row.status === 'skipped' && <Minus size={12} />}
      </span>
      <span className="stage__name">
        {name}
        {progress && <span className="stage__progress"> · {progress}</span>}
        {row.status !== 'skipped' && row.status !== 'failed' && row.note && (
          <span className="stage__note"> · {row.note}</span>
        )}
        {row.status === 'failed' && <span className="stage__soft">{S.stageFailedSoft}</span>}
      </span>
      <span className="stage__right">
        {row.status === 'skipped' && <span className="stage__skipped">{row.note}</span>}
        {row.status === 'failed' && <span className="mono stage__code">{row.name} · failed</span>}
        {(row.status === 'done' || row.status === 'running') && row.ms !== null && (
          <span className={`mono ${row.status === 'running' ? 'stage__ms--live' : 'stage__ms'}`}>
            {formatMs(row.ms)}
          </span>
        )}
      </span>
    </div>
  );
}

interface ErrorProps {
  job: Job;
  onRetry: () => void;
  onOther: () => void;
  retrying: boolean;
  retryError: string | null;
}

/** Job failed (mockup 3c): what happened, what to do, retry and start over. */
export function JobErrorView({ job, onRetry, onOther, retrying, retryError }: ErrorProps) {
  const err = job.error ?? { stage: 'pipeline', code: 'generic', message: '' };
  const t = S.jobErrors[err.code] ?? S.jobErrors.generic;
  const stage = job.stages.find((s) => s.name === err.stage);
  const stageName =
    stage && stage.name !== 'probe' ? S.stageNames[stage.name as keyof typeof S.stageNames] : null;
  // The live API reports a failed stage with progress 0/0; the part only makes sense when there were parts.
  const progress = stage?.progress && stage.progress.total > 0 ? stage.progress : null;
  const where = stageName
    ? S.stoppedAt(stageName) +
      (progress ? S.stoppedAtPart(progress.done, progress.total) + '.' : '.')
    : '';
  return (
    <div className="jerr">
      <span className="jerr__icon">
        <TriangleAlert size={16} />
      </span>
      <div className="jerr__body">
        <h2 className="jerr__title">{t.title}</h2>
        <p className="jerr__text">
          {where} {t.text}
        </p>
        <div className="jerr__actions">
          {t.retry !== false && (
            <button
              type="button"
              className="btn btn--primary btn--job"
              onClick={onRetry}
              disabled={retrying}
            >
              <RefreshCw size={14} />
              {retrying ? S.retrying : S.retry}
            </button>
          )}
          <button type="button" className="btn btn--job" onClick={onOther} disabled={retrying}>
            {S.otherVideoBtn}
          </button>
          <span className="jerr__code mono">{job.job_id}</span>
        </div>
        {retryError && <div className="settings__error">{retryError}</div>}
      </div>
    </div>
  );
}
