import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { jsonResponse, useProfileTestEnvironment } from './profileFixtures';
import { App } from '../app/App';
import { JourneyStepper } from '../components/JourneyStepper';
import { Button, EmptyState, ErrorState, Field, Input, LoadingState, StatusPill } from '../components/ui';
import { LOCAL_PROFILE_KEY } from '../lib/profiles';
import { readyJourneyFixture } from './journeyFixtures';

function renderApp(path = '/profile') {
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
}
describe('desktop foundation', () => {
  useProfileTestEnvironment();
  it('renders Talap and the three desktop areas without reference branding', () => {
    renderApp();
    expect(screen.getByRole('link', { name: 'Talap home' })).toBeVisible();
    expect(screen.queryByText(/Pathway AI/i)).not.toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'About Talap' })).toBeVisible();
    expect(screen.getByRole('main', { name: 'Product workspace' })).toBeVisible();
    expect(screen.getByRole('complementary', { name: 'Journey information' })).toBeVisible();
  });
  it('redirects the root to the profile and marks exactly one current step', () => {
    renderApp('/');
    const nav = screen.getByRole('navigation', { name: 'Application journey' });
    expect(within(nav).getAllByRole('listitem')).toHaveLength(5);
    expect(within(nav).getByRole('link', { current: 'step' })).toHaveTextContent('Profile');
    expect(within(nav).queryByText('Completed')).not.toBeInTheDocument();
  });
  it('navigates to the real roadmap without claiming compare completion', async () => {
    const user = userEvent.setup();
    const journey = readyJourneyFixture();
    localStorage.setItem(LOCAL_PROFILE_KEY, journey.profile_key);
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(journey)));
    renderApp();
    const nav = screen.getByRole('navigation', { name: 'Application journey' });
    await user.click(within(nav).getByRole('link', { name: /Roadmap/ }));
    expect(await screen.findByRole('heading', { name: 'Your admissions roadmap' })).toBeVisible();
    expect(screen.getByText('No blocking actions are currently identified from the available evidence.')).toBeVisible();
    expect(within(screen.getByRole('navigation', { name: 'Application journey' })).getByRole('link', { current: 'step' })).toHaveTextContent('Roadmap');
    expect(screen.getAllByText('Completed')).toHaveLength(3);
    expect(within(screen.getByRole('navigation', { name: 'Application journey' })).getAllByRole('listitem')[3]).toHaveClass('step-future');
  });
  it('associates labels with working profile controls', async () => {
    renderApp();
    expect(await screen.findByLabelText('Display name')).toBeEnabled();
    for (const label of ['Citizenship country code *', 'GPA value', 'GPA scale', 'Estimated annual budget (USD)']) expect(screen.getByLabelText(label)).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Save and continue' })).toBeEnabled();
  });
  it('renders explicit completed, current, and future step states', () => {
    render(<MemoryRouter><JourneyStepper currentStep={2} completedSteps={[1]} /></MemoryRouter>);
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByRole('link', { current: 'step' })).toHaveTextContent('Diagnostics');
    expect(screen.getAllByRole('listitem')[4]).toHaveClass('step-future');
  });
  it('offers an accessible keyboard-operated primary button with safe default type', async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<Button onClick={onClick}>Continue</Button>);
    await user.tab();
    expect(screen.getByRole('button', { name: 'Continue' })).toHaveFocus();
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
    await user.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalledOnce();
  });
  it('links help and error descriptions to a field', () => {
    render(<Field label="Name" help="Use your chosen name" error="Enter a name"><Input /></Field>);
    expect(screen.getByLabelText('Name')).toHaveAccessibleDescription('Use your chosen name Enter a name');
    expect(screen.getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true');
  });
  it('renders feedback and truthful status components', async () => {
    const retry = vi.fn();
    render(<><LoadingState /><ErrorState message="Please try again later." onRetry={retry} /><EmptyState title="Nothing here yet" description="Add a profile to begin." /><StatusPill status="unavailable" /><StatusPill status="verification" /><StatusPill status="partial" /><StatusPill status="unevaluated" /></>);
    expect(screen.getByRole('status')).toHaveTextContent('Loading');
    expect(screen.getByRole('alert')).toHaveTextContent('Please try again later.');
    expect(screen.getByRole('heading', { name: 'Nothing here yet' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(retry).toHaveBeenCalledOnce();
    for (const text of ['Unavailable', 'Needs verification', 'Partial evidence', 'Not evaluated']) expect(screen.getByText(text)).toBeVisible();
  });
});

