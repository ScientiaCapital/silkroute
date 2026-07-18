import { fetchLedger, fetchMemories } from "@/lib/api";
import type { LedgerEntry, LedgerSummaryResponse, MemoryItem, MemoryListResponse } from "@/lib/types";

async function getLedger(): Promise<LedgerSummaryResponse> {
  try {
    return await fetchLedger();
  } catch {
    return { entries: [], counts: {}, best: null, available: false };
  }
}

async function getMemories(): Promise<MemoryListResponse> {
  try {
    return await fetchMemories();
  } catch {
    return { items: [], count: 0, available: false };
  }
}

const STATUS_COLORS: Record<string, string> = {
  keep: "text-green-400 bg-green-400/10",
  discard: "text-amber-400 bg-amber-400/10",
  crash: "text-red-400 bg-red-400/10",
};

export default async function AutonomyPage() {
  const [ledger, memories] = await Promise.all([getLedger(), getMemories()]);
  const counts = ledger.counts;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Autonomy</h1>
      <p className="text-neutral-500 text-sm mb-8">
        The self-improvement loop&rsquo;s experiment ledger and the agent&rsquo;s persistent memory —
        what it has tried, kept, and learned.
      </p>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
        <StatCard label="Total Experiments" value={counts.total ?? 0} />
        <StatCard label="Kept" value={counts.keep ?? 0} valueClass="text-green-500" />
        <StatCard label="Discarded" value={counts.discard ?? 0} valueClass="text-amber-500" />
        <StatCard label="Crashed" value={counts.crash ?? 0} valueClass="text-red-500" />
        <StatCard
          label="Best Score"
          value={ledger.best ? ledger.best.score.toFixed(4) : "—"}
        />
      </div>

      {/* Experiment ledger */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden mb-8">
        <div className="p-6 pb-4">
          <h2 className="text-lg font-semibold">Experiment Ledger</h2>
          <p className="text-neutral-500 text-sm mt-1">
            Every code/config change the research engine has tried, kept or discarded.
          </p>
        </div>
        {!ledger.available ? (
          <p className="text-neutral-500 text-sm px-6 pb-6">
            No experiments recorded yet. Run{" "}
            <code className="text-amber-500">silkroute research start</code> to begin the
            self-improvement loop.
          </p>
        ) : ledger.entries.length === 0 ? (
          <p className="text-neutral-500 text-sm px-6 pb-6">No experiments recorded yet.</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-neutral-800 text-xs text-neutral-500 uppercase tracking-wider">
                <th className="text-left p-4">Commit</th>
                <th className="text-right p-4">Score</th>
                <th className="text-right p-4">Pass Rate</th>
                <th className="text-right p-4">Coverage</th>
                <th className="text-left p-4">Status</th>
                <th className="text-left p-4">Description</th>
              </tr>
            </thead>
            <tbody>
              {ledger.entries.map((entry, i) => (
                <LedgerRow key={`${entry.commit}-${i}`} entry={entry} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Agent memories */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden">
        <div className="p-6 pb-4">
          <h2 className="text-lg font-semibold">Agent Memories</h2>
          <p className="text-neutral-500 text-sm mt-1">
            Facts, preferences, and outcomes the agent has persisted across sessions.
          </p>
        </div>
        {!memories.available ? (
          <p className="text-neutral-500 text-sm px-6 pb-6">Memory store unavailable.</p>
        ) : memories.items.length === 0 ? (
          <p className="text-neutral-500 text-sm px-6 pb-6">No memories recorded yet.</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-neutral-800 text-xs text-neutral-500 uppercase tracking-wider">
                <th className="text-left p-4">Kind</th>
                <th className="text-left p-4">Content</th>
                <th className="text-right p-4">Importance</th>
                <th className="text-right p-4">Recalled</th>
                <th className="text-left p-4">Created</th>
              </tr>
            </thead>
            <tbody>
              {memories.items.map((item) => (
                <MemoryRow key={item.id} item={item} />
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string | number;
  valueClass?: string;
}) {
  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
      <p className="text-xs text-neutral-500 uppercase tracking-wider">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${valueClass ?? ""}`}>{value}</p>
    </div>
  );
}

function LedgerRow({ entry }: { entry: LedgerEntry }) {
  const statusClass = STATUS_COLORS[entry.status] ?? "text-neutral-400 bg-neutral-400/10";
  return (
    <tr className="border-b border-neutral-800/50 hover:bg-neutral-800/30">
      <td className="p-4 font-mono text-sm">{entry.commit}</td>
      <td className="p-4 text-right font-mono text-sm">{entry.score.toFixed(4)}</td>
      <td className="p-4 text-right font-mono text-sm">{(entry.pass_rate * 100).toFixed(0)}%</td>
      <td className="p-4 text-right font-mono text-sm">{(entry.coverage * 100).toFixed(0)}%</td>
      <td className="p-4">
        <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${statusClass}`}>
          {entry.status}
        </span>
      </td>
      <td className="p-4 text-neutral-400 text-sm">{entry.description}</td>
    </tr>
  );
}

function MemoryRow({ item }: { item: MemoryItem }) {
  return (
    <tr className="border-b border-neutral-800/50 hover:bg-neutral-800/30">
      <td className="p-4 text-sm text-neutral-400">{item.kind}</td>
      <td className="p-4 text-sm max-w-md truncate">{item.content}</td>
      <td className="p-4 text-right font-mono text-sm">{item.importance.toFixed(2)}</td>
      <td className="p-4 text-right font-mono text-sm">{item.recall_count}</td>
      <td className="p-4 text-xs text-neutral-600">
        {item.created_at ? new Date(item.created_at).toLocaleString() : "—"}
      </td>
    </tr>
  );
}
