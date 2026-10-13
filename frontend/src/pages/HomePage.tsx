import { useEffect, useRef, useState } from 'react';
import { api, MOCK } from '@/api/client';
import { ApiError, type CreateJobRequest, type Limits, type ProbeResponse } from '@/api/types';
import { navigate, onLinkClick } from '@/lib/router';
import { reportError } from '@/lib/reportError';
import { S } from '@/strings';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import {
  LinkInput,
  ProbeErrorBanner,
  SourcesLine,
  type LinkState,
} from '@/components/home/LinkInput';
import { startErrorFor, type StartError } from '@/lib/startError';
import { Turnstile, type TurnstileHandle } from '@/components/home/Turnstile';

import { SourceCard } from '@/components/home/SourceCard';
import { Settings } from '@/components/home/Settings';
import { MyJobs } from '@/components/home/MyJobs';
import { estimateMinutes, type SettingsValue } from '@/lib/settings';
import { rememberJob } from '@/lib/jobsStore';
import '@/components/home/home.css';

const ACCEPT = '.mp4,.mov,.mkv,.webm,.mp3,.m4a,.wav,.ogg,.flac';

/**
 * One scrolling page: field → card → result language → presets → run (brief 3.1–3.3, step E4). State lives
 * here, components are dumb. The card confirms the source; the only run button is in the settings below it.
 */
export function HomePage() {
  const [link, setLink] = useState<LinkState>({ kind: 'empty' });
  const [probe, setProbe] = useState<ProbeResponse | null>(null);
  const [language, setLanguage] = useState('ru');
  const [settings, setSettings] = useState<SettingsValue>({
    preset: 'plain',
    outputLanguage: 'ru',
    options: [],
  });
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<StartError | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // The limits the page prints (sources line, size error) and checks before an upload come from GET /api/limits,
  // never from a constant here (step E4): until they arrive, or if the call fails, the form works without the
  // numbers and the server refuses what it refuses.
  const [limits, setLimits] = useState<Limits | null>(null);
  useEffect(() => {
    let alive = true;
    api.limits().then(
      (l) => alive && setLimits(l),
      (e: unknown) => reportError('limits', e),
    );
    return () => {
      alive = false;
    };
  }, []);

  const applyProbe = (p: ProbeResponse, url: string) => {
    const lang = p.language ?? 'ru';
    setProbe(p);
    setLanguage(lang);
    setSettings((s) => ({ ...s, outputLanguage: lang }));
    setLink({ kind: 'probed', url });
  };
  const fail = (e: unknown, url: string) => {
    const code = e instanceof ApiError ? e.code : 'generic';
    const maxDurationSec = e instanceof ApiError ? e.maxDurationSec : undefined;
    reportError(S.probeStage, e, { url });
    setLink({ kind: 'error', url, code, stage: S.probeStage, maxDurationSec });
  };

  const submit = async () => {
    if (link.kind !== 'ready') return;
    const url = link.url.trim();
    setLink({ kind: 'checking', url });
    try {
      applyProbe(await api.probe(url), url);
    } catch (e) {
      fail(e, url);
    }
  };
  const uploadRef = useRef(0);
  const onFile = async (file: File) => {
    // Refusing here spares the person a full upload that nginx would cut with 413 at the end; without the limits
    // the check is skipped and the server answers.
    if (limits && file.size > limits.upload_max_mb * 1024 * 1024) {
      fail(new ApiError(413, 'file_too_large', 'file exceeds UPLOAD_MAX_MB'), file.name);
      return;
    }
    const ticket = ++uploadRef.current;
    setProbe(null);
    setLink({ kind: 'uploading', name: file.name, size: file.size, fraction: 0 });
    try {
      const probe = await api.upload(file, (fraction) => {
        if (uploadRef.current === ticket)
          setLink({ kind: 'uploading', name: file.name, size: file.size, fraction });
      });
      if (uploadRef.current === ticket) applyProbe(probe, file.name);
    } catch (e) {
      if (uploadRef.current === ticket) fail(e, file.name);
    }
  };
  const cancelUpload = () => {
    uploadRef.current += 1;
    setLink({ kind: 'empty' });
  };
  /** «Изменить ссылку»: the card and the form below belong to the old source, so they go until the next probe. */
  const edit = () => {
    setProbe(null);
    setStartError(null);
    setLink({
      kind: 'ready',
      url: link.kind === 'error' || link.kind === 'probed' ? link.url : '',
    });
  };

  // Turnstile (step E3): one widget on the run form, its token goes with POST /api/jobs; the widget is reset
  // after every attempt because a token is single-use. No widget or no token: the request goes without it.
  const turnstile = useRef<TurnstileHandle>(null);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const run = async () => {
    if (!probe) return;
    setStarting(true);
    setStartError(null);
    const body: CreateJobRequest = {
      source_id: probe.source_id,
      source_language: language,
      preset: settings.preset,
      output_language: settings.outputLanguage,
      options: settings.options,
      ...(turnstileToken ? { turnstile_token: turnstileToken } : {}),
    };
    turnstile.current?.reset();
    try {
      const job = await api.createJob(body, estimateMinutes(probe, settings) * 60);
      rememberJob({ id: job.job_id, title: probe.title, created_at: new Date().toISOString() });
      navigate(`/jobs/${job.job_id}`);
    } catch (e) {
      reportError('create_job', e);
      setStartError(startErrorFor(e instanceof ApiError ? e.code : 'generic'));
      setStarting(false);
    }
  };

  return (
    <>
      <Header variant="home" />
      <main className={`home ${probe ? 'home--card' : ''}`}>
        <h1 className="home__title">{S.homeHeading}</h1>
        <LinkInput
          state={link}
          limits={limits}
          onChange={(url) => setLink(url.trim() ? { kind: 'ready', url } : { kind: 'empty' })}
          onSubmit={submit}
          onFile={onFile}
          onEdit={edit}
          onCancelUpload={cancelUpload}
        />
        <p className="upload-note">
          {S.uploadNote}{' '}
          <a href="/policy" onClick={onLinkClick}>
            {S.uploadNoteLink}
          </a>
        </p>
        {link.kind === 'error' && (
          <ProbeErrorBanner
            code={link.code}
            maxDurationSec={link.maxDurationSec}
            uploadMaxMb={limits?.upload_max_mb}
            onUpload={() => fileRef.current?.click()}
          />
        )}
        {!probe && <SourcesLine limits={limits} />}
        {!probe && MOCK && <p className="home__mock">{S.fixtureLinks}</p>}
        {!probe && <MyJobs />}
        {probe && (
          <>
            <SourceCard probe={probe} language={language} onLanguage={setLanguage} />
            <Settings
              probe={probe}
              sourceLanguage={language}
              value={settings}
              onChange={setSettings}
              onRun={run}
              busy={starting}
              error={startError}
              extra={<Turnstile ref={turnstile} onToken={setTurnstileToken} />}
            />
          </>
        )}
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
        />
      </main>
      <Footer />
    </>
  );
}
