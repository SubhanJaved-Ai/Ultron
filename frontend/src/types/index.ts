// --- SSE Event Types ---

export interface SSEEvent {
  event?: string;
  data: string;
}

export interface AgentTurnStartEvent {
  agent: string;
  input: string;
}

export interface InferenceStartEvent {
  model: string;
  engine: string;
  turn: number;
}

export interface InferenceEndEvent {
  model: string;
  engine: string;
  turn: number;
}

export interface ToolCallStartEvent {
  tool: string;
  arguments: string;
}

export interface ToolCallEndEvent {
  tool: string;
  success: boolean;
  latency: number;
}

// --- Chat Types ---

export interface ToolCallInfo {
  id: string;
  tool: string;
  arguments: string;
  status: 'running' | 'success' | 'error';
  result?: string;
  latency?: number;
  /** The model that dispatched this tool call (e.g. "gemini-2.5-flash") */
  model?: string;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface MessageTelemetry {
  engine?: string;
  model_id?: string;
  tokens_per_sec?: number;
  ttft_ms?: number;
  total_ms?: number;
  complexity_score?: number;
  complexity_tier?: string;
  suggested_max_tokens?: number;
}

export interface TimeRange {
  start?: string;
  end?: string;
}

export interface ResearchSource {
  ref: number;
  title?: string;
  sender?: string;
  date?: string;
  url?: string;
}

export interface ResearchSearchTrace {
  id: string;
  query: string;
  person?: string;
  timeRange?: TimeRange | string;
  status: 'pending' | 'complete';
  numHits?: number;
  topTitles?: string[];
}

export type ResearchEvent =
  | {
      type: 'search_call';
      arguments: {
        query: string;
        person?: string;
        time_range?: TimeRange | string;
      };
    }
  | {
      type: 'search_result';
      num_hits: number;
      top_titles?: string[];
      sources?: ResearchSource[];
    }
  | { type: 'synthesis'; text: string }
  | {
      type: 'system_metrics';
      power_w: number;
      energy_j: number;
      duration_s: number;
    }
  | { type: 'done'; usage?: TokenUsage }
  | { type: 'error'; message: string };

export interface LiveEnergyMetrics {
  power_w: number;
  energy_j: number;
  duration_s: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  toolCalls?: ToolCallInfo[];
  researchTraces?: ResearchSearchTrace[];
  researchSources?: ResearchSource[];
  isResearch?: boolean;
  usage?: TokenUsage;
  telemetry?: MessageTelemetry;
  audio?: { url: string };
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  model: string;
  messages: ChatMessage[];
}

export interface ConversationStore {
  version: 1;
  conversations: Record<string, Conversation>;
  activeId: string | null;
}

// --- Stream State ---

export interface StreamState {
  conversationId: string | null;
  isStreaming: boolean;
  phase: string;
  elapsedMs: number;
  activeToolCalls: ToolCallInfo[];
  content: string;
  /** The model currently being used for inference */
  activeModel?: string;
}

// --- API Types ---

export interface ModelInfo {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

export interface ProviderSavings {
  provider: string;
  label: string;
  input_cost: number;
  output_cost: number;
  total_cost: number;
  energy_wh: number;
  energy_joules: number;
  flops: number;
}

export interface SavingsData {
  total_calls: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  local_cost: number;
  per_provider: ProviderSavings[];
  token_counting_version?: number;
}

export interface ServerInfo {
  model: string;
  agent: string | null;
  engine: string;
}

// --- Log Types ---

export interface LogEntry {
  timestamp: number;
  level: 'info' | 'warn' | 'error';
  category: 'server' | 'model' | 'chat' | 'tool';
  message: string;
}

// --- Persistent Task Types ---

export type TaskStatus =
  | 'queued'
  | 'running'
  | 'paused'
  | 'waiting_approval'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type StepStatus =
  | 'pending'
  | 'running'
  | 'waiting_approval'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'skipped';

export interface TaskStep {
  step_id: string;
  task_id: string;
  step_index: number;
  title: string;
  tool_name: string;
  tool_args?: Record<string, any>;
  dependencies?: string[];
  expected_output?: string;
  actual_output?: string;
  status: StepStatus;
  error?: string | null;
  retry_count: number;
  max_retries: number;
  requires_code?: boolean;
  requires_user_input?: boolean;
  approval_token?: string | null;
  safety_decision?: {
    uncertain_external_action?: boolean;
    tool_name?: string;
    error?: string;
    duplicate_action_risk?: string;
    force_retry_warning?: string;
    force_retry_authorized?: boolean;
    risk_level?: string;
    reason?: string;
    operator_confirmed_duplicate_risk?: boolean;
    uncertain_resolved?: string;
    [key: string]: any;
  } | null;
  artifacts?: string[];
  started_at?: number | null;
  finished_at?: number | null;
}

export interface TaskRecord {
  task_id: string;
  prompt: string;
  status: TaskStatus;
  created_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  current_step_index: number;
  error?: string | null;
  steps: TaskStep[];
  metadata: Record<string, any>;
}

// --- Memory & Skills Control Center Types ---

export interface MemoryFact {
  id: string;
  text: string;
  source: string;
  source_type: string;
  is_external_untrusted_source: boolean;
  created_at: number;
  updated_at: number;
  trust: 'trusted' | 'auto' | 'untrusted';
  trusted_for_recall: boolean;
  category: string;
  project: string;
  verified: boolean;
  metadata: Record<string, any>;
}

export interface MemoryFactsResponse {
  status: string;
  memories: MemoryFact[];
  total: number;
  offset: number;
  limit: number;
  categories: string[];
  projects: string[];
  stats: {
    total_facts: number;
    trusted_count: number;
    auto_count: number;
    untrusted_count: number;
    verified_count: number;
    unverified_count: number;
  };
}

export interface SkillStepInfo {
  tool_name: string;
  skill_name?: string;
  arguments_template: string;
  output_key: string;
}

export interface SkillHealthInfo {
  is_healthy: boolean;
  issues: string[];
  consecutive_failures: number;
  execution_count: number;
  last_success_at?: number | null;
  last_failure_at?: number | null;
  last_failure_reason?: string | null;
  outdated: boolean;
  outdated_reason?: string | null;
}

export interface SkillValidationInfo {
  is_valid: boolean;
  errors: string[];
}

export interface SkillLedgerRecord {
  id: string;
  timestamp: number;
  action: string;
  skill_name: string;
  author: string;
  user_id?: string;
  description: string;
  reason?: string;
  before_manifest?: Record<string, string>;
  after_manifest?: Record<string, string>;
}

export interface LearnedSkill {
  name: string;
  version: string;
  description: string;
  author: string;
  tags: string[];
  required_capabilities: string[];
  depends: string[];
  user_invocable: boolean;
  disable_model_invocation: boolean;
  approval_status: 'draft' | 'pending_review' | 'approved' | 'rejected';
  approved: boolean;
  disabled: boolean;
  disabled_reason?: string | null;
  is_protected: boolean;
  steps_count: number;
  steps: SkillStepInfo[];
  health: SkillHealthInfo;
  validation: SkillValidationInfo;
  is_composite?: boolean;
  metadata: Record<string, any>;
  audit_history?: SkillLedgerRecord[];
}

export interface CreateCompositeSkillStep {
  tool_name?: string;
  skill_name?: string;
  arguments_template?: string;
  output_key?: string;
  condition?: string;
  is_else?: boolean;
  else_skill_name?: string;
  else_tool_name?: string;
  else_arguments_template?: string;
  else_output_key?: string;
}

export interface CreateCompositeSkillRequest {
  name: string;
  description?: string;
  steps: CreateCompositeSkillStep[];
  require_approval?: boolean;
  tags?: string[];
}

export interface ValidateCompositeSkillResponse {
  valid: boolean;
  errors: string[];
  required_capabilities: string[];
  dependencies: string[];
}

export interface CreateCompositeSkillResponse {
  status: string;
  skill: LearnedSkill;
}

export interface LearnedSkillsResponse {
  status: string;
  skills: LearnedSkill[];
  total: number;
  stats: {
    total_skills: number;
    pending_count: number;
    approved_count: number;
    disabled_count: number;
    rejected_count: number;
  };
}

export interface MaintenanceSuggestion {
  id: string;
  issue_type: 'duplicate' | 'contradiction' | 'outdated';
  project: string;
  category: string;
  reason: string;
  source_fact_ids: string[];
  source_facts: MemoryFact[];
  proposed_action: 'merge' | 'supersede' | 'delete' | 'mark_for_review';
  proposed_resolution: {
    target_fact_id?: string;
    merged_text?: string;
    facts_to_remove?: string[];
    keep_fact_id?: string;
    superseded_fact_id?: string;
    retire_fact_id?: string;
    action_detail?: string;
    quarantined_warning?: boolean;
    [key: string]: any;
  };
  quarantined_involved: boolean;
  status: 'pending' | 'approved' | 'dismissed';
  created_at: number;
  resolved_at?: number | null;
  resolved_by?: string | null;
  dismiss_reason?: string | null;
}

export interface MaintenanceScanResponse {
  status: string;
  suggestions: MaintenanceSuggestion[];
  total: number;
}

