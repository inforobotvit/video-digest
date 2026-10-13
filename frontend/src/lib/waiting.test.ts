import { describe, expect, it } from 'vitest';
import type { Job } from '@/api/types';
import { formatMs, progressText, remainingText, stageRows, type Row } from './waiting';

const base: Job = {
  job_id: 'j_1',
  status: 'processing',
  created_at: new Date(1_000_000).toISOString(),
  finished_at: null,
  estimate_sec: 480,
  preset: 'lecture',
  // `options` is the full list of blocks (2026-09-30): the preset adds none by itself.
  options: ['glossary', 'critique', 'self_check'],
  email: null,
  stages: [
    { name: 'probe', status: 'done', ms: 2000 },
    { name: 'download', status: 'done', ms: 10000 },
    { name: 'transcribe', status: 'running', progress: { done: 3, total: 7 } },
    { name: 'clean', status: 'pending' },
    { name: 'digest', status: 'pending' },
    { name: 'extras', status: 'pending' },
  ],
  source: {
    title: 't',
    duration_sec: 900,
    thumbnail_url: null,
    platform: 'youtube',
    language: 'ru',
    url: 'https://x',
  },
  result: null,
  error: null,
};

const plain = (s: string | null | undefined) => s?.replace(/[\u00a0\u202f]/g, ' ');

describe('stageRows', () => {
  it('folds probe into download, times the running stage live, notes skipped and extras', () => {
    const rows = stageRows(base, 1_000_000 + 62_000);
    expect(rows.map((r) => r.name)).toEqual([
      'download',
      'transcribe',
      'clean',
      'digest',
      'extras',
    ]);
    expect(rows[0].ms).toBe(12000);
    expect(rows[1].ms).toBe(50000); // 62 s elapsed minus 12 s of finished stages
    expect(plain(rows[4].note)).toBe('глоссарий, критика, вопросы для самопроверки');
  });
});

describe('remainingText', () => {
  it('counts down from the estimate and switches to "longer than usual"', () => {
    expect(remainingText(base, 1_000_000 + 60_000)).toBe('осталось около 7 минут');
    expect(remainingText(base, 1_000_000 + 450_000)).toBe('осталось меньше минуты');
    expect(remainingText(base, 1_000_000 + 500_000)).toBe('чуть дольше обычного');
    expect(remainingText({ ...base, estimate_sec: null }, 1_000_000)).toBeNull();
  });
});

describe('formatMs', () => {
  it('formats like the mockup', () => {
    expect(formatMs(12000)).toBe('12 с');
    expect(formatMs(62000)).toBe('1:02');
    expect(formatMs(3_735_000)).toBe('1:02:15');
  });
});

describe('progressText', () => {
  it('shows parts when known, «подготовка» before the first chunk, nothing for download', () => {
    const row = (name: Row['name'], progress?: { done: number; total: number }) => ({
      name,
      status: 'running' as const,
      progress,
      ms: 0,
      note: null,
    });
    expect(plain(progressText(row('transcribe', { done: 3, total: 7 })))).toBe('3 из 7 частей');
    expect(progressText(row('transcribe'))).toBe('подготовка');
    expect(progressText(row('clean', { done: 0, total: 0 }))).toBe('подготовка');
    expect(progressText(row('download'))).toBeNull();
    expect(progressText({ ...row('digest'), status: 'done' })).toBeNull();
  });
});
