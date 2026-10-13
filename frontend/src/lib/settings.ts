import type { OptionKey, Preset, ProbeResponse } from '@/api/types';
import { S } from '@/strings';

/** Extras blocks: every option is a block (the transcript translation flag was removed on 2026-09-17). */
export type Block = OptionKey;

/**
 * Blocks a preset checks by default (docs/result-schema.md, section 6). Since 2026-09-30 a preset is a set of
 * defaults, not a rule: every block can be unchecked, and `options` sent to POST /api/jobs is the final list.
 */
export const PRESET_EXTRAS: Record<Preset, Block[]> = {
  lecture: ['glossary', 'self_check'],
  meeting: ['decisions', 'action_items', 'questions'],
  talk: ['critique'],
  interview: ['questions'],
  plain: [],
};

/**
 * One order of the checkboxes for every preset, so rows never jump on a preset switch: first the blocks about the
 * content itself (glossary, critique, self-check), then the blocks about what follows from it (decisions, action
 * items, open questions). A preset's defaults are visible by their checkmarks, not by their position.
 */
export const OPTION_ORDER: Block[] = [
  'glossary',
  'critique',
  'self_check',
  'decisions',
  'action_items',
  'questions',
];
/** Rows of the preset accordion: «Просто выжимка» first and open by default, then by how often they are used. */
export const PRESET_ORDER: Preset[] = ['plain', 'lecture', 'talk', 'interview', 'meeting'];

export interface SettingsValue {
  preset: Preset;
  outputLanguage: string;
  /** The blocks that will run: the preset's defaults plus or minus what the person changed. */
  options: OptionKey[];
  /** Checkboxes of the presets the person left, so coming back finds them as they were (the sketch keeps them). */
  remembered?: Partial<Record<Preset, OptionKey[]>>;
}

/** Open another preset: keep this one's checkboxes aside, restore the other's or start from its defaults. */
export function switchPreset(v: SettingsValue, preset: Preset): SettingsValue {
  if (preset === v.preset) return v;
  const remembered = { ...(v.remembered ?? {}), [v.preset]: v.options };
  return { ...v, preset, options: remembered[preset] ?? [...PRESET_EXTRAS[preset]], remembered };
}

export function toggleOption(v: SettingsValue, option: OptionKey, on: boolean): SettingsValue {
  const options = on
    ? v.options.includes(option)
      ? v.options
      : [...v.options, option]
    : v.options.filter((o) => o !== option);
  return { ...v, options };
}

/** Estimated seconds: base processing plus the chosen blocks (the front adds per_option, contract section 2). */
export function estimateSeconds(probe: ProbeResponse, options: OptionKey[]): number {
  let sec = probe.estimate.seconds;
  for (const b of new Set(options)) sec += probe.estimate.per_option[b] ?? 0;
  return sec;
}

/** Estimated minutes for «Готово через ~N мин», never below one. */
export function estimateMinutes(probe: ProbeResponse, v: SettingsValue): number {
  return Math.max(1, Math.round(estimateSeconds(probe, v.options) / 60));
}

export function languageName(code: string): string {
  return S.languages[code] ?? code.toUpperCase();
}
