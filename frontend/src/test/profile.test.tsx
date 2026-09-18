import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../app/App';
import { LOCAL_PROFILE_KEY } from '../lib/profiles';
import { emptyDraft, textRow, toDraft, toPayload } from '../lib/profileForm';
import { jsonResponse, missingProfile, mockProfileServer, profileFixture, useProfileTestEnvironment, useSavedProfile } from './profileFixtures';

function renderProfile() {
  return render(<MemoryRouter initialEntries={['/profile']}><App /></MemoryRouter>);
}
async function ready() { await screen.findByLabelText('Display name'); }
const submit = () => screen.getByRole('button', { name: 'Save and continue' });
const form = () => screen.getByRole('form', { name: 'Your Talap profile' });
function edit(label: string, value: string) { fireEvent.change(screen.getByLabelText(label), { target: { value } }); }
function postPayload(fetcher: ReturnType<typeof mockProfileServer>['fetcher'], url: string) {
  const call = fetcher.mock.calls.find(([path]) => path === url);
  return JSON.parse(String(call?.[1]?.body));
}

describe('working profile', () => {
  useProfileTestEnvironment();

  it('renders empty supported groups without invented applicant values or target countries', async () => {
    const { fetcher } = mockProfileServer();
    renderProfile();
    expect(screen.getByRole('status')).toHaveTextContent('Loading your profile');
    await ready();
    for (const name of ['About you', 'Study direction', 'Academics', 'Test scores', 'Budget and aid', 'Location preferences']) expect(screen.getByRole('region', { name })).toBeVisible();
    expect(screen.getByLabelText('Display name')).toHaveValue('');
    expect(screen.getByLabelText('GPA value')).toHaveValue(null);
    expect(screen.getByLabelText('GPA scale')).toHaveValue(null);
    expect(screen.getByLabelText('Do you need financial aid?')).toHaveValue('');
    expect(screen.queryByText(/Pathway AI|Alex Chen|Canada|United Kingdom/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/target country/i)).not.toBeInTheDocument();
    expect(fetcher).not.toHaveBeenCalled();
    expect(localStorage.getItem(LOCAL_PROFILE_KEY)).toMatch(/^talap-local-/);
  });

  it('reuses the local key and treats only profile_not_found as a fresh profile', async () => {
    localStorage.setItem(LOCAL_PROFILE_KEY, 'talap-local-existing');
    const { fetcher } = mockProfileServer();
    renderProfile(); await ready();
    expect(fetcher).toHaveBeenCalledWith('/api/v1/profiles/talap-local-existing/', expect.objectContaining({ method: 'GET' }));
    expect(localStorage.getItem(LOCAL_PROFILE_KEY)).toBe('talap-local-existing');
    expect(screen.getByLabelText('Display name')).toHaveValue('');
  });

  it('prefills actual backend data including zero, false, notes, class rank, and TOEFL scale', async () => {
    useSavedProfile(); renderProfile(); await ready();
    expect(screen.getByLabelText('Display name')).toHaveValue('Test Applicant');
    expect(screen.getByLabelText('GPA value')).toHaveValue(4.7);
    expect(screen.getByLabelText('GPA scale')).toHaveValue(5);
    expect(screen.getByLabelText('Estimated annual budget (USD)')).toHaveValue(0);
    expect(screen.getByLabelText('Do you need financial aid?')).toHaveValue('no');
    expect(screen.getByLabelText('Test 1')).toHaveValue('toefl_ibt_1_6');
    expect(screen.getByLabelText('Taken date 1')).toHaveValue('2026-02-01');
    expect(screen.getByLabelText('Note 1 (optional)')).toHaveValue('Practice fixture');
    expect(screen.getByLabelText('Class rank')).toHaveValue(2);
    expect(screen.getByLabelText('CIP code 1')).toHaveValue('11.0701');
  });

  it('shows a load error for generic 404 and retries without overwriting identity', async () => {
    localStorage.setItem(LOCAL_PROFILE_KEY, 'talap-local-retry');
    const fetcher = vi.fn().mockResolvedValueOnce(jsonResponse({ error: { code: 'wrong_route', message: 'secret exception' } }, 404)).mockResolvedValueOnce(missingProfile());
    vi.stubGlobal('fetch', fetcher);
    renderProfile();
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load');
    expect(screen.queryByText('secret exception')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await ready();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(localStorage.getItem(LOCAL_PROFILE_KEY)).toBe('talap-local-retry');
  });

  it('reports blocked localStorage instead of silently losing identity', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
    renderProfile();
    expect(await screen.findByRole('alert')).toHaveTextContent('allow browser storage');
    storage.mockRestore();
  });

  it('switches study modes with keyboard support and sends only the active ordered interests', async () => {
    const { fetcher } = mockProfileServer();
    const user = userEvent.setup();
    renderProfile(); await ready();
    edit('Citizenship country code *', 'KZ');
    await user.click(screen.getByRole('button', { name: 'Add cip code' }));
    edit('CIP code 1', '11.0701');
    screen.getByRole('radio', { name: 'I know my major' }).focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: 'Help me choose' })).toBeChecked();
    expect(screen.queryByLabelText('CIP code 1')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Add interest' })); edit('Interest 1', 'AI / Technology');
    await user.click(screen.getByRole('button', { name: 'Add interest' })); edit('Interest 2', 'Social Impact');
    await user.click(submit());
    await screen.findByRole('heading', { name: 'Your applicant diagnostic' });
    expect(postPayload(fetcher, '/api/v1/profiles/').study_intent).toEqual({ mode: 'explore', intended_cip_codes: [], interests: ['AI / Technology', 'Social Impact'] });
  });

  it('allows adding/removing CIP rows and prevents blank repeated entries', async () => {
    renderProfile(); await ready();
    await userEvent.click(screen.getByRole('button', { name: 'Add cip code' }));
    expect(screen.getByRole('button', { name: 'Add cip code' })).toBeDisabled();
    edit('CIP code 1', '11.0701');
    await userEvent.click(screen.getByRole('button', { name: 'Add cip code' }));
    edit('CIP code 2', '14.0101');
    await userEvent.click(screen.getByRole('button', { name: 'Remove cip code 1' }));
    expect(screen.getByLabelText('CIP code 1')).toHaveValue('14.0101');
    expect(screen.queryByLabelText('CIP code 2')).not.toBeInTheDocument();
  });

  it('preserves arbitrary GPA scales, ordered test attempts and distinct TOEFL scales in payloads', async () => {
    const { fetcher } = mockProfileServer();
    renderProfile(); await ready();
    edit('Citizenship country code *', 'KZ'); edit('GPA value', '92'); edit('GPA scale', '100');
    await userEvent.click(screen.getByRole('button', { name: 'Add test score' }));
    await userEvent.selectOptions(screen.getByLabelText('Test 1'), 'toefl_ibt_0_120'); edit('Score 1 *', '100');
    await userEvent.click(screen.getByRole('button', { name: 'Add test score' }));
    await userEvent.selectOptions(screen.getByLabelText('Test 2'), 'toefl_ibt_1_6'); edit('Score 2 *', '5');
    await userEvent.click(screen.getByRole('button', { name: 'Add test score' })); edit('Score 3 *', '1200');
    await userEvent.click(screen.getByRole('button', { name: 'Remove test attempt 3' }));
    edit('Preferred U.S. states', 'ca, ny, ma'); fireEvent.blur(screen.getByLabelText('Preferred U.S. states'));
    expect(screen.getByLabelText('Preferred U.S. states')).toHaveValue('CA, NY, MA');
    edit('Excluded U.S. states', 'tx, fl');
    await userEvent.click(submit());
    await screen.findByRole('heading', { name: 'Your applicant diagnostic' });
    const payload = postPayload(fetcher, '/api/v1/profiles/validate/');
    expect(payload.academics).toMatchObject({ gpa_value: 92, gpa_scale: 100 });
    expect(payload.tests).toEqual([
      { test_type: 'toefl', scale: 'toefl_ibt_0_120', score: 100, taken_on: null, note: null },
      { test_type: 'toefl', scale: 'toefl_ibt_1_6', score: 5, taken_on: null, note: null },
    ]);
    expect(payload.preferences).toEqual({ preferred_states: ['CA', 'NY', 'MA'], excluded_states: ['TX', 'FL'] });
  });

  it('acquires CSRF, validates before saving, sends normalized response and reloads persisted mock data', async () => {
    const server = mockProfileServer();
    const view = renderProfile(); await ready();
    edit('Citizenship country code *', 'kz'); edit('Display name', 'Fictional Test');
    await userEvent.click(submit());
    await screen.findByRole('heading', { name: 'Your applicant diagnostic' });
    await waitFor(() => expect(server.fetcher.mock.calls.map(([url]) => url)).toEqual(['/api/v1/csrf/', '/api/v1/profiles/validate/', '/api/v1/profiles/', expect.stringContaining('/journey/?seed_order_start=1&seed_order_end=100')]));
    for (const [, options] of server.fetcher.mock.calls.slice(1, 3)) expect(options).toMatchObject({ credentials: 'same-origin', headers: { 'X-CSRFToken': 'test-csrf-token' } });
    expect(server.saved()).toMatchObject({ citizenship_country_code: 'KZ', display_name: 'Fictional Test', tests: [] });
    expect(screen.getByText('Completed')).toBeInTheDocument();
    view.unmount(); renderProfile(); await ready();
    expect(screen.getByLabelText('Display name')).toHaveValue('Fictional Test');
  });

  it('uses Django-normalized data for save instead of reusing the draft', async () => {
    const normalized = profileFixture();
    const fetcher = vi.fn().mockResolvedValueOnce(jsonResponse({ csrfToken: 'token' }))
      .mockResolvedValueOnce(jsonResponse(normalized)).mockResolvedValueOnce(jsonResponse(normalized));
    vi.stubGlobal('fetch', fetcher);
    renderProfile(); await ready(); edit('Citizenship country code *', 'KZ');
    await userEvent.click(submit()); await screen.findByRole('heading', { name: 'Your applicant diagnostic' });
    expect(JSON.parse(fetcher.mock.calls[2][1].body)).toEqual(normalized);
  });

  it('maps backend field and group errors, focuses the summary, and does not save invalid data', async () => {
    const details = [
      { location: ['academics', 'gpa_value'], message: 'GPA must be numeric.', type: 'decimal_parsing' },
      { location: ['tests', 0, 'score'], message: 'Enter a numeric score.', type: 'decimal_parsing' },
      { location: ['preferences', 'preferred_states'], message: 'Check state codes.', type: 'value_error' },
      { location: ['academics'], message: 'GPA value and scale must be supplied together.', type: 'value_error' },
    ];
    const fetcher = vi.fn().mockResolvedValueOnce(jsonResponse({ csrfToken: 'token' })).mockResolvedValueOnce(jsonResponse({ error: { code: 'validation_error', message: 'Invalid', details } }, 400));
    vi.stubGlobal('fetch', fetcher);
    renderProfile(); await ready(); edit('Citizenship country code *', 'KZ');
    await userEvent.click(screen.getByRole('button', { name: 'Add test score' })); edit('Score 1 *', '9999');
    await userEvent.click(submit());
    const alert = await screen.findByRole('alert');
    await waitFor(() => expect(alert).toHaveFocus());
    expect(within(alert).getByText('GPA must be numeric.')).toBeVisible();
    expect(screen.getByLabelText('GPA value')).toHaveAccessibleDescription('GPA must be numeric.');
    expect(screen.getByLabelText('Score 1 *')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Preferred U.S. states')).toHaveAccessibleDescription(expect.stringContaining('Check state codes.'));
    expect(screen.getByRole('group', { name: 'Academic information' })).toHaveAccessibleDescription('GPA value and scale must be supplied together.');
    expect(fetcher.mock.calls.some(([url]) => url === '/api/v1/profiles/')).toBe(false);
  });

  it('handles token acquisition failure safely and preserves edits for retry', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(new Response('private exception detail', { status: 500 }));
    vi.stubGlobal('fetch', fetcher);
    renderProfile(); await ready(); edit('Citizenship country code *', 'KZ'); edit('Display name', 'Keep my edit');
    await userEvent.click(submit());
    expect(await screen.findByRole('alert')).toHaveTextContent('new session token');
    expect(screen.queryByText('private exception detail')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Display name')).toHaveValue('Keep my edit');
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(submit()).toBeEnabled();
  });

  it('handles non-JSON CSRF rejection and save failures without navigating', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce(jsonResponse({ csrfToken: 'token' }))
      .mockResolvedValueOnce(jsonResponse(profileFixture())).mockResolvedValueOnce(new Response('<h1>CSRF private details</h1>', { status: 403 }));
    vi.stubGlobal('fetch', fetcher);
    renderProfile(); await ready(); edit('Citizenship country code *', 'KZ');
    await userEvent.click(submit());
    expect(await screen.findByRole('alert')).toHaveTextContent('session token was not accepted');
    expect(screen.getByLabelText('Citizenship country code *')).toHaveValue('KZ');
    expect(screen.queryByText('CSRF private details')).not.toBeInTheDocument();
  });

  it('rejects an empty bootstrap token before any POST', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ csrfToken: '' })); vi.stubGlobal('fetch', fetcher);
    renderProfile(); await ready(); edit('Citizenship country code *', 'KZ'); await userEvent.click(submit());
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save');
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it('blocks concurrent submission and disables editing while saving', async () => {
    let release!: (value: Response) => void;
    const pending = new Promise<Response>(resolve => { release = resolve; });
    const fetcher = vi.fn().mockReturnValueOnce(pending).mockImplementation(async () => jsonResponse(profileFixture()));
    vi.stubGlobal('fetch', fetcher);
    renderProfile(); await ready(); edit('Citizenship country code *', 'KZ');
    fireEvent.submit(form()); fireEvent.submit(form());
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
    expect(screen.getByLabelText('Display name')).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent('Validating and saving');
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => release(jsonResponse({ csrfToken: 'token' })));
    await screen.findByRole('heading', { name: 'Your applicant diagnostic' });
    expect(fetcher.mock.calls.filter(([url]) => url === '/api/v1/profiles/')).toHaveLength(1);
  });

  it('prevents journey navigation while dirty and warns on page unload', async () => {
    renderProfile(); await ready(); edit('Display name', 'Unsaved');
    const link = within(screen.getByRole('navigation', { name: 'Application journey' })).getByRole('link', { name: /Diagnostics/ });
    expect(link).toHaveAttribute('aria-disabled', 'true');
    await userEvent.click(link);
    expect(screen.getByLabelText('Display name')).toHaveValue('Unsaved');
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });
});

describe('profile representation', () => {
  it('round-trips all backend-supported fields without losing nulls, false, zero, order, or notes', () => {
    const profile = profileFixture();
    expect(toPayload(toDraft(profile), profile.profile_key)).toEqual(profile);
  });
  it('preserves missing values and excludes the inactive study mode', () => {
    const draft = emptyDraft(); draft.cips = [textRow('11.0701'), textRow('14.0101')]; draft.interests = [textRow('science')];
    const payload = toPayload(draft, 'key');
    expect(payload.study_intent).toEqual({ mode: 'known_major', intended_cip_codes: ['11.0701', '14.0101'], interests: [] });
    expect(payload.academics.gpa_scale).toBeNull();
    expect(payload.financial).toEqual({ annual_budget_usd: null, needs_financial_aid: null });
  });
});

