import type { HTMLAttributes, ReactNode } from 'react';
import type { Tone } from '../lib/semantics.ts';
import styles from './Card.module.css';
import { cx, toneVars } from './tone.ts';

export type CardPadding = 'none' | 'sm' | 'md' | 'lg';
export type CardRadius = 'tile' | 'kpi' | 'card';

export interface CardProps extends HTMLAttributes<HTMLElement> {
  /** Tinted card (no border, tint background), e.g. "Aanbevolen actie". */
  tone?: Tone;
  /** sm 16px · md 20px (default) · lg 22px */
  padding?: CardPadding;
  /** tile 14px · kpi 16px · card 20px (default) */
  radius?: CardRadius;
  as?: 'div' | 'section' | 'article' | 'aside';
  children?: ReactNode;
}

export function Card({
  tone,
  padding = 'md',
  radius = 'card',
  as: Element = 'div',
  className,
  style,
  children,
  ...rest
}: CardProps) {
  return (
    <Element
      className={cx(
        styles.card,
        tone ? styles.tinted : styles.plain,
        styles[`pad-${padding}`],
        styles[`radius-${radius}`],
        className,
      )}
      style={tone ? { ...toneVars(tone), ...style } : style}
      {...rest}
    >
      {children}
    </Element>
  );
}
