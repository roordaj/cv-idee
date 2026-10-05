import { CircleAlert, Loader2, Sliders } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useUpdateInstallation } from '../../api/hooks/installation.ts';
import { Button } from '../../components/Button.tsx';
import { Dialog } from '../../components/Dialog.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import styles from './Installation.module.css';
import {
  parseSpecValue,
  STATUS_OPTIONS,
  valueToField,
  type InstallationProfile,
  type Specification,
  type SpecStatus,
} from './specFormat.ts';

export interface SpecDialogProps {
  profile: InstallationProfile;
  spec: Specification;
  onClose: () => void;
}

/** Edits one specification; the whole profile is sent back with the revision read. */
export function SpecDialog({ profile, spec, onClose }: SpecDialogProps) {
  const [status, setStatus] = useState<SpecStatus>(spec.status);
  const [value, setValue] = useState(valueToField(spec.value));
  const [note, setNote] = useState(spec.note);
  const [error, setError] = useState<string | null>(null);
  const update = useUpdateInstallation();
  const dirty = status !== spec.status || value !== valueToField(spec.value) || note !== spec.note;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const parsed = status === 'known' ? parseSpecValue(value) : null;
    if (status === 'known' && parsed === null) {
      setError('Vul een waarde in, of kies "Onbekend".');
      return;
    }
    setError(null);
    update.mutate(
      {
        boiler: profile.boiler,
        circuits: profile.circuits,
        rooms: profile.rooms,
        revision: profile.revision,
        specifications: profile.specifications.map((s) =>
          s.key === spec.key ? { ...s, status, value: parsed, note } : s,
        ),
      },
      { onSuccess: onClose },
    );
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={spec.label}
      subtitle="Onbekende waarden blijven onbekend."
      icon={<Sliders size={ICON_SIZE} aria-hidden="true" />}
      tone="blue"
      isDirty={dirty}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Annuleren
          </Button>
          <Button
            type="submit"
            form="spec-form"
            disabled={update.isPending}
            iconStart={update.isPending ? <Loader2 size={16} aria-hidden="true" /> : undefined}
          >
            Opslaan
          </Button>
        </>
      }
    >
      <form id="spec-form" className={styles.form} onSubmit={submit} noValidate>
        <label className={styles.field}>
          Status
          <select
            className={styles.input}
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as SpecStatus);
            }}
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {status === 'known' ? (
          <label className={styles.field}>
            {spec.unit ? `Waarde (${spec.unit})` : 'Waarde'}
            <input
              className={styles.input}
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
              }}
              aria-invalid={error ? 'true' : undefined}
            />
          </label>
        ) : null}
        {error ? (
          <div role="alert" className={styles.error}>
            <CircleAlert size={14} aria-hidden="true" />
            {error}
          </div>
        ) : null}
        <label className={styles.field}>
          Notitie
          <input
            className={styles.input}
            value={note}
            onChange={(e) => {
              setNote(e.target.value);
            }}
          />
        </label>
        {update.isError ? (
          <div role="alert" className={styles.error}>
            <CircleAlert size={14} aria-hidden="true" />
            Opslaan is mislukt. Probeer het opnieuw.
          </div>
        ) : null}
      </form>
    </Dialog>
  );
}
