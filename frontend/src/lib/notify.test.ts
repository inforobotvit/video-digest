import { describe, expect, it } from 'vitest';
import { canNotify, shouldAsk } from './notify';

describe('notifications', () => {
  it('asks only while the browser has not decided and we have not asked', () => {
    expect(shouldAsk('default', null)).toBe(true);
    expect(shouldAsk('default', 'asked')).toBe(false);
    expect(shouldAsk('default', 'off')).toBe(false);
    expect(shouldAsk('granted', null)).toBe(false);
    expect(shouldAsk('denied', null)).toBe(false);
    expect(shouldAsk('unsupported', null)).toBe(false);
  });

  it('notifies only with an explicit grant', () => {
    expect(canNotify('granted')).toBe(true);
    expect(canNotify('default')).toBe(false);
    expect(canNotify('denied')).toBe(false);
    expect(canNotify('unsupported')).toBe(false);
  });
});
