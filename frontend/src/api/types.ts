import type { VideoDigestResult } from '@/types/result';

// docs/contract-api.md, section 2: GET /api/jobs/{job_id}
export type JobStatus = 'queued' | 'processing' | 'done' | 'failed';
export type StageName = 'probe' | 'download' | 'transcribe' | 'clean' | 'digest' | 'extras';
export type StageStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';

export interface JobError {
  stage: string;
  code: string;
  message: string;
}

export interface Stage {
  name: StageName;
  status: StageStatus;
  progress?: { done: number; total: number };
  /** duration of a finished stage, ms */
  ms?: number;
}

export interface Job {
  job_id: string;
  status: JobStatus;
  created_at: string;
  finished_at: string | null;
  /** base estimate plus per-option additions, seconds; null for jobs created before the field existed */
  estimate_sec: number | null;
  preset: Preset;
  options: OptionKey[];
  email: string | null;
  stages: Stage[];
  source: {
    /** null after the retention period: the identifying fields are removed with the result */
    title: string | null;
    duration_sec: number;
    thumbnail_url: string | null;
    platform: string;
    language: string;
    url: string | null;
  };
  result: VideoDigestResult | null;
  error: JobError | null;
}

export interface ApiErrorBody {
  /** Contract section 6: `too_long` carries `max_duration_sec`, the limit the server applied. */
  error: { code: string; message: string; max_duration_sec?: number };
}

/** GET /api/limits (contract section 2, step E4): the numbers the form prints and checks before an upload. */
export interface Limits {
  max_duration_sec: number;
  upload_max_mb: number;
}

/** POST /api/feedback (contract section 2): UMUX-Lite, one answer per job. */
export interface FeedbackRequest {
  job_id: string;
  /** «Возможности сервиса соответствуют моим требованиям», 1..5 */
  fits: number;
  /** «Сервисом легко пользоваться», 1..5 */
  easy: number;
  comment?: string;
  via: 'timer' | 'button';
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    /** Seconds, from `max_duration_sec`; only `too_long` sends it. */
    public maxDurationSec?: number,
    /** The response body as received, for the console (lib/reportError), never for the screen. */
    public body?: unknown,
  ) {
    super(message);
  }
}

// docs/contract-api.md, section 2: POST /api/probe (url or multipart file)
export interface ProbeResponse {
  source_id: string;
  platform: string;
  title: string;
  duration_sec: number | null;
  subtitles: { manual: string[]; auto: string[] };
  recommended: 'subtitles_manual' | 'subtitles_auto' | 'transcribe';
  language: string | null;
  thumbnail_url: string | null;
  estimate: {
    seconds: number;
    strategy: 'subtitles' | 'transcribe';
    per_option: Record<string, number>;
  };
}

export type Preset = 'lecture' | 'meeting' | 'talk' | 'interview' | 'plain';
export type OptionKey =
  'glossary' | 'critique' | 'self_check' | 'action_items' | 'decisions' | 'questions';

// GET /api/jobs/{job_id}/export/{format}
export const EXPORT_FORMATS = [
  'digest.md',
  'transcript.md',
  'transcript.srt',
  'digest.html',
  'digest.pdf',
  'all.zip',
] as const;
export type ExportFormat = (typeof EXPORT_FORMATS)[number];
export interface ExportFile {
  blob: Blob;
  filename: string;
}

// POST /api/jobs
export interface CreateJobRequest {
  source_id: string;
  source_language: string;
  preset: Preset;
  output_language: string;
  options: OptionKey[];
  email?: string;
  consent_152fz?: boolean;
  /** Cloudflare Turnstile token from the run form (contract section 2, step E3); absent when the widget did not load. */
  turnstile_token?: string;
}
export interface CreateJobResponse {
  job_id: string;
  status: 'queued';
  url: string;
}
