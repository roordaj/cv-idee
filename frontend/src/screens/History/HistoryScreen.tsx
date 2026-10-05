import { History, Info } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { useHistory } from '../../api/hooks/findings.ts';
import type { components } from '../../api/schema';
import { Callout } from '../../components/Callout.tsx';
import { Card } from '../../components/Card.tsx';
import { EmptyState } from '../../components/EmptyState.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { IconBadge } from '../../components/IconBadge.tsx';
import { KeyValueGrid } from '../../components/KeyValueGrid.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { Pill } from '../../components/Tag.tsx';
import { cx, toneVars } from '../../components/tone.ts';
import { formatDayMonth } from '../../lib/format.ts';
import {
  RECOMMENDATION_STATUS_TONE,
  type RecommendationStatus,
  type Tone,
} from '../../lib/semantics.ts';
import { formatDateTime } from '../Changes/verdict.ts';
import styles from './History.module.css';

type Entry = components['schemas']['HistoryEntry'];

function statusTone(status: Entry['status']): Tone {
  const key: RecommendationStatus = status === 'rollback_triggered' ? 'rollback' : status;
  return RECOMMENDATION_STATUS_TONE[key];
}

function periodText(entry: Entry): string {
  const p = entry.observation_period;
  if (!p) return 'onbekend';
  const start = formatDayMonth(new Date(p.start));
  return p.end ? `${start}–${formatDayMonth(new Date(p.end))}` : `vanaf ${start}`;
}

function Detail({ entry }: { entry: Entry }) {
  return (
    <Card className={styles.stack} aria-label="Toen vastgelegd">
      <p className={styles.kicker}>Toen vastgelegd</p>
      <h2 className={styles.h2}>{entry.recommendation}</h2>
      <p className={styles.why}>{entry.reasoning}</p>
      <KeyValueGrid
        variant="compact"
        items={[
          { key: 'Instellingen', value: entry.settings_text },
          { key: 'Regelversie', value: `${entry.rule.id} v${entry.rule.version}` },
          { key: 'Notitie', value: entry.note || '–' },
        ]}
      />
      <Callout tone="info" icon={<Info size={ICON_SIZE} />}>
        <strong>Sindsdien: </strong>
        {entry.rule_now_text}
      </Callout>
    </Card>
  );
}

export function HistoryScreen() {
  const history = useHistory();
  const [params] = useSearchParams();
  const items = history.data?.items ?? [];
  const selected = items.find((h) => h.id === params.get('advies')) ?? items[0];

  return (
    <div className={styles.screen}>
      <PageHeader
        title="Advieshistorie"
        subtitle="Elk advies met de meetperiode, instellingen en regelversie van dat moment"
        icon={<History size={ICON_SIZE} aria-hidden="true" />}
        tone="violet"
      />
      {history.isPending ? (
        <div className={styles.layout} aria-busy="true">
          <div className={styles.listCol}>
            <SkeletonGroup>
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} height={68} radius={16} />
              ))}
            </SkeletonGroup>
          </div>
          <div className={styles.detail}>
            <Skeleton height={320} radius={20} />
          </div>
        </div>
      ) : history.isError ? (
        <ErrorCallout
          subject="de advieshistorie"
          onRetry={() => {
            void history.refetch();
          }}
        />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<History size={ICON_SIZE} aria-hidden="true" />}
            title="Nog geen adviezen"
          >
            Elk advies dat de app geeft, wordt hier bewaard met de meetperiode, instellingen en
            regelversie van dat moment.
          </EmptyState>
        </Card>
      ) : (
        <div className={styles.layout}>
          <div className={styles.listCol}>
            <ul className={styles.list} aria-label="Adviezen">
              {items.map((h) => {
                const tone = statusTone(h.status);
                const active = h.id === selected?.id;
                return (
                  <li key={h.id}>
                    <Link
                      to={`?advies=${h.id}`}
                      replace
                      aria-current={active ? 'true' : undefined}
                      className={cx(styles.item, active && styles.itemActive)}
                      style={toneVars(tone)}
                    >
                      <IconBadge
                        icon={<History size={18} aria-hidden="true" />}
                        tone={tone}
                        size="lg"
                      />
                      <span className={styles.itemText}>
                        <span className={styles.advice}>{h.recommendation}</span>
                        <span className={styles.meta}>
                          {formatDateTime(h.recorded_at)} · {h.finding_id} · meetperiode{' '}
                          {periodText(h)}
                        </span>
                      </span>
                      <Pill tone={tone}>{h.status_text}</Pill>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
          <div className={styles.detail}>{selected ? <Detail entry={selected} /> : null}</div>
        </div>
      )}
    </div>
  );
}
