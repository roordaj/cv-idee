import { useId, useState, type ReactNode } from 'react';
import { GLOSS, type GlossaryTerm } from '../content/glossary.ts';
import { useExplain } from '../content/useExplain.ts';
import styles from './Term.module.css';

export interface TermProps {
  term: GlossaryTerm;
  /** Visible text; defaults to the term itself. */
  children?: ReactNode;
}

/** Inline glossary term with an accessible definition. Plain text when 'uitleg tonen' is off. */
export function Term({ term, children }: TermProps) {
  const { explain } = useExplain();
  const [open, setOpen] = useState(false);
  const id = useId();
  const label = children ?? term;
  if (!explain) return <>{label}</>;
  const show = () => {
    setOpen(true);
  };
  const hide = () => {
    setOpen(false);
  };
  return (
    <span className={styles.term} onMouseEnter={show} onMouseLeave={hide}>
      <button
        type="button"
        className={styles.trigger}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={show}
        onFocus={show}
        onBlur={hide}
        onKeyDown={(e) => {
          if (e.key === 'Escape') hide();
        }}
      >
        {label}
      </button>
      {open ? (
        <span role="tooltip" id={id} className={styles.pop}>
          {GLOSS[term]}
        </span>
      ) : null}
    </span>
  );
}
