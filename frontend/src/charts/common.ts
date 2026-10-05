import { CHART_COLORS, PALETTE } from '../lib/semantics.ts';
import type { components } from '../api/schema';

export type TimelineData = components['schemas']['TimelineResponse'];
export type Cycle = components['schemas']['Cycle'];
export type Mode = components['schemas']['Mode'];

export function cycleColor(c: Pick<Cycle, 'mode' | 'short_during_demand'>): string {
  if (c.short_during_demand) return CHART_COLORS.shortDuringDemand;
  return c.mode === 'dhw' ? CHART_COLORS.dhw : CHART_COLORS.burnCv;
}

/** `HATCH` is replaced by the per-chart pattern url. */
export const MODE_FILL: Readonly<Record<Mode, string>> = {
  ch: '#fbd5c1',
  dhw: '#cfe0f7',
  afterrun: '#e7e9ee',
  standby: '#eef0f3',
  fault_blocking: PALETTE.rose.tint,
  unknown: 'HATCH',
};

export const PERIOD_LABEL: Readonly<Record<string, string>> = {
  commissioning: 'Inbedrijfstelling',
  maintenance: 'Onderhoud',
  venting: 'Ontluchten',
  test: 'Test',
  vacation: 'Vakantie',
  special_use: 'Bijzonder gebruik',
};
