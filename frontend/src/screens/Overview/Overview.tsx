import {
  Activity,
  ArrowRight,
  Bed,
  ChevronRight,
  Clock,
  Droplet,
  Flame,
  Gauge,
  House,
  Info,
  Layers,
  Lightbulb,
  Pause,
  Plug,
  Repeat,
  ShieldCheck,
  Sun,
  Thermometer,
  WifiOff,
  type LucideIcon,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useOverview } from '../../api/hooks/system.ts';
import { useTimeline } from '../../api/hooks/data.ts';
import type { components } from '../../api/schema';
import { MiniTimeline } from '../../charts/MiniTimeline.tsx';
import { Callout } from '../../components/Callout.tsx';
import { Card } from '../../components/Card.tsx';
import { EmptyState } from '../../components/EmptyState.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { IconBadge } from '../../components/IconBadge.tsx';
import { KpiTile } from '../../components/KpiTile.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { Section } from '../../components/Section.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { Tag } from '../../components/Tag.tsx';
import { cx, toneVars } from '../../components/tone.ts';
import { kpiExplanation } from '../../content/glossary.ts';
import { useExplain } from '../../content/useExplain.ts';
import {
  formatDateShort,
  formatNumber,
  formatPercent,
  formatTimeRange,
  NBSP,
} from '../../lib/format.ts';
import {
  AVAILABILITY_LABEL,
  AVAILABILITY_TONE,
  SEVERITY_LABEL,
  SEVERITY_TONE,
  type Tone,
} from '../../lib/semantics.ts';
import styles from './Overview.module.css';

type Overview = components['schemas']['OverviewResponse'];
type Category = components['schemas']['Category'];
type Mode = components['schemas']['Mode'];
type AnalysisId = components['schemas']['AnalysisId'];
type Finding = components['schemas']['FindingSummary'];

const CATEGORY: Record<Category, { label: string; icon: LucideIcon; tone: Tone }> = {
  cycles: { label: 'Cycli', icon: Repeat, tone: 'orange' },
  temperature: { label: 'Temperatuur', icon: Thermometer, tone: 'orange' },
  data_quality: { label: 'Gegevenskwaliteit', icon: WifiOff, tone: 'rose' },
  operating_context: { label: 'Bedrijfscontext', icon: Info, tone: 'slate' },
  hydraulic: { label: 'Hydraulisch', icon: Droplet, tone: 'blue' },
  comfort: { label: 'Comfort', icon: House, tone: 'teal' },
  zones: { label: 'Zones', icon: Layers, tone: 'blue' },
  consumption: { label: 'Verbruik', icon: Flame, tone: 'orange' },
  effect_measurement: { label: 'Effectmeting', icon: Activity, tone: 'violet' },
};

const ANALYSIS_ICON: Record<AnalysisId, LucideIcon> = {
  cycles: Repeat,
  temperature: Thermometer,
  operating_mode: Gauge,
  comfort: House,
  zones: Layers,
  hydraulic: Droplet,
  consumption: Flame,
  efficiency: Activity,
  before_after: Activity,
};

const KPI_STYLE: Record<string, { icon: LucideIcon; tone: Tone }> = {
  flow_temperature: { icon: Flame, tone: 'orange' },
  return_temperature: { icon: Droplet, tone: 'blue' },
  modulation: { icon: Gauge, tone: 'violet' },
  'room:woonkamer': { icon: House, tone: 'teal' },
  'room:slaapkamer': { icon: Bed, tone: 'amber' },
  outdoor_temperature: { icon: Sun, tone: 'amber' },
};

const MODE_LABEL: Record<Mode, string> = {
  ch: 'CV',
  dhw: 'Tapwater',
  standby: 'Stand-by',
  afterrun: 'Naloop',
  fault_blocking: 'Storing',
  unknown: 'Onbekend',
};

const REASON_ICON: Partial<Record<string, LucideIcon>> = {
  flame_not_mapped: Plug,
  signals_not_mapped: Plug,
  too_few_hours: Clock,
  stale_signal: Clock,
  no_data_yet: Clock,
  low_coverage: ShieldCheck,
  data_gap: WifiOff,
  ha_disconnected: WifiOff,
};

const ISSUE_ICON: Record<'high' | 'medium' | 'info', { icon: LucideIcon; tone: Tone }> = {
  high: { icon: WifiOff, tone: 'rose' },
  medium: { icon: Clock, tone: 'amber' },
  info: { icon: Plug, tone: 'slate' },
};

const icon = (Icon: LucideIcon, size = ICON_SIZE) => <Icon size={size} aria-hidden="true" />;

function LinkButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className={styles.linkButton}>
      {children}
      {icon(ChevronRight, 16)}
    </Link>
  );
}

function kpiValue(k: Overview['kpis'][number]): string {
  if (k.value === null) return '—';
  return k.unit === '%'
    ? formatPercent(k.value)
    : `${formatNumber(k.value, 1)}${NBSP}${k.unit}`.trim();
}

function QualityRing({ pct, tone }: { pct: number | null; tone: Tone }) {
  const R = 34;
  const C = 2 * Math.PI * R;
  const shown = pct === null ? 0 : Math.min(100, Math.max(0, pct));
  const swatch = {
    base: `var(--color-${tone})`,
    tint: `var(--color-${tone}-tint)`,
  };
  return (
    <svg width="84" height="84" viewBox="0 0 84 84" style={{ flex: 'none' }} aria-hidden="true">
      <circle cx="42" cy="42" r={R} fill="none" stroke={swatch.tint} strokeWidth="10" />
      <circle
        cx="42"
        cy="42"
        r={R}
        fill="none"
        stroke={swatch.base}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={`${String((C * shown) / 100)} ${String(C)}`}
        transform="rotate(-90 42 42)"
      />
      <text x="42" y="47" textAnchor="middle" fontSize="16" fontWeight="800" fill="#1d2433">
        {pct === null ? '—' : formatPercent(pct)}
      </text>
    </svg>
  );
}

function OverviewSkeleton() {
  return (
    <SkeletonGroup className={styles.screen}>
      <PageHeader title="Overzicht" subtitle="Status van je installatie" />
      <div className={styles.row}>
        <div className={styles.grow2}>
          <Skeleton height={230} radius={20} />
        </div>
        <div className={styles.grow1}>
          <Skeleton height={230} radius={20} />
        </div>
      </div>
      <div className={styles.kpis}>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} height={110} radius={16} />
        ))}
      </div>
      <div className={styles.row}>
        <div className={styles.grow2}>
          <Skeleton height={260} radius={20} />
        </div>
        <div className={styles.grow1}>
          <Skeleton height={260} radius={20} />
        </div>
      </div>
      <Skeleton height={200} radius={20} />
    </SkeletonGroup>
  );
}

function MiniChart({ data }: { data: Overview }) {
  const timeline = useTimeline();
  if (timeline.isError) {
    return (
      <ErrorCallout
        subject="de tijdlijn"
        onRetry={() => {
          void timeline.refetch();
        }}
      />
    );
  }
  if (!timeline.data) return <Skeleton height={100} radius={14} />;
  const { start, end } = data.today.range;
  return (
    <div className={styles.inset}>
      <div className={styles.insetHead}>
        <strong>Vandaag {end ? formatTimeRange(new Date(start), new Date(end)) : ''}</strong>
        <span>
          {data.today.ch_cycles}
          {NBSP}cycli · {data.today.short_during_demand}
          {NBSP}kort tijdens warmtevraag
        </span>
      </div>
      <MiniTimeline data={timeline.data} />
    </div>
  );
}

function StatusCard({ data }: { data: Overview }) {
  const { assessment: a, status_card: s, setup } = data;
  const insufficient = a.level === 'insufficient_data';
  const mode = MODE_LABEL[s.mode];
  const modeKnown = s.mode !== 'unknown';
  return (
    <Card padding="lg" className={styles.grow2}>
      <div className={styles.statusHead}>
        <IconBadge
          icon={icon(insufficient ? Info : Pause, 24)}
          tone="slate"
          size="xl"
          emphasis="soft"
        />
        <div className={styles.statusBody}>
          <div className={styles.eyebrow}>{insufficient ? 'Status' : 'Status ketel'}</div>
          <h2 className={styles.statusTitle}>
            {insufficient ? 'Nog geen beoordeling mogelijk' : s.title}
          </h2>
          <p className={styles.text}>
            {insufficient
              ? 'Er zijn te weinig gegevens om iets te zeggen over hoe je installatie draait. De app geeft daarom (nog) geen oordeel.'
              : s.text}
          </p>
          <div className={styles.pills}>
            {insufficient ? (
              <>
                <Tag tone="slate">Onvoldoende gegevens</Tag>
                {modeKnown ? <Tag tone="slate">Modus: {mode} · live</Tag> : null}
              </>
            ) : (
              <>
                {a.level === 'limited' ? <Tag tone="amber">Datakwaliteit: beperkt</Tag> : null}
                {data.findings.action_required_count > 0 ? (
                  <Tag tone="rose">{data.findings.action_required_count} vragen om actie</Tag>
                ) : null}
                {a.level === 'sufficient' && data.findings.open_count === 0 ? (
                  <Tag tone="green">Gegevens voldoende · {formatPercent(a.coverage_pct)}%</Tag>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>
      {insufficient && a.reasons.length > 0 ? (
        <ul className={styles.why} aria-label="Waarom nog geen beoordeling">
          {a.reasons.map((r) => (
            <li key={r.code}>
              <span aria-hidden="true">{icon(REASON_ICON[r.code] ?? Info)}</span>
              <span className={styles.reason}>{r.text}</span>
              {r.action ? <LinkButton to={r.action.target}>{r.action.label}</LinkButton> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {!insufficient || setup.history_imported ? <MiniChart data={data} /> : null}
    </Card>
  );
}

function ActionCard({ data }: { data: Overview }) {
  const na = data.next_action;
  const insufficient = data.assessment.level === 'insufficient_data';
  if (!na) return null;
  const target = na.action?.target ?? (na.finding_id ? `/bevindingen/${na.finding_id}` : null);
  return (
    <Card tone="orange" padding="lg" className={cx(styles.grow1, styles.stretch)}>
      <IconBadge icon={icon(Lightbulb, 22)} tone="orange" size="lg" emphasis="solid" />
      <div className={styles.actionEyebrow}>
        {insufficient || na.kind === 'setup' ? 'Eerste stap' : 'Aanbevolen actie'}
      </div>
      <h2 className={styles.actionTitle}>{na.title}</h2>
      <p className={styles.actionText}>{na.text}</p>
      {target && na.action ? (
        <Link
          to={target}
          className={cx(styles.actionButton, styles.primaryLink)}
          style={toneVars('orange')}
        >
          {na.action.label}
          {icon(ArrowRight)}
        </Link>
      ) : null}
    </Card>
  );
}

function FindingRow({ f }: { f: Finding }) {
  const cat = CATEGORY[f.category];
  return (
    <Link to={`/bevindingen/${f.id}`} className={styles.finding}>
      <IconBadge icon={icon(cat.icon)} tone={cat.tone} size="lg" />
      <span className={styles.findingBody}>
        <span className={styles.findingTitle}>{f.title}</span>
        <span className={styles.findingMeta}>
          {cat.label} · {f.when_text}
        </span>
      </span>
      <Tag tone={SEVERITY_TONE[f.severity]}>{SEVERITY_LABEL[f.severity]}</Tag>
    </Link>
  );
}

function FindingsCard({ data }: { data: Overview }) {
  const { assessment: a, findings } = data;
  return (
    <Section
      title="Bevindingen"
      className={styles.grow2 ?? ''}
      action={<LinkButton to="/bevindingen">Alles bekijken</LinkButton>}
    >
      {findings.items.length > 0 ? (
        <div className={styles.findingList}>
          {findings.items.map((f) => (
            <FindingRow key={f.id} f={f} />
          ))}
        </div>
      ) : a.level === 'insufficient_data' ? (
        <EmptyState icon={icon(Info, 24)} title="Nog geen bevindingen mogelijk">
          Er zijn te weinig gegevens om patronen te herkennen ({formatNumber(a.observed_hours, 0)}{' '}
          van minimaal {formatNumber(a.minimum_hours, 0)} uur).
        </EmptyState>
      ) : (
        <EmptyState icon={icon(ShieldCheck, 24)} tone="slate" title="Geen open bevindingen">
          De app vond geen patroon dat aandacht vraagt. Dat is geen garantie: analyses die niet
          beschikbaar zijn, zijn niet beoordeeld.
        </EmptyState>
      )}
    </Section>
  );
}

function QualityCard({ data }: { data: Overview }) {
  const q = data.data_quality;
  const tone: Tone =
    q.level === 'insufficient_data' ? 'slate' : q.level === 'limited' ? 'amber' : 'green';
  return (
    <Section title="Datakwaliteit" className={styles.grow1 ?? ''}>
      <div className={styles.quality}>
        <QualityRing pct={q.coverage_pct} tone={tone} />
        <div className={styles.qualityText}>{q.text}</div>
      </div>
      {q.issues.length > 0 ? (
        <ul className={styles.issues}>
          {q.issues.map((i) => {
            const s = ISSUE_ICON[i.severity];
            return (
              <li key={i.title}>
                <span style={{ color: `var(--color-${s.tone})` }}>{icon(s.icon, 16)}</span>
                <span className={styles.issueName}>{i.title}</span>
                <strong>{i.value_text}</strong>
              </li>
            );
          })}
        </ul>
      ) : null}
      <LinkButton to="/kwaliteit">Details</LinkButton>
    </Section>
  );
}

function AnalysesCard({
  insufficient,
  analyses,
}: {
  insufficient: boolean;
  analyses: Overview['analyses'];
}) {
  return (
    <Card>
      <div className={styles.analysesHead}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Beschikbare analyses</h3>
        <p>Een ontbrekend signaal blokkeert alleen de analyses die ervan afhangen</p>
      </div>
      {
        <div className={styles.analyses}>
          {analyses.map((a) => {
            // No green anywhere while the assessment is "onvoldoende gegevens" (FR-36).
            const tone: Tone =
              insufficient && a.status === 'available' ? 'slate' : AVAILABILITY_TONE[a.status];
            const Icon = ANALYSIS_ICON[a.id];
            return (
              <div key={a.id} className={styles.analysis} style={toneVars(tone)}>
                <div className={styles.analysisHead}>
                  <span className={styles.analysisIcon}>{icon(Icon, 16)}</span>
                  <span>{a.name}</span>
                </div>
                <Tag tone={tone} size="sm">
                  {insufficient && a.status === 'available'
                    ? 'Beschikbaar · wacht op gegevens'
                    : AVAILABILITY_LABEL[a.status]}
                </Tag>
                <span className={styles.analysisNote}>{a.note}</span>
              </div>
            );
          })}
        </div>
      }
    </Card>
  );
}

function OverviewContent({ data }: { data: Overview }) {
  const { explain } = useExplain();
  const { assessment: a, setup } = data;
  const insufficient = a.level === 'insufficient_data';
  const haDown = a.reasons.find((r) => r.code === 'ha_disconnected');
  const start = new Date(data.window.start);
  const end = data.window.end ? new Date(data.window.end) : null;
  return (
    <div className={styles.screen}>
      <PageHeader
        title="Overzicht"
        subtitle={`Status van je installatie · ${formatDateShort(start)}${
          end ? `, ${formatTimeRange(start, end)}` : ''
        }.`}
      />
      {haDown ? (
        <Callout tone="error" title="Geen verbinding met Home Assistant.">
          {haDown.text} Deze tijd telt als onbekend, niet als &lsquo;brander uit&rsquo;. Conclusies
          over deze periode worden niet getrokken.
        </Callout>
      ) : null}
      {!setup.onboarding_done ? (
        <Callout tone="neutral">
          Inrichting nog niet af — {setup.steps_done} van {setup.steps_total} stappen gedaan.{' '}
          <Link to="/welkom">Verder met inrichten</Link>
        </Callout>
      ) : null}
      <div className={styles.row}>
        <StatusCard data={data} />
        <ActionCard data={data} />
      </div>
      <div className={styles.kpis}>
        {data.kpis.map((k) => {
          const style = KPI_STYLE[k.key] ?? { icon: Gauge, tone: 'slate' as Tone };
          const Icon = style.icon;
          const text = explain ? kpiExplanation(k.label) || k.explanation : '';
          return (
            <KpiTile
              key={k.key}
              icon={icon(Icon, 20)}
              tone={style.tone}
              label={k.label}
              value={kpiValue(k)}
              sub={
                k.stale && !k.note_text.includes('oud') ? `${k.note_text} · verouderd` : k.note_text
              }
              {...(text ? { explain: text } : {})}
            />
          );
        })}
      </div>
      <div className={styles.row}>
        <FindingsCard data={data} />
        <QualityCard data={data} />
      </div>
      <AnalysesCard insufficient={insufficient} analyses={data.analyses} />
      <Section title="Rapportage">
        <LinkButton to="/rapporten">Dag- of weekrapport bekijken</LinkButton>
      </Section>
    </div>
  );
}

export function Overview() {
  const overview = useOverview();
  if (overview.isError) {
    return (
      <div className={styles.screen}>
        <PageHeader title="Overzicht" subtitle="Status van je installatie" />
        <ErrorCallout
          subject="de status"
          onRetry={() => {
            void overview.refetch();
          }}
        />
      </div>
    );
  }
  if (!overview.data) return <OverviewSkeleton />;
  return <OverviewContent data={overview.data} />;
}
