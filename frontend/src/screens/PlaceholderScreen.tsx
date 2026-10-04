import { Construction } from 'lucide-react';
import type { ScreenDef } from '../app/navigation.ts';
import { Card } from '../components/Card.tsx';
import { EmptyState } from '../components/EmptyState.tsx';
import { ICON_SIZE } from '../components/icons.ts';
import { PageHeader } from '../components/PageHeader.tsx';
import styles from './PlaceholderScreen.module.css';

export interface PlaceholderScreenProps {
  screen: ScreenDef;
}

/** Temporary screen until the real one is built; keeps the shell navigable. */
export function PlaceholderScreen({ screen }: PlaceholderScreenProps) {
  const Icon = screen.icon;
  const isOverview = screen.key === 'overzicht';
  return (
    <div className={styles.screen}>
      <PageHeader
        title={screen.title}
        {...(screen.subtitle ? { subtitle: screen.subtitle } : {})}
        {...(isOverview
          ? {}
          : { icon: <Icon size={ICON_SIZE} aria-hidden="true" />, tone: screen.tone })}
      />
      <Card>
        <EmptyState icon={<Construction size={24} aria-hidden="true" />} title="Nog in aanbouw">
          Dit scherm volgt in een volgende stap. Alleen-lezen analyse van je cv-installatie.
        </EmptyState>
      </Card>
    </div>
  );
}
