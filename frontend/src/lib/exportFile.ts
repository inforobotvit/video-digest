import { api } from '@/api/client';
import { ApiError, type ExportFormat } from '@/api/types';
import { toast } from '@/lib/toast';
import { S } from '@/strings';

/**
 * Downloads one export through fetch rather than a plain link: 409 not_ready and 404 need a
 * toast, and a link would show the browser's error page instead. The blob is handed to the
 * browser as a file with the name from Content-Disposition.
 */
export async function downloadExport(jobId: string, format: ExportFormat): Promise<void> {
  const retry = { label: S.retryShort, run: () => void downloadExport(jobId, format) };
  try {
    const { blob, filename } = await api.export(jobId, format);
    saveBlob(blob, filename);
    toast(S.toastFileReady(filename));
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 0;
    if (status === 409) toast(S.toastExportNotReady, { tone: 'error', action: retry });
    else if (status === 404 || status === 410) toast(S.toastExportGone, { tone: 'error' });
    else toast(S.toastExportFailed, { tone: 'error', action: retry });
  }
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Copies the result link; the toast reports either way (c11). */
export async function shareLink(jobId: string): Promise<void> {
  const url = `${window.location.origin}/jobs/${jobId}`;
  try {
    // A clipboard write can hang in an unfocused document; give up after 2 s.
    await Promise.race([
      navigator.clipboard.writeText(url),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 2000)),
    ]);
    toast(S.toastCopied);
  } catch {
    toast(S.toastCopyFailed, {
      tone: 'error',
      action: { label: S.retryShort, run: () => void shareLink(jobId) },
    });
  }
}
