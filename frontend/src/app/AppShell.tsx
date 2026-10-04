import { Calendar, Flame, Plug, ShieldCheck } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { ICON_SIZE } from '../components/icons.ts';
import { HeaderPill, StatusPill, StubDataPill } from '../components/StatusPill.tsx';
import { cx } from '../components/tone.ts';
import { capitalize, formatDateLong } from '../lib/format.ts';
import styles from './AppShell.module.css';
import { SCREENS, type ScreenDef } from './navigation.ts';
import type { ShellData } from './shellData.ts';
import { RAIL_QUERY, useMediaQuery } from './useMediaQuery.ts';

export interface AppShellProps {
  data: ShellData;
  /** Date shown in the header; defaults to now. */
  today?: Date;
}

interface NavCount {
  text: string;
  /** Screen-reader text appended to the link name. */
  srText: string;
  emphasis: 'alert' | 'neutral';
}

function navCount(screen: ScreenDef, data: ShellData): NavCount | null {
  if (screen.key === 'bevindingen' && data.openFindings !== null && data.openFindings > 0) {
    return {
      text: String(data.openFindings),
      srText: `${String(data.openFindings)} open`,
      emphasis: 'alert',
    };
  }
  if (screen.key === 'signalen' && data.signals) {
    const { linked, total } = data.signals;
    return {
      text: `${String(linked)}/${String(total)}`,
      srText: `${String(linked)} van ${String(total)} gekoppeld`,
      emphasis: 'neutral',
    };
  }
  return null;
}

function NavItem({ screen, data, rail }: { screen: ScreenDef; data: ShellData; rail: boolean }) {
  const Icon = screen.icon;
  const count = navCount(screen, data);
  // Design v3: in rail mode only the alert badge (Bevindingen) stays visible.
  const showBadge = count !== null && (!rail || count.emphasis === 'alert');
  return (
    <NavLink
      to={screen.path}
      title={screen.label}
      className={({ isActive }) => cx(styles.navItem, isActive && styles.active)}
    >
      <Icon size={ICON_SIZE} aria-hidden="true" className={styles.navIcon} />
      <span className={rail ? 'visually-hidden' : styles.navLabel}>{screen.label}</span>
      {count ? (
        <>
          {showBadge ? (
            <span
              aria-hidden="true"
              className={cx(styles.count, styles[count.emphasis], rail && styles.countRail)}
            >
              {count.text}
            </span>
          ) : null}
          <span className="visually-hidden">, {count.srText}</span>
        </>
      ) : null}
    </NavLink>
  );
}

export function AppShell({ data, today = new Date() }: AppShellProps) {
  const rail = useMediaQuery(RAIL_QUERY);
  const analyse = SCREENS.filter((s) => s.section === 'analyse');
  const settings = SCREENS.filter((s) => s.section === 'instellingen');

  return (
    <div className={cx(styles.shell, rail && styles.rail)} data-layout={rail ? 'rail' : 'full'}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span className={styles.brandBadge} aria-hidden="true">
            <Flame size={ICON_SIZE} />
          </span>
          {rail ? (
            <span className="visually-hidden">CV-analyse · Thuis · Calenta Ace</span>
          ) : (
            <span className={styles.brandText}>
              <span className={styles.brandName}>CV-analyse</span>
              <span className={styles.brandSub}>Thuis · Calenta Ace</span>
            </span>
          )}
        </div>
        <nav aria-label="Hoofdnavigatie" className={styles.nav}>
          <div className={rail ? 'visually-hidden' : styles.sectionLabel} id="nav-analyse">
            Analyse
          </div>
          <ul aria-labelledby="nav-analyse" className={styles.navList}>
            {analyse.map((screen) => (
              <li key={screen.key}>
                <NavItem screen={screen} data={data} rail={rail} />
              </li>
            ))}
          </ul>
          {rail ? <div className={styles.railDivider} aria-hidden="true" /> : null}
          <div
            className={rail ? 'visually-hidden' : cx(styles.sectionLabel, styles.sectionLabelGap)}
            id="nav-instellingen"
          >
            Instellingen
          </div>
          <ul aria-labelledby="nav-instellingen" className={styles.navList}>
            {settings.map((screen) => (
              <li key={screen.key}>
                <NavItem screen={screen} data={data} rail={rail} />
              </li>
            ))}
          </ul>
        </nav>
        {rail ? null : (
          <div className={styles.readOnly}>
            <ShieldCheck size={ICON_SIZE} aria-hidden="true" className={styles.readOnlyIcon} />
            <span>
              Alleen-lezen: deze app stuurt niets aan. Wijzigingen aan ketel of thermostaat voer je
              zelf uit.
            </span>
          </div>
        )}
      </aside>

      <div className={styles.main}>
        <header className={styles.header}>
          <StatusPill status={data.status} />
          {data.stubData ? <StubDataPill /> : null}
          <HeaderPill muted icon={<Plug size={ICON_SIZE} aria-hidden="true" />}>
            {data.source}
          </HeaderPill>
          <div className={styles.date}>
            <Calendar size={ICON_SIZE} aria-hidden="true" />
            <time dateTime={today.toISOString()}>{capitalize(formatDateLong(today))}</time>
          </div>
        </header>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
