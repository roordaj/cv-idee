import type { CSSProperties } from 'react';
import type { Tone } from '../lib/semantics.ts';

export type ToneStyle = CSSProperties & Record<`--${string}`, string>;

/** CSS custom properties exposing a tone's base/tint/dark colour to a CSS Module. */
export function toneVars(tone: Tone): ToneStyle {
  return {
    '--tone-base': `var(--color-${tone})`,
    '--tone-tint': `var(--color-${tone}-tint)`,
    '--tone-dark': `var(--color-${tone}-dark)`,
  };
}

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}
