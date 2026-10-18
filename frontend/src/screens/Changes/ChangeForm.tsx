import { Check, CircleAlert, Loader2, Plus } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useCreateChange } from '../../api/hooks/changes.ts';
import { useFindings } from '../../api/hooks/findings.ts';
import { Button } from '../../components/Button.tsx';
import { Card } from '../../components/Card.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { cx } from '../../components/tone.ts';
import styles from './Changes.module.css';
import { PARAMETERS } from './verdict.ts';
import { amsterdamLocalTime, changeTimeCandidates } from './changeTime.ts';
import type { components } from '../../api/schema';

interface Errors {
  at?: string;
  old?: string;
  next?: string;
}

function validate(oldValue: string, newValue: string): Errors {
  const errors: Errors = {};
  if (!oldValue.trim()) errors.old = 'Vul de oude waarde in.';
  if (!newValue.trim()) errors.next = 'Vul de nieuwe waarde in.';
  else if (oldValue.trim() && oldValue.trim() === newValue.trim())
    errors.next = 'De nieuwe waarde is gelijk aan de oude.';
  return errors;
}

export function ChangeForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [parameter, setParameter] = useState(PARAMETERS[0] ?? '');
  const [oldValue, setOldValue] = useState('');
  const [newValue, setNewValue] = useState('');
  const [findingId, setFindingId] = useState('');
  const [at, setAt] = useState(() => amsterdamLocalTime(new Date()));
  const [occurrence, setOccurrence] = useState(() => {
    const now = new Date();
    now.setUTCSeconds(0, 0);
    return now.toISOString();
  });
  const [reason, setReason] = useState('');
  const [actor, setActor] = useState<components['schemas']['ChangeActor']>('user');
  const candidates = changeTimeCandidates(at);
  const instant =
    candidates.length === 1 ? candidates[0] : candidates.find((c) => c === occurrence);
  const [errors, setErrors] = useState<Errors>({});
  const [saved, setSaved] = useState(false);
  const create = useCreateChange();
  const findings = useFindings();

  const check = () => {
    const next = validate(oldValue, newValue);
    if (candidates.length === 0)
      next.at = 'Vul een geldig tijdstip in. Deze tijd moet bestaan in Europe/Amsterdam.';
    else if (!instant) next.at = 'Kies welk tijdstip je bedoelt bij de overgang naar wintertijd.';
    else if (Date.parse(instant) > Date.now())
      next.at = 'Het tijdstip mag niet in de toekomst liggen.';
    setErrors(next);
    return next;
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    const found = check();
    if (found.old || found.next || found.at || !instant) return;
    create.mutate(
      {
        at: instant,
        actor,
        parameter,
        old_value: oldValue.trim(),
        new_value: newValue.trim(),
        reason: reason.trim(),
        finding_id: findingId || null,
      },
      {
        onSuccess: (created) => {
          setSaved(true);
          setOldValue('');
          setNewValue('');
          setFindingId('');
          setReason('');
          setAt(amsterdamLocalTime(new Date()));
          const now = new Date();
          now.setUTCSeconds(0, 0);
          setOccurrence(now.toISOString());
          setActor('user');
          onCreated(created.id);
        },
      },
    );
  };

  return (
    <Card padding="md">
      <form className={styles.form} onSubmit={submit} noValidate>
        <h2 className={styles.formTitle}>
          <Plus size={ICON_SIZE} aria-hidden="true" />
          Wijziging vastleggen
        </h2>
        <label className={styles.field}>
          Tijdstip (Europe/Amsterdam)
          <input
            type="datetime-local"
            className={cx(styles.input, errors.at && styles.invalid)}
            value={at}
            aria-invalid={errors.at ? 'true' : undefined}
            aria-describedby={errors.at ? 'change-at-error' : undefined}
            onChange={(e) => {
              setAt(e.target.value);
              setOccurrence('');
            }}
          />
        </label>
        {candidates.length > 1 ? (
          <label className={styles.field}>
            Tijd bij overgang naar wintertijd
            <select
              className={styles.input}
              value={occurrence}
              onChange={(e) => {
                setOccurrence(e.target.value);
              }}
            >
              <option value="">Kies een tijdstip</option>
              <option value={candidates[0]}>Eerste keer (zomertijd, UTC+02:00)</option>
              <option value={candidates[1]}>Tweede keer (wintertijd, UTC+01:00)</option>
            </select>
          </label>
        ) : null}
        {errors.at ? (
          <div id="change-at-error" role="alert" className={styles.error}>
            {errors.at}
          </div>
        ) : null}
        <label className={styles.field}>
          Parameter
          <select
            className={styles.input}
            value={parameter}
            onChange={(e) => {
              setParameter(e.target.value);
            }}
          >
            {PARAMETERS.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <div className={styles.pair}>
          <label className={styles.field}>
            Oude waarde
            <input
              className={cx(styles.input, errors.old && styles.invalid)}
              value={oldValue}
              placeholder="60 °C"
              aria-invalid={errors.old ? 'true' : undefined}
              aria-describedby={errors.old ? 'change-old-error' : undefined}
              onChange={(e) => {
                setOldValue(e.target.value);
              }}
              onBlur={check}
            />
          </label>
          <label className={styles.field}>
            Nieuwe waarde
            <input
              className={cx(styles.input, errors.next && styles.invalid)}
              value={newValue}
              placeholder="70 °C"
              aria-invalid={errors.next ? 'true' : undefined}
              aria-describedby={errors.next ? 'change-new-error' : undefined}
              onChange={(e) => {
                setNewValue(e.target.value);
              }}
              onBlur={check}
            />
          </label>
        </div>
        {errors.old ? (
          <div id="change-old-error" className={styles.error}>
            <CircleAlert size={14} aria-hidden="true" />
            {errors.old}
          </div>
        ) : null}
        {errors.next ? (
          <div id="change-new-error" className={styles.error}>
            <CircleAlert size={14} aria-hidden="true" />
            {errors.next}
          </div>
        ) : null}
        <label className={styles.field}>
          Reden
          <textarea
            className={styles.input}
            value={reason}
            maxLength={280}
            rows={3}
            onChange={(e) => {
              setReason(e.target.value);
            }}
          />
        </label>
        <label className={styles.field}>
          Uitgevoerd door
          <select
            className={styles.input}
            value={actor}
            onChange={(e) => {
              setActor(e.target.value as components['schemas']['ChangeActor']);
            }}
          >
            <option value="user">Gebruiker</option>
            <option value="installer">Installateur</option>
            <option value="other">Anders</option>
          </select>
        </label>
        <label className={styles.field}>
          Gekoppeld advies
          <select
            className={styles.input}
            value={findingId}
            onChange={(e) => {
              setFindingId(e.target.value);
            }}
          >
            <option value="">Geen</option>
            {(findings.data?.items ?? []).map((f) => (
              <option key={f.id} value={f.id}>
                {f.id} · {f.title}
              </option>
            ))}
          </select>
        </label>
        {create.isError ? (
          <div role="alert" className={styles.error}>
            <CircleAlert size={14} aria-hidden="true" />
            Vastleggen is mislukt. Probeer het opnieuw.
          </div>
        ) : null}
        <Button
          type="submit"
          disabled={create.isPending}
          iconStart={
            create.isPending ? (
              <Loader2 size={16} aria-hidden="true" />
            ) : (
              <Check size={ICON_SIZE} aria-hidden="true" />
            )
          }
        >
          Vastleggen
        </Button>
        {saved ? (
          <div role="status" className={styles.ok}>
            <Check size={12} aria-hidden="true" />
            Wijziging vastgelegd
          </div>
        ) : null}
      </form>
    </Card>
  );
}
