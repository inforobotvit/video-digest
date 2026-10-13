// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { NoticeBand, type Notice } from './NoticeBand';
import { S } from '@/strings';

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function render(notices: Notice[] | undefined, onSeek = vi.fn()) {
  act(() => root.render(<NoticeBand notices={notices} onSeek={onSeek} />));
  return onSeek;
}
const click = (el: Element | null) =>
  act(() => el?.dispatchEvent(new MouseEvent('click', { bubbles: true })));
// S applies typography to every string (non-breaking spaces after short words); compare on plain spaces.
const plain = (el: Element | null) => (el?.textContent ?? '').replace(/\u00a0/g, ' ');

describe('NoticeBand', () => {
  it('renders nothing without notices', () => {
    render(undefined);
    expect(host.querySelector('.notices')).toBeNull();
    render([]);
    expect(host.querySelector('.notices')).toBeNull();
  });

  it('one place: singular wording, the place opens on request and seeks the player', () => {
    const onSeek = render([{ kind: 'transcript_shortened', places: 1, starts: [1357.5] }]);
    const text = plain(host.querySelector('.notice__text'));
    expect(text).toContain(S.notices.transcript_shortened.title);
    expect(text).toContain('в 1 месте');
    expect(text).not.toContain('ошибк');
    expect(host.querySelector('.notice__places')).toBeNull();
    click(host.querySelector('.notice__toggle'));
    const codes = host.querySelectorAll('.notice__places .tc');
    expect(codes.length).toBe(1);
    expect(codes[0].textContent).toBe('22:37');
    click(codes[0]);
    expect(onSeek).toHaveBeenCalledWith(1357.5);
    click(host.querySelector('.notice__toggle'));
    expect(host.querySelector('.notice__places')).toBeNull();
  });

  it('many places: plural wording, every place listed, sorted as given', () => {
    const starts = Array.from({ length: 37 }, (_, i) => 100 + i * 60);
    render([{ kind: 'transcript_shortened', places: 37, starts }]);
    expect(plain(host.querySelector('.notice__text'))).toContain('в 37 местах');
    click(host.querySelector('.notice__toggle'));
    expect(host.querySelectorAll('.notice__places .tc').length).toBe(37);
    expect(host.querySelector('.notice__capped')).toBeNull();
  });

  it('capped list says how many of the places are shown; both kinds render as separate bands', () => {
    render([
      {
        kind: 'transcript_shortened',
        places: 55,
        starts: Array.from({ length: 40 }, (_, i) => i * 30),
      },
      { kind: 'clean_fallback', places: 2, starts: [0, 600] },
    ]);
    const items = host.querySelectorAll('.notice');
    expect(items.length).toBe(2);
    expect(items[1].textContent).toContain(S.notices.clean_fallback.title);
    expect(plain(items[1])).toContain('На 2 участках');
    click(items[0].querySelector('.notice__toggle'));
    expect(items[0].querySelectorAll('.tc').length).toBe(40);
    expect(items[0].querySelector('.notice__capped')!.textContent).toBe(S.notices.capped(40, 55));
  });
});
