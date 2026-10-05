import type { ConnectionStatus } from '../components/connectionStatus.ts';
import { useStatus } from '../api/hooks/system.ts';
import type { components } from '../api/schema';

/** Data the shell needs, derived from `GET /api/status`. */
export interface ShellData {
  /** Open findings (status open or rollback); `null` when unknown. */
  openFindings: number | null;
  signals: { linked: number; total: number } | null;
  status: ConnectionStatus;
  /** Data source label in the header. */
  source: string;
  stubData: boolean;
}

type StatusResponse = components['schemas']['StatusResponse'];

/** Shown while the first status response is pending (graceful loading fallback). */
export const LOADING_SHELL_DATA: ShellData = {
  openFindings: null,
  signals: null,
  status: { state: 'connecting' },
  source: 'Gegevensbron laden…',
  stubData: false,
};

const UNREACHABLE_SHELL_DATA: ShellData = {
  ...LOADING_SHELL_DATA,
  status: { state: 'app-unreachable' },
  source: 'Gegevensbron onbekend',
};

export function connectionStatusFrom(status: StatusResponse): ConnectionStatus {
  const { live, now } = status;
  switch (live.state) {
    case 'live':
      return { state: 'live', updatedAt: new Date(live.last_data_at ?? now) };
    case 'delayed':
      return { state: 'delayed', lastDataAt: new Date(live.last_data_at ?? now) };
    case 'ha_offline':
      return { state: 'ha-offline', since: new Date(live.since ?? now) };
    case 'importing':
      return { state: 'importing', progress: live.progress_pct ?? 0 };
    case 'recomputing':
      return { state: 'recomputing', progress: live.progress_pct ?? 0 };
  }
}

export function shellDataFrom(status: StatusResponse): ShellData {
  return {
    openFindings: status.counts.open_findings,
    signals: { linked: status.counts.signals_linked, total: status.counts.signals_total },
    status: connectionStatusFrom(status),
    source: status.source_text,
    stubData: status.stub_data,
  };
}

/** Shell data from the API, with fallbacks while loading or when the app is unreachable. */
export function useShellData(): ShellData {
  const { data, isError } = useStatus();
  if (data) return shellDataFrom(data);
  return isError ? UNREACHABLE_SHELL_DATA : LOADING_SHELL_DATA;
}
