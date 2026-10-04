import type { ReactNode } from 'react';
import type { Tone } from '../lib/semantics.ts';
import { IconBadge } from './IconBadge.tsx';
import styles from './PageHeader.module.css';
import { cx } from './tone.ts';

export interface PageHeaderProps {
  title: string;
  subtitle?: ReactNode;
  /** 44px badge; omit for the Overzicht style (28px heading without badge). */
  icon?: ReactNode;
  tone?: Tone;
  /** Right-aligned controls, e.g. a SegmentedControl. */
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, icon, tone = 'orange', actions }: PageHeaderProps) {
  return (
    <div className={styles.header}>
      <div className={styles.lead}>
        {icon ? <IconBadge icon={icon} tone={tone} size="lg" /> : null}
        <div>
          <h1 className={cx(styles.title, !icon && styles.large)}>{title}</h1>
          {subtitle ? (
            <p className={cx(styles.subtitle, !icon && styles.subtitleLarge)}>{subtitle}</p>
          ) : null}
        </div>
      </div>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </div>
  );
}
