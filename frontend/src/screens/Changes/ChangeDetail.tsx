import { Activity, CircleCheck, Hourglass, TriangleAlert } from 'lucide-react';
import { useChangeEvaluation } from '../../api/hooks/changes.ts';
import type { components } from '../../api/schema';
import { Card } from '../../components/Card.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { Pill } from '../../components/Tag.tsx';
import { PALETTE } from '../../lib/semantics.ts';
import styles from './Changes.module.css';
import {
  ACTOR_LABEL,
  ASSESSMENT_TONE,
  COMPARABLE_LABEL,
  COMPARABLE_TONE,
  VERDICT_TONE,
  formatDateTime,
} from './verdict.ts';

type Change = components['schemas']['Change'];

function ResultIcon({ verdict }: { verdict: Change['verdict'] }) {
  if (verdict === 'improved') return <CircleCheck size={ICON_SIZE} aria-hidden="true" />;
  if (verdict === 'pending') return <Hourglass size={ICON_SIZE} aria-hidden="true" />;
  if (verdict === 'worsened' || verdict === 'trade_off')
    return <TriangleAlert size={ICON_SIZE} aria-hidden="true" />;
  return <Activity size={ICON_SIZE} aria-hidden="true" />;
}

export function ChangeDetail({ change }: { change: Change }) {
  const evaluation = useChangeEvaluation(change.id);

  return (
    <>
      <Card padding="lg" className={styles.head}>
        <p className={styles.meta}>
          {change.id}&#160;·&#160;{formatDateTime(change.at)}&#160;·&#160;door{' '}
          {ACTOR_LABEL[change.actor]}
        </p>
        <h2 className={styles.h2}>
          {change.parameter}: {change.old_value} → {change.new_value}
        </h2>
        <p className={styles.reason}>
          {change.reason ? `Reden: ${change.reason}` : 'Geen reden opgegeven'}
        </p>
      </Card>

      {evaluation.isPending ? (
        <SkeletonGroup>
          <Skeleton height={110} radius={20} />
        </SkeletonGroup>
      ) : evaluation.isError ? (
        <ErrorCallout
          subject="de evaluatie"
          onRetry={() => {
            void evaluation.refetch();
          }}
        />
      ) : (
        <>
          <Card tone={VERDICT_TONE[evaluation.data.verdict]} className={styles.result}>
            <ResultIcon verdict={evaluation.data.verdict} />
            <div className={styles.resultBody}>
              <div className={styles.resultLabel}>Resultaat voor/na</div>
              <div className={styles.resultVerdict}>{evaluation.data.verdict_text}</div>
              <p className={styles.resultText}>
                {evaluation.data.verdict === 'pending' && evaluation.data.result_expected_at
                  ? `Evaluatie loopt — resultaat na ${formatDateTime(evaluation.data.result_expected_at)}.`
                  : evaluation.data.summary}
              </p>
            </div>
          </Card>

          {evaluation.data.metrics.length > 0 ? (
            <Card as="section" aria-labelledby="ba-title">
              <div className={styles.baHead}>
                <h3 id="ba-title" className={styles.h3}>
                  Voor en na
                </h3>
                <span className={styles.legend}>
                  <span className={styles.legendItem}>
                    <span className={styles.swatch} style={{ background: '#c3c8d2' }} />
                    Voor ·&#160;{evaluation.data.before_text}
                  </span>
                  <span className={styles.legendItem}>
                    <span className={styles.swatch} style={{ background: PALETTE.violet.base }} />
                    Na ·&#160;{evaluation.data.after_text}
                  </span>
                </span>
              </div>
              {evaluation.data.metrics.map((m) => (
                <div key={m.label} className={styles.metric}>
                  <div className={styles.metricLabel}>
                    <div className={styles.metricName}>{m.label}</div>
                    <div className={styles.metricNote}>{m.note}</div>
                  </div>
                  <div className={styles.bars}>
                    <div className={styles.barRow}>
                      <span
                        className={styles.bar}
                        style={{ background: '#c3c8d2', width: `${String(m.before_bar_pct)}%` }}
                      />
                      <span>{m.before}</span>
                    </div>
                    <div className={styles.barRow}>
                      <span
                        className={styles.bar}
                        style={{
                          background: PALETTE.violet.base,
                          width: `${String(m.after_bar_pct)}%`,
                        }}
                      />
                      <strong>{m.after}</strong>
                    </div>
                  </div>
                  <Pill tone={ASSESSMENT_TONE[m.assessment]}>{m.effect_text}</Pill>
                </div>
              ))}
            </Card>
          ) : null}

          <Card as="section" aria-labelledby="comp-title" className={styles.stack}>
            <h3 id="comp-title" className={styles.h3}>
              Vergelijkbaarheid
            </h3>
            <div className={styles.cond}>
              {evaluation.data.conditions.map((c) => (
                <div key={c.label} className={styles.condItem}>
                  <div className={styles.condHead}>
                    <span className={styles.condKey}>{c.label}</span>
                    <Pill size="sm" tone={COMPARABLE_TONE[c.comparable]}>
                      {COMPARABLE_LABEL[c.comparable]}
                    </Pill>
                  </div>
                  <div className={styles.condVals}>
                    <strong>{c.before}</strong> → <strong>{c.after}</strong>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </>
  );
}
