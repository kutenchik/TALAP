import { Building2, MapPin } from 'lucide-react';
import { academicLabels, actionLabels, englishLabels, policyLabels, programLabels, qualityLabels, reasonLabels, recommendationLabels } from '../lib/recommendationLabels';
import { testScaleLabels, testTypeFallbackLabels } from '../lib/journeyLabels';
import type { TestScale, UniversityRecommendation } from '../types/journey';

function scaleLabel(scale: string) {
  return Object.hasOwn(testScaleLabels, scale) ? testScaleLabels[scale as TestScale] : scale;
}
export function UniversityRecommendationCard({ item, selected, atLimit, onToggle }: { item: UniversityRecommendation; selected: boolean; atLimit: boolean; onToggle: () => void }) {
  const { institution, assessment } = item;
  const excluded = item.recommendation_state === 'excluded_by_applicant';
  return <article className={`university-card${excluded ? ' university-card--excluded' : ''}`} aria-labelledby={`university-${institution.ipeds_unitid}`}>
    <header className="university-heading"><Building2 size={24} aria-hidden="true" /><div><h3 id={`university-${institution.ipeds_unitid}`}>{institution.name}</h3><p><MapPin size={13} aria-hidden="true" />{institution.state || 'Location unavailable'}</p></div></header>
    <span className={`recommendation-state recommendation-state--${item.recommendation_state}`}>{recommendationLabels[item.recommendation_state]}</span>
    {excluded && <p className="caption">Excluded by your location preferences</p>}
    <div className="recommendation-evidence">
      <section><h4>Program</h4><p>{programLabels[assessment.program.state]}</p><ul>{assessment.program.requested_cips.map(cip => <li key={cip.cip_code}>{cip.cip_code}: {cip.state === 'observed' ? 'Evidence found' : cip.state === 'not_observed' ? 'Not observed in current data' : 'Unavailable'}{cip.academic_years.length > 0 && ` (${cip.academic_years.join(', ')})`}</li>)}</ul></section>
      <section><h4>English</h4><p>{policyLabels[assessment.english.policy_state]}</p><ul>{assessment.english.tests.map((test, index) => <li key={`${test.test_type}-${index}`}><strong>{testTypeFallbackLabels[test.test_type]}: {englishLabels[test.state]}</strong>
        {test.requirements.map((requirement, i) => <p key={i}>{scaleLabel(requirement.scale)}: minimum {requirement.minimum_score}; cycle {requirement.policy_cycle}{requirement.valid_for_tests_before && `; tests before ${requirement.valid_for_tests_before}`}{requirement.valid_for_tests_on_or_after && `; tests on or after ${requirement.valid_for_tests_on_or_after}`}</p>)}
        {test.supporting_attempts.map((attempt, i) => <p key={i}>{scaleLabel(attempt.scale)}: submitted {attempt.score}{attempt.taken_on && ` (${attempt.taken_on})`}</p>)}
        {test.conditional_policy_present && <p>Conditional policy present</p>}
      </li>)}</ul></section>
      <section><h4>Academic context</h4><p>SAT: {academicLabels[assessment.academic.sat.state]}</p><p>ACT: {academicLabels[assessment.academic.act.state]}</p>{assessment.academic.data_year && <p>Data year: {assessment.academic.data_year}</p>}</section>
      <section><h4>Evidence quality</h4><p>{qualityLabels[item.signals.data_quality]}</p></section>
    </div>
    <div className="recommendation-explanation"><section><h4>Why this appears</h4>{item.reason_codes.length ? <ul>{item.reason_codes.map(code => <li key={code}>{reasonLabels[code]}</li>)}</ul> : <p>No additional reasons supplied.</p>}</section><section><h4>Next actions</h4>{item.action_codes.length ? <ul>{item.action_codes.map(code => <li key={code}>{actionLabels[code]}</li>)}</ul> : <p>No actions listed.</p>}</section></div>
    <label className="compare-choice"><input type="checkbox" checked={selected} disabled={excluded || (!selected && atLimit)} onChange={onToggle} aria-label={`Compare ${institution.name}`} />Select for comparison{excluded && <span>Unavailable for excluded universities</span>}</label>
  </article>;
}
