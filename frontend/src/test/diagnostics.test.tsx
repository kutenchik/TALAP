import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../app/App';
import { clearJourneyCache } from '../lib/journey';
import { LOCAL_PROFILE_KEY } from '../lib/profiles';
import type { AdmissionJourney } from '../types/journey';
import { jsonResponse, missingProfile } from './profileFixtures';
import { preparationJourneyFixture, readyJourneyFixture } from './journeyFixtures';

const journeyUrl = '/api/v1/profiles/talap-local-journey-test/journey/?seed_order_start=1&seed_order_end=100';

function renderDiagnostics() {
  return render(<MemoryRouter initialEntries={['/diagnostics']}><App /></MemoryRouter>);
}
function saveIdentity() {
  localStorage.setItem(LOCAL_PROFILE_KEY, 'talap-local-journey-test');
}
function mockJourney(response: AdmissionJourney | unknown, status = 200) {
  return vi.fn(async (url: string) => url === journeyUrl ? jsonResponse(response, status) : missingProfile());
}

describe('Diagnostics journey experience', () => {
  beforeEach(() => {
    localStorage.clear();
    clearJourneyCache();
    vi.stubEnv('VITE_API_BASE_URL', '');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    localStorage.clear();
    clearJourneyCache();
  });

  it('loads the saved journey once with the default scope', async () => {
    saveIdentity();
    const fetcher = mockJourney(readyJourneyFixture());
    vi.stubGlobal('fetch', fetcher);
    renderDiagnostics();
    expect(await screen.findByRole('heading', { name: 'Your submitted details' })).toBeVisible();
    expect(fetcher.mock.calls.filter(([url]) => url === journeyUrl)).toHaveLength(1);
  });

  it('redirects to Profile without creating an identity before Diagnostics', async () => {
    const fetcher = mockJourney(readyJourneyFixture());
    vi.stubGlobal('fetch', fetcher);
    renderDiagnostics();
    expect(await screen.findByRole('heading', { name: 'Let’s get to know you' })).toBeVisible();
    expect(fetcher.mock.calls.some(([url]) => url === journeyUrl)).toBe(false);
  });

  it('redirects to Profile for profile_not_found', async () => {
    saveIdentity();
    vi.stubGlobal('fetch', vi.fn(async (url: string) => url === journeyUrl ? missingProfile() : missingProfile()));
    renderDiagnostics();
    expect(await screen.findByRole('heading', { name: 'Let’s get to know you' })).toBeVisible();
  });

  it('shows a safe retry state and requests the journey again', async () => {
    saveIdentity();
    const journey = readyJourneyFixture();
    let attempts = 0;
    const fetcher = vi.fn(async (url: string) => {
      if (url !== journeyUrl) return missingProfile();
      attempts += 1;
      return attempts === 1 ? jsonResponse({ error: { code: 'server_error', message: 'Private detail' } }, 500) : jsonResponse(journey);
    });
    vi.stubGlobal('fetch', fetcher);
    renderDiagnostics();
    expect(await screen.findByRole('alert')).toHaveTextContent('could not load your diagnostic');
    expect(screen.queryByText('Private detail')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: 'Your submitted details' })).toBeVisible();
    expect(attempts).toBe(2);
  });

  it('shows a safe error for an invalid journey response', async () => {
    saveIdentity();
    vi.stubGlobal('fetch', mockJourney({ journey_state: 'recommendations_ready' }));
    renderDiagnostics();
    expect(await screen.findByRole('alert')).toHaveTextContent('unexpected journey response');
  });

  it('renders profile preparation and keeps the primary action on Profile', async () => {
    saveIdentity();
    vi.stubGlobal('fetch', mockJourney(preparationJourneyFixture()));
    renderDiagnostics();
    expect(await screen.findByText('Required profile information is still missing')).toBeVisible();
    expect(screen.getByText('Add your intended major')).toBeVisible();
    expect(screen.queryByRole('link', { name: /Continue to recommendations/i })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Complete your profile/i })).toHaveAttribute('href', '/profile');
  });

  it('renders factual diagnostics and preserves distinct test scales', async () => {
    saveIdentity();
    vi.stubGlobal('fetch', mockJourney(readyJourneyFixture()));
    renderDiagnostics();
    expect(await screen.findByText('4.7 / 5')).toBeVisible();
    for (const text of ['SAT 1450', 'ACT 32', 'TOEFL iBT (0–120) 105', 'TOEFL iBT (1–6) 5', 'IELTS 6.5', '11.0701', '14.0901', '$25,000']) {
      expect(screen.getByText(text)).toBeVisible();
    }
    expect(screen.getByText('Financial aid needed').nextElementSibling).toHaveTextContent('Yes');
    const location = screen.getByRole('heading', { name: 'Location preferences and constraints' }).closest('section')!;
    for (const state of ['CA', 'NY', 'TX', 'FL']) expect(within(location).getAllByText(state).length).toBeGreaterThan(0);
    expect(within(location).getByText('Source: Your profile')).toBeVisible();
    expect(screen.getByRole('link', { name: /Continue to recommendations/i })).toHaveAttribute('href', '/recommendations');
  });

  it('renders explore interests instead of major codes', async () => {
    saveIdentity();
    const journey = readyJourneyFixture();
    journey.diagnostic.goal = { mode: 'explore', intended_cip_codes: [], interests: ['Robotics', 'Public policy'], goal_supplied: true };
    vi.stubGlobal('fetch', mockJourney(journey));
    renderDiagnostics();
    expect(await screen.findByText('Exploring majors')).toBeVisible();
    expect(screen.getByText('Robotics')).toBeVisible();
    expect(screen.getByText('Public policy')).toBeVisible();
  });

  it('groups missing information by backend importance while preserving order within a group', async () => {
    saveIdentity();
    vi.stubGlobal('fetch', mockJourney(preparationJourneyFixture()));
    renderDiagnostics();
    const section = (await screen.findByRole('heading', { name: 'Missing information' })).closest('section')!;
    for (const label of ['Required next step', 'Useful', 'Optional']) expect(within(section).getByRole('heading', { name: label })).toBeVisible();
    const useful = within(section).getByRole('heading', { name: 'Useful' }).closest('.missing-group') as HTMLElement;
    const usefulItems = within(useful).getAllByRole('listitem');
    expect(usefulItems[0]).toHaveTextContent('Add your GPA');
    expect(usefulItems[1]).toHaveTextContent('Add an English test score');
  });

  it('marks Profile completed, Diagnostics current, and later steps future', async () => {
    saveIdentity();
    vi.stubGlobal('fetch', mockJourney(readyJourneyFixture()));
    renderDiagnostics();
    await screen.findByRole('heading', { name: 'Your submitted details' });
    const nav = screen.getByRole('navigation', { name: 'Application journey' });
    expect(within(nav).getByRole('link', { name: /Profile/ }).closest('li')).toHaveClass('step-completed');
    expect(within(nav).getByRole('link', { current: 'step' })).toHaveTextContent('Diagnostics');
    for (const name of ['Recommendations', 'Compare', 'Roadmap']) expect(within(nav).getByRole('link', { name: new RegExp(name) }).closest('li')).toHaveClass('step-future');
  });

  it('does not render unsupported diagnostic claims', async () => {
    saveIdentity();
    vi.stubGlobal('fetch', mockJourney(readyJourneyFixture()));
    renderDiagnostics();
    await screen.findByRole('heading', { name: 'Your submitted details' });
    const content = document.body.textContent ?? '';
    for (const phrase of ['admission chance', 'acceptance probability', 'reach', 'target', 'safety', 'readiness %', 'strong GPA', 'likely admitted']) {
      expect(content).not.toMatch(new RegExp(phrase, 'i'));
    }
  });
});
