import { useCallback, useEffect, useRef, useState } from 'react';
import type { PlaybackKind } from '@/lib/playback';
import {
  html5Backend,
  rutubeBackend,
  vkBackend,
  youtubeBackend,
  type Backend,
  type PlayerEvent,
} from './backends';

export interface PlayerState {
  ready: boolean;
  playing: boolean;
  /** seconds; optimistic after a seek, then whatever the player reports */
  time: number;
  duration: number | null;
  rate: number;
  muted: boolean;
  failed: boolean;
  /** true after the first play or seek; the axis shows the player mark only from then on */
  started: boolean;
}

export interface PlayerApi {
  kind: PlaybackKind;
  state: PlayerState;
  /** callback ref for the iframe or media element */
  attach: (el: HTMLIFrameElement | HTMLMediaElement | null) => void;
  /** seek and play: a timecode click means "listen from here" */
  seek: (seconds: number) => void;
  toggle: () => void;
  setRate: (rate: number) => void;
  toggleMuted: () => void;
}

const INITIAL: PlayerState = {
  ready: false,
  playing: false,
  time: 0,
  duration: null,
  rate: 1,
  muted: false,
  failed: false,
  started: false,
};

/**
 * One player for the result page regardless of playback kind. The element is attached through
 * `attach` (a callback ref) so the bar can keep an iframe mounted while it is collapsed. A seek
 * before the player is ready is kept and applied once it reports ready.
 */
export function usePlayer(kind: PlaybackKind): PlayerApi {
  const [state, setState] = useState<PlayerState>(INITIAL);
  const backend = useRef<Backend | null>(null);
  const ready = useRef(false);
  const playing = useRef(false);
  const pending = useRef<number | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;

  const attach = useCallback(
    (el: HTMLIFrameElement | HTMLMediaElement | null) => {
      backend.current?.destroy();
      backend.current = null;
      ready.current = false;
      if (!el) return;
      const emit = (e: PlayerEvent) => {
        if (e.ready && !ready.current) {
          ready.current = true;
          if (pending.current !== null) {
            const t = pending.current;
            pending.current = null;
            backend.current?.seek(t);
            backend.current?.play();
          }
        }
        if (e.playing !== undefined) playing.current = e.playing;
        setState((s) => {
          const next: PlayerState = {
            ...s,
            ...(e.ready ? { ready: true } : {}),
            ...(e.time !== undefined ? { time: e.time } : {}),
            ...(e.playing !== undefined ? { playing: e.playing } : {}),
            ...(e.playing ? { started: true } : {}),
            ...(e.duration !== undefined ? { duration: e.duration } : {}),
            ...(e.rate !== undefined ? { rate: e.rate } : {}),
            ...(e.muted !== undefined ? { muted: e.muted } : {}),
            ...(e.failed ? { failed: true } : {}),
          };
          return shallowEqual(s, next) ? s : next;
        });
      };
      if (kind === 'youtube') backend.current = youtubeBackend(el as HTMLIFrameElement, emit);
      else if (kind === 'rutube') backend.current = rutubeBackend(el as HTMLIFrameElement, emit);
      else if (kind === 'vk') backend.current = vkBackend(el as HTMLIFrameElement, emit);
      else backend.current = html5Backend(el as HTMLMediaElement, emit);
    },
    [kind],
  );

  useEffect(
    () => () => {
      backend.current?.destroy();
      backend.current = null;
    },
    [],
  );

  const seek = useCallback((seconds: number) => {
    const t = Math.max(0, seconds);
    setState((s) => ({ ...s, time: t, started: true }));
    if (!backend.current || !ready.current) {
      pending.current = t;
      return;
    }
    backend.current.seek(t);
    backend.current.play();
  }, []);

  const toggle = useCallback(() => {
    const b = backend.current;
    if (!b) return;
    if (playing.current) b.pause();
    else b.play();
    // Optimistic; the player confirms with its own state event.
    playing.current = !playing.current;
    setState((s) => ({ ...s, playing: playing.current, started: s.started || playing.current }));
  }, []);

  const setRate = useCallback((rate: number) => {
    backend.current?.setRate(rate);
    setState((s) => ({ ...s, rate }));
  }, []);

  const toggleMuted = useCallback(() => {
    const muted = !stateRef.current.muted;
    backend.current?.setMuted(muted);
    setState((s) => ({ ...s, muted }));
  }, []);

  return { kind, state, attach, seek, toggle, setRate, toggleMuted };
}

function shallowEqual(a: PlayerState, b: PlayerState): boolean {
  return (
    a.ready === b.ready &&
    a.playing === b.playing &&
    a.time === b.time &&
    a.duration === b.duration &&
    a.rate === b.rate &&
    a.muted === b.muted &&
    a.failed === b.failed &&
    a.started === b.started
  );
}
