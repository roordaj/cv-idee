export const MODE_LABELS: Record<string, string> = {
  ch: 'cv',
  dhw: 'tapwater',
  standby: 'stand-by',
  afterrun: 'naloop',
  fault_blocking: 'storing/blokkering',
  unknown: 'onbekend',
};
export function modeTableText(table: Record<string, unknown> | null | undefined): string {
  return Object.entries(table ?? {})
    .map(
      ([code, mode]) =>
        `${code} = ${typeof mode === 'string' ? (MODE_LABELS[mode] ?? 'onbekend') : 'onbekend'}`,
    )
    .join('\n');
}
export function parseModeTable(text: string): {
  table: Record<string, string> | null;
  error: string | null;
} {
  const table: Record<string, string> = {};
  const lines = text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length > 100) return { table: null, error: 'Gebruik maximaal 100 statuscodes.' };
  for (const line of lines) {
    const [code, label, ...rest] = line.split('=').map((part) => part.trim());
    const mode = Object.keys(MODE_LABELS).find((key) => MODE_LABELS[key] === label?.toLowerCase());
    if (!code || !mode || rest.length || Object.hasOwn(table, code))
      return {
        table: null,
        error:
          'Gebruik één unieke code per regel: code = cv, tapwater, stand-by, naloop, storing/blokkering of onbekend.',
      };
    table[code] = mode;
  }
  return { table: lines.length ? table : null, error: null };
}
