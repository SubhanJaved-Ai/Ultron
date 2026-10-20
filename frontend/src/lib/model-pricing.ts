/**
 * Real-time Model Pricing and Cost Calculation Utility.
 * Provides accurate per-model rates and cost calculations for local and cloud models.
 */

export interface ModelPricingTier {
  idPrefix: string;
  displayName: string;
  inputPerMillion: number;  // $ USD per 1M prompt tokens
  outputPerMillion: number; // $ USD per 1M completion tokens
  isLocal?: boolean;
}

export const KNOWN_MODEL_PRICING: ModelPricingTier[] = [
  // Local models (zero API cost)
  { idPrefix: 'ollama', displayName: 'Ollama (Local)', inputPerMillion: 0, outputPerMillion: 0, isLocal: true },
  { idPrefix: 'local', displayName: 'Local Inference', inputPerMillion: 0, outputPerMillion: 0, isLocal: true },
  // OpenRouter Free
  { idPrefix: ':free', displayName: 'OpenRouter Free Tier', inputPerMillion: 0, outputPerMillion: 0 },
  // Google Gemini models
  { idPrefix: 'gemini-1.5-flash', displayName: 'Gemini 1.5 Flash', inputPerMillion: 0.075, outputPerMillion: 0.30 },
  { idPrefix: 'gemini-2.0-flash', displayName: 'Gemini 2.0 Flash', inputPerMillion: 0.10, outputPerMillion: 0.40 },
  { idPrefix: 'gemini-2.5-flash', displayName: 'Gemini 2.5 Flash', inputPerMillion: 0.10, outputPerMillion: 0.40 },
  { idPrefix: 'gemini-3.5-flash', displayName: 'Gemini 3.5 Flash', inputPerMillion: 0.15, outputPerMillion: 0.60 },
  { idPrefix: 'gemini-3.7-flash', displayName: 'Gemini 3.7 Flash', inputPerMillion: 0.15, outputPerMillion: 0.60 },
  { idPrefix: 'gemini-3.8-flash', displayName: 'Gemini 3.8 Flash', inputPerMillion: 0.15, outputPerMillion: 0.60 },
  { idPrefix: 'gemini-flash', displayName: 'Gemini Flash', inputPerMillion: 0.10, outputPerMillion: 0.40 },
  { idPrefix: 'gemini-1.5-pro', displayName: 'Gemini 1.5 Pro', inputPerMillion: 1.25, outputPerMillion: 5.00 },
  { idPrefix: 'gemini-2.5-pro', displayName: 'Gemini 2.5 Pro', inputPerMillion: 1.25, outputPerMillion: 5.00 },
  { idPrefix: 'gemini-pro', displayName: 'Gemini Pro', inputPerMillion: 1.25, outputPerMillion: 5.00 },
  { idPrefix: 'models/gemini', displayName: 'Google Gemini', inputPerMillion: 0.15, outputPerMillion: 0.60 },
  // OpenAI models
  { idPrefix: 'gpt-4o-mini', displayName: 'GPT-4o Mini', inputPerMillion: 0.15, outputPerMillion: 0.60 },
  { idPrefix: 'gpt-4o', displayName: 'GPT-4o', inputPerMillion: 2.50, outputPerMillion: 10.00 },
  { idPrefix: 'gpt-4-turbo', displayName: 'GPT-4 Turbo', inputPerMillion: 10.00, outputPerMillion: 30.00 },
  { idPrefix: 'o1', displayName: 'OpenAI o1', inputPerMillion: 15.00, outputPerMillion: 60.00 },
  { idPrefix: 'o3', displayName: 'OpenAI o3-mini', inputPerMillion: 1.10, outputPerMillion: 4.40 },
  // Anthropic Claude models
  { idPrefix: 'claude-3-5-haiku', displayName: 'Claude 3.5 Haiku', inputPerMillion: 0.80, outputPerMillion: 4.00 },
  { idPrefix: 'claude-3-5-sonnet', displayName: 'Claude 3.5 Sonnet', inputPerMillion: 3.00, outputPerMillion: 15.00 },
  { idPrefix: 'claude-3-opus', displayName: 'Claude 3 Opus', inputPerMillion: 15.00, outputPerMillion: 75.00 },
  // OpenRouter general
  { idPrefix: 'openrouter/', displayName: 'OpenRouter', inputPerMillion: 0.20, outputPerMillion: 0.80 },
];

/**
 * Resolve pricing for a model name. Defaults to standard lightweight rates.
 */
export function getModelPricing(modelName?: string | unknown): ModelPricingTier {
  if (!modelName || typeof modelName !== 'string') {
    return { idPrefix: 'default', displayName: 'Standard Model', inputPerMillion: 0.15, outputPerMillion: 0.60 };
  }
  const lower = modelName.toLowerCase();
  for (const tier of KNOWN_MODEL_PRICING) {
    if (lower.includes(tier.idPrefix)) {
      return {
        ...tier,
        displayName: formatModelName(modelName),
      };
    }
  }
  // If it's a typical local model name without prefix (e.g. qwen, llama, mistral, deepseek)
  const isLikelyLocal = ['llama', 'qwen', 'mistral', 'phi', 'gemma', 'deepseek', 'codellama'].some(
    (prefix) => lower.startsWith(prefix) && !lower.includes('claude') && !lower.includes('gpt')
  );
  if (isLikelyLocal) {
    return {
      idPrefix: 'local',
      displayName: formatModelName(modelName),
      inputPerMillion: 0,
      outputPerMillion: 0,
      isLocal: true,
    };
  }

  return {
    idPrefix: 'cloud-standard',
    displayName: formatModelName(modelName),
    inputPerMillion: 0.20,
    outputPerMillion: 0.80,
  };
}

/**
 * Formats model ID into clean human-readable title.
 */
export function formatModelName(modelId?: string | unknown): string {
  if (!modelId || typeof modelId !== 'string') return 'Default Model';
  // Strip common prefixes
  let clean = modelId.replace(/^models\//, '').replace(/^openrouter\//, '');
  // Capitalize nicely
  return clean
    .split(/[-_/]/)
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : ''))
    .join(' ');
}

/**
 * Calculates exact cost in USD for given prompt and completion tokens.
 */
export function calculateModelCost(
  modelName: string | undefined,
  promptTokens: number,
  completionTokens: number,
  localElectricityCost: number = 0
): { cost: number; pricing: ModelPricingTier } {
  const pricing = getModelPricing(modelName);
  if (pricing.isLocal) {
    return { cost: localElectricityCost, pricing };
  }
  const promptCost = (promptTokens / 1_000_000) * pricing.inputPerMillion;
  const completionCost = (completionTokens / 1_000_000) * pricing.outputPerMillion;
  return {
    cost: promptCost + completionCost,
    pricing,
  };
}
