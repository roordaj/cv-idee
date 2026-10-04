import { Repeat } from 'lucide-react';
import { Button } from './Button.tsx';
import { Callout } from './Callout.tsx';
import styles from './ErrorCallout.module.css';
import { ICON_SIZE } from './icons.ts';

export interface ErrorCalloutProps {
  /** Subject in "Kon {subject} niet laden." */
  subject: string;
  onRetry?: () => void;
  /** Technical details (HTTP status, endpoint, time), collapsed by default. */
  details?: string;
}

/** Per-card load error (docs/design/aanvullingen.md §0.3 and §5a). */
export function ErrorCallout({ subject, onRetry, details }: ErrorCalloutProps) {
  return (
    <Callout tone="error">
      <span>
        Kon {subject} niet laden. De analyse zelf draait gewoon door; dit gaat alleen over het
        tonen.
      </span>
      {onRetry ? (
        <div className={styles.actions}>
          <Button
            variant="secondary"
            size="sm"
            iconStart={<Repeat size={ICON_SIZE} aria-hidden="true" />}
            onClick={onRetry}
          >
            Opnieuw proberen
          </Button>
        </div>
      ) : null}
      {details ? (
        <details className={styles.details}>
          <summary>Technische details</summary>
          <code>{details}</code>
        </details>
      ) : null}
    </Callout>
  );
}
