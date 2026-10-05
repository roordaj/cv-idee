import { Bell, House, Repeat, TriangleAlert, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  useNotificationPolicy,
  useNotifications,
  useUpdateNotificationPolicy,
} from '../../api/hooks/settings.ts';
import { useHaExport } from '../../api/hooks/signals.ts';
import type { components } from '../../api/schema';
import { Callout } from '../../components/Callout.tsx';
import { Card } from '../../components/Card.tsx';
import { ErrorCallout } from '../../components/ErrorCallout.tsx';
import { ICON_SIZE } from '../../components/icons.ts';
import { IconBadge } from '../../components/IconBadge.tsx';
import { PageHeader } from '../../components/PageHeader.tsx';
import { SegmentedControl, type SegmentedOption } from '../../components/SegmentedControl.tsx';
import { Skeleton, SkeletonGroup } from '../../components/Skeleton.tsx';
import { Pill } from '../../components/Tag.tsx';
import { Toggle } from '../../components/Toggle.tsx';
import { SEVERITY_LABEL, SEVERITY_TONE, type Severity, type Tone } from '../../lib/semantics.ts';
import { formatDateTime } from '../Changes/verdict.ts';
import styles from './Notifications.module.css';

type Policy = components['schemas']['NotificationPolicy'];
type Channel = components['schemas']['NotificationChannel'];
type Kind = components['schemas']['NotificationKind'];

const SEVERITIES: readonly Severity[] = ['high', 'medium', 'low', 'info'];

const CHANNEL_OPTIONS: readonly SegmentedOption<Channel>[] = [
  { value: 'direct', label: 'Direct' },
  { value: 'daily_digest', label: 'Dagbundel' },
  { value: 'weekly_report', label: 'Weekrapport' },
  { value: 'none', label: 'Geen' },
];

const KIND_VIEW: Record<Kind, { icon: LucideIcon; tone: Tone }> = {
  finding_new: { icon: Repeat, tone: 'orange' },
  finding_worsened: { icon: TriangleAlert, tone: 'rose' },
  finding_resolved: { icon: Bell, tone: 'green' },
  daily_digest: { icon: Bell, tone: 'violet' },
  weekly_report: { icon: Bell, tone: 'violet' },
};

const TRANSPORT_LABEL = { mqtt: 'MQTT', fallback: 'REST', none: 'Niet actief' } as const;

function PolicyCards({ policy }: { policy: Policy }) {
  const update = useUpdateNotificationPolicy();
  const save = (
    patch: Partial<Pick<Policy, 'channels' | 'bundle_related' | 'renotify_on_worsening'>>,
  ) => {
    update.mutate({
      channels: policy.channels,
      bundle_related: policy.bundle_related,
      renotify_on_worsening: policy.renotify_on_worsening,
      ...patch,
    });
  };
  return (
    <>
      <Card className={styles.card}>
        <h2 className={styles.h3}>Kanaal per ernst</h2>
        {SEVERITIES.map((s) => (
          <div key={s} className={styles.row}>
            <Pill tone={SEVERITY_TONE[s]} size="sm">
              {SEVERITY_LABEL[s]}
            </Pill>
            <SegmentedControl
              fill
              label={`Kanaal voor ernst ${SEVERITY_LABEL[s]}`}
              options={CHANNEL_OPTIONS}
              value={policy.channels[s]}
              onChange={(value) => {
                save({ channels: { ...policy.channels, [s]: value } });
              }}
            />
          </div>
        ))}
        {update.isError ? (
          <ErrorCallout
            subject="het meldingsbeleid"
            onRetry={() => {
              update.reset();
            }}
          />
        ) : null}
      </Card>
      <Card className={styles.card}>
        <h2 className={styles.h3}>Ruisonderdrukking</h2>
        <Toggle
          label="Meldingen bij hetzelfde patroon bundelen"
          checked={policy.bundle_related}
          onChange={(bundle_related) => {
            save({ bundle_related });
          }}
        />
        <Toggle
          label="Opnieuw melden als het erger wordt"
          checked={policy.renotify_on_worsening}
          onChange={(renotify_on_worsening) => {
            save({ renotify_on_worsening });
          }}
        />
        <div className={styles.summary}>
          Herstelcriterium (melding sluit pas daarna)
          <div className={styles.summaryBox}>{policy.recovery_text}</div>
          <Link to="/instellingen/analyse" className={styles.link}>
            Aanpassen in Analyse-instellingen ›
          </Link>
        </div>
      </Card>
    </>
  );
}

function HaExportCard() {
  const ha = useHaExport();
  return (
    <Card className={styles.card}>
      <div className={styles.exportHead}>
        <IconBadge icon={<House size={16} aria-hidden="true" />} tone="teal" size="md" />
        <div>
          <h2 className={styles.h3}>Geëxporteerd naar Home Assistant</h2>
          <div className={styles.sub}>Te gebruiken in dashboards en automations</div>
        </div>
      </div>
      {ha.isPending ? (
        <SkeletonGroup>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} height={34} radius={8} />
          ))}
        </SkeletonGroup>
      ) : ha.isError ? (
        <ErrorCallout
          subject="de export naar Home Assistant"
          onRetry={() => {
            void ha.refetch();
          }}
        />
      ) : (
        <>
          <div>
            <Pill tone={ha.data.connected ? 'green' : 'rose'} size="sm">
              {TRANSPORT_LABEL[ha.data.transport]} ·{' '}
              {ha.data.connected ? 'verbonden' : 'niet verbonden'}
            </Pill>
          </div>
          {!ha.data.connected ? (
            <Callout tone="error">
              Niet verbonden met de MQTT-broker. Home Assistant toont de CV-analyse-entiteiten als{' '}
              <em>niet beschikbaar</em>.
            </Callout>
          ) : null}
          {ha.data.entities.map((e) => (
            <div key={e.entity_id} className={styles.entity}>
              <span className={styles.entityKey}>{e.entity_id}</span>
              <span className={styles.entityValue}>{e.display}</span>
            </div>
          ))}
        </>
      )}
    </Card>
  );
}

function RecentCard() {
  const recent = useNotifications({ limit: 5 });
  const items = recent.data?.items ?? [];
  return (
    <Card className={styles.card}>
      <h2 className={styles.h3}>Recent verstuurd</h2>
      {recent.isPending ? (
        <Skeleton height={60} radius={9} />
      ) : recent.isError ? (
        <ErrorCallout
          subject="de verstuurde meldingen"
          onRetry={() => {
            void recent.refetch();
          }}
        />
      ) : items.length === 0 ? (
        <p className={styles.muted}>Nog geen meldingen verstuurd.</p>
      ) : (
        <ul className={styles.list} aria-label="Recent verstuurd">
          {items.map((n) => {
            const view = KIND_VIEW[n.kind];
            const Icon = view.icon;
            return (
              <li key={n.id} className={styles.sent}>
                <IconBadge
                  icon={<Icon size={16} aria-hidden="true" />}
                  tone={view.tone}
                  size="sm"
                />
                <span className={styles.sentText}>
                  <strong>{n.title}</strong> · {n.detail}
                </span>
                <span className={styles.time}>{formatDateTime(n.sent_at)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function NotificationsScreen() {
  const policy = useNotificationPolicy();
  return (
    <div className={styles.screen}>
      <PageHeader
        title="Meldingen"
        subtitle="Eén melding per probleem, niet per cyclus"
        icon={<Bell size={ICON_SIZE} aria-hidden="true" />}
        tone="rose"
      />
      <div className={styles.layout}>
        <div className={styles.col}>
          {policy.isPending ? (
            <div aria-busy="true">
              <Skeleton height={320} radius={20} />
            </div>
          ) : policy.isError ? (
            <ErrorCallout
              subject="het meldingsbeleid"
              onRetry={() => {
                void policy.refetch();
              }}
            />
          ) : (
            <PolicyCards policy={policy.data} />
          )}
        </div>
        <div className={styles.col}>
          <HaExportCard />
          <RecentCard />
        </div>
      </div>
    </div>
  );
}
