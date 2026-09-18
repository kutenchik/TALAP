import { useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { journeySteps, type JourneyStep } from '../components/JourneyStepper';
import { DesktopShell } from '../layouts/DesktopShell';
import { ProfilePage } from '../pages/ProfilePage';
import { PlaceholderPage } from '../pages/PlaceholderPage';

function ProfileRoute() {
  const [navigationLocked, setNavigationLocked] = useState(false);
  return <DesktopShell currentStep={1} navigationLocked={navigationLocked}>
    <ProfilePage onNavigationLock={setNavigationLocked} />
  </DesktopShell>;
}

export function App() {
  return <Routes>
    <Route path="/" element={<Navigate to="/profile" replace />} />
    <Route path="/profile" element={<ProfileRoute />} />
    {journeySteps.slice(1).map((step, index) => <Route key={step.path} path={step.path}
      element={<DesktopShell currentStep={(index + 2) as JourneyStep}><PlaceholderPage title={step.title} /></DesktopShell>} />)}
    <Route path="*" element={<DesktopShell currentStep={1}><div className="page-content">
      <h2 className="page-title">Page not found</h2><a className="text-link" href="/profile">Return to your profile</a>
    </div></DesktopShell>} />
  </Routes>;
}
