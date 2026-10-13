import { useCallback, useEffect, useRef, useState } from 'react';
import { MOCK } from '@/api/client';

/**
 * When the survey is offered (decisions of 2026-09-23 and 2026-09-30): 45 s after the result opened, only
 * after the person did something (scrolled or played), never on a failed job, once per job and not more than once
 * a day per browser. Closing without an answer is not an answer – the job stays unrated and «Оценить» works – but
 * it does silence the timer for a day: a person who just closed the form must not meet it again on the next job.
 * The «Оценить» button is always there and turns into thanks after an answer. localStorage may be unavailable:
 * then the timer never opens the form and the button stays.
 */
export const FEEDBACK_DELAY_MS = 45_000;
const DAY_MS = 24 * 60 * 60 * 1000;
const KEY_RATED = (jobId: string) => `feedback:rated:${jobId}`;
const KEY_SHOWN = (jobId: string) => `feedback:shown:${jobId}`;
const KEY_LAST = 'feedback:lastAnswered';
const KEY_DISMISSED = 'feedback:lastDismissed';

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export function isRated(jobId: string): boolean {
  return read(KEY_RATED(jobId)) === '1';
}
export function markRated(jobId: string): void {
  write(KEY_RATED(jobId), '1');
  write(KEY_LAST, String(Date.now()));
}
function withinDay(key: string, now: number): boolean {
  const last = Number(read(key));
  return Number.isFinite(last) && last > 0 && now - last < DAY_MS;
}
export function answeredWithinDay(now = Date.now()): boolean {
  return withinDay(KEY_LAST, now);
}
export function dismissedWithinDay(now = Date.now()): boolean {
  return withinDay(KEY_DISMISSED, now);
}
/** Closed without an answer: not an answer, but the timer keeps quiet for a day. */
export function markDismissed(): void {
  write(KEY_DISMISSED, String(Date.now()));
}
/** The timer may open the form: storage works, nothing shown for this job yet, no answer and no dismissal today. */
export function canAutoPrompt(jobId: string, now = Date.now()): boolean {
  if (!write('feedback:probe', '1')) return false;
  if (isRated(jobId) || read(KEY_SHOWN(jobId)) === '1') return false;
  return !answeredWithinDay(now) && !dismissedWithinDay(now);
}
export function markPromptShown(jobId: string): void {
  write(KEY_SHOWN(jobId), '1');
}

/** The mock lets e2e shorten the wait: /jobs/<id>?feedback_after=<ms>. The real build ignores the parameter. */
export function feedbackDelayMs(): number {
  if (!MOCK) return FEEDBACK_DELAY_MS;
  const v = Number(new URLSearchParams(window.location.search).get('feedback_after'));
  return Number.isFinite(v) && v > 0 ? v : FEEDBACK_DELAY_MS;
}

export interface FeedbackPrompt {
  open: boolean;
  via: 'timer' | 'button';
  rated: boolean;
  openManual: () => void;
  close: () => void;
  markAnswered: () => void;
}

/** `interacted` is true once the person scrolled or played; `done` only for a finished job with a result. */
export function useFeedbackPrompt(
  jobId: string,
  done: boolean,
  interacted: boolean,
): FeedbackPrompt {
  const [open, setOpen] = useState(false);
  const [via, setVia] = useState<'timer' | 'button'>('button');
  const [rated, setRated] = useState(() => isRated(jobId));
  const [elapsed, setElapsed] = useState(false);
  const fired = useRef(false);

  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => setElapsed(true), feedbackDelayMs());
    return () => clearTimeout(t);
  }, [jobId, done]);

  useEffect(() => {
    if (!done || !elapsed || !interacted || fired.current || rated) return;
    if (!canAutoPrompt(jobId)) return;
    fired.current = true;
    markPromptShown(jobId);
    setVia('timer');
    setOpen(true);
  }, [done, elapsed, interacted, rated, jobId]);

  const openManual = useCallback(() => {
    setVia('button');
    setOpen(true);
  }, []);
  const close = useCallback(() => {
    setOpen(false);
    if (!rated) markDismissed();
  }, [rated]);
  const markAnswered = useCallback(() => {
    markRated(jobId);
    setRated(true);
  }, [jobId]);
  return { open, via, rated, openManual, close, markAnswered };
}
