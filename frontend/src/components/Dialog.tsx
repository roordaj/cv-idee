import { X } from 'lucide-react';
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import type { Tone } from '../lib/semantics.ts';
import { Button, IconButton } from './Button.tsx';
import styles from './Dialog.module.css';
import { IconBadge } from './IconBadge.tsx';
import { ICON_SIZE } from './icons.ts';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
const FIELDS = 'input:not([disabled]), select:not([disabled]), textarea:not([disabled])';

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
  children: ReactNode;
  /** Right-aligned footer actions: usually a secondary "Annuleren" and a primary button. */
  footer?: ReactNode;
  /** Left-aligned destructive action (DangerButton). */
  dangerAction?: ReactNode;
  /** When true, Esc / overlay click asks "Wijzigingen weggooien?" first. */
  isDirty?: boolean;
}

/**
 * Modal dialog (docs/design/aanvullingen.md §0.3). Becomes a bottom sheet below 640px.
 * Focus moves to the first field (or the title), is trapped, and returns to the opener on close.
 */
export function Dialog({
  open,
  onClose,
  title,
  subtitle,
  icon,
  tone = 'orange',
  children,
  footer,
  dangerAction,
  isDirty = false,
}: DialogProps) {
  const titleId = useId();
  const subtitleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const firstField = panelRef.current?.querySelector<HTMLElement>(FIELDS);
    (firstField ?? titleRef.current)?.focus();
    return () => {
      setConfirming(false);
      opener?.focus();
    };
  }, [open]);

  const requestClose = useCallback(() => {
    if (isDirty) {
      setConfirming(true);
    } else {
      onClose();
    }
  }, [isDirty, onClose]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      if (confirming) {
        setConfirming(false);
      } else {
        requestClose();
      }
      return;
    }
    if (event.key !== 'Tab' || !panelRef.current) return;
    const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) return;
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === titleRef.current)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  };

  if (!open) return null;

  return createPortal(
    <div
      className={styles.overlay}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        {...(subtitle ? { 'aria-describedby': subtitleId } : {})}
        className={styles.panel}
        onKeyDown={onKeyDown}
      >
        <div className={styles.head}>
          {icon ? <IconBadge icon={icon} tone={tone} size="lg" /> : null}
          <div className={styles.headText}>
            <h2 id={titleId} ref={titleRef} tabIndex={-1} className={styles.title}>
              {title}
            </h2>
            {subtitle ? (
              <p id={subtitleId} className={styles.subtitle}>
                {subtitle}
              </p>
            ) : null}
          </div>
          <IconButton
            aria-label="Sluiten"
            icon={<X size={ICON_SIZE} aria-hidden="true" />}
            onClick={requestClose}
          />
        </div>
        <div className={styles.body}>{children}</div>
        {confirming ? (
          <div className={styles.confirm} role="alertdialog" aria-label="Wijzigingen weggooien?">
            <strong>Wijzigingen weggooien?</strong>
            <div className={styles.confirmActions}>
              <Button
                variant="secondary"
                size="sm"
                autoFocus
                onClick={() => {
                  setConfirming(false);
                }}
              >
                Verder bewerken
              </Button>
              <Button variant="danger" size="sm" onClick={onClose}>
                Weggooien
              </Button>
            </div>
          </div>
        ) : null}
        {footer || dangerAction ? (
          <div className={styles.footer}>
            {dangerAction ? <div className={styles.danger}>{dangerAction}</div> : null}
            <div className={styles.actions}>{footer}</div>
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
