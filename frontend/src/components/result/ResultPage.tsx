import { useCallback, useEffect, useMemo, useState } from 'react';
import { useIsMobile, useMediaQuery } from '@/lib/useMediaQuery';
import type { Job } from '@/api/types';
import { api } from '@/api/client';
import type { VideoDigestResult } from '@/types/result';
import { typoResult } from '@/lib/typo';
import {
  buildChapters,
  currentRowKey,
  effectiveDepth,
  partIndexAt,
  type Depth,
} from '@/lib/digest';
import { usePlayer } from '@/player/usePlayer';
import { useReadingChapter } from '@/lib/useReading';
import { Header } from '@/components/Header';
import { Sidebar } from './Sidebar';
import { TocSheet } from './TocSheet';
import { DepthBar } from './DepthBar';
import { TldrBlock } from './TldrBlock';
import { NoticeBand } from './NoticeBand';
import { FeedbackModal } from '@/components/feedback/FeedbackModal';
import { useFeedbackPrompt } from '@/lib/feedback';
import { ChapterBlock } from './ChapterBlock';
import { ExtrasSections } from './ExtrasSections';
import { Player } from '@/components/player/Player';
import './result.css';

export function ResultPage({ job, result: raw }: { job: Job; result: VideoDigestResult }) {
  const result = useMemo(() => typoResult(raw), [raw]);
  const chapters = useMemo(() => buildChapters(result), [result]);
  const [depth, setDepth] = useState<Depth>(() => depthFromUrl());
  const [overrides, setOverrides] = useState<Map<number, Depth>>(new Map());
  // Mobile (turn 4): no sidebar, the table of contents lives in a sheet opened from the sticky bar.
  const mobile = useIsMobile();
  // Below 1100px the margin column is gone and sidenotes sit under their rows.
  const insets = useMediaQuery('(max-width: 1100px)');
  const [tocOpen, setTocOpen] = useState(false);
  const closeToc = useCallback(() => setTocOpen(false), []);

  const setGlobalDepth = (d: Depth) => {
    setDepth(d);
    setOverrides(new Map());
    const url = new URL(window.location.href);
    if (d === 2) url.searchParams.delete('depth');
    else url.searchParams.set('depth', String(d));
    window.history.replaceState(null, '', url);
  };
  const setChapterDepth = useCallback(
    (index: number, d: Depth | null) => {
      setOverrides((prev) => {
        const next = new Map(prev);
        if (d === null || d === depth) next.delete(index);
        else next.set(index, d);
        return next;
      });
    },
    [depth],
  );
  const depths = chapters.map((c) => effectiveDepth(depth, overrides, c.index));

  // One player for the page; every timecode seeks it (brief: "читаю здесь – слушаю здесь").
  const player = usePlayer(result.source.playback.kind);
  const time = player.state.time;
  const current = partIndexAt(result.digest.structure, time);
  const nowRows = chapters.map((c) =>
    c.index === current ? currentRowKey(c, depths[c.index], time) : null,
  );
  // The reading position (scrollspy) is the primary one on the axis; a timecode click seeks the
  // player and pins the reading to the same chapter, so both positions meet there.
  const [reading, pinReading] = useReadingChapter(chapters.length, depths.join(''));
  const structure = result.digest.structure;
  // The survey (step E2): offered by a timer only after the person scrolled or played; the button is always there.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    if (scrolled) return;
    const onScroll = () => setScrolled(true);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [scrolled]);
  const feedback = useFeedbackPrompt(
    job.job_id,
    job.status === 'done',
    scrolled || player.state.started,
  );
  const playerSeek = player.seek;
  const seek = useCallback(
    (seconds: number) => {
      playerSeek(seconds);
      pinReading(partIndexAt(structure, seconds));
    },
    [playerSeek, pinReading, structure],
  );

  return (
    <>
      <Header
        jobId={job.job_id}
        feedback={{ rated: feedback.rated, onOpen: feedback.openManual }}
      />
      <div className="res">
        {!mobile && (
          <Sidebar
            job={job}
            result={result}
            chapters={chapters}
            depths={depths}
            reading={reading}
            time={time}
            current={current}
            mark={player.state.started}
            onPick={pinReading}
          />
        )}
        <main className="res__main">
          <DepthBar
            depth={depth}
            overrides={overrides}
            result={result}
            chapters={chapters}
            reading={reading}
            onChange={setGlobalDepth}
            onReset={() => setOverrides(new Map())}
            onOpenToc={() => setTocOpen(true)}
          />
          <div className="res__doc">
            <TldrBlock text={result.digest.tldr} />
            <NoticeBand notices={result.notices} onSeek={seek} />
            {chapters.map((chapter) => (
              <ChapterBlock
                key={chapter.index}
                chapter={chapter}
                result={result}
                depth={depths[chapter.index]}
                globalDepth={depth}
                nowRow={nowRows[chapter.index]}
                onDepth={setChapterDepth}
                onSeek={seek}
                mobile={mobile}
                insets={insets}
              />
            ))}
          </div>
          <ExtrasSections result={result} onSeek={seek} />
        </main>
      </div>
      <Player
        result={result}
        chapters={chapters}
        player={player}
        current={current}
        mediaUrl={api.mediaUrl(result.source.playback.url)}
        mobile={mobile}
      />
      <FeedbackModal
        open={feedback.open}
        jobId={job.job_id}
        via={feedback.via}
        rated={feedback.rated}
        onClose={feedback.close}
        onAnswered={feedback.markAnswered}
      />
      {mobile && (
        <TocSheet
          open={tocOpen}
          onClose={closeToc}
          result={result}
          chapters={chapters}
          depths={depths}
          reading={reading}
          time={time}
          current={current}
          mark={player.state.started}
          onPick={pinReading}
        />
      )}
    </>
  );
}

/** Reading depth is part of the page state and lives in the URL: /jobs/{id}?depth=1|2|3 (default 2). */
function depthFromUrl(): Depth {
  const d = Number(new URLSearchParams(window.location.search).get('depth'));
  return d === 1 || d === 3 ? d : 2;
}
