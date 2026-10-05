import type { ShellData } from '../app/shellData.ts';

export function fixtureShellData(now: Date = new Date()): ShellData {
  return {
    openFindings: 5,
    signals: { linked: 9, total: 15 },
    status: { state: 'live', updatedAt: now },
    source: 'CAN-bus via Home Assistant',
    stubData: false,
  };
}
