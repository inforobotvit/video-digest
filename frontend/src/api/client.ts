import {
  ApiError,
  type ApiErrorBody,
  type FeedbackRequest,
  type CreateJobRequest,
  type CreateJobResponse,
  type ExportFile,
  type ExportFormat,
  type Job,
  type Limits,
  type ProbeResponse,
} from './types';
import {
  mockCreateJob,
  mockExport,
  mockGetJob,
  mockProbe,
  mockRetryJob,
  mockUpload,
  rememberProbe,
  mockSendFeedback,
  mockLimits,
} from './mock';

export const MOCK = import.meta.env.VITE_MOCK === '1';
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';
const JSON_HEADERS = { 'content-type': 'application/json' };

/**
 * Contract errors are `{ error: { code, message } }`. Anything else (nginx, n8n's own 404 for an
 * unregistered path: `{ code: 404, message }`) becomes `http_error` with whatever message it has.
 */
export function toApiError(status: number, body: unknown, fallback: string): ApiError {
  const err = (body as Partial<ApiErrorBody> | null)?.error;
  if (err && typeof err.code === 'string') {
    const max = typeof err.max_duration_sec === 'number' ? err.max_duration_sec : undefined;
    return new ApiError(status, err.code, err.message ?? fallback, max, body);
  }
  // nginx answers its own refusals with contract-shaped JSON (413 file_too_large, 429 rate_limited); should the
  // body still be html (a proxy in between), the status alone names the code.
  if (status === 413) return new ApiError(status, 'file_too_large', fallback, undefined, body);
  if (status === 429) return new ApiError(status, 'rate_limited', fallback, undefined, body);
  const message = (body as { message?: unknown } | null)?.message;
  return new ApiError(
    status,
    'http_error',
    typeof message === 'string' ? message : fallback,
    undefined,
    body,
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { accept: 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await res.json()) as ApiErrorBody;
    } catch {
      /* non-json error body */
    }
    throw toApiError(res.status, body, res.statusText);
  }
  return (await res.json()) as T;
}

/** File name from Content-Disposition (RFC 6266: filename*=UTF-8''… wins over filename="…"). */
function filenameFrom(header: string | null): string | null {
  if (!header) return null;
  const star = header.match(/filename\*=(?:UTF-8|utf-8)''([^;]+)/);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      /* fall through */
    }
  }
  const plain = header.match(/filename="?([^";]+)"?/);
  return plain ? plain[1].trim() : null;
}

/** Multipart upload with progress: fetch has no upload progress, XHR does. */
function upload(file: File, onProgress?: (fraction: number) => void): Promise<ProbeResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/probe`);
    xhr.setRequestHeader('accept', 'application/json');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new ApiError(0, 'network', 'network error'));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* non-json */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as ProbeResponse);
      else reject(toApiError(xhr.status, body as ApiErrorBody | null, xhr.statusText));
    };
    const form = new FormData();
    form.append('file', file, file.name);
    xhr.send(form);
  });
}

// GET /api/limits once per page load: the form prints the numbers when they arrive and works without them – a
// failed call is forgotten so the next home page mount asks again.
let limits: Promise<Limits> | null = null;

/** One client for the contract (docs/contract-api.md); the mock serves fixtures when VITE_MOCK=1. */
export const api = {
  limits(): Promise<Limits> {
    if (!limits) {
      limits = (MOCK ? mockLimits() : request<Limits>('/limits', { cache: 'no-store' })).catch(
        (e: unknown) => {
          limits = null;
          throw e;
        },
      );
    }
    return limits;
  },
  getJob(id: string): Promise<Job> {
    return MOCK
      ? mockGetJob(id)
      : request<Job>(`/jobs/${encodeURIComponent(id)}`, { cache: 'no-store' });
  },
  async probe(url: string): Promise<ProbeResponse> {
    if (MOCK) {
      const p = await mockProbe(url);
      rememberProbe(url, p);
      return p;
    }
    return request<ProbeResponse>('/probe', {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify({ url }),
    });
  },
  async upload(file: File, onProgress?: (fraction: number) => void): Promise<ProbeResponse> {
    if (MOCK) {
      const p = await mockUpload(file, onProgress);
      rememberProbe(null, p);
      return p;
    }
    return upload(file, onProgress);
  },
  /** `estimateSec` is only for the mock, which has no pipeline to compute it. */
  createJob(body: CreateJobRequest, estimateSec = 0): Promise<CreateJobResponse> {
    return MOCK
      ? mockCreateJob(body, estimateSec)
      : request<CreateJobResponse>('/jobs', {
          method: 'POST',
          headers: JSON_HEADERS,
          body: JSON.stringify(body),
        });
  },
  /** Export as a file: errors (409 not_ready, 404) come back as ApiError for the toast. */
  async export(id: string, format: ExportFormat): Promise<ExportFile> {
    if (MOCK) return mockExport(id, format);
    const res = await fetch(`${BASE}/jobs/${encodeURIComponent(id)}/export/${format}`);
    if (!res.ok) {
      let body: ApiErrorBody | null = null;
      try {
        body = (await res.json()) as ApiErrorBody;
      } catch {
        /* non-json error body */
      }
      throw toApiError(res.status, body, res.statusText);
    }
    return {
      blob: await res.blob(),
      filename: filenameFrom(res.headers.get('content-disposition')) ?? `${id}-${format}`,
    };
  },
  /** Our mp3 for `playback.kind = audio`; the mock serves a file from public/. */
  mediaUrl(playbackUrl: string): string {
    return MOCK ? '/mock/playback.mp3' : playbackUrl;
  },
  /** One answer per job: 201 once, then 409 already_rated (contract section 2). */
  sendFeedback(body: FeedbackRequest): Promise<{ ok: true; job_id: string }> {
    return MOCK
      ? mockSendFeedback(body)
      : request<{ ok: true; job_id: string }>('/feedback', {
          method: 'POST',
          headers: JSON_HEADERS,
          body: JSON.stringify(body),
        });
  },
  retry(id: string): Promise<CreateJobResponse> {
    return MOCK
      ? mockRetryJob(id)
      : request<CreateJobResponse>(`/jobs/${encodeURIComponent(id)}/retry`, { method: 'POST' });
  },
};
