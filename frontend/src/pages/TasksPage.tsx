import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ListTodo,
  Play,
  Pause,
  XCircle,
  CheckCircle2,
  Clock,
  AlertTriangle,
  RefreshCw,
  Plus,
  ChevronDown,
  ChevronRight,
  ShieldAlert,
  ShieldCheck,
  Key,
  Copy,
  Check,
  FileCode,
  Layers,
  ArrowRight,
  Sliders,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  fetchTasks,
  pauseTask,
  resumeTask,
  cancelTask,
  approveTaskStep,
  rejectTaskStep,
  submitStepInput,
  createTask,
} from '../lib/api';
import type { TaskRecord, TaskStep, TaskStatus, StepStatus } from '../types';

// Status badge color and icon mapping
export const STATUS_CONFIG: Record<
  TaskStatus,
  { label: string; color: string; bg: string; border: string; icon: React.ElementType }
> = {
  running: {
    label: 'RUNNING',
    color: '#38bdf8',
    bg: 'rgba(56, 189, 248, 0.12)',
    border: 'rgba(56, 189, 248, 0.3)',
    icon: RefreshCw,
  },
  waiting_approval: {
    label: 'WAITING APPROVAL',
    color: '#f59e0b',
    bg: 'rgba(245, 158, 11, 0.15)',
    border: 'rgba(245, 158, 11, 0.4)',
    icon: AlertTriangle,
  },
  completed: {
    label: 'COMPLETED',
    color: '#10b981',
    bg: 'rgba(16, 185, 129, 0.12)',
    border: 'rgba(16, 185, 129, 0.3)',
    icon: CheckCircle2,
  },
  failed: {
    label: 'FAILED',
    color: '#ef4444',
    bg: 'rgba(239, 68, 68, 0.12)',
    border: 'rgba(239, 68, 68, 0.3)',
    icon: XCircle,
  },
  paused: {
    label: 'PAUSED',
    color: '#eab308',
    bg: 'rgba(234, 179, 8, 0.12)',
    border: 'rgba(234, 179, 8, 0.3)',
    icon: Pause,
  },
  cancelled: {
    label: 'CANCELLED',
    color: '#94a3b8',
    bg: 'rgba(148, 163, 184, 0.12)',
    border: 'rgba(148, 163, 184, 0.3)',
    icon: XCircle,
  },
  queued: {
    label: 'QUEUED',
    color: '#a855f7',
    bg: 'rgba(168, 85, 247, 0.12)',
    border: 'rgba(168, 85, 247, 0.3)',
    icon: Clock,
  },
};

export const STEP_STATUS_CONFIG: Record<
  StepStatus,
  { label: string; color: string; icon: React.ElementType }
> = {
  pending: { label: 'Pending', color: 'var(--color-text-tertiary)', icon: Clock },
  running: { label: 'Running', color: '#38bdf8', icon: RefreshCw },
  waiting_approval: { label: 'Waiting Approval', color: '#f59e0b', icon: AlertTriangle },
  completed: { label: 'Completed', color: '#10b981', icon: CheckCircle2 },
  failed: { label: 'Failed', color: '#ef4444', icon: XCircle },
  cancelled: { label: 'Cancelled', color: '#94a3b8', icon: XCircle },
  skipped: { label: 'Skipped', color: '#64748b', icon: ArrowRight },
};

// ---------------------------------------------------------------------------
// Subcomponent: TaskStatusBadge
// ---------------------------------------------------------------------------
export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.queued;
  const Icon = cfg.icon;
  return (
    <span
      data-testid={`status-badge-${status}`}
      className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border"
      style={{
        color: cfg.color,
        background: cfg.bg,
        borderColor: cfg.border,
      }}
    >
      <Icon size={12} className={status === 'running' ? 'animate-spin' : ''} />
      <span>{cfg.label}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Subcomponent: MetricsSummary
// ---------------------------------------------------------------------------
export function MetricsSummary({ tasks }: { tasks: TaskRecord[] }) {
  const totalCount = tasks.length;
  const activeCount = tasks.filter((t) => t.status === 'running' || t.status === 'queued').length;
  const waitingApprovalCount = tasks.filter((t) => t.status === 'waiting_approval').length;
  const completedCount = tasks.filter((t) => t.status === 'completed').length;
  const failedCount = tasks.filter((t) => t.status === 'failed').length;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6 shrink-0" data-testid="metrics-summary">
      <div
        className="p-3.5 rounded-xl border flex flex-col justify-between"
        style={{ background: 'var(--color-bg-secondary)', borderColor: 'var(--color-border)' }}
      >
        <span className="text-[11px] font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          Total Tasks
        </span>
        <span className="text-xl font-bold mt-1" style={{ color: 'var(--color-text)' }}>
          {totalCount}
        </span>
      </div>

      <div
        className="p-3.5 rounded-xl border flex flex-col justify-between"
        style={{
          background: 'rgba(56, 189, 248, 0.05)',
          borderColor: 'rgba(56, 189, 248, 0.25)',
        }}
      >
        <span className="text-[11px] font-medium" style={{ color: '#38bdf8' }}>
          Active & Queued
        </span>
        <span className="text-xl font-bold mt-1" style={{ color: '#38bdf8' }}>
          {activeCount}
        </span>
      </div>

      <div
        className="p-3.5 rounded-xl border flex flex-col justify-between"
        style={{
          background: 'rgba(245, 158, 11, 0.08)',
          borderColor: 'rgba(245, 158, 11, 0.35)',
        }}
      >
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-amber-500">Needs Approval</span>
          {waitingApprovalCount > 0 && (
            <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
          )}
        </div>
        <span className="text-xl font-bold mt-1 text-amber-500">
          {waitingApprovalCount}
        </span>
      </div>

      <div
        className="p-3.5 rounded-xl border flex flex-col justify-between"
        style={{
          background: 'rgba(16, 185, 129, 0.05)',
          borderColor: 'rgba(16, 185, 129, 0.25)',
        }}
      >
        <span className="text-[11px] font-medium text-emerald-500">Completed</span>
        <span className="text-xl font-bold mt-1 text-emerald-500">
          {completedCount}
        </span>
      </div>

      <div
        className="p-3.5 rounded-xl border flex flex-col justify-between col-span-2 sm:col-span-1"
        style={{
          background: 'rgba(239, 68, 68, 0.05)',
          borderColor: 'rgba(239, 68, 68, 0.25)',
        }}
      >
        <span className="text-[11px] font-medium text-rose-500">Failed</span>
        <span className="text-xl font-bold mt-1 text-rose-500">
          {failedCount}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subcomponent: OperatorApprovalPanel
// ---------------------------------------------------------------------------
export interface OperatorApprovalPanelProps {
  step: TaskStep;
  resolution?: string;
  confirmDuplicate?: boolean;
  safetyCode?: string;
  rejectReason?: string;
  isLoading?: boolean;
  onResolutionChange?: (res: string) => void;
  onConfirmDuplicateChange?: (checked: boolean) => void;
  onSafetyCodeChange?: (code: string) => void;
  onRejectReasonChange?: (reason: string) => void;
  onApprove?: () => void;
  onReject?: () => void;
}

export function OperatorApprovalPanel({
  step,
  resolution,
  confirmDuplicate = false,
  safetyCode = '',
  rejectReason = '',
  isLoading = false,
  onResolutionChange,
  onConfirmDuplicateChange,
  onSafetyCodeChange,
  onRejectReasonChange,
  onApprove,
  onReject,
}: OperatorApprovalPanelProps) {
  const stepKey = step.step_id;
  const isUncertain = !!step.safety_decision?.uncertain_external_action;
  const currentRes = resolution || (isUncertain ? 'mark_completed' : '');

  return (
    <div
      data-testid={`approval-panel-${stepKey}`}
      className="mt-3.5 p-3.5 rounded-xl border shadow-sm space-y-3"
      style={{
        background: 'rgba(245, 158, 11, 0.06)',
        borderColor: 'rgba(245, 158, 11, 0.45)',
      }}
    >
      <div className="flex items-center gap-2">
        <ShieldAlert size={16} className="text-amber-500 shrink-0" />
        <span className="text-xs font-bold" style={{ color: '#f59e0b' }}>
          Operator Authorization & Resolution Required
        </span>
      </div>

      {/* Decision reason */}
      {step.safety_decision?.reason && (
        <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {step.safety_decision.reason}
        </p>
      )}

      {/* UNCERTAIN EXTERNAL ACTION DUPLICATE RISK WARNING */}
      {isUncertain && (
        <div
          data-testid="duplicate-risk-warning"
          className="p-3 rounded-lg border space-y-2.5"
          style={{
            background: 'rgba(245, 158, 11, 0.1)',
            borderColor: 'rgba(245, 158, 11, 0.4)',
          }}
        >
          <div className="flex items-start gap-2">
            <AlertTriangle size={15} className="text-amber-500 shrink-0 mt-0.5" />
            <div className="text-xs">
              <span className="font-bold text-amber-500 block mb-0.5">
                Duplicate-Action Risk Detected
              </span>
              <span style={{ color: 'var(--color-text)' }}>
                {step.safety_decision?.duplicate_action_risk ||
                  'External action timed out or disconnected. Remote execution status is unknown. Blindly retrying may result in duplicate side effects (e.g., repeated charges, redundant API requests, or duplicate messages).'}
              </span>
            </div>
          </div>

          {/* Resolution Selector */}
          <div className="space-y-1.5 pt-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider block text-amber-400">
              Select Resolution Mode:
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <label
                className="flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer transition-colors"
                style={{
                  background:
                    currentRes === 'mark_completed'
                      ? 'rgba(16, 185, 129, 0.15)'
                      : 'var(--color-bg-secondary)',
                  borderColor:
                    currentRes === 'mark_completed'
                      ? 'rgba(16, 185, 129, 0.5)'
                      : 'var(--color-border)',
                }}
              >
                <input
                  type="radio"
                  name={`resolution_${stepKey}`}
                  value="mark_completed"
                  checked={currentRes === 'mark_completed'}
                  onChange={() => onResolutionChange?.('mark_completed')}
                  className="accent-emerald-500"
                />
                <div>
                  <span className="font-semibold block text-emerald-400">
                    Mark Completed
                  </span>
                  <span className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
                    Confirmed succeeded on remote system
                  </span>
                </div>
              </label>

              <label
                className="flex items-center gap-2 p-2.5 rounded-lg border cursor-pointer transition-colors"
                style={{
                  background:
                    currentRes === 'force_retry'
                      ? 'rgba(239, 68, 68, 0.15)'
                      : 'var(--color-bg-secondary)',
                  borderColor:
                    currentRes === 'force_retry'
                      ? 'rgba(239, 68, 68, 0.5)'
                      : 'var(--color-border)',
                }}
              >
                <input
                  type="radio"
                  name={`resolution_${stepKey}`}
                  value="force_retry"
                  checked={currentRes === 'force_retry'}
                  onChange={() => onResolutionChange?.('force_retry')}
                  className="accent-rose-500"
                />
                <div>
                  <span className="font-semibold block text-rose-400">
                    Force Re-execution
                  </span>
                  <span className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
                    Re-dispatch external action
                  </span>
                </div>
              </label>
            </div>
          </div>

          {/* Mandatory confirmation checkbox if force_retry */}
          {currentRes === 'force_retry' && (
            <div
              data-testid="force-retry-warning-box"
              className="p-2.5 rounded-lg border mt-2 space-y-1.5"
              style={{
                background: 'rgba(239, 68, 68, 0.08)',
                borderColor: 'rgba(239, 68, 68, 0.3)',
              }}
            >
              <p className="text-[11px] text-rose-300">
                {step.safety_decision?.force_retry_warning ||
                  'WARNING: Force-retrying may repeat the external action and cause duplicate messages, requests, or other side effects. Explicit operator confirmation is required.'}
              </p>
              <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={confirmDuplicate}
                  onChange={(e) => onConfirmDuplicateChange?.(e.target.checked)}
                  className="rounded accent-rose-500"
                />
                <span className="font-medium text-rose-200">
                  I confirm that I understand this external action may be repeated and cause duplicate side effects.
                </span>
              </label>
            </div>
          )}
        </div>
      )}

      {/* Safety Code Input if required by policy */}
      {step.requires_code && (
        <div className="space-y-1.5 pt-1" data-testid="safety-code-container">
          <div className="flex items-center gap-1.5">
            <Key size={13} className="text-amber-400" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-400">
              Safety Code Required
            </span>
          </div>
          <p className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
            This high-risk action requires your verified PBKDF2 safety code.
          </p>
          <input
            type="password"
            placeholder="Enter safety code..."
            value={safetyCode}
            onChange={(e) => onSafetyCodeChange?.(e.target.value)}
            className="w-full sm:w-64 p-2 rounded-lg text-xs font-mono focus:outline-none"
            style={{
              background: 'var(--color-bg-secondary)',
              color: 'var(--color-text)',
              border: '1px solid var(--color-border)',
            }}
          />
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Rejection reason (optional)..."
            value={rejectReason}
            onChange={(e) => onRejectReasonChange?.(e.target.value)}
            className="p-1.5 rounded-lg text-xs w-48 sm:w-60 focus:outline-none"
            style={{
              background: 'var(--color-bg-secondary)',
              color: 'var(--color-text)',
              border: '1px solid var(--color-border)',
            }}
          />
          <button
            type="button"
            data-testid="reject-button"
            onClick={onReject}
            disabled={isLoading}
            className="px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors disabled:opacity-50"
            style={{
              background: 'rgba(239, 68, 68, 0.1)',
              color: '#ef4444',
              border: '1px solid rgba(239, 68, 68, 0.3)',
            }}
          >
            Reject Step
          </button>
        </div>

        <button
          type="button"
          data-testid="authorize-button"
          onClick={onApprove}
          disabled={
            isLoading ||
            (isUncertain && currentRes === 'force_retry' && !confirmDuplicate) ||
            (step.requires_code && !safetyCode)
          }
          className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold cursor-pointer transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
          style={{
            background: '#10b981',
            color: '#ffffff',
          }}
        >
          {isLoading ? (
            <>
              <RefreshCw size={12} className="animate-spin" />
              <span>Authorizing...</span>
            </>
          ) : (
            <>
              <ShieldCheck size={14} />
              <span>
                {currentRes === 'mark_completed'
                  ? 'Mark Resolved'
                  : currentRes === 'force_retry'
                  ? 'Confirm Force Retry'
                  : 'Authorize & Execute'}
              </span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subcomponent: StepUserInputPanel
// ---------------------------------------------------------------------------
export interface StepUserInputPanelProps {
  step: TaskStep;
  inputValues?: Record<string, any>;
  onInputChange?: (fieldName: string, value: any) => void;
  onSubmitInput?: () => void;
  onReject?: () => void;
  isLoading?: boolean;
  validationError?: string | null;
}

export function StepUserInputPanel({
  step,
  inputValues = {},
  onInputChange,
  onSubmitInput,
  onReject,
  isLoading = false,
  validationError = null,
}: StepUserInputPanelProps) {
  const stepKey = step.step_id;
  const decision = step.safety_decision || {};
  const schema = decision.schema || {};
  const properties = (schema.properties as Record<string, any>) || {};
  const missingFields: string[] = decision.missing_fields || schema.required || [];

  // Determine which fields to present: all missing fields, plus any properties in schema
  const displayFields = Array.from(new Set([...missingFields, ...Object.keys(properties)]));

  return (
    <div
      data-testid={`user-input-panel-${stepKey}`}
      className="mt-3.5 p-3.5 rounded-xl border shadow-sm space-y-3"
      style={{
        background: 'rgba(6, 182, 212, 0.05)',
        borderColor: 'rgba(6, 182, 212, 0.4)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sliders size={16} className="text-cyan-400 shrink-0" />
          <span className="text-xs font-bold text-cyan-400">
            User Input Required: Tool Parameters Missing
          </span>
        </div>
        <span
          className="text-[10px] font-mono px-2 py-0.5 rounded-full"
          style={{
            background: 'rgba(6, 182, 212, 0.15)',
            color: '#22d3ee',
            border: '1px solid rgba(6, 182, 212, 0.3)',
          }}
        >
          {step.tool_name}
        </span>
      </div>

      {/* Explanation / Prompt */}
      <p className="text-xs text-slate-300" data-testid="user-input-prompt">
        {decision.prompt || step.error || 'Essential parameters are missing for this tool. Please provide the required values below.'}
      </p>

      {/* Missing Fields Badge Indicators */}
      {missingFields.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-cyan-400">
            Missing:
          </span>
          {missingFields.map((field) => (
            <span
              key={field}
              data-testid={`missing-field-badge-${field}`}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-950/60 border border-cyan-500/40 text-cyan-300"
            >
              {field}
            </span>
          ))}
        </div>
      )}

      {/* Form Controls based on Tool Schema */}
      <div className="space-y-3 pt-1" data-testid="user-input-controls">
        {displayFields.length === 0 ? (
          <div className="text-xs text-slate-400">No parameter schema available. Please enter arguments manually.</div>
        ) : (
          displayFields.map((fieldName) => {
            const prop = properties[fieldName] || {};
            const propType = prop.type || 'string';
            const isMissing = missingFields.includes(fieldName);
            const isRequired = isMissing || (schema.required && schema.required.includes(fieldName));
            const enumValues = prop.enum;
            const description = prop.description || '';
            const currentValue = inputValues[fieldName] ?? step.tool_args?.[fieldName] ?? '';

            return (
              <div
                key={fieldName}
                data-testid={`input-group-${fieldName}`}
                className="space-y-1.5 p-2.5 rounded-lg border"
                style={{
                  background: 'var(--color-bg-secondary)',
                  borderColor: isMissing ? 'rgba(6, 182, 212, 0.3)' : 'var(--color-border)',
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-mono font-semibold" style={{ color: 'var(--color-text)' }}>
                      {fieldName}
                    </span>
                    <span className="text-[10px] font-mono px-1 rounded bg-slate-800 text-slate-400">
                      {propType}
                    </span>
                    {isRequired && (
                      <span className="text-[10px] font-semibold text-rose-400">
                        *required
                      </span>
                    )}
                  </div>
                  {prop.default !== undefined && (
                    <span className="text-[10px] text-slate-400">
                      Default: {String(prop.default)}
                    </span>
                  )}
                </div>

                {description && (
                  <p className="text-[11px] text-slate-400">
                    {description}
                  </p>
                )}

                {/* Input control rendering based on type */}
                {Array.isArray(enumValues) && enumValues.length > 0 ? (
                  <select
                    data-testid={`input-field-${fieldName}`}
                    value={currentValue}
                    onChange={(e) => onInputChange?.(fieldName, e.target.value)}
                    disabled={isLoading}
                    className="w-full p-2 rounded-lg text-xs font-mono focus:outline-none"
                    style={{
                      background: 'var(--color-bg-tertiary)',
                      color: 'var(--color-text)',
                      border: '1px solid var(--color-border)',
                    }}
                  >
                    <option value="">Select an option...</option>
                    {enumValues.map((v) => (
                      <option key={v} value={v}>
                        {v}
                      </option>
                    ))}
                  </select>
                ) : propType === 'boolean' ? (
                  <label className="flex items-center gap-2 cursor-pointer select-none pt-1">
                    <input
                      type="checkbox"
                      data-testid={`input-field-${fieldName}`}
                      checked={Boolean(currentValue)}
                      onChange={(e) => onInputChange?.(fieldName, e.target.checked)}
                      disabled={isLoading}
                      className="rounded accent-cyan-500 w-4 h-4"
                    />
                    <span className="text-xs text-slate-300 font-medium">
                      Enable {fieldName}
                    </span>
                  </label>
                ) : propType === 'integer' || propType === 'number' ? (
                  <input
                    type="number"
                    step={propType === 'integer' ? '1' : 'any'}
                    min={prop.minimum}
                    max={prop.maximum}
                    data-testid={`input-field-${fieldName}`}
                    placeholder={`Enter ${fieldName} (${propType})...`}
                    value={currentValue}
                    onChange={(e) => onInputChange?.(fieldName, e.target.value)}
                    disabled={isLoading}
                    className="w-full p-2 rounded-lg text-xs font-mono focus:outline-none"
                    style={{
                      background: 'var(--color-bg-tertiary)',
                      color: 'var(--color-text)',
                      border: '1px solid var(--color-border)',
                    }}
                  />
                ) : propType === 'object' || propType === 'array' ? (
                  <div className="space-y-1">
                    <textarea
                      rows={3}
                      data-testid={`input-field-${fieldName}`}
                      placeholder={
                        propType === 'object'
                          ? '{\n  "key": "value"\n}'
                          : '[\n  "item1",\n  "item2"\n]'
                      }
                      value={
                        typeof currentValue === 'object'
                          ? JSON.stringify(currentValue, null, 2)
                          : currentValue
                      }
                      onChange={(e) => onInputChange?.(fieldName, e.target.value)}
                      disabled={isLoading}
                      className="w-full p-2 rounded-lg text-xs font-mono focus:outline-none"
                      style={{
                        background: 'var(--color-bg-tertiary)',
                        color: 'var(--color-text)',
                        border: '1px solid var(--color-border)',
                      }}
                    />
                    <span className="text-[10px] text-slate-500 block">
                      Must be valid JSON {propType}
                    </span>
                  </div>
                ) : (
                  <input
                    type="text"
                    data-testid={`input-field-${fieldName}`}
                    placeholder={`Enter ${fieldName}...`}
                    value={currentValue}
                    onChange={(e) => onInputChange?.(fieldName, e.target.value)}
                    disabled={isLoading}
                    className="w-full p-2 rounded-lg text-xs font-mono focus:outline-none"
                    style={{
                      background: 'var(--color-bg-tertiary)',
                      color: 'var(--color-text)',
                      border: '1px solid var(--color-border)',
                    }}
                  />
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Validation Error Banner */}
      {validationError && (
        <div
          data-testid="input-validation-error"
          className="p-2.5 rounded-lg text-xs border"
          style={{
            background: 'rgba(239, 68, 68, 0.08)',
            borderColor: 'rgba(239, 68, 68, 0.3)',
            color: '#ef4444',
          }}
        >
          <span className="font-semibold block mb-0.5">Validation Error:</span>
          <span>{validationError}</span>
        </div>
      )}

      {/* Security notice */}
      <div
        className="p-2 rounded-lg border text-[11px]"
        style={{
          background: 'rgba(56, 189, 248, 0.04)',
          borderColor: 'rgba(56, 189, 248, 0.2)',
          color: 'var(--color-text-secondary)',
        }}
      >
        <div className="flex items-start gap-1.5">
          <ShieldAlert size={13} className="text-cyan-400 shrink-0 mt-0.5" />
          <span>
            Security Policy: Supplying missing parameters does not bypass permissions or authorize risky actions. If this action is classified as high-risk, operator authorization with safety code will be required before execution.
          </span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between gap-3 pt-1">
        {onReject && (
          <button
            type="button"
            data-testid="reject-input-button"
            onClick={onReject}
            disabled={isLoading}
            className="px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer transition-colors disabled:opacity-50"
            style={{
              background: 'rgba(239, 68, 68, 0.1)',
              color: '#ef4444',
              border: '1px solid rgba(239, 68, 68, 0.3)',
            }}
          >
            Reject Step
          </button>
        )}

        <button
          type="button"
          data-testid="submit-input-button"
          onClick={onSubmitInput}
          disabled={isLoading}
          className="ml-auto flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold cursor-pointer transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
          style={{
            background: '#06b6d4',
            color: '#000000',
          }}
        >
          {isLoading ? (
            <>
              <RefreshCw size={12} className="animate-spin text-black" />
              <span>Validating...</span>
            </>
          ) : (
            <>
              <Sliders size={13} className="text-black" />
              <span>Submit Arguments</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subcomponent: StepCard
// ---------------------------------------------------------------------------
export interface StepCardProps {
  step: TaskStep;
  idx: number;
  approvalProps?: OperatorApprovalPanelProps;
  userInputProps?: StepUserInputPanelProps;
}

export function StepCard({ step, idx, approvalProps, userInputProps }: StepCardProps) {
  const isInputRequired = Boolean(step.requires_user_input || step.safety_decision?.requires_user_input);
  const isWaiting = step.status === 'waiting_approval';
  const stepCfg = isInputRequired && isWaiting
    ? { label: 'Waiting for Input', color: '#06b6d4', icon: Sliders }
    : STEP_STATUS_CONFIG[step.status] || STEP_STATUS_CONFIG.pending;

  return (
    <div
      data-testid={`step-card-${step.step_id}`}
      className="rounded-xl border p-3.5 transition-all"
      style={{
        background: isWaiting
          ? isInputRequired
            ? 'rgba(6, 182, 212, 0.04)'
            : 'rgba(245, 158, 11, 0.04)'
          : 'var(--color-bg-secondary)',
        borderColor: isWaiting
          ? isInputRequired
            ? 'rgba(6, 182, 212, 0.4)'
            : 'rgba(245, 158, 11, 0.4)'
          : 'var(--color-border)',
      }}
    >
      {/* Step Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0"
            style={{
              background: isWaiting
                ? isInputRequired
                  ? '#06b6d4'
                  : '#f59e0b'
                : 'var(--color-bg-tertiary)',
              color: isWaiting ? '#000000' : 'var(--color-text-secondary)',
            }}
          >
            {idx + 1}
          </span>

          <div className="min-w-0">
            <h5 className="text-xs font-semibold truncate" style={{ color: 'var(--color-text)' }}>
              {step.title}
            </h5>
            <div className="flex items-center gap-2 mt-0.5">
              <span
                className="text-[10px] font-mono px-1.5 py-0.2 rounded"
                style={{
                  background: 'var(--color-bg-tertiary)',
                  color: 'var(--color-accent)',
                }}
              >
                {step.tool_name}
              </span>

              {step.dependencies && step.dependencies.length > 0 && (
                <span className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
                  Depends on: {step.dependencies.join(', ')}
                </span>
              )}

              <span className="text-[10px]" style={{ color: 'var(--color-text-tertiary)' }}>
                Retries: {step.retry_count}/{step.max_retries}
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold"
            style={{
              color: stepCfg.color,
              background: 'rgba(0, 0, 0, 0.2)',
            }}
          >
            <stepCfg.icon size={11} className={step.status === 'running' ? 'animate-spin' : ''} />
            <span>{stepCfg.label}</span>
          </span>
        </div>
      </div>

      {/* Step Arguments preview */}
      {step.tool_args && Object.keys(step.tool_args).length > 0 && (
        <div
          data-testid="step-arguments"
          className="mt-2.5 p-2 rounded-lg text-[11px] font-mono overflow-x-auto"
          style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-text-secondary)' }}
        >
          <span className="text-[10px] uppercase font-sans font-semibold tracking-wider block text-slate-500 mb-1">
            Arguments:
          </span>
          <pre className="text-[11px] whitespace-pre-wrap">
            {JSON.stringify(step.tool_args, null, 2)}
          </pre>
        </div>
      )}

      {/* Step Output preview */}
      {step.actual_output && (
        <div
          data-testid="step-output"
          className="mt-2 p-2 rounded-lg text-[11px] font-mono overflow-x-auto"
          style={{
            background: 'rgba(16, 185, 129, 0.05)',
            border: '1px solid rgba(16, 185, 129, 0.2)',
            color: 'var(--color-text)',
          }}
        >
          <span className="text-[10px] uppercase font-sans font-semibold tracking-wider block text-emerald-500 mb-1">
            Output:
          </span>
          <pre className="text-[11px] whitespace-pre-wrap">{step.actual_output}</pre>
        </div>
      )}

      {/* Step Error */}
      {step.error && (
        <div
          data-testid="step-error"
          className="mt-2 p-2 rounded-lg text-xs border"
          style={{
            background: 'rgba(239, 68, 68, 0.06)',
            borderColor: 'rgba(239, 68, 68, 0.25)',
            color: '#ef4444',
          }}
        >
          <span className="font-semibold block mb-0.5">Error:</span>
          <span className="font-mono">{step.error}</span>
        </div>
      )}

      {/* Step Artifacts */}
      {step.artifacts && step.artifacts.length > 0 && (
        <div data-testid="step-artifacts" className="mt-2 flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-tertiary)' }}>
            Artifacts:
          </span>
          {step.artifacts.map((art, aIdx) => (
            <span
              key={aIdx}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono"
              style={{ background: 'var(--color-bg-tertiary)', color: 'var(--color-accent)' }}
            >
              <FileCode size={11} />
              <span>{art}</span>
            </span>
          ))}
        </div>
      )}

      {/* Operator Approval & Resolution Panel vs User Input Panel */}
      {isWaiting && (
        isInputRequired && userInputProps ? (
          <StepUserInputPanel {...userInputProps} />
        ) : approvalProps ? (
          <OperatorApprovalPanel {...approvalProps} />
        ) : null
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Subcomponent: TaskCard
// ---------------------------------------------------------------------------
export interface TaskCardProps {
  task: TaskRecord;
  isExpanded: boolean;
  copiedTaskId?: string | null;
  actionLoading?: Record<string, boolean>;
  approvalResolutions?: Record<string, string>;
  approvalConfirmDuplicate?: Record<string, boolean>;
  approvalSafetyCodes?: Record<string, string>;
  rejectReasons?: Record<string, string>;
  onToggleExpand?: (taskId: string) => void;
  onCopyTaskId?: (taskId: string, e: React.MouseEvent) => void;
  onPause?: (taskId: string, e: React.MouseEvent) => void;
  onResume?: (taskId: string, e: React.MouseEvent) => void;
  onCancel?: (taskId: string, e: React.MouseEvent) => void;
  onApproveStep?: (task: TaskRecord, step: TaskStep) => void;
  onRejectStep?: (task: TaskRecord, step: TaskStep) => void;
  onResolutionChange?: (stepId: string, res: string) => void;
  onConfirmDuplicateChange?: (stepId: string, checked: boolean) => void;
  onSafetyCodeChange?: (stepId: string, code: string) => void;
  onRejectReasonChange?: (stepId: string, reason: string) => void;
  stepInputs?: Record<string, Record<string, any>>;
  inputValidationErrors?: Record<string, string>;
  onStepInputChange?: (stepId: string, fieldName: string, value: any) => void;
  onSubmitStepInput?: (task: TaskRecord, step: TaskStep) => void;
}

export function TaskCard({
  task,
  isExpanded,
  copiedTaskId,
  actionLoading = {},
  approvalResolutions = {},
  approvalConfirmDuplicate = {},
  approvalSafetyCodes = {},
  rejectReasons = {},
  onToggleExpand,
  onCopyTaskId,
  onPause,
  onResume,
  onCancel,
  onApproveStep,
  onRejectStep,
  onResolutionChange,
  onConfirmDuplicateChange,
  onSafetyCodeChange,
  onRejectReasonChange,
  stepInputs = {},
  inputValidationErrors = {},
  onStepInputChange,
  onSubmitStepInput,
}: TaskCardProps) {
  const statusCfg = STATUS_CONFIG[task.status] || STATUS_CONFIG.queued;
  const totalSteps = task.steps?.length || 0;
  const completedSteps = task.steps?.filter((s) => s.status === 'completed').length || 0;
  const progressPct = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;
  const waitingStep = task.steps?.find((s) => s.status === 'waiting_approval');
  const currentStep = task.steps?.find((s) => s.status === 'running') || waitingStep;

  return (
    <div
      data-testid={`task-card-${task.task_id}`}
      className="rounded-xl border transition-all overflow-hidden"
      style={{
        background: 'var(--color-bg-secondary)',
        borderColor:
          task.status === 'waiting_approval'
            ? 'rgba(245, 158, 11, 0.4)'
            : isExpanded
            ? 'var(--color-accent)'
            : 'var(--color-border)',
      }}
    >
      {/* Task Card Header / Primary Row */}
      <div
        onClick={() => onToggleExpand?.(task.task_id)}
        className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer select-none transition-colors"
        style={{ background: isExpanded ? 'var(--color-bg-tertiary)' : 'transparent' }}
      >
        <div className="flex items-start sm:items-center gap-3 min-w-0 flex-1">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggleExpand?.(task.task_id);
            }}
            className="mt-0.5 sm:mt-0 p-1 rounded-md transition-colors"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <TaskStatusBadge status={task.status} />

              {/* Task ID chip with copy button */}
              <span
                onClick={(e) => onCopyTaskId?.(task.task_id, e)}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono transition-colors cursor-pointer"
                style={{
                  background: 'var(--color-bg-tertiary)',
                  color: 'var(--color-text-secondary)',
                }}
                title="Click to copy task ID"
              >
                <span>{task.task_id}</span>
                {copiedTaskId === task.task_id ? (
                  <Check size={10} className="text-emerald-400" />
                ) : (
                  <Copy size={10} />
                )}
              </span>

              <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                {new Date(task.created_at * 1000).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
              </span>
            </div>

            {/* Task Prompt */}
            <h4
              className="text-sm font-semibold truncate max-w-xl"
              style={{ color: 'var(--color-text)' }}
              title={task.prompt}
            >
              {task.prompt}
            </h4>

            {/* Progress Bar & Current Step */}
            <div className="flex items-center gap-3 mt-2 text-xs">
              <div
                className="w-28 sm:w-36 h-1.5 rounded-full overflow-hidden"
                style={{ background: 'var(--color-bg-tertiary)' }}
              >
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${progressPct}%`,
                    background:
                      task.status === 'failed'
                        ? '#ef4444'
                        : task.status === 'waiting_approval'
                        ? '#f59e0b'
                        : 'var(--color-accent)',
                  }}
                />
              </div>

              <span className="text-[11px] font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                {completedSteps}/{totalSteps} steps ({progressPct}%)
              </span>

              {currentStep && (
                <span
                  className="hidden md:inline-flex items-center gap-1 text-[11px] font-mono truncate max-w-xs"
                  style={{ color: 'var(--color-text-tertiary)' }}
                >
                  <span>Current:</span>
                  <span style={{ color: 'var(--color-accent)' }}>{currentStep.tool_name}</span>
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Task Controls Row */}
        <div
          className="flex items-center gap-2 mt-2 sm:mt-0 justify-end shrink-0"
          onClick={(e) => e.stopPropagation()}
        >
          {task.status === 'running' && (
            <button
              type="button"
              onClick={(e) => onPause?.(task.task_id, e)}
              disabled={actionLoading[task.task_id]}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium cursor-pointer transition-colors"
              style={{
                background: 'rgba(234, 179, 8, 0.1)',
                color: '#eab308',
                border: '1px solid rgba(234, 179, 8, 0.3)',
              }}
              title="Pause execution after current step"
            >
              <Pause size={12} />
              <span>Pause</span>
            </button>
          )}

          {task.status === 'paused' && (
            <button
              type="button"
              onClick={(e) => onResume?.(task.task_id, e)}
              disabled={actionLoading[task.task_id]}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium cursor-pointer transition-colors"
              style={{
                background: 'rgba(56, 189, 248, 0.1)',
                color: '#38bdf8',
                border: '1px solid rgba(56, 189, 248, 0.3)',
              }}
              title="Resume execution"
            >
              <Play size={12} />
              <span>Resume</span>
            </button>
          )}

          {task.status === 'waiting_approval' && (
            <button
              type="button"
              onClick={() => onToggleExpand?.(task.task_id)}
              className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs font-semibold cursor-pointer animate-pulse shadow-sm"
              style={
                task.steps?.some((s) => s.requires_user_input || s.safety_decision?.requires_user_input)
                  ? {
                      background: 'rgba(6, 182, 212, 0.2)',
                      color: '#06b6d4',
                      border: '1px solid rgba(6, 182, 212, 0.5)',
                    }
                  : {
                      background: 'rgba(245, 158, 11, 0.2)',
                      color: '#f59e0b',
                      border: '1px solid rgba(245, 158, 11, 0.5)',
                    }
              }
            >
              {task.steps?.some((s) => s.requires_user_input || s.safety_decision?.requires_user_input) ? (
                <>
                  <Sliders size={12} />
                  <span>Input Needed</span>
                </>
              ) : (
                <>
                  <AlertTriangle size={12} />
                  <span>Action Needed</span>
                </>
              )}
            </button>
          )}

          {(task.status === 'running' ||
            task.status === 'queued' ||
            task.status === 'paused' ||
            task.status === 'waiting_approval') && (
            <button
              type="button"
              onClick={(e) => onCancel?.(task.task_id, e)}
              disabled={actionLoading[task.task_id]}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium cursor-pointer transition-colors"
              style={{
                background: 'rgba(239, 68, 68, 0.08)',
                color: '#ef4444',
                border: '1px solid rgba(239, 68, 68, 0.25)',
              }}
              title="Cancel task"
            >
              <XCircle size={12} />
              <span>Cancel</span>
            </button>
          )}
        </div>
      </div>

      {/* Expanded Task Details Accordion */}
      {isExpanded && (
        <div
          data-testid="expanded-task-details"
          className="p-4 border-t space-y-4"
          style={{
            background: 'rgba(0, 0, 0, 0.15)',
            borderColor: 'var(--color-border)',
          }}
        >
          {/* Task Error Message */}
          {task.error && (
            <div
              data-testid="task-error-banner"
              className="p-3 rounded-lg border text-xs flex items-start gap-2"
              style={{
                background: 'rgba(239, 68, 68, 0.08)',
                borderColor: 'rgba(239, 68, 68, 0.3)',
                color: '#ef4444',
              }}
            >
              <AlertTriangle size={15} className="shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block mb-0.5">Task Error:</span>
                <span className="font-mono">{task.error}</span>
              </div>
            </div>
          )}

          {/* Step DAG Pipeline Timeline */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                <Layers size={13} />
                <span>Step Execution Pipeline</span>
              </span>
              <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                {task.steps?.length || 0} Total Steps
              </span>
            </div>

            <div className="space-y-3">
              {task.steps?.map((step, idx) => {
                const stepKey = step.step_id;
                const isWaiting = step.status === 'waiting_approval';
                const isInputRequired = Boolean(step.requires_user_input || step.safety_decision?.requires_user_input);

                const userInputProps: StepUserInputPanelProps | undefined =
                  isWaiting && isInputRequired
                    ? {
                        step,
                        inputValues: stepInputs[stepKey] || {},
                        onInputChange: (fieldName, val) => onStepInputChange?.(stepKey, fieldName, val),
                        onSubmitInput: () => onSubmitStepInput?.(task, step),
                        onReject: () => onRejectStep?.(task, step),
                        isLoading: actionLoading[stepKey],
                        validationError: inputValidationErrors[stepKey],
                      }
                    : undefined;

                const approvalProps: OperatorApprovalPanelProps | undefined =
                  isWaiting && !isInputRequired
                    ? {
                        step,
                        resolution: approvalResolutions[stepKey],
                        confirmDuplicate: approvalConfirmDuplicate[stepKey],
                        safetyCode: approvalSafetyCodes[stepKey],
                        rejectReason: rejectReasons[stepKey],
                        isLoading: actionLoading[stepKey],
                        onResolutionChange: (res) => onResolutionChange?.(stepKey, res),
                        onConfirmDuplicateChange: (chk) => onConfirmDuplicateChange?.(stepKey, chk),
                        onSafetyCodeChange: (code) => onSafetyCodeChange?.(stepKey, code),
                        onRejectReasonChange: (reason) => onRejectReasonChange?.(stepKey, reason),
                        onApprove: () => onApproveStep?.(task, step),
                        onReject: () => onRejectStep?.(task, step),
                      }
                    : undefined;

                return (
                  <StepCard
                    key={step.step_id}
                    step={step}
                    idx={idx}
                    approvalProps={approvalProps}
                    userInputProps={userInputProps}
                  />
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component: TasksPage
// ---------------------------------------------------------------------------
export function TasksPage() {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeFilter, setActiveFilter] = useState<string>('all');
  const [expandedTasks, setExpandedTasks] = useState<Record<string, boolean>>({});
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [copiedTaskId, setCopiedTaskId] = useState<string | null>(null);

  // New task drawer / form state
  const [showNewTaskForm, setShowNewTaskForm] = useState<boolean>(false);
  const [newTaskPrompt, setNewTaskPrompt] = useState<string>('');
  const [creatingTask, setCreatingTask] = useState<boolean>(false);

  // Step approval form state per step: stepId -> { resolution, confirmDuplicate, safetyCode, reason }
  const [approvalResolutions, setApprovalResolutions] = useState<Record<string, string>>({});
  const [approvalConfirmDuplicate, setApprovalConfirmDuplicate] = useState<Record<string, boolean>>({});
  const [approvalSafetyCodes, setApprovalSafetyCodes] = useState<Record<string, string>>({});
  const [rejectReasons, setRejectReasons] = useState<Record<string, string>>({});

  // Step missing-input form state per step: stepId -> { fieldName: value }
  const [stepInputs, setStepInputs] = useState<Record<string, Record<string, any>>>({});
  const [inputValidationErrors, setInputValidationErrors] = useState<Record<string, string>>({});

  // Polling ref to prevent concurrent fetches
  const isFetchingRef = useRef<boolean>(false);

  const loadTasks = useCallback(async (isManualRefresh: boolean = false) => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    if (isManualRefresh) setRefreshing(true);

    try {
      const data = await fetchTasks();
      setTasks(data);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Failed to communicate with Task Runner backend.');
    } finally {
      setLoading(false);
      setRefreshing(false);
      isFetchingRef.current = false;
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  // Periodic polling: faster when active or waiting tasks exist
  useEffect(() => {
    const hasActiveTasks = tasks.some(
      (t) => t.status === 'running' || t.status === 'queued' || t.status === 'waiting_approval',
    );
    const intervalMs = hasActiveTasks ? 3500 : 15000;

    const intervalId = setInterval(() => {
      loadTasks();
    }, intervalMs);

    return () => clearInterval(intervalId);
  }, [tasks, loadTasks]);

  // Filter tasks
  const filteredTasks = tasks.filter((t) => {
    if (activeFilter === 'all') return true;
    if (activeFilter === 'active') return t.status === 'running' || t.status === 'queued';
    return t.status === activeFilter;
  });

  const toggleTaskExpanded = (taskId: string) => {
    setExpandedTasks((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  };

  const handleCopyTaskId = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(taskId);
      setCopiedTaskId(taskId);
      setTimeout(() => setCopiedTaskId(null), 2000);
      toast.success('Task ID copied to clipboard');
    } catch {
      toast.error('Failed to copy Task ID');
    }
  };

  // ---------------------------------------------------------------------------
  // Task Controls: Pause, Resume, Cancel
  // ---------------------------------------------------------------------------

  const handlePause = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (actionLoading[taskId]) return;
    setActionLoading((prev) => ({ ...prev, [taskId]: true }));

    try {
      await pauseTask(taskId);
      toast.success(`Task ${taskId} paused`);
      await loadTasks();
    } catch (err: any) {
      toast.error(err?.message || `Failed to pause task ${taskId}`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  const handleResume = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (actionLoading[taskId]) return;
    setActionLoading((prev) => ({ ...prev, [taskId]: true }));

    try {
      await resumeTask(taskId);
      toast.success(`Task ${taskId} resumed`);
      await loadTasks();
    } catch (err: any) {
      toast.error(err?.message || `Failed to resume task ${taskId}`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  const handleCancel = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (actionLoading[taskId]) return;
    if (!window.confirm(`Are you sure you want to cancel task '${taskId}'?`)) return;

    setActionLoading((prev) => ({ ...prev, [taskId]: true }));
    try {
      await cancelTask(taskId);
      toast.success(`Task ${taskId} cancelled`);
      await loadTasks();
    } catch (err: any) {
      toast.error(err?.message || `Failed to cancel task ${taskId}`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [taskId]: false }));
    }
  };

  // ---------------------------------------------------------------------------
  // Step Controls: Approve & Reject
  // ---------------------------------------------------------------------------

  const handleApproveStep = async (task: TaskRecord, step: TaskStep) => {
    const stepKey = step.step_id;
    if (actionLoading[stepKey]) return;

    const isUncertain = !!step.safety_decision?.uncertain_external_action;
    const selectedResolution = approvalResolutions[stepKey] || (isUncertain ? 'mark_completed' : undefined);
    const confirmedDuplicate = !!approvalConfirmDuplicate[stepKey];
    const safetyCode = approvalSafetyCodes[stepKey] || undefined;

    if (isUncertain && selectedResolution === 'force_retry' && !confirmedDuplicate) {
      toast.error('Explicit confirmation of duplicate action risk is required before force retrying.');
      return;
    }

    if (step.requires_code && !safetyCode) {
      toast.error('Safety code is required by policy to authorize this high-risk step.');
      return;
    }

    setActionLoading((prev) => ({ ...prev, [stepKey]: true }));

    try {
      await approveTaskStep(task.task_id, {
        step_id: step.step_id,
        safety_code: safetyCode,
        resolution: selectedResolution,
        confirm_duplicate_risk: confirmedDuplicate,
      });

      toast.success(`Step '${step.title}' approved successfully.`);
      // Clear step state
      setApprovalResolutions((prev) => {
        const copy = { ...prev };
        delete copy[stepKey];
        return copy;
      });
      setApprovalConfirmDuplicate((prev) => {
        const copy = { ...prev };
        delete copy[stepKey];
        return copy;
      });
      setApprovalSafetyCodes((prev) => {
        const copy = { ...prev };
        delete copy[stepKey];
        return copy;
      });
      await loadTasks();
    } catch (err: any) {
      toast.error(err?.message || `Failed to approve step '${step.title}'`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [stepKey]: false }));
    }
  };

  const handleRejectStep = async (task: TaskRecord, step: TaskStep) => {
    const stepKey = step.step_id;
    if (actionLoading[stepKey]) return;

    const reason = rejectReasons[stepKey] || 'Rejected by operator in Task Center';
    setActionLoading((prev) => ({ ...prev, [stepKey]: true }));

    try {
      await rejectTaskStep(task.task_id, {
        step_id: step.step_id,
        reason,
      });

      toast.success(`Step '${step.title}' rejected.`);
      await loadTasks();
    } catch (err: any) {
      toast.error(err?.message || `Failed to reject step '${step.title}'`);
    } finally {
      setActionLoading((prev) => ({ ...prev, [stepKey]: false }));
    }
  };

  // ---------------------------------------------------------------------------
  // Step Controls: Missing Input Submission
  // ---------------------------------------------------------------------------

  const handleStepInputChange = (stepId: string, fieldName: string, value: any) => {
    setStepInputs((prev) => ({
      ...prev,
      [stepId]: {
        ...(prev[stepId] || {}),
        [fieldName]: value,
      },
    }));
    if (inputValidationErrors[stepId]) {
      setInputValidationErrors((prev) => {
        const copy = { ...prev };
        delete copy[stepId];
        return copy;
      });
    }
  };

  const handleSubmitStepInput = async (task: TaskRecord, step: TaskStep) => {
    const stepKey = step.step_id;
    if (actionLoading[stepKey]) return;

    const rawValues = stepInputs[stepKey] || {};
    const schema = step.safety_decision?.schema;
    const properties = (schema?.properties as Record<string, any>) || {};
    const missingFields: string[] = step.safety_decision?.missing_fields || schema?.required || [];

    // Client-side argument conversion & check
    const convertedArgs: Record<string, any> = { ...(step.tool_args || {}) };
    let clientError: string | null = null;

    const allFieldNames = Array.from(
      new Set([...missingFields, ...Object.keys(properties), ...Object.keys(rawValues)]),
    );

    for (const fieldName of allFieldNames) {
      const val = rawValues[fieldName];
      const prop = properties[fieldName] || {};
      const expectedType = prop.type;

      if (val === undefined || val === '') {
        if (missingFields.includes(fieldName) && (convertedArgs[fieldName] === undefined || convertedArgs[fieldName] === '')) {
          clientError = `Required parameter '${fieldName}' must not be empty.`;
          break;
        }
        continue;
      }

      if (expectedType === 'integer') {
        const num = parseInt(val, 10);
        if (isNaN(num)) {
          clientError = `Parameter '${fieldName}' must be a valid integer.`;
          break;
        }
        convertedArgs[fieldName] = num;
      } else if (expectedType === 'number') {
        const num = parseFloat(val);
        if (isNaN(num)) {
          clientError = `Parameter '${fieldName}' must be a valid number.`;
          break;
        }
        convertedArgs[fieldName] = num;
      } else if (expectedType === 'boolean') {
        convertedArgs[fieldName] = Boolean(val);
      } else if (expectedType === 'object' || expectedType === 'array') {
        if (typeof val === 'string') {
          try {
            convertedArgs[fieldName] = JSON.parse(val);
          } catch (e: any) {
            clientError = `Parameter '${fieldName}' must be valid JSON: ${e.message}`;
            break;
          }
        } else {
          convertedArgs[fieldName] = val;
        }
      } else {
        convertedArgs[fieldName] = String(val);
      }
    }

    if (clientError) {
      setInputValidationErrors((prev) => ({ ...prev, [stepKey]: clientError! }));
      toast.error(clientError);
      return;
    }

    setInputValidationErrors((prev) => {
      const copy = { ...prev };
      delete copy[stepKey];
      return copy;
    });

    setActionLoading((prev) => ({ ...prev, [stepKey]: true }));

    try {
      const res = await submitStepInput(task.task_id, {
        step_id: step.step_id,
        tool_args: convertedArgs,
      });

      if (res.requires_approval) {
        toast.info(
          `Arguments recorded for '${step.title}'. This action requires operator authorization before execution.`,
        );
      } else {
        toast.success(`Arguments submitted for '${step.title}'. Execution resumed.`);
      }

      // Clear step input state
      setStepInputs((prev) => {
        const copy = { ...prev };
        delete copy[stepKey];
        return copy;
      });

      await loadTasks();
    } catch (err: any) {
      const msg = err?.message || `Failed to submit inputs for step '${step.title}'`;
      setInputValidationErrors((prev) => ({ ...prev, [stepKey]: msg }));
      toast.error(msg);
    } finally {
      setActionLoading((prev) => ({ ...prev, [stepKey]: false }));
    }
  };


  // ---------------------------------------------------------------------------
  // Create New Task
  // ---------------------------------------------------------------------------

  const handleCreateNewTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskPrompt.trim() || creatingTask) return;

    setCreatingTask(true);
    try {
      const created = await createTask(newTaskPrompt.trim());
      toast.success(`Task planned and launched: ${created.task_id}`);
      setNewTaskPrompt('');
      setShowNewTaskForm(false);
      setExpandedTasks((prev) => ({ ...prev, [created.task_id]: true }));
      await loadTasks();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to create task');
    } finally {
      setCreatingTask(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden px-6 py-8">
      <div className="max-w-6xl mx-auto w-full flex flex-col flex-1 overflow-hidden">
        {/* Header Ribbon */}
        <header className="mb-6 shrink-0">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2.5">
                <div
                  className="p-2 rounded-xl"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border)' }}
                >
                  <ListTodo size={22} style={{ color: 'var(--color-accent)' }} />
                </div>
                <div>
                  <h1 className="text-xl font-bold tracking-tight" style={{ color: 'var(--color-text)' }}>
                    Task Center
                  </h1>
                  <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                    Persistent DAG execution, bounded retries, and Safety Kernel authorization
                  </p>
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2.5">
              <button
                type="button"
                onClick={() => loadTasks(true)}
                disabled={refreshing}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
                style={{
                  background: 'var(--color-bg-secondary)',
                  color: 'var(--color-text-secondary)',
                  border: '1px solid var(--color-border)',
                }}
                title="Refresh task list"
              >
                <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
                <span>Refresh</span>
              </button>

              <button
                type="button"
                onClick={() => setShowNewTaskForm((v) => !v)}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer shadow-sm"
                style={{
                  background: 'var(--color-accent)',
                  color: '#ffffff',
                }}
              >
                <Plus size={14} />
                <span>New Task</span>
              </button>
            </div>
          </div>

          {/* Quick Metrics Cards */}
          <div className="mt-5">
            <MetricsSummary tasks={tasks} />
          </div>

          {/* Create Task Drawer / Collapsible Box */}
          {showNewTaskForm && (
            <form
              onSubmit={handleCreateNewTask}
              className="mb-5 p-4 rounded-xl border shadow-sm transition-all animate-in fade-in"
              style={{
                background: 'var(--color-bg-secondary)',
                borderColor: 'var(--color-accent)',
              }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
                  Plan and Execute Persistent Task
                </span>
                <span className="text-[11px]" style={{ color: 'var(--color-text-tertiary)' }}>
                  Ultron will decompose this into an executable DAG
                </span>
              </div>
              <textarea
                value={newTaskPrompt}
                onChange={(e) => setNewTaskPrompt(e.target.value)}
                placeholder="e.g. Clean up build caches, update repository packages, and launch development server..."
                rows={3}
                className="w-full p-2.5 rounded-lg text-xs focus:outline-none resize-none"
                style={{
                  background: 'var(--color-bg-tertiary)',
                  color: 'var(--color-text)',
                  border: '1px solid var(--color-border)',
                }}
              />
              <div className="flex justify-end gap-2 mt-3">
                <button
                  type="button"
                  onClick={() => setShowNewTaskForm(false)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newTaskPrompt.trim() || creatingTask}
                  className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium cursor-pointer shadow-sm disabled:opacity-50"
                  style={{ background: 'var(--color-accent)', color: '#ffffff' }}
                >
                  {creatingTask ? (
                    <>
                      <RefreshCw size={12} className="animate-spin" />
                      <span>Planning...</span>
                    </>
                  ) : (
                    <>
                      <Play size={12} />
                      <span>Start Task</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          {/* Filter Tabs */}
          <div className="flex items-center gap-1.5 mt-5 overflow-x-auto pb-1 scrollbar-none">
            {[
              { id: 'all', label: 'All Tasks', count: tasks.length },
              { id: 'active', label: 'Active', count: tasks.filter((t) => t.status === 'running' || t.status === 'queued').length },
              { id: 'waiting_approval', label: 'Needs Approval', count: tasks.filter((t) => t.status === 'waiting_approval').length },
              { id: 'completed', label: 'Completed', count: tasks.filter((t) => t.status === 'completed').length },
              { id: 'failed', label: 'Failed', count: tasks.filter((t) => t.status === 'failed').length },
              { id: 'paused', label: 'Paused', count: tasks.filter((t) => t.status === 'paused').length },
            ].map((tab) => {
              const active = activeFilter === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveFilter(tab.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer shrink-0"
                  style={{
                    background: active ? 'var(--color-bg-tertiary)' : 'transparent',
                    color: active ? 'var(--color-text)' : 'var(--color-text-secondary)',
                    border: active ? '1px solid var(--color-border)' : '1px solid transparent',
                  }}
                >
                  <span>{tab.label}</span>
                  <span
                    className="px-1.5 py-0.2 rounded-full text-[10px]"
                    style={{
                      background: active ? 'var(--color-accent-subtle)' : 'var(--color-bg-secondary)',
                      color: active ? 'var(--color-accent)' : 'var(--color-text-tertiary)',
                    }}
                  >
                    {tab.count}
                  </span>
                </button>
              );
            })}
          </div>
        </header>

        {/* Error State */}
        {error && (
          <div
            data-testid="tasks-error-banner"
            className="mb-4 p-3.5 rounded-xl border flex items-center justify-between text-xs"
            style={{
              background: 'rgba(239, 68, 68, 0.08)',
              borderColor: 'rgba(239, 68, 68, 0.3)',
              color: '#ef4444',
            }}
          >
            <div className="flex items-center gap-2">
              <AlertTriangle size={16} />
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={() => loadTasks(true)}
              className="underline font-semibold cursor-pointer ml-3"
            >
              Retry
            </button>
          </div>
        )}

        {/* Task List / Accordion */}
        <div className="flex-1 overflow-y-auto space-y-3.5 pr-1 pb-10">
          {loading && tasks.length === 0 ? (
            <div data-testid="tasks-loading" className="flex flex-col items-center justify-center py-20 text-center">
              <RefreshCw size={28} className="animate-spin mb-3" style={{ color: 'var(--color-accent)' }} />
              <p className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                Loading persistent tasks...
              </p>
            </div>
          ) : filteredTasks.length === 0 ? (
            <div
              data-testid="tasks-empty-state"
              className="flex flex-col items-center justify-center py-20 text-center rounded-2xl border border-dashed p-8"
              style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-secondary)' }}
            >
              <div
                className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3"
                style={{ background: 'var(--color-bg-tertiary)' }}
              >
                <ListTodo size={24} style={{ color: 'var(--color-text-tertiary)' }} />
              </div>
              <h3 className="text-sm font-semibold mb-1" style={{ color: 'var(--color-text)' }}>
                No tasks found
              </h3>
              <p className="text-xs max-w-sm mb-4" style={{ color: 'var(--color-text-secondary)' }}>
                {activeFilter === 'all'
                  ? 'There are no persistent tasks recorded in SQLite storage yet.'
                  : `There are currently no tasks in '${activeFilter}' state.`}
              </p>
              <button
                type="button"
                onClick={() => setShowNewTaskForm(true)}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium cursor-pointer"
                style={{ background: 'var(--color-accent)', color: '#ffffff' }}
              >
                <Plus size={13} />
                <span>Plan First Task</span>
              </button>
            </div>
          ) : (
            filteredTasks.map((task) => (
              <TaskCard
                key={task.task_id}
                task={task}
                isExpanded={!!expandedTasks[task.task_id]}
                copiedTaskId={copiedTaskId}
                actionLoading={actionLoading}
                approvalResolutions={approvalResolutions}
                approvalConfirmDuplicate={approvalConfirmDuplicate}
                approvalSafetyCodes={approvalSafetyCodes}
                rejectReasons={rejectReasons}
                onToggleExpand={toggleTaskExpanded}
                onCopyTaskId={handleCopyTaskId}
                onPause={handlePause}
                onResume={handleResume}
                onCancel={handleCancel}
                onApproveStep={handleApproveStep}
                onRejectStep={handleRejectStep}
                onResolutionChange={(sId, res) =>
                  setApprovalResolutions((prev) => ({ ...prev, [sId]: res }))
                }
                onConfirmDuplicateChange={(sId, chk) =>
                  setApprovalConfirmDuplicate((prev) => ({ ...prev, [sId]: chk }))
                }
                onSafetyCodeChange={(sId, code) =>
                  setApprovalSafetyCodes((prev) => ({ ...prev, [sId]: code }))
                }
                onRejectReasonChange={(sId, r) =>
                  setRejectReasons((prev) => ({ ...prev, [sId]: r }))
                }
                stepInputs={stepInputs}
                inputValidationErrors={inputValidationErrors}
                onStepInputChange={handleStepInputChange}
                onSubmitStepInput={handleSubmitStepInput}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default TasksPage;
