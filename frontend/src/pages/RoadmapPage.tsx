import { ArrowLeft, CircleCheckBig, Map as MapIcon, PencilLine } from 'lucide-react';
import { Link } from 'react-router-dom';
import { RoadmapItemCard } from '../components/RoadmapItemCard';
import { Badge, Card, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { DesktopShell } from '../layouts/DesktopShell';
import { roadmapPriorityLabels, roadmapPriorityOrder } from '../lib/roadmapLabels';
import type { AdmissionJourney, RoadmapItem } from '../types/journey';
import { useJourney } from './useJourney';

function RoadmapContextPanel() {
  return <Card className="journey-card roadmap-context"><span className="context-icon"><MapIcon aria-hidden="true" /></span><h2 className="section-title">How to use your roadmap</h2><dl>
    <div><dt>Required</dt><dd>Profile information needed before the next stage.</dd></div>
    <div><dt>High and medium</dt><dd>Actions worth addressing as you review your options.</dd></div>
    <div><dt>Optional</dt><dd>Useful context that is not blocking.</dd></div>
  </dl><p className="caption">Priorities come from your current journey. They do not represent a calendar schedule.</p></Card>;
}

function resolveUniversityNames(item: RoadmapItem, names: ReadonlyMap<number, string>) {
  return item.institution_unitids.map(unitid => names.get(unitid) ?? `University ID ${unitid}`);
}

function PriorityGroups({ items, names }: { items: RoadmapItem[]; names: ReadonlyMap<number, string> }) {
  const groups = roadmapPriorityOrder.map(priority => ({
    priority,
    items: items.filter(item => item.priority === priority),
  })).filter(group => group.items.length > 0);
  return <div className="roadmap-groups">{groups.map(group => <section className="roadmap-group" key={group.priority} aria-labelledby={`roadmap-${group.priority}`}>
    <header><h3 id={`roadmap-${group.priority}`}>{roadmapPriorityLabels[group.priority]}</h3><span>{group.items.length} {group.items.length === 1 ? 'action' : 'actions'}</span></header>
    <div className="roadmap-items">{group.items.map((item, index) => <RoadmapItemCard key={`${item.action_code}-${index}`} item={item} universityNames={resolveUniversityNames(item, names)} />)}</div>
  </section>)}</div>;
}

function RoadmapActions({ state }: { state: AdmissionJourney['roadmap']['roadmap_state'] }) {
  return <footer className="roadmap-actions"><Link className="button button--secondary" to="/profile"><PencilLine size={15} aria-hidden="true" />Edit profile</Link>
    {state === 'profile_preparation'
      ? <Link className="button button--primary" to="/profile">Update profile</Link>
      : <Link className="button button--primary" to="/recommendations"><ArrowLeft size={15} aria-hidden="true" />Back to recommendations</Link>}
  </footer>;
}

function RoadmapResults({ journey }: { journey: AdmissionJourney }) {
  const recommendationItems = journey.recommendations?.recommendations ?? [];
  const names = new Map(recommendationItems.map(item => [item.institution.ipeds_unitid, item.institution.name]));
  const roadmap = journey.roadmap;
  return <DesktopShell currentStep={5} contextPanel={<RoadmapContextPanel />}><div className="page-content roadmap-page"><header className="page-heading"><Badge>ROADMAP</Badge><h1 className="page-title">Your admissions roadmap</h1><p>These are the next actions supported by your current profile and university evidence.</p></header>
    {roadmap.roadmap_state === 'no_blocking_actions' && <div className="roadmap-clear-state"><CircleCheckBig aria-hidden="true" /><div><h3>No blocking actions are currently identified from the available evidence.</h3><p>Unavailable evidence may still require review.</p></div></div>}
    {roadmap.items.length > 0 && <PriorityGroups items={roadmap.items} names={names} />}
    {roadmap.items.length === 0 && roadmap.roadmap_state !== 'no_blocking_actions' && <EmptyState title="No roadmap actions available" description="Your current journey did not return any actions to display." />}
    <RoadmapActions state={roadmap.roadmap_state} />
  </div></DesktopShell>;
}

export function RoadmapPage() {
  const { state, retry } = useJourney();
  if (state.status === 'ready') return <RoadmapResults journey={state.journey} />;
  return <DesktopShell currentStep={5} contextPanel={<RoadmapContextPanel />}><div className="page-content roadmap-page"><header className="page-heading"><Badge>ROADMAP</Badge><h1 className="page-title">Your admissions roadmap</h1><p>These are the next actions supported by your current profile and university evidence.</p></header>
    {state.status === 'loading' ? <LoadingState message="Loading your admissions roadmap..." /> : <ErrorState message={state.message} onRetry={retry} />}
  </div></DesktopShell>;
}
