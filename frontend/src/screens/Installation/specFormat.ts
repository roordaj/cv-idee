import type { components } from '../../api/schema';

export type Specification = components['schemas']['Specification'];
export type SpecStatus = components['schemas']['SpecStatus'];
export type InstallationProfile = components['schemas']['InstallationProfile'];

export const STATUS_OPTIONS: readonly { value: SpecStatus; label: string }[] = [
  { value: 'known', label: 'Bekend' },
  { value: 'unknown', label: 'Onbekend' },
  { value: 'not_applicable', label: 'Niet van toepassing' },
];

const NUMBER = new Intl.NumberFormat('nl-NL', { maximumFractionDigits: 2 });

/**
 * Display text of a specification. Unknown stays explicitly "Onbekend" (FR-03); nothing is ever
 * converted, in particular modulation (%) is not shown as kW.
 */
export function specText(spec: Specification): string {
  if (spec.status === 'unknown') return 'Onbekend';
  if (spec.status === 'not_applicable') return 'n.v.t.';
  if (spec.value === null || spec.value === '') return 'Onbekend';
  const value = typeof spec.value === 'number' ? NUMBER.format(spec.value) : spec.value;
  return spec.unit ? `${value} ${spec.unit}` : value;
}

/** Parses the edit field: a number (comma or point) when it looks like one, otherwise text. */
export function parseSpecValue(text: string): number | string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const numeric = /^-?\d+([.,]\d+)?$/.test(trimmed) ? Number(trimmed.replace(',', '.')) : NaN;
  return Number.isNaN(numeric) ? trimmed : numeric;
}

export function valueToField(value: Specification['value']): string {
  if (value === null) return '';
  return typeof value === 'number' ? String(value).replace('.', ',') : value;
}
