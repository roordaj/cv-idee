import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import styles from './Button.module.css';
import { cx } from './tone.ts';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /**
   * primary: orange, hover #d65a20 · secondary: white with border · ghost: link-style
   * ("Alles bekijken ›") · danger: secondary size, rose (design additions §0.3).
   */
  variant?: ButtonVariant;
  /** md: 10px 16px, radius 12 (default) · sm: 8px 14px, radius 10 */
  size?: ButtonSize;
  iconStart?: ReactNode;
  iconEnd?: ReactNode;
  /** Stretch to the container width. */
  block?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    iconStart,
    iconEnd,
    block = false,
    className,
    type = 'button',
    children,
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx(styles.button, styles[variant], styles[size], block && styles.block, className)}
      {...rest}
    >
      {iconStart}
      {children}
      {iconEnd}
    </button>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required: icon-only buttons need an accessible name. */
  'aria-label': string;
  icon: ReactNode;
}

/** Square 36×36 icon-only button (e.g. dialog close). */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { icon, className, type = 'button', title, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      title={title ?? rest['aria-label']}
      className={cx(styles.button, styles.icon, className)}
      {...rest}
    >
      {icon}
    </button>
  );
});
