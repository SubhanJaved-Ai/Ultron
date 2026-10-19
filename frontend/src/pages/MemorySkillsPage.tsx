import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Brain,
  Sparkles,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Search,
  Plus,
  Trash2,
  Edit3,
  Lock,
  PauseCircle,
  PlayCircle,
  XCircle,
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Layers,
  FileText,
  Globe,
  Mail,
  Terminal,
  ListTodo,
  User,
  History,
  Copy,
  Wrench,
  Activity,
  ArrowUp,
  ArrowDown,
  GitBranch,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  fetchMemoryFacts,
  createMemoryFact,
  updateMemoryFact,
  deleteMemoryFact,
  fetchLearnedSkills,
  fetchLearnedSkillDetail,
  approveLearnedSkill,
  rejectLearnedSkill,
  disableLearnedSkill,
  enableLearnedSkill,
  validateCompositeSkill,
  createCompositeSkill,
  scanMemoryMaintenance,
  fetchMaintenanceSuggestions,
  approveMaintenanceSuggestion,
  dismissMaintenanceSuggestion,
} from '../lib/api';
import type {
  MemoryFact,
  MemoryFactsResponse,
  LearnedSkill,
  LearnedSkillsResponse,
  SkillLedgerRecord,
  MaintenanceSuggestion,
  MaintenanceScanResponse,
  CreateCompositeSkillStep,
  CreateCompositeSkillRequest,
  ValidateCompositeSkillResponse,
} from '../types';

export function MemoryTrustBadge({ trust }: { trust: string }) {
  if (trust === 'trusted') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        <ShieldCheck size={11} />
        <span>TRUSTED</span>
      </span>
    );
  }
  if (trust === 'untrusted') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40">
        <ShieldAlert size={11} />
        <span>QUARANTINED</span>
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-sky-500/15 text-sky-400 border border-sky-500/30">
      <Brain size={11} />
      <span>AUTO</span>
    </span>
  );
}

export function SkillStatusBadge({
  status,
  disabled,
  disabledReason,
}: {
  status: string;
  disabled?: boolean;
  disabledReason?: string | null;
}) {
  if (disabled) {
    return (
      <span
        title={disabledReason || 'Skill is disabled'}
        className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-700/50 text-slate-300 border border-slate-600"
      >
        <PauseCircle size={11} />
        <span>DISABLED</span>
      </span>
    );
  }
  if (status === 'approved') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
        <CheckCircle2 size={11} />
        <span>APPROVED & ACTIVE</span>
      </span>
    );
  }
  if (status === 'pending_review' || status === 'draft') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse">
        <AlertTriangle size={11} />
        <span>PENDING REVIEW</span>
      </span>
    );
  }
  if (status === 'rejected') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
        <XCircle size={11} />
        <span>REJECTED</span>
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300">
      {status.toUpperCase()}
    </span>
  );
}

export function SkillValidationChecklist({
  validation,
}: {
  validation: { is_valid: boolean; errors: string[] };
}) {
  return (
    <div
      className={`p-3.5 rounded-xl border flex flex-col gap-2 ${
        validation.is_valid
          ? 'bg-emerald-500/5 border-emerald-500/30 text-emerald-300'
          : 'bg-rose-500/10 border-rose-500/40 text-rose-300'
      }`}
    >
      <div className="flex items-center justify-between text-xs font-bold">
        <span className="flex items-center gap-1.5">
          {validation.is_valid ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span>Pre-Approval Security & Schema Validation</span>
        </span>
        <span>{validation.is_valid ? 'PASSED' : 'ACTION REQUIRED'}</span>
      </div>
      {validation.is_valid ? (
        <p className="text-[11px] opacity-90">
          All workflow tools are registered, argument templates are valid JSON, dependency keys resolve
          topologically, and required capabilities are fully declared.
        </p>
      ) : (
        <div className="flex flex-col gap-1 text-[11px]">
          <span>Execution and approval are blocked due to the following issues:</span>
          <ul className="list-disc list-inside space-y-0.5 font-mono text-[10.5px]">
            {validation.errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function StepDAGPipeline({
  steps,
}: {
  steps: Array<{
    tool_name?: string;
    skill_name?: string;
    arguments_template?: string;
    output_key?: string;
  }>;
}) {
  return (
    <div className="flex flex-col gap-2">
      {steps.map((st, i) => (
        <div key={i} className="p-3 rounded-lg border border-slate-800 bg-slate-900/70 flex flex-col gap-1.5 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-semibold flex items-center gap-1.5">
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  st.skill_name ? 'bg-purple-500/20 text-purple-400' : 'bg-sky-500/20 text-sky-400'
                }`}
              >
                {i + 1}
              </span>
              {st.skill_name ? (
                <>
                  <span className="text-purple-300">Sub-Skill:</span>{' '}
                  <code className="text-purple-200">{st.skill_name}</code>
                </>
              ) : (
                <>
                  <span className="text-sky-300">Tool:</span>{' '}
                  <code className="text-slate-100">{st.tool_name}</code>
                </>
              )}
            </span>
            {st.output_key && (
              <span className="text-[10px] font-mono text-slate-400 bg-slate-800 px-1.5 py-0.5 rounded">
                output: {st.output_key}
              </span>
            )}
          </div>
          {st.arguments_template && (
            <pre className="p-2 rounded bg-black/50 text-[10.5px] font-mono text-slate-300 overflow-x-auto">
              {st.arguments_template}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}

export function SkillAuditLedger({ ledger }: { ledger: SkillLedgerRecord[] }) {
  return (
    <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
      {ledger.map((entry, idx) => (
        <div
          key={idx}
          className="p-2 rounded bg-slate-900/70 border border-slate-800 text-[11px] flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${
                entry.action === 'approved'
                  ? 'bg-emerald-500/20 text-emerald-300'
                  : entry.action === 'rejected'
                  ? 'bg-rose-500/20 text-rose-300'
                  : entry.action === 'disabled'
                  ? 'bg-amber-500/20 text-amber-300'
                  : entry.action === 'enabled'
                  ? 'bg-sky-500/20 text-sky-300'
                  : 'bg-slate-800 text-slate-300'
              }`}
            >
              {entry.action}
            </span>
            <span className="text-slate-300">by {entry.user_id || entry.author || 'system'}</span>
            {(entry.reason || entry.description) && (
              <span className="text-slate-400 italic">"{entry.reason || entry.description}"</span>
            )}
          </div>
          <span className="text-[10px] text-slate-400">
            {entry.timestamp ? new Date(entry.timestamp * 1000).toLocaleString() : ''}
          </span>
        </div>
      ))}
    </div>
  );
}

export function MaintenanceIssueBadge({ issueType }: { issueType: string }) {
  if (issueType === 'duplicate') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
        <Copy size={11} />
        <span>DUPLICATE</span>
      </span>
    );
  }
  if (issueType === 'contradiction') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
        <AlertTriangle size={11} />
        <span>CONTRADICTION</span>
      </span>
    );
  }
  if (issueType === 'outdated') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30">
        <History size={11} />
        <span>OUTDATED</span>
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300">
      {issueType.toUpperCase()}
    </span>
  );
}

export function ProposedActionBadge({ action }: { action: string }) {
  if (action === 'merge') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">
        <Layers size={11} />
        <span>MERGE</span>
      </span>
    );
  }
  if (action === 'supersede') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
        <RefreshCw size={11} />
        <span>SUPERSEDE</span>
      </span>
    );
  }
  if (action === 'delete') {
    return (
      <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
        <Trash2 size={11} />
        <span>RETIRE</span>
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300">
      {action.toUpperCase()}
    </span>
  );
}

export function SkillCompositionValidationBanner({
  validationResult,
}: {
  validationResult: ValidateCompositeSkillResponse;
}) {
  return (
    <div
      className={`p-3 rounded-xl border flex flex-col gap-2 ${
        validationResult.valid
          ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
          : 'bg-rose-500/10 border-rose-500/40 text-rose-300'
      }`}
    >
      <div className="flex items-center justify-between text-xs font-bold">
        <span className="flex items-center gap-1.5">
          {validationResult.valid ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span>{validationResult.valid ? 'Validation Passed' : 'Validation Failed'}</span>
        </span>
        <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-black/40">
          {validationResult.valid ? 'Safe to Submit' : 'Action Required'}
        </span>
      </div>

      {validationResult.valid ? (
        <div className="flex flex-col gap-1.5 text-xs">
          <p className="text-[11px] text-slate-300">
            Cycle detection confirmed no circular dependencies, recursion depth is within limits, and all child skills are approved.
          </p>
          {validationResult.required_capabilities.length > 0 && (
            <div className="flex flex-wrap items-center gap-1 mt-1">
              <span className="text-[10px] text-slate-400">Aggregated Capabilities:</span>
              {validationResult.required_capabilities.map((cap) => (
                <span
                  key={cap}
                  className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-500/20 text-purple-300 border border-purple-500/30"
                >
                  {cap}
                </span>
              ))}
            </div>
          )}
          {validationResult.dependencies.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-[10px] text-slate-400">Skill Dependencies:</span>
              {validationResult.dependencies.map((dep) => (
                <span
                  key={dep}
                  className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-sky-500/20 text-sky-300 border border-sky-500/30"
                >
                  {dep}
                </span>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-1 text-[11px]">
          <span>Execution and creation are blocked due to validation issues:</span>
          <ul className="list-disc list-inside space-y-0.5 font-mono text-[10.5px]">
            {validationResult.errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function SkillCompositionDraftCard({
  skill,
  onReset,
  onClose,
}: {
  skill: LearnedSkill;
  onReset?: () => void;
  onClose?: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between border-b pb-3 border-slate-800">
        <div className="flex items-center gap-2">
          <Layers className="text-purple-400" size={20} />
          <h2 className="text-base font-bold text-slate-100">Skill Composer</h2>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Close Composer"
            className="text-slate-400 hover:text-slate-200 cursor-pointer"
          >
            ✕
          </button>
        )}
      </div>

      <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 flex flex-col gap-3">
        <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
          <CheckCircle2 size={18} />
          <span>Composite Skill Draft Created Successfully</span>
        </div>
        <p className="text-xs text-slate-300">
          Workflow <code className="text-white font-mono bg-slate-900 px-1.5 py-0.5 rounded">{skill.name}</code> has been registered with {skill.steps_count} workflow steps.
        </p>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-slate-400">Current Status:</span>
          <SkillStatusBadge status={skill.approval_status} />
        </div>
        {skill.required_capabilities && skill.required_capabilities.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 mt-1">
            <span className="text-[11px] text-slate-400">Inherited Capabilities:</span>
            {skill.required_capabilities.map((cap) => (
              <span
                key={cap}
                className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-500/20 text-purple-300 border border-purple-500/30"
              >
                {cap}
              </span>
            ))}
          </div>
        )}
        <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs mt-2">
          <ShieldAlert size={16} className="shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold">Security &amp; Authorization Policy:</span> Newly composed skills are placed into <code className="text-amber-200 font-mono">pending_review</code> status. Execution is prohibited until an operator authorizes the skill in the Learned Skills review queue.
          </div>
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 pt-2">
        {onReset && (
          <button
            onClick={onReset}
            className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
          >
            Compose Another Skill
          </button>
        )}
        {onClose && (
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium cursor-pointer"
          >
            Done
          </button>
        )}
      </div>
    </div>
  );
}

export interface SkillComposerProps {
  availableSkills: LearnedSkill[];
  onSkillCreated?: (skill: LearnedSkill) => void;
  onClose?: () => void;
}

export function SkillComposer({
  availableSkills,
  onSkillCreated,
  onClose,
}: SkillComposerProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('composition, workflow');
  const [requireApproval, setRequireApproval] = useState(true);
  const [steps, setSteps] = useState<CreateCompositeSkillStep[]>([
    {
      skill_name: '',
      arguments_template: '{}',
      output_key: 'step1_out',
    },
  ]);

  const [validationResult, setValidationResult] = useState<ValidateCompositeSkillResponse | null>(null);
  const [validating, setValidating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [createdSkill, setCreatedSkill] = useState<LearnedSkill | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const approvedSkills = useMemo(
    () => availableSkills.filter((s) => s.approval_status === 'approved' && !s.disabled),
    [availableSkills],
  );

  const otherSkills = useMemo(
    () => availableSkills.filter((s) => s.approval_status !== 'approved' || s.disabled),
    [availableSkills],
  );

  const getPrecedingOutputs = (stepIdx: number) => {
    const outputs: string[] = [];
    for (let i = 0; i < stepIdx; i++) {
      const st = steps[i];
      if (st?.output_key && st.output_key.trim()) {
        outputs.push(st.output_key.trim());
      }
    }
    return outputs;
  };

  const handleSelectSkill = (idx: number, skillName: string) => {
    setValidationResult(null);
    setValidationError(null);
    const updated = [...steps];
    const existing = updated[idx];
    if (!existing) return;
    updated[idx] = {
      ...existing,
      skill_name: skillName,
      arguments_template:
        existing.arguments_template && existing.arguments_template !== '{}'
          ? existing.arguments_template
          : '{}',
    };
    setSteps(updated);
  };

  const handleAddStep = () => {
    setValidationResult(null);
    setValidationError(null);
    setSteps([
      ...steps,
      {
        skill_name: '',
        arguments_template: '{}',
        output_key: `step${steps.length + 1}_out`,
      },
    ]);
  };

  const handleRemoveStep = (idx: number) => {
    if (steps.length <= 1) {
      toast.error('A composite skill requires at least one workflow step.');
      return;
    }
    setValidationResult(null);
    setValidationError(null);
    setSteps(steps.filter((_, i) => i !== idx));
  };

  const handleMoveUp = (idx: number) => {
    if (idx === 0) return;
    setValidationResult(null);
    setValidationError(null);
    const updated = [...steps];
    const prev = updated[idx - 1];
    const curr = updated[idx];
    if (prev && curr) {
      updated[idx - 1] = curr;
      updated[idx] = prev;
      setSteps(updated);
    }
  };

  const handleMoveDown = (idx: number) => {
    if (idx >= steps.length - 1) return;
    setValidationResult(null);
    setValidationError(null);
    const updated = [...steps];
    const curr = updated[idx];
    const next = updated[idx + 1];
    if (curr && next) {
      updated[idx] = next;
      updated[idx + 1] = curr;
      setSteps(updated);
    }
  };

  const handleTemplateChange = (idx: number, val: string) => {
    setValidationResult(null);
    setValidationError(null);
    const updated = [...steps];
    const existing = updated[idx];
    if (!existing) return;
    updated[idx] = { ...existing, arguments_template: val };
    setSteps(updated);
  };

  const handleOutputKeyChange = (idx: number, val: string) => {
    setValidationResult(null);
    setValidationError(null);
    const updated = [...steps];
    const existing = updated[idx];
    if (!existing) return;
    updated[idx] = { ...existing, output_key: val };
    setSteps(updated);
  };

  const handleInsertToken = (stepIdx: number, token: string) => {
    setValidationResult(null);
    setValidationError(null);
    const current = steps[stepIdx]?.arguments_template || '{}';
    let nextVal = current;
    if (current.trim() === '{}') {
      nextVal = `{\n  "input": "{${token}}"\n}`;
    } else {
      nextVal = current + ` "{${token}}"`;
    }
    handleTemplateChange(stepIdx, nextVal);
  };

  const handleConditionChange = (idx: number, val: string) => {
    setValidationResult(null);
    setValidationError(null);
    const updated = [...steps];
    const existing = updated[idx];
    if (!existing) return;
    updated[idx] = { ...existing, condition: val, is_else: false };
    setSteps(updated);
  };

  const handleToggleElse = (idx: number, isElse: boolean) => {
    setValidationResult(null);
    setValidationError(null);
    const updated = [...steps];
    const existing = updated[idx];
    if (!existing) return;
    updated[idx] = {
      ...existing,
      is_else: isElse,
      condition: isElse ? 'else' : '',
    };
    setSteps(updated);
  };

  const handleSelectElseSkill = (idx: number, skillName: string) => {
    setValidationResult(null);
    setValidationError(null);
    const updated = [...steps];
    const existing = updated[idx];
    if (!existing) return;
    updated[idx] = { ...existing, else_skill_name: skillName };
    setSteps(updated);
  };

  const handleInsertConditionToken = (stepIdx: number, token: string) => {
    setValidationResult(null);
    setValidationError(null);
    const current = steps[stepIdx]?.condition || '';
    let nextVal = current;
    if (!current.trim()) {
      nextVal = `{${token}} == 'success'`;
    } else {
      nextVal = current + ` {${token}}`;
    }
    handleConditionChange(stepIdx, nextVal);
  };

  const runValidation = async (): Promise<ValidateCompositeSkillResponse | null> => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setValidationError('Skill name is required.');
      return null;
    }
    if (steps.length === 0) {
      setValidationError('At least one workflow step is required.');
      return null;
    }
    const hasEmpty = steps.some((s) => !s.skill_name || !s.skill_name.trim());
    if (hasEmpty) {
      setValidationError('All workflow steps must select a child skill.');
      return null;
    }

    setValidating(true);
    setValidationError(null);
    try {
      const parsedTags = tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await validateCompositeSkill({
        name: trimmedName,
        description: description.trim(),
        steps,
        require_approval: requireApproval,
        tags: parsedTags,
      });
      setValidationResult(res);
      if (!res.valid) {
        setValidationError(res.errors.join('; '));
      }
      return res;
    } catch (err: any) {
      const msg = err.message || 'Validation request failed';
      setValidationError(msg);
      setValidationResult({
        valid: false,
        errors: [msg],
        required_capabilities: [],
        dependencies: [],
      });
      return null;
    } finally {
      setValidating(false);
    }
  };

  const handleCreate = async () => {
    const valRes = await runValidation();
    if (!valRes || !valRes.valid) {
      toast.error('Resolve validation errors before creating the composite skill.');
      return;
    }

    setSubmitting(true);
    try {
      const parsedTags = tags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await createCompositeSkill({
        name: name.trim(),
        description: description.trim(),
        steps,
        require_approval: true, // Always enforce approval requirement on newly created composite skills
        tags: parsedTags,
      });
      setCreatedSkill(res.skill);
      toast.success(`Composite skill '${res.skill.name}' created in pending review status.`);
      if (onSkillCreated) {
        onSkillCreated(res.skill);
      }
    } catch (err: any) {
      const msg = err.message || 'Failed to create composite skill';
      toast.error(msg);
      setValidationError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (createdSkill) {
    return (
      <SkillCompositionDraftCard
        skill={createdSkill}
        onReset={() => {
          setCreatedSkill(null);
          setName('');
          setDescription('');
          setSteps([{ skill_name: '', arguments_template: '{}', output_key: 'step1_out' }]);
          setValidationResult(null);
        }}
        onClose={onClose}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b pb-3 border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="text-purple-400" size={20} />
            <h2 className="text-base font-bold text-slate-100">Skill Composer</h2>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
              Safe Composition
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Combine multiple approved skills into a larger reusable workflow.
          </p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Close Composer"
            className="text-slate-400 hover:text-slate-200 cursor-pointer"
          >
            ✕
          </button>
        )}
      </div>

      {/* Form Fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
        <div className="flex flex-col gap-1.5">
          <label className="font-semibold text-slate-200">
            Composite Skill Name *
          </label>
          <input
            type="text"
            aria-label="Composite Skill Name"
            placeholder="e.g. repo_audit_and_cleanup"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setValidationResult(null);
            }}
            className="p-2.5 rounded-lg border border-slate-700 bg-slate-900 text-slate-100 outline-none text-xs font-mono"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="font-semibold text-slate-200">Tags</label>
          <input
            type="text"
            aria-label="Skill Tags"
            placeholder="e.g. security, audit, composite"
            value={tags}
            onChange={(e) => {
              setTags(e.target.value);
              setValidationResult(null);
            }}
            className="p-2.5 rounded-lg border border-slate-700 bg-slate-900 text-slate-100 outline-none text-xs"
          />
        </div>

        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <label className="font-semibold text-slate-200">Description</label>
          <textarea
            aria-label="Composite Skill Description"
            placeholder="Describe what this composite workflow accomplishes..."
            value={description}
            onChange={(e) => {
              setDescription(e.target.value);
              setValidationResult(null);
            }}
            rows={2}
            className="p-2.5 rounded-lg border border-slate-700 bg-slate-900 text-slate-100 outline-none text-xs resize-none"
          />
        </div>
      </div>

      {/* Steps Pipeline Builder */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
            <Sparkles size={14} className="text-purple-400" />
            <span>Workflow Steps Pipeline ({steps.length} Step{steps.length !== 1 ? 's' : ''})</span>
          </h3>
          <button
            onClick={handleAddStep}
            aria-label="Add Step"
            className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/30 transition-colors cursor-pointer"
          >
            <Plus size={12} />
            <span>Add Step</span>
          </button>
        </div>

        {/* Step Cards List */}
        <div className="flex flex-col gap-3 max-h-[42vh] overflow-y-auto pr-1">
          {steps.map((st, idx) => {
            const preceding = getPrecedingOutputs(idx);
            return (
              <div
                key={idx}
                data-testid={`composite-step-${idx}`}
                className="p-3.5 rounded-xl border border-slate-800 bg-slate-900/60 flex flex-col gap-2.5 text-xs"
              >
                {/* Step Top Bar */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 flex-1 mr-2">
                    <span className="w-5 h-5 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-[10px] font-bold">
                      {idx + 1}
                    </span>
                    <select
                      aria-label={`Step ${idx + 1} Child Skill`}
                      value={st.skill_name || ''}
                      onChange={(e) => handleSelectSkill(idx, e.target.value)}
                      className="p-1.5 rounded-lg border border-slate-700 bg-slate-900 text-slate-100 text-xs font-mono flex-1 outline-none"
                    >
                      <option value="">-- Select Child Skill --</option>
                      {approvedSkills.length > 0 && (
                        <optgroup label="Approved Skills (Ready for Composition)">
                          {approvedSkills.map((sk) => (
                            <option key={sk.name} value={sk.name}>
                              {sk.name} (v{sk.version})
                            </option>
                          ))}
                        </optgroup>
                      )}
                      {otherSkills.length > 0 && (
                        <optgroup label="Unapproved or Disabled (Will Block Execution)">
                          {otherSkills.map((sk) => (
                            <option key={sk.name} value={sk.name}>
                              {sk.name} {sk.disabled ? '[Disabled]' : `[${sk.approval_status}]`}
                            </option>
                          ))}
                        </optgroup>
                      )}
                    </select>
                  </div>

                  {/* Reorder and Delete controls */}
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleMoveUp(idx)}
                      disabled={idx === 0}
                      aria-label={`Move Step ${idx + 1} Up`}
                      className="p-1 rounded hover:bg-slate-800 text-slate-400 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                      title="Move Step Up"
                    >
                      <ArrowUp size={13} />
                    </button>
                    <button
                      onClick={() => handleMoveDown(idx)}
                      disabled={idx === steps.length - 1}
                      aria-label={`Move Step ${idx + 1} Down`}
                      className="p-1 rounded hover:bg-slate-800 text-slate-400 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                      title="Move Step Down"
                    >
                      <ArrowDown size={13} />
                    </button>
                    <button
                      onClick={() => handleRemoveStep(idx)}
                      disabled={steps.length <= 1}
                      aria-label={`Remove Step ${idx + 1}`}
                      className="p-1 rounded hover:bg-rose-500/20 text-rose-400 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                      title="Remove Step"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* Branch Condition Configuration */}
                <div className="p-2.5 rounded-lg border border-slate-800/80 bg-slate-950/40 flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-slate-300 font-medium text-[11px]">
                      <GitBranch size={13} className="text-purple-400" />
                      <span>Branch Condition</span>
                      {st.is_else ? (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                          ELSE BRANCH
                        </span>
                      ) : st.condition ? (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                          CONDITIONAL IF
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded text-[9px] text-slate-400 bg-slate-800">
                          SEQUENTIAL
                        </span>
                      )}
                    </div>
                    {idx > 0 && (
                      <label className="flex items-center gap-1.5 cursor-pointer text-[11px] text-slate-400 hover:text-slate-200">
                        <input
                          type="checkbox"
                          aria-label={`Step ${idx + 1} Is Else Branch`}
                          checked={st.is_else || false}
                          onChange={(e) => handleToggleElse(idx, e.target.checked)}
                          className="rounded border-slate-700 bg-slate-900 text-purple-600 focus:ring-0"
                        />
                        <span>Else branch of Step {idx}</span>
                      </label>
                    )}
                  </div>

                  {!st.is_else && (
                    <div className="flex flex-col gap-1.5">
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          aria-label={`Step ${idx + 1} Condition`}
                          placeholder="e.g. {step1_out} == 'success' or {count} > 0"
                          value={st.condition || ''}
                          onChange={(e) => handleConditionChange(idx, e.target.value)}
                          className="flex-1 p-1.5 rounded bg-slate-900 border border-slate-800 text-[11px] font-mono text-slate-200 outline-none"
                        />
                      </div>
                      {preceding.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1">
                          <span className="text-[10px] text-slate-400">Condition Tokens:</span>
                          {preceding.map((outKey) => (
                            <button
                              key={outKey}
                              type="button"
                              onClick={() => handleInsertConditionToken(idx, outKey)}
                              aria-label={`Insert condition token {${outKey}} into Step ${idx + 1}`}
                              className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-500/15 hover:bg-purple-500/25 text-purple-300 border border-purple-500/30 cursor-pointer"
                              title={`Insert token {${outKey}}`}
                            >
                              &#123;{outKey}&#125;
                            </button>
                          ))}
                        </div>
                      )}

                      {/* Optional Inline Else Child Skill */}
                      {st.condition && (
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[10px] text-slate-400 shrink-0">Inline Else Child Skill:</span>
                          <select
                            aria-label={`Step ${idx + 1} Else Child Skill`}
                            value={st.else_skill_name || ''}
                            onChange={(e) => handleSelectElseSkill(idx, e.target.value)}
                            className="p-1 rounded border border-slate-700 bg-slate-900 text-slate-100 text-[11px] font-mono flex-1 outline-none"
                          >
                            <option value="">-- None (Skip step if False) --</option>
                            {approvedSkills.map((sk) => (
                              <option key={sk.name} value={sk.name}>
                                {sk.name} (v{sk.version})
                              </option>
                            ))}
                          </select>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Step Configuration Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                  {/* Arguments Template */}
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-medium text-slate-300">
                        Arguments Template (JSON)
                      </span>
                    </div>
                    <textarea
                      aria-label={`Step ${idx + 1} Arguments Template`}
                      value={st.arguments_template || '{}'}
                      onChange={(e) => handleTemplateChange(idx, e.target.value)}
                      rows={2}
                      className="p-2 rounded bg-black/50 border border-slate-800 text-[11px] font-mono text-slate-200 outline-none resize-none"
                      placeholder='{"param": "{input_val}"}'
                    />
                    {preceding.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1 mt-0.5">
                        <span className="text-[10px] text-slate-400">Insert Output:</span>
                        {preceding.map((outKey) => (
                          <button
                            key={outKey}
                            type="button"
                            onClick={() => handleInsertToken(idx, outKey)}
                            aria-label={`Insert {${outKey}} into Step ${idx + 1}`}
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 border border-sky-500/30 cursor-pointer"
                            title={`Insert reference {${outKey}}`}
                          >
                            &#123;{outKey}&#125;
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Output Key */}
                  <div className="flex flex-col gap-1">
                    <span className="text-[11px] font-medium text-slate-300">
                      Output Key (Optional)
                    </span>
                    <input
                      type="text"
                      aria-label={`Step ${idx + 1} Output Key`}
                      placeholder={`e.g. step${idx + 1}_out`}
                      value={st.output_key || ''}
                      onChange={(e) => handleOutputKeyChange(idx, e.target.value)}
                      className="p-2 rounded bg-slate-900 border border-slate-800 text-[11px] font-mono text-slate-200 outline-none"
                    />
                    <span className="text-[10px] text-slate-400">
                      Exports output into workflow context for subsequent steps.
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Validation Result Feedback Box */}
      {validationResult && (
        <SkillCompositionValidationBanner validationResult={validationResult} />
      )}

      {/* Validation Error banner if non-JSON error or client validation error */}
      {validationError && !validationResult && (
        <div className="p-3 rounded-xl border bg-rose-500/10 border-rose-500/40 text-rose-300 flex items-center gap-2 text-xs">
          <AlertTriangle size={16} className="shrink-0" />
          <span>{validationError}</span>
        </div>
      )}

      {/* Security & Action Footer */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800 text-xs">
        <div className="flex items-center gap-1.5 text-slate-400 text-[11px]">
          <ShieldCheck size={14} className="text-purple-400 shrink-0" />
          <span>Transitive capabilities &amp; SafetyKernel checks will be enforced.</span>
        </div>

        <div className="flex items-center gap-2">
          {onClose && (
            <button
              onClick={onClose}
              aria-label="Close Composer"
              className="px-3.5 py-1.5 rounded-lg text-slate-400 hover:text-slate-200 text-xs transition-colors cursor-pointer"
            >
              Cancel
            </button>
          )}

          <button
            onClick={runValidation}
            disabled={validating}
            aria-label="Validate Workflow"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors cursor-pointer"
          >
            {validating ? (
              <RefreshCw size={13} className="animate-spin text-purple-400" />
            ) : (
              <CheckCircle2 size={13} className="text-purple-400" />
            )}
            <span>{validating ? 'Validating...' : 'Validate Workflow'}</span>
          </button>

          <button
            onClick={handleCreate}
            disabled={submitting || validating || validationResult?.valid === false}
            aria-label="Create Composite Skill"
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:bg-purple-600/40 disabled:cursor-not-allowed text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer"
          >
            {submitting ? (
              <RefreshCw size={13} className="animate-spin" />
            ) : (
              <Plus size={13} />
            )}
            <span>{submitting ? 'Creating...' : 'Create Composite Skill'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export function MemorySkillsPage() {
  const [activeTab, setActiveTab] = useState<'memories' | 'skills' | 'maintenance'>('memories');

  // ---------------------------------------------------------------------------
  // Memory State
  // ---------------------------------------------------------------------------
  const [memories, setMemories] = useState<MemoryFact[]>([]);
  const [memoryStats, setMemoryStats] = useState<MemoryFactsResponse['stats']>({
    total_facts: 0,
    trusted_count: 0,
    auto_count: 0,
    untrusted_count: 0,
    verified_count: 0,
    unverified_count: 0,
  });
  const [memoryCategories, setMemoryCategories] = useState<string[]>([]);
  const [memoryProjects, setMemoryProjects] = useState<string[]>([]);
  const [memoryLoading, setMemoryLoading] = useState<boolean>(true);
  const [memorySearch, setMemorySearch] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedProject, setSelectedProject] = useState<string>('all');
  const [selectedTrust, setSelectedTrust] = useState<string>('all');
  const [selectedVerified, setSelectedVerified] = useState<string>('all');
  const [expandedMemoryId, setExpandedMemoryId] = useState<string | null>(null);

  // Modals for Memory
  const [createMemoryOpen, setCreateMemoryOpen] = useState<boolean>(false);
  const [newMemoryText, setNewMemoryText] = useState<string>('');
  const [newMemoryCategory, setNewMemoryCategory] = useState<string>('general');
  const [newMemoryProject, setNewMemoryProject] = useState<string>('default');
  const [newMemoryTrust, setNewMemoryTrust] = useState<'trusted' | 'auto' | 'untrusted'>('trusted');
  const [newMemoryVerified, setNewMemoryVerified] = useState<boolean>(true);
  const [submittingMemory, setSubmittingMemory] = useState<boolean>(false);

  const [editMemoryOpen, setEditMemoryOpen] = useState<boolean>(false);
  const [editingMemory, setEditingMemory] = useState<MemoryFact | null>(null);
  const [editText, setEditText] = useState<string>('');
  const [editCategory, setEditCategory] = useState<string>('general');
  const [editProject, setEditProject] = useState<string>('default');
  const [editTrust, setEditTrust] = useState<string>('trusted');
  const [editVerified, setEditVerified] = useState<boolean>(true);

  const [deleteMemoryOpen, setDeleteMemoryOpen] = useState<boolean>(false);
  const [deletingMemoryId, setDeletingMemoryId] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Skills State
  // ---------------------------------------------------------------------------
  const [skills, setSkills] = useState<LearnedSkill[]>([]);
  const [skillsStats, setSkillsStats] = useState<LearnedSkillsResponse['stats']>({
    total_skills: 0,
    pending_count: 0,
    approved_count: 0,
    disabled_count: 0,
    rejected_count: 0,
  });
  const [skillsLoading, setSkillsLoading] = useState<boolean>(true);
  const [skillSearch, setSkillSearch] = useState<string>('');
  const [skillStatusFilter, setSkillStatusFilter] = useState<string>('all');

  // Modals for Skills
  const [detailSkill, setDetailSkill] = useState<LearnedSkill | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [actionSkill, setActionSkill] = useState<LearnedSkill | null>(null);
  const [actionType, setActionType] = useState<'approve' | 'reject' | 'disable' | 'enable' | null>(null);
  const [actionReason, setActionReason] = useState<string>('');
  const [submittingAction, setSubmittingAction] = useState<boolean>(false);
  const [composerOpen, setComposerOpen] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Maintenance State
  // ---------------------------------------------------------------------------
  const [maintenanceSuggestions, setMaintenanceSuggestions] = useState<MaintenanceSuggestion[]>([]);
  const [maintenanceLoading, setMaintenanceLoading] = useState<boolean>(false);
  const [scanningMaintenance, setScanningMaintenance] = useState<boolean>(false);
  const [selectedIssueType, setSelectedIssueType] = useState<string>('all');
  const [selectedMaintenanceStatus, setSelectedMaintenanceStatus] = useState<string>('pending');
  const [selectedMaintenanceProject, setSelectedMaintenanceProject] = useState<string>('all');

  const [approvingSuggestion, setApprovingSuggestion] = useState<MaintenanceSuggestion | null>(null);
  const [customMergedText, setCustomMergedText] = useState<string>('');
  const [submittingApproval, setSubmittingApproval] = useState<boolean>(false);

  const [dismissingSuggestion, setDismissingSuggestion] = useState<MaintenanceSuggestion | null>(null);
  const [dismissReason, setDismissReason] = useState<string>('');
  const [submittingDismiss, setSubmittingDismiss] = useState<boolean>(false);

  const pendingMaintenanceCount = useMemo(
    () => maintenanceSuggestions.filter((s) => s.status === 'pending').length,
    [maintenanceSuggestions],
  );

  const loadMaintenanceSuggestions = useCallback(async () => {
    setMaintenanceLoading(true);
    try {
      const res = await fetchMaintenanceSuggestions({
        project: selectedMaintenanceProject !== 'all' ? selectedMaintenanceProject : undefined,
        issue_type: selectedIssueType !== 'all' ? selectedIssueType : undefined,
        status: selectedMaintenanceStatus !== 'all' ? selectedMaintenanceStatus : undefined,
      });
      setMaintenanceSuggestions(res.suggestions || []);
    } catch (err: any) {
      toast.error(err.message || 'Failed to fetch maintenance suggestions');
    } finally {
      setMaintenanceLoading(false);
    }
  }, [selectedMaintenanceProject, selectedIssueType, selectedMaintenanceStatus]);

  useEffect(() => {
    if (activeTab === 'maintenance') {
      loadMaintenanceSuggestions();
    }
  }, [activeTab, loadMaintenanceSuggestions]);

  const handleScanMaintenance = async () => {
    setScanningMaintenance(true);
    try {
      const res = await scanMemoryMaintenance(
        selectedMaintenanceProject !== 'all' ? selectedMaintenanceProject : undefined,
      );
      toast.success(`Scan completed. Found ${res.total} issue suggestion${res.total !== 1 ? 's' : ''}.`);
      loadMaintenanceSuggestions();
    } catch (err: any) {
      toast.error(err.message || 'Maintenance scan failed');
    } finally {
      setScanningMaintenance(false);
    }
  };

  const openApproveModal = (sug: MaintenanceSuggestion) => {
    setApprovingSuggestion(sug);
    const defaultText = sug.proposed_resolution?.merged_text || '';
    setCustomMergedText(defaultText);
  };

  const handleExecuteApproval = async () => {
    if (!approvingSuggestion) return;
    setSubmittingApproval(true);
    try {
      await approveMaintenanceSuggestion(approvingSuggestion.id, {
        custom_text: customMergedText.trim() || undefined,
      });
      toast.success('Maintenance suggestion approved and executed successfully.');
      setApprovingSuggestion(null);
      loadMaintenanceSuggestions();
      loadMemories();
    } catch (err: any) {
      toast.error(err.message || 'Failed to apply maintenance suggestion');
    } finally {
      setSubmittingApproval(false);
    }
  };

  const openDismissModal = (sug: MaintenanceSuggestion) => {
    setDismissingSuggestion(sug);
    setDismissReason('Dismissed after operator review.');
  };

  const handleExecuteDismiss = async () => {
    if (!dismissingSuggestion) return;
    setSubmittingDismiss(true);
    try {
      await dismissMaintenanceSuggestion(dismissingSuggestion.id, {
        reason: dismissReason.trim() || 'Dismissed by operator.',
      });
      toast.success('Maintenance suggestion dismissed.');
      setDismissingSuggestion(null);
      loadMaintenanceSuggestions();
    } catch (err: any) {
      toast.error(err.message || 'Failed to dismiss suggestion');
    } finally {
      setSubmittingDismiss(false);
    }
  };
  // ---------------------------------------------------------------------------
  const loadMemories = useCallback(async () => {
    setMemoryLoading(true);
    try {
      const verifiedParam =
        selectedVerified === 'verified'
          ? true
          : selectedVerified === 'unverified'
          ? false
          : undefined;

      const data = await fetchMemoryFacts({
        q: memorySearch.trim() || undefined,
        category: selectedCategory,
        project: selectedProject,
        trust: selectedTrust,
        verified: verifiedParam,
        limit: 100,
      });

      setMemories(data.memories || []);
      setMemoryStats(data.stats);
      if (data.categories?.length) setMemoryCategories(data.categories);
      if (data.projects?.length) setMemoryProjects(data.projects);
    } catch (err: any) {
      toast.error(err.message || 'Failed to load memories');
    } finally {
      setMemoryLoading(false);
    }
  }, [memorySearch, selectedCategory, selectedProject, selectedTrust, selectedVerified]);

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  // ---------------------------------------------------------------------------
  // Load Learned Skills
  // ---------------------------------------------------------------------------
  const loadSkills = useCallback(async () => {
    setSkillsLoading(true);
    try {
      const data = await fetchLearnedSkills({
        status: skillStatusFilter,
        q: skillSearch.trim() || undefined,
      });
      setSkills(data.skills || []);
      setSkillsStats(data.stats);
    } catch (err: any) {
      toast.error(err.message || 'Failed to load learned skills');
    } finally {
      setSkillsLoading(false);
    }
  }, [skillStatusFilter, skillSearch]);

  useEffect(() => {
    loadSkills();
  }, [loadSkills]);

  // ---------------------------------------------------------------------------
  // Memory Actions
  // ---------------------------------------------------------------------------
  const handleCreateMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemoryText.trim()) {
      toast.error('Please enter memory text');
      return;
    }
    setSubmittingMemory(true);
    try {
      await createMemoryFact({
        text: newMemoryText.trim(),
        category: newMemoryCategory,
        project: newMemoryProject.trim() || 'default',
        trust: newMemoryTrust,
        verified: newMemoryVerified,
      });
      toast.success('Memory fact recorded successfully');
      setCreateMemoryOpen(false);
      setNewMemoryText('');
      loadMemories();
    } catch (err: any) {
      toast.error(err.message || 'Failed to create memory fact');
    } finally {
      setSubmittingMemory(false);
    }
  };

  const openEditModal = (mem: MemoryFact) => {
    setEditingMemory(mem);
    setEditText(mem.text);
    setEditCategory(mem.category);
    setEditProject(mem.project);
    setEditTrust(mem.trust);
    setEditVerified(mem.verified);
    setEditMemoryOpen(true);
  };

  const handleUpdateMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingMemory) return;
    if (!editText.trim()) {
      toast.error('Memory text cannot be empty');
      return;
    }
    setSubmittingMemory(true);
    try {
      await updateMemoryFact(editingMemory.id, {
        text: editText.trim(),
        category: editCategory,
        project: editProject.trim(),
        trust: editTrust,
        verified: editVerified,
      });
      toast.success('Memory updated successfully');
      setEditMemoryOpen(false);
      loadMemories();
    } catch (err: any) {
      toast.error(err.message || 'Failed to update memory');
    } finally {
      setSubmittingMemory(false);
    }
  };

  const handleDeleteMemory = async () => {
    if (!deletingMemoryId) return;
    setSubmittingMemory(true);
    try {
      await deleteMemoryFact(deletingMemoryId);
      toast.success('Memory entry deleted');
      setDeleteMemoryOpen(false);
      setDeletingMemoryId(null);
      loadMemories();
    } catch (err: any) {
      toast.error(err.message || 'Failed to delete memory');
    } finally {
      setSubmittingMemory(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Skill Actions
  // ---------------------------------------------------------------------------
  const inspectSkill = async (skillName: string) => {
    setDetailLoading(true);
    try {
      const full = await fetchLearnedSkillDetail(skillName);
      setDetailSkill(full);
    } catch (err: any) {
      toast.error(err.message || `Failed to fetch skill details for '${skillName}'`);
    } finally {
      setDetailLoading(false);
    }
  };

  const openSkillAction = (
    skill: LearnedSkill,
    type: 'approve' | 'reject' | 'disable' | 'enable',
  ) => {
    setActionSkill(skill);
    setActionType(type);
    setActionReason('');
  };

  const handleExecuteSkillAction = async () => {
    if (!actionSkill || !actionType) return;
    setSubmittingAction(true);
    try {
      if (actionType === 'approve') {
        await approveLearnedSkill(actionSkill.name);
        toast.success(`Skill '${actionSkill.name}' approved successfully`);
      } else if (actionType === 'reject') {
        await rejectLearnedSkill(actionSkill.name, actionReason.trim());
        toast.success(`Skill '${actionSkill.name}' rejected`);
      } else if (actionType === 'disable') {
        await disableLearnedSkill(actionSkill.name, actionReason.trim());
        toast.success(`Skill '${actionSkill.name}' disabled`);
      } else if (actionType === 'enable') {
        await enableLearnedSkill(actionSkill.name);
        toast.success(`Skill '${actionSkill.name}' re-enabled`);
      }

      setActionType(null);
      setActionSkill(null);
      loadSkills();
      if (detailSkill?.name === actionSkill.name) {
        inspectSkill(actionSkill.name);
      }
    } catch (err: any) {
      toast.error(err.message || `Failed to ${actionType} skill`);
    } finally {
      setSubmittingAction(false);
    }
  };

  // Helper for source type icon
  const renderSourceTypeIcon = (type?: string | unknown) => {
    const safeType = typeof type === 'string' ? type.toLowerCase() : '';
    switch (safeType) {
      case 'website':
      case 'web':
        return <Globe size={13} className="text-cyan-400" />;
      case 'file':
        return <FileText size={13} className="text-emerald-400" />;
      case 'email':
        return <Mail size={13} className="text-amber-400" />;
      case 'tool_output':
        return <Terminal size={13} className="text-purple-400" />;
      case 'task_execution':
        return <ListTodo size={13} className="text-blue-400" />;
      case 'user_direct':
      default:
        return <User size={13} className="text-slate-400" />;
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto" style={{ background: 'var(--color-bg-primary)' }}>
      {/* Page Header */}
      <div
        className="px-6 py-5 border-b sticky top-0 z-10 backdrop-blur-md"
        style={{
          background: 'var(--color-bg-primary)',
          borderColor: 'var(--color-border)',
        }}
      >
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 max-w-7xl mx-auto w-full">
          <div>
            <div className="flex items-center gap-2.5">
              <div
                className="p-2 rounded-lg"
                style={{
                  background: 'rgba(56, 189, 248, 0.15)',
                  color: '#38bdf8',
                  border: '1px solid rgba(56, 189, 248, 0.3)',
                }}
              >
                <Brain size={22} />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight" style={{ color: 'var(--color-text-primary)' }}>
                  Memory & Skills Control Center
                </h1>
                <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  Inspect persistent facts, quarantine untrusted memory, and govern reusable learned workflows.
                </p>
              </div>
            </div>
          </div>

          {/* Tab Navigation Buttons */}
          <div
            className="flex items-center p-1 rounded-lg border gap-1 self-start sm:self-auto"
            style={{
              background: 'var(--color-bg-secondary)',
              borderColor: 'var(--color-border)',
            }}
          >
            <button
              onClick={() => setActiveTab('memories')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                activeTab === 'memories'
                  ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Brain size={14} />
              <span>Memories</span>
              <span
                className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold"
                style={{ background: 'rgba(255,255,255,0.08)' }}
              >
                {memoryStats.total_facts}
              </span>
            </button>
            <button
              onClick={() => setActiveTab('skills')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                activeTab === 'skills'
                  ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Sparkles size={14} />
              <span>Learned Skills</span>
              {skillsStats.pending_count > 0 ? (
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse">
                  {skillsStats.pending_count} review
                </span>
              ) : (
                <span
                  className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold"
                  style={{ background: 'rgba(255,255,255,0.08)' }}
                >
                  {skillsStats.total_skills}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab('maintenance')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                activeTab === 'maintenance'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Wrench size={14} />
              <span>Maintenance &amp; Consolidation</span>
              {pendingMaintenanceCount > 0 ? (
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse">
                  {pendingMaintenanceCount} issue{pendingMaintenanceCount !== 1 ? 's' : ''}
                </span>
              ) : (
                <span
                  className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold"
                  style={{ background: 'rgba(255,255,255,0.08)' }}
                >
                  {maintenanceSuggestions.length}
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="p-6 max-w-7xl mx-auto w-full flex-1 flex flex-col gap-6">
        {/* =================================================================== */}
        {/* TAB 1: MEMORIES MANAGEMENT                                         */}
        {/* =================================================================== */}
        {activeTab === 'memories' && (
          <>
            {/* Stats Overview Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
              >
                <span className="text-[11px] font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                  Total Facts
                </span>
                <span className="text-2xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
                  {memoryStats.total_facts}
                </span>
              </div>
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(16, 185, 129, 0.25)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-emerald-400">Trusted</span>
                  <ShieldCheck size={14} className="text-emerald-400" />
                </div>
                <span className="text-2xl font-bold text-emerald-400">{memoryStats.trusted_count}</span>
              </div>
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(56, 189, 248, 0.25)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-sky-400">Auto-Extracted</span>
                  <Brain size={14} className="text-sky-400" />
                </div>
                <span className="text-2xl font-bold text-sky-400">{memoryStats.auto_count}</span>
              </div>
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(239, 68, 68, 0.3)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-rose-400">Quarantined</span>
                  <ShieldAlert size={14} className="text-rose-400" />
                </div>
                <span className="text-2xl font-bold text-rose-400">{memoryStats.untrusted_count}</span>
              </div>
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1 col-span-2 sm:col-span-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(168, 85, 247, 0.25)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-purple-400">Verified</span>
                  <CheckCircle2 size={14} className="text-purple-400" />
                </div>
                <span className="text-2xl font-bold text-purple-400">{memoryStats.verified_count}</span>
              </div>
            </div>

            {/* Filter and Action Bar */}
            <div
              className="p-3.5 rounded-xl border flex flex-wrap items-center justify-between gap-3"
              style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
            >
              {/* Search & Selectors */}
              <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[280px]">
                {/* Search */}
                <div
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg border flex-1 min-w-[180px] max-w-xs text-xs"
                  style={{ background: 'var(--color-bg-primary)', borderColor: 'var(--color-border)' }}
                >
                  <Search size={14} style={{ color: 'var(--color-text-secondary)' }} />
                  <input
                    type="text"
                    placeholder="Search memories..."
                    value={memorySearch}
                    onChange={(e) => setMemorySearch(e.target.value)}
                    className="bg-transparent border-none outline-none w-full text-xs"
                    style={{ color: 'var(--color-text-primary)' }}
                  />
                  {memorySearch && (
                    <button
                      onClick={() => setMemorySearch('')}
                      className="text-xs text-slate-400 hover:text-slate-200"
                    >
                      ✕
                    </button>
                  )}
                </div>

                {/* Category Dropdown */}
                <select
                  value={selectedCategory}
                  onChange={(e) => setSelectedCategory(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg border text-xs outline-none cursor-pointer"
                  style={{
                    background: 'var(--color-bg-primary)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text-primary)',
                  }}
                >
                  <option value="all">All Categories</option>
                  {memoryCategories.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat.replace(/_/g, ' ')}
                    </option>
                  ))}
                </select>

                {/* Trust Status Dropdown */}
                <select
                  value={selectedTrust}
                  onChange={(e) => setSelectedTrust(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg border text-xs outline-none cursor-pointer"
                  style={{
                    background: 'var(--color-bg-primary)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text-primary)',
                  }}
                >
                  <option value="all">All Trust Tiers</option>
                  <option value="trusted">Trusted Only</option>
                  <option value="auto">Auto-Extracted</option>
                  <option value="untrusted">Quarantined / Untrusted</option>
                </select>

                {/* Verified Dropdown */}
                <select
                  value={selectedVerified}
                  onChange={(e) => setSelectedVerified(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg border text-xs outline-none cursor-pointer"
                  style={{
                    background: 'var(--color-bg-primary)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text-primary)',
                  }}
                >
                  <option value="all">All Verification</option>
                  <option value="verified">Verified Only</option>
                  <option value="unverified">Unverified Only</option>
                </select>

                {/* Project Filter (if multiple projects exist) */}
                {memoryProjects.length > 1 && (
                  <select
                    value={selectedProject}
                    onChange={(e) => setSelectedProject(e.target.value)}
                    className="px-2.5 py-1.5 rounded-lg border text-xs outline-none cursor-pointer"
                    style={{
                      background: 'var(--color-bg-primary)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    <option value="all">All Projects</option>
                    {memoryProjects.map((p) => (
                      <option key={p} value={p}>
                        Project: {p}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2">
                <button
                  onClick={loadMemories}
                  disabled={memoryLoading}
                  className="p-1.5 rounded-lg border text-xs hover:bg-slate-800 transition-colors cursor-pointer"
                  style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}
                  title="Refresh Memories"
                >
                  <RefreshCw size={14} className={memoryLoading ? 'animate-spin' : ''} />
                </button>
                <button
                  onClick={() => setCreateMemoryOpen(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-sky-500 hover:bg-sky-600 text-white transition-colors cursor-pointer"
                >
                  <Plus size={14} />
                  <span>Add Memory</span>
                </button>
              </div>
            </div>

            {/* Memories List */}
            {memoryLoading ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <RefreshCw size={24} className="animate-spin text-sky-400" />
                <span className="text-xs text-slate-400">Loading persistent memories...</span>
              </div>
            ) : memories.length === 0 ? (
              <div
                className="flex flex-col items-center justify-center py-16 px-4 rounded-xl border border-dashed text-center"
                style={{ borderColor: 'var(--color-border)' }}
              >
                <Brain size={32} className="text-slate-500 mb-2" />
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                  No memories found
                </h3>
                <p className="text-xs text-slate-400 mt-1 max-w-sm">
                  {memorySearch || selectedCategory !== 'all' || selectedTrust !== 'all'
                    ? 'No memories match your active search and filter criteria.'
                    : 'No durable facts have been extracted or recorded yet. Use "Add Memory" to create one.'}
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {memories.map((mem) => {
                  const isQuarantined = mem.trust === 'untrusted';
                  const isExpanded = expandedMemoryId === mem.id;

                  return (
                    <div
                      key={mem.id}
                      className="p-4 rounded-xl border transition-all"
                      style={{
                        background: 'var(--color-bg-secondary)',
                        borderColor: isQuarantined
                          ? 'rgba(239, 68, 68, 0.4)'
                          : 'var(--color-border)',
                      }}
                    >
                      {/* Top Header Row */}
                      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                        <div className="flex flex-wrap items-center gap-2">
                          {/* Trust Badge */}
                          <MemoryTrustBadge trust={mem.trust} />

                          {/* Category Badge */}
                          <span
                            className="px-2 py-0.5 rounded-md text-[10px] font-medium"
                            style={{ background: 'rgba(255,255,255,0.06)', color: 'var(--color-text-secondary)' }}
                          >
                            {mem.category.replace(/_/g, ' ')}
                          </span>

                          {/* Verification Badge */}
                          {mem.verified ? (
                            <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium text-emerald-400 bg-emerald-500/10">
                              <CheckCircle2 size={11} />
                              <span>Verified</span>
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium text-amber-400 bg-amber-500/10">
                              <AlertTriangle size={11} />
                              <span>Unverified</span>
                            </span>
                          )}

                          {/* Project Tag */}
                          {mem.project && mem.project !== 'default' && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] text-slate-400 bg-slate-800">
                              proj: {mem.project}
                            </span>
                          )}
                        </div>

                        {/* Provenance & Timestamp */}
                        <div className="flex items-center gap-3 text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                          <span className="flex items-center gap-1">
                            {renderSourceTypeIcon(mem.source_type)}
                            <span>{mem.source_type || 'user_direct'}</span>
                          </span>
                          <span>
                            {mem.created_at
                              ? new Date(mem.created_at * 1000).toLocaleDateString(undefined, {
                                  month: 'short',
                                  day: 'numeric',
                                  hour: '2-digit',
                                  minute: '2-digit',
                                })
                              : ''}
                          </span>
                        </div>
                      </div>

                      {/* Quarantined Warning Alert */}
                      {isQuarantined && (
                        <div className="mb-2 p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-start gap-2 text-xs text-rose-300">
                          <ShieldAlert size={15} className="shrink-0 mt-0.5 text-rose-400" />
                          <div>
                            <span className="font-semibold">Security Quarantine:</span> This entry contains
                            instruction-like or suspicious prompt content. It is strictly isolated from model planning
                            context to prevent prompt injection.
                          </div>
                        </div>
                      )}

                      {/* Fact Content Text */}
                      <p className="text-sm font-medium leading-relaxed my-1.5" style={{ color: 'var(--color-text-primary)' }}>
                        {mem.text}
                      </p>

                      {/* Bottom Controls / Expandable Details */}
                      <div className="flex items-center justify-between mt-3 pt-2 border-t text-xs" style={{ borderColor: 'var(--color-border)' }}>
                        <button
                          onClick={() => setExpandedMemoryId(isExpanded ? null : mem.id)}
                          className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-200 cursor-pointer"
                        >
                          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <span>{isExpanded ? 'Hide Details' : 'View Provenance & Metadata'}</span>
                        </button>

                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => {
                              navigator.clipboard.writeText(mem.text);
                              toast.success('Memory text copied to clipboard');
                            }}
                            className="p-1 text-slate-400 hover:text-slate-200 cursor-pointer"
                            title="Copy memory text"
                          >
                            <Copy size={13} />
                          </button>
                          <button
                            onClick={() => openEditModal(mem)}
                            className="flex items-center gap-1 px-2 py-1 rounded text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 transition-colors cursor-pointer text-[11px]"
                          >
                            <Edit3 size={11} />
                            <span>Edit</span>
                          </button>
                          <button
                            onClick={() => {
                              setDeletingMemoryId(mem.id);
                              setDeleteMemoryOpen(true);
                            }}
                            className="flex items-center gap-1 px-2 py-1 rounded text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 transition-colors cursor-pointer text-[11px]"
                          >
                            <Trash2 size={11} />
                            <span>Delete</span>
                          </button>
                        </div>
                      </div>

                      {/* Expanded Provenance Inspector */}
                      {isExpanded && (
                        <div
                          className="mt-3 p-3 rounded-lg border text-xs font-mono flex flex-col gap-1.5"
                          style={{
                            background: 'var(--color-bg-primary)',
                            borderColor: 'var(--color-border)',
                            color: 'var(--color-text-secondary)',
                          }}
                        >
                          <div>
                            <span className="text-slate-400">Memory ID: </span>
                            <span className="text-slate-200">{mem.id}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Source: </span>
                            <span className="text-slate-200">{mem.source || 'user_direct'}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">Model Recall Status: </span>
                            <span className={mem.trusted_for_recall ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
                              {mem.trusted_for_recall ? 'Eligible for Planning Context' : 'Quarantined / Excluded from Model Context'}
                            </span>
                          </div>
                          {mem.metadata && Object.keys(mem.metadata).length > 0 && (
                            <div>
                              <span className="text-slate-400">Metadata Payload:</span>
                              <pre className="mt-1 p-2 rounded bg-black/40 overflow-x-auto text-[11px] text-slate-300">
                                {JSON.stringify(mem.metadata, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* =================================================================== */}
        {/* TAB 2: LEARNED SKILLS MANAGEMENT                                    */}
        {/* =================================================================== */}
        {activeTab === 'skills' && (
          <>
            {/* Skills Stats Row */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3.5">
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
              >
                <span className="text-[11px] font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                  Total Skills
                </span>
                <span className="text-2xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
                  {skillsStats.total_skills}
                </span>
              </div>
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(245, 158, 11, 0.3)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-amber-400">Pending Review</span>
                  <AlertTriangle size={14} className="text-amber-400" />
                </div>
                <span className="text-2xl font-bold text-amber-400">{skillsStats.pending_count}</span>
              </div>
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(16, 185, 129, 0.3)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-emerald-400">Approved & Active</span>
                  <CheckCircle2 size={14} className="text-emerald-400" />
                </div>
                <span className="text-2xl font-bold text-emerald-400">{skillsStats.approved_count}</span>
              </div>
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(148, 163, 184, 0.3)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-slate-400">Disabled</span>
                  <PauseCircle size={14} className="text-slate-400" />
                </div>
                <span className="text-2xl font-bold text-slate-400">{skillsStats.disabled_count}</span>
              </div>
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1 col-span-2 sm:col-span-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(239, 68, 68, 0.3)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-rose-400">Rejected</span>
                  <XCircle size={14} className="text-rose-400" />
                </div>
                <span className="text-2xl font-bold text-rose-400">{skillsStats.rejected_count}</span>
              </div>
            </div>

            {/* Skills Filter Bar */}
            <div
              className="p-3.5 rounded-xl border flex flex-wrap items-center justify-between gap-3"
              style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
            >
              <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[280px]">
                {/* Search */}
                <div
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg border flex-1 min-w-[200px] max-w-sm text-xs"
                  style={{ background: 'var(--color-bg-primary)', borderColor: 'var(--color-border)' }}
                >
                  <Search size={14} style={{ color: 'var(--color-text-secondary)' }} />
                  <input
                    type="text"
                    placeholder="Search learned skills..."
                    value={skillSearch}
                    onChange={(e) => setSkillSearch(e.target.value)}
                    className="bg-transparent border-none outline-none w-full text-xs"
                    style={{ color: 'var(--color-text-primary)' }}
                  />
                  {skillSearch && (
                    <button
                      onClick={() => setSkillSearch('')}
                      className="text-xs text-slate-400 hover:text-slate-200"
                    >
                      ✕
                    </button>
                  )}
                </div>

                {/* Status Filter */}
                <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-900 border border-slate-800 text-xs">
                  {['all', 'pending_review', 'approved', 'disabled', 'rejected'].map((st) => (
                    <button
                      key={st}
                      onClick={() => setSkillStatusFilter(st)}
                      className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer capitalize ${
                        skillStatusFilter === st
                          ? 'bg-slate-800 text-white font-medium'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {st.replace(/_/g, ' ')}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setComposerOpen(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer"
                  title="Compose New Skill Workflow"
                >
                  <Plus size={14} />
                  <span>Compose Skill</span>
                </button>

                <button
                  onClick={loadSkills}
                  disabled={skillsLoading}
                  className="p-1.5 rounded-lg border text-xs hover:bg-slate-800 transition-colors cursor-pointer"
                  style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}
                  title="Refresh Skills"
                >
                  <RefreshCw size={14} className={skillsLoading ? 'animate-spin' : ''} />
                </button>
              </div>
            </div>

            {/* Skills Cards Grid */}
            {skillsLoading ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <RefreshCw size={24} className="animate-spin text-purple-400" />
                <span className="text-xs text-slate-400">Loading learned skills...</span>
              </div>
            ) : skills.length === 0 ? (
              <div
                className="flex flex-col items-center justify-center py-16 px-4 rounded-xl border border-dashed text-center"
                style={{ borderColor: 'var(--color-border)' }}
              >
                <Sparkles size={32} className="text-slate-500 mb-2" />
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                  No skills found
                </h3>
                <p className="text-xs text-slate-400 mt-1 max-w-sm">
                  {skillSearch || skillStatusFilter !== 'all'
                    ? 'No learned skills match your active filter.'
                    : 'Skills are distilled automatically when multi-step tasks successfully complete.'}
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {skills.map((s) => {
                  const isPending = s.approval_status === 'pending_review';
                  const isRejected = s.approval_status === 'rejected';
                  const isApproved = s.approval_status === 'approved' && !s.disabled;
                  const isDisabled = s.disabled;
                  const isUnhealthy = !s.health.is_healthy;

                  return (
                    <div
                      key={s.name}
                      className="p-4 rounded-xl border flex flex-col justify-between transition-all"
                      style={{
                        background: 'var(--color-bg-secondary)',
                        borderColor: isPending
                          ? 'rgba(245, 158, 11, 0.4)'
                          : isUnhealthy
                          ? 'rgba(239, 68, 68, 0.35)'
                          : 'var(--color-border)',
                      }}
                    >
                      <div>
                        {/* Top Meta Badges */}
                        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                          <div className="flex flex-wrap items-center gap-1.5">
                            {/* Status Badge */}
                            <SkillStatusBadge
                              status={s.approval_status}
                              disabled={isDisabled}
                              disabledReason={s.disabled_reason}
                            />

                            {/* Composite Flag */}
                            {(s.is_composite || s.steps?.some((st) => !!st.skill_name)) && (
                              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold">
                                <Layers size={10} />
                                <span>Composite</span>
                              </span>
                            )}

                            {/* System Protected Flag */}
                            {s.is_protected && (
                              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700">
                                <Lock size={10} />
                                <span>Core System</span>
                              </span>
                            )}

                            {/* Health Badge */}
                            {s.health.outdated ? (
                              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-rose-500/15 text-rose-300 border border-rose-500/30 font-semibold">
                                <AlertTriangle size={10} />
                                <span>Outdated</span>
                              </span>
                            ) : s.health.consecutive_failures > 0 ? (
                              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-amber-500/15 text-amber-300 border border-amber-500/30 font-medium">
                                <AlertTriangle size={10} />
                                <span>{s.health.consecutive_failures} Failures</span>
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] text-emerald-400 bg-emerald-500/10">
                                <Activity size={10} />
                                <span>Healthy</span>
                              </span>
                            )}
                          </div>

                          <span className="text-[11px] text-slate-400 font-mono">v{s.version}</span>
                        </div>

                        {/* Title and Description */}
                        <h3 className="text-sm font-bold tracking-tight text-slate-100 flex items-center gap-2">
                          <span>{s.name}</span>
                        </h3>
                        <p className="text-xs text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                          {s.description || 'No description provided.'}
                        </p>

                        {/* Validation Alert if Broken */}
                        {!s.validation.is_valid && (
                          <div className="mt-2.5 p-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-xs text-rose-300">
                            <span className="font-semibold">Validation Blocked: </span>
                            {s.validation.errors.join('; ')}
                          </div>
                        )}

                        {/* Disabled Reason if present */}
                        {isDisabled && s.disabled_reason && (
                          <div className="mt-2 p-2 rounded-lg bg-slate-800 border border-slate-700 text-xs text-slate-300">
                            <span className="font-semibold text-slate-400">Disabled note: </span>
                            {s.disabled_reason}
                          </div>
                        )}

                        {/* Pipeline Steps and Required Capabilities */}
                        <div className="mt-3 flex flex-wrap items-center gap-1.5">
                          <span className="px-2 py-0.5 rounded text-[11px] bg-slate-800 text-slate-300">
                            {s.steps_count} workflow step{s.steps_count !== 1 ? 's' : ''}
                          </span>
                          {s.required_capabilities.map((cap) => (
                            <span
                              key={cap}
                              className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-500/10 text-purple-300 border border-purple-500/20"
                            >
                              {cap}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Card Actions Footer */}
                      <div className="flex items-center justify-between mt-4 pt-3 border-t text-xs border-slate-800">
                        <button
                          onClick={() => inspectSkill(s.name)}
                          className="flex items-center gap-1 text-slate-300 hover:text-white transition-colors cursor-pointer text-xs font-medium"
                        >
                          <Layers size={13} />
                          <span>Inspect Workflow</span>
                        </button>

                        <div className="flex items-center gap-1.5">
                          {isPending && !s.is_protected && (
                            <>
                              <button
                                onClick={() => openSkillAction(s, 'reject')}
                                className="px-2.5 py-1 rounded text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 transition-colors cursor-pointer text-xs"
                              >
                                Reject
                              </button>
                              <button
                                onClick={() => openSkillAction(s, 'approve')}
                                disabled={!s.validation.is_valid}
                                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer ${
                                  s.validation.is_valid
                                    ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                                    : 'bg-slate-800 text-slate-500 cursor-not-allowed'
                                }`}
                                title={!s.validation.is_valid ? 'Validation errors must be resolved' : 'Approve skill'}
                              >
                                Approve
                              </button>
                            </>
                          )}

                          {isApproved && !s.is_protected && (
                            <button
                              onClick={() => openSkillAction(s, 'disable')}
                              className="px-2.5 py-1 rounded text-slate-400 hover:text-slate-200 bg-slate-800 hover:bg-slate-700 transition-colors cursor-pointer text-xs"
                            >
                              Disable
                            </button>
                          )}

                          {isDisabled && !s.is_protected && (
                            <button
                              onClick={() => openSkillAction(s, 'enable')}
                              className="px-2.5 py-1 rounded text-emerald-400 hover:text-emerald-300 bg-emerald-500/15 hover:bg-emerald-500/25 transition-colors cursor-pointer text-xs font-medium"
                            >
                              Enable
                            </button>
                          )}

                          {isRejected && !s.is_protected && (
                            <button
                              onClick={() => openSkillAction(s, 'approve')}
                              disabled={!s.validation.is_valid}
                              className="px-2.5 py-1 rounded text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors cursor-pointer"
                            >
                              Re-Approve
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {/* =================================================================== */}
        {/* TAB 3: MEMORY MAINTENANCE & CONSOLIDATION                          */}
        {/* =================================================================== */}
        {activeTab === 'maintenance' && (
          <>
            {/* Stats Overview Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
              >
                <span className="text-[11px] font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                  Total Findings
                </span>
                <span className="text-2xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
                  {maintenanceSuggestions.length}
                </span>
              </div>

              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(245, 158, 11, 0.3)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-amber-400">Pending Review</span>
                  <AlertTriangle size={14} className="text-amber-400" />
                </div>
                <span className="text-2xl font-bold text-amber-400">{pendingMaintenanceCount}</span>
              </div>

              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(245, 158, 11, 0.2)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-amber-300">Duplicates</span>
                  <Copy size={14} className="text-amber-300" />
                </div>
                <span className="text-2xl font-bold text-amber-300">
                  {maintenanceSuggestions.filter((s) => s.issue_type === 'duplicate').length}
                </span>
              </div>

              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(239, 68, 68, 0.25)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-rose-400">Contradictions</span>
                  <AlertTriangle size={14} className="text-rose-400" />
                </div>
                <span className="text-2xl font-bold text-rose-400">
                  {maintenanceSuggestions.filter((s) => s.issue_type === 'contradiction').length}
                </span>
              </div>

              <div
                className="p-3.5 rounded-xl border flex flex-col gap-1 col-span-2 sm:col-span-1"
                style={{ background: 'var(--color-bg-secondary)', borderColor: 'rgba(56, 189, 248, 0.25)' }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-sky-400">Outdated Facts</span>
                  <History size={14} className="text-sky-400" />
                </div>
                <span className="text-2xl font-bold text-sky-400">
                  {maintenanceSuggestions.filter((s) => s.issue_type === 'outdated').length}
                </span>
              </div>
            </div>

            {/* Filter and On-Demand Scan Bar */}
            <div
              className="p-3.5 rounded-xl border flex flex-wrap items-center justify-between gap-3"
              style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
            >
              <div className="flex flex-wrap items-center gap-2.5 flex-1 min-w-[280px]">
                {/* Issue Type Filter */}
                <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-900 border border-slate-800 text-xs">
                  {['all', 'duplicate', 'contradiction', 'outdated'].map((it) => (
                    <button
                      key={it}
                      onClick={() => setSelectedIssueType(it)}
                      className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer capitalize ${
                        selectedIssueType === it
                          ? 'bg-slate-800 text-white font-medium'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {it === 'all' ? 'All Types' : it}
                    </button>
                  ))}
                </div>

                {/* Status Filter */}
                <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-900 border border-slate-800 text-xs">
                  {['pending', 'approved', 'dismissed', 'all'].map((st) => (
                    <button
                      key={st}
                      onClick={() => setSelectedMaintenanceStatus(st)}
                      className={`px-2.5 py-1 rounded text-xs transition-colors cursor-pointer capitalize ${
                        selectedMaintenanceStatus === st
                          ? 'bg-slate-800 text-white font-medium'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {st === 'all' ? 'All Status' : st}
                    </button>
                  ))}
                </div>

                {/* Project Filter */}
                <select
                  value={selectedMaintenanceProject}
                  onChange={(e) => setSelectedMaintenanceProject(e.target.value)}
                  className="p-2 rounded-lg border outline-none text-xs cursor-pointer"
                  style={{
                    background: 'var(--color-bg-primary)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text-primary)',
                  }}
                >
                  <option value="all">All Projects</option>
                  {memoryProjects.map((proj) => (
                    <option key={proj} value={proj}>
                      Project: {proj}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={loadMaintenanceSuggestions}
                  disabled={maintenanceLoading}
                  className="p-1.5 rounded-lg border text-xs hover:bg-slate-800 transition-colors cursor-pointer"
                  style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}
                  title="Refresh Suggestions"
                >
                  <RefreshCw size={14} className={maintenanceLoading ? 'animate-spin' : ''} />
                </button>

                <button
                  onClick={handleScanMaintenance}
                  disabled={scanningMaintenance}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-slate-950 font-semibold text-xs transition-colors cursor-pointer"
                  title="Run on-demand scan. No changes are applied without your explicit approval."
                >
                  {scanningMaintenance ? (
                    <RefreshCw size={14} className="animate-spin" />
                  ) : (
                    <Wrench size={14} />
                  )}
                  <span>{scanningMaintenance ? 'Scanning Memories...' : 'Scan for Issues'}</span>
                </button>
              </div>
            </div>

            {/* Safety & Isolation Invariants Banner */}
            <div
              className="p-3.5 rounded-xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs"
              style={{
                background: 'rgba(56, 189, 248, 0.05)',
                borderColor: 'rgba(56, 189, 248, 0.25)',
              }}
            >
              <div className="flex items-center gap-2.5">
                <ShieldCheck size={18} className="text-sky-400 shrink-0" />
                <div className="flex flex-col gap-0.5">
                  <span className="font-bold text-sky-300">
                    Ultron Memory Safety &amp; Project Isolation Guardrails Active
                  </span>
                  <span className="text-[11px] text-slate-300">
                    • 100% On-Demand • Zero Automatic Mutations • Strict Project Boundaries • Quarantine Protection
                  </span>
                </div>
              </div>
              <span className="text-[11px] text-slate-400 bg-slate-900/80 px-2 py-1 rounded border border-slate-800 shrink-0">
                Operator Approval Mandatory
              </span>
            </div>

            {/* Suggestions Cards List */}
            {maintenanceLoading ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <RefreshCw size={24} className="animate-spin text-amber-400" />
                <span className="text-xs text-slate-400">Loading maintenance suggestions...</span>
              </div>
            ) : maintenanceSuggestions.length === 0 ? (
              <div
                className="flex flex-col items-center justify-center py-16 px-4 rounded-xl border border-dashed text-center"
                style={{ borderColor: 'var(--color-border)' }}
              >
                <Sparkles size={32} className="text-slate-500 mb-2" />
                <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                  No maintenance issues found
                </h3>
                <p className="text-xs text-slate-400 mt-1 max-w-md">
                  {selectedIssueType !== 'all' || selectedMaintenanceStatus !== 'all'
                    ? 'No suggestions match your active filter.'
                    : 'Your memory store is clean and consolidated! Click "Scan for Issues" at any time to run an on-demand audit.'}
                </p>
                <button
                  onClick={handleScanMaintenance}
                  disabled={scanningMaintenance}
                  className="mt-4 flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-600 text-slate-950 font-semibold text-xs transition-colors cursor-pointer"
                >
                  {scanningMaintenance ? <RefreshCw size={14} className="animate-spin" /> : <Wrench size={14} />}
                  <span>{scanningMaintenance ? 'Scanning...' : 'Run Memory Maintenance Scan'}</span>
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-4">
                {maintenanceSuggestions.map((sug) => {
                  const isPending = sug.status === 'pending';
                  const isApproved = sug.status === 'approved';
                  const isDismissed = sug.status === 'dismissed';

                  return (
                    <div
                      key={sug.id}
                      className="p-4 rounded-xl border flex flex-col gap-3.5 transition-all"
                      style={{
                        background: 'var(--color-bg-secondary)',
                        borderColor: isPending
                          ? 'rgba(245, 158, 11, 0.4)'
                          : isApproved
                          ? 'rgba(16, 185, 129, 0.35)'
                          : 'var(--color-border)',
                      }}
                    >
                      {/* Suggestion Top Row */}
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3 border-slate-800/80">
                        <div className="flex flex-wrap items-center gap-2">
                          <MaintenanceIssueBadge issueType={sug.issue_type} />
                          <ProposedActionBadge action={sug.proposed_action} />

                          {sug.quarantined_involved && (
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/40">
                              <ShieldAlert size={11} />
                              <span>QUARANTINE PROTECTED</span>
                            </span>
                          )}

                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                            project: {sug.project}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">
                            {sug.category.replace(/_/g, ' ')}
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          {isPending && (
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse">
                              <AlertTriangle size={11} />
                              <span>AWAITING APPROVAL</span>
                            </span>
                          )}
                          {isApproved && (
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                              <CheckCircle2 size={11} />
                              <span>APPROVED &amp; APPLIED</span>
                            </span>
                          )}
                          {isDismissed && (
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                              <XCircle size={11} />
                              <span>DISMISSED</span>
                            </span>
                          )}
                          <span className="text-[11px] text-slate-400">
                            {sug.created_at ? new Date(sug.created_at * 1000).toLocaleString() : ''}
                          </span>
                        </div>
                      </div>

                      {/* Explanation Callout */}
                      <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-slate-200 flex items-start gap-2.5">
                        <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
                        <div className="flex flex-col gap-0.5">
                          <span className="font-semibold text-slate-100">Analysis Finding:</span>
                          <span className="text-slate-300 leading-relaxed">{sug.reason}</span>
                        </div>
                      </div>

                      {/* Involved Memories List */}
                      <div className="flex flex-col gap-2">
                        <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                          Involved Memory Entries ({sug.source_facts.length})
                        </span>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                          {sug.source_facts.map((fact) => {
                            const isTargetKeep =
                              sug.proposed_resolution?.target_fact_id === fact.id ||
                              sug.proposed_resolution?.keep_fact_id === fact.id;
                            const isToRemove =
                              sug.proposed_resolution?.facts_to_remove?.includes(fact.id) ||
                              sug.proposed_resolution?.superseded_fact_id === fact.id ||
                              sug.proposed_resolution?.retire_fact_id === fact.id;

                            return (
                              <div
                                key={fact.id}
                                className={`p-3 rounded-lg border text-xs flex flex-col justify-between gap-2 ${
                                  isTargetKeep
                                    ? 'bg-emerald-500/5 border-emerald-500/30'
                                    : isToRemove
                                    ? 'bg-rose-500/5 border-rose-500/25'
                                    : 'bg-slate-900/50 border-slate-800'
                                }`}
                              >
                                <div>
                                  <div className="flex items-center justify-between gap-1.5 mb-1.5">
                                    <div className="flex items-center gap-1.5">
                                      <MemoryTrustBadge trust={fact.trust} />
                                      {fact.verified ? (
                                        <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                          <CheckCircle2 size={10} />
                                          <span>Verified</span>
                                        </span>
                                      ) : (
                                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">
                                          Unverified
                                        </span>
                                      )}
                                    </div>

                                    {isTargetKeep && (
                                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                                        PROPOSED KEEP
                                      </span>
                                    )}
                                    {isToRemove && (
                                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                                        TO REMOVE
                                      </span>
                                    )}
                                  </div>

                                  <p className="text-slate-200 leading-relaxed font-sans italic">
                                    "{fact.text}"
                                  </p>
                                </div>

                                <div className="flex items-center justify-between text-[10.5px] text-slate-400 pt-2 border-t border-slate-800/60">
                                  <span className="flex items-center gap-1">
                                    {renderSourceTypeIcon(fact.source_type)}
                                    <span className="truncate max-w-[150px]">{fact.source}</span>
                                  </span>
                                  <span className="font-mono text-slate-500 text-[10px]">{fact.id.slice(0, 10)}</span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Proposed Resolution Preview */}
                      <div className="p-3 rounded-lg border border-purple-500/30 bg-purple-500/5 text-xs flex flex-col gap-1.5">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-purple-300 flex items-center gap-1.5">
                            <Layers size={13} />
                            <span>Proposed Remediation ({sug.proposed_action.toUpperCase()})</span>
                          </span>
                        </div>
                        {sug.proposed_action === 'merge' && sug.proposed_resolution?.merged_text && (
                          <div className="flex flex-col gap-1 mt-1">
                            <span className="text-[11px] text-slate-400">Merged Memory Preview:</span>
                            <div className="p-2.5 rounded bg-black/40 border border-purple-500/20 font-sans text-slate-100 text-xs">
                              {sug.proposed_resolution.merged_text}
                            </div>
                            <span className="text-[10.5px] text-slate-400">
                              Redundant memory entries ({sug.proposed_resolution.facts_to_remove?.length || 0}) will be removed, preserving merged provenance IDs.
                            </span>
                          </div>
                        )}
                        {sug.proposed_resolution?.action_detail && (
                          <p className="text-slate-300 text-xs">
                            {sug.proposed_resolution.action_detail}
                          </p>
                        )}
                      </div>

                      {/* Card Footer Actions */}
                      <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs">
                        {isPending ? (
                          <>
                            <span className="text-[11px] text-slate-400">
                              Requires explicit approval to execute.
                            </span>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => openDismissModal(sug)}
                                className="px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 hover:text-slate-100 text-xs transition-colors cursor-pointer"
                              >
                                Dismiss
                              </button>
                              <button
                                onClick={() => openApproveModal(sug)}
                                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs transition-colors cursor-pointer"
                              >
                                <CheckCircle2 size={13} />
                                <span>Review &amp; Approve</span>
                              </button>
                            </div>
                          </>
                        ) : isApproved ? (
                          <div className="flex items-center justify-between w-full text-slate-400 text-xs">
                            <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
                              <CheckCircle2 size={14} />
                              <span>Approved and resolved by {sug.resolved_by || 'operator'}</span>
                            </span>
                            <span className="text-[11px]">
                              {sug.resolved_at ? new Date(sug.resolved_at * 1000).toLocaleString() : ''}
                            </span>
                          </div>
                        ) : (
                          <div className="flex items-center justify-between w-full text-slate-400 text-xs">
                            <span className="flex items-center gap-1.5 text-slate-400">
                              <XCircle size={14} />
                              <span>Dismissed: "{sug.dismiss_reason || 'Dismissed by operator'}"</span>
                            </span>
                            <span className="text-[11px]">
                              {sug.resolved_at ? new Date(sug.resolved_at * 1000).toLocaleString() : ''}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      {/* =================================================================== */}
      {/* MODAL: CREATE MEMORY                                               */}
      {/* =================================================================== */}
      {createMemoryOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div
            className="w-full max-w-lg rounded-2xl border p-6 shadow-2xl flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-150"
            style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
          >
            <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--color-border)' }}>
              <div className="flex items-center gap-2 text-sky-400">
                <Brain size={18} />
                <h2 className="text-base font-bold" style={{ color: 'var(--color-text-primary)' }}>
                  Add Persistent Memory Fact
                </h2>
              </div>
              <button
                onClick={() => setCreateMemoryOpen(false)}
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateMemory} className="flex flex-col gap-4 text-xs">
              <div className="flex flex-col gap-1.5">
                <label className="font-medium text-slate-300">Memory Text / Fact Statement *</label>
                <textarea
                  required
                  rows={4}
                  value={newMemoryText}
                  onChange={(e) => setNewMemoryText(e.target.value)}
                  placeholder="e.g. Always structure database queries using indexed primary keys."
                  className="p-3 rounded-lg border outline-none resize-none font-sans text-xs"
                  style={{
                    background: 'var(--color-bg-primary)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text-primary)',
                  }}
                />
                <span className="text-[11px] text-slate-400">
                  Sensitive credentials, API keys, passwords, and tokens are automatically scrubbed before persistence.
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <label className="font-medium text-slate-300">Category</label>
                  <select
                    value={newMemoryCategory}
                    onChange={(e) => setNewMemoryCategory(e.target.value)}
                    className="p-2.5 rounded-lg border outline-none cursor-pointer text-xs"
                    style={{
                      background: 'var(--color-bg-primary)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    {memoryCategories.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="font-medium text-slate-300">Project Scope</label>
                  <input
                    type="text"
                    value={newMemoryProject}
                    onChange={(e) => setNewMemoryProject(e.target.value)}
                    placeholder="default"
                    className="p-2.5 rounded-lg border outline-none text-xs"
                    style={{
                      background: 'var(--color-bg-primary)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text-primary)',
                    }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 items-center">
                <div className="flex flex-col gap-1.5">
                  <label className="font-medium text-slate-300">Trust Level</label>
                  <select
                    value={newMemoryTrust}
                    onChange={(e) => setNewMemoryTrust(e.target.value as any)}
                    className="p-2.5 rounded-lg border outline-none cursor-pointer text-xs"
                    style={{
                      background: 'var(--color-bg-primary)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    <option value="trusted">Trusted (Human Verified)</option>
                    <option value="auto">Auto-Extracted</option>
                    <option value="untrusted">Quarantined (Excluded)</option>
                  </select>
                </div>

                <div className="flex items-center gap-2 pt-5">
                  <input
                    type="checkbox"
                    id="new-verified-check"
                    checked={newMemoryVerified}
                    onChange={(e) => setNewMemoryVerified(e.target.checked)}
                    className="rounded border-slate-700 w-4 h-4 text-sky-500 cursor-pointer"
                  />
                  <label htmlFor="new-verified-check" className="font-medium text-slate-300 cursor-pointer">
                    Verified Ground Truth
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 mt-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setCreateMemoryOpen(false)}
                  className="px-4 py-2 rounded-lg text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingMemory}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-600 text-white font-medium transition-colors cursor-pointer"
                >
                  {submittingMemory ? <RefreshCw size={14} className="animate-spin" /> : <Plus size={14} />}
                  <span>Save Fact</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL: EDIT MEMORY                                                 */}
      {/* =================================================================== */}
      {editMemoryOpen && editingMemory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div
            className="w-full max-w-lg rounded-2xl border p-6 shadow-2xl flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-150"
            style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
          >
            <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--color-border)' }}>
              <div className="flex items-center gap-2 text-sky-400">
                <Edit3 size={18} />
                <h2 className="text-base font-bold" style={{ color: 'var(--color-text-primary)' }}>
                  Edit Persistent Memory
                </h2>
              </div>
              <button onClick={() => setEditMemoryOpen(false)} className="text-slate-400 hover:text-slate-200 cursor-pointer">
                ✕
              </button>
            </div>

            <form onSubmit={handleUpdateMemory} className="flex flex-col gap-4 text-xs">
              <div className="flex flex-col gap-1.5">
                <label className="font-medium text-slate-300">Memory Statement *</label>
                <textarea
                  required
                  rows={4}
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  className="p-3 rounded-lg border outline-none resize-none font-sans text-xs"
                  style={{
                    background: 'var(--color-bg-primary)',
                    borderColor: 'var(--color-border)',
                    color: 'var(--color-text-primary)',
                  }}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <label className="font-medium text-slate-300">Category</label>
                  <select
                    value={editCategory}
                    onChange={(e) => setEditCategory(e.target.value)}
                    className="p-2.5 rounded-lg border outline-none cursor-pointer text-xs"
                    style={{
                      background: 'var(--color-bg-primary)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    {memoryCategories.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="font-medium text-slate-300">Project</label>
                  <input
                    type="text"
                    value={editProject}
                    onChange={(e) => setEditProject(e.target.value)}
                    className="p-2.5 rounded-lg border outline-none text-xs"
                    style={{
                      background: 'var(--color-bg-primary)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text-primary)',
                    }}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 items-center">
                <div className="flex flex-col gap-1.5">
                  <label className="font-medium text-slate-300">Trust Level</label>
                  <select
                    value={editTrust}
                    onChange={(e) => setEditTrust(e.target.value)}
                    className="p-2.5 rounded-lg border outline-none cursor-pointer text-xs"
                    style={{
                      background: 'var(--color-bg-primary)',
                      borderColor: 'var(--color-border)',
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    <option value="trusted">Trusted (Recallable)</option>
                    <option value="auto">Auto-Extracted</option>
                    <option value="untrusted">Quarantined (Excluded)</option>
                  </select>
                </div>

                <div className="flex items-center gap-2 pt-5">
                  <input
                    type="checkbox"
                    id="edit-verified-check"
                    checked={editVerified}
                    onChange={(e) => setEditVerified(e.target.checked)}
                    className="rounded border-slate-700 w-4 h-4 text-sky-500 cursor-pointer"
                  />
                  <label htmlFor="edit-verified-check" className="font-medium text-slate-300 cursor-pointer">
                    Verified Ground Truth
                  </label>
                </div>
              </div>

              {/* Promoting quarantine alert */}
              {editingMemory.trust === 'untrusted' && editTrust === 'trusted' && (
                <div className="p-2.5 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2">
                  <AlertTriangle size={15} className="shrink-0 mt-0.5 text-amber-400" />
                  <div>
                    <span className="font-semibold">Promoting Quarantined Memory:</span> You are removing this memory
                    from quarantine and marking it trusted for future model planning context.
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 mt-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setEditMemoryOpen(false)}
                  className="px-4 py-2 rounded-lg text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingMemory}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-500 hover:bg-sky-600 text-white font-medium transition-colors cursor-pointer"
                >
                  {submittingMemory ? <RefreshCw size={14} className="animate-spin" /> : <Check size={14} />}
                  <span>Save Changes</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL: DELETE CONFIRMATION                                         */}
      {/* =================================================================== */}
      {deleteMemoryOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div
            className="w-full max-w-md rounded-2xl border p-6 shadow-2xl flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-150"
            style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
          >
            <div className="flex items-center gap-3 text-rose-400">
              <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/30">
                <Trash2 size={20} />
              </div>
              <div>
                <h3 className="text-base font-bold" style={{ color: 'var(--color-text-primary)' }}>
                  Delete Memory Fact
                </h3>
                <p className="text-xs text-slate-400">This action cannot be undone.</p>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Are you sure you want to permanently remove this persistent fact from the store? It will no longer be
              recalled in any future planning context.
            </p>

            <div className="flex items-center justify-end gap-2 mt-3 pt-3 border-t border-slate-800">
              <button
                onClick={() => {
                  setDeleteMemoryOpen(false);
                  setDeletingMemoryId(null);
                }}
                className="px-4 py-2 rounded-lg text-slate-400 hover:text-slate-200 text-xs transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteMemory}
                disabled={submittingMemory}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-medium transition-colors cursor-pointer"
              >
                {submittingMemory ? <RefreshCw size={14} className="animate-spin" /> : <Trash2 size={14} />}
                <span>Delete Permanently</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL: LEARNED SKILL DETAIL & WORKFLOW INSPECTION                   */}
      {/* =================================================================== */}
      {detailSkill && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div
            className="w-full max-w-3xl max-h-[88vh] rounded-2xl border p-6 shadow-2xl flex flex-col gap-4 overflow-y-auto animate-in fade-in zoom-in-95 duration-150"
            style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
          >
            {/* Header */}
            <div className="flex items-start justify-between border-b pb-3 border-slate-800">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-slate-100">{detailSkill.name}</h2>
                  <span className="text-xs font-mono text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded border border-purple-500/20">
                    v{detailSkill.version}
                  </span>
                  {(detailSkill.is_composite || detailSkill.steps?.some((st) => !!st.skill_name)) && (
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold">
                      <Layers size={10} />
                      <span>Composite Workflow</span>
                    </span>
                  )}
                  {detailSkill.is_protected && (
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-300 border border-slate-700">
                      <Lock size={10} />
                      <span>Protected</span>
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1">{detailSkill.description}</p>
              </div>
              <button onClick={() => setDetailSkill(null)} className="text-slate-400 hover:text-slate-200 cursor-pointer">
                ✕
              </button>
            </div>

            {/* Validation Checklist Box */}
            <SkillValidationChecklist validation={detailSkill.validation} />

            {/* Workflow Pipeline Steps */}
            <div className="flex flex-col gap-2">
              <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                <Layers size={14} className="text-sky-400" />
                <span>Execution Step Pipeline ({detailSkill.steps.length} Steps)</span>
              </h3>
              <StepDAGPipeline steps={detailSkill.steps} />
            </div>

            {/* Health & Reliability */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div className="p-2.5 rounded-lg border border-slate-800 bg-slate-900/50 flex flex-col gap-0.5">
                <span className="text-[10px] text-slate-400">Execution Count</span>
                <span className="font-bold text-slate-100">{detailSkill.health.execution_count}</span>
              </div>
              <div className="p-2.5 rounded-lg border border-slate-800 bg-slate-900/50 flex flex-col gap-0.5">
                <span className="text-[10px] text-slate-400">Consecutive Failures</span>
                <span className={`font-bold ${detailSkill.health.consecutive_failures > 0 ? 'text-amber-400' : 'text-slate-100'}`}>
                  {detailSkill.health.consecutive_failures}
                </span>
              </div>
              <div className="p-2.5 rounded-lg border border-slate-800 bg-slate-900/50 flex flex-col gap-0.5">
                <span className="text-[10px] text-slate-400">Approval State</span>
                <span className="font-bold capitalize text-slate-100">{detailSkill.approval_status.replace(/_/g, ' ')}</span>
              </div>
              <div className="p-2.5 rounded-lg border border-slate-800 bg-slate-900/50 flex flex-col gap-0.5">
                <span className="text-[10px] text-slate-400">Invocable</span>
                <span className="font-bold text-slate-100">{detailSkill.user_invocable ? 'Yes' : 'No'}</span>
              </div>
            </div>

            {/* Audit History from SkillLedger */}
            {detailSkill.audit_history && detailSkill.audit_history.length > 0 && (
              <div className="flex flex-col gap-2">
                <h3 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                  <History size={14} className="text-purple-400" />
                  <span>Audit Mutation Ledger</span>
                </h3>
                <div className="flex flex-col gap-1.5 max-h-40 overflow-y-auto">
                  {detailSkill.audit_history.map((record) => (
                    <div
                      key={record.id}
                      className="p-2 rounded border border-slate-800 bg-slate-900/40 text-[11px] flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-purple-300 font-semibold uppercase text-[10px]">
                          [{record.action}]
                        </span>
                        <span className="text-slate-300">{record.description}</span>
                      </div>
                      <span className="text-[10px] text-slate-400">
                        {new Date(record.timestamp * 1000).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Modal Footer */}
            <div className="flex items-center justify-between mt-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setDetailSkill(null)}
                className="px-4 py-2 rounded-lg text-slate-400 hover:text-slate-200 text-xs transition-colors cursor-pointer"
              >
                Close
              </button>

              {!detailSkill.is_protected && (
                <div className="flex items-center gap-2">
                  {detailSkill.approval_status === 'pending_review' && (
                    <>
                      <button
                        onClick={() => openSkillAction(detailSkill, 'reject')}
                        className="px-3 py-1.5 rounded-lg text-rose-400 bg-rose-500/10 hover:bg-rose-500/20 text-xs font-medium cursor-pointer"
                      >
                        Reject Skill
                      </button>
                      <button
                        onClick={() => openSkillAction(detailSkill, 'approve')}
                        disabled={!detailSkill.validation.is_valid}
                        className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium cursor-pointer"
                      >
                        Approve Skill
                      </button>
                    </>
                  )}
                  {detailSkill.approval_status === 'approved' && !detailSkill.disabled && (
                    <button
                      onClick={() => openSkillAction(detailSkill, 'disable')}
                      className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium cursor-pointer"
                    >
                      Disable Skill
                    </button>
                  )}
                  {detailSkill.disabled && (
                    <button
                      onClick={() => openSkillAction(detailSkill, 'enable')}
                      className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium cursor-pointer"
                    >
                      Enable Skill
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL: SKILL MUTATION ACTION (APPROVE / REJECT / DISABLE / ENABLE)   */}
      {/* =================================================================== */}
      {actionSkill && actionType && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div
            className="w-full max-w-md rounded-2xl border p-6 shadow-2xl flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-150"
            style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
          >
            <div className="flex items-center gap-3">
              <div
                className={`p-2 rounded-lg ${
                  actionType === 'approve' || actionType === 'enable'
                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                    : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                }`}
              >
                {actionType === 'approve' || actionType === 'enable' ? (
                  <CheckCircle2 size={20} />
                ) : (
                  <AlertTriangle size={20} />
                )}
              </div>
              <div>
                <h3 className="text-base font-bold capitalize text-slate-100">
                  {actionType} Skill: {actionSkill.name}
                </h3>
                <p className="text-xs text-slate-400">Confirm skill lifecycle state transition</p>
              </div>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              {actionType === 'approve' &&
                'Approving this skill authorizes it for normal tool discovery and agent plan execution. CapabilityPolicy and SafetyKernel boundaries continue to apply.'}
              {actionType === 'reject' &&
                'Rejecting this skill will mark it rejected and prevent execution by the task runner.'}
              {actionType === 'disable' &&
                'Disabling this skill will immediately remove it from active LLM discovery and block execution until re-enabled.'}
              {actionType === 'enable' &&
                'Re-enabling this skill restores its active invocation and discovery in task plans.'}
            </p>

            {/* Optional Reason field for Reject & Disable */}
            {(actionType === 'reject' || actionType === 'disable') && (
              <div className="flex flex-col gap-1.5 text-xs">
                <label className="font-medium text-slate-300">
                  {actionType === 'reject' ? 'Rejection Reason (Optional)' : 'Disabling Reason (Optional)'}
                </label>
                <input
                  type="text"
                  value={actionReason}
                  onChange={(e) => setActionReason(e.target.value)}
                  placeholder={actionType === 'reject' ? 'e.g. Unverified output format' : 'e.g. Upstream tool maintenance'}
                  className="p-2.5 rounded-lg border border-slate-700 bg-slate-900 text-slate-100 outline-none text-xs"
                />
              </div>
            )}

            <div className="flex items-center justify-end gap-2 mt-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => {
                  setActionType(null);
                  setActionSkill(null);
                }}
                className="px-4 py-2 rounded-lg text-slate-400 hover:text-slate-200 text-xs transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleExecuteSkillAction}
                disabled={submittingAction}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-white text-xs font-medium transition-colors cursor-pointer ${
                  actionType === 'approve' || actionType === 'enable'
                    ? 'bg-emerald-600 hover:bg-emerald-500'
                    : 'bg-rose-600 hover:bg-rose-500'
                }`}
              >
                {submittingAction && <RefreshCw size={14} className="animate-spin" />}
                <span className="capitalize">Confirm {actionType}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL: APPROVE MAINTENANCE SUGGESTION                               */}
      {/* =================================================================== */}
      {approvingSuggestion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div
            className="w-full max-w-lg rounded-2xl border p-6 shadow-2xl flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-150"
            style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
          >
            <div className="flex items-center justify-between border-b pb-3 border-slate-800">
              <div className="flex items-center gap-2 text-emerald-400">
                <CheckCircle2 size={18} />
                <h2 className="text-base font-bold text-slate-100">
                  Approve Memory Maintenance Resolution
                </h2>
              </div>
              <button
                onClick={() => setApprovingSuggestion(null)}
                className="text-slate-400 hover:text-slate-200 cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="flex flex-col gap-3 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <MaintenanceIssueBadge issueType={approvingSuggestion.issue_type} />
                <ProposedActionBadge action={approvingSuggestion.proposed_action} />
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300">
                  project: {approvingSuggestion.project}
                </span>
              </div>

              {/* Action Description */}
              <p className="text-slate-300 leading-relaxed">
                {approvingSuggestion.proposed_action === 'merge' &&
                  'Confirm merging redundant facts. Redundant memory facts will be deleted while preserving provenance history.'}
                {approvingSuggestion.proposed_action === 'supersede' &&
                  'Confirm superseding contradictory facts. The outdated fact will be retired and the verified fact preserved.'}
                {approvingSuggestion.proposed_action === 'delete' &&
                  'Confirm permanently retiring this outdated memory entry.'}
                {approvingSuggestion.proposed_action === 'mark_for_review' &&
                  'Confirm flagging these memory entries for manual review.'}
              </p>

              {/* Merge custom text editing */}
              {approvingSuggestion.proposed_action === 'merge' && (
                <div className="flex flex-col gap-1.5 mt-1">
                  <label className="font-semibold text-slate-200">
                    Merged Memory Statement (Editable) *
                  </label>
                  <textarea
                    rows={4}
                    value={customMergedText}
                    onChange={(e) => setCustomMergedText(e.target.value)}
                    placeholder="Enter the consolidated fact statement..."
                    className="p-3 rounded-lg border outline-none resize-none font-sans text-xs bg-slate-900 border-slate-700 text-slate-100 focus:border-emerald-500"
                  />
                  <span className="text-[10.5px] text-slate-400">
                    Any credentials or API keys will be automatically scrubbed. Injection checks will be enforced.
                  </span>
                </div>
              )}

              {/* Supersede / Delete detail */}
              {approvingSuggestion.proposed_action !== 'merge' && approvingSuggestion.proposed_resolution?.action_detail && (
                <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 text-xs">
                  <span className="font-semibold text-slate-200">Action Plan: </span>
                  {approvingSuggestion.proposed_resolution.action_detail}
                </div>
              )}

              {/* Quarantine Invariant Warning */}
              {approvingSuggestion.quarantined_involved && (
                <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2">
                  <ShieldAlert size={16} className="shrink-0 mt-0.5 text-rose-400" />
                  <div>
                    <span className="font-bold">Quarantine Protection Active: </span>
                    <span>
                      Because this finding involves quarantined memory, the resulting entry will remain strictly
                      UNTRUSTED and excluded from standard agent recall.
                    </span>
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2 mt-2 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setApprovingSuggestion(null)}
                className="px-4 py-2 rounded-lg text-slate-400 hover:text-slate-200 text-xs transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleExecuteApproval}
                disabled={submittingApproval}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs transition-colors cursor-pointer"
              >
                {submittingApproval ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                <span>Confirm &amp; Execute Action</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL: DISMISS MAINTENANCE SUGGESTION                               */}
      {/* =================================================================== */}
      {dismissingSuggestion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div
            className="w-full max-w-md rounded-2xl border p-6 shadow-2xl flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-150"
            style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
          >
            <div className="flex items-center gap-2.5 text-slate-200 border-b pb-3 border-slate-800">
              <XCircle size={18} className="text-slate-400" />
              <h2 className="text-base font-bold text-slate-100">
                Dismiss Maintenance Suggestion
              </h2>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Dismissing this suggestion marks it resolved without making any changes to stored memories. All memories
              will remain intact in their current state.
            </p>

            <div className="flex flex-col gap-1.5 text-xs">
              <label className="font-medium text-slate-300">Dismissal Reason (Optional)</label>
              <input
                type="text"
                value={dismissReason}
                onChange={(e) => setDismissReason(e.target.value)}
                placeholder="e.g. Both facts are intentionally distinct"
                className="p-2.5 rounded-lg border border-slate-700 bg-slate-900 text-slate-100 outline-none text-xs"
              />
            </div>

            <div className="flex items-center justify-end gap-2 mt-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setDismissingSuggestion(null)}
                className="px-4 py-2 rounded-lg text-slate-400 hover:text-slate-200 text-xs transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleExecuteDismiss}
                disabled={submittingDismiss}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-white font-medium text-xs transition-colors cursor-pointer"
              >
                {submittingDismiss && <RefreshCw size={14} className="animate-spin" />}
                <span>Confirm Dismissal</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL: SKILL COMPOSER                                               */}
      {/* =================================================================== */}
      {composerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div
            className="w-full max-w-3xl max-h-[90vh] rounded-2xl border p-6 shadow-2xl flex flex-col gap-4 overflow-y-auto animate-in fade-in zoom-in-95 duration-150"
            style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
          >
            <SkillComposer
              availableSkills={skills}
              onSkillCreated={() => {
                loadSkills();
              }}
              onClose={() => setComposerOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
