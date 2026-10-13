import { useRef, useState } from 'react';
import { Link2, Upload, X } from 'lucide-react';
import { S } from '@/strings';
import type { Limits } from '@/api/types';

export type LinkState =
  | { kind: 'empty' }
  | { kind: 'ready'; url: string }
  | { kind: 'checking'; url: string }
  | { kind: 'uploading'; name: string; size: number; fraction: number }
  | { kind: 'error'; url: string; code: string; stage: string; maxDurationSec?: number }
  | { kind: 'probed'; url: string };

interface Props {
  state: LinkState;
  /** from GET /api/limits; null until it answers – the numbers are then simply not printed */
  limits?: Limits | null;
  onChange: (url: string) => void;
  onSubmit: () => void;
  onFile: (file: File) => void;
  onEdit: () => void;
  onCancelUpload?: () => void;
}

const ACCEPT = '.mp4,.mov,.mkv,.webm,.mp3,.m4a,.wav,.ogg,.flac';

/** The composite row from mockup 3.1 / component c1: link field, "or upload a file" zone, action. */
export function LinkInput({
  state,
  limits,
  onChange,
  onSubmit,
  onFile,
  onEdit,
  onCancelUpload,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const url = state.kind === 'empty' || state.kind === 'uploading' ? '' : state.url;
  const locked = state.kind === 'checking' || state.kind === 'probed' || state.kind === 'uploading';
  const cls = ['link', `link--${state.kind}`, drag ? 'link--drag' : ''].join(' ');

  const pick = () => fileRef.current?.click();
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  };

  return (
    <div
      className={cls}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
    >
      {drag && (
        <div className="link__drop">
          <Upload size={16} />
          {S.dropHere} · <span className="sources__mono">{S.formats}</span>
          {limits && <> · {S.maxSize(limits.upload_max_mb)}</>}
        </div>
      )}
      {!drag && state.kind === 'uploading' && (
        <div className="link__uploading">
          <Upload size={16} className="link__icon" />
          <span className="link__filename">{state.name}</span>
          <span className="mono link__size">{formatSize(state.size)}</span>
          <span className="link__bar">
            <span
              className="link__bar-fill"
              style={{ width: `${Math.round(state.fraction * 100)}%` }}
            />
          </span>
          <span className="mono link__percent">{Math.round(state.fraction * 100)}%</span>
          <button
            type="button"
            className="link__clear"
            onClick={onCancelUpload}
            aria-label={S.cancelUpload}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {!drag && state.kind !== 'uploading' && (
        <>
          <div className="link__field">
            <Link2 size={18} className="link__icon" />
            <input
              type="url"
              inputMode="url"
              className="link__input"
              placeholder={S.linkPlaceholder}
              value={url}
              disabled={locked}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && state.kind === 'ready') onSubmit();
              }}
              aria-label={S.linkPlaceholder}
            />
            {url && !locked && (
              <button
                type="button"
                className="link__clear"
                onClick={() => onChange('')}
                aria-label={S.clearLink}
              >
                <X size={15} />
              </button>
            )}
          </div>
          {state.kind === 'empty' && (
            <button type="button" className="link__upload" onClick={pick} title={S.orUpload}>
              <Upload size={15} />
              <span className="link__upload-text">{S.orUpload}</span>
            </button>
          )}
          {state.kind === 'empty' && (
            <button type="button" className="link__action link__action--idle" disabled>
              {S.continue}
            </button>
          )}
          {state.kind === 'ready' && (
            <button type="button" className="link__action link__action--primary" onClick={onSubmit}>
              {S.continue}
            </button>
          )}
          {state.kind === 'checking' && (
            <button
              type="button"
              className="link__action link__action--primary link__action--busy"
              disabled
            >
              <span className="link__progress" />
              <span className="link__action-text">{S.checking}</span>
            </button>
          )}
          {(state.kind === 'error' || state.kind === 'probed') && (
            <button type="button" className="link__action link__action--secondary" onClick={onEdit}>
              {S.changeLink}
            </button>
          )}
        </>
      )}
      <input
        ref={fileRef}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
      />
    </div>
  );
}

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${Math.round(mb)} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`;
}

/** Supported sources, formats and – once GET /api/limits answered – the size and duration ceilings. */
export function SourcesLine({ limits }: { limits: Limits | null }) {
  return (
    <div className="sources">
      {S.sources.map((s, i) => (
        <span key={s}>
          {i > 0 && <span className="sources__dot">·</span>}
          {s}
        </span>
      ))}
      <span className="sources__dot">·</span>
      <span className="sources__mono">{S.formats}</span>
      {limits && (
        <>
          <span className="sources__dot">·</span>
          <span>{S.maxSize(limits.upload_max_mb)}</span>
          <span className="sources__dot">·</span>
          <span>{S.maxDuration(Math.round(limits.max_duration_sec / 60))}</span>
        </>
      )}
    </div>
  );
}

export function ProbeErrorBanner({
  code,
  maxDurationSec,
  uploadMaxMb,
  onUpload,
}: {
  code: string;
  maxDurationSec?: number;
  /** from GET /api/limits, for file_too_large */
  uploadMaxMb?: number | null;
  onUpload: () => void;
}) {
  // too_long takes its limit from the response, file_too_large from GET /api/limits (contract section 6): no
  // number here is a constant of the front.
  const t =
    code === 'too_long'
      ? S.probeTooLong(maxDurationSec ? Math.round(maxDurationSec / 60) : null)
      : code === 'file_too_large'
        ? S.fileTooLarge(uploadMaxMb ?? null)
        : (S.probeErrors[code] ?? S.probeErrors.generic);
  const offersUpload = code === 'private_or_removed' || code === 'bot_check';
  return (
    <div className="banner" role="alert">
      <span className="banner__icon" aria-hidden />
      <div className="banner__body">
        <b>{t.title}</b> {t.text}
        {offersUpload && (
          <div className="banner__actions">
            <button type="button" className="btn btn--primary btn--banner" onClick={onUpload}>
              <Upload size={14} />
              {S.uploadFile}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
