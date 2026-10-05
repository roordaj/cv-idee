import { Activity, Flame, Gauge, Plug, Thermometer, Waves, type LucideIcon } from 'lucide-react';
import { useState } from 'react';
import { useSignals } from '../../api/hooks/signals.ts';
import { Callout } from '../../components/Callout.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { IconBadge } from '../../components/IconBadge.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { Pill } from '../../components/Tag.tsx';
import { cx } from '../../components/tone.ts';
import { SignalPanel } from './SignalPanel.tsx';
import styles from './Signals.module.css';
import { agePill, type Signal } from './signalFormat.ts';

const ROLE_ICON: Partial<Record<Signal['role'], LucideIcon>> = {
  flame: Flame,
  flow_temperature: Thermometer,
  return_temperature: Thermometer,
  room_temperature: Thermometer,
  outdoor_temperature: Thermometer,
  modulation: Gauge,
  gas_cumulative: Gauge,
  manifold_flow_temperature: Waves,
  manifold_return_temperature: Waves,
  flow_rate: Waves,
};

function SignalTile({
  signal,
  active,
  onPick,
}: {
  signal: Signal;
  active: boolean;
  onPick: () => void;
}) {
  const Icon = ROLE_ICON[signal.role] ?? Activity;
  const pill = agePill(signal);
  return (
    <li>
      <button
        type="button"
        className={cx(styles.tile, active && styles.tileActive)}
        aria-pressed={active}
        onClick={onPick}
      >
        <span className={styles.tileHead}>
          <IconBadge
            icon={<Icon size={16} aria-hidden="true" />}
            tone={signal.state === 'missing' ? 'slate' : 'teal'}
            size="sm"
          />
          <Pill tone={pill.tone} size="sm">
            {pill.text}
          </Pill>
        </span>
        <span className={styles.tileName}>{signal.name}</span>
        <span className={cx(styles.entity, !signal.entity_id && styles.entityMissing)}>
          {signal.entity_id ?? 'Niet gekoppeld'}
        </span>
        <span className={styles.needed}>Nodig voor {signal.needed_for_text}</span>
      </button>
    </li>
  );
}

export function SignalsScreen() {
  const signals = useSignals();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const items = signals.data?.items ?? [];
  const selected = items.find((s) => s.id === selectedId) ?? items[0];

  return (
    <div className={styles.screen}>
      <PageHeader
        title="Signaalkoppeling"
        subtitle={
          signals.data
            ? `${String(signals.data.linked)} van ${String(signals.data.total)} signalen gekoppeld`
            : 'Welke Home Assistant-entiteiten de analyses gebruiken.'
        }
        icon={<Plug size={ICON_SIZE} aria-hidden="true" />}
        tone="teal"
      />
      {signals.data?.linked === 0 ? (
        <Callout tone="info">
          Nog niets gekoppeld. Begin met de vlamstatus; de eerste start helpt je stap voor stap.
        </Callout>
      ) : null}
      {signals.isPending ? (
        <SkeletonGroup>
          <div className={styles.grid}>
            {Array.from({ length: 12 }, (_, i) => (
              <Skeleton key={i} height={120} radius={16} />
            ))}
          </div>
        </SkeletonGroup>
      ) : signals.isError ? (
        <ErrorCallout
          subject="de signalen"
          onRetry={() => {
            void signals.refetch();
          }}
        />
      ) : (
        <div className={styles.layout}>
          <ul className={styles.grid} aria-label="Signalen">
            {items.map((signal) => (
              <SignalTile
                key={signal.id}
                signal={signal}
                active={signal.id === selected?.id}
                onPick={() => {
                  setSelectedId(signal.id);
                }}
              />
            ))}
          </ul>
          {selected ? <SignalPanel key={selected.id} signal={selected} signals={items} /> : null}
        </div>
      )}
      <Callout tone="warning">
        Let op bij interpretatie: een klepcommando bewijst niet dat de klep fysiek open is; een
        gasmeter telt ook koken en tapwater mee; en de ΔT (aanvoer min retour) van de ketel is niet
        de ΔT per vloerverwarmingsgroep.
      </Callout>
    </div>
  );
}
