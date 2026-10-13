// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';

vi.mock('@/api/client', () => ({ MOCK: false }));
const { useFeedbackPrompt, FEEDBACK_DELAY_MS, markRated, canAutoPrompt, feedbackDelayMs } =
  await import('./feedback');

let host: HTMLDivElement;
let root: Root;
let last: ReturnType<typeof useFeedbackPrompt> | null = null;
function Probe({ jobId, done, interacted }: { jobId: string; done: boolean; interacted: boolean }) {
  last = useFeedbackPrompt(jobId, done, interacted);
  return null;
}
const render = (jobId: string, done: boolean, interacted: boolean) =>
  act(() => root.render(<Probe jobId={jobId} done={done} interacted={interacted} />));
const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));

beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  last = null;
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.useRealTimers();
});

describe('when the survey is offered', () => {
  it('not before 45 s, and only after an interaction', () => {
    render('j_one001', true, false);
    wait(FEEDBACK_DELAY_MS - 1);
    expect(last!.open).toBe(false);
    wait(2);
    expect(last!.open).toBe(false); // elapsed, but nothing done yet
    render('j_one001', true, true);
    expect(last!.open).toBe(true);
    expect(last!.via).toBe('timer');
  });

  it('interaction before the timer: opens exactly at 45 s', () => {
    render('j_one002', true, true);
    wait(FEEDBACK_DELAY_MS - 1);
    expect(last!.open).toBe(false);
    wait(1);
    expect(last!.open).toBe(true);
  });

  it('never on a job that is not done', () => {
    render('j_fail01', false, true);
    wait(FEEDBACK_DELAY_MS * 2);
    expect(last!.open).toBe(false);
  });

  it('once per job, not twice a day per browser; closing without an answer keeps the job unrated but silences the timer for a day', () => {
    render('j_day001', true, true);
    wait(FEEDBACK_DELAY_MS);
    expect(last!.open).toBe(true);
    act(() => last!.close());
    expect(last!.rated).toBe(false); // not an answer: the button still opens the form
    act(() => last!.openManual());
    expect(last!.open).toBe(true);
    act(() => last!.close());
    // another job the same day: the timer keeps quiet, the button works
    act(() => root.unmount());
    root = createRoot(host);
    render('j_day002', true, true);
    wait(FEEDBACK_DELAY_MS);
    expect(last!.open).toBe(false);
    act(() => last!.openManual());
    expect(last!.open).toBe(true);
    expect(last!.via).toBe('button');
    act(() => last!.close());
    // a day later the timer speaks again on a new job
    vi.setSystemTime(Date.now() + 24 * 60 * 60 * 1000 + 1);
    act(() => root.unmount());
    root = createRoot(host);
    render('j_day003', true, true);
    wait(FEEDBACK_DELAY_MS);
    expect(last!.open).toBe(true);
    act(() => last!.markAnswered());
    expect(last!.rated).toBe(true);
    // a fourth job after an answer today: not offered, the button still works
    act(() => root.unmount());
    root = createRoot(host);
    render('j_day004', true, true);
    wait(FEEDBACK_DELAY_MS);
    expect(last!.open).toBe(false);
    act(() => last!.openManual());
    expect(last!.open).toBe(true);
  });

  it('?feedback_after is understood by the mock only: the real build keeps the 45 s', () => {
    window.history.replaceState({}, '', '/jobs/j_x?feedback_after=10');
    expect(feedbackDelayMs()).toBe(FEEDBACK_DELAY_MS);
    window.history.replaceState({}, '', '/');
  });

  it('a rated job is remembered and not offered again', () => {
    markRated('j_rated1');
    render('j_rated1', true, true);
    expect(last!.rated).toBe(true);
    wait(FEEDBACK_DELAY_MS);
    expect(last!.open).toBe(false);
  });

  it('with storage unavailable the timer never opens the form', () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(canAutoPrompt('j_nost01')).toBe(false);
    render('j_nost01', true, true);
    wait(FEEDBACK_DELAY_MS);
    expect(last!.open).toBe(false);
    act(() => last!.openManual());
    expect(last!.open).toBe(true);
    spy.mockRestore();
  });
});
