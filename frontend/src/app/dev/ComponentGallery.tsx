import {
  Activity,
  ArrowRight,
  Bed,
  Calendar,
  Check,
  ChevronRight,
  CircleCheck,
  Database,
  Droplet,
  Eye,
  Flame,
  Gauge,
  House,
  Lightbulb,
  Pause,
  Plug,
  Plus,
  Repeat,
  Sun,
  Trash2,
  Wrench,
  X,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Button, IconButton } from '../../components/Button.tsx';
import { Callout, type CalloutTone } from '../../components/Callout.tsx';
import { Card } from '../../components/Card.tsx';
import type { ConnectionStatus } from '../../components/connectionStatus.ts';
import { DataTable, type DataTableColumn } from '../../components/DataTable.tsx';
import { Dialog } from '../../components/Dialog.tsx';
import { EmptyState } from '../../components/EmptyState.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { IconBadge, type IconBadgeEmphasis } from '../../components/IconBadge.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { KeyValueGrid } from '../../components/KeyValueGrid.tsx';
import { KpiTile } from '../../components/KpiTile.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { Section } from '../../components/Section.tsx';
import { SegmentedControl } from '../../components/SegmentedControl.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { StatusPill, StubDataPill } from '../../components/StatusPill.tsx';
import { Tag } from '../../components/Tag.tsx';
import { Toggle } from '../../components/Toggle.tsx';
import { formatDuration, formatPercent, formatTemperature, formatTime } from '../../lib/format.ts';
import {
  AVAILABILITY_LABEL,
  AVAILABILITY_TONE,
  CHART_COLORS,
  NO_DATA_PATTERN,
  PALETTE,
  RECOMMENDATION_STATUS_LABEL,
  RECOMMENDATION_STATUS_TONE,
  SEVERITY_LABEL,
  SEVERITY_TONE,
  TONES,
  type AnalysisAvailability,
  type RecommendationStatus,
  type Severity,
} from '../../lib/semantics.ts';
import styles from './ComponentGallery.module.css';

const at = (hhmm: string) => new Date(`2026-10-04T${hhmm}:00+02:00`);

interface CycleRow {
  n: number;
  start: Date;
  end: Date;
  mode: 'CV' | 'Tapwater';
  endReason: string;
  maxFlow: number;
  modulation: number;
  kind: 'short' | 'normal' | 'excluded';
}

const CYCLES: CycleRow[] = [
  {
    n: 1,
    start: at('06:05'),
    end: at('06:07'),
    mode: 'CV',
    endReason: 'Stop tijdens vraag',
    maxFlow: 58.7,
    modulation: 19,
    kind: 'short',
  },
  {
    n: 2,
    start: at('06:15'),
    end: at('06:18'),
    mode: 'CV',
    endReason: 'Stop tijdens vraag',
    maxFlow: 59.1,
    modulation: 19,
    kind: 'normal',
  },
  {
    n: 3,
    start: at('07:12'),
    end: at('07:22'),
    mode: 'Tapwater',
    endReason: 'Einde tapvraag',
    maxFlow: 71.2,
    modulation: 62,
    kind: 'excluded',
  },
];

const CYCLE_LABEL = {
  short: ['Kort', 'rose'],
  normal: ['Normaal', 'green'],
  excluded: ['Uitgesloten', 'blue'],
} as const;

const CYCLE_COLUMNS: DataTableColumn<CycleRow>[] = [
  { key: 'n', header: '#', render: (c) => c.n, muted: true },
  { key: 'start', header: 'Start', render: (c) => formatTime(c.start), strong: true },
  { key: 'end', header: 'Einde', render: (c) => formatTime(c.end) },
  {
    key: 'dur',
    header: 'Duur',
    render: (c) => formatDuration((c.end.getTime() - c.start.getTime()) / 1000),
  },
  { key: 'mode', header: 'Modus', render: (c) => c.mode },
  { key: 'reason', header: 'Gestopt door', render: (c) => c.endReason },
  { key: 'max', header: 'Max. aanvoer', render: (c) => formatTemperature(c.maxFlow) },
  { key: 'mod', header: 'Modulatie', render: (c) => formatPercent(c.modulation) },
  {
    key: 'label',
    header: 'Beoordeling',
    render: (c) => (
      <Tag size="sm" tone={CYCLE_LABEL[c.kind][1]}>
        {CYCLE_LABEL[c.kind][0]}
      </Tag>
    ),
  },
];

const STATUSES: ConnectionStatus[] = [
  { state: 'live', updatedAt: at('12:00') },
  { state: 'delayed', lastDataAt: at('11:52') },
  { state: 'ha-offline', since: at('10:10') },
  { state: 'app-unreachable' },
  { state: 'importing', progress: 42 },
  { state: 'recomputing', progress: 63 },
];

function Demo({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Section title={title} headingLevel={2}>
      {children}
    </Section>
  );
}

export default function ComponentGallery() {
  const [range, setRange] = useState<'6 uur' | '24 uur' | '7 dagen'>('6 uur');
  const [channel, setChannel] = useState('Dagbundel');
  const [bundle, setBundle] = useState(true);
  const [escalate, setEscalate] = useState(false);
  const [selectedCycle, setSelectedCycle] = useState<string | null>('2');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [note, setNote] = useState('');

  return (
    <div className={styles.page}>
      <PageHeader
        title="Componenten"
        subtitle="Ontwikkelpagina: alle basiscomponenten in alle varianten (ontwerp v3)."
        icon={<Wrench size={ICON_SIZE} aria-hidden="true" />}
        tone="slate"
      />

      <Demo title="Palet en tokens">
        <div className={styles.swatches}>
          {TONES.map((tone) => (
            <div key={tone} className={styles.swatch}>
              <span style={{ background: PALETTE[tone].base }} />
              <span style={{ background: PALETTE[tone].tint }} />
              <span style={{ background: PALETTE[tone].dark }} />
              <code>{tone}</code>
            </div>
          ))}
        </div>
        <div className={styles.row}>
          {Object.entries(CHART_COLORS).map(([name, color]) => (
            <span key={name} className={styles.legend}>
              <span className={styles.legendSwatch} style={{ background: color }} />
              {name}
            </span>
          ))}
          <span className={styles.legend}>
            <span className={styles.legendSwatch} style={{ background: NO_DATA_PATTERN }} />
            Geen gegevens
          </span>
        </div>
      </Demo>

      <Demo title="Page header">
        <PageHeader
          title="Overzicht"
          subtitle="Status van je installatie · zondag 4 okt, 06:00–12:00."
        />
        <PageHeader
          title="Cycli"
          subtitle="Zondag 4 oktober, 06:00–12:00"
          icon={<Activity size={ICON_SIZE} aria-hidden="true" />}
          tone="orange"
          actions={
            <SegmentedControl
              label="Tijdbereik"
              variant="accent"
              value={range}
              onChange={setRange}
              options={[
                { value: '6 uur', label: '6 uur' },
                { value: '24 uur', label: '24 uur' },
                { value: '7 dagen', label: '7 dagen' },
              ]}
            />
          }
        />
      </Demo>

      <Demo title="Card">
        <div className={styles.grid2}>
          <Card>
            <strong>Card (wit, rand, radius 20)</strong>
            <span className={styles.muted}>padding md · 20px</span>
          </Card>
          <Card tone="orange" padding="lg">
            <IconBadge
              icon={<Lightbulb size={ICON_SIZE} />}
              tone="orange"
              size="lg"
              emphasis="solid"
            />
            <div className={styles.eyebrow}>Aanbevolen actie</div>
            <div className={styles.cardTitle}>Max. aanvoertemperatuur terug naar 70 °C</div>
            <Button iconEnd={<ArrowRight size={ICON_SIZE} aria-hidden="true" />}>
              Open advies
            </Button>
          </Card>
          <Card tone="green" radius="tile" padding="sm">
            <strong>Tegel (tint, radius 14)</strong>
          </Card>
        </div>
      </Demo>

      <Demo title="Tag / Pill">
        <div className={styles.row}>
          {TONES.map((tone) => (
            <Tag key={tone} tone={tone}>
              {tone}
            </Tag>
          ))}
        </div>
        <div className={styles.row}>
          {TONES.map((tone) => (
            <Tag key={tone} tone={tone} size="sm">
              {tone}
            </Tag>
          ))}
        </div>
        <div className={styles.row}>
          {(Object.keys(SEVERITY_TONE) as Severity[]).map((s) => (
            <Tag key={s} tone={SEVERITY_TONE[s]}>
              {SEVERITY_LABEL[s]}
            </Tag>
          ))}
          {(Object.keys(RECOMMENDATION_STATUS_TONE) as RecommendationStatus[]).map((s) => (
            <Tag key={s} tone={RECOMMENDATION_STATUS_TONE[s]}>
              {RECOMMENDATION_STATUS_LABEL[s]}
            </Tag>
          ))}
          {(Object.keys(AVAILABILITY_TONE) as AnalysisAvailability[]).map((a) => (
            <Tag key={a} tone={AVAILABILITY_TONE[a]} size="sm">
              {AVAILABILITY_LABEL[a]}
            </Tag>
          ))}
        </div>
      </Demo>

      <Demo title="Button">
        <div className={styles.row}>
          <Button iconEnd={<ArrowRight size={ICON_SIZE} aria-hidden="true" />}>Open advies</Button>
          <Button iconStart={<Check size={ICON_SIZE} aria-hidden="true" />}>Accepteren</Button>
          <Button disabled>Uitgeschakeld</Button>
        </div>
        <div className={styles.row}>
          <Button
            variant="secondary"
            iconStart={<CircleCheck size={ICON_SIZE} aria-hidden="true" />}
          >
            Uitgevoerd
          </Button>
          <Button
            variant="secondary"
            size="sm"
            iconStart={<Plus size={ICON_SIZE} aria-hidden="true" />}
          >
            Periode markeren
          </Button>
          <Button
            variant="danger"
            size="sm"
            iconStart={<Trash2 size={ICON_SIZE} aria-hidden="true" />}
          >
            Verwijderen
          </Button>
        </div>
        <div className={styles.row}>
          <Button variant="ghost" iconEnd={<ChevronRight size={ICON_SIZE} aria-hidden="true" />}>
            Alles bekijken
          </Button>
          <IconButton aria-label="Sluiten" icon={<X size={ICON_SIZE} aria-hidden="true" />} />
        </div>
      </Demo>

      <Demo title="IconBadge">
        {(['soft', 'softDark', 'solid'] as IconBadgeEmphasis[]).map((emphasis) => (
          <div key={emphasis} className={styles.row}>
            {(['xs', 'sm', 'md', 'lg', 'xl'] as const).map((size) => (
              <IconBadge
                key={size}
                icon={<Flame size={ICON_SIZE} />}
                tone="orange"
                size={size}
                emphasis={emphasis}
              />
            ))}
            {TONES.map((tone) => (
              <IconBadge
                key={tone}
                icon={<Eye size={ICON_SIZE} />}
                tone={tone}
                emphasis={emphasis}
              />
            ))}
            <code>{emphasis}</code>
          </div>
        ))}
      </Demo>

      <Demo title="KpiTile">
        <div className={styles.kpis}>
          <KpiTile
            icon={<Flame size={ICON_SIZE} />}
            tone="orange"
            label="Aanvoer"
            value={formatTemperature(38.2)}
            sub="gemeten · 4 s"
            explain="Temperatuur van het water van de ketel naar radiatoren en vloer."
          />
          <KpiTile
            icon={<Droplet size={ICON_SIZE} />}
            tone="blue"
            label="Retour"
            value={formatTemperature(35.1)}
            sub="gemeten · 4 s"
          />
          <KpiTile
            icon={<Gauge size={ICON_SIZE} />}
            tone="violet"
            label="Modulatie"
            value={formatPercent(0)}
            sub="niet omgerekend naar kW"
          />
          <KpiTile
            icon={<House size={ICON_SIZE} />}
            tone="teal"
            label="Woonkamer"
            value={formatTemperature(20.4)}
            sub="doel 20,5 °C"
          />
          <KpiTile
            icon={<Bed size={ICON_SIZE} />}
            tone="amber"
            label="Slaapkamer"
            value="—"
            sub="geen recente meting"
          />
          <KpiTile
            icon={<Sun size={ICON_SIZE} />}
            tone="amber"
            label="Buiten"
            value={formatTemperature(9.8)}
            sub="gemeten · 5 min"
          />
        </div>
        <div className={styles.kpis}>
          <KpiTile
            compact
            icon={<Repeat size={ICON_SIZE} />}
            tone="rose"
            valueTone="rose"
            label="Kort tijdens warmtevraag"
            value="14"
            sub="< 3 min, tijdens vraag"
          />
          <KpiTile
            compact
            icon={<Activity size={ICON_SIZE} />}
            tone="orange"
            label="Starts per uur"
            value="5,1"
            sub="cv-cycli"
          />
        </div>
      </Demo>

      <Demo title="SegmentedControl">
        <SegmentedControl
          label="Tijdbereik"
          variant="accent"
          value={range}
          onChange={setRange}
          options={[
            { value: '6 uur', label: '6 uur' },
            { value: '24 uur', label: '24 uur' },
            { value: '7 dagen', label: '7 dagen' },
          ]}
        />
        <div className={styles.narrow}>
          <SegmentedControl
            label="Kanaal voor ernst Middel"
            fill
            value={channel}
            onChange={setChannel}
            options={['Direct', 'Dagbundel', 'Weekrapport', 'Geen'].map((v) => ({
              value: v,
              label: v,
            }))}
          />
        </div>
      </Demo>

      <Demo title="Toggle">
        <Toggle
          checked={bundle}
          onChange={setBundle}
          label="Bundel meldingen die bij hetzelfde patroon horen"
        />
        <Toggle
          checked={escalate}
          onChange={setEscalate}
          label="Opnieuw melden als het erger wordt"
        />
        <Toggle checked={false} onChange={() => undefined} label="Uitgeschakeld" disabled />
      </Demo>

      <Section
        title="Alle cycli"
        headingLevel={2}
        description="Klik op een rij om de cyclus te markeren"
        padding="sm"
      >
        <DataTable
          caption="Alle cycli"
          columns={CYCLE_COLUMNS}
          rows={CYCLES}
          getRowKey={(c) => String(c.n)}
          onRowSelect={(c) => {
            setSelectedCycle(String(c.n));
          }}
          selectedKey={selectedCycle}
        />
      </Section>

      <Demo title="KeyValueGrid">
        <KeyValueGrid
          items={[
            {
              key: 'Reden',
              value: 'Onderscheidt hypothese 1 en 2 voordat een instelling wordt gewijzigd.',
            },
            {
              key: 'Verwacht effect',
              value: 'Geen direct energie-effect. Maakt een gerichte vervolgstap mogelijk.',
            },
            { key: 'Comfort', value: 'Geen invloed.' },
          ]}
        />
        <KeyValueGrid
          variant="tiles"
          items={[
            {
              key: 'Datadekking',
              value: '93 % · 30 min onbekend',
              icon: <Database size={ICON_SIZE} />,
              iconColor: PALETTE.teal.base,
            },
            {
              key: 'Relevante cycli',
              value: '14 van 22 cv-cycli',
              icon: <Repeat size={ICON_SIZE} />,
              iconColor: PALETTE.orange.base,
            },
            {
              key: 'Herhaling',
              value: '3 van laatste 7 dagen',
              icon: <Calendar size={ICON_SIZE} />,
              iconColor: PALETTE.violet.base,
            },
            {
              key: 'Ontbrekende signalen',
              value: 'Zoneklep, verdeler, pomp',
              icon: <Plug size={ICON_SIZE} />,
              iconColor: PALETTE.amber.base,
            },
          ]}
        />
        <KeyValueGrid
          variant="compact"
          items={[
            { key: 'Periode', value: 'Zo 4 okt 06:00–10:10' },
            { key: 'Signalen', value: 'Vlamstatus, CV-modus, warmtevraag' },
          ]}
        />
      </Demo>

      <Section
        title="Section met actie"
        headingLevel={2}
        action={
          <Button variant="ghost" iconEnd={<ChevronRight size={ICON_SIZE} aria-hidden="true" />}>
            Alles bekijken
          </Button>
        }
      >
        <span className={styles.muted}>Kop 16px/700 met rechts een actie.</span>
      </Section>

      <Demo title="Callout">
        {(['info', 'warning', 'success', 'error', 'neutral'] as CalloutTone[]).map((tone) => (
          <Callout key={tone} tone={tone}>
            <span>
              <strong>{tone}</strong> — Cyclus = één brandperiode, van start tot stop.
            </span>
          </Callout>
        ))}
        <ErrorCallout
          subject="de bevindingen"
          onRetry={() => undefined}
          details="HTTP 503 · GET /api/findings · 12:04"
        />
      </Demo>

      <Demo title="EmptyState">
        <div className={styles.grid2}>
          <Card>
            <EmptyState icon={<CircleCheck size={24} />} tone="green" title="Geen open bevindingen">
              In de geanalyseerde periode vond de app geen patroon dat aandacht vraagt.
            </EmptyState>
          </Card>
          <Card>
            <EmptyState
              icon={<Activity size={24} />}
              tone="orange"
              title="Cycli zijn nog niet beschikbaar"
              action={<Button>Vlamstatus koppelen</Button>}
            >
              Daarvoor is de vlamstatus van de brander nodig.
            </EmptyState>
          </Card>
        </div>
      </Demo>

      <Demo title="Skeleton">
        <SkeletonGroup className={styles.kpis}>
          {[0, 1, 2].map((i) => (
            <Card key={i} radius="kpi" padding="sm">
              <Skeleton width={36} height={36} radius={11} />
              <Skeleton width="60%" height={12} />
              <Skeleton width="80%" height={24} />
            </Card>
          ))}
        </SkeletonGroup>
      </Demo>

      <Demo title="Header status">
        <div className={styles.row}>
          {STATUSES.map((s) => (
            <StatusPill key={s.state} status={s} />
          ))}
          <StubDataPill />
        </div>
      </Demo>

      <Demo title="Dialog">
        <div className={styles.row}>
          <Button
            variant="secondary"
            size="sm"
            iconStart={<Pause size={ICON_SIZE} aria-hidden="true" />}
            onClick={() => {
              setDialogOpen(true);
            }}
          >
            Periode markeren
          </Button>
        </div>
        <Dialog
          open={dialogOpen}
          onClose={() => {
            setDialogOpen(false);
            setNote('');
          }}
          title="Periode markeren"
          subtitle="Deze tijd telt niet mee in vergelijkingen."
          icon={<Calendar size={ICON_SIZE} />}
          tone="blue"
          isDirty={note !== ''}
          dangerAction={
            <Button variant="danger" size="sm">
              Verwijderen
            </Button>
          }
          footer={
            <>
              <Button
                variant="secondary"
                onClick={() => {
                  setDialogOpen(false);
                }}
              >
                Annuleren
              </Button>
              <Button
                iconStart={<Check size={ICON_SIZE} aria-hidden="true" />}
                onClick={() => {
                  setDialogOpen(false);
                }}
              >
                Vastleggen
              </Button>
            </>
          }
        >
          <label className={styles.field}>
            Omschrijving
            <input
              value={note}
              onChange={(e) => {
                setNote(e.target.value);
              }}
              placeholder="Bijv. onderhoud"
            />
          </label>
        </Dialog>
      </Demo>
    </div>
  );
}
