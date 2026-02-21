import type { BudgetSnapshot } from "@/lib/types";

const mockBudgets: BudgetSnapshot[] = [
  { projectId: "default", projectName: "Default Project", budgetMonthlyUsd: 200, spentThisMonth: 0, remaining: 200, status: "OK" },
  { projectId: "lang-core", projectName: "lang-core", budgetMonthlyUsd: 2.85, spentThisMonth: 0, remaining: 2.85, status: "OK" },
  { projectId: "signal-siphon", projectName: "signal-siphon", budgetMonthlyUsd: 2.85, spentThisMonth: 0, remaining: 2.85, status: "OK" },
];

const statusColors: Record<string, string> = {
  OK: "text-green-500",
  WARNING: "text-amber-500",
  CRITICAL: "text-red-500",
  EXCEEDED: "text-red-700",
};

export default function BudgetPage() {
  const totalBudget = mockBudgets.reduce((sum, b) => sum + b.budgetMonthlyUsd, 0);
  const totalSpent = mockBudgets.reduce((sum, b) => sum + b.spentThisMonth, 0);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Budget Tracker</h1>
      <p className="text-neutral-500 text-sm mb-8">Per-project spend tracking with alert thresholds.</p>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
          <p className="text-xs text-neutral-500 uppercase tracking-wider">Monthly Budget</p>
          <p className="text-3xl font-bold mt-1">${totalBudget.toFixed(2)}</p>
        </div>
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
          <p className="text-xs text-neutral-500 uppercase tracking-wider">Spent This Month</p>
          <p className="text-3xl font-bold mt-1 text-green-500">${totalSpent.toFixed(2)}</p>
        </div>
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
          <p className="text-xs text-neutral-500 uppercase tracking-wider">Remaining</p>
          <p className="text-3xl font-bold mt-1">${(totalBudget - totalSpent).toFixed(2)}</p>
        </div>
      </div>

      {/* Project Table */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-neutral-800 text-xs text-neutral-500 uppercase tracking-wider">
              <th className="text-left p-4">Project</th>
              <th className="text-right p-4">Budget</th>
              <th className="text-right p-4">Spent</th>
              <th className="text-right p-4">Remaining</th>
              <th className="text-right p-4">Status</th>
            </tr>
          </thead>
          <tbody>
            {mockBudgets.map((budget) => (
              <tr key={budget.projectId} className="border-b border-neutral-800/50 hover:bg-neutral-800/30">
                <td className="p-4 font-medium">{budget.projectName}</td>
                <td className="p-4 text-right font-mono text-sm">${budget.budgetMonthlyUsd.toFixed(2)}</td>
                <td className="p-4 text-right font-mono text-sm">${budget.spentThisMonth.toFixed(2)}</td>
                <td className="p-4 text-right font-mono text-sm">${budget.remaining.toFixed(2)}</td>
                <td className={`p-4 text-right font-semibold text-sm ${statusColors[budget.status]}`}>{budget.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Alert Thresholds */}
      <div className="mt-8 bg-neutral-900 border border-neutral-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Alert Thresholds</h2>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-neutral-400">Warning</span><span className="text-amber-500">50% of budget</span></div>
          <div className="flex justify-between"><span className="text-neutral-400">Critical</span><span className="text-red-500">80% of budget</span></div>
          <div className="flex justify-between"><span className="text-neutral-400">Shutdown</span><span className="text-red-700">100% of budget</span></div>
        </div>
      </div>
    </div>
  );
}
