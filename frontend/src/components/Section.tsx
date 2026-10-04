import { useId, type ReactNode } from 'react';
import { Card, type CardPadding } from './Card.tsx';
import styles from './Section.module.css';

export interface SectionProps {
  title: ReactNode;
  /** Right-aligned action, e.g. a ghost "Alles bekijken ›" button. */
  action?: ReactNode;
  /** Secondary text next to the heading (13px, secondary colour). */
  description?: ReactNode;
  headingLevel?: 2 | 3 | 4;
  padding?: CardPadding;
  className?: string;
  children?: ReactNode;
}

/** White card with a 16px/700 heading and optional action (design v3 card pattern). */
export function Section({
  title,
  action,
  description,
  headingLevel = 3,
  padding = 'md',
  className,
  children,
}: SectionProps) {
  const headingId = useId();
  const Heading = `h${String(headingLevel)}` as 'h2' | 'h3' | 'h4';
  return (
    <Card
      as="section"
      padding={padding}
      aria-labelledby={headingId}
      {...(className ? { className } : {})}
    >
      <div className={styles.head}>
        <Heading id={headingId} className={styles.title}>
          {title}
        </Heading>
        {description ? <span className={styles.description}>{description}</span> : null}
        {action ? <div className={styles.action}>{action}</div> : null}
      </div>
      {children}
    </Card>
  );
}
