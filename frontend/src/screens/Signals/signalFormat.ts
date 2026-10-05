import type { components } from '../../api/schema';
import type { Tone } from '../../lib/semantics.ts';

export type Signal = components['schemas']['Signal'];
export type HaEntity = components['schemas']['HaEntity'];
export type ValueKind = NonNullable<Signal['value_kind']>;

export const VALUE_KINDS: readonly { value: ValueKind; label: string }[] = [
  { value: 'measured', label: 'Gemeten' },
  { value: 'reported', label: 'Gerapporteerd' },
  { value: 'derived', label: 'Afgeleid' },
  { value: 'estimated', label: 'Geschat' },
];

export const AGE_UNITS = [
  { value: 's', label: 'seconden', factor: 1 },
  { value: 'min', label: 'minuten', factor: 60 },
  { value: 'u', label: 'uur', factor: 3600 },
] as const;
export type AgeUnit = (typeof AGE_UNITS)[number]['value'];

export function formatAge(seconds: number): string {
  if (seconds < 90) return `${String(Math.round(seconds))} s`;
  if (seconds < 5400) return `${String(Math.round(seconds / 60))} min`;
  return `${String(Math.round(seconds / 3600))} u`;
}

export function agePill(signal: Signal): { tone: Tone; text: string } {
  if (signal.state === 'missing') return { tone: 'slate', text: 'ontbreekt' };
  const age = signal.age_s === null ? '' : formatAge(signal.age_s);
  if (signal.state === 'stale') return { tone: 'amber', text: `${age} · te oud`.trim() };
  return { tone: 'green', text: age || 'ok' };
}

/** Largest unit that divides the age exactly, so 30 s stays "30" s and 600 s becomes "10" min. */
export function splitAge(seconds: number | null): { amount: string; unit: AgeUnit } {
  if (seconds === null) return { amount: '', unit: 'min' };
  if (seconds % 3600 === 0) return { amount: String(seconds / 3600), unit: 'u' };
  if (seconds % 60 === 0) return { amount: String(seconds / 60), unit: 'min' };
  return { amount: String(seconds), unit: 's' };
}

export function ageSeconds(amount: string, unit: AgeUnit): number | null {
  const value = Number(amount.trim().replace(',', '.'));
  if (!amount.trim() || !Number.isFinite(value)) return null;
  const factor = AGE_UNITS.find((u) => u.value === unit)?.factor ?? 1;
  return Math.round(value * factor);
}

export function normalise(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

export function isUnavailable(entity: HaEntity): boolean {
  return entity.state === 'unavailable' || entity.state === 'unknown' || !entity.state;
}

export type UnitCheck =
  { kind: 'ok' } | { kind: 'convert'; text: string } | { kind: 'mismatch'; text: string };

/** Compares the entity unit with the unit the signal expects (design additions §3b). */
export function checkUnit(expected: string | null, entity: HaEntity | undefined): UnitCheck {
  const actual = entity?.unit ?? null;
  if (!entity || !expected || !actual || expected === actual) return { kind: 'ok' };
  if (expected === '°C' && actual === '°F')
    return { kind: 'convert', text: 'Wordt omgerekend van °F naar °C.' };
  return {
    kind: 'mismatch',
    text: `Deze entiteit meet in ${actual}, maar dit signaal verwacht ${expected}.`,
  };
}

export function fitsUnit(expected: string | null, entity: HaEntity): boolean {
  if (!expected) return true;
  return entity.unit === expected || (expected === '°C' && entity.unit === '°F');
}
