import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import { Star } from 'lucide-react';
import { api } from '@/api/client';
import { ApiError } from '@/api/types';
import { S } from '@/strings';
import './feedback.css';

const MAX = 500;
/** Controls in the tab order: the stars of a scale share one tab stop (roving tabindex), the rest are ordinary. */
const TABBABLE =
  'input:not([disabled]), textarea:not([disabled]), button:not([disabled]):not([tabindex="-1"])';

interface Props {
  open: boolean;
  jobId: string;
  via: 'timer' | 'button';
  rated: boolean;
  onClose: () => void;
  onAnswered: () => void;
}

/**
 * UMUX-Lite: two agreement statements on a 1..5 scale and an optional comment (step E2). A dialog that behaves:
 * Esc and a click outside close it, focus stays inside and returns where it was, everything reachable from the
 * keyboard. Closing without sending is not an answer. After an answer the same dialog shows thanks.
 */
export function FeedbackModal({ open, jobId, via, rated, onClose, onAnswered }: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const [fits, setFits] = useState<number | null>(null);
  const [easy, setEasy] = useState<number | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const before = document.activeElement as HTMLElement | null;
    const first = panel.current?.querySelector<HTMLElement>(TABBABLE);
    first?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== 'Tab' || !panel.current) return;
      const items = Array.from(panel.current.querySelectorAll<HTMLElement>(TABBABLE));
      if (!items.length) return;
      const a = items[0];
      const z = items[items.length - 1];
      if (e.shiftKey && document.activeElement === a) {
        e.preventDefault();
        z.focus();
      } else if (!e.shiftKey && document.activeElement === z) {
        e.preventDefault();
        a.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
      before?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  const t = S.feedback;
  const ready = fits !== null && easy !== null && !busy;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (fits === null || easy === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.sendFeedback({
        job_id: jobId,
        fits,
        easy,
        comment: comment.trim() || undefined,
        via,
      });
      onAnswered();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'already_rated') {
        onAnswered();
        return;
      }
      setError(t.failed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fb" role="dialog" aria-modal="true" aria-labelledby="fb-title">
      <button
        type="button"
        className="fb__overlay"
        onClick={onClose}
        aria-label={t.close}
        tabIndex={-1}
      />
      <div className="fb__panel" ref={panel}>
        {rated ? (
          <div className="fb__thanks">
            <h2 id="fb-title" className="fb__title">
              {t.thanksTitle}
            </h2>
            <p className="fb__text">{t.thanksText}</p>
            <button type="button" className="btn btn--primary" onClick={onClose}>
              {t.close}
            </button>
          </div>
        ) : (
          <form onSubmit={submit} className="fb__form">
            <h2 id="fb-title" className="fb__title">
              {t.title}
            </h2>
            <p className="fb__text">{t.intro}</p>
            <Stars name="fits" label={t.fits} value={fits} onChange={setFits} />
            <Stars name="easy" label={t.easy} value={easy} onChange={setEasy} />
            <label className="fb__field">
              <span className="fb__label">{t.comment}</span>
              <textarea
                className="fb__textarea"
                value={comment}
                maxLength={MAX}
                rows={3}
                onChange={(e) => setComment(e.target.value.slice(0, MAX))}
                aria-describedby="fb-comment-hint"
              />
              <span className="fb__row">
                <span id="fb-comment-hint" className="fb__hint">
                  {t.commentHint}
                </span>
                <span className="fb__counter mono" aria-live="polite">
                  {t.counter(comment.length, MAX)}
                </span>
              </span>
              <span className="fb__hint">{t.replyHint}</span>
            </label>
            {error && (
              <p className="fb__error" role="alert">
                {error}
              </p>
            )}
            <div className="fb__actions">
              <button type="submit" className="btn btn--primary" disabled={!ready}>
                {busy ? t.sending : t.send}
              </button>
              <button type="button" className="btn" onClick={onClose}>
                {t.skip}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

/**
 * Five stars for one agreement statement (step E4, sketch 2026-09-30-preset-list-and-umux-stars.html): a click on
 * the third lights the first three, hovering previews, the end captions keep the scale about agreement rather than
 * a product rating. A radiogroup: the stars are radios labelled 1–5 with a roving tabindex, arrows move the focus
 * (the outline shows where it is), Enter or Space choose. The value stored is the same 1–5.
 */
function Stars({
  name,
  label,
  value,
  onChange,
}: {
  name: string;
  label: string;
  value: number | null;
  onChange: (v: number) => void;
}) {
  const t = S.feedback;
  const [preview, setPreview] = useState<number | null>(null);
  const stars = useRef<(HTMLButtonElement | null)[]>([]);
  const shown = preview ?? value ?? 0;
  const focusStar = (n: number) => {
    const i = (((n - 1) % 5) + 5) % 5;
    stars.current[i]?.focus();
  };
  const onKey = (e: ReactKeyboardEvent, n: number) => {
    const next = {
      ArrowRight: n + 1,
      ArrowDown: n + 1,
      ArrowLeft: n - 1,
      ArrowUp: n - 1,
      Home: 1,
      End: 5,
    }[e.key];
    if (next === undefined) return; // Enter and Space: the button's own click
    e.preventDefault();
    focusStar(next);
  };
  return (
    <fieldset className="fb__scale">
      <legend className="fb__label">{label}</legend>
      <div className="fb__stars" role="radiogroup" aria-label={label} data-name={name}>
        <span className="fb__end fb__end--low">{t.scaleLow}</span>
        <span className="fb__starrow" onMouseLeave={() => setPreview(null)}>
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              ref={(el) => {
                stars.current[n - 1] = el;
              }}
              type="button"
              role="radio"
              aria-checked={value === n}
              aria-label={String(n)}
              tabIndex={n === (value ?? 1) ? 0 : -1}
              className={`fb__star ${n <= shown ? 'fb__star--on' : ''}`}
              onMouseEnter={() => setPreview(n)}
              onClick={() => onChange(n)}
              onKeyDown={(e) => onKey(e, n)}
            >
              <Star size={24} fill="currentColor" strokeWidth={0} aria-hidden="true" />
            </button>
          ))}
        </span>
        <span className="fb__end fb__end--high">{t.scaleHigh}</span>
      </div>
    </fieldset>
  );
}
