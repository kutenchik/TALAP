import { StrictMode } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../app/App';
import { clearJourneyCache } from '../lib/journey';
import { LOCAL_PROFILE_KEY } from '../lib/profiles';
import { COMPARE_STORAGE_KEY } from '../pages/useCompareSelection';
import { recommendationLabels } from '../lib/recommendationLabels';
import { jsonResponse } from './profileFixtures';
import { preparationJourneyFixture, readyJourneyFixture } from './journeyFixtures';
import { recommendationJourneyFixture } from './recommendationFixtures';
import type { AdmissionJourney } from '../types/journey';

function setup(journey: AdmissionJourney = recommendationJourneyFixture()) {
  localStorage.setItem(LOCAL_PROFILE_KEY, journey.profile_key);
  const fetcher = vi.fn(async () => jsonResponse(journey));
  vi.stubGlobal('fetch', fetcher);
  const view = render(<StrictMode><MemoryRouter initialEntries={['/recommendations']}><App /></MemoryRouter></StrictMode>);
  return { ...view, fetcher };
}
describe('university recommendations', () => {
  beforeEach(() => { clearJourneyCache(); localStorage.clear(); sessionStorage.clear(); });
  afterEach(() => { vi.unstubAllGlobals(); clearJourneyCache(); localStorage.clear(); sessionStorage.clear(); });

  it('loads once even in StrictMode, renders all states and preserves backend order', async () => {
    const { fetcher } = setup();
    await screen.findByRole('heading', { name: 'Test University 40' });
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole('article').map(card => within(card).getByRole('heading', { level: 3 }).textContent)).toEqual([40, 20, 60, 10, 30].map(id => `Test University ${id}`));
    for (const label of Object.values(recommendationLabels)) expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    const excluded = screen.getByRole('article', { name: 'Test University 10' });
    expect(within(excluded).getByRole('checkbox')).toBeDisabled();
    expect(within(excluded).getByRole('checkbox')).not.toBeChecked();
    expect(screen.getAllByText('Completed')).toHaveLength(2);
    expect(screen.getByRole('link', { current: 'step' })).toHaveTextContent('Recommendations');
  });
  it('renders conservative evidence, distinct scales and only backend actions and reasons', async () => {
    setup();
    const card = await screen.findByRole('article', { name: 'Test University 40' });
    expect(card).toHaveTextContent('Not observed in current data');
    expect(card).toHaveTextContent('Requirement unavailable');
    expect(card).not.toHaveTextContent('Meets verified minimum');
    expect(card).toHaveTextContent('TOEFL iBT (0–120): submitted 105');
    expect(card).toHaveTextContent('TOEFL iBT (1–6): submitted 5');
    expect(card).toHaveTextContent('SAT: Context not comparable');
    expect(card).toHaveTextContent('Research financial aid');
    expect(card).toHaveTextContent('Partial program evidence');
    expect(card).not.toHaveTextContent('Retake or improve your English test');
    expect(document.body.textContent).not.toMatch(/admission probability|acceptance chance|likely admitted|\breach\b|\btarget\b|\bsafety\b|guaranteed|ranking|tuition|scholarship amount|deadline|not offered/i);
  });
  it('requires two, limits selection to three, and restores identifiers on remount', async () => {
    const view = setup();
    await screen.findByRole('article', { name: 'Test University 40' });
    const cta = screen.getByRole('button', { name: 'Compare selected' });
    expect(cta).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Compare Test University 40' }));
    expect(cta).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Compare Test University 20' }));
    expect(cta).toBeEnabled();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Compare Test University 60' }));
    expect(screen.getByRole('checkbox', { name: 'Compare Test University 30' })).toBeDisabled();
    expect(JSON.parse(sessionStorage.getItem(COMPARE_STORAGE_KEY)!)).toEqual([40, 20, 60]);
    await userEvent.click(cta);
    expect(screen.getByRole('heading', { name: 'Compare' })).toBeVisible();
    view.unmount();
    setup();
    expect(await screen.findByRole('checkbox', { name: 'Compare Test University 40' })).toBeChecked();
    await userEvent.click(screen.getByRole('checkbox', { name: 'Compare Test University 20' }));
    expect(screen.getByRole('checkbox', { name: 'Compare Test University 30' })).toBeEnabled();
  });
  it('prunes stale, excluded, duplicate and invalid session selections', async () => {
    sessionStorage.setItem(COMPARE_STORAGE_KEY, '[10,999,40,40,"20"]');
    setup();
    await screen.findByRole('article', { name: 'Test University 40' });
    expect(JSON.parse(sessionStorage.getItem(COMPARE_STORAGE_KEY)!)).toEqual([40]);
  });
  it('filters without reordering or losing hidden selections', async () => {
    setup();
    await screen.findByRole('article', { name: 'Test University 40' });
    await userEvent.click(screen.getByRole('checkbox', { name: 'Compare Test University 20' }));
    await userEvent.selectOptions(screen.getByLabelText('Show'), 'recommended_for_review');
    expect(screen.getAllByRole('article').map(card => within(card).getByRole('heading', { level: 3 }).textContent)).toEqual(['Test University 40', 'Test University 30']);
    expect(screen.getByRole('status')).toHaveTextContent('1 selected');
  });
  it('blocks recommendations during profile preparation', async () => {
    setup(preparationJourneyFixture());
    expect(await screen.findByRole('link', { name: 'Complete profile' })).toHaveAttribute('href', '/profile');
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Compare selected' })).not.toBeInTheDocument();
  });
  it('handles an empty recommendation set', async () => {
    setup(readyJourneyFixture());
    expect(await screen.findByText('No university recommendations available')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Compare selected' })).toBeDisabled();
  });
  it('shows all-excluded and all-insufficient notices without fabricating results', async () => {
    const journey = recommendationJourneyFixture();
    journey.recommendations!.recommendations = journey.recommendations!.recommendations.filter(item => item.recommendation_state === 'excluded_by_applicant');
    Object.assign(journey.summary, { candidate_count: 1, recommended_for_review_count: 0, consider_with_actions_count: 0, insufficient_evidence_count: 0 });
    setup(journey);
    expect(await screen.findByText(/All returned universities are excluded/)).toBeVisible();
    expect(screen.getAllByRole('article')).toHaveLength(1);
  });
  it('shows when every candidate needs more evidence', async () => {
    const journey = recommendationJourneyFixture();
    journey.recommendations!.recommendations = journey.recommendations!.recommendations.filter(item => item.recommendation_state === 'insufficient_evidence');
    Object.assign(journey.summary, { candidate_count: 1, recommended_for_review_count: 0, consider_with_actions_count: 0, excluded_by_applicant_count: 0 });
    setup(journey);
    expect(await screen.findByText(/More candidate evidence is needed/)).toBeVisible();
  });
});
