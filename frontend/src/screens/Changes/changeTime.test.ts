import { describe, expect, it } from 'vitest';
import { amsterdamLocalTime, changeTimeCandidates } from './changeTime.ts';

describe('Amsterdam change timestamps', () => {
  it('formats now in Amsterdam independently of the browser timezone', () => {
    expect(amsterdamLocalTime(new Date('2026-07-02T12:34:56Z'))).toBe('2026-07-02T14:34');
    expect(amsterdamLocalTime(new Date('2026-01-02T12:34:56Z'))).toBe('2026-01-02T13:34');
  });

  it('converts summer and winter wall times into exact UTC timestamps', () => {
    expect(changeTimeCandidates('2026-07-02T14:34')).toEqual(['2026-07-02T12:34:00.000Z']);
    expect(changeTimeCandidates('2026-01-02T13:34')).toEqual(['2026-01-02T12:34:00.000Z']);
  });

  it('rejects nonexistent spring times, invalid dates and empty inputs', () => {
    for (const value of ['2026-03-29T02:30', '2026-02-30T12:00', '', 'invalid']) {
      expect(changeTimeCandidates(value)).toEqual([]);
    }
  });

  it('keeps both autumn instants distinct', () => {
    expect(changeTimeCandidates('2026-10-25T02:30')).toEqual([
      '2026-10-25T00:30:00.000Z',
      '2026-10-25T01:30:00.000Z',
    ]);
  });
});
