import { Link } from 'react-router-dom';
import { Badge, EmptyState, StatusPill } from '../components/ui';

export function PlaceholderPage({ title }: { title: string }) {
  return <div className="page-content"><div className="page-heading"><Badge>JOURNEY PREVIEW</Badge><h2 className="page-title">{title}</h2><p>This workspace will be connected in a later frontend task.</p></div><EmptyState title="Coming in next frontend task" description="Your journey will appear here once this step is implemented and connected to verified backend data." /><div className="placeholder-footer"><StatusPill status="unevaluated" /><Link className="text-link" to="/profile">Back to your profile</Link></div></div>;
}
