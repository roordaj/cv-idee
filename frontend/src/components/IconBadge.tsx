import type { ReactNode } from 'react';
import type { Tone } from '../lib/semantics.ts';
import styles from './IconBadge.module.css';
import { cx, toneVars } from './tone.ts';

/** xs 22/r7 · sm 30/r9 · md 36/r11 · lg 44/r14 · xl 52/r16 (sizes used in design v3). */
export type IconBadgeSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

/**
 * soft: tint background, base icon colour (KPI tiles, page headers) ·
 * softDark: tint background, dark icon colour (finding detail section heads) ·
 * solid: base background, white icon (brand, "Aanbevolen actie").
 */
export type IconBadgeEmphasis = 'soft' | 'softDark' | 'solid';

export interface IconBadgeProps {
  icon: ReactNode;
  tone?: Tone;
  size?: IconBadgeSize;
  emphasis?: IconBadgeEmphasis;
  className?: string;
}

export function IconBadge({
  icon,
  tone = 'slate',
  size = 'md',
  emphasis = 'soft',
  className,
}: IconBadgeProps) {
  return (
    <span
      aria-hidden="true"
      className={cx(styles.badge, styles[size], styles[emphasis], className)}
      style={toneVars(tone)}
    >
      {icon}
    </span>
  );
}
