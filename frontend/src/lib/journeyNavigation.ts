import type { JourneyStep } from '../components/JourneyStepper';
import type { JourneySnapshot } from './journey';

export function journeyNavigation(currentStep: JourneyStep, snapshot: JourneySnapshot) {
  const completedSteps: JourneyStep[] = [];
  const availableSteps: JourneyStep[] = [1];
  if (snapshot.savedProfile) { completedSteps.push(1); availableSteps.push(2); }
  if (snapshot.state.status === 'ready') {
    const journey = snapshot.state.journey;
    completedSteps.push(2);
    availableSteps.push(5);
    if (journey.journey_state === 'recommendations_ready') {
      availableSteps.push(3);
      if (journey.recommendations?.recommendations.length) {
        availableSteps.push(4);
        if (currentStep > 3) completedSteps.push(3);
      }
    }
  }
  // Compare is an optional local interaction, not a backend completion milestone.
  return { completedSteps, availableSteps };
}
