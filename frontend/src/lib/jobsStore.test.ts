// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { forgetJob, listJobs, rememberJob, updateJob } from './jobsStore';

const entry = (n: number) => ({ id: `j_${n}`, title: `Видео ${n}`, created_at: `2026-09-0${n}` });

describe('jobsStore', () => {
  beforeEach(() => {
    localStorage.clear();
    for (const j of listJobs()) forgetJob(j.id);
  });

  it('keeps the last ten, newest first', () => {
    for (let n = 1; n <= 12; n++) rememberJob({ ...entry(n), created_at: `2026-09-${n}` });
    const jobs = listJobs();
    expect(jobs).toHaveLength(10);
    expect(jobs[0].id).toBe('j_12');
    expect(jobs[9].id).toBe('j_3');
    expect(jobs[0].status).toBe('processing');
    expect(JSON.parse(localStorage.getItem('jobs') ?? '[]')).toHaveLength(10);
  });

  it('updates only jobs it knows and removes on request', () => {
    rememberJob(entry(1));
    updateJob('j_1', { status: 'done', title: 'Новое название' });
    updateJob('j_9', { status: 'done' });
    expect(listJobs()).toEqual([
      { id: 'j_1', title: 'Новое название', created_at: '2026-09-01', status: 'done' },
    ]);
    forgetJob('j_1');
    expect(listJobs()).toEqual([]);
  });

  it('re-creating a job moves it to the top instead of duplicating', () => {
    rememberJob(entry(1));
    rememberJob(entry(2));
    rememberJob(entry(1));
    expect(listJobs().map((j) => j.id)).toEqual(['j_1', 'j_2']);
  });
});
