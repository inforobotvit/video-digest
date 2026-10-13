import { useSyncExternalStore } from 'react';
import type { Job } from '@/api/types';

/**
 * «Мои задачи»: the last ten jobs created from this browser, in localStorage only. Nothing here
 * goes to the server. A job is added when it is created and updated when its page is opened;
 * a job opened by someone else's link is never added.
 */
export type StoredStatus = 'processing' | 'done' | 'failed' | 'expired';
export interface StoredJob {
  id: string;
  title: string;
  /** ISO date of creation */
  created_at: string;
  status: StoredStatus;
}

const KEY = 'jobs';
const LIMIT = 10;
const listeners = new Set<() => void>();
let cache: StoredJob[] | null = null;

function read(): StoredJob[] {
  if (cache) return cache;
  try {
    const raw = localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    cache = Array.isArray(parsed) ? parsed.filter(isStoredJob).slice(0, LIMIT) : [];
  } catch {
    cache = [];
  }
  return cache;
}

function isStoredJob(v: unknown): v is StoredJob {
  const j = v as Partial<StoredJob> | null;
  return (
    !!j &&
    typeof j.id === 'string' &&
    typeof j.title === 'string' &&
    typeof j.created_at === 'string' &&
    (j.status === 'processing' ||
      j.status === 'done' ||
      j.status === 'failed' ||
      j.status === 'expired')
  );
}

function write(next: StoredJob[]): void {
  cache = next.slice(0, LIMIT);
  try {
    localStorage.setItem(KEY, JSON.stringify(cache));
  } catch {
    /* storage blocked or full: the list lives for this page only */
  }
  listeners.forEach((l) => l());
}

export function listJobs(): StoredJob[] {
  return read();
}

/** Adds a freshly created job to the top of the list (or moves it there). */
export function rememberJob(job: Omit<StoredJob, 'status'> & { status?: StoredStatus }): void {
  const entry: StoredJob = { status: 'processing', ...job };
  write([entry, ...read().filter((j) => j.id !== job.id)]);
}

/** Refreshes title and status of a job that is already in the list; unknown jobs are ignored. */
export function updateJob(id: string, patch: Partial<Omit<StoredJob, 'id'>>): void {
  const jobs = read();
  const i = jobs.findIndex((j) => j.id === id);
  if (i < 0) return;
  const next = { ...jobs[i], ...patch };
  if (Object.keys(patch).every((k) => next[k as keyof StoredJob] === jobs[i][k as keyof StoredJob]))
    return;
  write(jobs.map((j, k) => (k === i ? next : j)));
}

export function forgetJob(id: string): void {
  const jobs = read();
  if (!jobs.some((j) => j.id === id)) return;
  write(jobs.filter((j) => j.id !== id));
}

/** The status word for the list, from a job the API returned. */
export function storedStatus(job: Job): StoredStatus {
  if (job.status === 'failed') return 'failed';
  if (job.status === 'done') return job.result ? 'done' : 'expired';
  return 'processing';
}

function subscribe(l: () => void) {
  listeners.add(l);
  // Another tab changed the list: drop the cache and re-render.
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY || e.key === null) {
      cache = null;
      l();
    }
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(l);
    window.removeEventListener('storage', onStorage);
  };
}

export function useStoredJobs(): StoredJob[] {
  return useSyncExternalStore(subscribe, read);
}
