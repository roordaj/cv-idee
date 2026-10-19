import { useRef, useState } from 'react';
import { useHaEntities, useSignals, useUpdateSignal } from '../../api/hooks/signals.ts';
import { useUpdateInstallation } from '../../api/hooks/installation.ts';
import type { components } from '../../api/schema';
import { Button } from '../../components/Button.tsx';
import { Callout } from '../../components/Callout.tsx';
import { Card } from '../../components/Card.tsx';
import type { InstallationProfile } from './specFormat.ts';
import styles from './Installation.module.css';

type Zone = InstallationProfile['zones'][number];
type DraftZone = Zone & { draftId: string };
type Signal = components['schemas']['Signal'];
type Role = 'zone_demand' | 'valve_state';

function validateZones(zones: readonly Zone[], circuitIds: readonly string[]): string | null {
  const keys = new Set<string>();
  for (const zone of zones) {
    const key = zone.key.trim();
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(key))
      return 'Gebruik voor de zonesleutel alleen kleine letters, cijfers en koppeltekens.';
    if (keys.has(key)) return `De zonesleutel “${key}” komt meer dan één keer voor.`;
    keys.add(key);
    if (!zone.name.trim()) return `Vul een naam in voor zone “${key}”.`;
    if (!zone.circuit_key || !circuitIds.includes(zone.circuit_key))
      return `Kies een geldig circuit voor zone “${zone.name || key}”.`;
  }
  return null;
}

export function ZoneConfigurationPanel({ profile }: { profile: InstallationProfile }) {
  const [draft, setDraft] = useState<DraftZone[] | null>(null);
  const nextDraftId = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const update = useUpdateInstallation();
  const zones =
    draft ?? profile.zones.map((zone, index) => ({ ...zone, draftId: `saved-${String(index)}` }));
  const addZone = () => {
    const circuit = profile.circuits[0];
    if (!circuit) {
      setError('Voeg eerst een circuit toe aan het installatieprofiel.');
      return;
    }
    setDraft([
      ...zones,
      {
        key: `zone-${String(zones.length + 1)}`,
        name: '',
        circuit_key: circuit.id,
        draftId: `new-${String(nextDraftId.current++)}`,
      },
    ]);
    setError(null);
  };
  const save = () => {
    const normalized = zones.map((zone) => ({
      key: zone.key.trim(),
      name: zone.name.trim(),
      circuit_key: zone.circuit_key,
    }));
    const issue = validateZones(
      normalized,
      profile.circuits.map((c) => c.id),
    );
    if (issue) {
      setError(issue);
      return;
    }
    setError(null);
    update.mutate(
      {
        boiler: profile.boiler,
        circuits: profile.circuits,
        zones: normalized,
        rooms: profile.rooms,
        specifications: profile.specifications,
        revision: profile.revision,
      },
      {
        onSuccess: () => {
          setDraft(null);
        },
      },
    );
  };

  return (
    <Card className={styles.zoneConfig} id="zones">
      <div className={styles.comfortHead}>
        <div>
          <h2 className={styles.h3}>Zones per circuit</h2>
          <p className={styles.note}>
            Stabiele zonesleutels · signaalkoppelingen per profielversie
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={addZone}>
          Zone toevoegen
        </Button>
      </div>
      {!profile.circuits.length ? (
        <p className={styles.note}>Voeg eerst een circuit toe voordat je zones instelt.</p>
      ) : zones.length === 0 ? (
        <p className={styles.note}>
          Nog geen zones ingesteld. Zonder zones blijft de zoneanalyse onbekend.
        </p>
      ) : null}
      <div className={styles.zoneCards}>
        {zones.map((zone, index) => (
          <ZoneEditor
            key={zone.draftId}
            zone={zone}
            circuits={profile.circuits}
            onChange={(next) => {
              setDraft(
                zones.map((item, i) => (i === index ? { ...next, draftId: item.draftId } : item)),
              );
            }}
            onRemove={() => {
              setDraft(zones.filter((_, i) => i !== index));
            }}
          />
        ))}
      </div>
      {zones.length > 0 ? (
        <div className={styles.zoneSave}>
          <Button disabled={!draft || update.isPending} onClick={save}>
            {update.isPending ? 'Opslaan…' : 'Profiel opslaan'}
          </Button>
        </div>
      ) : null}
      {error ? (
        <Callout tone="error" title="Zoneprofiel niet opgeslagen">
          {error}
        </Callout>
      ) : null}
      {update.isError ? (
        <Callout tone="warning">
          Opslaan is mislukt. Controleer of het profiel intussen is gewijzigd.
        </Callout>
      ) : null}
      <Callout tone="warning">
        Zonevraag en gemelde klepstatus zijn aparte bronnen. Een gemelde status of commando bewijst
        geen fysieke opening of debiet. Opslaan wijzigt alleen het analyseprofiel; de app bedient
        geen kleppen, ketel of thermostaat.
      </Callout>
    </Card>
  );
}

function ZoneEditor({
  zone,
  circuits,
  onChange,
  onRemove,
}: {
  zone: Zone;
  circuits: readonly InstallationProfile['circuits'][number][];
  onChange: (zone: Zone) => void;
  onRemove: () => void;
}) {
  const signals = useSignals();
  const scoped = signals.data?.items.filter(
    (s) => s.scope_kind === 'zone' && s.scope_key === zone.key,
  );
  return (
    <article className={styles.zoneCard}>
      <div className={styles.zoneTitle}>
        <strong>{zone.name || 'Nieuwe zone'}</strong>
        <Button variant="secondary" size="sm" onClick={onRemove}>
          Verwijderen
        </Button>
      </div>
      <label className={styles.field}>
        Zonesleutel
        <input
          className={styles.input}
          value={zone.key}
          onChange={(e) => {
            onChange({ ...zone, key: e.target.value });
          }}
          aria-label={`Zonesleutel ${zone.name || zone.key}`}
        />
        <span className={styles.note}>
          Kleine letters, cijfers en koppeltekens; houd deze sleutel stabiel zodat historische
          koppelingen herkenbaar blijven.
        </span>
      </label>
      <label className={styles.field}>
        Naam
        <input
          className={styles.input}
          value={zone.name}
          onChange={(e) => {
            onChange({ ...zone, name: e.target.value });
          }}
          aria-label={`Zonenaam ${zone.name || zone.key}`}
        />
      </label>
      <label className={styles.field}>
        Circuit
        <select
          className={styles.input}
          value={zone.circuit_key ?? ''}
          onChange={(e) => {
            onChange({ ...zone, circuit_key: e.target.value || null });
          }}
          aria-label={`Circuit ${zone.name || zone.key}`}
        >
          <option value="">Kies een circuit</option>
          {circuits.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <ZoneSignalMapping
        key={`${zone.key}-demand-${String(scoped?.find((s) => s.role === 'zone_demand')?.mapping_version ?? 'new')}`}
        zone={zone}
        role="zone_demand"
        signal={scoped?.find((s) => s.role === 'zone_demand')}
      />
      <ZoneSignalMapping
        key={`${zone.key}-valve-${String(scoped?.find((s) => s.role === 'valve_state')?.mapping_version ?? 'new')}`}
        zone={zone}
        role="valve_state"
        signal={scoped?.find((s) => s.role === 'valve_state')}
      />
    </article>
  );
}

function ZoneSignalMapping({
  zone,
  role,
  signal,
}: {
  zone: Zone;
  role: Role;
  signal: Signal | undefined;
}) {
  const entities = useHaEntities();
  const update = useUpdateSignal();
  const [entityId, setEntityId] = useState(signal?.entity_id ?? '');
  const [meaning, setMeaning] = useState(signal?.meaning ?? '');
  const demand = role === 'zone_demand';
  const label = demand ? 'Zone vraagt warmte' : 'Klep meldt open/gesloten';
  const save = () => {
    if (!signal) return;
    update.mutate({
      signalId: signal.id,
      body: {
        entity_id: entityId || null,
        unit: signal.unit,
        location: zone.name,
        value_kind: signal.value_kind ?? 'reported',
        meaning: meaning.trim() || null,
        max_age_s: signal.max_age_s,
        expects_regular_updates: signal.expects_regular_updates,
      },
    });
  };
  return (
    <div className={styles.zoneSignal}>
      <label className={styles.field}>
        {label}
        <select
          className={styles.input}
          value={entityId}
          onChange={(e) => {
            setEntityId(e.target.value);
          }}
          aria-label={`${label} · ${zone.name || zone.key}`}
        >
          <option value="">Niet gekoppeld</option>
          {(entities.data ?? []).map((e) => (
            <option value={e.id} key={e.id}>
              {e.id}
              {e.friendly_name ? ` · ${e.friendly_name}` : ''}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.field}>
        Herkomst of betekenis
        <input
          className={styles.input}
          value={meaning}
          onChange={(e) => {
            setMeaning(e.target.value);
          }}
          aria-label={`Herkomst ${label} · ${zone.name || zone.key}`}
          placeholder={
            demand ? 'Bijv. gerapporteerde warmtevraag' : 'Bijv. status gemeld of commando'
          }
        />
      </label>
      <div className={styles.mappingFoot}>
        <span className={styles.note}>
          {signal?.entity_id
            ? `${signal.state === 'stale' ? 'Te oud' : signal.state === 'missing' ? 'Ontbreekt' : 'Gekoppeld'} · ${signal.value_kind === 'reported' ? 'gerapporteerd' : signal.value_kind === 'measured' ? 'gemeten' : (signal.meaning ?? 'bron onbekend')}`
            : 'Niet gekoppeld'}
        </span>
        <Button
          variant="secondary"
          size="sm"
          disabled={
            !signal ||
            update.isPending ||
            (entityId === (signal.entity_id ?? '') && meaning === (signal.meaning ?? ''))
          }
          onClick={save}
        >
          Koppeling opslaan
        </Button>
        {update.isError ? (
          <span role="alert" className={styles.errorText}>
            Opslaan mislukt.
          </span>
        ) : null}
      </div>
    </div>
  );
}
