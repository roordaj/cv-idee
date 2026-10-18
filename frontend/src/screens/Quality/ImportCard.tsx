import { useQueryClient } from '@tanstack/react-query';
import { CalendarDays, Database, Download, Repeat, Shield } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useCancelImport, useImport, useImports, useStartImport } from '../../api/hooks/data.ts';
import { Button } from '../../components/Button.tsx';
import { Callout } from '../../components/Callout.tsx';
import { Card } from '../../components/Card.tsx';
import { Dialog } from '../../components/Dialog.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { KpiTile } from '../../components/KpiTile.tsx';
import { SegmentedControl } from '../../components/SegmentedControl.tsx';
import { Skeleton } from '../../components/Skeleton.tsx';
import { Tag } from '../../components/Tag.tsx';
import { formatDateShort, formatDayMonth, formatNumber, formatPercent } from '../../lib/format.ts';
import { IMPORT_ACTIVE, IMPORT_STATUS } from './labels.ts';
import styles from './Quality.module.css';

type Preset = '7' | '30' | 'all' | 'custom';
const DAY_MS = 86_400_000;
const PRESETS = [
  { value: '7', label: 'Laatste 7 dagen' },
  { value: '30', label: 'Laatste 30 dagen' },
  { value: 'all', label: 'Alles beschikbaar' },
  { value: 'custom', label: 'Zelf kiezen' },
] as const;

const int = (n: number) => formatNumber(n, 0);
const day = (iso: string) => formatDayMonth(new Date(iso));
const dateInput = (d: Date) => d.toISOString().slice(0, 10);

function etaText(seconds: number | null | undefined, blocksDone: number): string {
  if (blocksDone < 2 || seconds == null) return 'tijd wordt geschat…';
  return seconds < 90 ? 'nog ca. 1 min' : `nog ca. ${String(Math.round(seconds / 60))} min`;
}

export function ImportCard({
  minCoveragePct = 95,
  defaultPreset = '7',
}: {
  minCoveragePct?: number;
  defaultPreset?: Preset;
}) {
  const queryClient = useQueryClient();
  const [now] = useState(() => Date.now());
  const list = useImports();
  const latest = list.data?.items
    .slice()
    .sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
  const polled = useImport(latest?.id ?? null);
  const job = polled.data ?? latest;
  const start = useStartImport();
  const cancel = useCancelImport();
  const [preset, setPreset] = useState<Preset>(defaultPreset);
  const [from, setFrom] = useState(dateInput(new Date(now - 7 * DAY_MS)));
  const [to, setTo] = useState(dateInput(new Date()));
  const [stopping, setStopping] = useState(false);
  const [forceForm, setForceForm] = useState(false);

  const active = job ? IMPORT_ACTIVE.includes(job.status) : false;
  const status = job?.status;
  const prev = useRef(status);
  useEffect(() => {
    if (prev.current && IMPORT_ACTIVE.includes(prev.current) && status === 'done') {
      for (const key of ['overview', 'quality', 'cycles', 'timeline'])
        void queryClient.invalidateQueries({ queryKey: [key] });
    }
    prev.current = status;
  }, [status, queryClient]);

  const earliest = list.data?.earliest_available_at ?? null;
  const rangeFrom = (): Date => {
    if (preset === 'custom') return new Date(`${from}T00:00`);
    if (preset === 'all') return earliest ? new Date(earliest) : new Date(now - 30 * DAY_MS);
    return new Date(now - Number(preset) * DAY_MS);
  };
  const rangeTo = (): Date => (preset === 'custom' ? new Date(`${to}T23:59`) : new Date());
  const customError =
    preset === 'custom' && (!from || !to || from >= to)
      ? 'De begindatum moet vóór de einddatum liggen.'
      : preset === 'custom' && new Date(`${to}T00:00`).getTime() > now + DAY_MS
        ? 'De einddatum mag niet in de toekomst liggen.'
        : null;
  const bigRange =
    preset === 'custom' &&
    !customError &&
    rangeTo().getTime() - rangeFrom().getTime() > 365 * DAY_MS;
  const beforeEarliest = earliest !== null && rangeFrom().getTime() < new Date(earliest).getTime();

  const begin = (range?: { from: string; to: string }) => {
    if (customError) return;
    setForceForm(false);
    start.mutate({
      from: range?.from ?? rangeFrom().toISOString(),
      to: range?.to ?? rangeTo().toISOString(),
    });
  };

  const statusInfo = job ? IMPORT_STATUS[job.status] : null;
  const showForm = !job || forceForm || (!active && status === 'cancelled');
  const pct =
    job && job.blocks_total > 0 ? Math.round((job.blocks_done / job.blocks_total) * 100) : 0;
  const analysing = status === 'analysing';

  let body;
  if (list.isPending) {
    body = <Skeleton height={80} radius={12} />;
  } else if (list.isError) {
    body = (
      <ErrorCallout
        subject="de importstatus"
        onRetry={() => {
          void list.refetch();
        }}
      />
    );
  } else if (job && active) {
    body = (
      <>
        <div aria-live="polite" className={styles.muted}>
          {analysing
            ? 'Metingen opgehaald. Cycli en bevindingen worden berekend…'
            : `${day(job.range.start)} → ${job.range.end ? day(job.range.end) : 'nu'}${
                job.current_block_day
                  ? ` · dag ${String(Math.min(job.blocks_done + 1, job.blocks_total))} van ${String(job.blocks_total)} (${day(job.current_block_day)})`
                  : ''
              }`}
        </div>
        <div className={styles.progressRow}>
          <div
            className={styles.progress}
            role="progressbar"
            aria-label="Voortgang import"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            aria-valuetext={`dag ${String(Math.min(job.blocks_done + 1, job.blocks_total))} van ${String(job.blocks_total)}, ${String(pct)} procent`}
          >
            <div
              className={styles.progressFill}
              data-phase={analysing ? 'analysing' : 'fetching'}
              style={{ width: `${String(pct)}%` }}
            />
          </div>
          <span className={styles.pct}>{pct} %</span>
        </div>
        <div className={styles.phases}>
          <span className={analysing ? undefined : styles.phaseOn}>
            {analysing ? '✓' : '①'} Ophalen
          </span>
          <span className={analysing ? styles.phaseOn : undefined}>② Analyseren</span>
          <span>③ Klaar</span>
        </div>
        <div className={styles.muted}>
          {int(job.observations_imported)} metingen · {int(job.duplicates_skipped)} dubbel
          overgeslagen · {etaText(job.eta_s, job.blocks_done)}
        </div>
        <p className={styles.note}>
          Je kunt de app gewoon gebruiken; de import loopt op de achtergrond door.
        </p>
        <div className={styles.actions}>
          <span />
          <Button
            variant="secondary"
            onClick={() => {
              setStopping(true);
            }}
          >
            Stoppen
          </Button>
        </div>
      </>
    );
  } else if (job && status === 'done') {
    const meets = job.coverage_pct !== null && job.coverage_pct >= minCoveragePct;
    body = (
      <>
        <div className={styles.kpis}>
          <KpiTile
            compact
            icon={<CalendarDays size={16} aria-hidden="true" />}
            tone="blue"
            label="Periode"
            value={`${day(job.range.start)} – ${job.range.end ? day(job.range.end) : 'nu'}`}
          />
          <KpiTile
            compact
            icon={<Database size={16} aria-hidden="true" />}
            tone="teal"
            label="Metingen"
            value={int(job.observations_imported)}
          />
          <KpiTile
            compact
            icon={<Repeat size={16} aria-hidden="true" />}
            tone="orange"
            label="Cycli"
            value={job.cycles_found === null ? '—' : int(job.cycles_found)}
          />
          <KpiTile
            compact
            icon={<Shield size={16} aria-hidden="true" />}
            tone="amber"
            label="Dekking"
            value={job.coverage_pct === null ? '—' : formatPercent(job.coverage_pct, 1)}
            valueTone={meets ? 'green' : 'amber'}
          />
        </div>
        {job.observations_imported === 0 ? (
          <Callout tone="neutral">
            Home Assistant had voor deze periode geen gegevens van de gekoppelde signalen.
          </Callout>
        ) : job.warnings.length > 0 ? (
          <Callout tone="warning" title={`${String(job.warnings.length)} aandachtspunten`}>
            <ul className={styles.list}>
              {job.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </Callout>
        ) : (
          <Callout tone="success">
            Alles binnen. Geen gaten gevonden in de geïmporteerde periode.
          </Callout>
        )}
        <div className={styles.actions}>
          <span style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Link to="/cycli">Bekijk in Cycli ›</Link>
          </span>
          <Button
            variant="secondary"
            onClick={() => {
              setForceForm(true);
            }}
          >
            Nog een import
          </Button>
        </div>
      </>
    );
  } else if (job && status === 'interrupted') {
    body = (
      <>
        <Callout tone="warning">
          De import is onderbroken bij{' '}
          {job.current_block_day ? day(job.current_block_day) : 'het begin'} (
          {job.errors[0] ?? 'app herstart of verbinding weg'}). Wat al binnen is, is bewaard.
        </Callout>
        <div className={styles.actions}>
          <span />
          <Button
            disabled={start.isPending}
            onClick={() => {
              begin({ from: job.range.start, to: job.range.end ?? new Date().toISOString() });
            }}
          >
            Hervatten
          </Button>
        </div>
      </>
    );
  } else if (job && status === 'failed') {
    body = (
      <>
        <Callout tone="error">
          De import is mislukt: {job.errors[0] ?? 'onbekende fout'}. Er is niets dubbel opgeslagen;
          je kunt het veilig opnieuw proberen.
        </Callout>
        <div className={styles.actions}>
          <span />
          <Button
            disabled={start.isPending}
            onClick={() => {
              begin({ from: job.range.start, to: job.range.end ?? new Date().toISOString() });
            }}
          >
            Opnieuw proberen
          </Button>
        </div>
      </>
    );
  } else {
    body = null;
  }

  const form = (
    <>
      <p className={styles.muted}>
        Haal eerdere metingen op uit Home Assistant. De import gebruikt precies dezelfde analyse als
        live gegevens, dus dezelfde historie levert dezelfde cycli op.
      </p>
      <SegmentedControl
        label="Periode"
        variant="subtle"
        options={PRESETS}
        value={preset}
        onChange={setPreset}
      />
      {preset === 'custom' ? (
        <div className={styles.pair}>
          <label className={styles.field}>
            Van
            <input
              type="date"
              className={styles.input}
              value={from}
              onChange={(e) => {
                setFrom(e.target.value);
              }}
            />
          </label>
          <label className={styles.field}>
            Tot
            <input
              type="date"
              className={styles.input}
              value={to}
              onChange={(e) => {
                setTo(e.target.value);
              }}
            />
          </label>
        </div>
      ) : null}
      {customError ? (
        <div role="alert" className={styles.error}>
          {customError}
        </div>
      ) : null}
      {bigRange ? <div className={styles.warn}>Grote import; dit kan lang duren.</div> : null}
      {earliest ? (
        <Callout tone={beforeEarliest ? 'warning' : 'neutral'}>
          Home Assistant bewaart historie vanaf {formatDateShort(new Date(earliest))}. Oudere
          gegevens bestaan daar niet meer en worden overgeslagen.
        </Callout>
      ) : null}
      {start.isError ? (
        <div role="alert" className={styles.error}>
          Importeren starten is mislukt. Probeer het opnieuw.
        </div>
      ) : null}
      <div className={styles.actions}>
        <span />
        <Button
          disabled={start.isPending || customError !== null}
          iconStart={<Download size={ICON_SIZE} aria-hidden="true" />}
          onClick={() => {
            begin();
          }}
        >
          Importeren
        </Button>
      </div>
    </>
  );

  return (
    <Card padding="md" className={styles.card}>
      <div className={styles.cardHead}>
        <h3 className={styles.h3}>Historie importeren</h3>
        {statusInfo ? (
          <Tag tone={statusInfo.tone}>
            {status === 'done' && job?.finished_at
              ? `Klaar · ${day(job.finished_at)}`
              : statusInfo.label}
          </Tag>
        ) : null}
      </div>
      {showForm && !active ? form : body}
      <Dialog
        open={stopping}
        onClose={() => {
          setStopping(false);
        }}
        title="Import stoppen?"
        subtitle="Wat al is opgehaald blijft bewaard en wordt geanalyseerd. Je kunt later verdergaan waar de import stopte."
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setStopping(false);
              }}
            >
              Doorgaan met importeren
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                if (job) cancel.mutate(job.id);
                setStopping(false);
              }}
            >
              Stoppen
            </Button>
          </>
        }
      >
        <span />
      </Dialog>
    </Card>
  );
}
