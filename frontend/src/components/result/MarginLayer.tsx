import { useLayoutEffect, useRef, useState } from 'react';

export interface MarginCard {
  key: string;
  /** data-row of the text row this card belongs to */
  anchor: string;
  /** seconds; cards about different moments get a larger gap when they have to stack */
  moment: number;
  node: React.ReactNode;
}

const GAP_SAME = 10;
const GAP_OTHER = 24;

/**
 * Sidenotes: a card sits next to its anchor row when there is room, otherwise it stacks below the
 * previous card with a small gap. The text column never moves; the chapter grows when the stack
 * outruns it. The chapter element is the layer's parent: a parent ref is not attached yet when a
 * child's layout effect runs. No CSS transition on `top`: background tabs and headless renders
 * would freeze it at the start value.
 */
export function MarginLayer({ cards }: { cards: MarginCard[] }) {
  const layer = useRef<HTMLDivElement>(null);
  const [tops, setTops] = useState<number[]>([]);

  useLayoutEffect(() => {
    const el = layer.current;
    const root = el?.parentElement;
    if (!el || !root) return;
    const place = () => {
      const layerTop = el.getBoundingClientRect().top;
      const nodes = Array.from(el.children) as HTMLElement[];
      let prevBottom = -Infinity;
      let prevMoment: number | null = null;
      const next: number[] = [];
      cards.forEach((card, i) => {
        const anchor = root.querySelector<HTMLElement>(`[data-row="${CSS.escape(card.anchor)}"]`);
        const anchorTop = anchor ? anchor.getBoundingClientRect().top - layerTop : 0;
        const gap =
          prevMoment !== null && Math.abs(prevMoment - card.moment) > 1 ? GAP_OTHER : GAP_SAME;
        const top = Math.max(anchorTop, prevBottom + gap);
        next.push(top);
        prevBottom = top + (nodes[i]?.offsetHeight ?? 0);
        prevMoment = card.moment;
      });
      setTops((old) =>
        old.length === next.length && old.every((v, i) => Math.abs(v - next[i]) < 0.5) ? old : next,
      );
      const bottom =
        prevBottom === -Infinity ? 0 : prevBottom + (layerTop - root.getBoundingClientRect().top);
      root.style.minHeight = bottom > 0 ? `${Math.ceil(bottom)}px` : '';
    };
    place();
    const ro = new ResizeObserver(place);
    ro.observe(root);
    Array.from(el.children).forEach((c) => ro.observe(c));
    return () => {
      ro.disconnect();
      root.style.minHeight = '';
    };
  }, [cards]);

  if (cards.length === 0) return null;
  return (
    <div className="chapter__margin" ref={layer}>
      {cards.map((c, i) => (
        <div key={c.key} className="chapter__margin-card" style={{ top: tops[i] ?? 0 }}>
          {c.node}
        </div>
      ))}
    </div>
  );
}
