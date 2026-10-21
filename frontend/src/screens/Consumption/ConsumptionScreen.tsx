import { useMemo, useState } from 'react';
import { Flame, Info, Scale, ShieldAlert } from 'lucide-react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import type { components } from '../../api/schema';
import { api, unwrap, type RequestBody } from '../../api/client.ts';
import { Button } from '../../components/Button.tsx';
import { Callout } from '../../components/Callout.tsx';
import { Card } from '../../components/Card.tsx';
import { EmptyState } from '../../components/EmptyState.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { PageHeader } from '../../components/PageHeader.tsx';
import { Pill } from '../../components/Tag.tsx';
import { formatNumber, formatPercent, formatTemperature } from '../../lib/format.ts';
import styles from './Consumption.module.css';

type Candidate = components['schemas']['ConsumptionPeriodCandidate'];
type Reason = components['schemas']['ConsumptionComparisonReason'];
const DASH = '—';

const REASON_TEXT: Record<Reason, string> = {
  no_valid_period: 'Geen geldige meetperiode',
  no_meter: 'Geen gasmeter gekoppeld',
  unknown_meter_scope: 'Meterscope onbekend',
  meter_mismatch: 'Andere meterbron',
  mapping_changed: 'Signaalkoppeling gewijzigd',
  scope_changed: 'Meterscope gewijzigd',
  unit_mismatch: 'Eenheid verschilt',
  duration_mismatch: 'Periodelengte verschilt',
  low_coverage: 'Onvoldoende meetdekking',
  counter_reset: 'Tellerreset in periode',
  data_gap: 'Datagat in periode',
  excluded_period: 'Uitgesloten bijzondere periode',
  weather_out_of_range: 'Weer valt buiten de vergelijkingsgrens',
  weather_limited: 'Weer beperkt vergelijkbaar',
  setpoint_mismatch: 'Setpointprofiel verschilt',
  setpoint_unknown: 'Setpointprofiel onbekend',
  use_context_unknown: 'Koken, tapwater of ander gebruik onbekend',
};

function dateInAmsterdam(date: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Amsterdam',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function addDays(date: string, amount: number): string {
  const [year = 0, month = 1, day = 1] = date.split('-').map(Number);
  const value = new Date(Date.UTC(year, month - 1, day + amount));
  return value.toISOString().slice(0, 10);
}

function amsterdamMidnight(date: string): string {
  const [year = 0, month = 1, day = 1] = date.split('-').map(Number);
  const guess = Date.UTC(year, month - 1, day);
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Amsterdam',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(guess));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((item) => item.type === type)?.value ?? 0);
  const localAsUtc = Date.UTC(
    part('year'),
    part('month') - 1,
    part('day'),
    part('hour'),
    part('minute'),
    part('second'),
  );
  return new Date(guess - (localAsUtc - guess)).toISOString();
}

function rangeLabel(range: Candidate['range']): string {
  const format = new Intl.DateTimeFormat('nl-NL', {
    dateStyle: 'medium',
    timeZone: 'Europe/Amsterdam',
  });
  return `${format.format(new Date(range.start))} – ${format.format(new Date(range.end ?? range.start))}`;
}

function statusLabel(status: Candidate['status']): string {
  return status === 'available'
    ? 'Beschikbaar'
    : status === 'limited'
      ? 'Beperkt'
      : 'Niet beschikbaar';
}

function meterScope(value: Candidate['meter_scope']): string {
  if (value === 'whole_house') return 'Hele woning';
  if (value === 'boiler_only') return 'Alleen ketel';
  return 'Onbekend';
}

export function ConsumptionScreen() {
  const today = dateInAmsterdam(new Date());
  const [fromDate, setFromDate] = useState(() => addDays(today, -7));
  const [throughDate, setThroughDate] = useState(() => addDays(today, -1));
  const [selected, setSelected] = useState('');
  const from = amsterdamMidnight(fromDate);
  const to = amsterdamMidnight(addDays(throughDate, 1));
  const durationDays =
    (Date.parse(`${addDays(throughDate, 1)}T00:00:00Z`) - Date.parse(`${fromDate}T00:00:00Z`)) /
    86_400_000;
  const validRange =
    fromDate <= throughDate && durationDays <= 31 && to <= new Date().toISOString();
  const candidates = useQuery({
    queryKey: ['consumption-candidates', from, to],
    enabled: validRange,
    queryFn: async () =>
      unwrap(
        await api().GET('/api/consumption/comparison/candidates', {
          params: { query: { from, to, limit: 30, offset: 0 } },
        }),
      ),
  });
  const comparison = useMutation({
    mutationFn: async (body: RequestBody<'/api/consumption/comparison', 'post'>) =>
      unwrap(await api().POST('/api/consumption/comparison', { body })),
  });
  const available = useMemo(
    () => (candidates.data?.candidates ?? []).filter((item) => item.status !== 'unavailable'),
    [candidates.data?.candidates],
  );
  const selectedCandidate = available.find(
    (item) => `${item.range.start}/${item.range.end ?? ''}` === selected,
  );

  const runComparison = () => {
    if (!selectedCandidate?.range.end) return;
    comparison.mutate({
      observation: { start: from, end: to },
      reference: { start: selectedCandidate.range.start, end: selectedCandidate.range.end },
    });
  };

  const result = comparison.data;
  const resultReasons = result?.reasons ?? [];

  return (
    <div className={styles.screen}>
      <PageHeader
        title="Gasverbruik"
        subtitle="Ruwe meterstanden en een beschrijvende vergelijking · zonder weerscorrectie"
        icon={<Flame size={ICON_SIZE} aria-hidden="true" />}
        tone="orange"
        actions={
          candidates.data ? (
            <Pill
              tone={
                candidates.data.observation_data.consumption_availability === 'available'
                  ? 'teal'
                  : candidates.data.observation_data.consumption_availability === 'limited'
                    ? 'amber'
                    : 'slate'
              }
              size="sm"
            >
              Verbruik {statusLabel(candidates.data.observation_data.consumption_availability)}
            </Pill>
          ) : null
        }
      />

      <div className={styles.grid}>
        <Card padding="md" className={styles.card}>
          <h2 className={styles.heading}>Gemeten gas</h2>
          {candidates.isError ? (
            <ErrorCallout subject="de meetperioden" onRetry={() => void candidates.refetch()} />
          ) : candidates.data ? (
            <>
              <div className={styles.metric}>
                {formatNumber(candidates.data.observation_data.consumption_m3, 3)} <span>m³</span>
              </div>
              <dl className={styles.details}>
                <dt>Beschikbaarheid meting</dt>
                <dd>{statusLabel(candidates.data.observation_data.consumption_availability)}</dd>
                <dt>Meterbron</dt>
                <dd>
                  {candidates.data.observation_data.meter_entity_id ??
                    'Niet gekoppeld of geen meetpunten'}
                </dd>
                <dt>Meterscope</dt>
                <dd>{meterScope(candidates.data.observation_data.meter_scope)}</dd>
                <dt>Eenheid</dt>
                <dd>{candidates.data.observation_data.unit ?? DASH}</dd>
                <dt>Meterstand</dt>
                <dd>
                  {formatNumber(candidates.data.observation_data.counter_start, 3)} →{' '}
                  {formatNumber(candidates.data.observation_data.counter_end, 3)} m³
                </dd>
                <dt>Dekking</dt>
                <dd>{formatPercent(candidates.data.observation_data.coverage_pct, 1)}</dd>
              </dl>
              <Link to="/installatie" className={styles.linkButton}>
                Bekijk installatieprofiel
              </Link>
              <p className={styles.muted}>
                {candidates.data.observation_data.meter_entity_id
                  ? candidates.data.observation_data.meter_scope === 'whole_house'
                    ? 'Deze woningmeter kan ook koken en tapwater omvatten; totaal gasverbruik wordt niet aan ruimteverwarming toegeschreven.'
                    : candidates.data.observation_data.meter_scope === 'boiler_only'
                      ? 'Een ketelmeter kan ook tapwater omvatten; totaal gasverbruik wordt niet als ruimteverwarming gepresenteerd.'
                      : 'Leg in het installatieprofiel vast wat deze meter meet voordat perioden worden vergeleken.'
                  : 'Koppel een cumulatieve gasmeter en leg vast of deze alleen de ketel of de hele woning meet.'}
              </p>
            </>
          ) : (
            <p className={styles.muted}>Meetbasis wordt opgehaald…</p>
          )}
        </Card>

        <Card padding="md" className={styles.card}>
          <div className={styles.cardHead}>
            <h2 className={styles.heading}>Vergelijk perioden</h2>
            {candidates.data ? (
              <Pill tone={candidates.data.status === 'unavailable' ? 'slate' : 'amber'} size="sm">
                {statusLabel(candidates.data.status)}
              </Pill>
            ) : null}
          </div>
          {candidates.isLoading ? (
            <p className={styles.muted}>Historische perioden worden opgehaald…</p>
          ) : null}
          {candidates.data && available.length > 0 ? (
            <>
              <label className={styles.field}>
                Historische periode
                <select
                  aria-label="Historische referentieperiode"
                  value={selected}
                  onChange={(event) => {
                    setSelected(event.target.value);
                    comparison.reset();
                  }}
                >
                  <option value="">Selecteer een periode</option>
                  {available.map((item) => (
                    <option
                      key={`${item.range.start}/${item.range.end ?? ''}`}
                      value={`${item.range.start}/${item.range.end ?? ''}`}
                    >
                      {rangeLabel(item.range)} · {statusLabel(item.status)}
                    </option>
                  ))}
                </select>
              </label>
              <Button
                variant="primary"
                disabled={!selectedCandidate || comparison.isPending}
                onClick={runComparison}
              >
                Vergelijk geselecteerde periode
              </Button>
            </>
          ) : candidates.data ? (
            <EmptyState
              icon={<Scale size={ICON_SIZE} aria-hidden="true" />}
              title="Geen vergelijkbare periode beschikbaar"
              headingLevel={3}
            >
              Er is geen historische periode met dezelfde meetbasis en voldoende dekking.
              {candidates.data.reasons.length
                ? ` ${candidates.data.reasons.map((reason) => REASON_TEXT[reason]).join(' · ')}.`
                : null}
            </EmptyState>
          ) : null}
          {candidates.data?.candidates.some((item) => item.status === 'unavailable') ? (
            <details className={styles.excluded}>
              <summary>
                Uitgesloten perioden (
                {candidates.data.candidates.filter((item) => item.status === 'unavailable').length})
              </summary>
              <ul>
                {candidates.data.candidates
                  .filter((item) => item.status === 'unavailable')
                  .map((item) => (
                    <li key={`${item.range.start}/${item.range.end ?? ''}`}>
                      <strong>{rangeLabel(item.range)}</strong>:{' '}
                      {item.reasons.map((reason) => REASON_TEXT[reason]).join(' · ')}
                    </li>
                  ))}
              </ul>
            </details>
          ) : null}
        </Card>

        <Card padding="md" className={styles.card}>
          <h2 className={styles.heading}>Rendement en kosten</h2>
          <StatusLine
            label="Rendement"
            value={statusLabel(candidates.data?.efficiency_availability ?? 'unavailable')}
          />
          <p className={styles.muted}>
            Zonder gevalideerde meting van geleverde warmte en systeemgrens is rendement niet
            beschikbaar.
          </p>
          <StatusLine
            label="Gaskosten"
            value={statusLabel(candidates.data?.cost_availability ?? 'unavailable')}
          />
          <p className={styles.muted}>
            Kosten zijn alleen beschikbaar met een toepasselijke ingestelde gasprijs. Zonder die
            basis wordt geen eurobedrag getoond.
          </p>
        </Card>
      </div>

      <Card padding="md" className={styles.card}>
        <div>
          <h2 className={styles.heading}>Meterdekking en datakwaliteit</h2>
          <p className={styles.muted}>
            Schematische uitleg van herkenbare toestanden · geen meetreeks
          </p>
        </div>
        <div
          className={styles.coverageTrack}
          role="img"
          aria-label="Schematische meterreeks met onbekend interval en tellerreset; geen meetreeks"
        >
          <span className={styles.coverageSegment} />
          <span className={styles.gapSegment} />
          <span className={styles.coverageSegment} />
          <span className={styles.resetMarker} />
          <span className={styles.coverageSegment} />
        </div>
        <div className={styles.legend}>
          <span>
            <i className={styles.coverageDot} />
            Dekking beschikbaar
          </span>
          <span>
            <i className={styles.gapDot} />
            Gearceerd: onbekend interval
          </span>
          <span>
            <i className={styles.resetDot} />
            Rode markering: tellerreset
          </span>
          <span>
            <i className={styles.staleDot} />
            Verouderd: apart gemeld
          </span>
        </div>
        <p className={styles.muted}>
          Een reset start een nieuw tel-segment; het verschil over de reset wordt niet berekend.
          Verouderde standen verlengen de dekking niet. Onbekende intervallen blijven onbekend.
        </p>
      </Card>

      <Card padding="md" className={styles.card}>
        <div>
          <h2 className={styles.heading}>Periode en omstandigheden</h2>
          <p className={styles.muted}>
            Kies een observatieperiode; context helpt verschillen te duiden, maar corrigeert het
            gemeten verbruik niet.
          </p>
        </div>
        <div className={styles.dateGrid}>
          <label className={styles.field}>
            Van
            <input
              aria-label="Start observatieperiode"
              type="date"
              value={fromDate}
              max={throughDate}
              onChange={(event) => {
                setFromDate(event.target.value);
                setSelected('');
                comparison.reset();
              }}
            />
          </label>
          <label className={styles.field}>
            Tot en met
            <input
              aria-label="Einde observatieperiode"
              type="date"
              value={throughDate}
              max={addDays(today, -1)}
              min={fromDate}
              onChange={(event) => {
                setThroughDate(event.target.value);
                setSelected('');
                comparison.reset();
              }}
            />
          </label>
        </div>
        {!validRange ? (
          <p className={styles.muted}>
            Kies een volledige, verstreken periode van maximaal 31 dagen.
          </p>
        ) : null}
        <ContextTable
          reference={result?.reference ?? selectedCandidate}
          observation={result?.observation ?? candidates.data?.observation_data}
        />
      </Card>

      {comparison.isError ? (
        <ErrorCallout subject="de periodevergelijking" onRetry={runComparison} />
      ) : null}
      {result ? (
        <Card padding="md" className={styles.card}>
          <div className={styles.cardHead}>
            <h2 className={styles.heading}>Geselecteerde periodevergelijking</h2>
            <Pill
              tone={
                result.status === 'available'
                  ? 'teal'
                  : result.status === 'limited'
                    ? 'amber'
                    : 'slate'
              }
              size="sm"
            >
              {statusLabel(result.status)}
            </Pill>
          </div>
          <p className={styles.basis}>{result.basis}</p>
          <div className={styles.rawGrid}>
            <RawPeriod title="Referentie" period={result.reference} />
            <RawPeriod title="Observatie" period={result.observation} />
            <div className={styles.difference}>
              <span>Ruw verschil</span>
              <strong>{formatNumber(result.difference_m3, 3)} m³</strong>
            </div>
          </div>
          {resultReasons.length ? (
            <Callout tone="warning" title="Beperkte vergelijkbaarheid">
              <ul className={styles.reasons}>
                {resultReasons.map((reason) => (
                  <li key={reason}>{REASON_TEXT[reason]}</li>
                ))}
              </ul>
              De ruwe waarden blijven zichtbaar; dit verschil is niet genormaliseerd en wordt niet
              aan ruimteverwarming toegeschreven.
            </Callout>
          ) : null}
          <div className={styles.grid}>
            <StatusLine label="Rendement" value={statusLabel(result.efficiency_availability)} />
            <StatusLine label="Kosten" value={statusLabel(result.cost_availability)} />
          </div>
        </Card>
      ) : null}

      <Card padding="md" className={styles.card}>
        <h2 className={styles.heading}>Meetbasis en aannames</h2>
        <p className={styles.body}>
          Alleen gelijke periodeduren, dezelfde meter, eenheid en bevestigde meterscope kunnen
          worden vergeleken. Een woningmeter kan ook koken en tapwater omvatten; ketelgas kan
          tapwater omvatten. Tapwatercycli zijn context en geen gasverdeling.
        </p>
        <div className={styles.statusGrid}>
          <StatusLine label="Weer" value="Ter vergelijking getoond; geen correctie" />
          <StatusLine label="Setpoint en gebruik" value="Onbekend blijft onbekend" />
          <StatusLine label="Rendement" value="Alleen met gevalideerde warmtemeting" />
          <StatusLine label="Kosten" value="Alleen met ingestelde toepasselijke gasprijs" />
        </div>
        <Callout tone="info" title="Geen fictieve nul">
          Een tellerreset, datagat, verouderde waarde of uitgesloten periode kan de vergelijking
          beperken of onbeschikbaar maken. Ontbrekende intervallen tellen nooit als nul en worden
          niet gladgestreken.
        </Callout>
        <p className={styles.note}>
          <Info size={14} aria-hidden="true" /> De selectie toont gemeten perioden; zij verklaart
          niet waardoor het gasverbruik verschilt.
        </p>
        {candidates.data ? (
          <p className={styles.note}>
            <ShieldAlert size={14} aria-hidden="true" /> Dekking observatieperiode:{' '}
            {formatPercent(candidates.data.observation_data.coverage_pct, 1)}
          </p>
        ) : null}
      </Card>
    </div>
  );
}

function RawPeriod({ title, period }: { title: string; period: Candidate }) {
  return (
    <div className={styles.rawPeriod}>
      <h3>
        {title} · {rangeLabel(period.range)}
      </h3>
      <strong>{formatNumber(period.consumption_m3, 3)} m³</strong>
      <dl className={styles.details}>
        <dt>Tellerstand begin</dt>
        <dd>{formatNumber(period.counter_start, 3)} m³</dd>
        <dt>Tellerstand einde</dt>
        <dd>{formatNumber(period.counter_end, 3)} m³</dd>
        <dt>Meter-scope</dt>
        <dd>{meterScope(period.meter_scope)}</dd>
        <dt>Dekking</dt>
        <dd>{formatPercent(period.coverage_pct, 1)}</dd>
        <dt>Buitentemperatuur</dt>
        <dd>{formatTemperature(period.context.outdoor_temperature_c)}</dd>
        <dt>Setpoints</dt>
        <dd>
          {Object.keys(period.context.room_setpoints_c).length
            ? Object.entries(period.context.room_setpoints_c)
                .map(([room, value]) => `${room}: ${formatTemperature(value)}`)
                .join(' · ')
            : 'Onbekend'}
        </dd>
        <dt>CV-branderduur</dt>
        <dd>{formatNumber(period.context.heating_runtime_hours, 1)} u</dd>
        <dt>Tapwatermodus</dt>
        <dd>{formatNumber(period.context.dhw_runtime_hours, 1)} u</dd>
        <dt>Zonegebruik</dt>
        <dd>{period.context.zone_use === 'unknown' ? 'Onbekend' : 'Gedeeltelijk beschikbaar'}</dd>
        <dt>Bijzondere perioden</dt>
        <dd>
          {period.context.special_periods.length
            ? period.context.special_periods.join(' · ')
            : 'Niet geregistreerd'}
        </dd>
      </dl>
      {period.reasons.length ? (
        <p className={styles.muted}>
          {period.reasons.map((reason) => REASON_TEXT[reason]).join(' · ')}
        </p>
      ) : null}
    </div>
  );
}

function ContextTable({
  reference,
  observation,
}: {
  reference: Candidate | undefined;
  observation: Candidate | undefined;
}) {
  const setpoints = (period: Candidate | undefined) => {
    if (!period || Object.keys(period.context.room_setpoints_c).length === 0) return 'Onbekend';
    return Object.entries(period.context.room_setpoints_c)
      .map(([room, value]) => `${room}: ${formatTemperature(value)}`)
      .join(' · ');
  };
  const specialPeriods = (period: Candidate | undefined) =>
    period?.context.special_periods.length
      ? period.context.special_periods.join(' · ')
      : 'Niet geregistreerd';
  const rows = [
    {
      label: 'Buitentemperatuur',
      reference: reference
        ? formatTemperature(reference.context.outdoor_temperature_c)
        : 'Onbekend',
      observation: observation
        ? formatTemperature(observation.context.outdoor_temperature_c)
        : 'Onbekend',
    },
    {
      label: 'Binnen-setpoint',
      reference: setpoints(reference),
      observation: setpoints(observation),
    },
    {
      label: 'CV-bedrijfsduur',
      reference: reference
        ? `${formatNumber(reference.context.heating_runtime_hours, 1)} u`
        : 'Onbekend',
      observation: observation
        ? `${formatNumber(observation.context.heating_runtime_hours, 1)} u`
        : 'Onbekend',
    },
    {
      label: 'Warmtevraag',
      reference: reference
        ? `${formatNumber(reference.context.heat_demand_hours, 1)} u`
        : 'Onbekend',
      observation: observation
        ? `${formatNumber(observation.context.heat_demand_hours, 1)} u`
        : 'Onbekend',
    },
    {
      label: 'Tapwatermodus',
      reference: reference
        ? `${formatNumber(reference.context.dhw_runtime_hours, 1)} u`
        : 'Onbekend',
      observation: observation
        ? `${formatNumber(observation.context.dhw_runtime_hours, 1)} u`
        : 'Onbekend',
    },
    {
      label: 'Zonegebruik',
      reference: reference
        ? reference.context.zone_use === 'unknown'
          ? 'Onbekend'
          : 'Gedeeltelijk beschikbaar'
        : 'Onbekend',
      observation: observation
        ? observation.context.zone_use === 'unknown'
          ? 'Onbekend'
          : 'Gedeeltelijk beschikbaar'
        : 'Onbekend',
    },
    {
      label: 'Bijzondere perioden',
      reference: specialPeriods(reference),
      observation: specialPeriods(observation),
    },
  ];

  return (
    <div className={styles.tableWrap}>
      <table className={styles.contextTable} aria-label="Context bij geselecteerde perioden">
        <thead>
          <tr>
            <th scope="col">Context</th>
            <th scope="col">Referentie</th>
            <th scope="col">Observatie</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              <td>{row.reference}</td>
              <td>{row.observation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.statusLine}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
