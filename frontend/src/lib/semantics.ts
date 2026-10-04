/**
 * Semantic colour mappings from technical plan §3.10 / design v3.
 * Components take a `Tone`; use these maps to pick the tone for a domain value.
 */

export const TONES = [
  'orange',
  'teal',
  'violet',
  'blue',
  'amber',
  'rose',
  'green',
  'slate',
] as const;
export type Tone = (typeof TONES)[number];

export interface ToneSwatch {
  base: string;
  tint: string;
  dark: string;
}

/** Raw palette values (same as tokens.css); for SVG charts that cannot use CSS variables. */
export const PALETTE: Readonly<Record<Tone, ToneSwatch>> = {
  orange: { base: '#ea6a2f', tint: '#fdeee6', dark: '#a2421a' },
  teal: { base: '#1a9e8f', tint: '#e1f4f1', dark: '#0f6b61' },
  violet: { base: '#7c5cd6', tint: '#efeafb', dark: '#563ba8' },
  blue: { base: '#3b7ddd', tint: '#e7effb', dark: '#2659a8' },
  amber: { base: '#d99a12', tint: '#fcf3dc', dark: '#8a6206' },
  rose: { base: '#e0475b', tint: '#fce8eb', dark: '#a92536' },
  green: { base: '#2f9e5b', tint: '#e4f4ea', dark: '#1d6b3c' },
  slate: { base: '#5b6475', tint: '#eef0f3', dark: '#3d4452' },
};

export type Severity = 'high' | 'medium' | 'low' | 'info';

export const SEVERITY_TONE: Readonly<Record<Severity, Tone>> = {
  high: 'rose',
  medium: 'amber',
  low: 'blue',
  info: 'slate',
};

export const SEVERITY_LABEL: Readonly<Record<Severity, string>> = {
  high: 'Hoog',
  medium: 'Middel',
  low: 'Laag',
  info: 'Info',
};

export type RecommendationStatus =
  'open' | 'accepted' | 'postponed' | 'done' | 'rejected' | 'rollback';

export const RECOMMENDATION_STATUS_TONE: Readonly<Record<RecommendationStatus, Tone>> = {
  open: 'blue',
  accepted: 'teal',
  done: 'green',
  postponed: 'slate',
  rejected: 'slate',
  rollback: 'rose',
};

export const RECOMMENDATION_STATUS_LABEL: Readonly<Record<RecommendationStatus, string>> = {
  open: 'Open',
  accepted: 'Geaccepteerd',
  done: 'Uitgevoerd',
  postponed: 'Uitgesteld',
  rejected: 'Afgewezen',
  rollback: 'Terugdraaicriterium geactiveerd',
};

export type AnalysisAvailability = 'available' | 'limited' | 'unavailable';

export const AVAILABILITY_TONE: Readonly<Record<AnalysisAvailability, Tone>> = {
  available: 'green',
  limited: 'amber',
  unavailable: 'slate',
};

export const AVAILABILITY_LABEL: Readonly<Record<AnalysisAvailability, string>> = {
  available: 'Beschikbaar',
  limited: 'Beperkt',
  unavailable: 'Niet beschikbaar',
};

/** Chart series colours (design v3, Cycli legend). */
export const CHART_COLORS = {
  burnCv: PALETTE.orange.base,
  shortDuringDemand: PALETTE.rose.base,
  dhw: PALETTE.blue.base,
  flow: PALETTE.orange.base,
  flowSetpoint: '#8a92a3',
  return: PALETTE.blue.base,
  modulation: PALETTE.violet.base,
  noDataStripe: '#c3c8d2',
  noDataBackground: '#f4f5f8',
  selection: PALETTE.violet.base,
} as const;

/** CSS background for "no data" hatching (design v3 legend swatch). */
export const NO_DATA_PATTERN = `repeating-linear-gradient(45deg, ${CHART_COLORS.noDataStripe} 0 2px, ${CHART_COLORS.noDataBackground} 2px 5px)`;

/** Flow setpoint is drawn grey and dashed. */
export const FLOW_SETPOINT_DASH = '5 4';
