import { useEffect, useState } from 'react';
import type { UniversityRecommendation } from '../types/journey';
import { cleanSelection, eligibleUnitids, readCompareSelection, writeCompareSelection } from '../lib/compareSelection';
import { readLocalProfileKey } from '../lib/profiles';

export { COMPARE_STORAGE_KEY, eligibleUnitids } from '../lib/compareSelection';
export function useCompareSelection(items: UniversityRecommendation[]) {
  const eligible = eligibleUnitids(items);
  const profileKey = readLocalProfileKey();
  const [selection, setSelection] = useState(() => ({ profileKey, ids: readCompareSelection(profileKey, items) }));
  const selected = cleanSelection(selection.profileKey === profileKey ? selection.ids : [], items);
  const serialized = JSON.stringify(selected);
  const [storageUnavailable, setStorageUnavailable] = useState(false);
  useEffect(() => {
    try { writeCompareSelection(profileKey, JSON.parse(serialized)); }
    catch { /* The selection event reports storage failure before navigation is enabled. */ }
  }, [profileKey, serialized]);
  function toggle(id: number) {
    if (!eligible.includes(id)) return;
    const next = selected.includes(id) ? selected.filter(value => value !== id) : selected.length < 3 ? [...selected, id] : selected;
    try {
      writeCompareSelection(profileKey, next);
      setStorageUnavailable(false);
    } catch { setStorageUnavailable(true); }
    setSelection({ profileKey, ids: next });
  }
  return { selected, toggle, storageUnavailable };
}
