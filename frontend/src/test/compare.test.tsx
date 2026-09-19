import { StrictMode } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../app/App';
import { clearJourneyCache } from '../lib/journey';
import { LOCAL_PROFILE_KEY } from '../lib/profiles';
import { COMPARE_STORAGE_KEY } from '../pages/useCompareSelection';
import type { AdmissionJourney } from '../types/journey';
import { recommendationJourneyFixture } from './recommendationFixtures';
import { jsonResponse } from './profileFixtures';

function setup(journey: AdmissionJourney = recommendationJourneyFixture(), selected: unknown = [40, 20]) {
  localStorage.setItem(LOCAL_PROFILE_KEY, journey.profile_key);
  sessionStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(selected));
  const fetcher = vi.fn(async () => jsonResponse(journey));
  vi.stubGlobal('fetch', fetcher);
  const view = render(<StrictMode><MemoryRouter initialEntries={['/compare']}><App /></MemoryRouter></StrictMode>);
  return { ...view, fetcher };
}

describe('university comparison', () => {
  beforeEach(() => { clearJourneyCache(); localStorage.clear(); sessionStorage.clear(); });
  afterEach(() => { vi.unstubAllGlobals(); clearJourneyCache(); localStorage.clear(); sessionStorage.clear(); });

  it('renders two current journey recommendations in an accessible factual table', async () => {
    const journey = recommendationJourneyFixture();
    journey.recommendations!.recommendations.find(item => item.institution.ipeds_unitid === 20)!.institution.name = 'Fresh Journey University Name';
    const { fetcher } = setup(journey);
    const table = await screen.findByRole('table', { name: 'Factual comparison of selected universities' });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(within(table).getAllByRole('columnheader')).toHaveLength(3);
    expect(within(table).getByRole('columnheader', { name: /Test University 40/ })).toBeVisible();
    expect(within(table).getByRole('columnheader', { name: /Fresh Journey University Name/ })).toBeVisible();
    expect(within(table).getAllByRole('rowheader').map(cell => cell.textContent)).toEqual([
      'Recommendation state', 'Location', 'Program evidence', 'English requirement and evidence',
      'Academic context', 'Evidence qualityData coverage, not likelihood of admission.', 'Required and next actions',
    ]);
    expect(screen.getAllByText('Completed')).toHaveLength(3);
    expect(screen.getByRole('link', { current: 'step' })).toHaveTextContent('Compare');
  });

  it('renders three valid selections and discards stale identifiers against the fresh journey', async () => {
    setup(recommendationJourneyFixture(), [60, 999, 20, 30]);
    const table = await screen.findByRole('table');
    expect(within(table).getAllByRole('columnheader')).toHaveLength(4);
    for (const id of [60, 20, 30]) expect(within(table).getByRole('columnheader', { name: new RegExp(`Test University ${id}`) })).toBeVisible();
    expect(screen.queryByText(/999/)).not.toBeInTheDocument();
    await waitFor(() => expect(JSON.parse(sessionStorage.getItem(COMPARE_STORAGE_KEY)!)).toEqual([60, 20, 30]));
  });

  it('shows the selection-required state for fewer than two valid selections', async () => {
    setup(recommendationJourneyFixture(), [999, 40]);
    expect(await screen.findByRole('heading', { name: 'Select at least two universities to compare.' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Back to recommendations' })).toHaveAttribute('href', '/recommendations');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('removes a university, persists the identifier change, and returns to the required state', async () => {
    setup();
    await screen.findByRole('table');
    await userEvent.click(screen.getByRole('button', { name: 'Remove Test University 40 from comparison' }));
    expect(await screen.findByRole('heading', { name: 'Select at least two universities to compare.' })).toBeVisible();
    await waitFor(() => expect(JSON.parse(sessionStorage.getItem(COMPARE_STORAGE_KEY)!)).toEqual([20]));
  });

  it('preserves English scales and states, conservative program wording, academic context, and backend actions', async () => {
    const journey = recommendationJourneyFixture();
    const first = journey.recommendations!.recommendations.find(item => item.institution.ipeds_unitid === 40)!;
    first.assessment.english.policy_state = 'verified_minimum';
    first.assessment.english.tests[0].state = 'meets_verified_minimum';
    first.assessment.english.tests[0].requirements = [{ scale: 'toefl_ibt_0_120', minimum_score: 80, policy_cycle: '2026', valid_for_tests_before: null, valid_for_tests_on_or_after: null }];
    const second = journey.recommendations!.recommendations.find(item => item.institution.ipeds_unitid === 20)!;
    second.assessment.english.policy_state = 'conflicting';
    second.assessment.english.tests[0].state = 'requirement_conflicting';
    setup(journey);
    const table = await screen.findByRole('table');
    expect(table).toHaveTextContent('Not observed in current data');
    expect(table).not.toHaveTextContent('Does not offer');
    expect(table).toHaveTextContent('Verified minimum published');
    expect(table).toHaveTextContent('Meets verified minimum');
    expect(table).toHaveTextContent('Conflicting policy evidence');
    expect(table).toHaveTextContent('TOEFL iBT (0–120): submitted 105');
    expect(table).toHaveTextContent('TOEFL iBT (1–6): submitted 5');
    expect(table).toHaveTextContent('SAT: Context not comparable');
    expect(table).toHaveTextContent('ACT: Applicant score missing');
    expect(table).toHaveTextContent('Verify the current English policy');
    expect(table).toHaveTextContent('Research financial aid');
    expect(table).not.toHaveTextContent('Retake or improve your English test');
    expect(document.body.textContent).not.toMatch(/best university|winner|admission probability|acceptance chance|\breach\b|\btarget\b|\bsafety\b|guaranteed|#1 choice|ranking/i);
  });

  it('offers change-selection and roadmap navigation only with a valid comparison', async () => {
    setup();
    await screen.findByRole('table');
    expect(screen.getByRole('link', { name: 'Change universities' })).toHaveAttribute('href', '/recommendations');
    const continueLink = screen.getByRole('link', { name: /Continue to roadmap/ });
    expect(continueLink).toHaveAttribute('href', '/roadmap');
    await userEvent.click(continueLink);
    expect(screen.getByRole('heading', { name: 'Your admissions roadmap' })).toBeVisible();
  });
});
