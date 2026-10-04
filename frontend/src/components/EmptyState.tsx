import type { ReactNode } from 'react';
import type { Tone } from '../lib/semantics.ts';
import styles from './EmptyState.module.css';
import { IconBadge } from './IconBadge.tsx';

export interface EmptyStateProps {
  icon: ReactNode;
  /** Badge tone; slate by default (docs/design/aanvullingen.md §0.3). */
  tone?: Tone;
  title: string;
  children?: ReactNode;
  /** One optional follow-up action (primary or secondary button, or link button). */
  action?: ReactNode;
  headingLevel?: 2 | 3;
}

export function EmptyState({
  icon,
  tone = 'slate',
  title,
  children,
  action,
  headingLevel = 3,
}: EmptyStateProps) {
  const Heading = headingLevel === 2 ? 'h2' : 'h3';
  return (
    <div className={styles.empty}>
      <IconBadge icon={icon} tone={tone} size="xl" />
      <Heading className={styles.title}>{title}</Heading>
      {children ? <p className={styles.text}>{children}</p> : null}
      {action ? <div className={styles.action}>{action}</div> : null}
    </div>
  );
}
