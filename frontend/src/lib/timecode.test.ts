import { describe, expect, it } from 'vitest';
import { formatDuration, formatTimecode, platformUrlAt } from './timecode';

describe('formatTimecode', () => {
  it('formats minutes and hours', () => {
    expect(formatTimecode(0)).toBe('0:00');
    expect(formatTimecode(283.4)).toBe('4:43');
    expect(formatTimecode(3735)).toBe('1:02:15');
  });
});

describe('formatDuration', () => {
  it('reads like a human', () => {
    expect(formatDuration(372)).toBe('6 мин 12 с');
    expect(formatDuration(48)).toBe('48 с');
    expect(formatDuration(3780)).toBe('1 ч 3 мин');
  });
});

describe('platformUrlAt', () => {
  it('uses the platform format', () => {
    expect(platformUrlAt('youtube', 'https://www.youtube.com/watch?v=x', 245.9)).toBe(
      'https://www.youtube.com/watch?v=x&t=245s',
    );
    expect(platformUrlAt('vk', 'https://vk.com/video-1_2', 10)).toBe(
      'https://vk.com/video-1_2?t=10',
    );
    expect(platformUrlAt('upload', null, 10)).toBeNull();
  });
});
