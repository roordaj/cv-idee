import { formatPercent, formatTime } from '../lib/format.ts';
import type { Tone } from '../lib/semantics.ts';

/** Header status (design v3 "Live · bijgewerkt 12:00", extended in aanvullingen.md §0.3). */
export type ConnectionStatus =
  | { state: 'live'; updatedAt: Date }
  | { state: 'delayed'; lastDataAt: Date }
  | { state: 'ha-offline'; since: Date }
  | { state: 'app-unreachable' }
  | { state: 'connecting' }
  | { state: 'importing'; progress: number }
  | { state: 'recomputing'; progress: number };

export const STATUS_TONE: Readonly<Record<ConnectionStatus['state'], Tone>> = {
  live: 'green',
  delayed: 'amber',
  'ha-offline': 'rose',
  'app-unreachable': 'rose',
  connecting: 'slate',
  importing: 'blue',
  recomputing: 'violet',
};

export function statusText(status: ConnectionStatus): string {
  switch (status.state) {
    case 'live':
      return `Live · bijgewerkt ${formatTime(status.updatedAt)}`;
    case 'delayed':
      return `Vertraagd · laatste gegevens ${formatTime(status.lastDataAt)}`;
    case 'ha-offline':
      return `Geen verbinding met Home Assistant · sinds ${formatTime(status.since)}`;
    case 'app-unreachable':
      return 'Geen verbinding met CV-analyse';
    case 'connecting':
      return 'Verbinding maken…';
    case 'importing':
      return `Historie importeren · ${formatPercent(status.progress)}`;
    case 'recomputing':
      return `Analyses herberekenen · ${formatPercent(status.progress)}`;
  }
}
