import type { components } from '../../api/schema';

export type RoomComfort = components['schemas']['RoomComfort'];
export type ComfortWindow = NonNullable<RoomComfort['windows']>[number];
export type ComfortStatus = RoomComfort['status'];

export const WEEKDAYS = [
  { value: 0, short: 'Ma', label: 'maandag' },
  { value: 1, short: 'Di', label: 'dinsdag' },
  { value: 2, short: 'Wo', label: 'woensdag' },
  { value: 3, short: 'Do', label: 'donderdag' },
  { value: 4, short: 'Vr', label: 'vrijdag' },
  { value: 5, short: 'Za', label: 'zaterdag' },
  { value: 6, short: 'Zo', label: 'zondag' },
] as const;

export const DEFAULT_COMFORT: RoomComfort = {
  status: 'not_configured',
  timezone: 'Europe/Amsterdam',
  windows: [],
};

export function initialComfort(): RoomComfort {
  return { ...DEFAULT_COMFORT, windows: [] };
}

export function initialComfortWindow(): ComfortWindow {
  return {
    kind: 'comfort',
    weekdays: [0, 1, 2, 3, 4, 5, 6],
    start_time: '07:00',
    end_time: '22:30',
    target_temperature_c: 20.5,
  };
}

/** Returns a Dutch validation message when local weekly windows cannot be saved. */
export function validateComfortSchedule(value: RoomComfort): string | null {
  if (value.status !== 'scheduled') return null;
  const windows = value.windows ?? [];
  if (windows.length === 0) return 'Voeg ten minste één comforttijdvak toe.';

  const occupied: { start: number; end: number; label: string }[][] = Array.from(
    { length: 7 },
    () => [],
  );
  for (const window of windows) {
    const start = minutes(window.start_time);
    const end = minutes(window.end_time);
    if (start === null || end === null || start === end)
      return 'Kies geldige, verschillende begin- en eindtijden.';
    if (!Number.isFinite(window.target_temperature_c) || window.target_temperature_c <= 0)
      return 'Het comfortdoel moet hoger zijn dan 0 °C.';
    if (window.weekdays.length === 0) return 'Kies ten minste één dag voor elk tijdvak.';

    for (const day of window.weekdays) {
      if (day < 0 || day > 6) return 'Kies geldige weekdagen.';
      if (end > start) {
        occupied[day]?.push({ start, end, label: window.kind });
      } else {
        occupied[day]?.push({ start, end: 1440, label: window.kind });
        occupied[(day + 1) % 7]?.push({ start: 0, end, label: window.kind });
      }
    }
  }

  for (const day of occupied) {
    const ordered = [...day].sort((a, b) => a.start - b.start || a.end - b.end);
    for (let index = 1; index < ordered.length; index += 1) {
      const previous = ordered[index - 1];
      const current = ordered[index];
      if (previous && current && current.start < previous.end)
        return 'De tijdvakken overlappen. Pas een dag of begin- en eindtijd aan.';
    }
  }
  return null;
}

function minutes(value: string): number | null {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  return hour < 24 && minute < 60 ? hour * 60 + minute : null;
}
