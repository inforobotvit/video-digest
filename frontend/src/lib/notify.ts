import { useEffect, useRef, useSyncExternalStore } from 'react';
import type { Job } from '@/api/types';
import { S } from '@/strings';

/**
 * Browser notification when a job reaches done or failed while the tab is in the background.
 * The permission is requested once, from a soft in-page prompt on the waiting page, never from
 * the browser dialog alone; «Не надо», a dismissed dialog and a refusal are all remembered.
 */
const KEY = 'notify';
const listeners = new Set<() => void>();

type Permission = NotificationPermission | 'unsupported';

function permission(): Permission {
  return typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
}

function stored(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

function remember(value: 'asked' | 'off'): void {
  try {
    localStorage.setItem(KEY, value);
  } catch {
    /* storage blocked: the prompt may show again next time */
  }
  listeners.forEach((l) => l());
}

/** Whether the soft prompt should show: the browser still asks and we have not asked yet. */
export function shouldAsk(
  perm: Permission = permission(),
  local: string | null = stored(),
): boolean {
  return perm === 'default' && local === null;
}

export function canNotify(perm: Permission = permission()): boolean {
  return perm === 'granted';
}

/** «Разрешить»: opens the browser dialog (needs a click) and remembers that we asked. */
export async function allowNotifications(): Promise<void> {
  if (typeof Notification === 'undefined') return;
  try {
    await Notification.requestPermission();
  } catch {
    /* old callback-only API or a blocked dialog */
  }
  remember('asked');
}

/** «Не надо»: never ask again. */
export function declineNotifications(): void {
  remember('off');
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useShouldAsk(): boolean {
  return useSyncExternalStore(subscribe, () => shouldAsk());
}

/** Shows the notification; the click brings the tab back. Failures are silent. */
export function notifyFinished(job: Job): void {
  if (!canNotify()) return;
  const title = job.status === 'failed' ? S.notifyFailed : S.notifyDone;
  try {
    const n = new Notification(title, { body: job.source.title ?? '', tag: job.job_id });
    n.onclick = () => {
      window.focus();
      n.close();
    };
  } catch {
    /* some mobile browsers only notify through a service worker */
  }
}

/**
 * Fires once when a job we were waiting on finishes in a background tab. A job opened already
 * finished does not notify: there was nothing to wait for.
 */
export function useNotifyOnFinish(job: Job | null): void {
  const waited = useRef(false);
  const fired = useRef(false);
  useEffect(() => {
    if (!job) return;
    const finished = job.status === 'done' || job.status === 'failed';
    if (!finished) {
      waited.current = true;
      return;
    }
    if (waited.current && !fired.current && document.hidden) {
      fired.current = true;
      notifyFinished(job);
    }
  }, [job]);
}
