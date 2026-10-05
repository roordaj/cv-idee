import { Check, CircleAlert, Loader2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useHaEntities, useUpdateSignal } from '../../api/hooks/signals.ts';
import { Button } from '../../components/Button.tsx';
import { Card } from '../../components/Card.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { SegmentedControl } from '../../components/SegmentedControl.tsx';
import { Toggle } from '../../components/Toggle.tsx';
import { cx } from '../../components/tone.ts';
import { EntityPicker } from './EntityPicker.tsx';
import styles from './Signals.module.css';
import {
  AGE_UNITS,
  ageSeconds,
  checkUnit,
  splitAge,
  VALUE_KINDS,
  type AgeUnit,
  type HaEntity,
  type Signal,
  type ValueKind,
} from './signalFormat.ts';

const MIN_AGE_S = 5;
const MAX_AGE_S = 24 * 3600;

export interface SignalPanelProps {
  signal: Signal;
  signals: readonly Signal[];
}

/** "Signaal instellen": edits the mapping of one signal. Remount (key) per signal. */
export function SignalPanel({ signal, signals }: SignalPanelProps) {
  const initialAge = splitAge(signal.max_age_s);
  const [entityId, setEntityId] = useState<string | null>(signal.entity_id);
  const [unit, setUnit] = useState(signal.unit ?? '');
  const [ageAmount, setAgeAmount] = useState(initialAge.amount);
  const [ageUnit, setAgeUnit] = useState<AgeUnit>(initialAge.unit);
  const [regular, setRegular] = useState(signal.expects_regular_updates);
  const [location, setLocation] = useState(signal.location ?? '');
  const [kind, setKind] = useState<ValueKind | null>(signal.value_kind);
  const [meaning, setMeaning] = useState(signal.meaning ?? '');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [ageError, setAgeError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const update = useUpdateSignal();
  const entities = useHaEntities();

  const entity = entities.data?.find((e) => e.id === entityId);
  const unitCheck = checkUnit(signal.unit, entity);
  const alsoLinked =
    entityId !== null && entityId !== signal.entity_id
      ? signals.find((s) => s.id !== signal.id && s.entity_id === entityId)
      : undefined;

  const validateAge = (): number | null | undefined => {
    if (!regular || !ageAmount.trim()) {
      setAgeError(null);
      return null;
    }
    const seconds = ageSeconds(ageAmount, ageUnit);
    if (seconds === null || seconds < MIN_AGE_S || seconds > MAX_AGE_S) {
      setAgeError('Kies een leeftijd tussen 5 seconden en 24 uur.');
      return undefined;
    }
    setAgeError(null);
    return seconds;
  };

  const save = (nextEntityId: string | null) => {
    setSaved(false);
    const maxAge = nextEntityId === null ? signal.max_age_s : validateAge();
    if (maxAge === undefined) return;
    update.mutate(
      {
        signalId: signal.id,
        body: {
          entity_id: nextEntityId,
          unit: unit.trim() || null,
          location: location.trim() || null,
          value_kind: kind,
          meaning: meaning.trim() || null,
          max_age_s: maxAge,
          expects_regular_updates: regular,
        },
      },
      {
        onSuccess: () => {
          setSaved(true);
          setConfirmUnlink(false);
          if (nextEntityId === null) setEntityId(null);
        },
      },
    );
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    save(entityId);
  };

  const pick = (picked: HaEntity) => {
    setEntityId(picked.id);
    if (!unit && picked.unit) setUnit(picked.unit);
    setPickerOpen(false);
    setSaved(false);
  };

  return (
    <Card as="aside" padding="md" className={styles.sticky} aria-label="Signaal instellen">
      <form className={styles.form} onSubmit={submit} noValidate>
        <div className={styles.eyebrow}>Signaal instellen</div>
        <h2 className={styles.panelTitle}>{signal.name}</h2>
        <div className={styles.field}>
          <label htmlFor="signal-entity">Home Assistant-entiteit</label>
          <input
            id="signal-entity"
            className={styles.input}
            readOnly
            value={entityId ?? ''}
            placeholder="Kies een entiteit…"
            onClick={() => {
              setPickerOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setPickerOpen(true);
              }
            }}
          />
          <div className={styles.row}>
            <button
              type="button"
              className={styles.link}
              onClick={() => {
                setPickerOpen(true);
              }}
            >
              {entityId ? 'Andere entiteit kiezen' : 'Entiteit kiezen'}
            </button>
            {signal.entity_id ? (
              <button
                type="button"
                className={styles.link}
                onClick={() => {
                  setConfirmUnlink(true);
                }}
              >
                Ontkoppelen
              </button>
            ) : null}
          </div>
        </div>
        {confirmUnlink ? (
          <div className={styles.confirm} role="alertdialog" aria-label="Ontkoppelen bevestigen">
            <span>
              Ontkoppel {signal.name}? Analyses die dit signaal nodig hebben worden beperkt of niet
              beschikbaar. Bestaande gegevens blijven bewaard.
            </span>
            <div className={styles.confirmActions}>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  setConfirmUnlink(false);
                }}
              >
                Annuleren
              </Button>
              <Button
                size="sm"
                variant="danger"
                disabled={update.isPending}
                onClick={() => {
                  save(null);
                }}
              >
                Ontkoppelen
              </Button>
            </div>
          </div>
        ) : null}
        {alsoLinked ? (
          <div className={styles.warn} role="status">
            Deze entiteit is ook gekoppeld aan {alsoLinked.name}. Klopt dat?
          </div>
        ) : null}
        {unitCheck.kind === 'convert' ? <div className={styles.info}>{unitCheck.text}</div> : null}
        {unitCheck.kind === 'mismatch' ? (
          <div className={styles.error} role="alert">
            <CircleAlert size={14} aria-hidden="true" />
            {unitCheck.text}
          </div>
        ) : null}
        <div className={styles.pair}>
          <label className={styles.field}>
            Eenheid
            <input
              className={styles.input}
              value={unit}
              onChange={(e) => {
                setUnit(e.target.value);
              }}
            />
          </label>
          <div className={styles.field}>
            <label htmlFor="signal-max-age">Max. leeftijd</label>
            <div className={styles.pair}>
              <input
                id="signal-max-age"
                className={cx(styles.input, ageError && styles.invalid)}
                inputMode="decimal"
                disabled={!regular}
                value={regular ? ageAmount : ''}
                placeholder={regular ? '' : 'n.v.t.'}
                aria-invalid={ageError ? 'true' : undefined}
                aria-describedby={ageError ? 'signal-age-error' : undefined}
                onChange={(e) => {
                  setAgeAmount(e.target.value);
                }}
                onBlur={() => {
                  validateAge();
                }}
              />
              <select
                className={styles.input}
                aria-label="Eenheid van max. leeftijd"
                disabled={!regular}
                value={ageUnit}
                onChange={(e) => {
                  setAgeUnit(e.target.value as AgeUnit);
                }}
              >
                {AGE_UNITS.map((u) => (
                  <option key={u.value} value={u.value}>
                    {u.value}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
        {ageError ? (
          <div id="signal-age-error" className={styles.error}>
            <CircleAlert size={14} aria-hidden="true" />
            {ageError}
          </div>
        ) : null}
        <Toggle checked={regular} onChange={setRegular} label="Verwacht regelmatige updates" />
        <p className={styles.hint}>
          Aan als het signaal ook zonder verandering regelmatig een waarde stuurt. Alleen dan kan de
          app aan de leeftijd zien dat een meting verouderd is.
        </p>
        <label className={styles.field}>
          Sensorlocatie
          <input
            className={styles.input}
            value={location}
            onChange={(e) => {
              setLocation(e.target.value);
            }}
          />
        </label>
        <div className={styles.group}>
          Soort waarde
          <SegmentedControl
            label="Soort waarde"
            value={kind ?? 'measured'}
            onChange={setKind}
            options={VALUE_KINDS}
          />
        </div>
        <label className={styles.field}>
          Betekenis
          <textarea
            className={styles.input}
            rows={3}
            value={meaning}
            onChange={(e) => {
              setMeaning(e.target.value);
            }}
          />
        </label>
        {update.isError ? (
          <div role="alert" className={styles.error}>
            <CircleAlert size={14} aria-hidden="true" />
            Opslaan is mislukt. Probeer het opnieuw.
          </div>
        ) : null}
        <div className={styles.actions}>
          <Button
            type="submit"
            disabled={update.isPending || unitCheck.kind === 'mismatch'}
            iconStart={
              update.isPending ? (
                <Loader2 size={16} aria-hidden="true" />
              ) : (
                <Check size={ICON_SIZE} aria-hidden="true" />
              )
            }
          >
            Koppeling opslaan
          </Button>
          {saved ? (
            <div role="status" className={styles.ok}>
              <Check size={12} aria-hidden="true" />
              Opgeslagen
            </div>
          ) : null}
        </div>
      </form>
      {pickerOpen ? (
        <EntityPicker
          open
          signal={signal}
          current={entityId}
          signals={signals}
          onClose={() => {
            setPickerOpen(false);
          }}
          onPick={pick}
        />
      ) : null}
    </Card>
  );
}
