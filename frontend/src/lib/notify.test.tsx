// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import type { Job } from '@/api/types';
import { S } from '@/strings';
import { useNotifyOnFinish } from './notify';

const calls: { title: string; body?: string }[] = [];
class FakeNotification {
  static permission: NotificationPermission = 'granted';
  onclick: (() => void) | null = null;
  constructor(title: string, opts?: NotificationOptions) {
    calls.push({ title, body: opts?.body });
  }
  close() {}
}

const job = (status: Job['status']): Job =>
  ({
    job_id: 'j_1',
    status,
    source: { title: 'Лекция 7' },
    result: null,
    stages: [],
  }) as unknown as Job;

function Probe({ job }: { job: Job | null }) {
  useNotifyOnFinish(job);
  return null;
}

let root: Root;
let container: HTMLDivElement;
let hidden = true;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('Notification', FakeNotification);
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
  calls.length = 0;
  hidden = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const render = (j: Job | null) => act(() => root.render(<Probe job={j} />));

describe('useNotifyOnFinish', () => {
  it('notifies once when a job we waited on finishes in a hidden tab', () => {
    render(job('processing'));
    render(job('processing'));
    expect(calls).toEqual([]);
    render(job('done'));
    render(job('done'));
    expect(calls).toEqual([{ title: S.notifyDone, body: 'Лекция 7' }]);
  });

  it('names the failure', () => {
    render(job('queued'));
    render(job('failed'));
    expect(calls[0].title).toBe(S.notifyFailed);
  });

  it('stays quiet for a visible tab, a job opened already finished, or without permission', () => {
    hidden = false;
    render(job('processing'));
    render(job('done'));
    expect(calls).toEqual([]);

    hidden = true;
    act(() => root.unmount());
    root = createRoot(container);
    render(job('done'));
    expect(calls).toEqual([]);

    FakeNotification.permission = 'default';
    act(() => root.unmount());
    root = createRoot(container);
    render(job('processing'));
    render(job('done'));
    expect(calls).toEqual([]);
    FakeNotification.permission = 'granted';
  });
});
