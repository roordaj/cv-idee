import type { ReactNode } from 'react';
import { STATUS_TONE, statusText, type ConnectionStatus } from './connectionStatus.ts';
import styles from './StatusPill.module.css';
import { cx, toneVars } from './tone.ts';

export interface HeaderPillProps {
  icon?: ReactNode;
  muted?: boolean;
  className?: string;
  children: ReactNode;
}

/** White rounded header pill (13px, border), e.g. "CAN-bus via Home Assistant". */
export function HeaderPill({ icon, muted = false, className, children }: HeaderPillProps) {
  return (
    <div className={cx(styles.pill, muted && styles.muted, className)}>
      {icon}
      {children}
    </div>
  );
}

export interface StatusPillProps {
  status: ConnectionStatus;
}

/** Header connection status with coloured dot + tint ring. */
export function StatusPill({ status }: StatusPillProps) {
  return (
    <div className={styles.pill} role="status" style={toneVars(STATUS_TONE[status.state])}>
      <span className={styles.dot} aria-hidden="true" />
      {statusText(status)}
    </div>
  );
}

/** Extra slate pill shown when the backend serves stub data. */
export function StubDataPill() {
  return (
    <div className={styles.pill} style={toneVars('slate')}>
      <span className={styles.dot} aria-hidden="true" />
      Voorbeeldgegevens
    </div>
  );
}
