import { useEffect, useState } from 'react';
import { api } from '@/api/client';
import { ApiError } from '@/api/types';
import { navigate } from '@/lib/router';
import { reportError, reportJobError } from '@/lib/reportError';
import { useJob } from '@/lib/usePolling';
import { rememberJob, storedStatus, updateJob } from '@/lib/jobsStore';
import { useNotifyOnFinish } from '@/lib/notify';
import { S } from '@/strings';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { ResultPage } from '@/components/result/ResultPage';
import { JobCard, JobErrorView, WaitingView } from '@/components/job/WaitingView';
import { ExpiredPage, NotFoundPage } from './ServicePages';

/** /jobs/{id}: polls the job; waiting, failed, expired and done all live here (brief 3.4–3.6). */
export function JobPage({ id }: { id: string }) {
  const state = useJob(id);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  // Browser notification if the job finishes while the tab is in the background (lib/notify).
  useNotifyOnFinish(state.kind === 'ready' ? state.job : null);

  // «Мои задачи»: refresh the stored title and status when this job is in the list.
  useEffect(() => {
    // An expired job has no title any more: the one stored at creation stays, only the status moves.
    if (state.kind === 'ready')
      updateJob(id, {
        ...(state.job.source.title ? { title: state.job.source.title } : {}),
        status: storedStatus(state.job),
      });
  }, [id, state]);

  // A failed job: stage, code and message go to the console once, the screen shows only the sentence.
  const failedJob = state.kind === 'ready' && state.job.status === 'failed' ? state.job : null;
  const failedKey = failedJob ? `${failedJob.job_id}:${failedJob.error?.code ?? ''}` : null;
  useEffect(() => {
    if (failedJob) reportJobError(failedJob);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per job and code, not per poll
  }, [failedKey]);

  const retry = async () => {
    setRetrying(true);
    setRetryError(null);
    try {
      const next = await api.retry(id);
      if (state.kind === 'ready')
        rememberJob({
          id: next.job_id,
          title: state.job.source.title ?? S.expiredJobTitle,
          created_at: new Date().toISOString(),
        });
      navigate(`/jobs/${next.job_id}`);
    } catch (e) {
      const code = e instanceof ApiError ? e.code : 'generic';
      reportError('retry', e, { job_id: id });
      setRetryError(code === 'source_gone' ? S.jobErrors.source_gone.text : S.retryFailed);
      setRetrying(false);
    }
  };

  if (state.kind === 'missing') return <NotFoundPage path={`/jobs/${id}`} />;
  if (state.kind === 'ready' && state.job.status === 'done') {
    if (state.job.result) return <ResultPage job={state.job} result={state.job.result} />;
    return (
      <ExpiredPage job={state.job} onRetry={retry} retrying={retrying} retryError={retryError} />
    );
  }
  return (
    <>
      <Header variant="home" bordered />
      <main className="job">
        {state.kind === 'loading' && <p className="page__hint">{S.loading}</p>}
        {state.kind === 'error' && <p className="page__hint">{S.errorGeneric}</p>}
        {state.kind === 'ready' && (
          <>
            <JobCard job={state.job} />
            {state.job.status === 'failed' ? (
              <JobErrorView
                job={state.job}
                onRetry={retry}
                onOther={() => navigate('/')}
                retrying={retrying}
                retryError={retryError}
              />
            ) : (
              <WaitingView job={state.job} />
            )}
          </>
        )}
      </main>
      <Footer />
    </>
  );
}
