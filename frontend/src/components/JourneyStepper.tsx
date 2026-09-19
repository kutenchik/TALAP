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
export function JourneyStepper({ currentStep, completedSteps = [], availableSteps = [1, 2, 3, 4, 5], navigationLocked = false }: { currentStep: JourneyStep; completedSteps?: readonly JourneyStep[]; availableSteps?: readonly JourneyStep[]; navigationLocked?: boolean }) {
  const currentTitle = journeySteps[currentStep - 1].title;
  return <nav aria-label="Application journey" className="journey-stepper"><p className="mobile-step-summary" data-testid="mobile-step-summary"><span>Step {currentStep} of {journeySteps.length}</span><strong>{currentTitle}</strong></p><ol>{journeySteps.map((step, index) => {
    const number = (index + 1) as JourneyStep;
    const current = number === currentStep;
    const completed = !current && completedSteps.includes(number);
    const disabled = !current && (navigationLocked || !availableSteps.includes(number));
    const reason = navigationLocked ? 'Save your profile edits to continue.' : 'Available after the required profile and journey data load.';
    return <li key={step.path} className={current ? 'step-current' : completed ? 'step-completed' : 'step-future'}><Link to={step.path} aria-current={current ? 'step' : undefined} aria-disabled={disabled || undefined} tabIndex={disabled ? -1 : undefined} title={disabled ? reason : undefined} onClick={event => { if (disabled) event.preventDefault(); }}><span className="step-number" aria-hidden="true">{completed ? <Check size={16} /> : number}</span><span className="step-title">{step.title}</span><span className="step-subtitle">{step.subtitle}</span>{completed && <span className="sr-only">Completed</span>}</Link></li>;
  })}</ol></nav>;
}
