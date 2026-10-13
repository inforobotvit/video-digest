import { useEffect, useImperativeHandle, useRef, forwardRef } from 'react';
import { renderTurnstile, type Widget } from '@/lib/turnstile';

export interface TurnstileHandle {
  /** After every submit attempt: the token is single-use. */
  reset: () => void;
}

/**
 * One Turnstile widget on the run form; the token goes to the parent through `onToken`. The widget lives in the
 * run row of the open preset and is remounted when another preset opens (an iframe cannot be moved without a
 * reload); a token already received is kept by the parent across the remount – it is a string valid for five
 * minutes on its own – and only replaced when the new widget hands over its own. The parent drops it itself
 * after every submit attempt (`reset`) and the widget on expiry or error.
 */
export const Turnstile = forwardRef<TurnstileHandle, { onToken: (token: string | null) => void }>(
  function Turnstile({ onToken }, ref) {
    const box = useRef<HTMLDivElement>(null);
    const widget = useRef<Widget | null>(null);
    const latest = useRef(onToken);
    latest.current = onToken;
    useEffect(() => {
      const el = box.current;
      if (!el) return;
      let alive = true;
      void renderTurnstile(el, (t) => latest.current(t)).then((w) => {
        if (!alive) w?.remove();
        else widget.current = w;
      });
      return () => {
        alive = false;
        widget.current?.remove();
        widget.current = null;
      };
    }, []);
    useImperativeHandle(ref, () => ({ reset: () => widget.current?.reset() }), []);
    return <div ref={box} className="turnstile" />;
  },
);
