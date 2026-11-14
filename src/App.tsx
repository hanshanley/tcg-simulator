import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Beaker,
  BookOpen,
  Box,
  Check,
  ChevronRight,
  CircleHelp,
  Cpu,
  Database,
  FlaskConical,
  Layers,
  LoaderCircle,
  MonitorPlay,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Terminal,
  Trophy,
  X,
} from 'lucide-react';
import { api, formatDate, navigate, percent, shortHash } from './api';
import { Inspector } from './Inspector';
import type { Catalog, Deck, Experiment } from './types';

const activeStatuses = ['queued', 'running', 'cancelling'];

export function Status({ status }: { status: string }) {
  return (
    <span className={`status ${status}`}>
      <span />
      {status.replaceAll('_', ' ')}
    </span>
  );
}

export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}

function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={close}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div className="modal-header">
        <div>
          <span className="eyebrow">RESEARCH WORKSPACE</span>
          <h2>{title}</h2>
        </div>
        <button className="icon-button" aria-label="Close dialog" onClick={close}>
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function App() {
  const [route, setRoute] = useState(window.location.hash.slice(1) || '/experiments');
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [decks, setDecks] = useState<Deck[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [modal, setModal] = useState<'experiment' | 'deck' | null>(null);
  const [query, setQuery] = useState('');
  const [lastReplay, setLastReplay] = useState<string | null>(null);
  useEffect(() => {
    const listener = () => setRoute(window.location.hash.slice(1) || '/experiments');
    window.addEventListener('hashchange', listener);
    return () => window.removeEventListener('hashchange', listener);
  }, []);
  const refresh = useCallback(async () => {
    const [nextExperiments, nextDecks] = await Promise.all([
      api<Experiment[]>('/experiments'),
      api<Deck[]>('/decks'),
    ]);
    setExperiments(nextExperiments);
    setDecks(nextDecks);
  }, []);
  useEffect(() => {
    let alive = true;
    Promise.all([
      api<Catalog>('/catalog'),
      api<Experiment[]>('/experiments'),
      api<Deck[]>('/decks'),
    ])
      .then(([nextCatalog, nextExperiments, nextDecks]) => {
        if (!alive) return;
        setCatalog(nextCatalog);
        setExperiments(nextExperiments);
        setDecks(nextDecks);
        setLoaded(true);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    const timer = window.setInterval(() => {
      if (alive)
        refresh().catch((e) => {
          if (alive) setError(e.message);
        });
    }, 1500);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [refresh]);
  const parts = route.split('/');
  const section = parts[1] || 'experiments';
  const selected = experiments.find((experiment) => experiment.id === parts[2]);
  const active = experiments.filter((experiment) =>
    activeStatuses.includes(experiment.status),
  ).length;
  const finished = experiments.reduce((sum, experiment) => sum + experiment.summary.completed, 0);
  const traces = experiments.reduce((sum, experiment) => sum + experiment.summary.decisions, 0);
  const openReplay = useCallback((id: string) => {
    setLastReplay(id);
    navigate(`/replay/${id}`);
  }, []);
  const nav = [
    { id: 'experiments', label: 'Experiments', icon: FlaskConical, path: '/experiments' },
    {
      id: 'replay',
      label: 'Battle inspector',
      icon: MonitorPlay,
      path: lastReplay ? `/replay/${lastReplay}` : '/replay',
    },
    { id: 'agents', label: 'Agents', icon: Cpu, path: '/agents' },
    { id: 'decks', label: 'Deck lab', icon: Layers, path: '/decks' },
    { id: 'results', label: 'Results', icon: Activity, path: '/results' },
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#/experiments">
          <span className="brand-symbol">
            <Layers size={23} strokeWidth={2} />
          </span>
          <span>
            counterplay<span className="brand-sub">TCG RESEARCH STUDIO</span>
          </span>
        </a>
        <div className="workspace-switch">
          <span className="workspace-avatar">L</span>
          <span>
            Local workspace<small>Personal research</small>
          </span>
          <ChevronRight size={15} />
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {nav.map((item) => (
            <a
              key={item.id}
              aria-label={item.label}
              className={section === item.id ? 'nav-item selected' : 'nav-item'}
              href={`#${item.path}`}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
              {item.id === 'experiments' && active > 0 && (
                <span className="nav-count">{active}</span>
              )}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="engine-card">
            <div className="engine-label">
              <span className={catalog ? 'live-dot' : 'offline-dot'} />
              {catalog ? 'Engine connected' : 'Connecting to engine'}
            </div>
            <strong>
              CABT <span>v{catalog?.engine.rules_version ?? '—'}</span>
            </strong>
            <small>Isolated local execution</small>
          </div>
          <a className="nav-item" href="#/about">
            <CircleHelp size={17} />
            About this workspace
            <ArrowUpRight size={14} />
          </a>
          <div className="local-profile">
            <div className="profile-icon">
              <Terminal size={16} />
            </div>
            <div>
              Local researcher<small>All data stays on this machine</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <strong>{nav.find((item) => item.id === section)?.label ?? 'About'}</strong>
          </div>
          <div className="topbar-right">
            <span className="local-chip">
              <ShieldCheck size={14} />
              Local-first
            </span>
            <span className="top-avatar">R</span>
          </div>
        </header>
        <main>
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError('')}>
                <X size={17} />
              </button>
            </div>
          )}
          {!loaded ? (
            <Empty icon={<LoaderCircle className="spin" />} title="Connecting to your workspace">
              Start the API with the command in the README. Your research will appear here.
            </Empty>
          ) : (
            <>
              {section === 'experiments' && !parts[2] && (
                <>
                  <div className="page-heading">
                    <div>
                      <div className="eyebrow">YOUR RESEARCH, IN MOTION</div>
                      <h1>Experiments</h1>
                      <p>Better agents start with better questions.</p>
                    </div>
                    <button className="button primary" onClick={() => setModal('experiment')}>
                      <Plus size={17} />
                      New experiment
                    </button>
                  </div>
                  <div className="intro-banner">
                    <div className="intro-copy">
                      <span className="tag">
                        <Beaker size={13} />
                        THE LOCAL RESEARCH LAB
                      </span>
                      <h2>
                        Every decision tells a story.
                        <br />
                        <span>Find the one that changes the game.</span>
                      </h2>
                      <p>
                        Put agents head-to-head, test a deck hypothesis, and follow
                        <br className="desktop-break" /> the evidence all the way down to a single
                        move.
                      </p>
                      <button className="text-button" onClick={() => setModal('experiment')}>
                        Set up an experiment <ArrowRight size={16} />
                      </button>
                    </div>
                    <div className="intro-graphic" aria-hidden="true">
                      <div className="orbit orbit-one" />
                      <div className="orbit orbit-two" />
                      <div className="graphic-card back">
                        <span>02</span>
                        <Cpu size={38} />
                        <small>BASELINE</small>
                      </div>
                      <div className="graphic-card front">
                        <span>01</span>
                        <FlaskConical size={38} />
                        <small>CANDIDATE</small>
                      </div>
                      <span className="graphic-spark">
                        <Sparkles size={21} />
                      </span>
                      <span className="graphic-caption">
                        A SMALL CHANGE. A MEASURABLE DIFFERENCE.
                      </span>
                    </div>
                  </div>
                  <div className="metrics">
                    <Metric
                      label="Total experiments"
                      value={experiments.length}
                      sub="Versioned & recorded"
                      icon={<FlaskConical size={17} />}
                    />
                    <Metric
                      label="Running or queued"
                      value={active}
                      sub="Isolated match workers"
                      icon={<Activity size={17} />}
                    />
                    <Metric
                      label="Completed games"
                      value={finished}
                      sub="Excludes failures & capped runs"
                      icon={<Trophy size={17} />}
                    />
                    <Metric
                      label="Decision traces"
                      value={traces.toLocaleString()}
                      sub="Every selection, preserved"
                      icon={<Database size={17} />}
                    />
                  </div>
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h3>
                          Experiment library <span className="count">{experiments.length}</span>
                        </h3>
                        <p>Your hypotheses, their results, and everything in between.</p>
                      </div>
                      <label className="search-field">
                        <Search size={16} />
                        <input
                          placeholder="Find an experiment…"
                          aria-label="Find an experiment"
                          value={query}
                          onChange={(event) => setQuery(event.target.value)}
                        />
                      </label>
                    </div>
                    <ExperimentTable
                      experiments={experiments.filter((experiment) =>
                        experiment.name.toLowerCase().includes(query.toLowerCase()),
                      )}
                      emptyAction={
                        <button className="button secondary" onClick={() => setModal('experiment')}>
                          <Plus size={16} />
                          Run your first experiment
                        </button>
                      }
                    />
                  </section>
                  <div className="footnote">
                    <ShieldCheck size={14} />
                    <span>Real engine. Complete traces. No hidden cloud services.</span>
                    <span className="footnote-right">
                      CABT rules v{catalog?.engine.rules_version} <span>·</span> Best-of-one games
                    </span>
                  </div>
                </>
              )}
              {section === 'experiments' &&
                parts[2] &&
                (selected ? (
                  <ExperimentDetail
                    experiment={selected}
                    openReplay={openReplay}
                    refresh={refresh}
                    onError={setError}
                  />
                ) : (
                  <Empty icon={<Search />} title="Experiment not found">
                    Return to the experiment library to select a run.
                  </Empty>
                ))}
              {section === 'replay' &&
                (parts[2] ? (
                  <Inspector
                    key={parts[2]}
                    gameId={parts[2]}
                    catalog={catalog!}
                    experiment={experiments.find((experiment) =>
                      experiment.games.some((game) => game.id === parts[2]),
                    )}
                  />
                ) : (
                  <>
                    <PageHeading
                      eyebrow="FOLLOW THE EVIDENCE"
                      title="Battle inspector"
                      description="A microscope for every move."
                    />
                    <section className="panel">
                      <Empty
                        icon={<MonitorPlay size={28} />}
                        title="Every move, ready for a closer look"
                        action={
                          <button
                            className="button primary"
                            onClick={() => navigate('/experiments')}
                          >
                            Open experiments <ArrowRight size={16} />
                          </button>
                        }
                      >
                        Run an experiment, then select a game to inspect its board state, legal
                        choices, and agent diagnostics.
                      </Empty>
                    </section>
                  </>
                ))}
              {section === 'agents' && (
                <>
                  <PageHeading
                    eyebrow="THE MINDS BEHIND THE MOVES"
                    title="Agents"
                    description="Small baselines. Honest benchmarks. A foundation to build on."
                  />
                  <div className="agent-grid">
                    {catalog?.agents.map((agent, index) => (
                      <section className="panel agent-card" key={agent.id}>
                        <div className="agent-card-top">
                          <div className={`agent-avatar agent-${index}`}>
                            <Cpu size={25} />
                          </div>
                          <span className="pill">BUILT-IN · V{agent.version}</span>
                        </div>
                        <h2>{agent.name}</h2>
                        <p>{agent.description}</p>
                        <div className="agent-code">
                          <Terminal size={14} />
                          <code>{agent.id}</code>
                          <span>Python policy</span>
                        </div>
                        <dl className="property-list">
                          <div>
                            <dt>Artifact fingerprint</dt>
                            <dd>
                              <code title={agent.artifact_sha256}>
                                {shortHash(agent.artifact_sha256)}
                              </code>
                            </dd>
                          </div>
                          <div>
                            <dt>Execution</dt>
                            <dd>Isolated match process</dd>
                          </div>
                          <div>
                            <dt>Diagnostics</dt>
                            <dd>Selection + timing</dd>
                          </div>
                        </dl>
                        <button
                          className="button secondary full-width"
                          onClick={() => setModal('experiment')}
                        >
                          Test this baseline <ArrowUpRight size={15} />
                        </button>
                      </section>
                    ))}
                  </div>
                  <div className="note">
                    <BookOpen size={19} />
                    <div>
                      <strong>A deliberate starting point</strong>
                      <p>
                        These are simple legal-choice baselines, not competitive agents. Policies
                        are registered in <code>backend/agents.py</code>; experiments snapshot their
                        version and implementation fingerprint.
                      </p>
                    </div>
                  </div>
                </>
              )}
              {section === 'decks' && (
                <>
                  <PageHeading
                    eyebrow="CHANGE A CARD. TEST A HYPOTHESIS."
                    title="Deck lab"
                    description="Immutable deck versions, backed by the engine's card catalog."
                    action={
                      <button className="button primary" onClick={() => setModal('deck')}>
                        <Plus size={16} />
                        New deck version
                      </button>
                    }
                  />
                  <div className="deck-grid">
                    {decks.map((deck) => (
                      <DeckCard key={deck.id} deck={deck} catalog={catalog!} />
                    ))}
                  </div>
                </>
              )}
              {section === 'results' && (
                <>
                  <PageHeading
                    eyebrow="LESS GUESSWORK. MORE EVIDENCE."
                    title="Results"
                    description="Candidate performance, with sample sizes and uncertainty in view."
                  />
                  <section className="panel">
                    <div className="panel-heading">
                      <div>
                        <h3>Experiment comparison</h3>
                        <p>
                          Descriptive results only. Different protocols are not interchangeable.
                        </p>
                      </div>
                    </div>
                    {experiments.length ? (
                      <div className="table-scroll">
                        <table>
                          <thead>
                            <tr>
                              <th>Experiment / candidate</th>
                              <th>W / L / D</th>
                              <th>Win rate</th>
                              <th>95% Wilson interval</th>
                              <th>Failed / capped</th>
                              <th />
                            </tr>
                          </thead>
                          <tbody>
                            {experiments.map((experiment) => (
                              <tr key={experiment.id}>
                                <td>
                                  <a className="row-title" href={`#/experiments/${experiment.id}`}>
                                    {experiment.name}
                                  </a>
                                  <small>
                                    {experiment.agents[0].name} vs {experiment.agents[1].name}
                                  </small>
                                </td>
                                <td className="mono">
                                  {experiment.summary.wins} / {experiment.summary.losses} /{' '}
                                  {experiment.summary.draws}
                                </td>
                                <td className="mono">{percent(experiment.summary.win_rate)}</td>
                                <td className="mono">
                                  {experiment.summary.win_rate_ci?.map(percent).join(' – ') ?? '—'}
                                </td>
                                <td className="mono">
                                  {experiment.summary.failed} / {experiment.summary.capped}
                                </td>
                                <td>
                                  <a
                                    className="icon-button"
                                    aria-label={`Open ${experiment.name}`}
                                    href={`#/experiments/${experiment.id}`}
                                  >
                                    <ArrowUpRight size={17} />
                                  </a>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <Empty icon={<Activity />} title="Evidence starts with a run">
                        Create an experiment to see its measured results here.
                      </Empty>
                    )}
                  </section>
                  <div className="note">
                    <CircleHelp size={19} />
                    <p>
                      Win rate = candidate wins / completed games, including draws in the
                      denominator. Failed and capped games are excluded. Intervals describe
                      individual experiments, not statistical significance between agents. Engine
                      randomness is not seeded.
                    </p>
                  </div>
                </>
              )}
              {section === 'about' && (
                <>
                  <PageHeading
                    eyebrow="BUILT FOR CURIOSITY"
                    title="Your local research studio"
                    description="Counterplay is a focused workspace for studying Pokémon TCG agents."
                  />
                  <section className="panel about-panel">
                    <h2>Evidence you can inspect.</h2>
                    <p>
                      Matches use the official CABT native engine distributed in
                      kaggle-environments. This studio is independent and is not affiliated with
                      Pokémon, Kaggle, or the engine authors.
                    </p>
                    <dl className="property-list">
                      <div>
                        <dt>Engine package</dt>
                        <dd>{catalog?.engine.package_version}</dd>
                      </div>
                      <div>
                        <dt>Native fingerprint</dt>
                        <dd>
                          <code className="long-hash">{catalog?.engine.native_sha256}</code>
                        </dd>
                      </div>
                      <div>
                        <dt>Platform</dt>
                        <dd>{catalog?.engine.platform}</dd>
                      </div>
                      <div>
                        <dt>Persistence</dt>
                        <dd>SQLite + compressed JSON replays</dd>
                      </div>
                      <div>
                        <dt>Execution</dt>
                        <dd>One subprocess per game; one local queue</dd>
                      </div>
                    </dl>
                    <div className="note">
                      <CircleHelp size={19} />
                      <p>
                        Policy seeds control only the random baseline's selections, not engine
                        shuffles or coin flips. Replays are recorded playback, not deterministic
                        reruns. This release has no counterfactual search, arbitrary agent upload,
                        or Kaggle export.
                      </p>
                    </div>
                  </section>
                </>
              )}
            </>
          )}
        </main>
      </div>
      {modal === 'experiment' && catalog && (
        <Modal title="New experiment" close={() => setModal(null)}>
          <ExperimentForm
            decks={decks}
            catalog={catalog}
            onCreated={async (experiment) => {
              await refresh();
              setModal(null);
              navigate(`/experiments/${experiment.id}`);
            }}
          />
        </Modal>
      )}
      {modal === 'deck' && catalog && (
        <Modal title="New deck version" close={() => setModal(null)}>
          <DeckForm
            catalog={catalog}
            starter={decks[0]}
            onCreated={async () => {
              await refresh();
              setModal(null);
            }}
          />
        </Modal>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  icon,
}: {
  label: string;
  value: ReactNode;
  sub: string;
  icon: ReactNode;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {label}
        {icon}
      </div>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

function ExperimentTable({
  experiments,
  emptyAction,
}: {
  experiments: Experiment[];
  emptyAction: ReactNode;
}) {
  if (!experiments.length)
    return (
      <Empty
        icon={<FlaskConical size={27} />}
        title="A clean slate for your next hypothesis"
        action={emptyAction}
      >
        Start with a baseline matchup. Every game and every decision will be waiting here.
      </Empty>
    );
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Experiment</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Candidate win rate</th>
            <th>Created</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {experiments.map((experiment) => (
            <tr key={experiment.id}>
              <td>
                <a className="row-title" href={`#/experiments/${experiment.id}`}>
                  <span className="table-icon">
                    <FlaskConical size={16} />
                  </span>
                  {experiment.name}
                </a>
                <small className="row-sub">
                  {experiment.agents[0].id} <span>vs</span> {experiment.agents[1].id}
                </small>
              </td>
              <td>
                <Status status={experiment.status} />
              </td>
              <td>
                <div className="progress-cell">
                  <span className="mono">
                    {experiment.games.length}{' '}
                    <span className="muted">/ {experiment.config.games}</span>
                  </span>
                  <progress max={experiment.config.games} value={experiment.games.length} />
                </div>
              </td>
              <td>
                <strong className="mono">{percent(experiment.summary.win_rate)}</strong>
                <small>n = {experiment.summary.completed}</small>
              </td>
              <td className="muted">{formatDate(experiment.created_at)}</td>
              <td>
                <a
                  href={`#/experiments/${experiment.id}`}
                  className="icon-button"
                  aria-label={`Open ${experiment.name}`}
                >
                  <ChevronRight size={18} />
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ExperimentDetail({
  experiment,
  openReplay,
  refresh,
  onError,
}: {
  experiment: Experiment;
  openReplay: (id: string) => void;
  refresh: () => Promise<void>;
  onError: (message: string) => void;
}) {
  const [protocolOpen, setProtocolOpen] = useState(false);
  const summary = experiment.summary;
  return (
    <>
      <a className="back-link" href="#/experiments">
        <ArrowLeft size={15} />
        All experiments
      </a>
      <div className="page-heading detail-heading">
        <div>
          <div className="eyebrow">
            EXPERIMENT <span className="mono">{experiment.id.slice(0, 8)}</span>
          </div>
          <h1>{experiment.name}</h1>
          <p>
            {experiment.agents[0].name} <span className="muted">vs</span>{' '}
            {experiment.agents[1].name} <span className="separator">/</span>{' '}
            {formatDate(experiment.created_at)}
          </p>
        </div>
        <div className="heading-actions">
          <Status status={experiment.status} />
          {['queued', 'running'].includes(experiment.status) && (
            <button
              className="button secondary"
              onClick={async () => {
                try {
                  await api(`/experiments/${experiment.id}/cancel`, { method: 'POST' });
                  await refresh();
                } catch (e) {
                  onError((e as Error).message);
                }
              }}
            >
              Stop experiment
            </button>
          )}
        </div>
      </div>
      {experiment.error && (
        <div className="error-banner" role="alert">
          {experiment.error}
        </div>
      )}
      <div className="metrics detail-metrics">
        <Metric
          label="Candidate win rate"
          value={percent(summary.win_rate)}
          sub={`${summary.wins} wins · ${summary.losses} losses · ${summary.draws} draws`}
          icon={<Trophy size={17} />}
        />
        <Metric
          label="95% Wilson interval"
          value={
            summary.win_rate_ci
              ? `${(summary.win_rate_ci[0] * 100).toFixed(0)}–${(summary.win_rate_ci[1] * 100).toFixed(0)}%`
              : '—'
          }
          sub={`${summary.completed} completed games · draws included`}
          icon={<Activity size={17} />}
        />
        <Metric
          label="Games recorded"
          value={`${experiment.games.length} / ${experiment.config.games}`}
          sub={`${summary.failed} failed · ${summary.capped} capped`}
          icon={<Box size={17} />}
        />
        <Metric
          label="Decision traces"
          value={summary.decisions.toLocaleString()}
          sub={`${(summary.duration_ms / 1000).toFixed(2)}s total engine + policy time`}
          icon={<Database size={17} />}
        />
      </div>
      {experiment.status === 'cancelling' && (
        <div className="note">
          <LoaderCircle className="spin" size={18} />
          <p>Stopping after the current game. Its trace will still be saved.</p>
        </div>
      )}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h3>
              Game ledger <span className="count">{experiment.games.length}</span>
            </h3>
            <p>Open a game to follow its decisions from setup to finish.</p>
          </div>
          <span className="pill">BEST OF ONE · ALTERNATING CHOICE PRIORITY</span>
        </div>
        {experiment.games.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Game</th>
                  <th>Outcome</th>
                  <th>Turns</th>
                  <th>Decisions</th>
                  <th>Policy p95</th>
                  <th>Duration</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {experiment.games.map((game) => (
                  <tr key={game.id}>
                    <td>
                      <button className="row-title unstyled" onClick={() => openReplay(game.id)}>
                        Game {String(game.number).padStart(2, '0')}
                      </button>
                      <small>
                        {game.first_player < 0
                          ? 'Setup'
                          : `${game.first_player === 0 ? 'Candidate' : 'Opponent'} went first`}
                      </small>
                    </td>
                    <td>
                      {game.status === 'completed' ? (
                        <span
                          className={`outcome ${game.winner === 0 ? 'win' : game.winner === 1 ? 'loss' : ''}`}
                        >
                          {game.winner === 0
                            ? 'Candidate win'
                            : game.winner === 1
                              ? 'Opponent win'
                              : 'Draw'}
                        </span>
                      ) : (
                        <Status status={game.status} />
                      )}
                      {game.error && <small className="error-text">{game.error}</small>}
                    </td>
                    <td className="mono">{game.turns}</td>
                    <td className="mono">{game.decision_count}</td>
                    <td className="mono">{game.p95_latency_ms?.toFixed(3) ?? '—'} ms</td>
                    <td className="mono">{(game.duration_ms / 1000).toFixed(2)}s</td>
                    <td>
                      <button
                        className="button small secondary"
                        onClick={() => openReplay(game.id)}
                      >
                        Inspect <ArrowUpRight size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon={
              <LoaderCircle className={activeStatuses.includes(experiment.status) ? 'spin' : ''} />
            }
            title={
              activeStatuses.includes(experiment.status)
                ? 'Preparing the first matchup'
                : 'No games recorded'
            }
          >
            Each completed or failed game will appear here with its own trace.
          </Empty>
        )}
      </section>
      <section className="panel protocol-panel">
        <button
          className="protocol-toggle"
          onClick={() => setProtocolOpen(!protocolOpen)}
          aria-expanded={protocolOpen}
        >
          <span>
            <ShieldCheck size={17} />
            <strong>Frozen protocol</strong>
            <span>Engine, policies, decks, and limits</span>
          </span>
          <ChevronRight className={protocolOpen ? 'rotate' : ''} size={18} />
        </button>
        {protocolOpen && (
          <div className="protocol-body">
            <dl className="property-list">
              <div>
                <dt>Engine</dt>
                <dd>
                  CABT v{experiment.engine.rules_version} · package{' '}
                  {experiment.engine.package_version}
                </dd>
              </div>
              <div>
                <dt>Native hash</dt>
                <dd>
                  <code>{shortHash(experiment.engine.native_sha256)}</code>
                </dd>
              </div>
              {experiment.agents.map((agent, index) => (
                <div key={index}>
                  <dt>{index === 0 ? 'Candidate' : 'Opponent'} policy</dt>
                  <dd>
                    {agent.name} · v{agent.version} ·{' '}
                    <code>{shortHash(agent.artifact_sha256)}</code>
                  </dd>
                </div>
              ))}
              {experiment.decks.map((deck, index) => (
                <div key={index}>
                  <dt>{index === 0 ? 'Candidate' : 'Opponent'} deck</dt>
                  <dd>
                    {deck.name} · v{deck.version} · <code>{shortHash(deck.sha256)}</code>
                  </dd>
                </div>
              ))}
              <div>
                <dt>Budget per game</dt>
                <dd>
                  {experiment.config.max_decisions.toLocaleString()} decisions /{' '}
                  {experiment.config.timeout_seconds}s
                </dd>
              </div>
              <div>
                <dt>Policy seed</dt>
                <dd>{experiment.config.policy_seed} (not engine randomness)</dd>
              </div>
              <div>
                <dt>Format</dt>
                <dd>Independent BO1 games; alternating who chooses first/second</dd>
              </div>
            </dl>
          </div>
        )}
      </section>
    </>
  );
}

function ExperimentForm({
  decks,
  catalog,
  onCreated,
}: {
  decks: Deck[];
  catalog: Catalog;
  onCreated: (experiment: Experiment) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError('');
    try {
      const experiment = await api<Experiment>('/experiments', {
        method: 'POST',
        body: JSON.stringify({
          name: data.get('name'),
          agent_ids: [data.get('candidate'), data.get('opponent')],
          deck_ids: [data.get('candidate_deck'), data.get('opponent_deck')],
          games: Number(data.get('games')),
          policy_seed: Number(data.get('seed')),
          max_decisions: Number(data.get('max_decisions')),
          timeout_seconds: Number(data.get('timeout')),
        }),
      });
      await onCreated(experiment);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="modal-form">
      <label>
        Experiment name
        <input
          autoFocus
          name="name"
          required
          maxLength={100}
          defaultValue="Baseline calibration"
          placeholder="What are you testing?"
        />
      </label>
      <div className="form-section-label">
        <span className="player-dot candidate" />
        CANDIDATE
      </div>
      <div className="form-grid">
        <label>
          Agent
          <select name="candidate" defaultValue="random">
            {catalog.agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Deck
          <select name="candidate_deck">
            {decks.map((deck) => (
              <option key={deck.id} value={deck.id}>
                {deck.name} · v{deck.version}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="form-section-label">
        <span className="player-dot opponent" />
        OPPONENT
      </div>
      <div className="form-grid">
        <label>
          Agent
          <select name="opponent" defaultValue="first">
            {catalog.agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Deck
          <select name="opponent_deck">
            {decks.map((deck) => (
              <option key={deck.id} value={deck.id}>
                {deck.name} · v{deck.version}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="form-grid">
        <label>
          Number of games
          <input name="games" type="number" defaultValue={10} min={1} max={200} required />
        </label>
        <label>
          Policy seed
          <input name="seed" type="number" defaultValue={42} min={0} max={2147483647} required />
        </label>
      </div>
      <details className="advanced">
        <summary>Execution limits</summary>
        <div className="form-grid">
          <label>
            Max decisions / game
            <input
              name="max_decisions"
              type="number"
              defaultValue={2500}
              min={1}
              max={10000}
              required
            />
          </label>
          <label>
            Timeout / game (seconds)
            <input name="timeout" type="number" defaultValue={30} min={1} max={120} required />
          </label>
        </div>
      </details>
      <div className="form-note">
        <ShieldCheck size={17} />
        <p>
          Independent BO1 games, alternating choice priority. Decks and agent fingerprints are
          frozen at launch. Policy seeds do not seed engine randomness.
        </p>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <button className="button primary full-width" disabled={busy}>
        {busy ? <LoaderCircle className="spin" size={17} /> : <FlaskConical size={17} />}
        {busy ? 'Starting experiment…' : 'Launch experiment'}
      </button>
    </form>
  );
}

function DeckCard({ deck, catalog }: { deck: Deck; catalog: Catalog }) {
  const [expanded, setExpanded] = useState(false);
  const counts = new Map<number, number>();
  deck.cards.forEach((id) => counts.set(id, (counts.get(id) ?? 0) + 1));
  const cards = new Map(catalog.cards.map((card) => [card.cardId, card]));
  const pokemon = deck.cards.filter((id) => cards.get(id)?.cardType === 0).length;
  const energy = deck.cards.filter((id) => (cards.get(id)?.cardType ?? 0) >= 5).length;
  return (
    <section className="panel deck-card">
      <div className="agent-card-top">
        <div className="deck-avatar">
          <Layers size={25} />
        </div>
        <span className="pill">VERSION {deck.version}</span>
      </div>
      <h2>{deck.name}</h2>
      <p>{deck.description || 'A custom research deck.'}</p>
      <div className="deck-stats">
        <span>
          <strong>{pokemon}</strong>Pokémon
        </span>
        <span>
          <strong>{60 - pokemon - energy}</strong>Trainers
        </span>
        <span>
          <strong>{energy}</strong>Energy
        </span>
        <span>
          <strong>60</strong>Total
        </span>
      </div>
      <div className="deck-footer">
        <code title={deck.sha256}>{shortHash(deck.sha256)}</code>
        <button
          className="text-button"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
        >
          {expanded ? 'Hide' : 'View'} card list{' '}
          <ChevronRight size={14} className={expanded ? 'rotate' : ''} />
        </button>
      </div>
      {expanded && (
        <div className="card-list">
          {[...counts.entries()].map(([id, count]) => (
            <div key={id}>
              <span className="mono">{String(count).padStart(2, '0')}</span>
              <span>{cards.get(id)?.name ?? `Card #${id}`}</span>
              <code>#{id}</code>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function DeckForm({
  catalog,
  starter,
  onCreated,
}: {
  catalog: Catalog;
  starter?: Deck;
  onCreated: () => Promise<void>;
}) {
  const [text, setText] = useState(starter?.cards.join('\n') ?? '');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const matches = catalog.cards
    .filter((card) => `${card.name} ${card.cardId}`.toLowerCase().includes(search.toLowerCase()))
    .slice(0, 8);
  const tokens = text
    .trim()
    .split(/[\s,]+/)
    .filter(Boolean);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    if (tokens.length !== 60 || tokens.some((token) => !/^\d+$/.test(token))) {
      setError('Enter exactly 60 integer card IDs, separated by commas or newlines.');
      return;
    }
    const data = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await api('/decks', {
        method: 'POST',
        body: JSON.stringify({
          name: data.get('name'),
          description: data.get('description'),
          cards: tokens.map(Number),
        }),
      });
      await onCreated();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <form className="modal-form" onSubmit={submit}>
      <label>
        Deck name
        <input name="name" required maxLength={100} defaultValue={starter?.name ?? ''} />
      </label>
      <label>
        Research note
        <input name="description" maxLength={500} placeholder="What does this version change?" />
      </label>
      <label>
        Card IDs{' '}
        <span className={tokens.length === 60 ? 'success-text' : 'muted'}>
          {tokens.length} / 60 cards
        </span>
        <textarea
          name="cards"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={7}
          spellCheck={false}
        />
      </label>
      <label>
        Look up a card
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search native card names or IDs…"
        />
      </label>
      {search && (
        <div className="catalog-results">
          {matches.map((card) => (
            <div key={card.cardId}>
              <span>{card.name}</span>
              <code>{card.cardId}</code>
            </div>
          ))}
          {!matches.length && <span>No matching cards</span>}
        </div>
      )}
      <div className="form-note">
        <Layers size={17} />
        <p>
          Saving creates an immutable version; existing experiments keep their original deck. Card
          IDs come directly from the installed engine.
        </p>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <button disabled={busy} className="button primary full-width">
        {busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />}Save deck version
      </button>
    </form>
  );
}

export function DownloadReplay({ gameId }: { gameId: string }) {
  return (
    <a
      className="button secondary small"
      href={`/api/games/${gameId}`}
      download={`replay-${gameId}.json`}
    >
      <ArrowDownToLine size={14} />
      Full trace
    </a>
  );
}
