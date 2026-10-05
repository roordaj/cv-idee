import { Droplet, Info, Repeat, SlidersHorizontal, WifiOff, type LucideIcon } from 'lucide-react';
import type { components } from '../../api/schema';
import { formatDayMonth } from '../../lib/format.ts';
import type { Severity, Tone } from '../../lib/semantics.ts';

type S = components['schemas'];

export const CATEGORY_LABEL: Record<S['Category'], string> = {
  cycles: 'Cycli',
  temperature: 'Temperatuur',
  data_quality: 'Gegevenskwaliteit',
  operating_context: 'Bedrijfscontext',
  hydraulic: 'Hydraulisch',
  comfort: 'Comfort',
  zones: 'Zones',
  consumption: 'Verbruik',
  effect_measurement: 'Effectmeting',
};

const CATEGORY_VISUAL: Partial<Record<S['Category'], { icon: LucideIcon; tone: Tone }>> = {
  cycles: { icon: Repeat, tone: 'orange' },
  effect_measurement: { icon: SlidersHorizontal, tone: 'violet' },
  data_quality: { icon: WifiOff, tone: 'rose' },
  hydraulic: { icon: Droplet, tone: 'blue' },
  operating_context: { icon: Info, tone: 'slate' },
};

export function categoryVisual(category: S['Category']): { icon: LucideIcon; tone: Tone } {
  return CATEGORY_VISUAL[category] ?? { icon: Info, tone: 'slate' };
}

export const SEVERITY_NL: Record<Severity, string> = {
  high: 'Hoog',
  medium: 'Middel',
  low: 'Laag',
  info: 'Info',
};

export const SEVERITY_TONE_MAP: Record<Severity, Tone> = {
  high: 'rose',
  medium: 'amber',
  low: 'blue',
  info: 'slate',
};

export const CERTAINTY_LABEL: Record<S['Certainty'], string> = {
  insufficient_evidence: 'Onvoldoende bewijs',
  preliminary: 'Voorlopig',
  moderate: 'Matig',
  reasonable: 'Redelijk',
  high: 'Hoog',
  high_measured: 'Hoog (gemeten)',
};

export const RELEVANCE_LABEL: Record<S['Relevance'], string> = {
  energy: 'energie',
  comfort: 'comfort',
  operational_stability: 'bedrijfsstabiliteit',
  data_reliability: 'betrouwbaarheid analyses',
};

export const STATUS_TONE: Record<S['RecommendationStatus'], Tone> = {
  open: 'blue',
  accepted: 'teal',
  done: 'green',
  postponed: 'slate',
  rejected: 'slate',
  rollback_triggered: 'rose',
};

export const POSTPONE_DAYS = 7;

/** Status text as shown in design v3 (also used for optimistic updates). */
export function statusText(status: S['RecommendationStatus'], postponedUntil?: Date): string {
  switch (status) {
    case 'open':
      return 'Open';
    case 'accepted':
      return 'Geaccepteerd';
    case 'done':
      return 'Uitgevoerd · evaluatie loopt';
    case 'postponed':
      return `Uitgesteld tot ${formatDayMonth(postponedUntil ?? new Date())}`;
    case 'rejected':
      return 'Afgewezen';
    case 'rollback_triggered':
      return 'Terugdraaicriterium geactiveerd';
  }
}
