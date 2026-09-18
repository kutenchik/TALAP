import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError } from '../lib/api';
import { emptyDraft, toDraft, toPayload, type ProfileDraft } from '../lib/profileForm';
import { loadLocalProfile, saveProfile } from '../lib/profiles';
import type { ValidationDetail } from '../types/api';

export interface FormProblem { message: string; details: ValidationDetail[] }

export function useProfile() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState(emptyDraft);
  const [key, setKey] = useState('');
  const [loadState, setLoadState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<FormProblem | null>(null);
  const savingLock = useRef(false);
  const saveController = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void loadLocalProfile(controller.signal).then(({ key, profile }) => {
      if (controller.signal.aborted) return;
      setKey(key);
      setDraft(profile ? toDraft(profile) : emptyDraft());
      setLoadState('ready');
    }).catch(() => {
      if (!controller.signal.aborted) setLoadState('error');
    });
    return () => controller.abort();
  }, [loadAttempt]);

  useEffect(() => () => saveController.current?.abort(), []);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  function change(next: ProfileDraft) {
    if (JSON.stringify(next) === JSON.stringify(draft)) return;
    setDraft(next);
    setDirty(true);
  }
  function retryLoad() { setLoadState('loading'); setLoadAttempt(attempt => attempt + 1); }
  function errorFor(path: string) {
    return problem?.details.filter(detail => detail.location.join('.') === path)
      .map(detail => detail.message).join(' ') || undefined;
  }

  async function submit() {
    if (savingLock.current || loadState !== 'ready') return;
    const rows = draft.mode === 'known_major' ? draft.cips : draft.interests;
    if (rows.some(row => !row.value.trim()) || draft.tests.some(row => !row.score.trim())) {
      setProblem({ message: 'Fill in or remove empty study direction and test score rows.', details: [] });
      return;
    }
    savingLock.current = true;
    setSaving(true);
    setProblem(null);
    const controller = new AbortController();
    saveController.current = controller;
    try {
      await saveProfile(toPayload(draft, key), controller.signal);
      if (controller.signal.aborted) return;
      setDirty(false);
      navigate('/diagnostics');
    } catch (error) {
      if (controller.signal.aborted) return;
      const validation = error instanceof ApiError && error.status === 400 &&
        error.envelope?.error.code === 'validation_error';
      setProblem({
        message: validation ? 'Please review the highlighted information.' :
          error instanceof ApiError && error.status === 403 ?
            'Your session token was not accepted. Try saving again to get a new token.' :
            'Could not save your profile. Check the connection to Django and try again; a new session token will be requested.',
        details: validation && error instanceof ApiError ? error.envelope?.error.details ?? [] : [],
      });
    } finally {
      savingLock.current = false;
      if (!controller.signal.aborted) setSaving(false);
    }
  }

  return { draft, change, loadState, retryLoad, dirty, saving, problem, errorFor, submit };
}
