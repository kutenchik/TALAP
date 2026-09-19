import { useEffect, useState } from 'react';
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import { clearJourneyCache } from '../lib/journey';
import { clearCompareSelection } from '../lib/compareSelection';
import { LOCAL_PROFILE_KEY } from '../lib/profiles';
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
  return <DesktopShell currentStep={2} contextPanel={<DiagnosticsContextPanel state={journey.state} />}>
    <DiagnosticsPage state={journey.state} onRetry={journey.retry} />
  </DesktopShell>;
}

export function App() {
  const navigate = useNavigate();
  useEffect(() => {
    const identityChanged = (event: StorageEvent) => {
      if (event.key !== null && event.key !== LOCAL_PROFILE_KEY) return;
      clearJourneyCache();
      clearCompareSelection();
      navigate('/profile', { replace: true });
    };
    window.addEventListener('storage', identityChanged);
    return () => window.removeEventListener('storage', identityChanged);
  }, [navigate]);
  return <Routes>
    <Route path="/" element={<Navigate to="/profile" replace />} />
    <Route path="/profile" element={<ProfileRoute />} />
    <Route path="/diagnostics" element={<DiagnosticsRoute />} />
    <Route path="/recommendations" element={<RecommendationsPage />} />
    <Route path="/compare" element={<ComparePage />} />
    <Route path="/roadmap" element={<RoadmapPage />} />
    <Route path="*" element={<DesktopShell currentStep={1}><div className="page-content">
      <h1 className="page-title">Page not found</h1><a className="text-link" href="/profile">Return to your profile</a>
    </div></DesktopShell>} />
  </Routes>;
}
