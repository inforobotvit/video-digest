import { useEffect, useState } from 'react';
import { ChevronDown, ExternalLink, Pause, Play, Tv, Volume2, VolumeX } from 'lucide-react';
import type { VideoDigestResult } from '@/types/result';
import type { Chapter } from '@/lib/digest';
import { chapterColor } from '@/lib/chapterColors';
import { CAN_RATE, PLATFORM_KINDS, RATES, embedUrl, formatRate } from '@/lib/playback';
import { formatTimecode, platformUrlAt } from '@/lib/timecode';
import type { PlayerApi } from '@/player/usePlayer';
import { S } from '@/strings';
import './player.css';

interface Props {
  result: VideoDigestResult;
  chapters: Chapter[];
  player: PlayerApi;
  /** index of the chapter the player is in */
  current: number;
  /** URL of our mp3 for `audio` playback */
  mediaUrl: string;
  /** mobile (turn 4): strip on top, play · time and chapter · rate · picture below */
  mobile: boolean;
}

/**
 * The bar at the bottom of the result page (directions, turn 5 / 5b): play · time · chapter
 * strip · rate · actions, 72px. Platform players and direct video expand to 176px with the
 * picture on the left; the iframe stays mounted while collapsed so playback continues.
 */
export function Player({ result, chapters, player, current, mediaUrl, mobile }: Props) {
  const { kind, url, has_video } = result.source.playback;
  const platform = PLATFORM_KINDS.has(kind);
  const platformName = S.platforms[kind] ?? kind;
  const src = platform
    ? embedUrl(kind, url, window.location.origin)
    : kind === 'audio'
      ? mediaUrl
      : url;
  const withPicture = platform || (kind === 'direct' && has_video);
  const [open, setOpen] = useState(false);

  // The page reserves room for the bar and toasts sit above it (body[data-player] in CSS).
  useEffect(() => {
    if (!src) return;
    document.body.dataset.player = open ? 'open' : 'strip';
    return () => {
      delete document.body.dataset.player;
    };
  }, [open, src]);

  if (!src) return null;

  const duration = result.source.duration_sec;
  const time = Math.min(Math.max(0, player.state.time), duration);
  const chapter = chapters[current] as Chapter | undefined;
  const color = chapter ? chapterColor(chapter.index) : undefined;
  const left = chapter ? Math.max(0, chapter.part.end - time) : 0;
  const externalUrl = platform
    ? platformUrlAt(result.source.platform, result.source.url, time)
    : null;

  const media = withPicture ? (
    <div className={`player__media ${open ? '' : 'player__media--hidden'}`}>
      {platform ? (
        <iframe
          ref={player.attach}
          src={src}
          title={platformName}
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
          allowFullScreen
        />
      ) : (
        <video ref={player.attach} src={src} controls={open} playsInline preload="metadata" />
      )}
    </div>
  ) : (
    <audio ref={player.attach} src={src} preload="metadata" />
  );

  const timeLabel = (
    <span className="player__time">
      <b>{formatTimecode(time)}</b> <span>/ {formatTimecode(duration)}</span>
    </span>
  );
  const chapterLine = (
    <div className="strip__meta">
      <span className="strip__chapter">
        {open && timeLabel}
        {player.state.failed && <span className="strip__failed">{S.playerFailed}</span>}
        {chapter && !player.state.failed && (
          <>
            <span className="strip__swatch" style={{ background: color }} />
            {chapter.part.title}
          </>
        )}
      </span>
      {chapter && <span className="strip__left">{S.toChapterEnd(formatTimecode(left))}</span>}
    </div>
  );
  const strip = (
    <ChapterStrip chapters={chapters} current={current} time={time} onSeek={player.seek} />
  );
  const external = externalUrl && (
    <a
      className="pbtn pbtn--icon"
      href={externalUrl}
      target="_blank"
      rel="noreferrer"
      title={S.openOnPlatformNamed(platformName)}
      aria-label={S.openOnPlatformNamed(platformName)}
    >
      <ExternalLink size={14} />
    </a>
  );

  const playButton = (
    <button
      type="button"
      className="player__play"
      onClick={player.toggle}
      aria-label={player.state.playing ? S.pause : S.play}
      title={player.state.playing ? S.pause : S.play}
    >
      {player.state.playing ? (
        <Pause size={14} fill="currentColor" strokeWidth={0} />
      ) : (
        <Play size={14} fill="currentColor" strokeWidth={0} />
      )}
    </button>
  );
  const rateButton = CAN_RATE[kind] && (
    <button
      type="button"
      className="pbtn pbtn--mono"
      title={S.speed}
      onClick={() => {
        const i = RATES.indexOf(player.state.rate as (typeof RATES)[number]);
        player.setRate(RATES[(i + 1) % RATES.length]);
      }}
    >
      {formatRate(player.state.rate)}
    </button>
  );
  const muteButton = !platform && (
    <button
      type="button"
      className="pbtn pbtn--ghost"
      onClick={player.toggleMuted}
      aria-label={player.state.muted ? S.unmute : S.mute}
      title={player.state.muted ? S.unmute : S.mute}
    >
      {player.state.muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
    </button>
  );

  if (mobile) {
    const pictureLabel = platform ? S.showPicture : S.showVideo;
    return (
      <div className={`player player--mobile ${open ? 'player--open' : ''}`} data-kind={kind}>
        {media}
        {strip}
        <div className="player__mrow">
          {playButton}
          <div className="player__mid">
            {timeLabel}
            <div className="player__mchapter">
              {player.state.failed && <span className="strip__failed">{S.playerFailed}</span>}
              {chapter && !player.state.failed && (
                <>
                  <span className="strip__swatch" style={{ background: color }} />
                  {chapter.part.title}
                </>
              )}
            </div>
          </div>
          {rateButton}
          {muteButton}
          {withPicture && (
            <button
              type="button"
              className={`pbtn pbtn--icon ${open ? 'pbtn--on' : ''}`}
              onClick={() => setOpen((v) => !v)}
              title={open ? S.collapsePlayer : pictureLabel}
              aria-label={open ? S.collapsePlayer : pictureLabel}
              aria-pressed={open}
            >
              <Tv size={14} />
            </button>
          )}
        </div>
      </div>
    );
  }

  if (open) {
    return (
      <div className="player player--open" data-kind={kind}>
        {media}
        <div className="player__body player__body--open">
          <div className="player__head">
            <div className="player__titles">
              <div className="player__title">{result.source.title}</div>
              <div className="player__hint">
                {platform ? S.platformControls(platformName) : S.directControls}
              </div>
            </div>
            <div className="player__actions">
              <button type="button" className="pbtn" onClick={() => setOpen(false)}>
                <ChevronDown size={14} />
                {S.collapsePlayer}
              </button>
              {external}
            </div>
          </div>
          <div>
            {strip}
            {chapterLine}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="player" data-kind={kind}>
      {media}
      <div className="player__body">
        {playButton}
        {timeLabel}
        <div className="player__strip">
          {strip}
          {chapterLine}
        </div>
        {rateButton}
        {muteButton}
        {withPicture && (
          <>
            <span className="player__sep" />
            <button
              type="button"
              className="pbtn"
              onClick={() => setOpen(true)}
              title={platform ? S.showPicture : S.showVideo}
            >
              <Tv size={14} />
              {platform ? S.showPicture : S.showVideo}
            </button>
            {external}
          </>
        )}
      </div>
    </div>
  );
}

/** The document axis laid horizontally: same colours and proportions as the sidebar (turn 5). */
function ChapterStrip({
  chapters,
  current,
  time,
  onSeek,
}: {
  chapters: Chapter[];
  current: number;
  time: number;
  onSeek: (s: number) => void;
}) {
  return (
    <div className="strip">
      {chapters.map((c) => {
        const state = c.index < current ? 'past' : c.index === current ? 'now' : 'next';
        const pct =
          c.index === current && c.seconds > 0
            ? Math.min(100, Math.max(0, ((time - c.part.start) / c.seconds) * 100))
            : 0;
        return (
          <button
            key={c.index}
            type="button"
            className={`strip__seg strip__seg--${state}`}
            style={
              {
                flexGrow: Math.max(c.seconds, 1),
                '--c': chapterColor(c.index),
              } as React.CSSProperties
            }
            title={`${formatTimecode(c.part.start)} ${c.part.title}`}
            onClick={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              const f = r.width > 0 ? (e.clientX - r.left) / r.width : 0;
              onSeek(c.part.start + Math.min(1, Math.max(0, f)) * c.seconds);
            }}
          >
            {state === 'now' && (
              <>
                <span className="strip__played" style={{ width: `${pct}%` }} />
                <span className="strip__head" style={{ left: `${pct}%` }} />
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}
