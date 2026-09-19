import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../app/App';
import { clearJourneyCache, getJourneySnapshot, loadJourney } from '../lib/journey';
import { COMPARE_PROFILE_KEY, COMPARE_STORAGE_KEY, clearCompareSelection } from '../lib/compareSelection';
import { LOCAL_PROFILE_KEY, saveProfile } from '../lib/profiles';
import { useCompareSelection } from '../pages/useCompareSelection';
import { preparationJourneyFixture } from './journeyFixtures';
import { recommendationJourneyFixture } from './recommendationFixtures';
import { jsonResponse, missingProfile, profileFixture } from './profileFixtures';
import type { ApplicantProfileInput } from '../types/profile';
import type { UniversityRecommendation } from '../types/journey';

const titles = {
  profile: 'Let’s get to know you', diagnostics: 'Your applicant diagnostic',
  recommendations: 'Your university recommendations', compare: 'Compare universities', roadmap: 'Your admissions roadmap',
};
type RouteName = keyof typeof titles;
const routes = Object.keys(titles) as RouteName[];
const forbidden = /admission probability|acceptance chance|likely admitted|\breach\b|\btarget\b|\bsafety\b|guaranteed|ranking|tuition|scholarship amount|application deadline|decision date|readiness percentage|mark complete|\d+%\s*(ready|complete)/i;
function mount(route: RouteName) {
  return render(<StrictMode><MemoryRouter initialEntries={[`/${route}`]}><App /></MemoryRouter></StrictMode>);
}
function server(initial = true) {
  let profile: ApplicantProfileInput | null = initial ? { ...profileFixture(), profile_key: recommendationJourneyFixture().profile_key } : null;
  if (profile) localStorage.setItem(LOCAL_PROFILE_KEY, profile.profile_key);
  const fetcher = vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith('/csrf/')) return jsonResponse({ csrfToken: 'fixture-token' });
    if (url.endsWith('/profiles/validate/')) return jsonResponse(JSON.parse(String(options?.body)));
    if (url.endsWith('/profiles/') && options?.method === 'POST') {
      profile = JSON.parse(String(options.body));
      return jsonResponse(profile);
    }
    if (!profile) return missingProfile();
    if (url.includes('/journey/')) {
      const journey = profile.study_intent.intended_cip_codes.length ? recommendationJourneyFixture() : preparationJourneyFixture();
      journey.profile_key = profile.profile_key;
      journey.diagnostic.profile_key = profile.profile_key;
      journey.roadmap.profile_key = profile.profile_key;
      if (journey.recommendations) journey.recommendations.profile_key = profile.profile_key;
      journey.diagnostic.financial.annual_budget_usd = profile.financial.annual_budget_usd;
      return jsonResponse(journey);
    }
    return jsonResponse(profile);
  });
  vi.stubGlobal('fetch', fetcher);
  return { fetcher, journeyCalls: () => fetcher.mock.calls.filter(([url]) => url.includes('/journey/')).length };
}
async function loaded(route: RouteName) {
  if (route === 'profile') await screen.findByLabelText('Display name');
  else if (route === 'diagnostics') await screen.findByRole('heading', { name: 'Your submitted details' });
  else if (route === 'recommendations') await screen.findByRole('checkbox', { name: 'Compare Test University 40' });
  else if (route === 'compare') await screen.findByRole('table');
  else await screen.findByText('No blocking actions are currently identified from the available evidence.');
}
const nav = () => within(screen.getByRole('navigation', { name: 'Application journey' }));

describe('complete desktop journey integration', () => {
  beforeEach(() => { clearJourneyCache(); clearCompareSelection(); localStorage.clear(); sessionStorage.clear(); });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('creates a profile, walks all five screens with one journey GET, then updates and refetches before showing results', async () => {
    const api = server(false);
    const user = userEvent.setup();
    mount('profile');
    await loaded('profile');
    expect(nav().getByRole('link', { name: /Diagnostics/ })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.change(screen.getByLabelText('Citizenship country code *'), { target: { value: 'KZ' } });
    await user.click(screen.getByRole('button', { name: 'Add cip code' }));
    fireEvent.change(screen.getByLabelText('CIP code 1'), { target: { value: '11.0701' } });
    await user.click(screen.getByRole('button', { name: 'Save and continue' }));
    await loaded('diagnostics');
    await user.click(screen.getByRole('link', { name: /Continue to recommendations/ }));
    await loaded('recommendations');
    for (const id of [40, 20]) await user.click(screen.getByRole('checkbox', { name: `Compare Test University ${id}` }));
    await user.click(screen.getByRole('button', { name: 'Compare selected' }));
    await loaded('compare');
    await user.click(screen.getByRole('link', { name: /Continue to roadmap/ }));
    await loaded('roadmap');
    expect(api.journeyCalls()).toBe(1);
    expect(nav().getByRole('link', { name: /Compare/ }).closest('li')).toHaveClass('step-future');
    await user.click(screen.getByRole('link', { name: 'Edit profile' }));
    await loaded('profile');
    fireEvent.change(screen.getByLabelText('Estimated annual budget (USD)'), { target: { value: '12345' } });
    await user.click(screen.getByRole('button', { name: 'Save and continue' }));
    await loaded('diagnostics');
    expect(screen.getByText('$12,345')).toBeVisible();
    expect(api.journeyCalls()).toBe(2);
    expect(sessionStorage.getItem(COMPARE_STORAGE_KEY)).toBeNull();
    await user.click(screen.getByRole('link', { name: /Continue to recommendations/ }));
    expect(await screen.findByRole('checkbox', { name: 'Compare Test University 40' })).not.toBeChecked();
    expect(api.journeyCalls()).toBe(2);
  });

  it('a saved update to profile preparation removes old universities and blocks recommendation navigation', async () => {
    const api = server();
    mount('recommendations');
    await loaded('recommendations');
    await userEvent.click(screen.getByRole('link', { name: 'Edit profile' }));
    await loaded('profile');
    await userEvent.click(screen.getByRole('button', { name: 'Remove cip code 1' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
    await screen.findByText('Required profile information is still missing');
    for (const name of ['Recommendations', 'Compare']) expect(nav().getByRole('link', { name: new RegExp(name) })).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(nav().getByRole('link', { name: /Roadmap/ }));
    expect(await screen.findByRole('heading', { name: 'Define your intended major' })).toBeVisible();
    expect(nav().getAllByText('Completed')).toHaveLength(2);
    expect(screen.queryByText('Test University 40')).not.toBeInTheDocument();
    expect(api.journeyCalls()).toBe(2);
  });

  it.each(routes)('recovers /%s after refresh from identity/backend and preserves truthful page content', async route => {
    const api = server();
    sessionStorage.setItem(COMPARE_STORAGE_KEY, '[40,20,10,999]');
    const first = mount(route);
    await loaded(route);
    expect(document.body.textContent).not.toMatch(forbidden);
    first.unmount();
    clearJourneyCache(); // Browser refresh loses all in-memory service state.
    mount(route);
    await loaded(route);
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(titles[route]);
    expect(document.body.textContent).not.toMatch(forbidden);
    expect(api.journeyCalls()).toBe(route === 'profile' ? 0 : 2);
    if (route === 'compare') expect(JSON.parse(sessionStorage.getItem(COMPARE_STORAGE_KEY)!)).toEqual([40, 20]);
  });

  it.each(routes.filter(route => route !== 'profile'))('recovers missing profile on /%s and clears comparison IDs', async route => {
    localStorage.setItem(LOCAL_PROFILE_KEY, 'deleted-profile');
    sessionStorage.setItem(COMPARE_STORAGE_KEY, '[40,20]');
    vi.stubGlobal('fetch', vi.fn(async () => missingProfile()));
    mount(route);
    await loaded('profile');
    expect(screen.getByLabelText('Display name')).toHaveValue('');
    expect(nav().queryByText('Completed')).not.toBeInTheDocument();
    expect(sessionStorage.getItem(COMPARE_STORAGE_KEY)).toBeNull();
  });

  it('uses safe retry feedback on every journey route without exposing server HTML', async () => {
    const api = server();
    let fail = true;
    const real = api.fetcher.getMockImplementation()!;
    api.fetcher.mockImplementation((url, options) => fail ? Promise.resolve(new Response('<h1>private stack trace</h1>', { status: 500 })) : real(url, options));
    mount('roadmap');
    expect(await screen.findByRole('alert')).toHaveTextContent('could not load your journey');
    expect(nav().queryByText('Completed')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/private stack trace/);
    fail = false;
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await loaded('roadmap');
    expect(api.journeyCalls()).toBe(2);
  });

  it('handles blocked identity storage on a direct journey route with recovery', async () => {
    server(false);
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked'); });
    mount('compare');
    expect(await screen.findByRole('alert')).toHaveTextContent('Allow browser storage');
    spy.mockRestore();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await loaded('profile');
  });

  it('never restores another profile’s otherwise eligible comparison identifiers', async () => {
    server();
    sessionStorage.setItem(COMPARE_PROFILE_KEY, 'another-profile');
    sessionStorage.setItem(COMPARE_STORAGE_KEY, '[40,20]');
    mount('compare');
    expect(await screen.findByRole('heading', { name: 'Select at least two universities to compare.' })).toBeVisible();
    expect(sessionStorage.getItem(COMPARE_STORAGE_KEY)).toBe('[]');
  });

  it('responds to profile identity replacement from another tab without retaining old results', async () => {
    server();
    mount('recommendations');
    await loaded('recommendations');
    vi.stubGlobal('fetch', vi.fn(async () => missingProfile()));
    act(() => {
      localStorage.setItem(LOCAL_PROFILE_KEY, 'replacement');
      window.dispatchEvent(new StorageEvent('storage', { key: LOCAL_PROFILE_KEY, newValue: 'replacement' }));
    });
    await loaded('profile');
    expect(screen.queryByText('Test University 40')).not.toBeInTheDocument();
    expect(nav().queryByText('Completed')).not.toBeInTheDocument();
  });

  it('does not publish an old in-flight response after a successful profile save', async () => {
    const api = server();
    let release!: (response: Response) => void;
    api.fetcher.mockImplementationOnce(() => new Promise(resolve => { release = resolve; }));
    const key = localStorage.getItem(LOCAL_PROFILE_KEY)!;
    const oldRequest = loadJourney(key);
    const profile = { ...profileFixture(), profile_key: key };
    await saveProfile(profile, new AbortController().signal);
    const freshRequest = loadJourney(key);
    await freshRequest;
    const fresh = getJourneySnapshot(key);
    release(jsonResponse(preparationJourneyFixture()));
    await oldRequest;
    expect(getJourneySnapshot(key)).toBe(fresh);
    expect(fresh.state.status).toBe('ready');
  });

  it('rejects a valid response belonging to another profile', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(recommendationJourneyFixture())));
    await expect(loadJourney('different-profile')).rejects.toThrow('expected contract');
    expect(getJourneySnapshot('different-profile').state.status).toBe('error');
  });

  it('prunes selections if the current result set changes while mounted', async () => {
    server();
    const items = recommendationJourneyFixture().recommendations!.recommendations;
    sessionStorage.setItem(COMPARE_STORAGE_KEY, '[40,20]');
    function Selection({ items }: { items: UniversityRecommendation[] }) {
      const { selected } = useCompareSelection(items);
      return <output>{selected.join(',')}</output>;
    }
    const view = render(<Selection items={items} />);
    expect(screen.getByRole('status')).toHaveTextContent('40,20');
    view.rerender(<Selection items={items.filter(item => item.institution.ipeds_unitid !== 40)} />);
    expect(screen.getByRole('status')).toHaveTextContent('20');
    await waitFor(() => expect(sessionStorage.getItem(COMPARE_STORAGE_KEY)).toBe('[20]'));
  });
});
