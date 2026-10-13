import { ApiError } from '@/api/types';
import type { Job } from '@/api/types';

/**
 * Error codes are not shown to people: the screen gets a sentence, the console gets the stage,
 * the code and the raw response body so a failed run can still be diagnosed from the browser.
 */
export function reportError(stage: string, e: unknown, extra: Record<string, unknown> = {}): void {
  if (e instanceof ApiError) {
    console.warn(`[video-digest] ${stage} · ${e.code}`, {
      status: e.status,
      code: e.code,
      message: e.message,
      body: e.body,
      ...extra,
    });
    return;
  }
  console.warn(`[video-digest] ${stage}`, { error: e, ...extra });
}

/** A job that ended as failed: the pipeline stage, code and message from GET /api/jobs/{id}. */
export function reportJobError(job: Job): void {
  const err = job.error ?? { stage: 'pipeline', code: 'generic', message: '' };
  console.warn(`[video-digest] ${err.stage} · ${err.code}`, { job_id: job.job_id, ...err });
}
