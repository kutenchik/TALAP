import { cloneElement, useId, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactElement, type ReactNode, type SelectHTMLAttributes } from 'react';
import { AlertCircle, Inbox, LoaderCircle } from 'lucide-react';

export function Button({ variant = 'primary', className = '', type = 'button', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' }) {
  return <button type={type} className={`button button--${variant} ${className}`} {...props} />;
}
export function Card({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`card ${className}`} {...props} />;
}
export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
}
export function Input({ icon, className = '', ...props }: InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }) {
  return <div className="control-wrap">{icon && <span className="control-icon" aria-hidden="true">{icon}</span>}<input className={`control ${icon ? 'control--icon' : ''} ${className}`} {...props} /></div>;
}
export function Select({ className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={`control ${className}`} {...props} />;
}
type FieldControl = { id?: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean };
export function Field({ label, help, error, children }: { label: string; help?: string; error?: string; children: ReactElement<FieldControl> }) {
  const generatedId = useId();
  const id = children.props.id ?? generatedId;
  const description = [children.props['aria-describedby'], help && `${id}-help`, error && `${id}-error`].filter(Boolean).join(' ') || undefined;
  return <div className="field"><label htmlFor={id}>{label}</label>{cloneElement(children, { id, 'aria-describedby': description, 'aria-invalid': error ? true : children.props['aria-invalid'] })}{help && <p id={`${id}-help`} className="caption">{help}</p>}{error && <p id={`${id}-error`} className="field-error">{error}</p>}</div>;
}
export function SectionHeader({ title, description }: { title: string; description?: string }) {
  return <div className="section-header"><h2 className="section-title">{title}</h2>{description && <p className="caption">{description}</p>}</div>;
}
const statusLabels = { unavailable: 'Unavailable', verification: 'Needs verification', partial: 'Partial evidence', unevaluated: 'Not evaluated' } as const;
export function StatusPill({ status }: { status: keyof typeof statusLabels }) {
  return <span className={`status-pill status-pill--${status}`}>{statusLabels[status]}</span>;
}
export function LoadingState({ message = 'Loading your workspace…' }: { message?: string }) {
  return <div className="feedback-state" role="status"><LoaderCircle aria-hidden="true" /><p>{message}</p></div>;
}
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="feedback-state" role="alert"><AlertCircle aria-hidden="true" /><h2 className="section-title">Something went wrong</h2><p>{message}</p>{onRetry && <Button variant="secondary" onClick={onRetry}>Try again</Button>}</div>;
}
export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="feedback-state"><Inbox aria-hidden="true" /><h2 className="section-title">{title}</h2><p>{description}</p></div>;
}
