import { PIPELINE, DEMO_META } from "@/lib/demo";
import type { PipelineStage } from "@/lib/demo";
import LiveRoomView from "./LiveRoomView";

function StageCard({ stage, index }: { stage: PipelineStage; index: number }) {
  const isDevice = stage.id === "device";
  return (
    <div
      className="sr-fade-up relative flex-1 min-w-[180px] bg-neutral-900 border border-neutral-800 rounded-xl p-5 hover:border-neutral-700 transition-colors"
      style={{ animationDelay: `${index * 120}ms` }}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-2xl">{stage.icon}</span>
        <span className="font-mono text-xs text-neutral-600">{stage.step}</span>
      </div>
      <h3 className="font-semibold">{stage.label}</h3>
      <p className="text-xs text-neutral-500 mb-3">{stage.sublabel}</p>
      <p className="text-sm text-neutral-400 leading-relaxed mb-4">{stage.detail}</p>
      <span
        className={
          "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full " +
          (isDevice
            ? "text-amber-400 bg-amber-400/10"
            : "text-neutral-400 bg-neutral-800 font-mono")
        }
      >
        {isDevice && <span className="sr-rec-dot w-2 h-2 rounded-full bg-amber-400" />}
        {stage.meta}
      </span>
    </div>
  );
}

function Arrow() {
  return (
    <div className="hidden lg:flex items-center text-neutral-700 px-1 select-none" aria-hidden>
      <span className="text-xl">→</span>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
      <p className="text-neutral-500 text-xs mb-1">{label}</p>
      <p className={"text-2xl font-bold font-mono " + (accent ? "text-amber-500" : "")}>{value}</p>
    </div>
  );
}

export default function DemoPage() {
  return (
    <div>
      <div className="sr-fade-up">
        <p className="text-xs uppercase tracking-[0.2em] text-amber-500 mb-2">OpenAV · control plane</p>
        <h1 className="text-2xl font-bold mb-1">AV / Edge Demo</h1>
        <p className="text-neutral-500 text-sm mb-8 max-w-2xl">
          An open-weight model on the edge answers a plain-English AV question by driving an Epiphan
          Pearl over MCP — self-hosted end to end, zero cloud inference, zero vendor lock-in.
        </p>
      </div>

      {/* Headline stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
        <Stat label="Edge model" value={DEMO_META.model.replace("ollama/", "")} />
        <Stat label="Inference cost" value={DEMO_META.inferenceCost} accent />
        <Stat label="Cloud calls" value={String(DEMO_META.cloudCalls)} />
        <Stat label="Protocol" value={DEMO_META.protocol} />
      </div>

      {/* Pipeline */}
      <h2 className="text-lg font-semibold mb-4">The pipeline</h2>
      <div className="flex flex-col lg:flex-row lg:items-stretch gap-4 lg:gap-0 mb-10">
        {PIPELINE.map((stage, i) => (
          <div key={stage.id} className="flex flex-1 items-stretch">
            <StageCard stage={stage} index={i} />
            {i < PIPELINE.length - 1 && <Arrow />}
          </div>
        ))}
      </div>

      {/* Live agent trace + device status (streams from the API; falls back to
          static fixtures when the API is unreachable). */}
      <LiveRoomView />

      <p className="text-neutral-600 text-xs mt-8">
        Live from the API when reachable (<span className="font-mono text-neutral-500">/demo/stream</span> ·
        SSE) — otherwise canned Pearl-2-Room320B fixtures. Run the agent yourself:{" "}
        <span className="font-mono text-neutral-500">python demo/agent_ready_av_demo.py --mock-mcp</span>
      </p>
    </div>
  );
}
