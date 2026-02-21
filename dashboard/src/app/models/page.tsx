import { ALL_MODELS, TIER_COLORS, PROVIDER_LABELS } from "@/lib/models";
import type { ModelSpec, ModelTier } from "@/lib/types";

function ModelCard({ model }: { model: ModelSpec }) {
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
        <div>
          <p className="text-neutral-500 text-xs">Params</p>
          <p className="font-mono">{model.totalParamsB > 0 ? `${model.totalParamsB}B` : "—"}{model.isMoe ? " (MoE)" : ""}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {model.capabilities.map((cap) => (
          <span key={cap} className="text-xs px-2 py-0.5 rounded bg-neutral-800 text-neutral-400">{cap}</span>
        ))}
      </div>
    </div>
  );
}

export default function ModelsPage() {
  const tiers: ModelTier[] = ["free", "standard", "premium"];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Model Registry</h1>
      <p className="text-neutral-500 text-sm mb-8">{ALL_MODELS.length} Chinese LLMs across 4 providers. Pricing via OpenRouter (Feb 2026).</p>

      {tiers.map((tier) => {
        const models = ALL_MODELS.filter((m) => m.tier === tier);
        const emoji = tier === "free" ? "🟢" : tier === "standard" ? "🔵" : "🟡";
        return (
          <div key={tier} className="mb-8">
            <h2 className="text-lg font-semibold mb-4 capitalize">{emoji} {tier} Tier ({models.length} models)</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {models.map((model) => (
                <ModelCard key={model.modelId} model={model} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
