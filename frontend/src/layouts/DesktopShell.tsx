import { ArrowUpRight, Compass, Fingerprint, ListChecks, ShieldCheck, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useEffect, useState, type ReactNode } from 'react';
import { useJourneySnapshot } from '../pages/useJourney';
import { journeyNavigation } from '../lib/journeyNavigation';
import { JourneyStepper, type JourneyStep } from '../components/JourneyStepper';
import { Badge, Card } from '../components/ui';

const compactShellQuery = '(max-width: 1023px)';

function useCompactShell() {
  const [compact, setCompact] = useState(() => typeof window.matchMedia === 'function' && window.matchMedia(compactShellQuery).matches);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia(compactShellQuery);
    const update = (event: MediaQueryListEvent) => setCompact(event.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return compact;
}

export function DesktopShell({ currentStep, children, navigationLocked = false, contextPanel }: { currentStep: JourneyStep; children: ReactNode; navigationLocked?: boolean; contextPanel?: ReactNode }) {
  const compact = useCompactShell();
  const snapshot = useJourneySnapshot();
  const navigation = journeyNavigation(currentStep, snapshot);
  useEffect(() => {
    document.getElementById('workspace')?.focus({ preventScroll: true });
    document.documentElement.scrollTop = 0;
  }, [currentStep]);
  const guidance = contextPanel ?? <><Card className="journey-card"><span className="context-icon"><Sparkles size={21} aria-hidden="true" /></span><h2 className="section-title">{currentStep === 1 ? "Your Talap profile" : "Your Talap journey"}</h2><p className="caption">{currentStep === 1 ? "What we’ll use:" : "A little clarity at every step."}</p><ol className="context-steps">{(currentStep === 1 ? ['Academic information', 'English test information', 'Intended study direction', 'Budget and aid context', 'U.S. location preferences'] : ['Build your profile', 'Review your diagnostics', 'Explore recommendations', 'Compare evidence', 'Follow your roadmap']).map((text, index) => <li key={text}><span aria-hidden="true">{index + 1}</span>{text}</li>)}</ol><div className="context-note"><ShieldCheck size={18} aria-hidden="true" /><p>{currentStep === 1 ? "Your profile is used to generate your local admissions journey. This development profile is identified by this browser, not by an authenticated account." : "Guidance grounded in evidence. Unknown information stays visible."}</p></div></Card><Card className="context-small"><Badge>THE TALAP APPROACH</Badge><h2 className="card-title">Clarity starts with you.</h2><p className="caption">Your goals, interests, and circumstances give your journey its direction.</p><ArrowUpRight size={21} aria-hidden="true" /></Card></>;
  return <><a className="skip-link" href="#workspace">Skip to workspace</a><header className="site-header"><Link to="/profile" className="wordmark" aria-label="Talap home"><span className="brand-mark" aria-hidden="true"><Compass size={23} /></span>Talap<span className="brand-dot" aria-hidden="true">.</span></Link><span className="header-caption">A clearer path to university</span><div className="header-scope"><span className="scope-dot" />U.S. undergraduate journey</div></header>
    <div className="desktop-layout" data-layout={compact ? 'compact' : 'desktop'}><aside aria-label="About Talap" className="brand-panel"><p className="eyebrow">BIG AMBITIONS. CLEAR NEXT STEPS.</p><p className="hero-title">Your future.<br />A <span>clearer path.</span></p><p className="brand-description">Make sense of your U.S. university journey, one informed decision at a time.</p><ul className="value-list"><li><ShieldCheck aria-hidden="true" /><span>Evidence-based<br />university guidance</span></li><li><Fingerprint aria-hidden="true" /><span>Personalized<br />applicant insights</span></li><li><ListChecks aria-hidden="true" /><span>Step-by-step<br />next actions</span></li></ul><div className="path-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="art-center"><Compass size={42} strokeWidth={1.2} /></div><span className="art-star star-one">✦</span><span className="art-star star-two">✦</span><span className="art-dot dot-one" /><span className="art-dot dot-two" /></div><p className="brand-footnote">Made for international applicants.<br />Built around evidence.</p></aside>
    <main id="workspace" tabIndex={-1} className="workspace" aria-label="Product workspace"><JourneyStepper currentStep={currentStep} {...navigation} navigationLocked={navigationLocked} />{children}</main>
    <aside aria-label="Journey information" className={`context-panel${compact ? ' context-panel--mobile' : ''}`}>{compact ? <details className="mobile-context"><summary>Journey guidance</summary><div className="mobile-context-content">{guidance}</div></details> : guidance}</aside></div><footer className="site-footer"><span>Talap · Your next chapter starts with clarity.</span><span className="desktop-footer-label">Desktop development version</span><span className="mobile-footer-label">Responsive web version</span></footer></>;
}
