const formatter = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Europe/Amsterdam',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

export function amsterdamLocalTime(date: Date): string {
  return formatter.format(date).replace(' ', 'T');
}

/** Return actual instants, including both occurrences when the clock goes back. */
export function changeTimeCandidates(localTime: string): string[] {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(localTime)) return [];
  const nominal = Date.parse(`${localTime}:00Z`);
  if (!Number.isFinite(nominal)) return [];
  const candidates: string[] = [];
  for (const offset of [120, 60]) {
    const date = new Date(nominal - offset * 60_000);
    if (amsterdamLocalTime(date) === localTime) candidates.push(date.toISOString());
  }
  return candidates;
}
