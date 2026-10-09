import {
  Activity,
  BookOpen,
  Calendar,
  Check,
  CircleCheck,
  Clock,
  Database,
  Eye,
  Layers,
  Plug,
  Repeat,
  CircleHelp,
  Wrench,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import {
  useAddFindingNote,
  useFinding,
  useFindings,
  useSetFindingStatus,
} from '../../api/hooks/findings.ts';
import type { components } from '../../api/schema';
import {
  Button,
  Card,
  EmptyState,
  ErrorCallout,
  IconBadge,
  PageHeader,
  ICON_SIZE,
  Skeleton,
  SkeletonGroup,
  Tag,
  TermsPanel,
} from '../../components/index.ts';
import type { Tone } from '../../lib/semantics.ts';
import { SCREENS } from '../../app/navigation.ts';
import styles from './Findings.module.css';
import {
  CATEGORY_LABEL,
  CERTAINTY_LABEL,
  RELEVANCE_LABEL,
  SEVERITY_NL,
  SEVERITY_TONE_MAP,
  STATUS_TONE,
  categoryVisual,
} from './labels.ts';
import { useElementWidth } from './useElementWidth.ts';

type Summary = components['schemas']['FindingSummary'];
type Detail = components['schemas']['FindingDetail'];

const SIDE_LIST_MIN = 1060;
const TWO_COLUMNS_MIN = 700;
const NOTE_DEBOUNCE_MS = 800;

function icon(Icon: LucideIcon, size = ICON_SIZE) {
  return <Icon size={size} aria-hidden="true" />;
}

function FindingButton({
  finding,
  selected,
  chip,
}: {
  finding: Summary;
  selected: boolean;
  chip: boolean;
}) {
  const navigate = useNavigate();
  const visual = categoryVisual(finding.category);
  return (
    <button
      type="button"
      className={chip ? styles.chip : styles.row}
      data-selected={selected}
      aria-current={selected ? 'true' : undefined}
      onClick={() => {
        void navigate(`/bevindingen/${finding.id}`);
      }}
    >
      <IconBadge icon={icon(visual.icon)} tone={visual.tone} size={chip ? 'sm' : 'md'} />
      <span className={styles.rowText}>
        <span className={chip ? styles.chipTitle : styles.rowTitle}>{finding.title}</span>
        <span className={styles.rowMeta}>
          <Tag size="sm" tone={SEVERITY_TONE_MAP[finding.severity]}>
            {SEVERITY_NL[finding.severity]}
          </Tag>
          {chip ? null : <span className={styles.rowStatus}>{finding.status_text}</span>}
        </span>
      </span>
    </button>
  );
}

function SectionHead({
  icon: node,
  tone,
  title,
  step,
}: {
  icon: ReactNode;
  tone: Tone;
  title: string;
  step: string;
}) {
  return (
    <div className={styles.sectionHead}>
      <IconBadge icon={node} tone={tone} size="sm" emphasis="softDark" />
      <h4>{title}</h4>
      <span>{step}</span>
    </div>
  );
}

function ProofTile({ k, v, node, tone }: { k: string; v: string; node: ReactNode; tone: Tone }) {
  return (
    <div className={styles.proof}>
      <span style={{ color: `var(--color-${tone})`, paddingTop: 2 }}>{node}</span>
      <div>
        <div className={styles.proofKey}>{k}</div>
        <div className={styles.proofValue}>{v}</div>
      </div>
    </div>
  );
}

function adviceRows(rec: NonNullable<Detail['recommendation']>): [string, string][] {
  const rows: [string, string | null | undefined][] = [
    ['Reden', rec.reason],
    ['Verwacht effect', rec.expected_effect],
    ['Comfort', rec.comfort_impact],
    ['Omvang', rec.magnitude],
    ['Voorwaarden', rec.conditions],
    ['Evaluatie', rec.evaluation],
    ['Succes', rec.success_criterion],
    ['Terugdraaien', rec.rollback_criterion],
    ['Opvolging', rec.follow_up],
  ];
  return rows.filter((r): r is [string, string] => Boolean(r[1]));
}

function timelineHref(finding: Detail): string | null {
  const range = finding.timeline_range;
  if (!range) return null;
  const params = new URLSearchParams({ from: range.start });
  if (range.end) params.set('to', range.end);
  const cycle = finding.evidence_links?.find((l) => l.kind === 'cycle' && l.start);
  if (cycle?.start) params.set('cycle', cycle.start);
  return `/cycli?${params.toString()}`;
}

function NoteField({ finding }: { finding: Detail }) {
  const addNote = useAddFindingNote();
  const lastSaved = finding.notes?.at(-1)?.text ?? '';
  const [text, setText] = useState(lastSaved);
  const saved = useRef(lastSaved);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const { mutate } = addNote;

  useEffect(
    () => () => {
      clearTimeout(timer.current);
    },
    [],
  );

  const onChange = (value: string) => {
    setText(value);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const trimmed = value.trim();
      if (trimmed && trimmed !== saved.current) {
        saved.current = trimmed;
        mutate({ findingId: finding.id, body: { text: trimmed } });
      }
    }, NOTE_DEBOUNCE_MS);
  };

  return (
    <textarea
      className={styles.note}
      aria-label="Notitie"
      value={text}
      onChange={(e) => {
        onChange(e.target.value);
      }}
      placeholder="Notitie, bijv.: groepen 3 en 4 van de verdeler stonden dicht."
    />
  );
}

function FollowUp({ finding }: { finding: Detail }) {
  const setStatus = useSetFindingStatus();
  const tone = STATUS_TONE[finding.status];
  const change = (status: 'accepted' | 'done' | 'postponed' | 'rejected') => {
    setStatus.mutate({ findingId: finding.id, body: { status } });
  };
  return (
    <Card>
      <div className={styles.followHead}>
        <h4>Opvolging</h4>
        <Tag tone={tone}>{finding.status_text}</Tag>
      </div>
      <div className={styles.actions}>
        <Button
          iconStart={icon(Check)}
          onClick={() => {
            change('accepted');
          }}
        >
          Accepteren
        </Button>
        <Button
          variant="secondary"
          iconStart={icon(CircleCheck)}
          onClick={() => {
            change('done');
          }}
        >
          Uitgevoerd
        </Button>
        <Button
          variant="secondary"
          iconStart={icon(Clock)}
          onClick={() => {
            change('postponed');
          }}
        >
          Uitstellen 7 d
        </Button>
        <Button
          variant="secondary"
          iconStart={icon(X)}
          onClick={() => {
            change('rejected');
          }}
        >
          Afwijzen
        </Button>
      </div>
      {setStatus.isError ? (
        <div role="alert" className={styles.alert}>
          Kon de status niet opslaan. De vorige status is hersteld.
        </div>
      ) : null}
      {finding.status === 'postponed' ? (
        <div className={styles.infoBox} data-tone="blue">
          Komt terug op{' '}
          {finding.postponed_until
            ? new Date(finding.postponed_until).toLocaleDateString('nl-NL', {
                day: 'numeric',
                month: 'short',
                timeZone: 'Europe/Amsterdam',
              })
            : 'het ingestelde moment'}
          , of eerder bij verslechtering (meer korte cycli of comfortverlies).
        </div>
      ) : null}
      {finding.status === 'done' ? (
        <div className={styles.infoBox} data-tone="green">
          Leg de wijziging vast (parameter, oude en nieuwe waarde), dan wordt het effect voor/na
          gemeten. <Link to="/wijzigingen">Wijziging vastleggen →</Link>
        </div>
      ) : null}
      <NoteField key={finding.id} finding={finding} />
      <div className={styles.saveLine}>
        Opgeslagen met meetperiode, instellingen en regelversie {finding.rule.id} v
        {finding.rule.version}.
      </div>
    </Card>
  );
}

function FindingDetailView({
  finding,
  narrow,
  small,
}: {
  finding: Detail;
  narrow: boolean;
  small: boolean;
}) {
  const navigate = useNavigate();
  const visual = categoryVisual(finding.category);
  const href = timelineHref(finding);
  const rows = finding.recommendation ? adviceRows(finding.recommendation) : [];
  const display = finding.evidence.display;
  const cols: CSSProperties = {
    gridTemplateColumns: narrow ? 'minmax(0,1fr)' : 'minmax(0,1.2fr) minmax(280px,1fr)',
  };
  return (
    <>
      <Card as="section" aria-label="Bevinding">
        <div className={styles.headTop}>
          <IconBadge icon={icon(visual.icon, 22)} tone={visual.tone} size="lg" />
          <div className={styles.headText}>
            <div className={styles.meta}>
              {finding.id} · {CATEGORY_LABEL[finding.category]} · {finding.when_text}
            </div>
            <h2 className={styles.title} style={{ fontSize: small ? 19 : 22 }}>
              {finding.title}
            </h2>
          </div>
        </div>
        <div className={styles.pills}>
          <Tag tone={SEVERITY_TONE_MAP[finding.severity]}>
            Ernst: {SEVERITY_NL[finding.severity]}
          </Tag>
          <Tag tone="violet">Zekerheid: {CERTAINTY_LABEL[finding.certainty]}</Tag>
          <Tag tone={STATUS_TONE[finding.status]}>{finding.status_text}</Tag>
          <Tag tone="slate">
            Impact:{' '}
            {finding.relevance.length > 0
              ? finding.relevance.map((r) => RELEVANCE_LABEL[r]).join(', ')
              : '—'}
          </Tag>
        </div>
        <div className={styles.proofGrid}>
          <ProofTile k="Datadekking" v={display.coverage} node={icon(Database)} tone="teal" />
          <ProofTile k="Relevante cycli" v={display.cycles} node={icon(Repeat)} tone="orange" />
          <ProofTile k="Herhaling" v={display.repetition} node={icon(Calendar)} tone="violet" />
          <ProofTile
            k="Ontbrekende signalen"
            v={display.missing_signals}
            node={icon(Plug)}
            tone="amber"
          />
        </div>
      </Card>

      <div className={styles.columns} style={cols}>
        <div className={styles.col}>
          <Card>
            <SectionHead icon={icon(Eye)} tone="blue" title="Observatie" step="1/3" />
            <p className={styles.body}>{finding.observation}</p>
            <dl className={styles.facts}>
              <dt>Tijdvak</dt>
              <dd>{finding.period_text}</dd>
              <dt>Signalen</dt>
              <dd>{finding.signals_text}</dd>
            </dl>
            {href ? (
              <Button
                variant="secondary"
                size="sm"
                className={styles.selfStart}
                iconStart={icon(Activity)}
                onClick={() => {
                  void navigate(href);
                }}
              >
                Toon in tijdlijn
              </Button>
            ) : null}
          </Card>
          <Card>
            <SectionHead
              icon={icon(CircleHelp)}
              tone="violet"
              title="Mogelijke verklaringen"
              step="2/3"
            />
            <p className={styles.body}>{finding.interpretation}</p>
            {finding.hypotheses.map((h) => (
              <div key={h.number} className={styles.hyp}>
                <div className={styles.hypHead}>
                  <span className={styles.hypNum}>{h.number}</span>
                  <strong>{h.name}</strong>
                </div>
                <dl className={styles.hypGrid}>
                  <dt data-k="for">Aanwijzing</dt>
                  <dd>{h.evidence_for}</dd>
                  <dt data-k="missing">Ontbreekt</dt>
                  <dd>{h.missing}</dd>
                  <dt data-k="test">Test</dt>
                  <dd>{h.distinguishing_measurement}</dd>
                </dl>
              </div>
            ))}
          </Card>
        </div>

        <div className={styles.col} data-sticky={!narrow}>
          <Card>
            <SectionHead icon={icon(Wrench)} tone="orange" title="Advies" step="3/3" />
            {finding.recommendation ? (
              <>
                <div className={styles.action}>{finding.recommendation.action}</div>
                <dl className={styles.adviceRows}>
                  {rows.map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{v}</dd>
                    </div>
                  ))}
                </dl>
              </>
            ) : (
              <div className={styles.noAdvice}>
                {finding.no_advice_text ?? 'Bij deze bevinding hoort geen advies.'}
              </div>
            )}
          </Card>
          <FollowUp finding={finding} />
        </div>
      </div>

      <TermsPanel findingId={finding.id} />

      {finding.bundle.length > 0 ? (
        <Card>
          <div className={styles.bundleHead}>
            {icon(Layers)}
            <h4>Samengevoegd tot één punt</h4>
            <span>Deze meldingen horen bij hetzelfde patroon</span>
          </div>
          <div className={styles.bundleGrid}>
            {finding.bundle.map((b) => (
              <div key={`${b.text}|${b.source}`} className={styles.bundleItem}>
                <span>{b.text}</span>
                <span className={styles.bundleSource}>{b.source}</span>
                {b.recommendation?.kind === 'measurement' ? (
                  <span>{b.recommendation.action}</span>
                ) : null}
              </div>
            ))}
          </div>
        </Card>
      ) : null}
    </>
  );
}

function DetailSkeleton() {
  return (
    <SkeletonGroup className={styles.skeleton}>
      <Skeleton height={190} radius={20} />
      <Skeleton height={260} radius={20} />
    </SkeletonGroup>
  );
}

function SelectedFinding({ id, narrow, small }: { id: string; narrow: boolean; small: boolean }) {
  const query = useFinding(id);
  if (query.isPending) return <DetailSkeleton />;
  if (query.isError) {
    return (
      <Card>
        <EmptyState
          icon={icon(BookOpen)}
          title="Deze bevinding bestaat niet meer"
          headingLevel={2}
          action={<Link to="/bevindingen">Naar alle bevindingen</Link>}
        >
          Mogelijk is ze samengevoegd of opnieuw berekend na een instellingswijziging.
        </EmptyState>
      </Card>
    );
  }
  return <FindingDetailView finding={query.data} narrow={narrow} small={small} />;
}

function FindingsBody() {
  const { id } = useParams<{ id: string }>();
  const list = useFindings();
  const [ref, width] = useElementWidth(900);
  const side = width >= SIDE_LIST_MIN;

  if (list.isPending) {
    return (
      <div ref={ref}>
        <SkeletonGroup className={styles.skeleton}>
          <Skeleton height={60} radius={14} />
          <Skeleton height={190} radius={20} />
          <Skeleton height={260} radius={20} />
        </SkeletonGroup>
      </div>
    );
  }
  if (list.isError) {
    return (
      <div ref={ref}>
        <ErrorCallout
          subject="de bevindingen"
          onRetry={() => {
            void list.refetch();
          }}
        />
      </div>
    );
  }
  const items = list.data.items;
  if (items.length === 0) {
    return (
      <div ref={ref}>
        <Card>
          <EmptyState icon={icon(CircleCheck)} title="Geen open bevindingen" headingLevel={2}>
            In de geanalyseerde periode vond de app geen patroon dat aandacht vraagt. Dat is geen
            garantie: analyses die niet beschikbaar zijn, zijn niet beoordeeld.
          </EmptyState>
        </Card>
      </div>
    );
  }
  const first = items[0];
  if (!id && first) return <Navigate to={`/bevindingen/${first.id}`} replace />;

  return (
    <div
      ref={ref}
      className={styles.layout}
      style={{ gridTemplateColumns: side ? '272px minmax(0,1fr)' : 'minmax(0,1fr)' }}
    >
      {side ? (
        <nav className={styles.side} aria-label="Bevindingen">
          <div className={styles.sideHead}>
            <span>Bevindingen</span>
            <span>op prioriteit</span>
          </div>
          {items.map((f) => (
            <FindingButton key={f.id} finding={f} selected={f.id === id} chip={false} />
          ))}
        </nav>
      ) : null}
      <div className={styles.main}>
        {side ? null : (
          <nav className={styles.chips} aria-label="Bevindingen">
            {items.map((f) => (
              <FindingButton key={f.id} finding={f} selected={f.id === id} chip />
            ))}
          </nav>
        )}
        {id ? (
          <SelectedFinding id={id} narrow={width < TWO_COLUMNS_MIN} small={width < 560} />
        ) : null}
      </div>
    </div>
  );
}

export default function Findings() {
  const def = SCREENS.find((screen) => screen.key === 'bevindingen');
  const Icon = def?.icon;
  return (
    <div className={styles.page}>
      {def && Icon ? (
        <PageHeader
          title={def.title}
          {...(def.subtitle ? { subtitle: def.subtitle } : {})}
          icon={<Icon size={ICON_SIZE} aria-hidden="true" />}
          tone={def.tone}
        />
      ) : null}
      <FindingsBody />
    </div>
  );
}
