import { Flame, Home, Thermometer, Waves } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useInstallation } from '../../api/hooks/installation.ts';
import { Card } from '../../components/Card.tsx';
import { EmptyState } from '../../components/EmptyState.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { IconBadge } from '../../components/IconBadge.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { Pill } from '../../components/Tag.tsx';
import { cx } from '../../components/tone.ts';
import styles from './Installation.module.css';
import { SpecDialog } from './SpecDialog.tsx';
import { RoomComfortPanel } from './RoomComfortPanel.tsx';
import { specText, type InstallationProfile, type Specification } from './specFormat.ts';

type Circuit = InstallationProfile['circuits'][number];

function emitterTitle(circuit: Circuit): string {
  switch (circuit.emitter) {
    case 'radiator':
      return 'Radiatoren';
    case 'underfloor':
      return circuit.loops
        ? `Vloerverwarming · ${String(circuit.loops)} groepen`
        : 'Vloerverwarming';
    case 'other':
      return 'Overig';
    default:
      return 'Onbekend';
  }
}

function BoilerCard({ boiler }: { boiler: InstallationProfile['boiler'] }) {
  return (
    <Card className={styles.card}>
      <IconBadge icon={<Flame size={ICON_SIZE} aria-hidden="true" />} tone="orange" size="lg" />
      <div>
        <div className={styles.label}>Ketel</div>
        <div className={styles.name}>{boiler.model}</div>
      </div>
      <dl className={styles.facts}>
        <dt>Regeling</dt>
        <dd>{boiler.control}</dd>
        <dt>Gegevens</dt>
        <dd>{boiler.data_source}</dd>
        <dt>Warmtevraag</dt>
        <dd>{boiler.heat_demand_source}</dd>
      </dl>
    </Card>
  );
}

function CircuitCard({ circuit, profile }: { circuit: Circuit; profile: InstallationProfile }) {
  const direct = circuit.kind === 'direct';
  const rooms = circuit.rooms.map((key) => profile.rooms.find((r) => r.key === key));
  return (
    <Card className={styles.card}>
      <div className={styles.cardHead}>
        <IconBadge
          icon={
            direct ? (
              <Thermometer size={ICON_SIZE} aria-hidden="true" />
            ) : (
              <Waves size={ICON_SIZE} aria-hidden="true" />
            )
          }
          tone={direct ? 'rose' : 'blue'}
          size="lg"
        />
        <Pill tone={direct ? 'slate' : 'blue'}>
          {direct ? 'Direct op ketel' : 'Via mengverdeler'}
        </Pill>
      </div>
      <div>
        <div className={styles.label}>{circuit.name}</div>
        <div className={styles.name}>{emitterTitle(circuit)}</div>
      </div>
      <div className={styles.chips}>
        {circuit.rooms.map((key, i) => {
          const room = rooms[i];
          return (
            <span key={key} className={styles.chip}>
              {room?.name ?? key}
              {room?.is_thermostat ? ' · thermostaat' : room?.has_sensor ? ' · sensor' : ''}
            </span>
          );
        })}
      </div>
      {circuit.note ? <p className={styles.note}>{circuit.note}</p> : null}
    </Card>
  );
}

function SpecRow({ spec, onEdit }: { spec: Specification; onEdit: () => void }) {
  const isPrice = spec.key === 'gas_price';
  const text = specText(spec);
  return (
    <li className={styles.spec}>
      <span className={styles.specKey}>{spec.label}</span>
      <span className={styles.specValue}>
        <span className={cx(styles.value, text === 'Onbekend' && styles.unknown)}>{text}</span>
        {spec.note ? <span className={styles.specNote}>{spec.note}</span> : null}
      </span>
      {isPrice ? (
        <Link to="/instellingen/analyse" className={styles.edit}>
          Instellen
        </Link>
      ) : (
        <button
          type="button"
          className={styles.edit}
          aria-label={`${spec.label} bewerken`}
          onClick={onEdit}
        >
          Bewerken
        </button>
      )}
    </li>
  );
}

export function InstallationScreen() {
  const installation = useInstallation();
  const [editKey, setEditKey] = useState<string | null>(null);
  const profile = installation.data;
  const editing = profile?.specifications.find((s) => s.key === editKey);

  return (
    <div className={styles.screen}>
      <PageHeader
        title="Installatieprofiel"
        subtitle={profile?.summary ?? 'Hoe de installatie in elkaar zit.'}
        icon={<Home size={ICON_SIZE} aria-hidden="true" />}
        tone="blue"
      />
      {installation.isPending ? (
        <SkeletonGroup>
          <div className={styles.cards}>
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} height={200} radius={20} />
            ))}
          </div>
          <div className={styles.lower}>
            <Skeleton height={300} radius={20} />
          </div>
        </SkeletonGroup>
      ) : installation.isError ? (
        <ErrorCallout
          subject="het installatieprofiel"
          onRetry={() => {
            void installation.refetch();
          }}
        />
      ) : (
        <>
          <div className={styles.cards}>
            <BoilerCard boiler={installation.data.boiler} />
            {installation.data.circuits.length === 0 ? (
              <Card>
                <EmptyState
                  icon={<Waves size={ICON_SIZE} aria-hidden="true" />}
                  title="Nog geen circuits beschreven"
                  headingLevel={2}
                >
                  Beschrijf of radiatoren direct op de ketel zitten of via een mengverdeler. Dat
                  bepaalt welke analyses kloppen.
                </EmptyState>
              </Card>
            ) : (
              installation.data.circuits.map((circuit) => (
                <CircuitCard key={circuit.id} circuit={circuit} profile={installation.data} />
              ))
            )}
          </div>
          <div className={styles.lower}>
            <Card className={styles.specs}>
              <h2 className={styles.h3}>Instellingen en specificaties</h2>
              <ul className={styles.specList}>
                {installation.data.specifications.map((spec) => (
                  <SpecRow
                    key={spec.key}
                    spec={spec}
                    onEdit={() => {
                      setEditKey(spec.key);
                    }}
                  />
                ))}
              </ul>
              <p className={styles.note}>
                Onbekende waarden blijven onbekend. Modulatie (%) wordt niet naar kW omgerekend
                zonder gevalideerde omrekening.
              </p>
            </Card>
            <RoomComfortPanel profile={installation.data} />
          </div>
          {editing ? (
            <SpecDialog
              key={editing.key}
              profile={installation.data}
              spec={editing}
              onClose={() => {
                setEditKey(null);
              }}
            />
          ) : null}
        </>
      )}
    </div>
  );
}
