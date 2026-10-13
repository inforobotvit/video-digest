// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import type { Job } from '@/api/types';
import type { VideoDigestResult } from '@/types/result';
import { ResultPage } from './ResultPage';
import sample from '@fixtures/result-sample.json';

// Every fixture the mock serves, plus the sample as an uploaded file (audio player) and a direct link.
const real = import.meta.glob<VideoDigestResult>('@fixtures/real/*.json', {
  import: 'default',
  eager: true,
});
const base = sample as unknown as VideoDigestResult;
const audio = structuredClone(base);
audio.source = {
  ...audio.source,
  type: 'upload',
  url: null,
  platform: 'upload',
  thumbnail_url: null,
  playback: { kind: 'audio', url: '/api/jobs/audio/media', has_video: false },
};
const direct = structuredClone(base);
direct.source = {
  ...direct.source,
  platform: 'generic',
  url: 'http://localhost/mock/playback.mp3',
  playback: { kind: 'direct', url: 'http://localhost/mock/playback.mp3', has_video: false },
};
const fixtures: Record<string, VideoDigestResult> = {
  sample: base,
  audio,
  direct,
  ...Object.fromEntries(
    Object.entries(real).map(([path, r]) => [
      path
        .split('/')
        .pop()!
        .replace(/\.json$/, ''),
      r,
    ]),
  ),
};

function toJob(id: string, result: VideoDigestResult): Job {
  return {
    job_id: id,
    status: 'done',
    created_at: result.meta.created_at,
    finished_at: result.meta.finished_at,
    estimate_sec: null,
    preset: result.preset,
    options: result.options,
    email: null,
    stages: [],
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

/** jsdom lacks the layout and media APIs the page touches; the stubs keep them inert. */
function stubBrowser(mobile: boolean) {
  window.matchMedia = (query: string) =>
    ({
      matches: mobile,
      media: query,
      addEventListener() {},
      removeEventListener() {},
    }) as unknown as MediaQueryList;
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
  if (typeof CSS === 'undefined' || !CSS.escape)
    (globalThis as { CSS?: unknown }).CSS = { escape: (s: string) => s.replace(/[^\w-]/g, '\\$&') };
  for (const m of ['play', 'pause', 'load'] as const)
    Object.defineProperty(HTMLMediaElement.prototype, m, { configurable: true, value: () => {} });
}

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe('ResultPage renders every fixture', () => {
  let root: Root;
  let container: HTMLDivElement;
  let errors: unknown[][];
  beforeEach(() => {
    errors = [];
    vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => errors.push(args));
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
    window.history.replaceState(null, '', '/');
  });

  const cases: [string, boolean, number][] = [];
  for (const id of Object.keys(fixtures))
    for (const mobile of [false, true])
      for (const depth of [1, 2, 3]) cases.push([id, mobile, depth]);

  it.each(cases)('%s (mobile=%s, depth=%d)', (id, mobile, depth) => {
    stubBrowser(mobile);
    window.history.replaceState(null, '', `/jobs/${id}?depth=${depth}`);
    const result = fixtures[id];
    act(() => root.render(<ResultPage job={toJob(id, result)} result={result} />));

    // Structure: one chapter per part, the title of each on the page; TL;DR present.
    expect(container.querySelectorAll('.chapter')).toHaveLength(result.digest.structure.length);
    // Typography rewrites spaces and dashes, so compare letters only.
    const letters = (t: string) => t.replace(/[^\p{L}\p{N}]+/gu, '');
    const page = letters(container.textContent ?? '');
    for (const part of result.digest.structure) expect(page).toContain(letters(part.title));
    expect(container.querySelector('.tldr__text')).not.toBeNull();
    // Sidebar on desktop, the chapter chip on mobile; a player bar in both.
    expect(container.querySelector(mobile ? '.depth__chapter' : '.side')).not.toBeNull();
    expect(container.querySelector('.player')).not.toBeNull();
    if (depth === 3) expect(container.querySelectorAll('.row--para').length).toBeGreaterThan(0);
    // React warnings (duplicate keys, bad props) are failures too.
    expect(errors.map((e) => String(e[0]))).toEqual([]);
  });
});
