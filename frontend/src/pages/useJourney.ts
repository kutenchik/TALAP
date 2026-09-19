import { useCallback, useEffect, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router-dom';
import { getJourneySnapshot, loadJourney, subscribeJourney, type JourneyLoadState } from '../lib/journey';
import { readLocalProfileKey } from '../lib/profiles';
import { clearCompareSelection } from '../lib/compareSelection';

export type { JourneyLoadState } from '../lib/journey';

// The shell observes the same service as the pages without starting extra requests.
export function useJourneySnapshot() {
  let profileKey: string | null = null;
  let storageUnavailable = false;
  try { profileKey = readLocalProfileKey(); } catch { storageUnavailable = true; }
  const snapshot = useSyncExternalStore(subscribeJourney, () => getJourneySnapshot(profileKey));
  return { ...snapshot, profileKey, storageUnavailable };
}

export function useJourney() {
  const navigate = useNavigate();
  const { state, started, profileKey, storageUnavailable } = useJourneySnapshot();
  const profileMissing = state.status === 'error' && state.profileMissing;
  useEffect(() => {
    if (storageUnavailable) return;
    if (!profileKey || profileMissing) {
      clearCompareSelection();
      navigate('/profile', { replace: true });
    } else if (!started) {
      void loadJourney(profileKey).catch(() => { /* The shared service publishes a safe error. */ });
    }
  }, [navigate, profileKey, profileMissing, storageUnavailable, started]);

  const retry = useCallback(() => {
    if (storageUnavailable) { navigate('/profile', { replace: true }); return; }
    if (profileKey) void loadJourney(profileKey, { refresh: true }).catch(() => { /* Published by the service. */ });
  }, [navigate, profileKey, storageUnavailable]);
  const visibleState: JourneyLoadState = storageUnavailable
    ? { status: 'error', message: 'Talap cannot access your local profile identity. Allow browser storage, then try again.' }
    : state;
  return { state: visibleState, retry };
}
