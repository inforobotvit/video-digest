/**
 * One small adapter per playback kind. Each turns the platform's own protocol into the same
 * events (time, playing, duration, ready) and the same commands (seek, play, pause, rate, mute).
 * YouTube: widget postMessage protocol (enablejsapi=1). Rutube: postMessage protocol from
 * rutube.ru/info/embed. VK: their videoplayer.js, loaded only when a VK player is on the page.
 * direct / audio: an HTML5 media element.
 */

export interface PlayerEvent {
  ready?: true;
  time?: number;
  playing?: boolean;
  duration?: number;
  rate?: number;
  muted?: boolean;
  failed?: true;
}
export type Emit = (e: PlayerEvent) => void;

export interface Backend {
  seek(seconds: number): void;
  play(): void;
  pause(): void;
  setRate(rate: number): void;
  setMuted(muted: boolean): void;
  destroy(): void;
}

function parseJson(data: unknown): Record<string, unknown> | null {
  if (typeof data !== 'string')
    return data && typeof data === 'object' ? (data as Record<string, unknown>) : null;
  try {
    const v: unknown = JSON.parse(data);
    return v && typeof v === 'object' ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

// --- YouTube ---------------------------------------------------------------------------------

const YT_ORIGIN = 'https://www.youtube.com';

export function youtubeBackend(iframe: HTMLIFrameElement, emit: Emit): Backend {
  let heard = false;
  const send = (msg: Record<string, unknown>) =>
    iframe.contentWindow?.postMessage(
      JSON.stringify({ ...msg, id: 'vd', channel: 'widget' }),
      YT_ORIGIN,
    );
  const command = (func: string, args: unknown[] = []) => send({ event: 'command', func, args });
  const listen = () => send({ event: 'listening' });

  const onMessage = (e: MessageEvent) => {
    if (e.origin !== YT_ORIGIN || e.source !== iframe.contentWindow) return;
    const data = parseJson(e.data);
    if (!data) return;
    if (!heard) {
      heard = true;
      emit({ ready: true });
    }
    // onError: 2 bad id, 5 html5 error, 100 not found, 101 / 150 embedding disallowed.
    if (data.event === 'onError') emit({ failed: true });
    const info = data.info as Record<string, unknown> | undefined;
    if (!info) return;
    const out: PlayerEvent = {};
    if (typeof info.currentTime === 'number') out.time = info.currentTime;
    if (typeof info.duration === 'number' && info.duration > 0) out.duration = info.duration;
    if (typeof info.playbackRate === 'number') out.rate = info.playbackRate;
    if (typeof info.muted === 'boolean') out.muted = info.muted;
    // -1 unstarted, 0 ended, 1 playing, 2 paused, 3 buffering (keeps the previous state), 5 cued.
    if (typeof info.playerState === 'number' && info.playerState !== 3)
      out.playing = info.playerState === 1;
    emit(out);
  };
  window.addEventListener('message', onMessage);
  // The widget only talks after a `listening` message; repeat until it answers.
  const timer = setInterval(() => (heard ? clearInterval(timer) : listen()), 300);
  iframe.addEventListener('load', listen);

  return {
    seek: (t) => command('seekTo', [t, true]),
    play: () => command('playVideo'),
    pause: () => command('pauseVideo'),
    setRate: (r) => command('setPlaybackRate', [r]),
    setMuted: (m) => command(m ? 'mute' : 'unMute'),
    destroy: () => {
      clearInterval(timer);
      window.removeEventListener('message', onMessage);
      iframe.removeEventListener('load', listen);
    },
  };
}

// --- Rutube ----------------------------------------------------------------------------------

export function rutubeBackend(iframe: HTMLIFrameElement, emit: Emit): Backend {
  const send = (type: string, data: Record<string, unknown> = {}) =>
    iframe.contentWindow?.postMessage(JSON.stringify({ type, data }), '*');
  // Rutube drops setCurrentTime sent before playback has started: keep the target and send it
  // again while the reported time is far from it (a few tries, then give up).
  let want: number | null = null;
  let tries = 0;

  const onMessage = (e: MessageEvent) => {
    if (e.source !== iframe.contentWindow) return;
    const msg = parseJson(e.data);
    if (!msg || typeof msg.type !== 'string') return;
    const data = (msg.data ?? {}) as Record<string, unknown>;
    switch (msg.type) {
      case 'player:ready':
        emit({ ready: true });
        break;
      case 'player:currentTime':
        if (typeof data.time !== 'number') break;
        if (want !== null) {
          if (Math.abs(data.time - want) <= 2 || tries >= 3) want = null;
          else {
            tries += 1;
            send('player:setCurrentTime', { time: want });
            break;
          }
        }
        emit({ time: data.time });
        break;
      case 'player:changeState':
        if (typeof data.state === 'string') emit({ playing: data.state === 'playing' });
        break;
      case 'player:durationChange':
        if (typeof data.duration === 'number' && data.duration > 0)
          emit({ duration: data.duration });
        break;
      case 'player:volumeChange':
        if (typeof data.muted === 'boolean') emit({ muted: data.muted });
        break;
      case 'player:error':
        emit({ failed: true });
        break;
    }
  };
  window.addEventListener('message', onMessage);

  return {
    seek: (t) => {
      want = t;
      tries = 0;
      send('player:setCurrentTime', { time: t });
    },
    play: () => send('player:play'),
    pause: () => send('player:pause'),
    setRate: () => {},
    setMuted: (m) => send(m ? 'player:mute' : 'player:unMute'),
    destroy: () => window.removeEventListener('message', onMessage),
  };
}

// --- VK --------------------------------------------------------------------------------------

interface VkState {
  time: number;
  duration: number;
  state: string;
  muted: boolean;
}
interface VkPlayer {
  play(): void;
  pause(): void;
  seek(seconds: number): void;
  mute(): void;
  unmute(): void;
  on(event: string, fn: (state: VkState) => void): void;
  destroy(): void;
}
declare global {
  interface Window {
    VK?: { VideoPlayer?: (iframe: HTMLIFrameElement) => VkPlayer };
  }
}

const VK_SCRIPT = 'https://vk.com/js/api/videoplayer.js';
let vkScript: Promise<void> | null = null;

function loadVkScript(): Promise<void> {
  if (window.VK?.VideoPlayer) return Promise.resolve();
  if (!vkScript) {
    vkScript = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = VK_SCRIPT;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => {
        vkScript = null;
        reject(new Error('VK player script failed to load'));
      };
      document.head.appendChild(s);
    });
  }
  return vkScript;
}

export function vkBackend(iframe: HTMLIFrameElement, emit: Emit): Backend {
  let player: VkPlayer | null = null;
  let inited = false;
  let dead = false;
  const queue: Array<(p: VkPlayer) => void> = [];
  const call = (fn: (p: VkPlayer) => void) => (player && inited ? fn(player) : queue.push(fn));
  const dur = (s: VkState) => (s.duration > 0 ? { duration: s.duration } : {});

  loadVkScript()
    .then(() => {
      const ctor = window.VK?.VideoPlayer;
      if (dead || !ctor) return;
      const p = ctor(iframe);
      player = p;
      p.on('inited', (s) => {
        inited = true;
        emit({ ready: true, ...dur(s) });
        queue.splice(0).forEach((fn) => fn(p));
      });
      p.on('timeupdate', (s) => emit({ time: s.time, ...dur(s) }));
      p.on('started', () => emit({ playing: true }));
      p.on('resumed', () => emit({ playing: true }));
      p.on('paused', () => emit({ playing: false }));
      p.on('ended', () => emit({ playing: false }));
      p.on('volumechange', (s) => emit({ muted: s.muted }));
      p.on('error', () => emit({ failed: true }));
    })
    .catch(() => emit({ failed: true }));

  return {
    seek: (t) => call((p) => p.seek(t)),
    play: () => call((p) => p.play()),
    pause: () => call((p) => p.pause()),
    setRate: () => {},
    setMuted: (m) => call((p) => (m ? p.mute() : p.unmute())),
    destroy: () => {
      dead = true;
      player?.destroy();
    },
  };
}

// --- HTML5 -----------------------------------------------------------------------------------

export function html5Backend(el: HTMLMediaElement, emit: Emit): Backend {
  const handlers: Array<[string, () => void]> = [
    ['timeupdate', () => emit({ time: el.currentTime })],
    ['seeked', () => emit({ time: el.currentTime })],
    ['playing', () => emit({ playing: true })],
    ['play', () => emit({ playing: true })],
    ['pause', () => emit({ playing: false })],
    ['ended', () => emit({ playing: false })],
    ['durationchange', () => Number.isFinite(el.duration) && emit({ duration: el.duration })],
    ['ratechange', () => emit({ rate: el.playbackRate })],
    ['volumechange', () => emit({ muted: el.muted })],
    ['error', () => emit({ failed: true })],
  ];
  handlers.forEach(([ev, fn]) => el.addEventListener(ev, fn));
  emit({ ready: true, rate: el.playbackRate, muted: el.muted });

  return {
    seek: (t) => {
      el.currentTime = t;
    },
    play: () => {
      void el.play().catch(() => {});
    },
    pause: () => el.pause(),
    setRate: (r) => {
      el.playbackRate = r;
    },
    setMuted: (m) => {
      el.muted = m;
    },
    destroy: () => handlers.forEach(([ev, fn]) => el.removeEventListener(ev, fn)),
  };
}
