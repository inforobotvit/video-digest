import { useEffect, useRef, useState } from 'react';
import { api } from '@/api/client';
import { ApiError, type Job } from '@/api/types';
import { reportError } from '@/lib/reportError';

const FOREGROUND_MS = 3000;
const BACKGROUND_MS = 10000;

export type JobState =
  | { kind: 'loading' }
  | { kind: 'ready'; job: Job }
  | { kind: 'missing' }
  | { kind: 'error'; message: string };

/** Polls GET /api/jobs/{id} every 3 s (10 s in a background tab) until done or failed. */
export function useJob(id: string): JobState {
  const [state, setState] = useState<JobState>({ kind: 'loading' });
  const stopped = useRef(false);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    stopped.current = false;

    const schedule = () => {
      if (!alive || stopped.current) return;
      timer = setTimeout(tick, document.hidden ? BACKGROUND_MS : FOREGROUND_MS);
    };
    const tick = async () => {
      try {
        const job = await api.getJob(id);
        if (!alive) return;
        setState({ kind: 'ready', job });
        if (job.status === 'done' || job.status === 'failed') stopped.current = true;
      } catch (e) {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) {
          setState({ kind: 'missing' });
          stopped.current = true;
          return;
        }
        // Transient errors keep polling; the page shows the last known state.
        reportError('poll', e, { job_id: id });
        setState((s) =>
          s.kind === 'ready'
            ? s
            : { kind: 'error', message: e instanceof Error ? e.message : String(e) },
        );
      }
      schedule();
    };
    const onVisibility = () => {
      if (!document.hidden && !stopped.current) {
        clearTimeout(timer);
        void tick();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [id]);

  return state;
}

/** Ticks once a second while `active`, so live durations re-render. */
export function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}
