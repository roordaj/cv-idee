import { act, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import { ExplainBanner } from '../components/ExplainBanner.tsx';
import { Term } from '../components/Term.tsx';
import { TermsPanel } from '../components/TermsPanel.tsx';
import { GLOSS, TERMS } from './glossary.ts';
import { resetExplainState, useExplain } from './useExplain.ts';

beforeEach(() => {
  window.localStorage.clear();
  resetExplainState();
});

describe('useExplain', () => {
  it('defaults to on and persists the toggle', () => {
    const { result } = renderHook(() => useExplain());
    expect(result.current.explain).toBe(true);
    act(() => {
      result.current.setExplain(false);
    });
    expect(result.current.explain).toBe(false);
    expect(window.localStorage.getItem('cv-idee.explain')).toBe('0');
    resetExplainState();
    expect(renderHook(() => useExplain()).result.current.explain).toBe(false);
  });
});

describe('TermsPanel', () => {
  it('lists all terms of a finding with their definitions', () => {
    render(<TermsPanel findingId="B-014" />);
    expect(screen.getByText('Begrippen in deze bevinding')).toBeInTheDocument();
    for (const t of TERMS['B-014'] ?? []) {
      expect(screen.getByText(GLOSS[t])).toBeInTheDocument();
    }
  });

  it('renders nothing when explanations are off', () => {
    window.localStorage.setItem('cv-idee.explain', '0');
    resetExplainState();
    render(
      <>
        <TermsPanel findingId="B-014" />
        <ExplainBanner />
      </>,
    );
    expect(screen.queryByText('Begrippen in deze bevinding')).toBeNull();
    expect(screen.queryByText(/één brandperiode/)).toBeNull();
  });
});

describe('Term', () => {
  it('shows the definition on click', async () => {
    render(<Term term="Naloop" />);
    await userEvent.click(screen.getByRole('button', { name: 'Naloop' }));
    expect(screen.getByRole('tooltip')).toHaveTextContent(GLOSS.Naloop);
  });
});
