import type { components } from '../../api/schema';
import { PALETTE, type Tone } from '../../lib/semantics.ts';

export type PeriodKind = components['schemas']['SpecialPeriodKind'];
export type ImportStatus = components['schemas']['ImportStatus'];
export type QualityEventKind = components['schemas']['QualityEventKind'];
export type Mode = components['schemas']['Mode'];

export const PERIOD_KINDS: readonly PeriodKind[] = [
  'commissioning',
  'maintenance',
  'venting',
  'test',
  'vacation',
  'special_use',
];

export const PERIOD_LABEL: Readonly<Record<PeriodKind, string>> = {
  commissioning: 'Opstookprotocol',
  maintenance: 'Onderhoud',
  venting: 'Ontluchten',
  test: 'Test',
  vacation: 'Vakantie',
  special_use: 'Bijzonder gebruik',
};

export const PERIOD_TONE: Readonly<Record<PeriodKind, Tone>> = {
  commissioning: 'orange',
  maintenance: 'slate',
  venting: 'teal',
  test: 'violet',
  vacation: 'blue',
  special_use: 'amber',
};

export const PERIOD_HELP: Readonly<Record<PeriodKind, string>> = {
  commissioning:
    'Nieuwe (vloer)verwarming wordt volgens schema opgestookt. Het gedrag is bewust afwijkend.',
  maintenance: 'Monteur aan het werk; ketel kan aan/uit gaan of op testwaarden staan.',
  venting: 'Radiatoren of vloer ontlucht; pomp en temperaturen gedragen zich tijdelijk anders.',
  test: 'Je probeert zelf iets uit, bijvoorbeeld een andere instelling voor een paar uur.',
  vacation: 'Niemand thuis, thermostaat lager. Weinig warmtevraag is dan normaal.',
  special_use: 'Iets ongewoons, zoals een feest, open ramen bij verbouwing of een kapotte sensor.',
};

export const EVENT_TONE: Readonly<Record<QualityEventKind, Tone>> = {
  data_gap: 'slate',
  stale: 'amber',
  invalid: 'rose',
  implausible: 'amber',
  unavailable: 'slate',
  connection_lost: 'rose',
  counter_reset: 'violet',
  duplicate: 'slate',
  misaligned: 'amber',
};

export const IMPORT_STATUS: Readonly<Record<ImportStatus, { label: string; tone: Tone }>> = {
  pending: { label: 'Wachtend', tone: 'blue' },
  fetching: { label: 'Bezig · ophalen', tone: 'blue' },
  analysing: { label: 'Analyseren', tone: 'violet' },
  done: { label: 'Klaar', tone: 'green' },
  interrupted: { label: 'Onderbroken', tone: 'amber' },
  failed: { label: 'Mislukt', tone: 'rose' },
  cancelled: { label: 'Geannuleerd', tone: 'slate' },
};

export const IMPORT_ACTIVE: readonly ImportStatus[] = ['pending', 'fetching', 'analysing'];

export const SEGMENT_COLOR = {
  connection_lost: PALETTE.rose.base,
  stale: '#f2c14e',
  not_mapped: 'repeating-linear-gradient(45deg,#c3c8d2 0 2px,#f4f5f8 2px 5px)',
} as const;

export const MODE_COLOR: Readonly<Record<Mode, string>> = {
  ch: PALETTE.orange.base,
  dhw: PALETTE.blue.base,
  standby: '#c3c8d2',
  afterrun: '#8a92a3',
  fault_blocking: PALETTE.rose.base,
  unknown: '#e7e9ee',
};
