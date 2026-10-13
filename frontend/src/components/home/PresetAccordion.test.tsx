// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import type { ProbeResponse } from '@/api/types';
import { S } from '@/strings';
import type { SettingsValue } from '@/lib/settings';
import { PresetAccordion } from './PresetAccordion';

const probe = {
  estimate: {
    seconds: 240,
    strategy: 'transcribe',
    per_option: {
      glossary: 30,
      critique: 30,
      self_check: 15,
      decisions: 15,
      action_items: 15,
      questions: 15,
    },
  },
} as unknown as ProbeResponse;

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
let last: SettingsValue | null = null;
const onRun = vi.fn();

function Harness() {
  const [value, setValue] = useState<SettingsValue>({
    preset: 'plain',
    outputLanguage: 'ru',
    options: [],
  });
  last = value;
  return (
    <PresetAccordion
      probe={probe}
      value={value}
      onChange={setValue}
      onRun={onRun}
      extra={<div className="turnstile" data-testid="widget" />}
    />
  );
}

beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root.render(<Harness />));
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
  onRun.mockReset();
});

const plain = (el: Element | null) => (el?.textContent ?? '').replace(/\u00a0/g, ' ');
const rows = () => Array.from(host.querySelectorAll<HTMLElement>('[role="radio"]'));
const row = (name: string) => rows().find((r) => plain(r).startsWith(name))!;
const click = (el: Element | null) =>
  act(() => el?.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const key = (el: Element, k: string) =>
  act(() => el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true })));
const checks = () => Array.from(host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'));
const check = (title: string) => checks().find((c) => plain(c.closest('label')).startsWith(title))!;
const estimate = () => plain(host.querySelector('.acc__est'));

describe('PresetAccordion', () => {
  it('«Просто выжимка» is first, open by default with every block unchecked; the run and the widget are inside', () => {
    expect(rows().map((r) => r.getAttribute('aria-checked'))).toEqual([
      'true',
      'false',
      'false',
      'false',
      'false',
    ]);
    expect(plain(rows()[0])).toContain(S.presetNames.plain);
    expect(host.querySelectorAll('.acc__body')).toHaveLength(1);
    expect(checks()).toHaveLength(6);
    expect(checks().every((c) => !c.checked)).toBe(true);
    const body = host.querySelector('.acc__body')!;
    expect(body.querySelector('button.btn--primary')?.textContent).toBe(S.run);
    expect(body.querySelector('[data-testid="widget"]')).not.toBeNull();
    expect(estimate()).toBe('Готово через ~4 мин');
  });

  it('opening «Лекция» checks its defaults, and a default can be unchecked; the estimate follows', () => {
    click(row(S.presetNames.lecture));
    expect(row(S.presetNames.lecture).getAttribute('aria-checked')).toBe('true');
    expect(last!.preset).toBe('lecture');
    expect(last!.options).toEqual(['glossary', 'self_check']);
    // the rows keep one order for every preset; the defaults show by their checkmarks
    expect(checks().map((c) => c.checked)).toEqual([true, false, true, false, false, false]);
    expect(estimate()).toBe('Готово через ~5 мин'); // 240+30+15 = 285 s
    expect(plain(check(S.optionLabels.glossary.title).closest('label'))).toContain('+30 с');
    act(() => check(S.optionLabels.glossary.title).click());
    expect(last!.options).toEqual(['self_check']);
    expect(estimate()).toBe('Готово через ~4 мин'); // 255 s
    act(() => check(S.optionLabels.critique.title).click());
    expect(last!.options).toEqual(['self_check', 'critique']);
    expect(estimate()).toBe('Готово через ~5 мин'); // 285 s
  });

  it('blocks can be added in «Просто выжимка»', () => {
    act(() => check(S.optionLabels.glossary.title).click());
    expect(last!.preset).toBe('plain');
    expect(last!.options).toEqual(['glossary']);
    expect(estimate()).toBe('Готово через ~5 мин'); // 270 s
  });

  it('keyboard: only the open row is in the tab order, arrows move focus, Enter and Space open', () => {
    expect(rows().map((r) => r.tabIndex)).toEqual([0, -1, -1, -1, -1]);
    rows()[0].focus();
    key(rows()[0], 'ArrowDown');
    expect(document.activeElement).toBe(rows()[1]);
    expect(last!.preset).toBe('plain'); // moving focus does not open
    key(rows()[1], 'Enter');
    expect(last!.preset).toBe('lecture');
    expect(rows().map((r) => r.tabIndex)).toEqual([-1, 0, -1, -1, -1]);
    key(rows()[1], 'ArrowUp');
    key(rows()[0], 'ArrowUp'); // wraps to the last row
    expect(document.activeElement).toBe(rows()[4]);
    key(rows()[4], ' ');
    expect(last!.preset).toBe('meeting');
    key(rows()[4], 'Home');
    expect(document.activeElement).toBe(rows()[0]);
  });

  it('«Запустить» calls onRun', () => {
    click(host.querySelector('.acc__body button.btn--primary'));
    expect(onRun).toHaveBeenCalledTimes(1);
  });
});
