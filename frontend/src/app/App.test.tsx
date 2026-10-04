import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { App } from './App.tsx';
import { AppProviders } from './AppProviders.tsx';

describe('App', () => {
  it('renders the placeholder page', () => {
    render(
      <AppProviders>
        <MemoryRouter>
          <App />
        </MemoryRouter>
      </AppProviders>,
    );
    expect(screen.getByRole('heading', { name: 'CV-analyse' })).toBeInTheDocument();
  });
});
