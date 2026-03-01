import { fetchSupervisorSessions } from "@/lib/api";
import type { SupervisorSession, SupervisorStepSummary } from "@/lib/types";

async function getSessions(): Promise<SupervisorSession[]> {
  try {
    return await fetchSupervisorSessions();
  } catch {
    return [];
  }
}

const STATUS_COLORS: Record<string, string> = {
  completed: "text-green-400 bg-green-400/10",
  running: "text-amber-400 bg-amber-400/10",
  failed: "text-red-400 bg-red-400/10",
  paused: "text-blue-400 bg-blue-400/10",
  cancelled: "text-neutral-400 bg-neutral-400/10",
};

const STEP_COLORS: Record<string, string> = {
  completed: "bg-green-500",
  running: "bg-amber-500 animate-pulse",
  failed: "bg-red-500",
  skipped: "bg-neutral-600",
  pending: "bg-neutral-800",
};

export default async function TaskHistoryPage() {
  const sessions = await getSessions();

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Task History</h1>
      <p className="text-neutral-500 text-sm mb-8">
        {sessions.length} supervisor session{sessions.length !== 1 ? "s" : ""}.
      </p>

      {sessions.length === 0 ? (
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-8 text-center">
          <p className="text-neutral-400">No supervisor sessions found.</p>
          <p className="text-neutral-600 text-sm mt-2">
            Create a session via the API:{" "}
            <code className="text-amber-500">POST /supervisor/sessions</code>
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {sessions.map((session) => (
            <SessionCard key={session.id} session={session} />
          ))}
        </div>
      )}
    </div>
  );
}

function SessionCard({ session }: { session: SupervisorSession }) {
  const statusClass = STATUS_COLORS[session.status] ?? STATUS_COLORS.cancelled;
  const completedSteps = session.steps.filter((s) => s.status === "completed").length;
  const totalSteps = session.steps.length;

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5 hover:border-neutral-700 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-xs text-neutral-500 font-mono">{session.id}</p>
          <p className="text-sm text-neutral-400 mt-1">
            Project: <span className="text-neutral-300">{session.project_id}</span>
          </p>
        </div>
        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${statusClass}`}>
          {session.status}
        </span>
      </div>

      {/* Step progress bar */}
      {totalSteps > 0 && (
        <div className="mb-3">
          <div className="flex items-center justify-between text-xs text-neutral-500 mb-1.5">
            <span>
              {completedSteps}/{totalSteps} steps
            </span>
            <span>${session.total_cost_usd.toFixed(4)}</span>
          </div>
          <div className="flex gap-1">
            {session.steps.map((step) => (
              <StepIndicator key={step.id} step={step} totalSteps={totalSteps} />
            ))}
          </div>
        </div>
      )}

      {/* Step details */}
      {totalSteps > 0 && (
        <div className="space-y-1 mb-3">
          {session.steps.map((step) => (
            <div key={step.id} className="flex items-center gap-2 text-xs">
              <span className={`w-1.5 h-1.5 rounded-full ${STEP_COLORS[step.status] ?? STEP_COLORS.pending}`} />
              <span className="text-neutral-400">{step.name}</span>
              {step.cost_usd > 0 && (
                <span className="text-neutral-600 ml-auto font-mono">
                  ${step.cost_usd.toFixed(4)}
                </span>
              )}
              {step.error && (
                <span className="text-red-400 ml-auto truncate max-w-[200px]">
                  {step.error}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {session.error && (
        <p className="text-xs text-red-400 bg-red-400/5 rounded px-2 py-1 mb-3">
          {session.error}
        </p>
      )}

      <div className="pt-3 border-t border-neutral-800 flex items-center justify-between">
        <p className="text-xs text-neutral-600">
          {session.created_at ? new Date(session.created_at).toLocaleString() : "\u2014"}
        </p>
        {session.total_cost_usd > 0 && (
          <p className="text-xs font-mono text-neutral-500">
            Total: ${session.total_cost_usd.toFixed(4)}
          </p>
        )}
      </div>
    </div>
  );
}

function StepIndicator({
  step,
  totalSteps,
}: {
  step: SupervisorStepSummary;
  totalSteps: number;
}) {
  const color = STEP_COLORS[step.status] ?? STEP_COLORS.pending;
  return (
    <div
      className={`h-2 rounded-sm ${color}`}
      style={{ flex: `1 1 ${100 / totalSteps}%` }}
      title={`${step.name}: ${step.status}`}
    />
  );
}
