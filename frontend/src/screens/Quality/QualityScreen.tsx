import { CalendarDays, CircleAlert, Clock, Plus, Shield, WifiOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useQuality } from '../../api/hooks/data.ts';
import { usePeriods } from '../../api/hooks/installation.ts';
import { useHaStatus } from '../../api/hooks/signals.ts';
import type { components } from '../../api/schema';
import { Button } from '../../components/Button.tsx';
import { Callout } from '../../components/Callout.tsx';
import { Card } from '../../components/Card.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { IconBadge } from '../../components/IconBadge.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { cx, toneVars } from '../../components/tone.ts';
import { StackedShareBar } from '../../charts/StackedShareBar.tsx';
import { formatDayMonth, formatNumber, formatPercent, formatTime } from '../../lib/format.ts';
import { NO_DATA_PATTERN } from '../../lib/semantics.ts';
import { ImportCard } from './ImportCard.tsx';
import {
  EVENT_TONE,
  MODE_COLOR,
  PERIOD_HELP,
  PERIOD_LABEL,
  PERIOD_TONE,
  SEGMENT_COLOR,
} from './labels.ts';
import { PeriodDialog } from './PeriodDialog.tsx';
import styles from './Quality.module.css';

type Period = components['schemas']['SpecialPeriod'];

const stamp = (iso: string) => {
  const d = new Date(iso);
  return `${formatDayMonth(d)} ${formatTime(d)}`;
};

function periodDate(p: Period): string {
  const s = new Date(p.start);
  if (!p.end) return `sinds ${formatDayMonth(s)} · loopt nog`;
  const e = new Date(p.end);
  if (formatDayMonth(s) === formatDayMonth(e))
    return `${formatDayMonth(s)} ${formatTime(s)}–${formatTime(e)}`;
  return `${formatDayMonth(s)} – ${formatDayMonth(e)}`;
}

function periodNote(p: Period): string {
  const excluded = p.excluded_from.normal_behaviour || p.excluded_from.comparisons;
  const tail = excluded ? 'telt niet mee in vergelijkingen' : 'telt gewoon mee';
  return `${p.description ? `${p.description} · ` : ''}${tail}`;
}

export function QualityScreen() {
  const quality = useQuality();
  const periods = usePeriods();
  const haStatus = useHaStatus();
  const [dialog, setDialog] = useState<{ period?: Period } | null>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [recomputing, setRecomputing] = useState(false);

  useEffect(() => {
    if (!highlight) return undefined;
    const t = window.setTimeout(() => {
      setHighlight(null);
    }, 2000);
    return () => {
      window.clearTimeout(t);
    };
  }, [highlight]);

  const q = quality.data;
  const coverageText = q?.core_coverage_pct == null ? null : formatPercent(q.core_coverage_pct, 1);
  const items = periods.data?.items ?? [];

  return (
    <div className={styles.screen}>
      <PageHeader
        title="Gegevenskwaliteit"
        subtitle={
          coverageText
            ? `Afgelopen 7 dagen · ${coverageText} dekking op ketelsignalen`
            : 'Afgelopen 7 dagen'
        }
        icon={<Shield size={ICON_SIZE} aria-hidden="true" />}
        tone="amber"
      />
      {haStatus.data?.configured && Math.abs(haStatus.data.clock_offset_ms) > 2000 ? (
        <Callout tone="warning" title="Klokverschil Home Assistant">
          De klok van Home Assistant loopt circa{' '}
          {formatNumber(Math.abs(haStatus.data.clock_offset_ms) / 1000, 1)} s{' '}
          {haStatus.data.clock_offset_ms > 0 ? 'achter' : 'voor'} op de app. Tijdstippen zijn
          gecorrigeerd.
        </Callout>
      ) : null}

      {quality.isError ? (
        <ErrorCallout
          subject="de gegevenskwaliteit"
          onRetry={() => {
            void quality.refetch();
          }}
        />
      ) : (
        <>
          <Card padding="md" className={styles.card}>
            <div className={styles.cardHead}>
              <h3 className={styles.h3}>Dekking per signaal</h3>
              {q ? (
                <span className={styles.range}>
                  {stamp(q.range.start)} → {q.range.end ? stamp(q.range.end) : 'nu'}
                </span>
              ) : null}
            </div>
            {!q ? (
              <SkeletonGroup>
                {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
                  <Skeleton key={i} height={12} radius={6} />
                ))}
              </SkeletonGroup>
            ) : (
              <CoverageRows data={q} />
            )}
            <ul className={styles.legend} aria-label="Legenda dekking">
              <li>
                <span className={styles.swatch} style={{ background: '#1a9e8f' }} />
                Compleet
              </li>
              <li>
                <span
                  className={styles.swatch}
                  style={{ background: SEGMENT_COLOR.connection_lost }}
                />
                Verbinding weg
              </li>
              <li>
                <span className={styles.swatch} style={{ background: SEGMENT_COLOR.stale }} />
                Te oud
              </li>
              <li>
                <span className={styles.swatch} style={{ background: NO_DATA_PATTERN }} />
                Niet gekoppeld
              </li>
            </ul>
          </Card>

          <div className={styles.cols}>
            <Card padding="md" className={cx(styles.card, styles.eventsCard)}>
              <h3 className={styles.h3}>Gedetecteerde gebeurtenissen</h3>
              {!q ? (
                <SkeletonGroup>
                  {[0, 1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} height={40} radius={9} />
                  ))}
                </SkeletonGroup>
              ) : q.events.length === 0 ? (
                <p className={styles.muted}>Geen bijzonderheden gedetecteerd in deze periode.</p>
              ) : (
                <ul className={styles.events} aria-label="Gebeurtenissen">
                  {q.events.map((e) => {
                    const tone = e.recovered ? 'green' : e.kind ? EVENT_TONE[e.kind] : 'green';
                    const Icon =
                      e.kind === 'connection_lost' ? WifiOff : e.recovered ? Clock : CircleAlert;
                    return (
                      <li key={`${e.at}-${e.title}`} className={styles.event}>
                        <IconBadge
                          icon={<Icon size={16} aria-hidden="true" />}
                          tone={tone}
                          size="sm"
                        />
                        <span className={styles.eventText}>
                          <span className={styles.eventTitle}>{e.title}</span>
                          <span className={styles.eventSub}>{e.consequence}</span>
                          <span className={styles.eventWhen}>
                            {stamp(e.at)}
                            {e.end ? ` → ${stamp(e.end)}` : ''}
                          </span>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
            <div className={styles.side}>
              <Card padding="md" className={styles.card}>
                <h3 className={styles.h3}>Bedrijfsmodi vandaag</h3>
                {!q ? <Skeleton height={14} radius={7} /> : <ModeShare data={q} />}
              </Card>
              {q ? (
                q.flame_resolution_s === null ? (
                  <Callout tone="warning">
                    Resolutie vlamstatus: onbekend. {q.flame_resolution_text}
                  </Callout>
                ) : (
                  <Callout tone="success">
                    Resolutie vlamstatus: <strong>{formatNumber(q.flame_resolution_s, 0)} s</strong>
                    . {q.flame_resolution_text}
                  </Callout>
                )
              ) : null}
            </div>
          </div>
        </>
      )}

      <Card padding="md" className={styles.card}>
        <div className={styles.cardHead}>
          <h3 className={styles.h3}>Bijzondere perioden</h3>
          <Button
            variant="secondary"
            size="sm"
            iconStart={<Plus size={ICON_SIZE} aria-hidden="true" />}
            onClick={() => {
              setDialog({});
            }}
          >
            Periode markeren
          </Button>
        </div>
        {periods.isPending ? (
          <Skeleton height={80} radius={14} />
        ) : periods.isError ? (
          <ErrorCallout
            subject="de bijzondere perioden"
            onRetry={() => {
              void periods.refetch();
            }}
          />
        ) : items.length === 0 ? (
          <p className={styles.muted}>
            Nog geen perioden gemarkeerd. Markeer bijvoorbeeld onderhoud of vakantie, zodat die tijd
            niet meetelt in vergelijkingen.
          </p>
        ) : (
          <ul className={styles.periods} aria-label="Bijzondere perioden">
            {items.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className={cx(styles.period, highlight === p.id && styles.periodNew)}
                  style={toneVars(PERIOD_TONE[p.kind])}
                  title={PERIOD_HELP[p.kind]}
                  onClick={() => {
                    setDialog({ period: p });
                  }}
                >
                  <span className={styles.periodKind}>{PERIOD_LABEL[p.kind]}</span>
                  <span className={styles.periodDate}>{periodDate(p)}</span>
                  <span className={styles.periodDesc}>{periodNote(p)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {recomputing ? (
          <p className={styles.note} role="status">
            <CalendarDays size={12} aria-hidden="true" /> Analyses over deze periode worden opnieuw
            berekend.
          </p>
        ) : null}
      </Card>

      <ImportCard />

      <PeriodDialog
        open={dialog !== null}
        period={dialog?.period}
        allPeriods={items}
        onClose={() => {
          setDialog(null);
        }}
        onSaved={(id) => {
          setHighlight(id);
          setRecomputing(true);
        }}
      />
    </div>
  );
}

type QualityData = components['schemas']['QualityResponse'];

function CoverageRows({ data }: { data: QualityData }) {
  const t0 = new Date(data.range.start).getTime();
  const t1 = data.range.end ? new Date(data.range.end).getTime() : t0 + 7 * 86_400_000;
  const span = Math.max(1, t1 - t0);
  return (
    <>
      {data.coverage.map((r) => (
        <div key={r.name} className={styles.covRow}>
          <span className={styles.covName}>{r.name}</span>
          <div
            className={styles.covTrack}
            style={{ background: r.coverage_pct === null ? NO_DATA_PATTERN : '#1a9e8f' }}
            role="img"
            aria-label={`${r.name}: ${r.coverage_pct === null ? 'niet gekoppeld' : formatPercent(r.coverage_pct, 1)} dekking`}
          >
            {r.segments.map((g) => {
              const l = Math.max(0, ((new Date(g.start).getTime() - t0) / span) * 100);
              const w = Math.min(
                100 - l,
                ((new Date(g.end).getTime() - new Date(g.start).getTime()) / span) * 100,
              );
              return (
                <span
                  key={`${g.kind}-${g.start}`}
                  className={styles.covSeg}
                  style={{
                    left: `${String(l)}%`,
                    width: `${String(w)}%`,
                    background: SEGMENT_COLOR[g.kind],
                  }}
                />
              );
            })}
          </div>
          <span className={styles.covPct}>
            {r.coverage_pct === null ? '—' : formatPercent(r.coverage_pct, 1)}
          </span>
        </div>
      ))}
    </>
  );
}

function ModeShare({ data }: { data: QualityData }) {
  const slices = data.mode_share.map((m) => ({
    key: m.mode,
    label: m.label,
    value: m.minutes,
    color: MODE_COLOR[m.mode],
  }));
  if (slices.length === 0) return <p className={styles.muted}>Nog geen gegevens van vandaag.</p>;
  return (
    <>
      <StackedShareBar slices={slices} />
      <ul className={styles.modeList} aria-label="Legenda bedrijfsmodi">
        {data.mode_share.map((m) => (
          <li key={m.mode} className={styles.modeItem}>
            <span
              className={styles.swatch}
              style={{ background: MODE_COLOR[m.mode], width: 10, height: 10, borderRadius: 3 }}
            />
            <span className={styles.modeLabel}>{m.label}</span>
            <span className={styles.muted}>{formatPercent(m.share_pct)}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
