import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { TaskRecord, TaskStep } from '../types';
import {
  TaskStatusBadge,
  MetricsSummary,
  TaskCard,
  StepCard,
  OperatorApprovalPanel,
  StepUserInputPanel,
} from './TasksPage';

// Sample mock steps
const mockStepRunning: TaskStep = {
  step_id: 'step_1',
  task_id: 'tsk_run_01',
  step_index: 0,
  title: 'Download release binary',
  tool_name: 'fetch_url',
  tool_args: { url: 'https://example.com/bin.tar.gz' },
  status: 'running',
  retry_count: 0,
  max_retries: 2,
  dependencies: [],
  started_at: 1729000000,
  finished_at: null,
};

const mockStepCompleted: TaskStep = {
  step_id: 'step_2',
  task_id: 'tsk_run_01',
  step_index: 1,
  title: 'Unpack distribution tarball',
  tool_name: 'cmd_exec',
  tool_args: { command: 'tar -xzf bin.tar.gz' },
  status: 'completed',
  retry_count: 0,
  max_retries: 2,
  dependencies: ['step_1'],
  actual_output: 'Successfully extracted 42 files to /tmp/release',
  artifacts: ['/tmp/release/bin', '/tmp/release/config.json'],
  started_at: 1729000020,
  finished_at: 1729000030,
};

const mockStepUncertain: TaskStep = {
  step_id: 'step_3',
  task_id: 'tsk_wait_02',
  step_index: 1,
  title: 'Trigger remote deployment webhook',
  tool_name: 'webhook',
  tool_args: { endpoint: 'https://api.internal/deploy', environment: 'production' },
  status: 'waiting_approval',
  retry_count: 1,
  max_retries: 2,
  dependencies: ['step_2'],
  started_at: 1729000040,
  finished_at: null,
  safety_decision: {
    uncertain_external_action: true,
    reason: 'Webhook timed out after 30 seconds; remote execution outcome is indeterminate.',
    duplicate_action_risk:
      'Retrying without confirmation may trigger multiple remote deployment runs and cause redundant resource allocations.',
    force_retry_warning:
      'WARNING: Force-retrying may repeat the remote deployment and cause duplicate side effects.',
  },
};

const mockStepHighRiskCode: TaskStep = {
  step_id: 'step_4',
  task_id: 'tsk_wait_02',
  step_index: 2,
  title: 'Delete legacy database backup',
  tool_name: 'delete_file',
  tool_args: { path: '/var/backups/legacy_db.bak' },
  status: 'waiting_approval',
  requires_code: true,
  retry_count: 0,
  max_retries: 1,
  dependencies: [],
  started_at: 1729000060,
  finished_at: null,
  safety_decision: {
    reason: 'High-risk destructive deletion requested; verified safety code required.',
  },
};

const mockStepFailed: TaskStep = {
  step_id: 'step_5',
  task_id: 'tsk_fail_03',
  step_index: 1,
  title: 'Launch production service',
  tool_name: 'app_launch',
  tool_args: { app_name: 'UltronDaemon' },
  status: 'failed',
  retry_count: 2,
  max_retries: 2,
  error: 'Port 8080 already in use by process PID 4120',
  dependencies: ['step_2'],
  started_at: 1729000080,
  finished_at: 1729000090,
};

const mockStepMissingInput: TaskStep = {
  step_id: 'step_missing_1',
  task_id: 'tsk_input_01',
  step_index: 0,
  title: 'Export financial ledger',
  tool_name: 'export_ledger',
  tool_args: {},
  status: 'waiting_approval',
  requires_user_input: true,
  retry_count: 0,
  max_retries: 2,
  dependencies: [],
  safety_decision: {
    requires_user_input: true,
    missing_fields: ['format', 'max_rows', 'include_tax', 'filter_options'],
    prompt: "Step 'Export financial ledger' requires essential parameter(s): 'format', 'max_rows', 'include_tax'. Please provide tool arguments.",
    schema: {
      type: 'object',
      properties: {
        format: {
          type: 'string',
          description: 'Export file format',
          enum: ['csv', 'json', 'parquet'],
        },
        max_rows: {
          type: 'integer',
          description: 'Maximum number of transactions to export',
          minimum: 1,
          maximum: 10000,
        },
        include_tax: {
          type: 'boolean',
          description: 'Whether to include tax breakdown calculations',
          default: false,
        },
        filter_options: {
          type: 'object',
          description: 'Structured JSON filters for departments and currencies',
        },
        memo: {
          type: 'string',
          description: 'Optional export memo tag',
        },
      },
      required: ['format', 'max_rows'],
    },
  },
};

// Sample mock tasks
const mockRunningTask: TaskRecord = {
  task_id: 'tsk_run_01',
  prompt: 'Automate weekly system upgrade and service validation',
  status: 'running',
  current_step_index: 1,
  steps: [mockStepCompleted, mockStepRunning],
  metadata: {},
  created_at: 1729000000,
  started_at: 1729000000,
};

const mockWaitingTask: TaskRecord = {
  task_id: 'tsk_wait_02',
  prompt: 'Deploy payment service to staging cluster',
  status: 'waiting_approval',
  current_step_index: 1,
  steps: [mockStepCompleted, mockStepUncertain],
  metadata: {},
  created_at: 1729000020,
  started_at: 1729000020,
};

const mockFailedTask: TaskRecord = {
  task_id: 'tsk_fail_03',
  prompt: 'Launch Ultron backend worker',
  status: 'failed',
  current_step_index: 1,
  error: 'Step 5 failed: Port 8080 already in use',
  steps: [mockStepCompleted, mockStepFailed],
  metadata: {},
  created_at: 1729000060,
  started_at: 1729000060,
  finished_at: 1729000090,
};

const mockPausedTask: TaskRecord = {
  task_id: 'tsk_pause_04',
  prompt: 'Nightly maintenance task',
  status: 'paused',
  current_step_index: 0,
  steps: [mockStepCompleted],
  metadata: {},
  created_at: 1729000010,
  started_at: 1729000010,
};

describe('Task Center UI Component Unit Tests', () => {
  describe('TaskStatusBadge', () => {
    it('renders accurate badge labels for all task statuses', () => {
      const runningHtml = renderToStaticMarkup(<TaskStatusBadge status="running" />);
      const waitingHtml = renderToStaticMarkup(<TaskStatusBadge status="waiting_approval" />);
      const completedHtml = renderToStaticMarkup(<TaskStatusBadge status="completed" />);
      const failedHtml = renderToStaticMarkup(<TaskStatusBadge status="failed" />);
      const pausedHtml = renderToStaticMarkup(<TaskStatusBadge status="paused" />);
      const cancelledHtml = renderToStaticMarkup(<TaskStatusBadge status="cancelled" />);
      const queuedHtml = renderToStaticMarkup(<TaskStatusBadge status="queued" />);

      expect(runningHtml).toContain('RUNNING');
      expect(waitingHtml).toContain('WAITING APPROVAL');
      expect(completedHtml).toContain('COMPLETED');
      expect(failedHtml).toContain('FAILED');
      expect(pausedHtml).toContain('PAUSED');
      expect(cancelledHtml).toContain('CANCELLED');
      expect(queuedHtml).toContain('QUEUED');
    });
  });

  describe('MetricsSummary', () => {
    it('computes and displays aggregate counts accurately', () => {
      const tasks: TaskRecord[] = [
        mockRunningTask,
        mockWaitingTask,
        mockFailedTask,
        mockPausedTask,
      ];
      const html = renderToStaticMarkup(<MetricsSummary tasks={tasks} />);

      expect(html).toContain('Total Tasks');
      expect(html).toContain('>4<'); // 4 total tasks
      expect(html).toContain('Active &amp; Queued');
      expect(html).toContain('>1<'); // 1 running task
      expect(html).toContain('Needs Approval');
      expect(html).toContain('Completed');
      expect(html).toContain('Failed');
    });
  });

  describe('TaskCard Rendering & Controls', () => {
    it('renders task prompt, ID, progress metrics, and appropriate action controls', () => {
      const html = renderToStaticMarkup(
        <TaskCard task={mockRunningTask} isExpanded={false} />,
      );

      expect(html).toContain('Automate weekly system upgrade and service validation');
      expect(html).toContain('tsk_run_01');
      expect(html).toContain('1/2 steps (50%)');
      expect(html).toContain('Pause');
      expect(html).toContain('Cancel');
      // Collapsed card does not show steps pipeline
      expect(html).not.toContain('Step Execution Pipeline');
    });

    it('renders resume button when task is paused', () => {
      const html = renderToStaticMarkup(
        <TaskCard task={mockPausedTask} isExpanded={false} />,
      );

      expect(html).toContain('Resume');
      expect(html).toContain('Cancel');
      expect(html).not.toContain('Pause');
    });

    it('renders expanded details with step pipeline and error banner when expanded', () => {
      const html = renderToStaticMarkup(
        <TaskCard task={mockFailedTask} isExpanded={true} />,
      );

      expect(html).toContain('Step Execution Pipeline');
      expect(html).toContain('Task Error:');
      expect(html).toContain('Step 5 failed: Port 8080 already in use');
      expect(html).toContain('Unpack distribution tarball');
      expect(html).toContain('Launch production service');
    });
  });

  describe('StepCard DAG Inspector', () => {
    it('displays step title, tool name, dependencies, outputs, and generated artifacts', () => {
      const html = renderToStaticMarkup(
        <StepCard step={mockStepCompleted} idx={1} />,
      );

      expect(html).toContain('Unpack distribution tarball');
      expect(html).toContain('cmd_exec');
      expect(html).toContain('Depends on: step_1');
      expect(html).toContain('Output:');
      expect(html).toContain('Successfully extracted 42 files to /tmp/release');
      expect(html).toContain('Artifacts:');
      expect(html).toContain('/tmp/release/bin');
      expect(html).toContain('/tmp/release/config.json');
    });

    it('displays failure error block when step has failed', () => {
      const html = renderToStaticMarkup(
        <StepCard step={mockStepFailed} idx={4} />,
      );

      expect(html).toContain('Error:');
      expect(html).toContain('Port 8080 already in use by process PID 4120');
      expect(html).toContain('Retries: 2/2');
    });
  });

  describe('Operator Approval & Resolution Panel', () => {
    it('renders duplicate-action risk warning and gates force_retry on explicit checkbox', () => {
      // 1. Unconfirmed force_retry state: Authorize button must be disabled
      const unconfirmedHtml = renderToStaticMarkup(
        <OperatorApprovalPanel
          step={mockStepUncertain}
          resolution="force_retry"
          confirmDuplicate={false}
          isLoading={false}
        />,
      );

      expect(unconfirmedHtml).toContain('Operator Authorization &amp; Resolution Required');
      expect(unconfirmedHtml).toContain('Duplicate-Action Risk Detected');
      expect(unconfirmedHtml).toContain('Retrying without confirmation may trigger multiple');
      expect(unconfirmedHtml).toContain('Force Re-execution');
      expect(unconfirmedHtml).toContain('I confirm that I understand this external action may be repeated');
      // The button should be disabled because confirmDuplicate is false
      expect(unconfirmedHtml).toMatch(/<button[^>]*data-testid="authorize-button"[^>]*disabled=""/);

      // 2. Confirmed force_retry state: Authorize button is active
      const confirmedHtml = renderToStaticMarkup(
        <OperatorApprovalPanel
          step={mockStepUncertain}
          resolution="force_retry"
          confirmDuplicate={true}
          isLoading={false}
        />,
      );

      // Must have enabled button with Confirm Force Retry label
      expect(confirmedHtml).toContain('Confirm Force Retry');
      expect(confirmedHtml).toMatch(/<button[^>]*data-testid="authorize-button"/);
      expect(confirmedHtml).not.toMatch(/<button[^>]*data-testid="authorize-button"[^>]*disabled=""/);
    });

    it('renders mark_completed mode with Mark Resolved label', () => {
      const html = renderToStaticMarkup(
        <OperatorApprovalPanel
          step={mockStepUncertain}
          resolution="mark_completed"
          confirmDuplicate={false}
          isLoading={false}
        />,
      );

      expect(html).toContain('Mark Resolved');
      // No force-retry warning box should be visible when mark_completed is selected
      expect(html).not.toContain('data-testid="force-retry-warning-box"');
    });

    it('gates authorization on safety code when requires_code is true', () => {
      // 1. Without code: button disabled
      const noCodeHtml = renderToStaticMarkup(
        <OperatorApprovalPanel
          step={mockStepHighRiskCode}
          safetyCode=""
          isLoading={false}
        />,
      );

      expect(noCodeHtml).toContain('Safety Code Required');
      expect(noCodeHtml).toContain('verified PBKDF2 safety code');
      expect(noCodeHtml).toMatch(/<button[^>]*data-testid="authorize-button"[^>]*disabled=""/);

      // 2. With code provided: button enabled
      const withCodeHtml = renderToStaticMarkup(
        <OperatorApprovalPanel
          step={mockStepHighRiskCode}
          safetyCode="my-secret-passcode"
          isLoading={false}
        />,
      );

      expect(withCodeHtml).toMatch(/<button[^>]*data-testid="authorize-button"/);
      expect(withCodeHtml).not.toMatch(/<button[^>]*data-testid="authorize-button"[^>]*disabled=""/);
    });

    it('disables controls and displays Authorizing... when action is in flight', () => {
      const loadingHtml = renderToStaticMarkup(
        <OperatorApprovalPanel
          step={mockStepHighRiskCode}
          safetyCode="valid-code"
          isLoading={true}
        />,
      );

      expect(loadingHtml).toContain('Authorizing...');
      expect(loadingHtml).toMatch(/<button[^>]*data-testid="authorize-button"[^>]*disabled=""/);
    });
  });

  describe('Step User Input Panel (Missing Information Workflow)', () => {
    it('renders exact missing fields and explanatory prompt', () => {
      const html = renderToStaticMarkup(
        <StepUserInputPanel
          step={mockStepMissingInput}
          inputValues={{}}
          isLoading={false}
        />,
      );

      expect(html).toContain('User Input Required: Tool Parameters Missing');
      expect(html).toContain('export_ledger');
      expect(html).toContain("Step &#x27;Export financial ledger&#x27; requires essential parameter(s)");
      expect(html).toContain('data-testid="missing-field-badge-format"');
      expect(html).toContain('data-testid="missing-field-badge-max_rows"');
      expect(html).toContain('data-testid="missing-field-badge-include_tax"');
      expect(html).toContain('data-testid="missing-field-badge-filter_options"');
    });

    it('renders type-appropriate form controls based on actual tool schema', () => {
      const html = renderToStaticMarkup(
        <StepUserInputPanel
          step={mockStepMissingInput}
          inputValues={{
            format: 'csv',
            max_rows: 500,
            include_tax: true,
            filter_options: '{"dept": "finance"}',
            memo: 'Q3 Audit',
          }}
          isLoading={false}
        />,
      );

      // Enum control should render select dropdown with options
      expect(html).toContain('data-testid="input-field-format"');
      expect(html).toContain('<select');
      expect(html).toContain('value="csv"');
      expect(html).toContain('value="parquet"');

      // Integer/number control should render number input with bounds
      expect(html).toContain('data-testid="input-field-max_rows"');
      expect(html).toContain('type="number"');
      expect(html).toContain('value="500"');
      expect(html).toContain('min="1"');
      expect(html).toContain('max="10000"');

      // Boolean control should render checkbox toggle
      expect(html).toContain('data-testid="input-field-include_tax"');
      expect(html).toContain('type="checkbox"');
      expect(html).toContain('checked=""');

      // Object control should render textarea for JSON
      expect(html).toContain('data-testid="input-field-filter_options"');
      expect(html).toContain('<textarea');
      expect(html).toContain('Must be valid JSON object');

      // String control should render text input
      expect(html).toContain('data-testid="input-field-memo"');
      expect(html).toContain('type="text"');
      expect(html).toContain('value="Q3 Audit"');
    });

    it('renders validation error banner when validation errors are present', () => {
      const html = renderToStaticMarkup(
        <StepUserInputPanel
          step={mockStepMissingInput}
          inputValues={{}}
          validationError="Parameter 'max_rows' must be an integer >= 1"
          isLoading={false}
        />,
      );

      expect(html).toContain('data-testid="input-validation-error"');
      expect(html).toContain('Validation Error:');
      expect(html).toContain("Parameter &#x27;max_rows&#x27; must be an integer &gt;= 1");
    });

    it('displays security notice that supplying parameters does not bypass permissions or authorize risky actions', () => {
      const html = renderToStaticMarkup(
        <StepUserInputPanel
          step={mockStepMissingInput}
          inputValues={{}}
          isLoading={false}
        />,
      );

      expect(html).toContain('Security Policy:');
      expect(html).toContain('Supplying missing parameters does not bypass permissions or authorize risky actions');
    });

    it('renders loading spinner and disables submit button when in flight', () => {
      const html = renderToStaticMarkup(
        <StepUserInputPanel
          step={mockStepMissingInput}
          inputValues={{ format: 'csv', max_rows: 100 }}
          isLoading={true}
        />,
      );

      expect(html).toContain('Validating...');
      expect(html).toMatch(/<button[^>]*data-testid="submit-input-button"[^>]*disabled=""/);
    });
  });

  describe('Separation between User Input and Security Authorization', () => {
    it('renders Waiting for Input badge and StepUserInputPanel when step requires user input', () => {
      const html = renderToStaticMarkup(
        <StepCard
          step={mockStepMissingInput}
          idx={0}
          userInputProps={{
            step: mockStepMissingInput,
            inputValues: {},
            isLoading: false,
          }}
          approvalProps={{
            step: mockStepMissingInput,
            isLoading: false,
          }}
        />,
      );

      // Must render Waiting for Input badge (cyan)
      expect(html).toContain('Waiting for Input');
      // Must render the User Input panel
      expect(html).toContain('data-testid="user-input-panel-step_missing_1"');
      expect(html).toContain('User Input Required: Tool Parameters Missing');
      // Must NOT render the Operator Security Authorization panel
      expect(html).not.toContain('Operator Authorization &amp; Resolution Required');
      expect(html).not.toContain('data-testid="approval-panel-step_missing_1"');
    });

    it('renders Waiting Approval badge and OperatorApprovalPanel when waiting for security approval', () => {
      const html = renderToStaticMarkup(
        <StepCard
          step={mockStepHighRiskCode}
          idx={1}
          approvalProps={{
            step: mockStepHighRiskCode,
            safetyCode: '',
            isLoading: false,
          }}
        />,
      );

      // Must render Waiting Approval badge (amber)
      expect(html).toContain('Waiting Approval');
      // Must render Operator Security Approval panel
      expect(html).toContain('Operator Authorization &amp; Resolution Required');
      expect(html).toContain('Safety Code Required');
      // Must NOT render User Input panel
      expect(html).not.toContain('User Input Required: Tool Parameters Missing');
      expect(html).not.toContain('data-testid="user-input-panel-step_4"');
    });
  });
});

