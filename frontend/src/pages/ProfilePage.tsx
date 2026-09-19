import { useEffect, useRef, type InputHTMLAttributes, type ReactNode } from 'react';
import { ArrowRight, BookOpen, CalendarDays, DollarSign, Globe2, GraduationCap, MapPin, Plus, Trash2, UserRound } from 'lucide-react';
import { Badge, Button, ErrorState, Field, Input, LoadingState, SectionHeader, Select } from '../components/ui';
import { testOptions, textRow, type ProfileDraft, type TextRow } from '../lib/profileForm';
import { useProfile } from './useProfile';

interface ProfilePageProps { onNavigationLock: (locked: boolean) => void }

export function ProfilePage({ onNavigationLock }: ProfilePageProps) {
  const { draft, change, loadState, retryLoad, dirty, saving, problem, errorFor, submit } = useProfile();
  const summary = useRef<HTMLDivElement>(null);
  useEffect(() => {
    onNavigationLock(dirty || saving);
    return () => onNavigationLock(false);
  }, [dirty, saving, onNavigationLock]);
  useEffect(() => { if (problem) summary.current?.focus(); }, [problem]);

  function update<K extends keyof ProfileDraft>(name: K, value: ProfileDraft[K]) {
    change({ ...draft, [name]: value });
  }
  type StringField = { [K in keyof ProfileDraft]: ProfileDraft[K] extends string ? K : never }[keyof ProfileDraft];
  function input(name: StringField, label: string, path: string, options: InputHTMLAttributes<HTMLInputElement> & { help?: string; icon?: ReactNode } = {}) {
    const { help, icon, ...attributes } = options;
    return <Field label={label} help={help} error={errorFor(path)}>
      <Input {...attributes} icon={icon} value={draft[name]} onChange={event => update(name, event.target.value as ProfileDraft[typeof name])} />
    </Field>;
  }
  function repeatable(name: 'cips' | 'interests', label: string, path: string, help: string) {
    const rows = draft[name];
    function replace(id: string, value: string) { update(name, rows.map(row => row.id === id ? { ...row, value } : row)); }
    return <div className="repeatable-group">
      <p className="caption">{help}</p>
      {errorFor(path) && <p className="field-error">{errorFor(path)}</p>}
      {rows.map((row: TextRow, index) => <div className="repeatable-row" key={row.id}>
        <Field label={`${label} ${index + 1}`} error={errorFor(`${path}.${index}`)}>
          <Input required value={row.value} icon={<BookOpen size={17} />} onChange={event => replace(row.id, event.target.value)} />
        </Field>
        <Button variant="ghost" onClick={() => update(name, rows.filter(item => item.id !== row.id))} aria-label={`Remove ${label.toLowerCase()} ${index + 1}`}><Trash2 size={17} aria-hidden="true" /></Button>
      </div>)}
      <Button variant="secondary" onClick={() => update(name, [...rows, textRow()])} disabled={rows.some(row => !row.value.trim())}><Plus size={16} aria-hidden="true" />Add {label.toLowerCase()}</Button>
    </div>;
  }

  if (loadState === 'loading') return <LoadingState message="Loading your profile…" />;
  if (loadState === 'error') return <ErrorState message="Could not load your local profile. Check your connection to Django and allow browser storage, then try again." onRetry={retryLoad} />;

  return <div className="page-content profile-page">
    <div className="page-heading">
      <Badge>YOUR STARTING POINT</Badge>
      <h1 className="page-title">Let’s get to know you</h1>
      <p>Share a few details so we can build your personalized admissions route.</p>
    </div>
    <p className="caption profile-intro">* Required. Leave optional information blank if you don’t know it yet.</p>
    {problem && <div ref={summary} tabIndex={-1} role="alert" className="error-summary">
      <h3>{problem.message}</h3>
      {problem.details.length > 0 && <ul>{problem.details.map((detail, index) => <li key={index}>{detail.message}</li>)}</ul>}
      <p>Your edits are still here. Review them and try again.</p>
    </div>}
    <form aria-label="Your Talap profile" onSubmit={event => { event.preventDefault(); void submit(); }}>
      <fieldset className="profile-fields" disabled={saving}>
        <section className="profile-section" aria-label="About you">
          <SectionHeader title="About you" description="A few details about where you’re starting from." />
          <div className="form-grid">
            {input('displayName', 'Display name', 'display_name', { autoComplete: 'name', placeholder: 'Your name', icon: <UserRound size={17} /> })}
            {input('graduationYear', 'Graduation year', 'graduation_year', { type: 'number', step: 1, placeholder: 'Year', icon: <CalendarDays size={17} /> })}
            {input('citizenship', 'Citizenship country code *', 'citizenship_country_code', { required: true, placeholder: 'e.g. KZ', help: 'Two-letter country code.', icon: <Globe2 size={17} />, onBlur: () => update('citizenship', draft.citizenship.toUpperCase()) })}
            {input('residence', 'Residence country code', 'residence_country_code', { placeholder: 'e.g. KZ', icon: <Globe2 size={17} />, onBlur: () => update('residence', draft.residence.toUpperCase()) })}
            {input('school', 'School country code', 'school_country_code', { placeholder: 'e.g. KZ', icon: <GraduationCap size={17} />, onBlur: () => update('school', draft.school.toUpperCase()) })}
          </div>
        </section>

        <section className="profile-section" aria-label="Study direction">
          <SectionHeader title="Your study direction" description="Know your field, or tell us what interests you." />
          <fieldset className="intent-picker" aria-describedby={errorFor('study_intent') ? 'intent-error' : undefined}>
            <legend className="control-legend">Study intent *</legend>
            <div className="segmented-control">
              <label><input type="radio" name="study-intent" value="known_major" checked={draft.mode === 'known_major'} onChange={() => update('mode', 'known_major')} /><span>I know my major</span></label>
              <label><input type="radio" name="study-intent" value="explore" checked={draft.mode === 'explore'} onChange={() => update('mode', 'explore')} /><span>Help me choose</span></label>
            </div>
          </fieldset>
          {errorFor('study_intent') && <p id="intent-error" className="field-error">{errorFor('study_intent')}</p>}
          {draft.mode === 'known_major' ? repeatable('cips', 'CIP code', 'study_intent.intended_cip_codes', 'Enter a CIP code for each intended field. Example: 11.0701. You can leave this empty if you are still checking your codes.') :
            repeatable('interests', 'Interest', 'study_intent.interests', 'Add your interests in your preferred order, for example AI / Technology or Social Impact.')}
        </section>

        <section className="profile-section" aria-label="Academics">
          <SectionHeader title="Academics" description="Use the GPA and scale shown by your school." />
          <fieldset className="section-fields" aria-describedby={errorFor('academics') ? 'academics-error' : undefined}>
            <legend className="sr-only">Academic information</legend>
            {errorFor('academics') && <p id="academics-error" className="field-error">{errorFor('academics')}</p>}
            <div className="form-grid">
              {input('gpaValue', 'GPA value', 'academics.gpa_value', { type: 'number', step: 'any', placeholder: 'Your GPA', icon: <GraduationCap size={17} /> })}
              {input('gpaScale', 'GPA scale', 'academics.gpa_scale', { type: 'number', step: 'any', placeholder: 'e.g. 5 or 100', help: 'Enter both GPA value and its original scale.' })}
              <Field label="GPA weighting" error={errorFor('academics.gpa_weighting')}><Select value={draft.gpaWeighting} onChange={event => update('gpaWeighting', event.target.value as ProfileDraft['gpaWeighting'])}><option value="unknown">Unknown</option><option value="weighted">Weighted</option><option value="unweighted">Unweighted</option></Select></Field>
            </div>
            <details className="secondary-fields"><summary>Class rank (optional)</summary><div className="form-grid">
              {input('classRank', 'Class rank', 'academics.class_rank', { type: 'number', step: 1 })}
              {input('classSize', 'Class size', 'academics.class_size', { type: 'number', step: 1 })}
            </div></details>
          </fieldset>
        </section>

        <section className="profile-section" aria-label="Test scores">
          <SectionHeader title="Test scores" description="Add any attempts you want to include. You can also leave this empty." />
          {errorFor('tests') && <p className="field-error">{errorFor('tests')}</p>}
          <div className="test-attempts">{draft.tests.map((attempt, index) => {
            function edit(values: Partial<typeof attempt>) { update('tests', draft.tests.map(row => row.id === attempt.id ? { ...row, ...values } : row)); }
            return <fieldset className="test-attempt" key={attempt.id} aria-describedby={errorFor(`tests.${index}`) ? `test-${attempt.id}-error` : undefined}>
              <legend>Test attempt {index + 1}</legend>
              {errorFor(`tests.${index}`) && <p id={`test-${attempt.id}-error`} className="field-error">{errorFor(`tests.${index}`)}</p>}
              <div className="form-grid">
                <Field label={`Test ${index + 1}`} error={errorFor(`tests.${index}.test_type`) || errorFor(`tests.${index}.scale`)}><Select value={attempt.scale} onChange={event => edit({ scale: event.target.value as typeof attempt.scale })}>{testOptions.map(option => <option value={option.scale} key={option.scale}>{option.label}</option>)}</Select></Field>
                <Field label={`Score ${index + 1} *`} error={errorFor(`tests.${index}.score`)}><Input required type="number" step="any" value={attempt.score} onChange={event => edit({ score: event.target.value })} /></Field>
                <Field label={`Taken date ${index + 1}`} error={errorFor(`tests.${index}.taken_on`)}><Input type="date" value={attempt.takenOn} onChange={event => edit({ takenOn: event.target.value })} /></Field>
                <Field label={`Note ${index + 1} (optional)`} error={errorFor(`tests.${index}.note`)}><Input value={attempt.note} onChange={event => edit({ note: event.target.value })} /></Field>
              </div>
              <Button variant="ghost" onClick={() => update('tests', draft.tests.filter(row => row.id !== attempt.id))}><Trash2 size={16} aria-hidden="true" />Remove test attempt {index + 1}</Button>
            </fieldset>;
          })}</div>
          <Button variant="secondary" disabled={draft.tests.some(row => !row.score.trim())} onClick={() => update('tests', [...draft.tests, { id: crypto.randomUUID(), scale: 'sat_total_400_1600', score: '', takenOn: '', note: '' }])}><Plus size={16} aria-hidden="true" />Add test score</Button>
        </section>

        <section className="profile-section" aria-label="Budget and aid">
          <SectionHeader title="Budget and aid" description="Share your financial context without having to know all the answers." />
          <div className="form-grid">
            {input('budget', 'Estimated annual budget (USD)', 'financial.annual_budget_usd', { type: 'number', step: 'any', placeholder: 'Annual amount', icon: <DollarSign size={17} /> })}
            <Field label="Do you need financial aid?" error={errorFor('financial.needs_financial_aid')}><Select value={draft.aid} onChange={event => update('aid', event.target.value as ProfileDraft['aid'])}><option value="">Not sure yet</option><option value="yes">Yes</option><option value="no">No</option></Select></Field>
          </div>
        </section>

        <section className="profile-section" aria-label="Location preferences">
          <SectionHeader title="Location preferences" description="Your journey currently covers U.S. bachelor’s programs." />
          <fieldset className="section-fields" aria-describedby={errorFor('preferences') ? 'preferences-error' : undefined}>
            <legend className="sr-only">U.S. state preferences</legend>
            {errorFor('preferences') && <p id="preferences-error" className="field-error">{errorFor('preferences')}</p>}
            <div className="form-grid">
              {input('preferredStates', 'Preferred U.S. states', 'preferences.preferred_states', { placeholder: 'e.g. CA, NY, MA', help: 'Comma-separated two-letter codes.', icon: <MapPin size={17} />, onBlur: () => update('preferredStates', draft.preferredStates.toUpperCase()) })}
              {input('excludedStates', 'Excluded U.S. states', 'preferences.excluded_states', { placeholder: 'e.g. TX, FL', help: 'Leave blank if you have no exclusions.', icon: <MapPin size={17} />, onBlur: () => update('excludedStates', draft.excludedStates.toUpperCase()) })}
            </div>
          </fieldset>
        </section>
      </fieldset>
      <div className="workspace-bottom">
        <p className="caption" role="status" aria-live="polite">{saving ? 'Validating and saving your profile…' : dirty ? 'You have unsaved edits. Save to continue.' : 'Your profile is ready to edit.'}</p>
        <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save and continue'}<ArrowRight size={17} aria-hidden="true" /></Button>
      </div>
    </form>
  </div>;
}
