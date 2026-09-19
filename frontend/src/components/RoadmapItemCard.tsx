import {
  BookOpen,
  CircleDollarSign,
  GraduationCap,
  Languages,
  Search,
  UserRound,
  type LucideIcon,
} from 'lucide-react';
import {
  roadmapActionLabels,
  roadmapCategoryLabels,
  roadmapPriorityLabels,
  roadmapReasonLabels,
} from '../lib/roadmapLabels';
import type { RoadmapCategory, RoadmapItem } from '../types/journey';

const categoryIcons: Record<RoadmapCategory, LucideIcon> = {
  profile: UserRound,
  academics: GraduationCap,
  english: Languages,
  program: BookOpen,
  financial: CircleDollarSign,
  research: Search,
};

export function RoadmapItemCard({ item, universityNames }: { item: RoadmapItem; universityNames: string[] }) {
  const CategoryIcon = categoryIcons[item.category];
  return <article className={`roadmap-item roadmap-item--${item.priority}`} data-priority={item.priority} data-category={item.category}>
    <div className="roadmap-item-heading"><span className="roadmap-category-icon" aria-hidden="true"><CategoryIcon size={18} /></span><div>
      <div className="roadmap-item-meta"><span className={`roadmap-priority roadmap-priority--${item.priority}`}>{roadmapPriorityLabels[item.priority]}</span><span className="roadmap-category"><CategoryIcon size={12} aria-hidden="true" />{roadmapCategoryLabels[item.category]}</span></div>
      <h4>{roadmapActionLabels[item.action_code]}</h4>
    </div></div>
    {item.reason_codes.length > 0 && <div className="roadmap-reasons"><h5>Why this action appears</h5><ul>{item.reason_codes.map(reason => <li key={reason}>{roadmapReasonLabels[reason]}</li>)}</ul></div>}
    {universityNames.length > 0 && <div className="roadmap-universities"><h5>Related universities</h5><ul>{universityNames.map((name, index) => <li key={`${item.institution_unitids[index]}-${name}`}>{name}</li>)}</ul></div>}
  </article>;
}
