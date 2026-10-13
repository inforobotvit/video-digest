import { describe, expect, it } from 'vitest';
import type { ProbeResponse } from '@/api/types';
import {
  estimateMinutes,
  OPTION_ORDER,
  PRESET_EXTRAS,
  PRESET_ORDER,
  switchPreset,
  toggleOption,
  type SettingsValue,
} from './settings';

const probe = {
  estimate: {
    seconds: 300,
    strategy: 'transcribe',
    per_option: { glossary: 15, critique: 30, self_check: 15 },
  },
} as unknown as ProbeResponse;
const base: SettingsValue = {
  preset: 'plain',
  outputLanguage: 'ru',
  options: [],
};

describe('estimateMinutes', () => {
  it('adds the chosen blocks once each; the preset itself adds nothing', () => {
    expect(estimateMinutes(probe, { ...base, options: [] })).toBe(5);
    expect(estimateMinutes(probe, { ...base, preset: 'lecture', options: [] })).toBe(5);
    expect(estimateMinutes(probe, { ...base, options: ['glossary', 'critique'] })).toBe(6); // 300+15+30
    expect(estimateMinutes(probe, { ...base, options: ['critique', 'critique'] })).toBe(6); // duplicate once
  });
});

describe('presets as defaults', () => {
  it('«Просто выжимка» is first and has no defaults; the checkbox order is one for every preset', () => {
    expect(PRESET_ORDER[0]).toBe('plain');
    expect(PRESET_EXTRAS.plain).toEqual([]);
    expect(OPTION_ORDER).toEqual([
      'glossary',
      'critique',
      'self_check',
      'decisions',
      'action_items',
      'questions',
    ]);
    for (const p of PRESET_ORDER)
      expect(PRESET_EXTRAS[p].every((o) => OPTION_ORDER.includes(o))).toBe(true);
  });

  it('switching a preset starts from its defaults and remembers the checkboxes of the one left', () => {
    let v = switchPreset(base, 'lecture');
    expect(v.options).toEqual(['glossary', 'self_check']);
    v = toggleOption(v, 'glossary', false);
    v = toggleOption(v, 'critique', true);
    expect(v.options).toEqual(['self_check', 'critique']);
    v = switchPreset(v, 'meeting');
    expect(v.options).toEqual(['decisions', 'action_items', 'questions']);
    v = switchPreset(v, 'lecture');
    expect(v.options).toEqual(['self_check', 'critique']);
    expect(switchPreset(v, 'lecture')).toBe(v);
  });

  it('toggling is idempotent', () => {
    const v = toggleOption(toggleOption(base, 'glossary', true), 'glossary', true);
    expect(v.options).toEqual(['glossary']);
    expect(toggleOption(v, 'critique', false).options).toEqual(['glossary']);
  });
});
