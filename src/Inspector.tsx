import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  Bookmark,
  Check,
  ChevronLeft,
  ChevronRight,
  Circle,
  Code2,
  Droplets,
  Flag,
  Flame,
  Layers,
  Leaf,
  LoaderCircle,
  Moon,
  Mountain,
  Pause,
  Play,
  ShieldCheck,
  SkipBack,
  SkipForward,
  Snowflake,
  Sparkles,
  Swords,
  Zap,
} from 'lucide-react';
import { api } from './api';
import { DownloadReplay, Empty, Status } from './App';
import type {
  BoardCard,
  CardData,
  Catalog,
  Experiment,
  Observation,
  Option,
  Player,
  Replay,
} from './types';

const selectionNames = [
  'Main action',
  'Select a card',
  'Attached card',
  'Card or attached card',
  'Energy',
  'Skill',
  'Attack',
  'Evolution',
  'Count',
  'Yes / no',
  'Special condition',
];
const optionNames = [
  'Number',
  'Yes',
  'No',
  'Card',
  'Tool card',
  'Energy card',
  'Energy',
  'Play',
  'Attach',
  'Evolve',
  'Ability',
  'Discard',
  'Retreat',
  'Attack',
  'End turn',
  'Skill',
  'Special condition',
];
const contextNames: Record<number, string> = {
  0: 'Choose a main action',
  1: 'Choose your starting active Pokémon',
  2: 'Set up your bench',
  3: 'Choose a switch target',
  4: 'Promote an active Pokémon',
  5: 'Move a Pokémon to the bench',
  6: 'Put a Pokémon into play',
  7: 'Choose a card for your hand',
  8: 'Choose a card to discard',
  9: 'Return a card to the deck',
  10: 'Place damage counters',
  15: 'Choose a damage target',
  17: 'Choose a healing target',
  35: 'Choose an attack',
  37: 'Choose an evolution',
  38: 'Choose how many cards to draw',
  41: 'Choose whether to go first',
  42: 'Opening-hand mulligan',
  43: 'Activate an effect?',
  44: 'Choose the first effect',
  46: 'Choose a coin result',
};
const areaNames: Record<number, string> = {
  1: 'deck',
  2: 'hand',
  3: 'discard',
  4: 'active',
  5: 'bench',
  6: 'prize',
  7: 'stadium',
  12: 'looking',
};
const logNames = [
  'Shuffle',
  'Basic Pokémon check',
  'Turn started',
  'Turn ended',
  'Card drawn',
  'Opponent drew a card',
  'Card moved',
  'Hidden card moved',
  'Switch',
  'Evolution / change',
  'Card played',
  'Energy attached',
  'Evolution',
  'Devolution',
  'Attachment moved',
  'Attack',
  'HP changed',
  'Poison',
  'Burn',
  'Sleep',
  'Paralysis',
  'Confusion',
  'Coin flip',
  'Game result',
];

function optionCard(option: Option, observation: Observation): BoardCard | null {
  if (option.cardId !== undefined) return { id: option.cardId, serial: -1 };
  const player = observation.current.players[option.playerIndex ?? observation.current.yourIndex];
  const area = option.type === 7 ? 2 : option.area;
  const index = option.index ?? 0;
  if (area === 1) return observation.select.deck?.[index] ?? null;
  if (area === 2) return player.hand?.[index] ?? null;
  if (area === 3) return player.discard[index] ?? null;
  if (area === 4) return player.active[index] ?? null;
  if (area === 5) return player.bench[index] ?? null;
  if (area === 6) return player.prize[index] ?? null;
  if (area === 7) return observation.current.stadium[index] ?? null;
  return null;
}

function optionLabel(option: Option, observation: Observation, catalog: Catalog) {
  if (option.attackId !== undefined)
    return (
      catalog.attacks.find((attack) => attack.attackId === option.attackId)?.name ??
      `Attack #${option.attackId}`
    );
  if (option.number !== undefined) return `Select ${option.number}`;
  const card = optionCard(option, observation);
  const name = card
    ? (catalog.cards.find((item) => item.cardId === card.id)?.name ?? `Card #${card.id}`)
    : null;
  return [optionNames[option.type] ?? `Option type ${option.type}`, name]
    .filter(Boolean)
    .join(' · ');
}

export function Inspector({
  gameId,
  catalog,
  experiment,
}: {
  gameId: string;
  catalog: Catalog;
  experiment?: Experiment;
}) {
  const [replay, setReplay] = useState<Replay | null>(null);
  const [error, setError] = useState('');
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [tab, setTab] = useState<'choices' | 'raw'>('choices');
  const [bookmarkBusy, setBookmarkBusy] = useState(false);
  const timelineRef = useRef<HTMLDivElement>(null);
  const cards = useMemo(() => new Map(catalog.cards.map((card) => [card.cardId, card])), [catalog]);
  useEffect(() => {
    let alive = true;
    api<Replay>(`/games/${gameId}`)
      .then((result) => {
        if (alive) setReplay(result);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [gameId]);
  const total = replay?.decisions.length ?? 0;
  useEffect(() => {
    const container = timelineRef.current;
    const current = container?.querySelector<HTMLElement>('.timeline-item.current');
    if (!container || !current) return;
    const top =
      current.getBoundingClientRect().top -
      container.getBoundingClientRect().top +
      container.scrollTop;
    if (top < container.scrollTop) container.scrollTop = top;
    else if (top + current.offsetHeight > container.scrollTop + container.clientHeight) {
      container.scrollTop = top + current.offsetHeight - container.clientHeight;
    }
  }, [index, replay]);
  useEffect(() => {
    if (!playing) return;
    if (index >= total) return;
    const timer = window.setTimeout(() => setIndex((value) => Math.min(total, value + 1)), 650);
    return () => window.clearTimeout(timer);
  }, [playing, index, total]);
  const isPlaying = playing && index < total;
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (
        event.target instanceof HTMLElement &&
        (event.target.closest('input, textarea, select, button, a') ||
          event.target.isContentEditable)
      )
        return;
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        event.preventDefault();
        setPlaying(false);
        setIndex((value) =>
          Math.max(0, Math.min(total, value + (event.key === 'ArrowRight' ? 1 : -1))),
        );
      }
      if (event.key === ' ') {
        event.preventDefault();
        setPlaying((value) => !value);
      }
    };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, [total]);
  if (!replay)
    return (
      <>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        <Empty
          icon={error ? <ShieldCheck /> : <LoaderCircle className="spin" />}
          title={error ? 'Unable to open this replay' : 'Opening the match trace'}
        >
          Every recorded observation, exactly as the agent received it.
        </Empty>
      </>
    );
  const decision = replay.decisions[index];
  const observation = decision?.observation ?? replay.final_observation;
  const terminal = index === total;
  const perspective = observation?.current.yourIndex ?? 0;
  const playerLabel = (player: number) => (player === 0 ? 'Candidate' : 'Opponent');
  const bookmark = replay.bookmarks.find((item) => item.decision === index);
  const goto = (value: number) => {
    setIndex(value);
    setPlaying(false);
  };
  async function toggleBookmark() {
    setBookmarkBusy(true);
    setError('');
    try {
      await api(`/games/${gameId}/bookmarks/${index}`, {
        method: 'PUT',
        body: JSON.stringify({ label: bookmark ? '' : 'Review decision' }),
      });
      setReplay((previous) =>
        previous
          ? {
              ...previous,
              bookmarks: bookmark
                ? previous.bookmarks.filter((item) => item.decision !== index)
                : [...previous.bookmarks, { decision: index, label: 'Review decision' }],
            }
          : previous,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBookmarkBusy(false);
    }
  }
  return (
    <>
      <a
        className="back-link"
        href={experiment ? `#/experiments/${experiment.id}` : '#/experiments'}
      >
        <ArrowLeft size={15} />
        {experiment?.name ?? 'All experiments'}
      </a>
      <div className="page-heading inspector-heading">
        <div>
          <div className="eyebrow">BATTLE INSPECTOR</div>
          <h1>
            Game {String(replay.number).padStart(2, '0')}{' '}
            <span className="heading-soft">/ Every move, in focus.</span>
          </h1>
          <p>
            {experiment
              ? `${experiment.agents[0].name} vs ${experiment.agents[1].name}`
              : 'Recorded native-engine game'}{' '}
            <span className="separator">/</span> <span className="mono">{gameId.slice(0, 8)}</span>
          </p>
        </div>
        <div className="heading-actions">
          <Status status={replay.status} />
          <DownloadReplay gameId={gameId} />
        </div>
      </div>
      {(error || replay.error) && (
        <div className="error-banner" role="alert">
          {error || replay.error}
        </div>
      )}
      <div className="inspector-workspace">
        <aside className="timeline panel">
          <div className="inspector-panel-heading">
            <h3>Decision timeline</h3>
            <span className="count">{total}</span>
          </div>
          <div className="timeline-scroll" ref={timelineRef}>
            {replay.decisions.map((item, position) => (
              <button
                key={position}
                className={`timeline-item ${position === index ? 'current' : ''}`}
                onClick={() => goto(position)}
              >
                <span className={`timeline-dot ${item.player === 0 ? 'candidate' : 'opponent'}`} />
                <div>
                  <span className="timeline-turn">
                    TURN {item.observation.current.turn} <span>· {playerLabel(item.player)}</span>
                  </span>
                  <strong>
                    {contextNames[item.observation.select.context] ??
                      selectionNames[item.observation.select.type] ??
                      'Selection'}
                  </strong>
                  <small>
                    #{position + 1} · {item.selected.length} selected{' '}
                    {replay.bookmarks.some((bookmark) => bookmark.decision === position) && (
                      <Bookmark size={10} />
                    )}
                  </small>
                </div>
              </button>
            ))}
            <button
              className={`timeline-item ${terminal ? 'current' : ''}`}
              onClick={() => goto(total)}
            >
              <Flag size={14} />
              <div>
                <strong>{replay.status === 'completed' ? 'Game finished' : 'Trace ended'}</strong>
                <small>
                  {replay.status === 'completed'
                    ? replay.winner === null
                      ? 'Draw'
                      : `${playerLabel(replay.winner)} won`
                    : replay.status}
                </small>
              </div>
            </button>
          </div>
        </aside>
        <section className="board-panel panel">
          <div className="inspector-panel-heading">
            <div className="board-title">
              <Swords size={16} />
              <strong>Turn {observation?.current.turn ?? 0}</strong>
            </div>
            <span className="perspective-chip">
              <ShieldCheck size={12} />
              {playerLabel(perspective)} observation
            </span>
          </div>
          {observation ? (
            <div className="battle-board">
              <PlayerField
                player={observation.current.players[1 - perspective]}
                label={playerLabel(1 - perspective)}
                agentName={experiment?.agents[1 - perspective]?.name}
                cards={cards}
                opponent
              />
              <div className="stadium-line">
                <span />
                {observation.current.stadium.length ? (
                  observation.current.stadium.map((card, i) => (
                    <span className="stadium-label" key={i}>
                      {card
                        ? (cards.get(card.id)?.name ?? `Stadium #${card.id}`)
                        : 'Hidden stadium'}
                    </span>
                  ))
                ) : (
                  <span className="stadium-label">
                    <Circle size={12} />
                    BATTLEFIELD
                  </span>
                )}
                <span />
              </div>
              <PlayerField
                player={observation.current.players[perspective]}
                label={playerLabel(perspective)}
                agentName={experiment?.agents[perspective]?.name}
                cards={cards}
              />
              <div className="hand-area">
                <span className="zone-label">
                  OBSERVED HAND <span>{observation.current.players[perspective].handCount}</span>
                </span>
                <div className="hand-cards">
                  {observation.current.players[perspective].hand?.map((card, i) => (
                    <div
                      key={i}
                      className="hand-card"
                      title={card ? cards.get(card.id)?.name : 'Hidden card'}
                    >
                      <span
                        className={`energy-mark energy-${card ? (cards.get(card.id)?.energyType ?? 0) : 0}`}
                      />
                      <span>
                        {card ? (cards.get(card.id)?.name ?? `Card #${card.id}`) : 'Face-down card'}
                      </span>
                      <code>{card ? `#${card.id}` : '?'}</code>
                    </div>
                  ))}
                  {!observation.current.players[perspective].hand?.length && (
                    <span className="muted small-text">No visible cards</span>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <Empty icon={<Flag />} title="No board state recorded">
              The worker ended before the first observation.
            </Empty>
          )}
          <div className="replay-controls">
            <div className="playback-buttons">
              <button
                className="icon-button"
                aria-label="First decision"
                onClick={() => goto(0)}
                disabled={index === 0}
              >
                <SkipBack size={16} />
              </button>
              <button
                className="icon-button"
                aria-label="Previous decision"
                onClick={() => goto(Math.max(0, index - 1))}
                disabled={index === 0}
              >
                <ChevronLeft size={18} />
              </button>
              <button
                className="play-button"
                aria-label={isPlaying ? 'Pause replay' : 'Play replay'}
                onClick={() => {
                  if (terminal) setIndex(0);
                  setPlaying(!isPlaying);
                }}
                disabled={!total}
              >
                {isPlaying ? <Pause size={15} /> : <Play size={15} />}
              </button>
              <button
                className="icon-button"
                aria-label="Next decision"
                onClick={() => goto(Math.min(total, index + 1))}
                disabled={terminal}
              >
                <ChevronRight size={18} />
              </button>
              <button
                className="icon-button"
                aria-label="Final state"
                onClick={() => goto(total)}
                disabled={terminal}
              >
                <SkipForward size={16} />
              </button>
            </div>
            <input
              aria-label="Replay position"
              type="range"
              min={0}
              max={total}
              value={index}
              onChange={(event) => goto(Number(event.target.value))}
            />
            <span className="mono">
              {terminal ? 'End' : index + 1} / {total}
            </span>
          </div>
        </section>
        <aside className="decision-panel panel">
          <div className="inspector-panel-heading">
            <h3>{terminal ? 'Final state' : 'Decision detail'}</h3>
            {!terminal && (
              <button
                className={`icon-button ${bookmark ? 'bookmarked' : ''}`}
                disabled={bookmarkBusy}
                aria-label={bookmark ? 'Remove bookmark' : 'Bookmark decision'}
                onClick={toggleBookmark}
              >
                <Bookmark size={16} fill={bookmark ? 'currentColor' : 'none'} />
              </button>
            )}
          </div>
          {terminal ? (
            <div className="terminal-detail">
              <div className="terminal-icon">
                <Flag size={25} />
              </div>
              <h2>
                {replay.status === 'completed'
                  ? replay.winner === null
                    ? 'A drawn game.'
                    : `${playerLabel(replay.winner)} wins.`
                  : 'Trace ended.'}
              </h2>
              <p>
                {total} decisions preserved.
                <br />
                {replay.status === 'capped'
                  ? 'The decision budget was reached. This is not a draw.'
                  : replay.status === 'failed'
                    ? 'The engine or worker reported an error. This game is excluded from win-rate estimates.'
                    : 'The final state comes directly from the engine.'}
              </p>
              <DownloadReplay gameId={gameId} />
            </div>
          ) : (
            decision &&
            observation && (
              <>
                <div className="decision-summary">
                  <span className="eyebrow">DECISION {index + 1}</span>
                  <h3>
                    {contextNames[observation.select.context] ??
                      selectionNames[observation.select.type] ??
                      'Selection'}
                  </h3>
                  <span className={`player-badge ${perspective === 0 ? 'candidate' : 'opponent'}`}>
                    {playerLabel(perspective)}
                  </span>
                </div>
                <div className="inspector-tabs">
                  <button
                    className={tab === 'choices' ? 'active' : ''}
                    onClick={() => setTab('choices')}
                  >
                    Legal choices <span>{observation.select.option.length}</span>
                  </button>
                  <button className={tab === 'raw' ? 'active' : ''} onClick={() => setTab('raw')}>
                    <Code2 size={13} />
                    Raw evidence
                  </button>
                </div>
                <div className="decision-content">
                  {tab === 'choices' ? (
                    <>
                      <div className="selection-rule">
                        Select{' '}
                        {observation.select.minCount === observation.select.maxCount
                          ? observation.select.minCount
                          : `${observation.select.minCount}–${observation.select.maxCount}`}{' '}
                        option(s)<span>{decision.selected.length} chosen</span>
                      </div>
                      <div className="option-list">
                        {observation.select.option.map((option, position) => (
                          <div
                            className={`option-item ${decision.selected.includes(position) ? 'chosen' : ''}`}
                            key={position}
                          >
                            <span className="option-index">
                              {decision.selected.includes(position) ? (
                                <Check size={12} />
                              ) : (
                                position
                              )}
                            </span>
                            <div>
                              <strong>{optionLabel(option, observation, catalog)}</strong>
                              {option.area !== undefined && (
                                <small>
                                  {areaNames[option.area] ?? `Area ${option.area}`}{' '}
                                  {option.index !== undefined && `· slot ${option.index + 1}`}
                                </small>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                      {!decision.selected.length && (
                        <div className="note compact">The agent chose an empty subset.</div>
                      )}
                      <div className="diagnostics">
                        <span className="eyebrow">AGENT-EMITTED DIAGNOSTICS</span>
                        <dl className="property-list">
                          <div>
                            <dt>Policy</dt>
                            <dd>{decision.diagnostics.policy}</dd>
                          </div>
                          <div>
                            <dt>Decision time</dt>
                            <dd className="mono">{decision.latency_ms.toFixed(4)} ms</dd>
                          </div>
                          <div>
                            <dt>Selected indices</dt>
                            <dd>
                              <code>[{decision.selected.join(', ')}]</code>
                            </dd>
                          </div>
                          <div>
                            <dt>Context / type</dt>
                            <dd className="mono">
                              {observation.select.context} / {observation.select.type}
                            </dd>
                          </div>
                        </dl>
                      </div>
                      <details className="event-logs">
                        <summary>Engine events ({observation.logs.length})</summary>
                        {observation.logs.map((log, i) => (
                          <div key={i}>
                            <strong>{logNames[Number(log.type)] ?? `Event ${log.type}`}</strong>
                            <code>{JSON.stringify(log)}</code>
                          </div>
                        ))}
                      </details>
                    </>
                  ) : (
                    <pre className="raw-evidence">{JSON.stringify(decision, null, 2)}</pre>
                  )}
                </div>
              </>
            )
          )}
        </aside>
      </div>
      <div className="footnote">
        <ShieldCheck size={14} />
        <span>Recorded agent-visible observations. Hidden cards stay hidden.</span>
        <span className="footnote-right">
          ← → Step <span>·</span> Space Play / pause
        </span>
      </div>
    </>
  );
}

function PlayerField({
  player,
  label,
  agentName,
  cards,
  opponent = false,
}: {
  player: Player;
  label: string;
  agentName?: string;
  cards: Map<number, CardData>;
  opponent?: boolean;
}) {
  const active = player.active[0];
  const status = (['poisoned', 'burned', 'asleep', 'paralyzed', 'confused'] as const).filter(
    (key) => player[key],
  );
  const bench = (
    <div className="bench-row">
      {Array.from({ length: Math.max(player.benchMax, player.bench.length) }, (_, index) =>
        player.bench[index] ? (
          <PokemonCard key={index} card={player.bench[index]!} cards={cards} small />
        ) : (
          <div className="empty-slot" key={index}>
            <span>+</span>
            <small>BENCH</small>
          </div>
        ),
      )}
    </div>
  );
  return (
    <div className={`player-field ${opponent ? 'opponent-field' : ''}`}>
      <div className="player-field-header">
        <div>
          <span className={`player-dot ${label === 'Candidate' ? 'candidate' : 'opponent'}`} />
          <strong>{label}</strong>
          <small>{agentName}</small>
        </div>
        <span className="zone-label">
          HAND {player.handCount} <span>·</span> DECK {player.deckCount} <span>·</span> DISCARD{' '}
          {player.discard.length}
        </span>
      </div>
      {opponent && bench}
      <div className="active-row">
        <div className="prize-zone">
          <span className="zone-label">PRIZES</span>
          <div>
            {player.prize.map((_, index) => (
              <span className="prize-card" key={index} />
            ))}
          </div>
          <strong>
            {player.prize.length}
            <small>remaining</small>
          </strong>
        </div>
        <div className="active-zone">
          {active ? (
            <PokemonCard card={active} cards={cards} />
          ) : (
            <div className="empty-active">
              <Circle size={24} />
              <span>{player.active.length ? 'Face-down Pokémon' : 'Active spot'}</span>
            </div>
          )}
          {status.length > 0 && <span className="condition">{status.join(' · ')}</span>}
        </div>
        <div className="deck-zone">
          <div className="deck-stack">
            <Layers size={24} />
          </div>
          <strong>{player.deckCount}</strong>
          <span className="zone-label">IN DECK</span>
        </div>
      </div>
      {!opponent && bench}
    </div>
  );
}

function PokemonCard({
  card,
  cards,
  small = false,
}: {
  card: BoardCard;
  cards: Map<number, CardData>;
  small?: boolean;
}) {
  const metadata = cards.get(card.id);
  const energy = metadata?.energyType ?? 0;
  const icons = [
    Circle,
    Leaf,
    Flame,
    Droplets,
    Zap,
    Sparkles,
    Mountain,
    Moon,
    ShieldCheck,
    Snowflake,
    Sparkles,
    Moon,
  ];
  const Icon = icons[energy] ?? Circle;
  return (
    <div
      className={`pokemon-card energy-${energy} ${small ? 'mini' : ''}`}
      title={`${metadata?.name ?? `Card #${card.id}`} · ${card.hp ?? '?'} HP`}
    >
      <div className="pokemon-card-heading">
        <strong>{metadata?.name ?? `Card #${card.id}`}</strong>
        <span>
          {card.hp ?? metadata?.hp ?? '—'} <small>HP</small>
        </span>
      </div>
      <div className="pokemon-illustration">
        <Icon size={small ? 24 : 38} strokeWidth={1.2} />
        <span>#{card.id}</span>
      </div>
      {!small && (
        <div className="pokemon-meta">
          <span>{metadata?.stage2 ? 'STAGE 2' : metadata?.stage1 ? 'STAGE 1' : 'BASIC'}</span>
          <span>{card.energies?.length ?? 0} ENERGY</span>
        </div>
      )}
      {card.maxHp !== undefined && (
        <div className="hp-track">
          <span
            style={{
              width: `${Math.min(100, Math.max(0, ((card.hp ?? 0) / Math.max(1, card.maxHp)) * 100))}%`,
            }}
          />
        </div>
      )}
      <div className="energy-dots">
        {card.energies?.map((type, i) => (
          <span className={`energy-mark energy-${type}`} key={i} />
        ))}
      </div>
    </div>
  );
}
