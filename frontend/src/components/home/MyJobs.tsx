import { X } from 'lucide-react';
import { onLinkClick } from '@/lib/router';
import { forgetJob, useStoredJobs } from '@/lib/jobsStore';
import { typo } from '@/lib/typo';
import { S } from '@/strings';

const DAY = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' });
const TIME = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' });

/** «Мои задачи» on the home page: the jobs created from this browser (lib/jobsStore). */
export function MyJobs() {
  const jobs = useStoredJobs();
  if (jobs.length === 0) return null;
  return (
    <section className="myjobs" aria-label={S.myJobs}>
      <div className="settings__head">
        <h2 className="settings__title">{S.myJobs}</h2>
        <span className="settings__hint">{S.myJobsHint}</span>
      </div>
      <ul className="myjobs__list">
        {jobs.map((j) => (
          <li key={j.id} className="myjob">
            <a href={`/jobs/${j.id}`} onClick={onLinkClick} className="myjob__link">
              <span className="myjob__title">{typo(j.title)}</span>
              <span className="myjob__meta">
                <span>{formatDate(j.created_at)}</span>
                <span className="myjob__dot">·</span>
                <span className={`myjob__status myjob__status--${j.status}`}>
                  {S.jobStatus[j.status]}
                </span>
              </span>
            </a>
            <button
              type="button"
              className="btn btn--icon myjob__remove"
              onClick={() => forgetJob(j.id)}
              title={S.removeFromList}
              aria-label={S.removeFromList}
            >
              <X size={14} />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function formatDate(iso: string): string {
  const t = Date.parse(iso);
  return Number.isNaN(t) ? '' : `${DAY.format(t)} · ${TIME.format(t)}`;
}
