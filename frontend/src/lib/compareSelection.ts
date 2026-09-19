import type { UniversityRecommendation } from '../types/journey';

export const COMPARE_STORAGE_KEY = 'talap.compareUnitids';
export const COMPARE_PROFILE_KEY = 'talap.compareProfileKey';
let invalidated = false;

export function eligibleUnitids(items: UniversityRecommendation[]) {
  return items.filter(item => item.recommendation_state !== 'excluded_by_applicant').map(item => item.institution.ipeds_unitid);
}
export function cleanSelection(value: unknown, items: UniversityRecommendation[]): number[] {
  const eligible = eligibleUnitids(items);
  return Array.isArray(value) ? [...new Set(value.filter((id): id is number => typeof id === 'number' && eligible.includes(id)))].slice(0, 3) : [];
}
export function readCompareSelection(profileKey: string | null, items: UniversityRecommendation[]) {
  if (!profileKey || invalidated) return [];
  try {
    const owner = sessionStorage.getItem(COMPARE_PROFILE_KEY);
    if (owner && owner !== profileKey) return [];
    return cleanSelection(JSON.parse(sessionStorage.getItem(COMPARE_STORAGE_KEY) ?? '[]'), items);
  } catch { return []; }
}
export function writeCompareSelection(profileKey: string | null, selected: number[]) {
  // Write the IDs first so a failed owner write cannot attach old IDs to a new profile.
  sessionStorage.setItem(COMPARE_STORAGE_KEY, JSON.stringify(selected));
  sessionStorage.setItem(COMPARE_PROFILE_KEY, profileKey ?? '');
  invalidated = false;
}
export function clearCompareSelection() {
  // Keep the in-memory guard if browser storage becomes temporarily unavailable.
  invalidated = true;
  try {
    sessionStorage.removeItem(COMPARE_STORAGE_KEY);
    sessionStorage.removeItem(COMPARE_PROFILE_KEY);
    invalidated = false;
  } catch { /* Old IDs must not return if storage later becomes available. */ }
}
