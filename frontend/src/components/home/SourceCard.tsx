import { typo } from '@/lib/typo';
import { Captions, AudioLines } from 'lucide-react';
import type { ProbeResponse } from '@/api/types';
import { formatTimecode } from '@/lib/timecode';
import { S } from '@/strings';
import { languageName } from '@/lib/settings';
import { LanguageSelect } from './LanguageSelect';

interface Props {
  probe: ProbeResponse;
  language: string;
  onLanguage: (lang: string) => void;
}

/** Mockup 3.2: "we understood you right" card. No buttons: the run lives in the settings under it (step E4). */
export function SourceCard({ probe, language, onLanguage }: Props) {
  const subs = probe.estimate.strategy === 'subtitles';
  const minutes = Math.max(1, Math.round(probe.estimate.seconds / 60));
  return (
    <div className="card">
      <Cover url={probe.thumbnail_url} />
      <div className="card__body">
        <div className="card__title" title={probe.title}>
          {typo(probe.title)}
        </div>
        <div className="card__meta">
          {probe.duration_sec !== null && (
            <span className="mono">{formatTimecode(probe.duration_sec)}</span>
          )}
          <span className="card__dot">·</span>
          <span>{S.platforms[probe.platform] ?? probe.platform}</span>
          <span className="card__dot">·</span>
          <span className="card__lang">
            {languageName(language)}
            <LanguageSelect
              value={language}
              onChange={onLanguage}
              className="lsel--inline"
              label={S.change}
            />
          </span>
        </div>
        <div className="card__subs">
          {subs ? <Captions size={15} /> : <AudioLines size={15} />}
          {subs ? S.subsFound : S.subsNone(minutes)}
        </div>
      </div>
    </div>
  );
}

function Cover({ url }: { url: string | null }) {
  return url ? <img className="card__cover" src={url} alt="" /> : <div className="card__cover" />;
}
