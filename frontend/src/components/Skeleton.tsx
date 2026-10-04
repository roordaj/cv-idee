import type { CSSProperties, ReactNode } from 'react';
import styles from './Skeleton.module.css';

export interface SkeletonProps {
  width?: CSSProperties['width'];
  height?: CSSProperties['height'];
  /** Match the radius of the element it replaces. */
  radius?: CSSProperties['borderRadius'];
}

/** Pulsing placeholder block (docs/design/aanvullingen.md §0.3). Decorative only. */
export function Skeleton({ width = '100%', height = 16, radius = 8 }: SkeletonProps) {
  return (
    <span
      className={styles.block}
      style={{ width, height, borderRadius: radius }}
      aria-hidden="true"
    />
  );
}

export interface SkeletonGroupProps {
  children: ReactNode;
  className?: string | undefined;
}

/** Wraps skeleton blocks: marks the region busy and announces "Laden…" to screen readers. */
export function SkeletonGroup({ children, className }: SkeletonGroupProps) {
  return (
    <div aria-busy="true" className={className}>
      <span className="visually-hidden" role="status">
        Laden…
      </span>
      {children}
    </div>
  );
}
