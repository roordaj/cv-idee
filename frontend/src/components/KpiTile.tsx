import type { ReactNode } from 'react';
import type { Tone } from '../lib/semantics.ts';
import { IconBadge } from './IconBadge.tsx';
import styles from './KpiTile.module.css';
import { cx } from './tone.ts';

export interface KpiTileProps {
  icon: ReactNode;
  tone: Tone;
  label: string;
  /** Pre-formatted value ("20,4 °C"). Use "—" for unknown, never 0. */
  value: string;
  sub?: string;
  /** Plain-language explanation, shown under a dashed line ("uitleg tonen"). */
  explain?: string;
  /** Colour the value (e.g. rose for "Kort tijdens warmtevraag" on Cycli). */
  valueTone?: Tone;
  /** compact: Cycli variant (padding 14, 30px badge, sub 11px). */
  compact?: boolean;
}

export function KpiTile({
  icon,
  tone,
  label,
  value,
  sub,
  explain,
  valueTone,
  compact = false,
}: KpiTileProps) {
  return (
    <div className={cx(styles.tile, compact && styles.compact)}>
      <IconBadge icon={icon} tone={tone} size={compact ? 'sm' : 'md'} />
      <div>
        <div className={styles.label}>{label}</div>
        <div
          className={styles.value}
          style={valueTone ? { color: `var(--color-${valueTone})` } : undefined}
        >
          {value}
        </div>
        {sub ? <div className={styles.sub}>{sub}</div> : null}
        {explain ? <div className={styles.explain}>{explain}</div> : null}
      </div>
    </div>
  );
}
