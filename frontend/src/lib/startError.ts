import { S } from '@/strings';

/** Refusal of POST /api/jobs as the person sees it: a sentence, and retry only when waiting can help. */
export interface StartError {
  code: string;
  text: string;
  retry: boolean;
}

export function startErrorFor(code: string): StartError {
  const known = S.startErrors[code];
  return known ? { code, ...known } : { code, text: S.startFailed, retry: false };
}
