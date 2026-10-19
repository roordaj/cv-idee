import { useMemo, useState } from 'react';
import { Layers, Settings2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useInstallation, useZoneAnalysis } from '../../api/hooks/installation.ts';
import { useSettings, useUpdateSettings } from '../../api/hooks/settings.ts';
import type { components } from '../../api/schema';
import { Button } from '../../components/Button.tsx';
import { Callout } from '../../components/Callout.tsx';
import { Card } from '../../components/Card.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { PageHeader } from '../../components/PageHeader.tsx';
import { Pill } from '../../components/Tag.tsx';
import { formatNumber } from '../../lib/format.ts';
import styles from './Zones.module.css';

type Source = components['schemas']['ZoneSignalAnalysis'];
type Bin = components['schemas']['ZoneCountBin'];
type Range = '24h' | '7d' | '30d';
const RANGE_MS: Record<Range, number> = {
  '24h': 86_400_000,
  '7d': 7 * 86_400_000,
  '30d': 30 * 86_400_000,
};
const RANGE_LABEL: Record<Range, string> = { '24h': '24 uur', '7d': '7 dagen', '30d': '30 dagen' };
const availabilityText = (value: Source['availability']) =>
  value === 'available' ? 'Beschikbaar' : value === 'limited' ? 'Beperkt' : 'Niet beschikbaar';
const coverageText = (value: number | null) =>
  value === null ? 'Onbekend' : `${formatNumber(value, 1)}%`;

export function ZoneAnalysisScreen() {
  const [range, setRange] = useState<Range>('7d');
  const period = useMemo(() => {
    const end = new Date();
    return {
      from: new Date(end.getTime() - RANGE_MS[range]).toISOString(),
      to: end.toISOString(),
    };
  }, [range]);
  const analysis = useZoneAnalysis(period);
  const installation = useInstallation();
  const settings = useSettings();
  const zoneCount = installation.data?.zones.length ?? 0;
  return (
    <div className={styles.screen}>
      <PageHeader
        title="Zoneanalyse"
        subtitle="Zonevraag en gemelde klepstatus naast bestaande CV-cycli"
        icon={<Layers size={ICON_SIZE} aria-hidden="true" />}
        tone="violet"
      />
      <div className={styles.range} role="group" aria-label="Analyseperiode">
        {(['24h', '7d', '30d'] as const).map((key) => (
          <Button
            key={key}
            size="sm"
            variant={range === key ? 'primary' : 'secondary'}
            aria-pressed={range === key}
            onClick={() => {
              setRange(key);
            }}
          >
            {RANGE_LABEL[key]}
          </Button>
        ))}
      </div>
      {analysis.isPending ? (
        <Card>Zoneanalyse laden…</Card>
      ) : analysis.isError ? (
        <ErrorCallout
          subject="de zoneanalyse"
          onRetry={() => {
            void analysis.refetch();
          }}
        />
      ) : (
        <>
          <div className={styles.meta}>
            <span>
              {dateTime(analysis.data.start)} – {dateTime(analysis.data.end)}
            </span>
            <span>Installatieprofiel v{analysis.data.profile_version}</span>
          </div>
          {installation.isSuccess && zoneCount === 0 ? (
            <Callout tone="warning" title="Zoneanalyse niet beschikbaar">
              Stel eerst zones in het <Link to="/installatie#zones">installatieprofiel</Link> in.
              Zonder geconfigureerde zones betekent onbekend niet nul actieve zones.
            </Callout>
          ) : null}
          <Callout tone="warning">
            {analysis.data.interpretation} De samenhang met korte cycli bewijst geen oorzaak.
          </Callout>
          <div className={styles.sources}>
            <SourceCard
              source={analysis.data.zone_demand}
              threshold={analysis.data.few_active_zones_max}
            />
            <SourceCard
              source={analysis.data.valve_state}
              threshold={analysis.data.few_active_zones_max}
            />
          </div>
          <div className={styles.evidence}>
            <Card>
              <h2 className={styles.h2}>Onvolledige tellingen</h2>
              <Incomplete source={analysis.data.zone_demand} />
              <Incomplete source={analysis.data.valve_state} />
            </Card>
            <ThresholdSetting
              key={String(analysis.data.few_active_zones_max)}
              value={settings.data?.values.few_active_zones_max ?? null}
              revision={settings.data?.revision ?? null}
              onboardingAt={settings.data?.onboarding_completed_at ?? null}
            />
          </div>
          <p className={styles.note}>
            Uitgesloten context: {analysis.data.exclusions.join(' · ')}. Een bestaande
            korte-cyclusclassificatie wordt alleen weergegeven; de zonecount wijzigt die beoordeling
            niet.
          </p>
        </>
      )}
    </div>
  );
}

function SourceCard({ source, threshold }: { source: Source; threshold: number | null }) {
  const demand = source.role === 'zone_demand';
  const title = demand ? 'Zone vraagt warmte' : 'Klep meldt open';
  const name = demand
    ? 'Zonevraag en korte cycli per zonecount'
    : 'Gemelde klepstatus en korte cycli per zonecount';
  return (
    <Card className={styles.sourceCard}>
      <div className={styles.sourceHead}>
        <h2 className={styles.h2}>{title}</h2>
        <Pill
          tone={
            source.availability === 'available'
              ? 'teal'
              : source.availability === 'limited'
                ? 'amber'
                : 'slate'
          }
        >
          {availabilityText(source.availability)}
        </Pill>
      </div>
      <p className={styles.note}>
        {source.complete_cycles} van {source.eligible_cycles} CV-cycli volledig beoordeelbaar ·
        dekking {coverageText(source.coverage_pct)}
      </p>
      <p className={styles.note}>
        {demand
          ? 'Gemapte warmtevraagstatus'
          : 'Gemelde status of commando; geen bewijs van fysieke opening'}
      </p>
      {source.distribution.length ? (
        <div className={styles.tableWrap}>
          <table aria-label={name}>
            <thead>
              <tr>
                <th scope="col">{demand ? 'Actieve zones' : 'Gemeld open'}</th>
                <th scope="col">Cycli</th>
                <th scope="col">Kort</th>
                {threshold !== null ? <th scope="col">Grens</th> : null}
                <th scope="col">Cycli bekijken</th>
              </tr>
            </thead>
            <tbody>
              {source.distribution.map((bin) => (
                <tr key={bin.active_count}>
                  <th scope="row">{bin.active_count}</th>
                  <td>{bin.cycles}</td>
                  <td>{bin.short_cycles}</td>
                  {threshold !== null ? (
                    <td>{bin.few_active_zones ? `≤ ${String(threshold)}` : '—'}</td>
                  ) : null}
                  <td>
                    <CycleLinks bin={bin} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={styles.empty}>
          Geen volledige zonecounts in deze periode. Dit is onbekend, niet nul activiteit.
        </p>
      )}
      <p className={styles.note}>{source.note}</p>
      {source.unmapped_zone_keys.length ? (
        <p className={styles.missing}>
          Niet gekoppelde zones: {source.unmapped_zone_keys.join(', ')}
        </p>
      ) : null}
      {source.signals.length ? (
        <ul className={styles.signalList} aria-label={`Bronnen · ${title}`}>
          {source.signals.map((signal) => (
            <li key={signal.signal_id}>
              <span>{signal.zone_key}</span>
              <code>{signal.signal_id}</code>
              <span>
                {signal.meaning ?? (demand ? 'Herkomst onbekend' : 'Status/commando onbekend')}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

function CycleLinks({ bin }: { bin: Bin }) {
  const [open, setOpen] = useState(false);
  if (!bin.cycle_starts.length) return <span>—</span>;
  return (
    <details
      className={styles.drilldown}
      open={open}
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
      }}
    >
      <summary>{bin.cycle_starts.length} cycli</summary>
      <ul>
        {bin.cycle_starts.map((start) => {
          const p = new URLSearchParams({
            from: start,
            to: new Date(new Date(start).getTime() + 15 * 60_000).toISOString(),
          });
          return (
            <li key={start}>
              <Link to={`/cycli?${p.toString()}`}>{dateTime(start)} · cyclusdetails</Link>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function Incomplete({ source }: { source: Source }) {
  const label = source.role === 'zone_demand' ? 'Zonevraag' : 'Gemelde klepstatus';
  return (
    <section className={styles.incomplete}>
      <h3>
        {label}: {source.incomplete_cycles.length} onvolledige cycli
      </h3>
      {source.incomplete_cycles.length ? (
        <ul>
          {source.incomplete_cycles.map((cycle) => (
            <li key={cycle.cycle_start}>
              <span>
                {dateTime(cycle.cycle_start)}: {cycle.known_active_count} bekend actief; ontbreekt:{' '}
                {cycle.missing_zone_keys.join(', ') || 'onbekend'}
              </span>
              {cycle.short ? (
                <Pill tone="amber" size="sm">
                  Korte cyclus
                </Pill>
              ) : null}
              <Link
                to={`/cycli?${new URLSearchParams({ from: cycle.cycle_start, to: new Date(new Date(cycle.cycle_start).getTime() + 15 * 60_000).toISOString() })}`}
              >
                Bekijk cyclus
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className={styles.note}>Geen onvolledige tellingen gerapporteerd.</p>
      )}
    </section>
  );
}

function ThresholdSetting({
  value,
  revision,
  onboardingAt,
}: {
  value: number | null;
  revision: string | null;
  onboardingAt: string | null;
}) {
  const update = useUpdateSettings();
  const [draft, setDraft] = useState(value === null ? '' : String(value));
  const [error, setError] = useState<string | null>(null);
  const settings = useSettings();
  const save = () => {
    if (!settings.data || !revision) return;
    const next = draft.trim() ? Number(draft) : null;
    if (next !== null && (!Number.isInteger(next) || next < 0)) {
      setError('Vul een geheel aantal in vanaf 0, of laat de grens leeg.');
      return;
    }
    setError(null);
    update.mutate({
      revision,
      values: { ...settings.data.values, few_active_zones_max: next },
      onboarding_completed_at: onboardingAt,
    });
  };
  return (
    <Card className={styles.threshold}>
      <div className={styles.sourceHead}>
        <h2 className={styles.h2}>Grens “weinig actieve zones”</h2>
        <Settings2 size={ICON_SIZE} aria-hidden="true" />
      </div>
      <label className={styles.field}>
        Optionele grens
        <input
          className={styles.input}
          aria-label="Grens weinig actieve zones"
          type="number"
          min="0"
          step="1"
          value={draft}
          placeholder="Niet ingesteld"
          onChange={(e) => {
            setDraft(e.target.value);
          }}
        />
      </label>
      <p className={styles.note}>
        Er is geen universele grens. Zonder instelling tonen we alleen concrete counts; deze
        vergelijking geeft geen oorzaak aan.
      </p>
      {error ? (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      ) : null}
      {update.isError ? (
        <p role="alert" className={styles.error}>
          Instelling opslaan is mislukt. Probeer opnieuw.
        </p>
      ) : null}
      <Button
        size="sm"
        disabled={!revision || draft === (value === null ? '' : String(value)) || update.isPending}
        onClick={save}
      >
        {update.isPending ? 'Opslaan…' : 'Grens opslaan'}
      </Button>
    </Card>
  );
}

function dateTime(value: string): string {
  return new Date(value).toLocaleString('nl-NL', {
    timeZone: 'Europe/Amsterdam',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  });
}
