import styles from './Toggle.module.css';
import { cx } from './tone.ts';

export interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
  className?: string;
}

/** On/off switch (design v3 "Ruisonderdrukking"): `role="switch"` with the label on the right. */
export function Toggle({ checked, onChange, label, disabled = false, className }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      className={cx(styles.toggle, className)}
      onClick={() => {
        onChange(!checked);
      }}
    >
      <span className={cx(styles.track, checked && styles.on)} aria-hidden="true">
        <span className={styles.knob} />
      </span>
      <span>{label}</span>
    </button>
  );
}
