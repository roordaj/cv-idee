import { lazy, Suspense } from 'react';
import { Link, Navigate, Route, Routes } from 'react-router-dom';
import { Card } from '../components/Card.tsx';
import { EmptyState } from '../components/EmptyState.tsx';
import { ICON_SIZE } from '../components/icons.ts';
import { ChangesScreen } from '../screens/Changes/index.ts';
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

export function App({ shellData }: AppProps) {
  const fetched = useShellData();
  return (
    <Routes>
      <Route element={<AppShell data={shellData ?? fetched} />}>
        <Route index element={<Navigate to="overzicht" replace />} />
        {SCREENS.map((screen) => (
          <Route
            key={screen.key}
            path={screen.path}
            element={
              screen.key === 'wijzigingen' ? (
                <ChangesScreen />
              ) : (
                <PlaceholderScreen screen={screen} />
              )
            }
          />
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
  );
}
