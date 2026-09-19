import { StrictMode } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../app/App';
import { clearJourneyCache } from '../lib/journey';
import { LOCAL_PROFILE_KEY } from '../lib/profiles';
import { roadmapActionLabels } from '../lib/roadmapLabels';
import { COMPARE_STORAGE_KEY } from '../pages/useCompareSelection';
import type { AdmissionJourney, RoadmapItem } from '../types/journey';
import { preparationJourneyFixture } from './journeyFixtures';
import { jsonResponse } from './profileFixtures';
import { recommendationJourneyFixture } from './recommendationFixtures';

function setup(journey: AdmissionJourney, selected?: number[]) {
  localStorage.setItem(LOCAL_PROFILE_KEY, journey.profile_key);
  if (selected) sessionStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(selected));
  const fetcher = vi.fn(async () => jsonResponse(journey));
  vi.stubGlobal('fetch', fetcher);
  return { ...render(<StrictMode><MemoryRouter initialEntries={['/roadmap']}><App /></MemoryRouter></StrictMode>), fetcher };
}

function universityActionsJourney() {
  const journey = recommendationJourneyFixture();
  const items: RoadmapItem[] = [
    { action_code: 'provide_missing_academic_test_if_desired', category: 'academics', priority: 'optional', scope: 'institutions', institution_unitids: [60], reason_codes: ['academic_context_unavailable'] },
    { action_code: 'verify_program_availability', category: 'program', priority: 'medium', scope: 'institutions', institution_unitids: [999], reason_codes: ['program_evidence_partial'] },
    { action_code: 'research_financial_aid', category: 'financial', priority: 'medium', scope: 'institutions', institution_unitids: [20], reason_codes: ['financial_review_needed'] },
    { action_code: 'verify_current_english_policy', category: 'english', priority: 'high', scope: 'institutions', institution_unitids: [40, 20], reason_codes: ['english_policy_unavailable'] },
  ];
  journey.roadmap.roadmap_state = 'university_actions';
  journey.roadmap.items = items;
  journey.summary.roadmap_item_count = items.length;
  return journey;
}

describe('admissions roadmap', () => {
  beforeEach(() => { clearJourneyCache(); localStorage.clear(); sessionStorage.clear(); });
  afterEach(() => { vi.unstubAllGlobals(); clearJourneyCache(); localStorage.clear(); sessionStorage.clear(); });

  it('renders profile preparation actions prominently without university work', async () => {
    const journey = preparationJourneyFixture();
    journey.roadmap.items.push(
      { action_code: 'provide_gpa', category: 'academics', priority: 'medium', scope: 'profile', institution_unitids: [], reason_codes: ['gpa_missing'] },
      { action_code: 'provide_class_rank_if_available', category: 'academics', priority: 'optional', scope: 'profile', institution_unitids: [], reason_codes: ['class_rank_missing'] },
    );
    journey.summary.roadmap_item_count = journey.roadmap.items.length;
    setup(journey);
    expect(await screen.findByRole('heading', { name: 'Define your intended major' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Your admissions roadmap' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Required' })).toBeVisible();
    expect(screen.getByText('Your intended major is missing from your profile.')).toBeVisible();
    expect(screen.queryByText('Related universities')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Update profile' })).toHaveAttribute('href', '/profile');
  });

  it('groups university actions in backend priority order and preserves categories and reasons', async () => {
    setup(universityActionsJourney());
    await screen.findByRole('heading', { name: 'Your admissions roadmap' });
    expect(screen.getAllByRole('heading', { level: 3 }).map(heading => heading.textContent)).toEqual([
      'High priority', 'Medium priority', 'Optional',
    ]);
    const cards = screen.getAllByRole('article');
    expect(cards.map(card => card.dataset.priority)).toEqual(['high', 'medium', 'medium', 'optional']);
    expect(cards.map(card => card.dataset.category)).toEqual(['english', 'program', 'financial', 'academics']);
    expect(screen.getByText('The current English policy is unavailable.')).toBeVisible();
    expect(screen.getAllByText('Test University 40')).toHaveLength(1);
    expect(screen.getAllByText('Test University 20')).toHaveLength(2);
    expect(screen.getByText('University ID 999')).toBeVisible();
    expect(screen.queryByText('Test University 10')).not.toBeInTheDocument();
  });

  it('maps every backend action code to its deterministic presentation label', () => {
    expect(roadmapActionLabels).toEqual({
      define_intended_major: 'Define your intended major',
      provide_academic_interests: 'Add your academic interests',
      provide_graduation_year: 'Add your graduation year',
      provide_gpa: 'Add your GPA',
      provide_class_rank_if_available: 'Add your class rank if available',
      provide_academic_test_if_desired: 'Add an academic test score if desired',
      provide_english_test_score: 'Add an English test score',
      provide_annual_budget: 'Add your annual budget',
      retake_or_improve_english_test: 'Retake or improve your English test',
      submit_compatible_english_score: 'Submit a compatible English score',
      verify_current_english_policy: 'Verify the current English policy',
      verify_program_availability: 'Verify program availability',
      research_financial_aid: 'Research financial aid',
      provide_missing_academic_test_if_desired: 'Provide an academic test score if desired',
    });
  });

  it('renders the factual no-blocking state without invented dates or completion controls', async () => {
    setup(recommendationJourneyFixture());
    expect(await screen.findByText('No blocking actions are currently identified from the available evidence.')).toBeVisible();
    expect(screen.getByText('Unavailable evidence may still require review.')).toBeVisible();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/application deadline|due on|decision date|admission probability|readiness percentage|mark complete|guaranteed ready|\d+% complete/i);
    expect(screen.getByRole('link', { name: 'Edit profile' })).toHaveAttribute('href', '/profile');
    expect(screen.getByRole('link', { name: 'Back to recommendations' })).toHaveAttribute('href', '/recommendations');
  });

  it('keeps Compare optional even with selected universities and keeps navigation working', async () => {
    setup(universityActionsJourney(), [40, 10, 20]);
    await screen.findByRole('heading', { name: 'Your admissions roadmap' });
    const nav = screen.getByRole('navigation', { name: 'Application journey' });
    expect(within(nav).getAllByText('Completed')).toHaveLength(3);
    expect(within(nav).getAllByRole('listitem')[3]).toHaveClass('step-future');
    await userEvent.click(screen.getByRole('link', { name: 'Back to recommendations' }));
    expect(await screen.findByRole('heading', { name: 'Your university recommendations' })).toBeVisible();
  });
});
