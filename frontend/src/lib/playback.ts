import type { VideoDigestResult } from '@/types/result';

export type Playback = VideoDigestResult['source']['playback'];
export type PlaybackKind = Playback['kind'];

const YT_ID =
  /(?:youtube\.com\/(?:embed\/|watch\?(?:.*&)?v=|shorts\/|live\/|v\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/;
const RUTUBE_ID = /rutube\.ru\/(?:play\/embed|video\/private|video|shorts)\/([0-9a-f]{32})/;
const VK_EXT = /vk(?:video)?\.(?:com|ru)\/video_(?:ext|embed)\.php\?/;
const VK_ID = /vk(?:video)?\.(?:com|ru)\/(?:video|clip)(-?\d+)_(\d+)/;

export const PLATFORM_KINDS: ReadonlySet<PlaybackKind> = new Set(['youtube', 'vk', 'rutube']);

/**
 * URL for the platform iframe. n8n gives an embed URL for YouTube and the page URL for VK and
 * Rutube (n8n debt for step 5); an embed URL is accepted as is, a page URL is
 * converted. Null when the URL cannot be understood: the page then shows no player.
 */
export function embedUrl(kind: PlaybackKind, url: string, origin: string): string | null {
  try {
    if (kind === 'youtube') {
      const m = url.match(YT_ID);
      if (!m) return null;
      const u = new URL(`https://www.youtube.com/embed/${m[1]}`);
      u.searchParams.set('enablejsapi', '1');
      u.searchParams.set('playsinline', '1');
      u.searchParams.set('rel', '0');
      u.searchParams.set('origin', origin);
      return u.toString();
    }
    if (kind === 'rutube') {
      const m = url.match(RUTUBE_ID);
      if (!m) return null;
      const u = new URL(`https://rutube.ru/play/embed/${m[1]}`);
      // Private videos carry their access key in `p`.
      const p = new URL(url).searchParams.get('p');
      if (p) u.searchParams.set('p', p);
      return u.toString();
    }
    if (kind === 'vk') {
      if (VK_EXT.test(url)) {
        const u = new URL(url);
        u.searchParams.set('js_api', '1');
        return u.toString();
      }
      const m = url.match(VK_ID);
      if (!m) return null;
      const u = new URL('https://vk.com/video_ext.php');
      u.searchParams.set('oid', m[1]);
      u.searchParams.set('id', m[2]);
      const hash = new URL(url).searchParams.get('hash');
      if (hash) u.searchParams.set('hash', hash);
      u.searchParams.set('js_api', '1');
      return u.toString();
    }
  } catch {
    return null;
  }
  return null;
}

/** Playback rate is only controllable where the player exposes it. */
export const CAN_RATE: Record<PlaybackKind, boolean> = {
  youtube: true,
  vk: false,
  rutube: false,
  direct: true,
  audio: true,
};

export const RATES = [1, 1.25, 1.5, 2] as const;

export function formatRate(rate: number): string {
  return `${String(rate).replace('.', ',')}×`;
}
