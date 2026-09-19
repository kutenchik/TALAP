import { useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { DesktopShell } from '../layouts/DesktopShell';
import { ProfilePage } from '../pages/ProfilePage';
import { DiagnosticsContextPanel, DiagnosticsPage } from '../pages/DiagnosticsPage';
import { useJourney } from '../pages/useJourney';
import { RecommendationsPage } from '../pages/RecommendationsPage';
import { ComparePage } from '../pages/ComparePage';
import { RoadmapPage } from '../pages/RoadmapPage';

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
    <Route path="/compare" element={<ComparePage />} />
    <Route path="/roadmap" element={<RoadmapPage />} />
    <Route path="*" element={<DesktopShell currentStep={1}><div className="page-content">
      <h2 className="page-title">Page not found</h2><a className="text-link" href="/profile">Return to your profile</a>
    </div></DesktopShell>} />
  </Routes>;
}
