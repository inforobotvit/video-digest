// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { ApiError } from '@/api/types';
import { S } from '@/strings';

const sendFeedback = vi.fn();
vi.mock('@/api/client', () => ({
  MOCK: false,
  api: { sendFeedback: (...a: unknown[]) => sendFeedback(...a) },
}));
const { FeedbackModal } = await import('./FeedbackModal');

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  sendFeedback.mockReset();
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const plain = (el: Element | null) => (el?.textContent ?? '').replace(/\u00a0/g, ' ');
const click = (el: Element | null) =>
  act(() => el?.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const key = (k: string, extra: KeyboardEventInit = {}) =>
  act(() =>
    document.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, ...extra })),
  );
function render(props: Partial<Parameters<typeof FeedbackModal>[0]> = {}) {
  const onClose = vi.fn();
  const onAnswered = vi.fn();
  act(() =>
    root.render(
      <FeedbackModal
        open
        jobId="j_abc123"
        via="button"
        rated={false}
        onClose={onClose}
        onAnswered={onAnswered}
        {...props}
      />,
    ),
  );
  return { onClose, onAnswered };
}
const star = (name: string, v: number) =>
  host.querySelector<HTMLButtonElement>(
    `[role="radiogroup"][data-name="${name}"] [role="radio"][aria-label="${v}"]`,
  )!;
const stars = (name: string) =>
  Array.from(
    host.querySelectorAll<HTMLButtonElement>(
      `[role="radiogroup"][data-name="${name}"] [role="radio"]`,
    ),
  );
const lit = (name: string) => stars(name).map((s) => s.classList.contains('fb__star--on'));
const pick = (name: string, v: number) => act(() => star(name, v).click());

describe('FeedbackModal', () => {
  it('renders the two statements, the comment with its caption and limit, no email field', () => {
    render();
    const text = plain(host);
    expect(text).toContain(S.feedback.fits);
    expect(text).toContain(S.feedback.easy);
    expect(text).toContain('Не указывайте здесь персональные данные');
    expect(text).toContain('напишите в Telegram');
    expect(host.querySelector('input[type="email"]')).toBeNull();
    expect(host.querySelectorAll('[role="radiogroup"] [role="radio"]')).toHaveLength(10);
    expect(host.querySelector('textarea')!.getAttribute('maxlength')).toBe('500');
    expect(plain(host.querySelector('.fb__counter'))).toBe('0/500');
    expect((host.querySelector('button[type="submit"]') as HTMLButtonElement).disabled).toBe(true);
    expect(document.activeElement?.closest('.fb__panel')).not.toBeNull();
  });

  it('stars: a click on the third lights the first three, hovering previews, arrows move the focus', () => {
    render();
    expect(lit('fits')).toEqual([false, false, false, false, false]);
    expect(stars('fits').map((s) => s.tabIndex)).toEqual([0, -1, -1, -1, -1]);
    act(() => star('fits', 4).dispatchEvent(new MouseEvent('mouseover', { bubbles: true })));
    // React's onMouseEnter listens to mouseover/mouseout pairs on the root
    expect(lit('fits')).toEqual([true, true, true, true, false]);
    act(() => star('fits', 4).dispatchEvent(new MouseEvent('mouseout', { bubbles: true })));
    act(() =>
      host
        .querySelector('[data-name="fits"] .fb__starrow')!
        .dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: document.body })),
    );
    expect(lit('fits')).toEqual([false, false, false, false, false]);
    pick('fits', 3);
    expect(lit('fits')).toEqual([true, true, true, false, false]);
    expect(stars('fits').map((s) => s.getAttribute('aria-checked'))).toEqual([
      'false',
      'false',
      'true',
      'false',
      'false',
    ]);
    expect(stars('fits').map((s) => s.tabIndex)).toEqual([-1, -1, 0, -1, -1]);
    expect(plain(host.querySelector('[data-name="fits"]'))).toContain('не согласен');
    expect(plain(host.querySelector('[data-name="fits"]'))).toContain('полностью согласен');
    star('fits', 3).focus();
    act(() =>
      star('fits', 3).dispatchEvent(
        new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
      ),
    );
    expect(document.activeElement).toBe(star('fits', 4));
    expect(lit('fits')).toEqual([true, true, true, false, false]); // moving the focus chooses nothing
    expect(star('fits', 3).getAttribute('aria-checked')).toBe('true');
    pick('fits', 4); // Enter or Space on a focused star is the button's own click
    expect(star('fits', 4).getAttribute('aria-checked')).toBe('true');
  });

  it('sends the answer and reports it; the dialog then shows thanks', async () => {
    sendFeedback.mockResolvedValue({ ok: true, job_id: 'j_abc123' });
    const { onAnswered } = render({ via: 'timer' });
    pick('fits', 4);
    pick('easy', 5);
    act(() => {
      const ta = host.querySelector<HTMLTextAreaElement>('textarea')!;
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!;
      setter.call(ta, ' коротко ');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => {
      host
        .querySelector('form')!
        .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(sendFeedback).toHaveBeenCalledWith({
      job_id: 'j_abc123',
      fits: 4,
      easy: 5,
      comment: 'коротко',
      via: 'timer',
    });
    expect(onAnswered).toHaveBeenCalled();
    render({ rated: true });
    expect(plain(host)).toContain(S.feedback.thanksTitle);
  });

  it('a second answer refused by the server counts as answered', async () => {
    sendFeedback.mockRejectedValue(new ApiError(409, 'already_rated', 'rated'));
    const { onAnswered } = render();
    pick('fits', 3);
    pick('easy', 3);
    await act(async () => {
      host
        .querySelector('form')!
        .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(onAnswered).toHaveBeenCalled();
  });

  it('Esc, the overlay and «Не сейчас» close it without an answer; Tab stays inside', () => {
    const { onClose, onAnswered } = render();
    key('Escape');
    expect(onClose).toHaveBeenCalledTimes(1);
    click(host.querySelector('.fb__overlay'));
    expect(onClose).toHaveBeenCalledTimes(2);
    click(
      Array.from(host.querySelectorAll('button')).find((b) => b.textContent === S.feedback.skip)!,
    );
    expect(onClose).toHaveBeenCalledTimes(3);
    expect(onAnswered).not.toHaveBeenCalled();
    // focus trap: Tab from the last control goes to the first, Shift+Tab from the first to the last
    const items = Array.from(
      host
        .querySelector('.fb__panel')!
        .querySelectorAll<HTMLElement>(
          'input:not([disabled]), textarea:not([disabled]), button:not([disabled]):not([tabindex="-1"])',
        ),
    );
    items[items.length - 1].focus();
    key('Tab');
    expect(document.activeElement).toBe(items[0]);
    key('Tab', { shiftKey: true });
    expect(document.activeElement).toBe(items[items.length - 1]);
  });
});
