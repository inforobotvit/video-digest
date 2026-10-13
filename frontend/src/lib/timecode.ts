/** `1:02:15` for hours, `4:43` below an hour; seconds are floored (brief: monospace, same everywhere). */
export function formatTimecode(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

/** Human duration for meta lines: `6 мин 12 с`, `48 с`, `1 ч 3 мин`. */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return m > 0 ? `${h} ч ${m} мин` : `${h} ч`;
  if (m > 0) return s > 0 ? `${m} мин ${s} с` : `${m} мин`;
  return `${s} с`;
}

/** Whole minutes for chapter transcript length, never below 1. */
export function minutesRounded(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}

/** Platform URL with the timecode, per docs/result-schema.md section 8. Null for uploads. */
export function platformUrlAt(
  platform: string,
  url: string | null,
  seconds: number,
): string | null {
  if (!url) return null;
  const t = Math.max(0, Math.floor(seconds));
  const sep = url.includes('?') ? '&' : '?';
  if (platform === 'youtube') return `${url}${sep}t=${t}s`;
  if (platform === 'vk' || platform === 'rutube') return `${url}${sep}t=${t}`;
  return url;
}
