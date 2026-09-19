import { ArrowRight, GitCompareArrows, MapPin, Scale, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge, Button, Card, EmptyState, ErrorState, LoadingState } from '../components/ui';
import { DesktopShell } from '../layouts/DesktopShell';
import { testScaleLabels, testTypeFallbackLabels } from '../lib/journeyLabels';
import {
  academicLabels,
  actionLabels,
  englishLabels,
  policyLabels,
  programLabels,
  qualityLabels,
  recommendationLabels,
} from '../lib/recommendationLabels';
import type {
  EvidenceState,
  TestScale,
  UniversityRecommendation,
} from '../types/journey';
import { useCompareSelection } from './useCompareSelection';
import { useJourney } from './useJourney';

const evidenceLabels: Record<EvidenceState, string> = {
  verified: 'Verified evidence',
  partial: 'Partial evidence',
  conflicting: 'Conflicting evidence',
  unavailable: 'Unavailable',
  not_applicable: 'Not applicable',
};

function scaleLabel(scale: string) {
  return Object.hasOwn(testScaleLabels, scale) ? testScaleLabels[scale as TestScale] : scale;
}

function ProgramCell({ item }: { item: UniversityRecommendation }) {
  const program = item.assessment.program;
  return <div className="compare-cell-content"><strong>{programLabels[program.state]}</strong>
    {program.requested_cips.length > 0 && <ul>{program.requested_cips.map(cip => <li key={cip.cip_code}><span>{cip.cip_code}</span>: {cip.state === 'observed' ? 'Evidence found' : cip.state === 'not_observed' ? 'Not observed in current data' : 'Unavailable'}{cip.academic_years.length > 0 && ` (${cip.academic_years.join(', ')})`}</li>)}</ul>}
  </div>;
}

function EnglishCell({ item }: { item: UniversityRecommendation }) {
  const english = item.assessment.english;
  return <div className="compare-cell-content"><strong>{policyLabels[english.policy_state]}</strong>
    {english.tests.length > 0 && <ul>{english.tests.map((test, index) => <li key={`${test.test_type}-${index}`}><span>{testTypeFallbackLabels[test.test_type]}: {englishLabels[test.state]}</span>
      {test.requirements.map((requirement, requirementIndex) => <p key={requirementIndex}>{scaleLabel(requirement.scale)}: minimum {requirement.minimum_score}; cycle {requirement.policy_cycle}{requirement.valid_for_tests_before && `; tests before ${requirement.valid_for_tests_before}`}{requirement.valid_for_tests_on_or_after && `; tests on or after ${requirement.valid_for_tests_on_or_after}`}</p>)}
      {test.supporting_attempts.map((attempt, attemptIndex) => <p key={attemptIndex}>{scaleLabel(attempt.scale)}: submitted {attempt.score}{attempt.taken_on && ` (${attempt.taken_on})`}</p>)}
      {test.conditional_policy_present && <p>Conditional policy present</p>}
    </li>)}</ul>}
  </div>;
}

function AcademicCell({ item }: { item: UniversityRecommendation }) {
  const academic = item.assessment.academic;
  return <div className="compare-cell-content"><p><strong>SAT:</strong> {academicLabels[academic.sat.state]}</p>
    {academic.sat.context && <p>{scaleLabel(academic.sat.context.scale)}: {academic.sat.context.lower}–{academic.sat.context.upper}</p>}
    <p><strong>ACT:</strong> {academicLabels[academic.act.state]}</p>
    {academic.act.context && <p>{scaleLabel(academic.act.context.scale)}: {academic.act.context.lower}–{academic.act.context.upper}</p>}
    {academic.data_year && <p>Data year: {academic.data_year}</p>}
  </div>;
}

function QualityCell({ item }: { item: UniversityRecommendation }) {
  const quality = item.assessment.evidence_quality;
  return <div className="compare-cell-content"><strong>{qualityLabels[item.signals.data_quality]}</strong><ul>
    <li>Program: {evidenceLabels[quality.program]}</li>
    <li>English: {evidenceLabels[quality.english]}</li>
    <li>Academic: {evidenceLabels[quality.academic]}</li>
  </ul></div>;
}

function ActionsCell({ item }: { item: UniversityRecommendation }) {
  return item.action_codes.length > 0
    ? <ul className="compare-action-list">{item.action_codes.map(code => <li key={code}>{actionLabels[code]}</li>)}</ul>
    : <p className="compare-empty-value">No actions listed.</p>;
}

function SelectionRequired() {
  return <div className="compare-selection-required"><EmptyState title="Select at least two universities to compare." description="Choose two or three eligible universities from your recommendations." /><Link className="button button--primary" to="/recommendations">Back to recommendations</Link></div>;
}

function ComparisonTable({ items, onRemove }: { items: UniversityRecommendation[]; onRemove: (unitid: number) => void }) {
  return <div className="comparison-table-wrap"><table className="comparison-table">
    <caption>Factual comparison of selected universities</caption>
    <thead><tr><th scope="col" className="comparison-row-heading">Evidence</th>{items.map(item => <th scope="col" key={item.institution.ipeds_unitid}>
      <div className="comparison-university"><span className="university-initial" aria-hidden="true">{item.institution.name.charAt(0).toUpperCase()}</span><div><h3>{item.institution.name}</h3><p><MapPin size={13} aria-hidden="true" />{item.institution.state || 'Location unavailable'}</p></div></div>
      <span className={`recommendation-state recommendation-state--${item.recommendation_state}`}>{recommendationLabels[item.recommendation_state]}</span>
      <Button variant="ghost" className="comparison-remove" onClick={() => onRemove(item.institution.ipeds_unitid)} aria-label={`Remove ${item.institution.name} from comparison`}><X size={14} aria-hidden="true" />Remove</Button>
    </th>)}</tr></thead>
    <tbody>
      <tr><th scope="row">Recommendation state</th>{items.map(item => <td key={item.institution.ipeds_unitid}>{recommendationLabels[item.recommendation_state]}</td>)}</tr>
      <tr><th scope="row">Location</th>{items.map(item => <td key={item.institution.ipeds_unitid}>{item.institution.state || 'Location unavailable'}</td>)}</tr>
      <tr><th scope="row">Program evidence</th>{items.map(item => <td key={item.institution.ipeds_unitid}><ProgramCell item={item} /></td>)}</tr>
      <tr><th scope="row">English requirement and evidence</th>{items.map(item => <td key={item.institution.ipeds_unitid}><EnglishCell item={item} /></td>)}</tr>
      <tr><th scope="row">Academic context</th>{items.map(item => <td key={item.institution.ipeds_unitid}><AcademicCell item={item} /></td>)}</tr>
      <tr><th scope="row"><span>Evidence quality</span><small>Data coverage, not likelihood of admission.</small></th>{items.map(item => <td key={item.institution.ipeds_unitid}><QualityCell item={item} /></td>)}</tr>
      <tr><th scope="row">Required and next actions</th>{items.map(item => <td key={item.institution.ipeds_unitid}><ActionsCell item={item} /></td>)}</tr>
    </tbody>
  </table></div>;
}

function CompareResults({ recommendations }: { recommendations: UniversityRecommendation[] }) {
  const { selected, toggle } = useCompareSelection(recommendations);
  const selectedItems = selected.map(unitid => recommendations.find(item => item.institution.ipeds_unitid === unitid)).filter((item): item is UniversityRecommendation => Boolean(item));
  if (selectedItems.length < 2) return <SelectionRequired />;
  return <><ComparisonTable items={selectedItems} onRemove={toggle} /><footer className="compare-actions"><Link className="button button--secondary" to="/recommendations">Change universities</Link><Link className="button button--primary" to="/roadmap">Continue to roadmap<ArrowRight size={16} aria-hidden="true" /></Link></footer></>;
}

export function ComparePage() {
  const { state, retry } = useJourney();
  const comparisonReady = state.status === 'ready' && state.journey.journey_state === 'recommendations_ready';
  const context = <Card className="journey-card"><span className="context-icon"><Scale aria-hidden="true" /></span><h2 className="section-title">How to compare</h2><ul className="diagnostic-context-list"><li>Compare evidence rather than a single score.</li><li>Missing evidence is not a negative fact.</li><li>Actions show what should be verified next.</li></ul><div className="context-note"><GitCompareArrows size={18} aria-hidden="true" /><p>Talap presents the available facts without choosing an institution for you.</p></div></Card>;
  return <DesktopShell currentStep={4} completedSteps={comparisonReady ? [1, 2, 3] : []} contextPanel={context}><div className="page-content compare-page"><header className="page-heading"><Badge>COMPARE</Badge><h2 className="page-title">Compare universities</h2><p>Review the evidence Talap currently has for each option.</p></header>
    {state.status === 'loading' && <LoadingState message="Loading your university comparison..." />}
    {state.status === 'error' && <ErrorState message="Talap could not load your comparison. Please try again." onRetry={retry} />}
    {state.status === 'ready' && (state.journey.journey_state === 'recommendations_ready'
      ? <CompareResults key={state.journey.profile_key} recommendations={state.journey.recommendations?.recommendations ?? []} />
      : <SelectionRequired />)}
  </div></DesktopShell>;
}
