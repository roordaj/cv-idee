import { GLOSS, TERMS } from '../content/glossary.ts';
import { useExplain } from '../content/useExplain.ts';
import { Card } from './Card.tsx';
import styles from './Term.module.css';

export interface TermsPanelProps {
  /** Finding id, e.g. 'B-014'. */
  findingId: string;
}

/** 'Begrippen in deze bevinding'. Renders nothing when explanations are off or no terms exist. */
export function TermsPanel({ findingId }: TermsPanelProps) {
  const { explain } = useExplain();
  const terms = TERMS[findingId];
  if (!explain || !terms || terms.length === 0) return null;
  return (
    <Card>
      <h3>Begrippen in deze bevinding</h3>
      <dl className={styles.panel}>
        {terms.map((t) => (
          <div key={t}>
            <dt>{t}</dt>
            <dd>{GLOSS[t]}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
