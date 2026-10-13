import type { Job, Stage, StageName } from '@/api/types';
import { S } from '@/strings';

export type Row = {
  name: Exclude<StageName, 'probe'>;
  status: Stage['status'];
  progress?: { done: number; total: number };
  /** ms for finished stages, live for the running one */
  ms: number | null;
  note: string | null;
};

/** The six visible rows: probe folds into download (brief 3.4). */
export function stageRows(job: Job, now: number): Row[] {
  const by = Object.fromEntries(job.stages.map((s) => [s.name, s])) as Partial<
    Record<StageName, Stage>
  >;
  const elapsed = Math.max(0, now - Date.parse(job.created_at));
  const doneMs = job.stages.reduce((a, s) => a + (s.ms ?? 0), 0);
  const blocks = extrasBlocks(job);
  const rows: Row[] = [];
  for (const name of ['download', 'transcribe', 'clean', 'digest', 'extras'] as const) {
    const st = by[name];
    if (!st) continue;
    let ms: number | null = null;
    if (st.status === 'done' || st.status === 'failed')
      ms = (st.ms ?? 0) + (name === 'download' ? (by.probe?.ms ?? 0) : 0);
    else if (st.status === 'running') ms = Math.max(0, elapsed - doneMs);
    let note: string | null = null;
    if (st.status === 'skipped') note = name === 'transcribe' ? S.hasSubtitles : S.notOrdered;
    else if (name === 'extras' && blocks.length) note = blocks.join(', ');
    rows.push({ name, status: st.status, progress: st.progress, ms, note });
  }
  return rows;
}

/** Chunked stages report progress after the first chunk; before that (split, chunking) the API
 *  sends no progress and the row says «подготовка». Download never has parts: nothing is shown. */
const CHUNKED = new Set<Row['name']>(['transcribe', 'clean', 'digest', 'extras']);
export function progressText(row: Row): string | null {
  if (row.status !== 'running') return null;
  if (row.progress && row.progress.total > 0)
    return S.stageProgress(row.progress.done, row.progress.total);
  return CHUNKED.has(row.name) ? S.stagePreparing : null;
}

/** Names of the extras blocks this job will produce, in the settings order (`options` is the full list). */
export function extrasBlocks(job: Job): string[] {
  const set = new Set<string>(job.options);
  return (['glossary', 'critique', 'self_check', 'decisions', 'action_items', 'questions'] as const)
    .filter((b) => set.has(b))
    .map((b) => S.optionLabels[b].title.toLowerCase());
}

/** "осталось около N минут" from the estimate minus elapsed; over the estimate → "чуть дольше обычного". */
export function remainingText(job: Job, now: number): string | null {
  if (job.estimate_sec === null) return null;
  const elapsed = (now - Date.parse(job.created_at)) / 1000;
  const left = job.estimate_sec - elapsed;
  if (left < 0) return S.longerThanUsual;
  if (left < 60) return S.remainingUnderMinute;
  return S.remaining(Math.round(left / 60));
}

/** `12 с`, `1:02`, `1:02:15` for stage durations. */
export function formatMs(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  if (total < 60) return `${total} с`;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`;
}
