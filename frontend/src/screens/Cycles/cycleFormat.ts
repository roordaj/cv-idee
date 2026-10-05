import type { components } from '../../api/schema';
import { formatDayMonth, formatDuration, formatTime } from '../../lib/format.ts';
import type { Tone } from '../../lib/semantics.ts';

export type Cycle = components['schemas']['Cycle'];

export const END_REASON_TEXT: Record<Cycle['end_reason'], string> = {
  stop_during_demand: 'Stop tijdens vraag',
  demand_ended: 'Einde warmtevraag',
  dhw_ended: 'Einde tapvraag',
  data_gap: 'Datagat',
  undetermined: 'Onbepaald',
};

export const CLASS_LABEL: Record<Cycle['classification'], string> = {
  short: 'Kort',
  normal: 'Normaal',
  excluded: 'Uitgesloten',
  incomplete: 'Onvolledig',
};

export const CLASS_TONE: Record<Cycle['classification'], Tone> = {
  short: 'rose',
  normal: 'green',
  excluded: 'blue',
  incomplete: 'amber',
};

export function formatCycleTime(iso: string, withDay: boolean): string {
  const d = new Date(iso);
  return withDay ? `${formatDayMonth(d)} ${formatTime(d)}` : formatTime(d);
}

export function formatCycleEnd(c: Cycle, withDay: boolean): string {
  return c.end ? formatCycleTime(c.end, withDay) : 'onbekend';
}

export function formatCycleDuration(c: Cycle): string {
  const d = formatDuration(c.duration_s);
  return c.duration_is_lower_bound || !c.end ? `≥ ${d}` : d;
}

/** "2:14 u" — total burn time as hours:minutes. */
export function formatBurnTotal(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  return `${String(Math.floor(minutes / 60))}:${String(minutes % 60).padStart(2, '0')} u`;
}
