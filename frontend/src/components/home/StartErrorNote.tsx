import { RefreshCw } from 'lucide-react';
import { S } from '@/strings';
import type { StartError } from '@/lib/startError';

export function StartErrorNote({
  error,
  onRetry,
}: {
  error?: StartError | null;
  onRetry: () => void;
}) {
  if (!error) return null;
  return (
    <div className="settings__error" role="alert">
      <span>{error.text}</span>
      {error.retry && (
        <button type="button" className="btn btn--banner settings__retry" onClick={onRetry}>
          <RefreshCw size={14} />
          {S.retryNow}
        </button>
      )}
    </div>
  );
}
