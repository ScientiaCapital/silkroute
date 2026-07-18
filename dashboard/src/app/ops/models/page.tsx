import { fetchModels } from "@/lib/api";
import { ALL_MODELS, PROVIDER_LABELS } from "@/lib/models";
import type { ModelCatalogItem, ModelSpec, ModelTier } from "@/lib/types";

// Common display shape both the live GET /models catalog and the static
// ALL_MODELS fallback normalize into — the live API doesn't serve param
// counts or recommendedFor, so those stay optional.
interface DisplayModel {
  modelId: string;
  name: string;
  provider: string;
  tier: ModelTier;
  inputCostPerM: number;
  outputCostPerM: number;
  contextWindow: number;
  capabilities: string[];
  isFree: boolean;
  isMoe: boolean;
  totalParamsB?: number;
}

function fromSpec(m: ModelSpec): DisplayModel {
  return {
    modelId: m.modelId,
    name: m.name,
    provider: m.provider,
    tier: m.tier,
    inputCostPerM: m.inputCostPerM,
    outputCostPerM: m.outputCostPerM,
    contextWindow: m.contextWindow,
    capabilities: m.capabilities,
    isFree: m.isFree,
    isMoe: m.isMoe,
    totalParamsB: m.totalParamsB,
  };
}

function fromCatalogItem(m: ModelCatalogItem): DisplayModel {
  return {
    modelId: m.model_id,
    name: m.name,
    provider: m.provider,
    tier: m.tier,
    inputCostPerM: m.input_cost_per_m,
    outputCostPerM: m.output_cost_per_m,
    contextWindow: m.context_window,
    capabilities: m.capabilities,
    isFree: m.is_free,
    isMoe: m.is_moe,
  };
}

async function getModels(): Promise<DisplayModel[]> {
  try {
    const live = await fetchModels();
    // The registry always has 21 entries in practice — an empty response from
    // a reachable API means something's actually wrong, not "zero models
    // configured," so it gets the same static fallback as an unreachable API.
    if (live.length === 0) return ALL_MODELS.map(fromSpec);
    return live.map(fromCatalogItem);
  } catch {
    return ALL_MODELS.map(fromSpec);
  }
}

function ModelCard({ model }: { model: DisplayModel }) {
  const tierEmoji = model.tier === "free" ? "🟢" : model.tier === "standard" ? "🔵" : "🟡";
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5 hover:border-neutral-700 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold">{model.name}</h3>
          <p className="text-xs text-neutral-500">{PROVIDER_LABELS[model.provider] || model.provider}</p>
        </div>
        <span className="text-xs px-2 py-1 rounded-full bg-neutral-800">
          {tierEmoji} {model.tier}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm mb-3">
        <div>
          <p className="text-neutral-500 text-xs">Input</p>
          <p className="font-mono">{model.isFree ? "FREE" : `$${model.inputCostPerM.toFixed(2)}/M`}</p>
        </div>
        <div>
          <p className="text-neutral-500 text-xs">Output</p>
          <p className="font-mono">{model.isFree ? "FREE" : `$${model.outputCostPerM.toFixed(2)}/M`}</p>
        </div>
        <div>
          <p className="text-neutral-500 text-xs">Context</p>
          <p className="font-mono">{(model.contextWindow / 1024).toFixed(0)}K</p>
        </div>
        {model.totalParamsB !== undefined && (
          <div>
            <p className="text-neutral-500 text-xs">Params</p>
            <p className="font-mono">{model.totalParamsB > 0 ? `${model.totalParamsB}B` : "—"}{model.isMoe ? " (MoE)" : ""}</p>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-1">
        {model.capabilities.map((cap) => (
          <span key={cap} className="text-xs px-2 py-0.5 rounded bg-neutral-800 text-neutral-400">{cap}</span>
        ))}
      </div>
    </div>
  );
}

export default async function ModelsPage() {
  const models = await getModels();
  const tiers: ModelTier[] = ["free", "standard", "premium"];
  const providerCount = new Set(models.map((m) => m.provider)).size;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Model Registry</h1>
      <p className="text-neutral-500 text-sm mb-8">
        {models.length} models across {providerCount} providers — Chinese/local by default, western
        frontier via OpenRouter.
      </p>

      {tiers.map((tier) => {
        const tierModels = models.filter((m) => m.tier === tier);
        if (tierModels.length === 0) return null;
        const emoji = tier === "free" ? "🟢" : tier === "standard" ? "🔵" : "🟡";
        return (
          <div key={tier} className="mb-8">
            <h2 className="text-lg font-semibold mb-4 capitalize">{emoji} {tier} Tier ({tierModels.length} models)</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {tierModels.map((model) => (
                <ModelCard key={model.modelId} model={model} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
