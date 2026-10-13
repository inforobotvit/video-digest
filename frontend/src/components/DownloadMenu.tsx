import { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Download } from 'lucide-react';
import { EXPORT_FORMATS, type ExportFormat } from '@/api/types';
import { downloadExport } from '@/lib/exportFile';
import { S } from '@/strings';

/** «Скачать» button with the format menu (components c8). One download at a time. */
export function DownloadMenu({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const pick = async (format: ExportFormat) => {
    setOpen(false);
    setBusy(format);
    try {
      await downloadExport(jobId, format);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="dl" ref={root}>
      <button
        type="button"
        className={`btn btn--collapsible ${open ? 'btn--open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        disabled={busy !== null}
        aria-haspopup="menu"
        aria-expanded={open}
        title={busy ? S.preparing : S.download}
        aria-label={busy ? S.preparing : S.download}
      >
        <Download size={15} />
        <span className="btn__text">{busy ? S.preparing : S.download}</span>
        <span className="btn__text">
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </span>
      </button>
      {open && (
        <div className="dl__menu" role="menu">
          {EXPORT_FORMATS.map((f, i) => (
            <div key={f} className="dl__group">
              {i === EXPORT_FORMATS.length - 1 && <div className="dl__sep" />}
              <button type="button" role="menuitem" className="dl__item" onClick={() => pick(f)}>
                <span>{S.exportTitles[f]}</span>
                <span className="dl__ext">.{f.split('.').pop()}</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
