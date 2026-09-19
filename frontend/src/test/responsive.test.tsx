import { StrictMode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../app/App';
import { clearJourneyCache } from '../lib/journey';
import { LOCAL_PROFILE_KEY } from '../lib/profiles';
import { COMPARE_STORAGE_KEY } from '../lib/compareSelection';
import { recommendationJourneyFixture } from './recommendationFixtures';
import { jsonResponse, mockProfileServer } from './profileFixtures';

function setCompactShell(compact: boolean) {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: query === '(max-width: 1023px)' && compact,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(() => true),
  })));
}

function renderApp(path: string) {
  return render(<StrictMode><MemoryRouter initialEntries={[path]}><App /></MemoryRouter></StrictMode>);
}

function mockJourney() {
  const journey = recommendationJourneyFixture();
  localStorage.setItem(LOCAL_PROFILE_KEY, journey.profile_key);
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(journey)));
  return journey;
}

describe('responsive Talap journey', () => {
  beforeEach(() => {
    clearJourneyCache();
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    clearJourneyCache();
    localStorage.clear();
    sessionStorage.clear();
  });

  it('renders the compact shell, usable five-step navigation, profile controls, and collapsible guidance', async () => {
    setCompactShell(true);
    mockProfileServer();
    renderApp('/profile');

    expect(document.querySelector('.desktop-layout')).toHaveAttribute('data-layout', 'compact');
    expect(screen.getByTestId('mobile-step-summary')).toHaveTextContent('Step 1 of 5Profile');
    expect(screen.getAllByRole('link', { name: /Profile|Diagnostics|Recommendations|Compare|Roadmap/ })).toHaveLength(5);
    expect(await screen.findByLabelText('Citizenship country code *')).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Save and continue' })).toBeEnabled();

    const guidance = screen.getByText('Journey guidance').closest('details');
    expect(guidance).not.toHaveAttribute('open');
    await userEvent.click(screen.getByText('Journey guidance'));
    expect(guidance).toHaveAttribute('open');
    expect(screen.getByRole('heading', { name: 'Your Talap profile' })).toBeInTheDocument();
  });

  it('retains the accepted three-area desktop shell above the compact breakpoint', async () => {
    setCompactShell(false);
    mockProfileServer();
    renderApp('/profile');

    expect(document.querySelector('.desktop-layout')).toHaveAttribute('data-layout', 'desktop');
    expect(screen.getByRole('complementary', { name: 'About Talap' })).toBeInTheDocument();
    expect(screen.getByRole('main', { name: 'Product workspace' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Journey information' })).toBeInTheDocument();
    expect(screen.queryByText('Journey guidance')).not.toBeInTheDocument();
    expect(await screen.findByLabelText('Display name')).toBeEnabled();
  });

  it('keeps recommendation selection touch flow and its ready CTA state on compact screens', async () => {
    setCompactShell(true);
    mockJourney();
    renderApp('/recommendations');

    await screen.findByRole('article', { name: 'Test University 40' });
    await userEvent.click(screen.getByRole('checkbox', { name: 'Compare Test University 40' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'Compare Test University 20' }));
    const cta = screen.getByRole('button', { name: 'Compare selected' });
    expect(cta).toBeEnabled();
    expect(cta.closest('footer')).toHaveClass('comparison-footer--ready');
  });

  it('keeps every selected university in the accessible mobile comparison region', async () => {
    setCompactShell(true);
    const journey = mockJourney();
    sessionStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify([40, 20, 60]));
    renderApp('/compare');

    const region = await screen.findByRole('region', { name: 'Scrollable university comparison' });
    expect(region).toHaveAttribute('tabindex', '0');
    for (const id of [40, 20, 60]) expect(region).toHaveTextContent(`Test University ${id}`);
    expect(region.querySelector('table')).toHaveAccessibleName('Factual comparison of selected universities');
    expect(journey.recommendations?.recommendations).toHaveLength(5);
  });

  it('retains roadmap actions and makes contextual guidance expandable on compact screens', async () => {
    setCompactShell(true);
    mockJourney();
    renderApp('/roadmap');

    await screen.findByText('No blocking actions are currently identified from the available evidence.');
    expect(screen.getByRole('heading', { name: 'Your admissions roadmap' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Edit profile' })).toHaveAttribute('href', '/profile');
    expect(screen.getByRole('link', { name: 'Back to recommendations' })).toHaveAttribute('href', '/recommendations');
    const guidance = screen.getByText('Journey guidance').closest('details');
    await userEvent.click(screen.getByText('Journey guidance'));
    await waitFor(() => expect(guidance).toHaveAttribute('open'));
    expect(screen.getByRole('heading', { name: 'How to use your roadmap' })).toBeInTheDocument();
  });
});
