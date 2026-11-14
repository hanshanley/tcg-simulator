export type Agent = {
  id: string;
  name: string;
  version: string;
  description: string;
  artifact_sha256: string;
};
export type Deck = {
  id: string;
  name: string;
  cards: number[];
  version: number;
  description: string;
  sha256: string;
  created_at: string;
};
export type CardData = {
  cardId: number;
  name: string;
  hp: number;
  cardType: number;
  energyType: number;
  basic: boolean;
  stage1: boolean;
  stage2: boolean;
  attacks: number[];
  skills: { name: string; text: string }[];
};
export type Attack = { attackId: number; name: string; damage: number; text: string };
export type Engine = {
  name: string;
  package_version: string;
  rules_version: number;
  adapter_version: string;
  native_sha256: string;
  platform: string;
  deterministic_reruns: boolean;
};
export type Catalog = { cards: CardData[]; attacks: Attack[]; agents: Agent[]; engine: Engine };
export type Game = {
  id: string;
  experiment_id: string;
  number: number;
  status: string;
  winner: number | null;
  decision_count: number;
  duration_ms: number;
  p95_latency_ms: number | null;
  turns: number;
  first_player: number;
  error?: string;
};
export type Summary = {
  wins: number;
  losses: number;
  draws: number;
  completed: number;
  failed: number;
  capped: number;
  win_rate: number | null;
  win_rate_ci: [number, number] | null;
  decisions: number;
  duration_ms: number;
};
export type Experiment = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  error?: string;
  config: {
    games: number;
    agent_ids: [string, string];
    deck_ids: [string, string];
    policy_seed: number;
    max_decisions: number;
    timeout_seconds: number;
  };
  agents: [Agent, Agent];
  decks: [Deck, Deck];
  engine: Engine;
  games: Game[];
  summary: Summary;
};
export type BoardCard = {
  id: number;
  serial: number;
  hp?: number;
  maxHp?: number;
  energies?: number[];
  tools?: BoardCard[];
  preEvolution?: BoardCard[];
};
export type Player = {
  active: (BoardCard | null)[];
  bench: (BoardCard | null)[];
  benchMax: number;
  hand: (BoardCard | null)[] | null;
  handCount: number;
  deckCount: number;
  discard: BoardCard[];
  prize: (BoardCard | null)[];
  poisoned: boolean;
  burned: boolean;
  asleep: boolean;
  paralyzed: boolean;
  confused: boolean;
};
export type Option = {
  type: number;
  index?: number;
  area?: number;
  playerIndex?: number;
  inPlayArea?: number;
  inPlayIndex?: number;
  attackId?: number;
  cardId?: number;
  number?: number;
};
export type Observation = {
  current: {
    turn: number;
    yourIndex: number;
    firstPlayer: number;
    result: number;
    players: [Player, Player];
    stadium: (BoardCard | null)[];
  };
  select: {
    type: number;
    context: number;
    minCount: number;
    maxCount: number;
    option: Option[];
    deck: BoardCard[] | null;
  };
  logs: Record<string, unknown>[];
};
export type Decision = {
  index: number;
  player: number;
  observation: Observation;
  selected: number[];
  latency_ms: number;
  diagnostics: { policy: string; selected_count: number };
};
export type Replay = {
  id: string;
  experiment_id: string;
  number: number;
  status: string;
  winner: number | null;
  decisions: Decision[];
  final_observation: Observation | null;
  bookmarks: { decision: number; label: string }[];
  error?: string;
};
