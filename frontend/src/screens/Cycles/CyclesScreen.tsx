import {
  Activity,
  ChevronLeft,
  ChevronRight,
  Clock,
  Flame,
  Pause,
  Repeat,
  TriangleAlert,
} from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { useCycles, useTimeline } from '../../api/hooks/data.ts';
import { Legend, TimelineChart } from '../../charts/index.ts';
import { IconButton } from '../../components/Button.tsx';
import { Card } from '../../components/Card.tsx';
import { DataTable, type DataTableColumn } from '../../components/DataTable.tsx';
import { EmptyState } from '../../components/EmptyState.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ExplainBanner } from '../../components/ExplainBanner.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { KpiTile } from '../../components/KpiTile.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { SegmentedControl } from '../../components/SegmentedControl.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { Pill } from '../../components/Tag.tsx';
import {
  capitalize,
  formatDateShort,
  formatDuration,
  formatNumber,
  formatPercent,
  formatTemperature,
  formatTimeRange,
} from '../../lib/format.ts';
import styles from './Cycles.module.css';
import {
  CLASS_LABEL,
  CLASS_TONE,
  END_REASON_TEXT,
  formatBurnTotal,
  formatCycleDuration,
  formatCycleEnd,
  formatCycleTime,
  type Cycle,
} from './cycleFormat.ts';

type RangeKey = '6h' | '24h' | '7d';
const HOUR = 3600_000;
const SPAN: Record<RangeKey, number> = { '6h': 6 * HOUR, '24h': 24 * HOUR, '7d': 7 * 24 * HOUR };
const OPTIONS = [
  { value: '6h', label: '6 uur' },
  { value: '24h', label: '24 uur' },
  { value: '7d', label: '7 dagen' },
] as const;

function rangeKeyOf(spanMs: number): RangeKey {
  return (Object.keys(SPAN) as RangeKey[]).reduce((best, k) =>
    Math.abs(SPAN[k] - spanMs) < Math.abs(SPAN[best] - spanMs) ? k : best,
  );
}

const DASH = '—';
const ICON = { size: 16, 'aria-hidden': true } as const;

export function CyclesScreen() {
  const [params, setParams] = useSearchParams();
  const from = params.get('from') ?? undefined;
  const to = params.get('to') ?? undefined;
  const cycleParam = params.get('cycle');
  const selected = cycleParam !== null && /^\d+$/.test(cycleParam) ? Number(cycleParam) : null;
  const range = { ...(from ? { from } : {}), ...(to ? { to } : {}) };

  const timeline = useTimeline(range);
  const cycles = useCycles({ ...range, limit: 500 });

  const resolved = timeline.data?.range ?? cycles.data?.range;
  const startMs = resolved ? new Date(resolved.start).getTime() : null;
  const endMs = resolved?.end ? new Date(resolved.end).getTime() : null;
  const spanMs = startMs !== null && endMs !== null ? endMs - startMs : SPAN['6h'];
  const rangeKey = rangeKeyOf(spanMs);
  const withDay = spanMs > 24 * HOUR;

  const update = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v === null) p.delete(k);
      else p.set(k, v);
    }
    setParams(p, { replace: true });
  };
  const setWindow = (s: number, e: number) => {
    update({ from: new Date(s).toISOString(), to: new Date(e).toISOString(), cycle: null });
  };
  const pickRange = (key: RangeKey) => {
    const e = endMs ?? Number(new Date());
    setWindow(e - SPAN[key], e);
  };
  const shift = (dir: -1 | 1) => {
    const s = startMs ?? Number(new Date()) - spanMs;
    const e = endMs ?? s + spanMs;
    setWindow(s + dir * spanMs, e + dir * spanMs);
  };
  const select = (n: number) => {
    update({ cycle: String(n) });
  };

  const rangeText =
    startMs !== null && endMs !== null ? formatTimeRange(new Date(startMs), new Date(endMs)) : null;
  const subtitle =
    startMs !== null && endMs !== null
      ? withDay
        ? `${capitalize(formatDateShort(new Date(startMs)))} – ${formatDateShort(new Date(endMs))}`
        : `${capitalize(formatDateShort(new Date(startMs)))}, ${rangeText ?? ''}`
      : 'Brandperiodes van de ketel';

  const columns: DataTableColumn<Cycle>[] = [
    { key: 'n', header: '#', muted: true, render: (c) => String(c.number) },
    {
      key: 'start',
      header: 'Start',
      strong: true,
      render: (c) => formatCycleTime(c.start, withDay),
    },
    { key: 'end', header: 'Einde', render: (c) => formatCycleEnd(c, withDay) },
    { key: 'dur', header: 'Duur', render: (c) => formatCycleDuration(c) },
    { key: 'mode', header: 'Modus', render: (c) => (c.mode === 'dhw' ? 'Tapwater' : 'CV') },
    { key: 'reason', header: 'Gestopt door', render: (c) => END_REASON_TEXT[c.end_reason] },
    {
      key: 'flow',
      header: 'Max. aanvoer',
      render: (c) => formatTemperature(c.max_flow_temperature),
    },
    { key: 'mod', header: 'Modulatie', render: (c) => formatPercent(c.mean_modulation_pct) },
    {
      key: 'class',
      header: 'Beoordeling',
      render: (c) => (
        <Pill tone={CLASS_TONE[c.classification]} size="sm">
          {CLASS_LABEL[c.classification]}
        </Pill>
      ),
    },
  ];

  const s = cycles.data?.summary;
  const none = !!s && s.ch_cycles + s.dhw_cycles === 0;

  return (
    <div className={styles.screen}>
      <PageHeader
        title="Cycli"
        subtitle={subtitle}
        icon={<Activity size={ICON_SIZE} aria-hidden="true" />}
        tone="orange"
        actions={
          <div className={styles.controls}>
            <IconButton
              aria-label="Vorige periode"
              icon={<ChevronLeft size={ICON_SIZE} aria-hidden="true" />}
              onClick={() => {
                shift(-1);
              }}
            />
            <SegmentedControl
              label="Tijdvak"
              variant="accent"
              options={OPTIONS}
              value={rangeKey}
              onChange={pickRange}
            />
            <IconButton
              aria-label="Volgende periode"
              icon={<ChevronRight size={ICON_SIZE} aria-hidden="true" />}
              onClick={() => {
                shift(1);
              }}
            />
          </div>
        }
      />
      <ExplainBanner />

      {cycles.isPending ? (
        <SkeletonGroup>
          <Skeleton height={104} radius={16} />
        </SkeletonGroup>
      ) : cycles.isError || !s ? (
        <ErrorCallout
          subject="de kengetallen"
          onRetry={() => {
            void cycles.refetch();
          }}
        />
      ) : (
        <div className={styles.kpis} aria-label="Kengetallen cycli" role="group">
          <KpiTile
            compact
            icon={<Repeat {...ICON} />}
            tone="orange"
            label="Starts per uur (CV)"
            value={s.starts_per_hour === null || none ? DASH : formatNumber(s.starts_per_hour)}
            sub={
              s.starts_per_hour === null
                ? 'te weinig gegevens'
                : `over ${formatNumber(s.observed_hours)} u met gegevens`
            }
          />
          <KpiTile
            compact
            icon={<Flame {...ICON} />}
            tone="orange"
            label="CV-cycli"
            value={String(s.ch_cycles)}
            sub={`+ ${String(s.dhw_cycles)} tapwater (uitgesloten)`}
          />
          <KpiTile
            compact
            icon={<TriangleAlert {...ICON} />}
            tone="rose"
            valueTone="rose"
            label="Kort tijdens warmtevraag"
            value={String(s.short_during_demand)}
            sub={`korter dan ${formatDuration(s.short_cycle_threshold_s)}`}
          />
          <KpiTile
            compact
            icon={<Clock {...ICON} />}
            tone="violet"
            label="Mediaan brandduur"
            value={formatDuration(s.median_burn_s)}
            sub={`gemiddeld ${formatDuration(s.mean_burn_s)}`}
          />
          <KpiTile
            compact
            icon={<Pause {...ICON} />}
            tone="blue"
            label="Mediaan pauze"
            value={formatDuration(s.median_pause_s)}
            sub="standby niet meegeteld"
          />
          <KpiTile
            compact
            icon={<Activity {...ICON} />}
            tone="teal"
            label="Totale brandtijd"
            value={s.total_burn_s === null || none ? DASH : formatBurnTotal(s.total_burn_s)}
            sub={
              s.incomplete_cycles > 0
                ? `${String(s.incomplete_cycles)} ${s.incomplete_cycles === 1 ? 'cyclus' : 'cycli'} onvolledig`
                : 'alle cycli compleet'
            }
          />
        </div>
      )}

      <Card padding="sm" className={styles.chartCard}>
        <Legend />
        {timeline.isPending ? (
          <SkeletonGroup>
            <Skeleton height={410} radius={12} />
          </SkeletonGroup>
        ) : timeline.isError ? (
          <ErrorCallout
            subject="de tijdlijn"
            onRetry={() => {
              void timeline.refetch();
            }}
          />
        ) : (
          <TimelineChart data={timeline.data} selectedCycle={selected} onSelectCycle={select} />
        )}
      </Card>

      <Card padding="none">
        <div className={styles.tableHead}>
          <h2 className={styles.tableTitle}>Alle cycli</h2>
          <span className={styles.hint}>Klik op een rij of balk om de cyclus te markeren</span>
        </div>
        {cycles.isPending ? (
          <SkeletonGroup>
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} height={36} radius={8} />
            ))}
          </SkeletonGroup>
        ) : cycles.isError ? (
          <ErrorCallout
            subject="de cycli"
            onRetry={() => {
              void cycles.refetch();
            }}
          />
        ) : cycles.data.items.length === 0 ? (
          <EmptyState
            icon={<Activity size={ICON_SIZE} aria-hidden="true" />}
            title={
              rangeText ? `Geen cycli tussen ${rangeText.replace('–', ' en ')}.` : 'Geen cycli.'
            }
          >
            Probeer 24 uur of 7 dagen.
          </EmptyState>
        ) : (
          <DataTable
            caption="Alle cycli"
            columns={columns}
            rows={cycles.data.items}
            getRowKey={(c) => String(c.number)}
            selectedKey={selected === null ? null : String(selected)}
            onRowSelect={(c) => {
              select(c.number);
            }}
          />
        )}
      </Card>
    </div>
  );
}
