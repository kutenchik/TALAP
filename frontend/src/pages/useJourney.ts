import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError } from '../lib/api';
import { InvalidJourneyResponseError, loadJourney } from '../lib/journey';
import { readLocalProfileKey } from '../lib/profiles';
import type { AdmissionJourney } from '../types/journey';

export type JourneyLoadState =
  | { status: 'loading' }
  | { status: 'ready'; journey: AdmissionJourney }
  | { status: 'error'; message: string };

export function useJourney() {
  const navigate = useNavigate();
  const [requestVersion, setRequestVersion] = useState(0);
  const [state, setState] = useState<JourneyLoadState>({ status: 'loading' });

  useEffect(() => {
    const profileKey = readLocalProfileKey();
    if (!profileKey) {
      navigate('/profile', { replace: true });
      return;
    }
    let active = true;
    void loadJourney(profileKey, { refresh: requestVersion > 0 }).then(journey => {
      if (active) setState({ status: 'ready', journey });
    }).catch(error => {
      if (!active) return;
      if (error instanceof ApiError && error.status === 404 && error.envelope?.error.code === 'profile_not_found') {
        navigate('/profile', { replace: true });
        return;
      }
      setState({
        status: 'error',
        message: error instanceof InvalidJourneyResponseError
          ? 'Talap received an unexpected journey response. Please try again.'
          : 'Talap could not load your diagnostic. Please check your connection and try again.',
      });
    });
    return () => { active = false; };
  }, [navigate, requestVersion]);

  const retry = useCallback(() => {
    setState({ status: 'loading' });
    setRequestVersion(version => version + 1);
  }, []);
  return { state, retry };
}
