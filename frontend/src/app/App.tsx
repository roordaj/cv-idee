import { Route, Routes } from 'react-router-dom';
import { PlaceholderScreen } from '../screens/PlaceholderScreen.tsx';

export function App() {
  return (
    <Routes>
      <Route path="*" element={<PlaceholderScreen />} />
    </Routes>
  );
}
