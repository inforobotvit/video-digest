import { useCallback, useEffect, useRef, useState } from 'react';

/** After a pin, scroll events this soon are the browser's own hash jump, not the reader's. */
const SETTLE_MS = 800;

/**
 * Scrollspy for the document axis. The chapter being read is the last one whose section starts
 * above the reading line (a third of the viewport from the top); above the first chapter it is
 * the first, below the last it is the last. A click on a timecode or a table-of-contents item
 * pins its chapter until the reader scrolls again, so both positions on the axis meet where the
 * click was. `layoutKey` forces a re-measure when the page reflows without scrolling (depth).
 */
export function useReadingChapter(
  count: number,
  layoutKey: string,
): [reading: number, pin: (index: number) => void] {
  const [reading, setReading] = useState(0);
  const pinnedAt = useRef<number | null>(null);
  const frame = useRef(0);

  const pin = useCallback((index: number) => {
    pinnedAt.current = performance.now();
    if (frame.current) {
      cancelAnimationFrame(frame.current);
      frame.current = 0;
    }
    setReading(index);
  }, []);

  useEffect(() => {
    const pinned = () =>
      pinnedAt.current !== null && performance.now() - pinnedAt.current < SETTLE_MS;
    const measure = () => {
      frame.current = 0;
      if (pinned()) return;
      setReading(chapterAtLine(count));
    };
    const onScroll = () => {
      if (pinned() || frame.current) return;
      frame.current = requestAnimationFrame(measure);
    };
    // The reader's own input lifts the pin at once; a scrollbar drag waits out SETTLE_MS.
    const onIntent = () => {
      pinnedAt.current = null;
    };
    pinnedAt.current = null;
    setReading(chapterAtLine(count));
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    window.addEventListener('wheel', onIntent, { passive: true });
    window.addEventListener('touchstart', onIntent, { passive: true });
    window.addEventListener('keydown', onIntent);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      window.removeEventListener('wheel', onIntent);
      window.removeEventListener('touchstart', onIntent);
      window.removeEventListener('keydown', onIntent);
      if (frame.current) cancelAnimationFrame(frame.current);
      frame.current = 0;
    };
  }, [count, layoutKey]);

  return [reading, pin];
}

function chapterAtLine(count: number): number {
  const line = window.innerHeight / 3;
  let reading = 0;
  for (let i = 0; i < count; i++) {
    const el = document.getElementById(`chapter-${i}`);
    if (!el || el.getBoundingClientRect().top > line) break;
    reading = i;
  }
  return reading;
}
