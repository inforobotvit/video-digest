import { dismiss, useToasts } from '@/lib/toast';
import './toasts.css';

/** Toast stack from components c11; sits above the player on the result page (body[data-player]). */
export function Toasts() {
  const toasts = useToasts();
  if (toasts.length === 0) return null;
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.action ? 'toast--action' : ''}`}>
          <span className={t.tone === 'error' ? 'toast__error' : undefined}>{t.text}</span>
          {t.action && (
            <button
              type="button"
              className="toast__btn"
              onClick={() => {
                dismiss(t.id);
                t.action?.run();
              }}
            >
              {t.action.label}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
