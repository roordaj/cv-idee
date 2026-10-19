import { OnboardingProvider } from '../screens/Onboarding/OnboardingProvider';
import { SettingsScreen } from '../screens/Settings/SettingsScreen';
import { OnboardingGate, OnboardingScreen } from '../screens/Onboarding/OnboardingScreen';
import { lazy, Suspense } from 'react';
import { Link, Navigate, Route, Routes } from 'react-router-dom';
import { Card } from '../components/Card.tsx';
import { EmptyState } from '../components/EmptyState.tsx';
import { ICON_SIZE } from '../components/icons.ts';
import Findings from '../screens/Findings/Findings.tsx';
import { ChangesScreen } from '../screens/Changes/index.ts';
import { HistoryScreen } from '../screens/History/index.ts';
import { NotificationsScreen } from '../screens/Notifications/index.ts';
import { Overview } from '../screens/Overview';
import { CyclesScreen } from '../screens/Cycles/index.ts';
import { InstallationScreen } from '../screens/Installation/index.ts';
import { SignalsScreen } from '../screens/Signals/index.ts';
import { QualityScreen } from '../screens/Quality/index.ts';
import { ZoneAnalysisScreen } from '../screens/Zones/ZoneAnalysisScreen.tsx';
import { PlaceholderScreen } from '../screens/PlaceholderScreen.tsx';
import { AppShell } from './AppShell.tsx';
import { SCREENS } from './navigation.ts';
import { useShellData, type ShellData } from './shellData.ts';
import { CircleHelp } from 'lucide-react';

const ComponentGallery = lazy(() => import('./dev/ComponentGallery.tsx'));

export interface AppProps {
  /** Override of the shell data (tests); defaults to `GET /api/status`. */
  shellData?: ShellData;
}

function NotFound() {
  return (
    <Card>
      <EmptyState
        icon={<CircleHelp size={ICON_SIZE} aria-hidden="true" />}
        title="Pagina niet gevonden"
        headingLevel={2}
        action={<Link to="/overzicht">Naar het overzicht</Link>}
      >
        Deze pagina bestaat niet (meer).
      </EmptyState>
    </Card>
  );
}

function screenElement(screen: (typeof SCREENS)[number]) {
  switch (screen.key) {
    case 'analyse-instellingen':
      return <SettingsScreen />;
    case 'wijzigingen':
      return <ChangesScreen />;
    case 'cycli':
      return <CyclesScreen />;
    case 'kwaliteit':
      return <QualityScreen />;
    case 'zones':
      return <ZoneAnalysisScreen />;
    case 'historie':
      return <HistoryScreen />;
    case 'signalen':
      return <SignalsScreen />;
    case 'installatie':
      return <InstallationScreen />;
    case 'meldingen':
      return <NotificationsScreen />;
    default:
      return <PlaceholderScreen screen={screen} />;
  }
}

export function App({ shellData }: AppProps) {
  const fetched = useShellData();
  return (
    <OnboardingProvider>
      {!shellData && <OnboardingGate />}
      <Routes>
        <Route element={<AppShell data={shellData ?? fetched} />}>
          <Route path="welkom" element={<OnboardingScreen />} />
          <Route index element={<Navigate to="overzicht" replace />} />
          <Route path="overzicht" element={<Overview />} />
          <Route path="bevindingen" element={<Findings />} />
          <Route path="bevindingen/:id" element={<Findings />} />
          {SCREENS.filter(
            (screen) => screen.key !== 'overzicht' && screen.key !== 'bevindingen',
          ).map((screen) => (
            <Route key={screen.key} path={screen.path} element={screenElement(screen)} />
          ))}
          <Route
            path="dev/components"
            element={
              <Suspense fallback={null}>
                <ComponentGallery />
              </Suspense>
            }
          />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </OnboardingProvider>
  );
}
