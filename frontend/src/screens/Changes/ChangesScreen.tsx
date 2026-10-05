import { Sliders } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { useChanges } from '../../api/hooks/changes.ts';
import { Card } from '../../components/Card.tsx';
import { EmptyState } from '../../components/EmptyState.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { IconBadge } from '../../components/IconBadge.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { cx, toneVars } from '../../components/tone.ts';
import { ChangeDetail } from './ChangeDetail.tsx';
import { ChangeForm } from './ChangeForm.tsx';
import styles from './Changes.module.css';
import { VERDICT_TONE, formatDateTime } from './verdict.ts';

export function ChangesScreen() {
  const changes = useChanges();
  const [params, setParams] = useSearchParams();
  const items = changes.data?.items ?? [];
  const selected = items.find((c) => c.id === params.get('wijziging')) ?? items[0];

  const select = (id: string) => {
    setParams({ wijziging: id }, { replace: true });
  };

  return (
    <div className={styles.screen}>
      <PageHeader
        title="Wijzigingen"
        subtitle="Wat er aan ketel of thermostaat is veranderd, en wat dat deed."
        icon={<Sliders size={ICON_SIZE} aria-hidden="true" />}
        tone="violet"
      />
      <div className={styles.layout}>
        <div className={styles.side}>
          <Card padding="sm" className={styles.logCard}>
            <h2 className={styles.cardTitle}>Logboek</h2>
            {changes.isPending ? (
              <SkeletonGroup>
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} height={58} radius={12} />
                ))}
              </SkeletonGroup>
            ) : changes.isError ? (
              <ErrorCallout
                subject="het logboek"
                onRetry={() => {
                  void changes.refetch();
                }}
              />
            ) : items.length === 0 ? (
              <EmptyState
                icon={<Sliders size={ICON_SIZE} aria-hidden="true" />}
                title="Nog geen wijzigingen vastgelegd"
              >
                Leg hier vast wat jij of de installateur aan ketel of thermostaat verandert. Dan
                meet de app het effect voor en na.
              </EmptyState>
            ) : (
              <ul className={styles.list} aria-label="Wijzigingen">
                {items.map((c) => {
                  const active = c.id === selected?.id;
                  const tone = VERDICT_TONE[c.verdict];
                  return (
                    <li key={c.id}>
                      <Link
                        to={`?wijziging=${c.id}`}
                        replace
                        aria-current={active ? 'true' : undefined}
                        className={cx(styles.item, active && styles.itemActive)}
                        style={toneVars(tone)}
                      >
                        <IconBadge
                          icon={<Sliders size={16} aria-hidden="true" />}
                          tone={tone}
                          size="sm"
                        />
                        <span className={styles.itemText}>
                          <span className={styles.date}>{formatDateTime(c.at)}</span>
                          <span className={styles.param}>{c.parameter}</span>
                          <span className={styles.verdict}>{c.verdict_text}</span>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
          <ChangeForm onCreated={select} />
        </div>
        <div className={styles.main}>
          {selected ? <ChangeDetail key={selected.id} change={selected} /> : null}
        </div>
      </div>
    </div>
  );
}
