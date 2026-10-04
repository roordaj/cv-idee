import { useRef, type KeyboardEvent } from 'react';
import styles from './SegmentedControl.module.css';
import { cx } from './tone.ts';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

/**
 * subtle: grey track, selected segment white with shadow (Meldingen) ·
 * accent: white track with border, selected segment orange (Cycli time range).
 */
export type SegmentedVariant = 'subtle' | 'accent';

export interface SegmentedControlProps<T extends string> {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Accessible name for the group. */
  label: string;
  variant?: SegmentedVariant;
  /** Segments share the full width (Meldingen) instead of hugging their labels. */
  fill?: boolean;
  className?: string;
}

/** Single-select segmented control: a radio group with roving focus and arrow-key navigation. */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  variant = 'subtle',
  fill = false,
  className,
}: SegmentedControlProps<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );

  const select = (index: number) => {
    const option = options[index];
    if (!option) return;
    onChange(option.value);
    refs.current[index]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = options.length - 1;
    let next: number;
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        next = index === last ? 0 : index + 1;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        next = index === 0 ? last : index - 1;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = last;
        break;
      default:
        return;
    }
    event.preventDefault();
    select(next);
  };

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cx(styles.group, styles[variant], fill && styles.fill, className)}
    >
      {options.map((option, index) => {
        const checked = index === selectedIndex;
        return (
          <button
            key={option.value}
            ref={(el) => {
              refs.current[index] = el;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            className={cx(styles.segment, checked && styles.selected)}
            onClick={() => {
              onChange(option.value);
            }}
            onKeyDown={(event) => {
              onKeyDown(event, index);
            }}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
