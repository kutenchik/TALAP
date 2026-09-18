import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, ListChecks } from 'lucide-react';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { UniversityRecommendationCard } from '../components/UniversityRecommendationCard';
import { DesktopShell } from '../layouts/DesktopShell';
import { recommendationLabels } from '../lib/recommendationLabels';
import type { AdmissionJourney, RecommendationState } from '../types/journey';
import { useJourney } from './useJourney';
import { useCompareSelection } from './useCompareSelection';

function RecommendationResults({ journey }: { journey: AdmissionJourney }) {
  const items = journey.recommendations?.recommendations ?? [];
  const { selected, toggle, storageUnavailable } = useCompareSelection(items);
  const [filter, setFilter] = useState<RecommendationState | 'all'>('all');
  const navigate = useNavigate();
  const visible = items.filter(item => filter === 'all' || item.recommendation_state === filter);
  return <>
    <div className="recommendation-toolbar"><label htmlFor="recommendation-filter">Show</label><select className="control" id="recommendation-filter" value={filter} onChange={event => setFilter(event.target.value as typeof filter)}><option value="all">All</option>{Object.entries(recommendationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span>{visible.length} of {journey.summary.candidate_count} universities</span></div>
    {!items.length ? <EmptyState title="No university recommendations available" description="There are no candidate results for this journey. You can review your profile and return later." /> : <>
      {items.every(item => item.recommendation_state === 'excluded_by_applicant') && <p className="demo-notice">All returned universities are excluded by your location preferences. Edit your profile to review those preferences.</p>}
      {items.every(item => item.recommendation_state === 'insufficient_evidence') && <p className="demo-notice">More candidate evidence is needed. Available details and missing information are shown below.</p>}
      {!visible.length && <EmptyState title="No universities in this filter" description="Choose another result state to view the returned universities." />}
      <div className="recommendation-list">{visible.map(item => <UniversityRecommendationCard key={item.institution.ipeds_unitid} item={item} selected={selected.includes(item.institution.ipeds_unitid)} atLimit={selected.length === 3} onToggle={() => toggle(item.institution.ipeds_unitid)} />)}</div>
    </>}
    <footer className="comparison-footer"><div><p role="status">{selected.length} selected. {selected.length === 3 ? 'Maximum of 3 selected.' : 'Select 2 or 3 universities.'}</p>{storageUnavailable && <p role="alert">Session storage is unavailable. Selection cannot be carried to comparison.</p>}<Link className="text-link" to="/profile">Edit profile</Link></div><Button disabled={selected.length < 2 || storageUnavailable} onClick={() => navigate('/compare')}>Compare selected<ArrowRight size={16} aria-hidden="true" /></Button></footer>
  </>;
}
export function RecommendationsPage() {
  const { state, retry } = useJourney();
  const ready = state.status === 'ready';
  const context = <Card className="journey-card"><span className="context-icon"><ListChecks aria-hidden="true" /></span><h2 className="section-title">How to read these recommendations</h2><ul className="diagnostic-context-list"><li>Recommendations use currently available evidence.</li><li>Unavailable data stays unavailable.</li><li>Actions identify information worth checking.</li></ul>{ready && <p className="caption">{state.journey.summary.candidate_count} universities returned</p>}</Card>;
  return <DesktopShell currentStep={3} completedSteps={ready ? [1, 2] : []} contextPanel={context}><div className="page-content recommendations-page"><header className="page-heading"><Badge>RECOMMENDATIONS</Badge><h2 className="page-title">Your university recommendations</h2><p>These universities are ordered using the evidence currently available for your profile.</p><p className="caption">Missing data is shown as unavailable rather than inferred.</p></header>
    {state.status === 'loading' && <LoadingState message="Loading your university recommendations..." />}
    {state.status === 'error' && <ErrorState message="Talap could not load your recommendations. Please try again." onRetry={retry} />}
    {ready && (state.journey.journey_state === 'profile_preparation' ? <><EmptyState title="Complete your profile first" description="Complete the required profile information before Talap can generate university recommendations." /><Link className="button button--primary" to="/profile">Complete profile</Link></> : <RecommendationResults key={state.journey.profile_key} journey={state.journey} />)}
  </div></DesktopShell>;
}
