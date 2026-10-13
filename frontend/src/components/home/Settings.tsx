import type { ReactNode } from 'react';
import { LanguageSelect } from './LanguageSelect';
import { PresetAccordion } from './PresetAccordion';
import type { ProbeResponse } from '@/api/types';
import { S } from '@/strings';
import type { StartError } from '@/lib/startError';
import { languageName, type SettingsValue } from '@/lib/settings';

interface Props {
  probe: ProbeResponse;
  sourceLanguage: string;
  value: SettingsValue;
  onChange: (v: SettingsValue) => void;
  onRun: () => void;
  busy?: boolean;
  error?: StartError | null;
  /** the Turnstile widget (step E3), rendered in the run row of the open preset */
  extra?: ReactNode;
}

/** Under the card (brief 3.3, step E4): the result language, then the presets with the run inside. */
export function Settings({
  probe,
  sourceLanguage,
  value,
  onChange,
  onRun,
  busy,
  error,
  extra,
}: Props) {
  return (
    <div className="settings">
      <section className="settings__section">
        <h2 className="settings__title">{S.outputLanguage}</h2>
        <div className="lang">
          <LanguageSelect
            value={value.outputLanguage}
            sourceLanguage={sourceLanguage}
            onChange={(code) => onChange({ ...value, outputLanguage: code })}
            label={S.outputLanguage}
          />
          <span className="settings__hint">{S.videoLanguageIs(languageName(sourceLanguage))}</span>
        </div>
      </section>

      <section className="settings__section">
        <div className="settings__head">
          <h2 className="settings__title">{S.presetTitle}</h2>
          <span className="settings__hint">{S.presetHint}</span>
        </div>
        <PresetAccordion
          probe={probe}
          value={value}
          onChange={onChange}
          onRun={onRun}
          busy={busy}
          error={error}
          extra={extra}
        />
      </section>
    </div>
  );
}
