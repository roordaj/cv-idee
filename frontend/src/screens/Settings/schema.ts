import type { components } from '../../api/schema';
export type Values = components['schemas']['AnalysisSettings'];
export interface Parameter {
  title?: string;
  description?: string;
  type?: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  anyOf?: Parameter[];
  'x-unit'?: string;
  'x-step'?: number;
  'x-group'?: string;
  'x-rule'?: string[];
}
export const GROUPS = {
  short_cycles: 'Korte cycli',
  comfort: 'Comfort',
  effect_measurement: 'Effectmeting',
  data: 'Gegevens',
  recovery: 'Herstel',
  costs: 'Kosten',
  display: 'Weergave',
};
export function numericSchema(p: Parameter): Parameter {
  return p.anyOf?.find((x) => x.type === 'number' || x.type === 'integer') ?? p;
}
export function parseNumber(text: string): number | null {
  if (!text.trim()) return null;
  if (!/^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)$/.test(text.trim())) return NaN;
  return Number(text.replace(',', '.'));
}
export function validate(_key: string, text: string, p: Parameter): string | null {
  const n = parseNumber(text);
  const s = numericSchema(p);
  if (n === null) return p.anyOf?.some((x) => x.type === 'null') ? null : 'Vul een waarde in.';
  if (!Number.isFinite(n)) return 'Vul een geldig getal in.';
  if (s.type === 'integer' && !Number.isInteger(n)) return 'Vul een geheel getal in.';
  if ((s.minimum !== undefined && n < s.minimum) || (s.maximum !== undefined && n > s.maximum))
    return `Kies een waarde tussen ${String(s.minimum).replace('.', ',')} en ${String(s.maximum).replace('.', ',')}.`;
  return null;
}
export function display(value: unknown): string {
  return value == null
    ? ''
    : typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean'
      ? String(value).replace('.', ',')
      : '';
}
