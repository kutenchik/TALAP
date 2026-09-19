import { ArrowRight, BookOpen, CircleDollarSign, GraduationCap, Languages, MapPin, Pencil, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge, Card, ErrorState, LoadingState } from '../components/ui';
import { importanceLabels, missingInformationLabels, studyModeLabels, testScaleLabels, weightingLabels } from '../lib/journeyLabels';
import type { AdmissionJourney, ApplicantDiagnostic, MissingInformationImportance, TestAttemptDiagnostic } from '../types/journey';
import type { JourneyLoadState } from './useJourney';

const importanceOrder: MissingInformationImportance[] = ['required_for_next_step', 'useful', 'optional'];
const budgetFormatter = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

function numberText(value: number) {
  return Number.isInteger(value) ? String(value) : String(value);
}
function dateText(value: string | null) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
}
function yesNo(value: boolean | null) {
  return value === null ? 'Not provided' : value ? 'Yes' : 'No';
}
function ValueRow({ label, value }: { label: string; value: string }) {
  return <div className="diagnostic-value"><dt>{label}</dt><dd>{value}</dd></div>;
}
function Attempts({ attempts, emptyText }: { attempts: TestAttemptDiagnostic[]; emptyText: string }) {
  if (!attempts.length) return <p className="diagnostic-empty">{emptyText}</p>;
  return <ol className="attempt-list">{attempts.map((attempt, index) => {
    const taken = dateText(attempt.taken_on);
    return <li key={`${attempt.test_type}-${attempt.scale}-${index}`}>
      <strong>{testScaleLabels[attempt.scale]} {numberText(attempt.score)}</strong>
      {taken && <span>Taken {taken}</span>}
    </li>;
  })}</ol>;
}
function StateList({ states, emptyText }: { states: string[]; emptyText: string }) {
  return states.length ? <ul className="state-list">{states.map(state => <li key={state}>{state}</li>)}</ul> : <p className="diagnostic-empty">{emptyText}</p>;
}

function DiagnosticSummary({ diagnostic }: { diagnostic: ApplicantDiagnostic }) {
  const gpa = diagnostic.academics.gpa;
  const rank = diagnostic.academics.class_rank;
  return <div className="diagnostic-grid">
    <Card className="diagnostic-card"><span className="diagnostic-card-icon"><GraduationCap aria-hidden="true" /></span><h4>Academic profile</h4><dl>
      <ValueRow label="GPA" value={gpa.state === 'provided' && gpa.gpa_value !== null ? `${numberText(gpa.gpa_value)}${gpa.gpa_scale !== null ? ` / ${numberText(gpa.gpa_scale)}` : ''}` : 'Not provided'} />
      <ValueRow label="Weighting" value={weightingLabels[gpa.gpa_weighting]} />
      <ValueRow label="Graduation year" value={diagnostic.academics.graduation_year?.toString() ?? 'Not provided'} />
      <ValueRow label="Class rank" value={rank.state === 'provided' && rank.class_rank !== null ? `${rank.class_rank}${rank.class_size !== null ? ` of ${rank.class_size}` : ''}` : 'Not provided'} />
    </dl><div className="diagnostic-subsection"><h5>SAT and ACT attempts</h5><Attempts attempts={diagnostic.testing.attempts} emptyText="No SAT or ACT score provided" /></div></Card>
    <Card className="diagnostic-card"><span className="diagnostic-card-icon"><Languages aria-hidden="true" /></span><h4>English testing</h4><Attempts attempts={diagnostic.english.attempts} emptyText="No English test score provided" /></Card>
    <Card className="diagnostic-card"><span className="diagnostic-card-icon"><BookOpen aria-hidden="true" /></span><h4>Study direction</h4><dl><ValueRow label="Mode" value={studyModeLabels[diagnostic.goal.mode]} /></dl>
      <div className="diagnostic-subsection"><h5>{diagnostic.goal.mode === 'known_major' ? 'Submitted CIP codes' : 'Submitted interests'}</h5><StateList states={diagnostic.goal.mode === 'known_major' ? diagnostic.goal.intended_cip_codes : diagnostic.goal.interests} emptyText="Not provided" /></div></Card>
    <Card className="diagnostic-card"><span className="diagnostic-card-icon"><CircleDollarSign aria-hidden="true" /></span><h4>Financial context</h4><dl>
      <ValueRow label="Annual budget" value={diagnostic.financial.annual_budget_usd === null ? 'Not provided' : budgetFormatter.format(diagnostic.financial.annual_budget_usd)} />
      <ValueRow label="Financial aid needed" value={yesNo(diagnostic.financial.needs_financial_aid)} />
    </dl></Card>
  </div>;
}

function Preferences({ diagnostic }: { diagnostic: ApplicantDiagnostic }) {
  return <section className="diagnostic-section" aria-labelledby="location-heading"><div className="diagnostic-section-heading"><div><span className="section-kicker">Your profile</span><h3 id="location-heading">Location preferences and constraints</h3></div><MapPin aria-hidden="true" /></div><div className="location-grid">
    <div><h4>Preferred states</h4><StateList states={diagnostic.preferences.preferred_states} emptyText="No preferred states provided" /></div>
    <div><h4>Excluded states</h4><StateList states={diagnostic.preferences.excluded_states} emptyText="No excluded states provided" /></div>
    <div className="explicit-constraints"><h4>Explicit exclusions</h4>{diagnostic.explicit_constraints.length
      ? <><StateList states={diagnostic.explicit_constraints.map(item => item.value)} emptyText="" /><p className="constraint-source">Source: Your profile</p></>
      : <p className="diagnostic-empty">No hard location exclusions</p>}</div>
  </div></section>;
}

function MissingInformation({ diagnostic }: { diagnostic: ApplicantDiagnostic }) {
  return <section className="diagnostic-section" aria-labelledby="missing-heading"><div className="diagnostic-section-heading"><div><span className="section-kicker">Information to complete</span><h3 id="missing-heading">Missing information</h3></div></div>
    {diagnostic.missing_information.length === 0 ? <p className="diagnostic-empty">No missing profile information listed.</p> : <div className="missing-groups">{importanceOrder.map(importance => {
      const items = diagnostic.missing_information.filter(item => item.importance === importance);
      if (!items.length) return null;
      return <div className={`missing-group missing-group--${importance}`} key={importance}><h4>{importanceLabels[importance]}</h4><ol>{items.map(item => <li key={item.code}><strong>{missingInformationLabels[item.code]}</strong><span>{item.message}</span></li>)}</ol></div>;
    })}</div>}
  </section>;
}

function ReadyDiagnostic({ journey }: { journey: AdmissionJourney }) {
  const needsGoal = journey.diagnostic.missing_information.some(item => item.importance === 'required_for_next_step');
  const preparation = journey.journey_state === 'profile_preparation';
  return <>
    {preparation && needsGoal && <div className="preparation-note" role="status"><ShieldCheck aria-hidden="true" /><div><strong>Required profile information is still missing</strong><p>Talap needs the required item below before university recommendations can be generated.</p></div></div>}
    <section aria-labelledby="available-heading"><div className="diagnostic-section-heading"><div><span className="section-kicker">Information available</span><h3 id="available-heading">Your submitted details</h3></div></div><DiagnosticSummary diagnostic={journey.diagnostic} /></section>
    <Preferences diagnostic={journey.diagnostic} />
    <MissingInformation diagnostic={journey.diagnostic} />
    <div className="diagnostic-actions"><Link className="button button--secondary" to="/profile"><Pencil size={16} aria-hidden="true" />Edit profile</Link><Link className="button button--primary" to={preparation ? '/profile' : '/recommendations'}>{preparation ? 'Complete your profile' : 'Continue to recommendations'}<ArrowRight size={16} aria-hidden="true" /></Link></div>
  </>;
}

export function DiagnosticsPage({ state, onRetry }: { state: JourneyLoadState; onRetry: () => void }) {
  return <div className="page-content diagnostics-page"><header className="page-heading diagnostics-heading"><Badge>DIAGNOSTICS</Badge><h1 className="page-title">Your applicant diagnostic</h1><p>Here’s what Talap can confirm from the information you provided.</p></header>
    {state.status === 'loading' && <LoadingState message="Loading your diagnostic…" />}
    {state.status === 'error' && <ErrorState message={state.message} onRetry={onRetry} />}
    {state.status === 'ready' && <ReadyDiagnostic journey={state.journey} />}
  </div>;
}

export function DiagnosticsContextPanel({ state }: { state: JourneyLoadState }) {
  const preparation = state.status === 'ready' && state.journey.journey_state === 'profile_preparation';
  return <><Card className="journey-card diagnostics-context"><span className="context-icon"><ShieldCheck size={21} aria-hidden="true" /></span><h2 className="section-title">What this diagnostic means</h2><p className="caption">Talap keeps three kinds of information separate.</p><ul className="diagnostic-context-list"><li>Information you provided</li><li>Information that is missing</li><li>University-specific evaluation, which comes next</li></ul></Card>
    <Card className="context-small diagnostics-next"><Badge>NEXT STEP</Badge><h2 className="card-title">{preparation ? 'Complete the required profile information first' : 'Review evidence-based university recommendations'}</h2><p className="caption">{preparation ? 'Return to your profile to add the required study direction.' : 'Continue when you are ready to review university evidence.'}</p></Card></>;
}
