import { describe, expect, it } from 'vitest';
import {
  initialComfortWindow,
  validateComfortSchedule,
  type ComfortWindow,
  type RoomComfort,
} from './comfortSchedule.ts';

const schedule = (...windows: ComfortWindow[]): RoomComfort => ({
  status: 'scheduled',
  timezone: 'Europe/Amsterdam',
  windows,
});

describe('validateComfortSchedule', () => {
  it('requires a window for a scheduled expectation and allows explicit no expectation', () => {
    expect(validateComfortSchedule(schedule())).toMatch(/ten minste één/);
    expect(
      validateComfortSchedule({ status: 'no_expectation', timezone: 'Europe/Amsterdam' }),
    ).toBeNull();
  });

  it('accepts separate weekly windows and rejects overlaps on a shared weekday', () => {
    const morning = {
      ...initialComfortWindow(),
      weekdays: [0],
      start_time: '06:00',
      end_time: '08:00',
    };
    const afternoon = {
      ...initialComfortWindow(),
      weekdays: [0, 1],
      start_time: '08:00',
      end_time: '10:00',
    };
    expect(validateComfortSchedule(schedule(morning, afternoon))).toBeNull();
    expect(
      validateComfortSchedule(schedule(morning, { ...afternoon, start_time: '07:59' })),
    ).toMatch(/overlappen/);
  });

  it('detects overnight overlap on the following weekday', () => {
    const overnight = {
      ...initialComfortWindow(),
      weekdays: [0],
      start_time: '22:00',
      end_time: '07:00',
    };
    const nextMorning = {
      ...initialComfortWindow(),
      weekdays: [1],
      start_time: '06:30',
      end_time: '08:00',
    };
    expect(validateComfortSchedule(schedule(overnight, nextMorning))).toMatch(/overlappen/);
  });

  it('rejects malformed times, empty days and zero targets', () => {
    expect(
      validateComfortSchedule(schedule({ ...initialComfortWindow(), start_time: '25:00' })),
    ).toMatch(/geldige/);
    expect(validateComfortSchedule(schedule({ ...initialComfortWindow(), weekdays: [] }))).toMatch(
      /ten minste één dag/,
    );
    expect(
      validateComfortSchedule(schedule({ ...initialComfortWindow(), target_temperature_c: 0 })),
    ).toContain('hoger zijn dan 0');
  });
});
