import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { Check } from 'lucide-react';
import type { OptionKey, Preset, ProbeResponse } from '@/api/types';
import { S } from '@/strings';
import { StartErrorNote } from './StartErrorNote';
import type { StartError } from '@/lib/startError';
import {
  estimateMinutes,
  OPTION_ORDER,
  PRESET_ORDER,
  switchPreset,
  toggleOption,
  type SettingsValue,
} from '@/lib/settings';

interface Props {
  probe: ProbeResponse;
  value: SettingsValue;
  onChange: (v: SettingsValue) => void;
  onRun: () => void;
  busy?: boolean;
  error?: StartError | null;
  /** the Turnstile widget (step E3): lives in the run row of the open preset */
  extra?: ReactNode;
}

/**
 * Presets as an accordion (step E4, sketch docs/design/sketches/2026-09-30-preset-accordion.html): one row per
 * preset – radio, title, grey subtitle; the chosen row opens with the option checkboxes (each with its time
 * addition from probe.estimate.per_option), «Запустить» with the total estimate and the Turnstile widget. A preset
 * is a set of defaults, not a rule: any block can be added or removed. Keyboard: the rows are a radiogroup with a
 * roving tabindex – arrows move between rows, Enter or Space opens the focused one; the checkboxes and the button
 * are ordinary controls.
 */
export function PresetAccordion({ probe, value, onChange, onRun, busy, error, extra }: Props) {
  const heads = useRef<(HTMLDivElement | null)[]>([]);
  const focusRow = (i: number) => {
    const n = PRESET_ORDER.length;
    heads.current[((i % n) + n) % n]?.focus();
  };
  const onKey = (e: KeyboardEvent, i: number, p: Preset) => {
    switch (e.key) {
      case 'ArrowDown':
      case 'ArrowRight':
        e.preventDefault();
        focusRow(i + 1);
        break;
      case 'ArrowUp':
      case 'ArrowLeft':
        e.preventDefault();
        focusRow(i - 1);
        break;
      case 'Home':
        e.preventDefault();
        focusRow(0);
        break;
      case 'End':
        e.preventDefault();
        focusRow(PRESET_ORDER.length - 1);
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        onChange(switchPreset(value, p));
        break;
    }
  };
  const minutes = estimateMinutes(probe, value);

  return (
    <div className="acc" role="radiogroup" aria-label={S.presetTitle}>
      {PRESET_ORDER.map((p, i) => {
        const open = p === value.preset;
        const bodyId = `acc-body-${p}`;
        return (
          <div key={p} className={`acc__item ${open ? 'acc__item--open' : ''}`}>
            <div
              ref={(el) => {
                heads.current[i] = el;
              }}
              role="radio"
              aria-checked={open}
              aria-expanded={open}
              aria-controls={bodyId}
              tabIndex={open ? 0 : -1}
              className="acc__head"
              onClick={() => onChange(switchPreset(value, p))}
              onKeyDown={(e) => onKey(e, i, p)}
            >
              <span className="acc__radio">{open && <Check size={11} strokeWidth={3} />}</span>
              <span className="acc__text">
                <span className="acc__title">{S.presetNames[p]}</span>
                <span className="acc__sub">{S.presetDescriptions[p]}</span>
              </span>
            </div>
            {open && (
              <div className="acc__body" id={bodyId}>
                <div className="acc__opts">
                  {OPTION_ORDER.map((o) => (
                    <OptionRow
                      key={o}
                      option={o}
                      on={value.options.includes(o)}
                      addSec={probe.estimate.per_option[o]}
                      onToggle={(on) => onChange(toggleOption(value, o, on))}
                    />
                  ))}
                </div>
                <div className="acc__run">
                  <button
                    type="button"
                    className="btn btn--primary btn--big"
                    onClick={onRun}
                    disabled={busy}
                  >
                    {busy ? S.starting : S.run}
                  </button>
                  <span className="acc__est" aria-live="polite">
                    {S.readyIn(minutes)}
                  </span>
                  {extra}
                </div>
                <StartErrorNote error={error} onRetry={onRun} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function OptionRow({
  option,
  on,
  addSec,
  onToggle,
}: {
  option: OptionKey;
  on: boolean;
  addSec?: number;
  onToggle: (on: boolean) => void;
}) {
  return (
    <label className="acc__opt">
      <input
        type="checkbox"
        className="acc__check"
        checked={on}
        onChange={(e) => onToggle(e.target.checked)}
      />
      <span className={`box ${on ? 'box--on' : ''}`} aria-hidden="true">
        {on && <Check size={12} strokeWidth={3} />}
      </span>
      <span className="acc__opt-title">{S.optionLabels[option].title}</span>
      {addSec !== undefined && addSec > 0 && (
        <span className="acc__opt-add">{S.addTime(addSec)}</span>
      )}
    </label>
  );
}
