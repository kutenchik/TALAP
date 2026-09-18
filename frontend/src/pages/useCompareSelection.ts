import { useEffect, useState } from 'react';
import type { UniversityRecommendation } from '../types/journey';

export const COMPARE_STORAGE_KEY = 'talap.compareUnitids';
export function eligibleUnitids(items: UniversityRecommendation[]) {
  return items.filter(item => item.recommendation_state !== 'excluded_by_applicant').map(item => item.institution.ipeds_unitid);
}
export function useCompareSelection(items: UniversityRecommendation[]) {
  const eligible = eligibleUnitids(items);
  const [selected, setSelected] = useState<number[]>(() => {
    try {
      const stored: unknown = JSON.parse(sessionStorage.getItem(COMPARE_STORAGE_KEY) ?? '[]');
      return Array.isArray(stored) ? [...new Set(stored.filter((id): id is number => typeof id === 'number' && eligible.includes(id)))].slice(0, 3) : [];
    } catch { return []; }
  });
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  useEffect(() => {
    try { sessionStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(selected)); }
    catch { /* The selection event reports storage failure before navigation is enabled. */ }
  }, [selected]);
  function toggle(id: number) {
    if (!eligible.includes(id)) return;
    const next = selected.includes(id) ? selected.filter(value => value !== id) : selected.length < 3 ? [...selected, id] : selected;
    try {
      sessionStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(next));
      setStorageUnavailable(false);
    } catch { setStorageUnavailable(true); }
    setSelected(next);
  }
  return { selected, toggle, storageUnavailable };
}
