import type { CreateJobRequest, Job, Stage, StageName } from './types';
import { S } from '@/strings';
import type { VideoDigestResult } from '@/types/result';
import sample from '@fixtures/result-sample.json';

/**
 * In-memory jobs for the mock: stages advance on a timer the way the fake n8n pipeline did
 * (3 / 8 / 5 / 4 / 3 s). Scenarios come from the source URL used at creation:
 * `fail` → stt_failed on transcribe, `extrasfail` → extras failed but the job completes,
 * `subs` → transcribe skipped. Any other job is served from the fixtures by id.
 */
interface MockJob {
  job: Job;
  scenario: { fail: boolean; extrasFail: boolean; subs: boolean; notices: boolean };
  timer?: ReturnType<typeof setTimeout>;
}
const jobs = new Map<string, MockJob>();
let counter = 0;

const ORDER: StageName[] = ['probe', 'download', 'transcribe', 'clean', 'digest', 'extras'];
const DELAY: Record<StageName, number> = {
  probe: 0,
  download: 3000,
  transcribe: 8000,
  clean: 5000,
  digest: 4000,
  extras: 3000,
};
export function mockStartJob(
  body: CreateJobRequest,
  sourceUrl: string | null,
  probeTitle: string,
  thumbnail: string | null,
  durationSec: number,
  estimateSec: number,
): Job {
  counter += 1;
  const id = `j_mock${counter}`;
  const u = (sourceUrl ?? '').toLowerCase();
  const scenario = {
    fail: u.includes('fail') && !u.includes('extrasfail'),
    extrasFail: u.includes('extrasfail'),
    subs: u.includes('subs'),
    notices: u.includes('notices'),
  };
  // The preset adds no blocks by itself (2026-09-30): `options` is the full list.
  const extras = new Set(body.options);
  const stages: Stage[] = ORDER.map((name) => ({
    name,
    status:
      name === 'probe'
        ? 'done'
        : name === 'transcribe' && scenario.subs
          ? 'skipped'
          : name === 'extras' && extras.size === 0
            ? 'skipped'
            : 'pending',
    ...(name === 'probe' ? { ms: 1800 } : {}),
  }));
  const job: Job = {
    job_id: id,
    status: 'queued',
    created_at: new Date().toISOString(),
    finished_at: null,
    estimate_sec: estimateSec,
    preset: body.preset,
    options: body.options,
    email: body.email ?? null,
    stages,
    source: {
      title: probeTitle,
      duration_sec: durationSec,
      thumbnail_url: thumbnail,
      platform: sourceUrl ? 'youtube' : 'upload',
      language: body.source_language,
      url: sourceUrl,
    },
    result: null,
    error: null,
  };
  const entry: MockJob = { job, scenario };
  jobs.set(id, entry);
  entry.timer = setTimeout(() => advance(entry), 800);
  return job;
}

function advance(entry: MockJob) {
  const { job, scenario } = entry;
  job.status = 'processing';
  const running = job.stages.find((s) => s.status === 'running');
  if (running) {
    if (scenario.fail && running.name === 'transcribe') {
      running.status = 'failed';
      job.status = 'failed';
      job.finished_at = new Date().toISOString();
      job.error = job.source.url?.includes('authfail')
        ? {
            stage: 'clean',
            code: 'provider_auth',
            message: 'openai rejected the key before start (HTTP 401)',
          }
        : { stage: 'transcribe', code: 'stt_failed', message: 'STT HTTP 500' };
      return;
    }
    if (
      running.name === 'transcribe' &&
      running.progress &&
      running.progress.done < running.progress.total - 1
    ) {
      running.progress = { done: running.progress.done + 1, total: running.progress.total };
      entry.timer = setTimeout(() => advance(entry), DELAY.transcribe / running.progress.total);
      return;
    }
    running.status = scenario.extrasFail && running.name === 'extras' ? 'failed' : 'done';
    running.ms = DELAY[running.name] + Math.round(Math.random() * 400);
    if (running.progress)
      running.progress = { done: running.progress.total, total: running.progress.total };
  }
  const next = job.stages.find((s) => s.status === 'pending');
  if (!next) {
    job.status = 'done';
    job.finished_at = new Date().toISOString();
    job.result = { ...(sample as unknown as VideoDigestResult), job_id: job.job_id };
    // Uploads play our mp3 (playback.kind = audio); links keep the sample's YouTube embed.
    if (!job.source.url)
      job.result.source = {
        ...job.result.source,
        type: 'upload',
        url: null,
        platform: 'upload',
        title: job.source.title ?? S.expiredJobTitle,
        thumbnail_url: null,
        playback: { kind: 'audio', url: `/api/jobs/${job.job_id}/media`, has_video: false },
      };
    // Failed extras: the result carries no blocks, the page shows placeholders for the ordered ones.
    if (scenario.extrasFail) job.result.extras = {} as VideoDigestResult['extras'];
    // `notices`: the transcript-shortened caveat with places on the sample's own timeline.
    if (scenario.notices) {
      const starts = job.result.transcript.clean.map((p) => p.start).filter((_, i) => i % 3 === 1);
      job.result.notices = [{ kind: 'transcript_shortened', places: starts.length, starts }];
    }
    return;
  }
  next.status = 'running';
  if (next.name === 'transcribe') {
    next.progress = { done: 0, total: 7 };
    if (scenario.fail) next.progress = { done: 3, total: 7 };
    entry.timer = setTimeout(() => advance(entry), scenario.fail ? 2500 : DELAY.transcribe / 7);
    return;
  }
  entry.timer = setTimeout(() => advance(entry), DELAY[next.name]);
}

export function mockJobSnapshot(id: string): Job | null {
  const entry = jobs.get(id);
  return entry ? structuredClone(entry.job) : null;
}

export function mockRetry(id: string): Job | null {
  const entry = jobs.get(id);
  if (!entry || entry.job.status !== 'failed') return null;
  const j = entry.job;
  // The retry of a mock failure succeeds: the source URL keeps its scenario keyword, so strip it.
  const url = j.source.url ? j.source.url.replace(/fail/gi, 'ok') : null;
  return mockStartJob(
    {
      source_id: 'a1b2c3d4e5f6',
      source_language: j.source.language,
      preset: j.preset,
      output_language: j.source.language,
      options: j.options,
      email: j.email ?? undefined,
      consent_152fz: !!j.email,
    },
    url,
    j.source.title ?? S.expiredJobTitle,
    j.source.thumbnail_url,
    j.source.duration_sec,
    j.estimate_sec ?? 300,
  );
}
