import { CHART_COLORS } from '../lib/semantics.ts';

export interface LegendItem {
  key: string;
  label: string;
  swatch: 'box' | 'line' | 'dashed' | 'hatch' | 'change';
  color?: string;
}

export const CYCLE_LEGEND: readonly LegendItem[] = [
  { key: 'cv', label: 'Brandperiode CV', swatch: 'box', color: CHART_COLORS.burnCv },
  {
    key: 'short',
    label: 'Kort tijdens vraag',
    swatch: 'box',
    color: CHART_COLORS.shortDuringDemand,
  },
  { key: 'dhw', label: 'Tapwater', swatch: 'box', color: CHART_COLORS.dhw },
  { key: 'flow', label: 'Aanvoer', swatch: 'line', color: CHART_COLORS.flow },
  {
    key: 'setpoint',
    label: 'Gewenste aanvoer',
    swatch: 'dashed',
    color: CHART_COLORS.flowSetpoint,
  },
  { key: 'return', label: 'Retour', swatch: 'line', color: CHART_COLORS.return },
  { key: 'mod', label: 'Modulatie', swatch: 'line', color: CHART_COLORS.modulation },
  { key: 'gap', label: 'Geen gegevens', swatch: 'hatch' },
  { key: 'change', label: 'Wijziging', swatch: 'change' },
];
