import { useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { journeySteps, type JourneyStep } from '../components/JourneyStepper';
import { DesktopShell } from '../layouts/DesktopShell';
import { ProfilePage } from '../pages/ProfilePage';
import { PlaceholderPage } from '../pages/PlaceholderPage';
import { DiagnosticsContextPanel, DiagnosticsPage } from '../pages/DiagnosticsPage';
import { useJourney } from '../pages/useJourney';
import { RecommendationsPage } from '../pages/RecommendationsPage';

function ProfileRoute() {
  const [navigationLocked, setNavigationLocked] = useState(false);
  return <DesktopShell currentStep={1} navigationLocked={navigationLocked}>
    <ProfilePage onNavigationLock={setNavigationLocked} />
  </DesktopShell>;
}

function DiagnosticsRoute() {
  const journey = useJourney();
  return <DesktopShell currentStep={2} completedSteps={[1]} contextPanel={<DiagnosticsContextPanel state={journey.state} />}>
    <DiagnosticsPage state={journey.state} onRetry={journey.retry} />
  </DesktopShell>;
}

export function App() {
  return <Routes>
    <Route path="/" element={<Navigate to="/profile" replace />} />
    <Route path="/profile" element={<ProfileRoute />} />
    <Route path="/diagnostics" element={<DiagnosticsRoute />} />
    <Route path="/recommendations" element={<RecommendationsPage />} />
    {journeySteps.slice(3).map((step, index) => <Route key={step.path} path={step.path}
      element={<DesktopShell currentStep={(index + 4) as JourneyStep}><PlaceholderPage title={step.title} /></DesktopShell>} />)}
    <Route path="*" element={<DesktopShell currentStep={1}><div className="page-content">
      <h2 className="page-title">Page not found</h2><a className="text-link" href="/profile">Return to your profile</a>
    </div></DesktopShell>} />
  </Routes>;
}
