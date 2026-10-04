import {
  NBSP,
  capitalize,
  formatDateLong,
  formatDateShort,
  formatDayMonth,
  formatDuration,
  formatNumber,
  formatPercent,
  formatTemperature,
  formatTime,
  formatTimeRange,
} from './format.ts';

// 4 Oct 2026 is CEST (UTC+2): 10:00Z is 12:00 in Amsterdam.
const sunday = new Date('2026-10-04T10:00:00Z');

describe('number formatters', () => {
  it('uses a decimal comma', () => {
    expect(formatNumber(4.1)).toBe('4,1');
    expect(formatNumber(2.6, 1)).toBe('2,6');
    expect(formatNumber(5, 0)).toBe('5');
    expect(formatNumber(1234.5, 1)).toBe('1.234,5');
  });

  it('formats temperatures with °C', () => {
    expect(formatTemperature(20.4)).toBe(`20,4${NBSP}°C`);
    expect(formatTemperature(55, 0)).toBe(`55${NBSP}°C`);
  });

  it('formats percentages', () => {
    expect(formatPercent(92)).toBe(`92${NBSP}%`);
    expect(formatPercent(99.3, 1)).toBe(`99,3${NBSP}%`);
  });

  it('renders a dash for missing values', () => {
    expect(formatNumber(null)).toBe('—');
    expect(formatTemperature(undefined)).toBe('—');
    expect(formatPercent(Number.NaN)).toBe('—');
  });
});

describe('formatDuration', () => {
  it('formats seconds as m:ss', () => {
    expect(formatDuration(150)).toBe('2:30');
    expect(formatDuration(59)).toBe('0:59');
    expect(formatDuration(600)).toBe('10:00');
    expect(formatDuration(3725)).toBe('62:05');
  });

  it('rounds to whole seconds and rejects invalid input', () => {
    expect(formatDuration(89.6)).toBe('1:30');
    expect(formatDuration(-1)).toBe('—');
    expect(formatDuration(null)).toBe('—');
  });
});

describe('time and date formatters (Europe/Amsterdam)', () => {
  it('formats times on a 24h clock in Amsterdam time', () => {
    expect(formatTime(sunday)).toBe('12:00');
    expect(formatTime(new Date('2026-10-04T04:00:00Z'))).toBe('06:00');
    expect(formatTime(new Date('2026-01-15T22:05:00Z'))).toBe('23:05');
  });

  it('formats a time range with an en dash', () => {
    expect(formatTimeRange(new Date('2026-10-04T04:00:00Z'), sunday)).toBe('06:00–12:00');
  });

  it('formats dates like the design', () => {
    expect(formatDateShort(sunday)).toBe('zondag 4 okt');
    expect(formatDayMonth(new Date('2026-09-21T10:00:00Z'))).toBe('21 sep');
    expect(formatDateLong(sunday)).toBe('zondag 4 oktober 2026');
    expect(capitalize(formatDateLong(sunday))).toBe('Zondag 4 oktober 2026');
  });

  it('uses the Amsterdam calendar day, not UTC', () => {
    // 23:30Z on 3 Oct is 01:30 on 4 Oct in Amsterdam.
    expect(formatDateShort(new Date('2026-10-03T23:30:00Z'))).toBe('zondag 4 okt');
  });
});
