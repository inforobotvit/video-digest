import type {
  CreateJobRequest,
  CreateJobResponse,
  ExportFile,
  ExportFormat,
  Job,
  ProbeResponse,
} from './types';
import { ApiError, EXPORT_FORMATS } from './types';
import { formatTimecode } from '@/lib/timecode';
import type { VideoDigestResult } from '@/types/result';
import { mockJobSnapshot, mockRetry, mockStartJob } from './mockJobs';
import type { FeedbackRequest, Limits } from './types';

/** The mock's limits: the same numbers the local stack runs with (MAX_DURATION_SEC 5400, UPLOAD_MAX_MB 200). */
export const MOCK_LIMITS: Limits = { max_duration_sec: 5400, upload_max_mb: 200 };
export async function mockLimits(): Promise<Limits> {
  await new Promise((r) => setTimeout(r, 200));
  return { ...MOCK_LIMITS };
}

// Fixtures are imported straight from ../n8n/fixtures (vite.config.ts alias), no copies.
import sample from '@fixtures/result-sample.json';
const real = import.meta.glob<VideoDigestResult>('@fixtures/real/*.json', { import: 'default' });

/** Job ids the mock understands (see S.fixtureLinks). */
export function mockJobIds(): string[] {
  return [
    'sample',
    'audio',
    'direct',
    'rutube',
    'expired',
    'missing',
    ...Object.keys(real).map((p) =>
      p
        .split('/')
        .pop()!
        .replace(/\.json$/, ''),
    ),
  ];
}

function toJob(id: string, result: VideoDigestResult): Job {
  const order = ['probe', 'download', 'transcribe', 'clean', 'digest', 'extras'] as const;
  return {
    job_id: id,
    status: 'done',
    created_at: result.meta.created_at,
    finished_at: result.meta.finished_at,
    estimate_sec: null,
    preset: result.preset,
    options: result.options,
    email: null,
    stages: order.map((name) => {
      const m = result.meta.stages.find((x) => x.name === name);
      return m
        ? { name, status: m.status, ...(m.status === 'done' ? { ms: m.ms } : {}) }
        : { name, status: 'skipped' as const };
    }),
    source: {
      title: result.source.title,
      duration_sec: result.source.duration_sec,
      thumbnail_url: result.source.thumbnail_url,
      platform: result.source.platform,
      language: result.source.language,
      url: result.source.url,
    },
    result,
    error: null,
  };
}

export async function mockGetJob(id: string): Promise<Job> {
  await new Promise((r) => setTimeout(r, 120));
  const live = mockJobSnapshot(id);
  if (live) return live;
  if (id === 'expired') {
    const j = toJob(id, sample as unknown as VideoDigestResult);
    // After the retention period the identifying fields are gone as well (contract section 4).
    return {
      ...j,
      result: null,
      finished_at: '2026-08-04T10:00:00Z',
      source: { ...j.source, title: null, url: null, thumbnail_url: null },
    };
  }
  if (id === 'sample') return toJob(id, sample as unknown as VideoDigestResult);
  // Playback kinds on the sample: our mp3 from public/, the same file as a direct link, a real
  // Rutube page URL (the embed is built on the client, network needed). The Rutube video must
  // be free of rights restrictions: licensed series answer the embed with a blocking rule.
  if (id === 'audio' || id === 'direct' || id === 'rutube') {
    const r = structuredClone(sample as unknown as VideoDigestResult);
    if (id === 'audio') {
      r.source = {
        ...r.source,
        type: 'upload',
        url: null,
        platform: 'upload',
        thumbnail_url: null,
        playback: { kind: 'audio', url: `/api/jobs/${id}/media`, has_video: false },
      };
    } else if (id === 'direct') {
      const url = `${window.location.origin}/mock/playback.mp3`;
      r.source = {
        ...r.source,
        platform: 'generic',
        url,
        playback: { kind: 'direct', url, has_video: false },
      };
    } else {
      const url = 'https://rutube.ru/video/07b7e77b61787c3cc6dffd8da8aee6f2/';
      r.source = {
        ...r.source,
        platform: 'rutube',
        url,
        playback: { kind: 'rutube', url, has_video: true },
      };
    }
    return toJob(id, r);
  }
  const key = Object.keys(real).find((p) => p.endsWith(`/${id}.json`));
  if (!key) throw new ApiError(404, 'not_found', 'job not found');
  return toJob(id, await real[key]());
}

const PER_OPTION = {
  glossary: 15,
  critique: 30,
  self_check: 15,
  action_items: 15,
  decisions: 15,
  questions: 15,
};

/** Mock probe: the URL decides the outcome so every state of the home page can be exercised. */
export async function mockProbe(url: string): Promise<ProbeResponse> {
  await new Promise((r) => setTimeout(r, 1200));
  const u = url.toLowerCase();
  if (!/^https?:\/\//.test(u) || u.includes('unsupported'))
    throw new ApiError(400, 'unsupported_url', 'URL is not supported');
  if (u.includes('private'))
    throw new ApiError(404, 'private_or_removed', 'video is private, removed or not accessible');
  if (u.includes('bot')) throw new ApiError(403, 'bot_check', 'YouTube asks to sign in');
  if (u.includes('long'))
    throw new ApiError(400, 'too_long', 'video is too long', MOCK_LIMITS.max_duration_sec);
  const src = (sample as unknown as VideoDigestResult).source;
  const subs = u.includes('subs');
  const d = src.duration_sec;
  return {
    source_id: 'a1b2c3d4e5f6',
    platform: 'youtube',
    title: src.title,
    duration_sec: d,
    subtitles: subs ? { manual: ['ru'], auto: ['ru'] } : { manual: [], auto: ['ru'] },
    recommended: subs ? 'subtitles_manual' : 'transcribe',
    language: 'ru',
    thumbnail_url: src.thumbnail_url,
    estimate: {
      seconds: subs ? 60 : Math.round(d * 0.08 + 60),
      strategy: subs ? 'subtitles' : 'transcribe',
      per_option: PER_OPTION,
    },
  };
}

export async function mockUpload(
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<ProbeResponse> {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (!['mp4', 'mov', 'mkv', 'webm', 'mp3', 'm4a', 'wav', 'ogg', 'flac'].includes(ext))
    throw new ApiError(400, 'unsupported_file', `extension '${ext}' not supported`);
  if (file.size > MOCK_LIMITS.upload_max_mb * 1024 * 1024)
    throw new ApiError(413, 'file_too_large', 'file exceeds UPLOAD_MAX_MB');
  for (let i = 1; i <= 10; i++) {
    await new Promise((r) => setTimeout(r, 180));
    onProgress?.(i / 10);
  }
  await new Promise((r) => setTimeout(r, 500));
  const d = 3721;
  return {
    source_id: '986432682780',
    platform: 'upload',
    title: file.name.replace(/\.[^.]+$/, ''),
    duration_sec: d,
    subtitles: { manual: [], auto: [] },
    recommended: 'transcribe',
    language: null,
    thumbnail_url: null,
    estimate: {
      seconds: Math.round(d * 0.08 + 60),
      strategy: 'transcribe',
      per_option: PER_OPTION,
    },
  };
}

let pdfAttempts = 0;

/**
 * Export from the result in memory. Formats other than md are placeholders with the right name.
 * The first pdf request answers 409 not_ready so the retry toast can be exercised.
 */
export async function mockExport(id: string, format: ExportFormat): Promise<ExportFile> {
  await new Promise((r) => setTimeout(r, 500));
  if (!EXPORT_FORMATS.includes(format)) throw new ApiError(400, 'bad_format', 'unknown format');
  if (id === 'expired' || id === 'missing') throw new ApiError(404, 'not_found', 'job not found');
  if (format === 'digest.pdf' && pdfAttempts++ % 2 === 0)
    throw new ApiError(409, 'not_ready', 'pdf is not generated yet');
  const job = await mockGetJob(id);
  const r = job.result;
  if (!r) throw new ApiError(404, 'not_found', 'result deleted');
  const md = [
    `# ${r.source.title}`,
    '',
    `**TL;DR** ${r.digest.tldr}`,
    '',
    ...r.digest.structure.map((p) => `- ${formatTimecode(p.start)} ${p.title}`),
    '',
    ...r.digest.key_points.map((k) => `- **${k.text}** ${k.detail}`),
    '',
  ].join('\n');
  const transcript = r.transcript.clean
    .map((p) => `${formatTimecode(p.start)} ${p.text}`)
    .join('\n\n');
  const srtTime = (s: number) => {
    const d = new Date(Math.round(s * 1000));
    return `${d.toISOString().slice(11, 23).replace('.', ',')}`;
  };
  const srt = r.transcript.segments
    .map((s, i) => `${i + 1}\n${srtTime(s.start)} --> ${srtTime(s.end)}\n${s.text}\n`)
    .join('\n');
  const html = `<!doctype html><meta charset="utf-8"><title>${r.source.title}</title><pre>${md}</pre>`;
  const content: Record<ExportFormat, [string, string]> = {
    'digest.md': [md, 'text/markdown'],
    'transcript.md': [transcript, 'text/markdown'],
    'transcript.srt': [srt, 'application/x-subrip'],
    'digest.html': [html, 'text/html'],
    'digest.pdf': [`mock pdf for ${id}`, 'application/pdf'],
    'all.zip': [`mock zip for ${id}`, 'application/zip'],
  };
  const [text, type] = content[format];
  return { blob: new Blob([text], { type }), filename: `${id}-${format}` };
}

let lastProbe: { url: string | null; probe: ProbeResponse } | null = null;
export function rememberProbe(url: string | null, probe: ProbeResponse): void {
  lastProbe = { url, probe };
}

export async function mockCreateJob(
  body: CreateJobRequest,
  estimateSec: number,
): Promise<CreateJobResponse> {
  await new Promise((r) => setTimeout(r, 400));
  if (body.email && body.consent_152fz !== true)
    throw new ApiError(400, 'consent_required', 'consent_152fz must be true');
  // 429 refusals of contract section 6, chosen by a word in the probed link.
  const u = (lastProbe?.url ?? '').toLowerCase();
  if (u.includes('budget'))
    throw new ApiError(429, 'daily_limit', 'daily budget of the service is exhausted');
  if (u.includes('busy')) throw new ApiError(429, 'busy', '2 of 2 job slots are taken');
  if (u.includes('checkfail'))
    throw new ApiError(403, 'bot_check_failed', 'the browser check failed');
  const p = lastProbe?.probe;
  const job = mockStartJob(
    body,
    lastProbe?.url ?? null,
    p?.title ?? 'Видео',
    p?.thumbnail_url ?? null,
    p?.duration_sec ?? 900,
    estimateSec,
  );
  return { job_id: job.job_id, status: 'queued', url: `/jobs/${job.job_id}` };
}

export async function mockRetryJob(id: string): Promise<CreateJobResponse> {
  await new Promise((r) => setTimeout(r, 400));
  let job = mockRetry(id);
  if (!job && id === 'expired') {
    // Expired sample: re-run it from the saved URL the way the real retry re-probes.
    const j = toJob(id, sample as unknown as VideoDigestResult);
    job = mockStartJob(
      {
        source_id: 'a1b2c3d4e5f6',
        source_language: j.source.language,
        preset: j.preset,
        output_language: j.source.language,
        options: j.options,
        consent_152fz: false,
      },
      j.source.url,
      j.source.title ?? '',
      j.source.thumbnail_url,
      j.source.duration_sec,
      300,
    );
  }
  if (!job) throw new ApiError(409, 'not_retryable', 'job is not failed');
  return { job_id: job.job_id, status: 'queued', url: `/jobs/${job.job_id}` };
}

// POST /api/feedback in the mock: one answer per job, remembered for the page's lifetime.
const rated = new Set<string>();
export async function mockSendFeedback(
  body: FeedbackRequest,
): Promise<{ ok: true; job_id: string }> {
  await new Promise((r) => setTimeout(r, 150));
  const score = (v: number) => Number.isInteger(v) && v >= 1 && v <= 5;
  if (!score(body.fits) || !score(body.easy))
    throw new ApiError(400, 'validation_error', 'scores must be integers from 1 to 5');
  if ((body.comment ?? '').length > 500)
    throw new ApiError(400, 'validation_error', 'comment must be at most 500 characters');
  const live = mockJobSnapshot(body.job_id);
  const known = live ? live.status === 'done' : mockJobIds().includes(body.job_id);
  if (!known) throw new ApiError(404, 'not_found', 'job not found');
  if (rated.has(body.job_id))
    throw new ApiError(409, 'already_rated', 'this job has already been rated');
  rated.add(body.job_id);
  return { ok: true, job_id: body.job_id };
}
