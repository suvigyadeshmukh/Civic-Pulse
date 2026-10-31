import { useEffect, useState } from 'react';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import {
  ArrowRight,
  BadgeCheck,
  Bot,
  CheckCircle2,
  CircleDashed,
  FileText,
  Landmark,
  LayoutDashboard,
  LogIn,
  MapPin,
  Menu,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import clsx from 'clsx';

type Accent = 'teal' | 'amber' | 'sky' | 'violet' | 'rose';

interface Pillar {
  path: string;
  navLabel: string;
  title: string;
  summary: string;
  icon: LucideIcon;
  accent: Accent;
  capabilities: string[];
}

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const PILLARS: Pillar[] = [
  {
    path: '/policies',
    navLabel: 'Policies',
    title: 'Policy Studio',
    summary:
      'Turn dense gazettes into plain-language guidance with clause citations, eligibility matching, and regional voice explainers.',
    icon: FileText,
    accent: 'sky',
    capabilities: [
      'OCR + PDF ingestion',
      'Personalised eligibility matrix',
      'Hindi, Tamil, Marathi, Telugu & English audio',
    ],
  },
  {
    path: '/grievances',
    navLabel: 'Grievances',
    title: 'Grievance Portal',
    summary:
      'Report civic hazards with a photo, a browser voice note, and GPS — then follow an accountable SLA timeline to resolution.',
    icon: MapPin,
    accent: 'amber',
    capabilities: [
      'Multimodal intake',
      '50 m PostGIS duplicate detection',
      'Severity-based SLA routing',
    ],
  },
  {
    path: '/agent',
    navLabel: 'Agent',
    title: 'Bureaucracy Agent',
    summary:
      'Let a supervised Playwright worker complete legacy portal forms from your encrypted vault, with live streaming and OTP hand-off.',
    icon: Bot,
    accent: 'violet',
    capabilities: [
      'AES-256-GCM citizen vault',
      'Live browser screenshot stream',
      'Human-in-the-loop OTP relay',
    ],
  },
  {
    path: '/fact-check',
    navLabel: 'Fact-Check',
    title: 'Fact Verification',
    summary:
      'Audit viral claims and synthetic media through C2PA credentials, forensic heatmaps, deepfake scoring, and trusted registries.',
    icon: ShieldCheck,
    accent: 'rose',
    capabilities: [
      'C2PA provenance inspection',
      'ELA + ViT media forensics',
      'Registry-backed credibility score',
    ],
  },
];

const ACCOUNTABILITY: Pillar = {
  path: '/accountability',
  navLabel: 'Accountability',
  title: 'Public Accountability',
  summary:
    'A login-free civic window into live grievance hotspots and department SLA compliance, built for public trust.',
  icon: BadgeCheck,
  accent: 'teal',
  capabilities: [
    'Leaflet geospatial heatmap',
    'Department SLA scorecards',
    'Open KPI tiles & resolution proof',
  ],
};

const MODULES: Pillar[] = [...PILLARS, ACCOUNTABILITY];

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  ...MODULES.map((pillar) => ({
    to: pillar.path,
    label: pillar.navLabel,
    icon: pillar.icon,
  })),
];

const ACCENT_STYLES: Record<
  Accent,
  { icon: string; chip: string; glow: string }
> = {
  teal: {
    icon: 'bg-teal-600 text-white',
    chip: 'border-teal-200 bg-teal-50 text-teal-800',
    glow: 'bg-teal-400/20',
  },
  amber: {
    icon: 'bg-amber-500 text-white',
    chip: 'border-amber-200 bg-amber-50 text-amber-800',
    glow: 'bg-amber-400/20',
  },
  sky: {
    icon: 'bg-sky-600 text-white',
    chip: 'border-sky-200 bg-sky-50 text-sky-800',
    glow: 'bg-sky-400/20',
  },
  violet: {
    icon: 'bg-violet-600 text-white',
    chip: 'border-violet-200 bg-violet-50 text-violet-800',
    glow: 'bg-violet-400/20',
  },
  rose: {
    icon: 'bg-rose-600 text-white',
    chip: 'border-rose-200 bg-rose-50 text-rose-800',
    glow: 'bg-rose-400/20',
  },
};

type ReadinessState = 'ready' | 'scaffolded' | 'queued';

const READINESS: Array<{ label: string; state: ReadinessState }> = [
  { label: 'React 18 + Vite 5 + TypeScript strict', state: 'ready' },
  { label: 'Tailwind design tokens & base styles', state: 'ready' },
  { label: 'Router, app shell & route map', state: 'ready' },
  { label: 'Axios, Zustand, RHF/Zod modules', state: 'scaffolded' },
  { label: 'Four civic domain modules', state: 'queued' },
];

const READINESS_LABEL: Record<ReadinessState, string> = {
  ready: 'Ready',
  scaffolded: 'Scaffolded',
  queued: 'Queued',
};

const READINESS_COLOR: Record<ReadinessState, string> = {
  ready: 'text-emerald-700',
  scaffolded: 'text-amber-700',
  queued: 'text-slate-500',
};

const LOCKED_STACK = [
  'React 18',
  'Vite 5',
  'TypeScript 5',
  'Tailwind 3',
  'React Router 6',
  'Axios',
  'Zustand',
  'RHF + Zod',
  'Leaflet',
  'Recharts',
];

function NavItemLink({ item }: { item: NavItem }) {
  const Icon = item.icon;

  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        clsx(
          'inline-flex items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] font-semibold transition-colors',
          isActive
            ? 'bg-civic-ink text-white shadow-sm'
            : 'text-slate-600 hover:bg-white hover:text-civic-ink',
        )
      }
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {item.label}
    </NavLink>
  );
}

function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-civic-parchment/90 backdrop-blur-xl">
      <div className="container-page flex h-16 items-center justify-between gap-4">
        <NavLink to="/" className="group flex shrink-0 items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-civic-ink text-civic-tealLight shadow-soft transition-colors group-hover:bg-civic-inkLight">
            <Landmark className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="leading-tight">
            <span className="block text-base font-extrabold tracking-tight text-civic-ink">
              Civic Pulse
            </span>
            <span className="hidden text-[10px] font-medium uppercase tracking-[0.14em] text-slate-500 sm:block">
              Digital governance
            </span>
          </span>
        </NavLink>

        <nav
          aria-label="Primary"
          className="hidden items-center gap-1 lg:flex"
        >
          {NAV_ITEMS.map((item) => (
            <NavItemLink key={item.to} item={item} />
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <span className="badge hidden xl:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            F1 shell online
          </span>
          <NavLink
            to="/login"
            className="hidden items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-[13px] font-semibold text-civic-ink transition-colors hover:border-civic-teal/40 hover:bg-civic-mist sm:inline-flex"
          >
            <LogIn className="h-4 w-4" aria-hidden="true" />
            Sign in
          </NavLink>
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="grid h-10 w-10 place-items-center rounded-lg border border-slate-300 bg-white text-civic-ink transition-colors hover:bg-civic-mist lg:hidden"
            aria-expanded={menuOpen}
            aria-controls="mobile-navigation"
            aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
          >
            {menuOpen ? (
              <X className="h-5 w-5" aria-hidden="true" />
            ) : (
              <Menu className="h-5 w-5" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav
          id="mobile-navigation"
          aria-label="Mobile"
          onClick={() => setMenuOpen(false)}
          className="border-t border-slate-200/80 bg-civic-parchment px-4 py-3 lg:hidden"
        >
          <div className="grid gap-1 sm:grid-cols-2">
            {NAV_ITEMS.map((item) => (
              <NavItemLink key={item.to} item={item} />
            ))}
            <NavLink
              to="/login"
              onClick={() => setMenuOpen(false)}
              className="inline-flex items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] font-semibold text-slate-600 hover:bg-white hover:text-civic-ink sm:hidden"
            >
              <LogIn className="h-4 w-4" aria-hidden="true" />
              Sign in
            </NavLink>
          </div>
        </nav>
      )}
    </header>
  );
}

function ReadinessPanel() {
  return (
    <aside className="surface relative overflow-hidden p-6 sm:p-7">
      <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-civic-tealLight/15 blur-2xl" />
      <div className="relative flex items-start justify-between gap-4">
        <div>
          <p className="label-caps">Build status</p>
          <h2 className="mt-1 text-lg font-bold tracking-tight">
            Platform readiness
          </h2>
        </div>
        <span className="badge border-civic-teal/20 bg-civic-teal/5 text-civic-teal">
          <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          Step F1
        </span>
      </div>

      <ul className="relative mt-6 space-y-3">
        {READINESS.map((item) => (
          <li key={item.label} className="flex items-center gap-2.5 text-sm">
            {item.state === 'ready' ? (
              <CheckCircle2
                className="h-4 w-4 shrink-0 text-emerald-600"
                aria-hidden="true"
              />
            ) : (
              <CircleDashed
                className="h-4 w-4 shrink-0 text-slate-400"
                aria-hidden="true"
              />
            )}
            <span className="text-slate-700">{item.label}</span>
            <span
              className={clsx(
                'ml-auto text-[10px] font-bold uppercase tracking-wider',
                READINESS_COLOR[item.state],
              )}
            >
              {READINESS_LABEL[item.state]}
            </span>
          </li>
        ))}
      </ul>

      <div className="relative mt-6 rounded-xl border border-civic-teal/20 bg-civic-teal/5 p-4">
        <p className="text-sm font-semibold text-civic-ink">
          Mock-first development
        </p>
        <p className="mt-1 text-xs leading-relaxed text-slate-600">
          The API layer defaults to deterministic contract fixtures via{' '}
          <code className="rounded bg-white px-1 py-0.5 font-mono text-[11px] text-civic-teal">
            VITE_USE_API_MOCKS=true
          </code>
          , so every screen can be built before backend merge.
        </p>
      </div>
    </aside>
  );
}

function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="max-w-2xl">
      <p className="label-caps">{eyebrow}</p>
      <h2 className="mt-2 text-balance text-2xl font-extrabold tracking-tight text-civic-ink sm:text-3xl">
        {title}
      </h2>
      <p className="mt-3 text-sm leading-relaxed text-slate-600 sm:text-base">
        {description}
      </p>
    </div>
  );
}

function PillarCard({ pillar }: { pillar: Pillar }) {
  const Icon = pillar.icon;
  const accent = ACCENT_STYLES[pillar.accent];

  return (
    <NavLink
      to={pillar.path}
      className="group surface relative flex flex-col overflow-hidden p-6 transition duration-200 hover:-translate-y-0.5 hover:shadow-lift"
    >
      <div
        className={clsx(
          'pointer-events-none absolute -right-12 -top-12 h-36 w-36 rounded-full blur-2xl transition-opacity group-hover:opacity-100',
          accent.glow,
          'opacity-50',
        )}
      />
      <div className="relative flex items-start justify-between gap-4">
        <span
          className={clsx(
            'grid h-12 w-12 place-items-center rounded-xl shadow-sm',
            accent.icon,
          )}
        >
          <Icon className="h-6 w-6" aria-hidden="true" />
        </span>
        <ArrowRight
          className="h-5 w-5 text-slate-300 transition-transform group-hover:translate-x-1 group-hover:text-civic-ink"
          aria-hidden="true"
        />
      </div>

      <h3 className="relative mt-4 text-lg font-bold tracking-tight text-civic-ink">
        {pillar.title}
      </h3>
      <p className="relative mt-2 text-sm leading-relaxed text-slate-600">
        {pillar.summary}
      </p>

      <div className="relative mt-auto flex flex-wrap gap-1.5 pt-5">
        {pillar.capabilities.map((capability) => (
          <span
            key={capability}
            className={clsx(
              'rounded-md border px-2 py-1 text-[10px] font-semibold',
              accent.chip,
            )}
          >
            {capability}
          </span>
        ))}
      </div>
    </NavLink>
  );
}

function OverviewPage() {
  return (
    <div className="animate-fade-up">
      <section className="relative overflow-hidden border-b border-slate-200/70">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-grid-civic [mask-image:radial-gradient(ellipse_at_top,black,transparent_72%)]"
        />
        <div className="container-page relative grid gap-12 py-16 lg:grid-cols-[1.15fr_0.85fr] lg:items-center lg:py-24">
          <div>
            <span className="badge border-civic-teal/20 bg-white text-civic-teal">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              Civic Pulse platform shell
            </span>
            <h1 className="mt-6 max-w-3xl text-balance text-4xl font-extrabold leading-[1.05] tracking-tight text-civic-ink sm:text-5xl lg:text-6xl">
              Public services that are{' '}
              <span className="text-civic-teal">legible</span>, accountable, and
              automatic.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-relaxed text-slate-600 sm:text-lg">
              One citizen-first portal for multilingual policy explainers,
              geospatial grievance triage, autonomous bureaucracy agents, and
              forensic fact-checking.
            </p>

            <div className="mt-8 flex flex-wrap gap-3">
              <NavLink to="/accountability" className="btn-primary">
                Open public dashboard
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </NavLink>
              <NavLink to="/policies" className="btn-secondary">
                Explore policy studio
              </NavLink>
            </div>

            <dl className="mt-10 grid max-w-xl grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-4">
              {[
                { value: '4', label: 'Civic pillars' },
                { value: '50 m', label: 'Dedup radius' },
                { value: '5', label: 'Indian languages' },
                { value: '24/7', label: 'Public access' },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="border-l border-slate-300/80 pl-4"
                >
                  <dt className="sr-only">{stat.label}</dt>
                  <dd className="text-xl font-extrabold tracking-tight text-civic-ink">
                    {stat.value}
                  </dd>
                  <dd className="mt-0.5 text-[11px] font-medium text-slate-500">
                    {stat.label}
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          <ReadinessPanel />
        </div>
      </section>

      <section className="container-page py-16 sm:py-20">
        <SectionHeading
          eyebrow="Platform modules"
          title="Four pillars, one citizen experience"
          description="Every domain shares the same shell, design language, and API contract. Routes are wired now; each module UI lands in its dedicated build step."
        />

        <div className="mt-10 grid gap-5 md:grid-cols-2">
          {PILLARS.map((pillar) => (
            <PillarCard key={pillar.path} pillar={pillar} />
          ))}
        </div>

        <div className="mt-5">
          <NavLink
            to={ACCOUNTABILITY.path}
            className="group flex flex-col gap-5 rounded-2xl border border-civic-ink/10 bg-civic-ink p-6 text-white shadow-soft transition-colors hover:bg-civic-inkLight sm:flex-row sm:items-center sm:justify-between sm:p-7"
          >
            <div className="flex items-start gap-4">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-white/10 text-civic-tealLight ring-1 ring-white/15">
                <BadgeCheck className="h-6 w-6" aria-hidden="true" />
              </span>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-civic-tealLight">
                  Public by default
                </p>
                <h3 className="mt-1 text-lg font-bold tracking-tight">
                  {ACCOUNTABILITY.title}
                </h3>
                <p className="mt-1 max-w-2xl text-sm leading-relaxed text-slate-300">
                  {ACCOUNTABILITY.summary}
                </p>
              </div>
            </div>
            <span className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-civic-ink">
              View dashboard
              <ArrowRight
                className="h-4 w-4 transition-transform group-hover:translate-x-1"
                aria-hidden="true"
              />
            </span>
          </NavLink>
        </div>
      </section>

      <section className="container-page pb-20">
        <div className="surface flex flex-col gap-5 p-6 sm:p-7">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="label-caps">Architecture</p>
              <h2 className="mt-1 text-lg font-bold tracking-tight">
                Locked frontend stack
              </h2>
            </div>
            <span className="badge border-emerald-200 bg-emerald-50 text-emerald-700">
              <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
              No Next.js · No TanStack Query
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            {LOCKED_STACK.map((item) => (
              <span
                key={item}
                className="rounded-lg border border-slate-200 bg-civic-mist/60 px-3 py-1.5 text-xs font-semibold text-slate-700"
              >
                {item}
              </span>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function ModulePlaceholder({ pillar }: { pillar: Pillar }) {
  const Icon = pillar.icon;
  const accent = ACCENT_STYLES[pillar.accent];
  const next =
    pillar.path === '/accountability'
      ? { to: '/grievances', label: 'Open grievance portal' }
      : { to: '/accountability', label: 'Open public dashboard' };

  return (
    <section className="container-page animate-fade-up py-14 sm:py-20">
      <div className="mx-auto max-w-4xl">
        <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-slate-500">
          <NavLink to="/" className="hover:text-civic-ink">
            Overview
          </NavLink>
          <span aria-hidden="true">/</span>
          <span className="text-civic-ink">{pillar.navLabel}</span>
          <span className="badge ml-auto border-emerald-200 bg-emerald-50 text-emerald-700">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Route wired
          </span>
        </div>

        <div className="surface mt-5 overflow-hidden">
          <div className="relative border-b border-slate-200/80 p-6 sm:p-9">
            <div
              className={clsx(
                'pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full blur-3xl',
                accent.glow,
              )}
            />
            <div className="relative flex items-start gap-4">
              <span
                className={clsx(
                  'grid h-14 w-14 shrink-0 place-items-center rounded-2xl shadow-sm',
                  accent.icon,
                )}
              >
                <Icon className="h-7 w-7" aria-hidden="true" />
              </span>
              <div>
                <p className="label-caps">Module scaffold</p>
                <h1 className="mt-1 text-balance text-2xl font-extrabold tracking-tight text-civic-ink sm:text-3xl">
                  {pillar.title}
                </h1>
              </div>
            </div>
            <p className="relative mt-5 max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base">
              {pillar.summary}
            </p>
          </div>

          <div className="grid gap-8 p-6 sm:p-9 lg:grid-cols-[1.2fr_0.8fr]">
            <div>
              <h2 className="text-sm font-bold text-civic-ink">
                Capabilities queued for this module
              </h2>
              <ul className="mt-4 space-y-3">
                {pillar.capabilities.map((capability) => (
                  <li
                    key={capability}
                    className="flex items-start gap-3 text-sm text-slate-600"
                  >
                    <CheckCircle2
                      className="mt-0.5 h-4 w-4 shrink-0 text-civic-teal"
                      aria-hidden="true"
                    />
                    {capability}
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-xl border border-dashed border-slate-300 bg-civic-mist/50 p-5">
              <p className="label-caps">Current state</p>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">
                The shell, route, and layout are verified. This placeholder will
                be replaced by the domain UI in a later frontend step.
              </p>
              <p className="mt-3 text-xs text-slate-500">
                Path:{' '}
                <code className="rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-civic-teal">
                  {pillar.path}
                </code>
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3 border-t border-slate-200/80 bg-slate-50/60 px-6 py-5 sm:px-9">
            <NavLink to="/" className="btn-secondary py-2.5">
              Back to overview
            </NavLink>
            <NavLink to={next.to} className="btn-primary py-2.5">
              {next.label}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </NavLink>
          </div>
        </div>
      </div>
    </section>
  );
}

function LoginPage() {
  return (
    <section className="container-page animate-fade-up py-14 sm:py-20">
      <div className="mx-auto max-w-md">
        <div className="surface p-6 sm:p-8">
          <span className="grid h-12 w-12 place-items-center rounded-xl bg-civic-ink text-civic-tealLight">
            <LogIn className="h-6 w-6" aria-hidden="true" />
          </span>
          <h1 className="mt-5 text-2xl font-extrabold tracking-tight text-civic-ink">
            Sign in to Civic Pulse
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            Authentication forms arrive with the identity UI step. Public
            accountability remains available without an account.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <NavLink to="/accountability" className="btn-primary py-2.5">
              Continue as public visitor
            </NavLink>
            <NavLink to="/" className="btn-secondary py-2.5">
              Back to overview
            </NavLink>
          </div>
        </div>
      </div>
    </section>
  );
}

function NotFoundPage() {
  return (
    <section className="container-page animate-fade-up py-20">
      <div className="mx-auto max-w-xl text-center">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-civic-ink text-civic-tealLight">
          <MapPin className="h-7 w-7" aria-hidden="true" />
        </span>
        <p className="label-caps mt-6">Error 404</p>
        <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-civic-ink">
          This route is not on the map
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-600">
          The page you requested does not exist yet. Return to the platform
          overview to explore the wired civic modules.
        </p>
        <NavLink to="/" className="btn-primary mt-7">
          Back to overview
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </NavLink>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-200/80 bg-white/60">
      <div className="container-page flex flex-col gap-3 py-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <p>
          © {new Date().getFullYear()} Civic Pulse · Built for public
          accountability.
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            SPA shell online
          </span>
          <span>React 18 · Vite 5 · Tailwind 3</span>
        </div>
      </div>
    </footer>
  );
}

export default function App() {
  const location = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-civic-ink focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
      >
        Skip to content
      </a>

      <Header />

      <main id="main-content" className="flex-1">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          {MODULES.map((pillar) => (
            <Route
              key={pillar.path}
              path={pillar.path}
              element={<ModulePlaceholder pillar={pillar} />}
            />
          ))}
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>

      <Footer />
    </div>
  );
}
