import type { ReactNode } from 'react';
import styles from './KeyValueGrid.module.css';
import { cx } from './tone.ts';

export interface KeyValueItem {
  key: string;
  value: ReactNode;
  /** Icon shown in the `tiles` variant (coloured via `iconColor`). */
  icon?: ReactNode;
  iconColor?: string;
}

/**
 * rows: label column 104px with row dividers (advice rows) ·
 * tiles: grey tiles separated by 1px gaps (evidence/"proof" grid) ·
 * compact: two-column definition list on a subtle background (Observatie / "Toen vastgelegd").
 */
export type KeyValueVariant = 'rows' | 'tiles' | 'compact';

export interface KeyValueGridProps {
  items: readonly KeyValueItem[];
  variant?: KeyValueVariant;
  className?: string;
}

export function KeyValueGrid({ items, variant = 'rows', className }: KeyValueGridProps) {
  return (
    <dl className={cx(styles.grid, styles[variant], className)}>
      {items.map((item) => (
        <div key={item.key} className={styles.item}>
          {variant === 'tiles' && item.icon ? (
            <span
              className={styles.icon}
              style={item.iconColor ? { color: item.iconColor } : undefined}
              aria-hidden="true"
            >
              {item.icon}
            </span>
          ) : null}
          <div className={styles.pair}>
            <dt className={styles.key}>{item.key}</dt>
            <dd className={styles.value}>{item.value}</dd>
          </div>
        </div>
      ))}
    </dl>
  );
}
