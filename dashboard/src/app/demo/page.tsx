import { PIPELINE, PEARL, CONVERSATION, DEMO_META } from "@/lib/demo";
import type { PipelineStage, DemoTurn } from "@/lib/demo";

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

function Turn({ turn }: { turn: DemoTurn }) {
  if (turn.role === "tool") {
    return (
      <p className="font-mono text-xs text-amber-400/80 pl-1">{turn.text}</p>
    );
  }
  const isUser = turn.role === "user";
  return (
    <div className={isUser ? "" : "border-l-2 border-amber-500/40 pl-3"}>
      <p className="text-xs uppercase tracking-wide text-neutral-600 mb-1">
        {isUser ? "You" : "SilkRoute"}
      </p>
      <p className={isUser ? "text-neutral-200" : "text-neutral-300 leading-relaxed"}>{turn.text}</p>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Conversation */}
        <div className="sr-fade-up bg-neutral-900 border border-neutral-800 rounded-xl p-6" style={{ animationDelay: "480ms" }}>
          <h2 className="text-lg font-semibold mb-4">What the agent did</h2>
          <div className="flex flex-col gap-4">
            {CONVERSATION.map((turn, i) => (
              <Turn key={i} turn={turn} />
            ))}
          </div>
        </div>

        {/* Device status */}
        <div className="sr-fade-up bg-neutral-900 border border-neutral-800 rounded-xl p-6" style={{ animationDelay: "560ms" }}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">{PEARL.room}</h2>
            <span className="inline-flex items-center gap-2 text-xs px-2.5 py-1 rounded-full text-amber-400 bg-amber-400/10">
              <span className="sr-rec-dot w-2 h-2 rounded-full bg-amber-400" />
              {PEARL.state}
            </span>
          </div>
          <dl className="grid grid-cols-2 gap-y-4 gap-x-4 text-sm">
            <div>
              <dt className="text-neutral-500 text-xs">Device</dt>
              <dd className="font-mono">{PEARL.name}</dd>
            </div>
            <div>
              <dt className="text-neutral-500 text-xs">Model · FW</dt>
              <dd className="font-mono">{PEARL.model} · {PEARL.firmware}</dd>
            </div>
            <div>
              <dt className="text-neutral-500 text-xs">Recorder</dt>
              <dd>{PEARL.recorderName}</dd>
            </div>
            <div>
              <dt className="text-neutral-500 text-xs">Duration</dt>
              <dd className="font-mono">{PEARL.durationLabel}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-neutral-500 text-xs">File</dt>
              <dd className="font-mono text-neutral-300 break-all">{PEARL.filename}</dd>
            </div>
            <div className="col-span-2">
              <dt className="text-neutral-500 text-xs">Input signal</dt>
              <dd className="font-mono text-neutral-300">{PEARL.inputSignal}</dd>
            </div>
          </dl>
        </div>
      </div>

      <p className="text-neutral-600 text-xs mt-8">
        Static demo — canned Pearl-2-Room320B data. Run it live:{" "}
        <span className="font-mono text-neutral-500">python demo/agent_ready_av_demo.py --mock-mcp</span>
      </p>
    </div>
  );
}
