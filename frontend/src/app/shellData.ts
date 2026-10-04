import type { ConnectionStatus } from '../components/connectionStatus.ts';

/** Data the shell needs; mocked until the API client lands (#11). */
export interface ShellData {
  /** Open findings (status open or rollback); `null` when unknown. */
  openFindings: number | null;
  signals: { linked: number; total: number } | null;
  status: ConnectionStatus;
  /** Data source label in the header. */
  source: string;
  stubData: boolean;
}

export function mockShellData(now: Date = new Date()): ShellData {
  return {
    openFindings: 5,
    signals: { linked: 9, total: 15 },
    status: { state: 'live', updatedAt: now },
    source: 'CAN-bus via Home Assistant',
    stubData: false,
  };
}
