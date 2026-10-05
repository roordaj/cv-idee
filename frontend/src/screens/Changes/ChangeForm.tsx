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

interface Errors {
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
  const [errors, setErrors] = useState<Errors>({});
  const [saved, setSaved] = useState(false);
  const create = useCreateChange();
  const findings = useFindings();

  const check = () => {
    const next = validate(oldValue, newValue);
    setErrors(next);
    return next;
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSaved(false);
    const found = check();
    if (found.old || found.next) return;
    create.mutate(
      {
        at: new Date().toISOString(),
        actor: 'user',
        parameter,
        old_value: oldValue.trim(),
        new_value: newValue.trim(),
        reason: '',
        finding_id: findingId || null,
      },
      {
        onSuccess: (created) => {
          setSaved(true);
          setOldValue('');
          setNewValue('');
          setFindingId('');
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
