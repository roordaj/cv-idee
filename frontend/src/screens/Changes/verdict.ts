import type { components } from '../../api/schema';
import type { Tone } from '../../lib/semantics.ts';

export type Verdict = components['schemas']['EvaluationVerdict'];

export const VERDICT_TONE: Record<Verdict, Tone> = {
  improved: 'green',
  worsened: 'rose',
  trade_off: 'orange',
  not_attributable: 'slate',
  insufficient_evidence: 'slate',
  pending: 'slate',
};

export const ACTOR_LABEL: Record<components['schemas']['ChangeActor'], string> = {
  user: 'gebruiker',
  installer: 'installateur',
  other: 'anders',
};

export const COMPARABLE_LABEL: Record<components['schemas']['Comparability'], string> = {
  yes: 'Ja',
  limited: 'Beperkt',
  no: 'Nee',
  excluded: 'Uitgesloten',
};

export const COMPARABLE_TONE: Record<components['schemas']['Comparability'], Tone> = {
  yes: 'green',
  limited: 'amber',
  no: 'rose',
  excluded: 'slate',
};

export const ASSESSMENT_TONE: Record<components['schemas']['MetricAssessment'], Tone> = {
  better: 'green',
  worse: 'rose',
  neutral: 'slate',
};

export const PARAMETERS = [
  'Maximale CV-aanvoer',
  'Pompstand',
  'Stooklijn eTwist',
  'Thermostaatprogramma',
  'Verdeler: lusdebiet',
];

const dateTime = new Intl.DateTimeFormat('nl-NL', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
  timeZone: 'Europe/Amsterdam',
});

/** "21 sep 2026 08:30" */
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso)).replace(/\./g, '').replace(',', '').replace(' om ', ' ');
}
