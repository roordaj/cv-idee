import type { ReactNode } from 'react';
import type { Tone } from '../lib/semantics.ts';
import styles from './Tag.module.css';
import { cx, toneVars } from './tone.ts';

export type TagSize = 'sm' | 'md';

export interface TagProps {
  tone?: Tone;
  /** md: 3px 10px · 12px/600 (default) · sm: 2px 9px · 11px/700 */
  size?: TagSize;
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** Pill-shaped label (design v3 "pill"): tint background, dark text. */
export function Tag({ tone = 'slate', size = 'md', icon, className, children }: TagProps) {
  return (
    <span className={cx(styles.tag, styles[size], className)} style={toneVars(tone)}>
      {icon}
      {children}
    </span>
  );
}

export { Tag as Pill };
