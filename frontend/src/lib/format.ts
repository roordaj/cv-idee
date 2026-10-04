/**
 * nl-NL formatters (decimal comma, 24h clock, Europe/Amsterdam) as used in design v3.
 * Units are separated from the number by a non-breaking space so "20,4 °C" never wraps.
 */

export const LOCALE = 'nl-NL';
export const TIME_ZONE = 'Europe/Amsterdam';
export const NBSP = ' ';
const EN_DASH = '–';
const PLACEHOLDER = '—';

const numberFormats = new Map<string, Intl.NumberFormat>();

function numberFormat(minDecimals: number, maxDecimals: number): Intl.NumberFormat {
  const key = `${String(minDecimals)}-${String(maxDecimals)}`;
  let fmt = numberFormats.get(key);
  if (!fmt) {
    fmt = new Intl.NumberFormat(LOCALE, {
      minimumFractionDigits: minDecimals,
      maximumFractionDigits: maxDecimals,
    });
    numberFormats.set(key, fmt);
  }
  return fmt;
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** "4,1" — fixed number of decimals, decimal comma, "." as thousands separator. */
export function formatNumber(value: number | null | undefined, decimals = 1): string {
  if (!isFiniteNumber(value)) return PLACEHOLDER;
  return numberFormat(decimals, decimals).format(value);
}

/** "20,4 °C" */
export function formatTemperature(value: number | null | undefined, decimals = 1): string {
  if (!isFiniteNumber(value)) return PLACEHOLDER;
  return `${formatNumber(value, decimals)}${NBSP}°C`;
}

/** "92 %" / "99,3 %" — value is already a percentage (0–100). */
export function formatPercent(value: number | null | undefined, decimals = 0): string {
  if (!isFiniteNumber(value)) return PLACEHOLDER;
  return `${formatNumber(value, decimals)}${NBSP}%`;
}

/** "2:30" — duration in seconds as minutes:seconds (minutes may exceed 59). */
export function formatDuration(seconds: number | null | undefined): string {
  if (!isFiniteNumber(seconds) || seconds < 0) return PLACEHOLDER;
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${String(minutes)}:${String(rest).padStart(2, '0')}`;
}

const timeFormat = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
  timeZone: TIME_ZONE,
});

/** "06:00" — 24h clock in Europe/Amsterdam. */
export function formatTime(date: Date): string {
  return timeFormat.format(date);
}

/** "06:00–12:00" */
export function formatTimeRange(start: Date, end: Date): string {
  return `${formatTime(start)}${EN_DASH}${formatTime(end)}`;
}

type DateParts = Partial<Record<Intl.DateTimeFormatPartTypes, string>>;

function dateParts(date: Date, month: 'short' | 'long', withYear: boolean): DateParts {
  const fmt = new Intl.DateTimeFormat(LOCALE, {
    weekday: 'long',
    day: 'numeric',
    month,
    ...(withYear ? { year: 'numeric' } : {}),
    timeZone: TIME_ZONE,
  });
  const parts: DateParts = {};
  for (const part of fmt.formatToParts(date)) {
    parts[part.type] = part.value;
  }
  return parts;
}

function shortMonth(parts: DateParts): string {
  // ICU may abbreviate as "okt." — the design uses "okt".
  return (parts.month ?? '').replace(/\.$/, '');
}

/** "4 okt" */
export function formatDayMonth(date: Date): string {
  const p = dateParts(date, 'short', false);
  return `${p.day ?? ''} ${shortMonth(p)}`;
}

/** "zondag 4 okt" */
export function formatDateShort(date: Date): string {
  const p = dateParts(date, 'short', false);
  return `${p.weekday ?? ''} ${p.day ?? ''} ${shortMonth(p)}`;
}

/** "zondag 4 oktober 2026" */
export function formatDateLong(date: Date): string {
  const p = dateParts(date, 'long', true);
  return `${p.weekday ?? ''} ${p.day ?? ''} ${p.month ?? ''} ${p.year ?? ''}`;
}

/** "Zondag 4 oktober 2026" — sentence case for headings. */
export function capitalize(text: string): string {
  return text.charAt(0).toLocaleUpperCase(LOCALE) + text.slice(1);
}
