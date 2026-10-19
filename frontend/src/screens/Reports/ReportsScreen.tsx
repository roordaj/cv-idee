import { useState } from 'react';
import { FileDown, FileText } from 'lucide-react';
import { api, unwrap } from '../../api/client.ts';
import { Card } from '../../components/Card.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { useQuery } from '@tanstack/react-query';
import type { components } from '../../api/schema';
import styles from './Reports.module.css';

type Kind = components['schemas']['ReportPeriodKind'];
type Report = components['schemas']['ReportSnapshot'];

function amsterdamToday(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Amsterdam',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const year = parts.find((part) => part.type === 'year')?.value ?? '1970';
  const month = parts.find((part) => part.type === 'month')?.value ?? '01';
  const day = parts.find((part) => part.type === 'day')?.value ?? '01';
  return `${year}-${month}-${day}`;
}

function addDays(value: string, days: number): string {
  const result = new Date(`${value}T12:00:00Z`);
  result.setUTCDate(result.getUTCDate() + days);
  return result.toISOString().slice(0, 10);
}

function defaultDate(kind: Kind): string {
  const today = amsterdamToday();
  return kind === 'day' ? addDays(today, -1) : addDays(mondayOf(today), -7);
}

function mondayOf(value: string): string {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
  return date.toISOString().slice(0, 10);
}

function useReport(kind: Kind, date: string) {
  return useQuery({
    queryKey: ['report', kind, date],
    queryFn: async () =>
      unwrap(
        await api().POST('/api/reports/{kind}/snapshots', {
          params: { path: { kind } },
          body: { reference_date: date },
        }),
      ),
  });
}

function useReportDelivery(kind: Kind, date: string) {
  return useQuery({
    queryKey: ['report-delivery', kind, date],
    queryFn: async () =>
      unwrap(
        await api().GET('/api/reports/{kind}/delivery-status', {
          params: { path: { kind }, query: { reference_date: date } },
        }),
      ),
    refetchInterval: 30_000,
  });
}

function localDate(value: string): string {
  return new Intl.DateTimeFormat('nl-NL', {
    dateStyle: 'long',
    timeZone: 'Europe/Amsterdam',
  }).format(new Date(value));
}

export function ReportsScreen() {
  const [kind, setKind] = useState<Kind>('day');
  const [selectedDate, setSelectedDate] = useState(() => defaultDate('day'));
  const date = kind === 'week' ? mondayOf(selectedDate) : selectedDate;
  const report = useReport(kind, date);
  const delivery = useReportDelivery(kind, date);
  const base = `/api/reports/${kind}`;
  return (
    <main className={styles.screen}>
      <PageHeader
        title="Rapporten"
        subtitle="Dag- en weekoverzicht van je installatie"
        icon={<FileText size={22} aria-hidden="true" />}
        tone="blue"
      />
      <Card>
        <div className={styles.controls}>
          <label>
            Periode{' '}
            <select
              aria-label="Periode"
              value={kind}
              onChange={(event) => {
                const nextKind = event.target.value as Kind;
                setKind(nextKind);
                setSelectedDate(defaultDate(nextKind));
              }}
            >
              <option value="day">Dag</option>
              <option value="week">Week</option>
            </select>
          </label>
          <label>
            {kind === 'day' ? 'Dag' : 'Datum in de week'}{' '}
            <input
              aria-label={kind === 'day' ? 'Dag' : 'Datum in de week'}
              type="date"
              max={
                kind === 'day'
                  ? addDays(amsterdamToday(), -1)
                  : addDays(mondayOf(amsterdamToday()), -1)
              }
              value={selectedDate}
              onChange={(event) => {
                setSelectedDate(event.target.value);
              }}
            />
          </label>
          {report.data ? (
            <div className={styles.downloads} aria-label="Rapport downloaden">
              {(['html', 'csv', 'pdf'] as const).map((format) => (
                <a
                  key={format}
                  href={`${base}/${format}?snapshot_id=${encodeURIComponent(report.data.id)}`}
                  download
                >
                  <FileDown size={16} aria-hidden="true" /> {format.toUpperCase()}
                </a>
              ))}
            </div>
          ) : null}
        </div>
      </Card>
      {report.isError ? (
        <ErrorCallout
          subject="het rapport"
          onRetry={() => {
            void report.refetch();
          }}
        />
      ) : null}
      {report.isPending ? <p role="status">Rapport wordt geladen…</p> : null}
      {report.data ? <ReportPreview report={report.data.report} /> : null}
      {report.data && delivery.data ? (
        <Card>
          <h2>Verzending via Home Assistant</h2>
          {!delivery.data.enabled ? (
            <p>Niet ingeschakeld. Je kunt het rapport wel blijven bekijken en downloaden.</p>
          ) : !delivery.data.available ? (
            <p>
              Er is geen Home Assistant-meldingsdoel ingesteld. Bekijken en downloaden blijft
              beschikbaar.
            </p>
          ) : delivery.data.error ? (
            <p role="alert">Verzending mislukt: {delivery.data.error}</p>
          ) : delivery.data.status === 'sent' ? (
            <p>Verstuurd via Home Assistant.</p>
          ) : delivery.data.status === 'failed' ? (
            <p role="alert">Verzending mislukt. De app probeert het opnieuw.</p>
          ) : delivery.data.status === 'pending' ? (
            <p>Verzending staat klaar.</p>
          ) : (
            <p>Ingeschakeld; verzending volgt volgens planning.</p>
          )}
        </Card>
      ) : null}
    </main>
  );
}

function ReportPreview({ report }: { report: Report }) {
  const start = new Date(report.period.start);
  const end = new Date(new Date(report.period.end ?? report.period.start).getTime() - 1);
  return (
    <div className={styles.preview}>
      <Card>
        <h2>
          {report.kind === 'day' ? 'Dagrapport' : 'Weekrapport'} · {localDate(start.toISOString())}
          {report.kind === 'week' ? ` – ${localDate(end.toISOString())}` : ''}
        </h2>
        <h3>Gegevensdekking</h3>
        <ul>
          {report.quality.coverage.map((signal) => (
            <li key={signal.name}>
              {signal.name}:{' '}
              {signal.coverage_pct === null
                ? 'niet gekoppeld'
                : `${new Intl.NumberFormat('nl-NL', { maximumFractionDigits: 0 }).format(signal.coverage_pct)}%`}
            </li>
          ))}
        </ul>
        <p>
          {report.cycle_summary.ch_cycles + report.cycle_summary.dhw_cycles} cycli ·{' '}
          {report.findings.length} bevindingen · {report.changes.length} wijzigingen
        </p>
        {report.has_more_cycles ? (
          <p>De download bevat alle cycli; de voorbeeldweergave is beperkt tot 500.</p>
        ) : null}
      </Card>
      <Card>
        <h2>Bevindingen</h2>
        {report.findings.length ? (
          <ul>
            {report.findings.map((item) => (
              <li key={item.id}>
                <strong>{item.title}</strong> · {item.status_text}
              </li>
            ))}
          </ul>
        ) : (
          <p>Geen bevindingen in deze periode.</p>
        )}
      </Card>
      <Card>
        <h2>Open adviezen</h2>
        {report.open_advice.length ? (
          <ul>
            {report.open_advice.map((item) => (
              <li key={item.finding_id}>
                <strong>{item.title}</strong>
                <p>{item.action}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p>Geen open adviezen.</p>
        )}
      </Card>
      <Card>
        <h2>Wijzigingen en evaluaties</h2>
        {report.changes.length ? (
          <ul>
            {report.changes.map((item) => (
              <li key={item.change_id}>
                {item.parameter}: {item.old_value} → {item.new_value}
              </li>
            ))}
          </ul>
        ) : (
          <p>Geen wijzigingen in deze periode.</p>
        )}
      </Card>
    </div>
  );
}
