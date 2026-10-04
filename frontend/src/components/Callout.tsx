import { BookOpen, CircleCheck, Info, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';
import styles from './Callout.module.css';
import { ICON_SIZE } from './icons.ts';
import { cx } from './tone.ts';

/**
 * info: explanation banner (violet, book) · warning: "Let op" (amber, info) ·
 * success: "in orde" (teal, check) · error: failure (rose, alert) · neutral (slate, info).
 * error/neutral/success come from docs/design/aanvullingen.md §0.2.
 */
export type CalloutTone = 'info' | 'warning' | 'success' | 'error' | 'neutral';

const DEFAULT_ICON: Record<CalloutTone, ReactNode> = {
  info: <BookOpen size={ICON_SIZE} />,
  warning: <Info size={ICON_SIZE} />,
  success: <CircleCheck size={ICON_SIZE} />,
  error: <TriangleAlert size={ICON_SIZE} />,
  neutral: <Info size={ICON_SIZE} />,
};

export interface CalloutProps {
  tone?: CalloutTone;
  /** Override the default icon; pass `null` for none. */
  icon?: ReactNode;
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Callout({ tone = 'info', icon, title, children, className }: CalloutProps) {
  const shownIcon = icon === undefined ? DEFAULT_ICON[tone] : icon;
  const role = tone === 'error' ? 'alert' : tone === 'warning' ? 'status' : undefined;
  return (
    <div className={cx(styles.callout, styles[tone], className)} role={role}>
      {shownIcon ? (
        <span className={styles.icon} aria-hidden="true">
          {shownIcon}
        </span>
      ) : null}
      <div className={styles.body}>
        {title ? <strong className={styles.title}>{title}</strong> : null}
        {children}
      </div>
    </div>
  );
}
