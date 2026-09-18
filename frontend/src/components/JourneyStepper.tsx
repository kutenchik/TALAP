import { Check } from 'lucide-react';
import { Link } from 'react-router-dom';

export const journeySteps = [
  { title: 'Profile', subtitle: 'Tell us about yourself', path: '/profile' },
  { title: 'Diagnostics', subtitle: 'Review your profile', path: '/diagnostics' },
  { title: 'Recommendations', subtitle: 'Explore universities', path: '/recommendations' },
  { title: 'Compare', subtitle: 'Compare evidence', path: '/compare' },
  { title: 'Roadmap', subtitle: 'Plan next actions', path: '/roadmap' },
] as const;
export type JourneyStep = 1 | 2 | 3 | 4 | 5;

// Completion requires explicit evidence; visiting a later route is not completion.
export function JourneyStepper({ currentStep, completedSteps = [], navigationLocked = false }: { currentStep: JourneyStep; completedSteps?: readonly JourneyStep[]; navigationLocked?: boolean }) {
  return <nav aria-label="Application journey" className="journey-stepper"><ol>{journeySteps.map((step, index) => {
    const number = (index + 1) as JourneyStep;
    const current = number === currentStep;
    const completed = !current && completedSteps.includes(number);
    const disabled = navigationLocked && !current;
    return <li key={step.path} className={current ? 'step-current' : completed ? 'step-completed' : 'step-future'}><Link to={step.path} aria-current={current ? 'step' : undefined} aria-disabled={disabled || undefined} onClick={event => { if (disabled) event.preventDefault(); }}><span className="step-number" aria-hidden="true">{completed ? <Check size={16} /> : number}</span><span className="step-title">{step.title}</span><span className="step-subtitle">{step.subtitle}</span>{completed && <span className="sr-only">Completed</span>}</Link></li>;
  })}</ol></nav>;
}
