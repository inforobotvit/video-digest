import { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { S } from '@/strings';
import { languageName } from '@/lib/settings';

interface Props {
  value: string;
  /** the video's own language gets a "язык видео" hint (component c6) */
  sourceLanguage?: string;
  onChange: (code: string) => void;
  className?: string;
  label: string;
}

/** Language dropdown from component c6: a button and a list, keyboard and click-outside aware. */
export function LanguageSelect({ value, sourceLanguage, onChange, className, label }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);
  return (
    <div className={`lsel ${className ?? ''}`} ref={root}>
      <button
        type="button"
        className={`lsel__btn ${open ? 'lsel__btn--open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label}
      >
        {languageName(value)}
        <ChevronDown size={14} />
      </button>
      {open && (
        <ul className="lsel__list" role="listbox" aria-label={label}>
          {Object.entries(S.languages).map(([code, name]) => (
            <li
              key={code}
              role="option"
              aria-selected={code === value}
              className={`lsel__item ${code === value ? 'lsel__item--on' : ''}`}
              onClick={() => {
                onChange(code);
                setOpen(false);
              }}
            >
              {name}
              {code === value ? (
                <Check size={14} />
              ) : code === sourceLanguage ? (
                <span className="lsel__hint">{S.videoLanguage}</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
