import { describe, expect, it } from 'vitest';
import { toApiError } from './client';

describe('toApiError', () => {
  it('reads contract errors', () => {
    const e = toApiError(
      404,
      { error: { code: 'not_found', message: 'job not found' } },
      'Not Found',
    );
    expect([e.status, e.code, e.message]).toEqual([404, 'not_found', 'job not found']);
  });
  it('keeps max_duration_sec of too_long and leaves it undefined elsewhere', () => {
    const e = toApiError(
      400,
      { error: { code: 'too_long', message: 'video is 600 min', max_duration_sec: 5400 } },
      'x',
    );
    expect([e.code, e.maxDurationSec]).toEqual(['too_long', 5400]);
    expect(e.body).toEqual({
      error: { code: 'too_long', message: 'video is 600 min', max_duration_sec: 5400 },
    });
    expect(toApiError(400, { error: { code: 'too_long', message: 'm' } }, 'x').maxDurationSec).toBe(
      undefined,
    );
  });
  it("survives n8n's own 404 for an unregistered path (no `error` object)", () => {
    const e = toApiError(
      404,
      { code: 404, message: 'The requested webhook is not registered.' },
      'x',
    );
    expect([e.code, e.message]).toEqual(['http_error', 'The requested webhook is not registered.']);
  });
  it('falls back to the status text for empty and non-JSON bodies', () => {
    expect(toApiError(502, null, 'Bad Gateway').message).toBe('Bad Gateway');
    expect(toApiError(500, 'oops', 'Internal').code).toBe('http_error');
  });
});
