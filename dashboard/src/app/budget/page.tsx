import { fetchProjects, fetchProjectBudget } from "@/lib/api";
import type { BudgetSnapshot } from "@/lib/types";

const mockBudgets: BudgetSnapshot[] = [
  { projectId: "default", projectName: "Default Project", budgetMonthlyUsd: 200, spentThisMonth: 0, remaining: 200, status: "OK" },
];

async function getBudgets(): Promise<BudgetSnapshot[]> {
  try {
    const { projects } = await fetchProjects();
    if (projects.length === 0) return mockBudgets;

    const budgets: BudgetSnapshot[] = await Promise.all(
      projects.map(async (p) => {
        try {
          const b = await fetchProjectBudget(p.id);
          const spent = b.monthly_spent_usd;
          const limit = b.monthly_limit_usd ?? p.budget_monthly_usd;
          const remaining = limit - spent;
          const pct = limit > 0 ? spent / limit : 0;
          let status: BudgetSnapshot["status"] = "OK";
          if (pct >= 1.0) status = "EXCEEDED";
          else if (pct >= 0.8) status = "CRITICAL";
          else if (pct >= 0.5) status = "WARNING";
          return {
            projectId: p.id,
            projectName: p.name,
            budgetMonthlyUsd: limit,
            spentThisMonth: spent,
            remaining,
            status,
          };
        } catch {
          return {
            projectId: p.id,
            projectName: p.name,
            budgetMonthlyUsd: p.budget_monthly_usd,
            spentThisMonth: 0,
            remaining: p.budget_monthly_usd,
            status: "OK" as const,
          };
        }
      })
    );
    return budgets;
  } catch {
    return mockBudgets;
  }
}

const statusColors: Record<string, string> = {
  OK: "text-green-500",
  WARNING: "text-amber-500",
  CRITICAL: "text-red-500",
  EXCEEDED: "text-red-700",
};

export default async function BudgetPage() {
  const budgets = await getBudgets();
  const totalBudget = budgets.reduce((sum, b) => sum + b.budgetMonthlyUsd, 0);
  const totalSpent = budgets.reduce((sum, b) => sum + b.spentThisMonth, 0);

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
            {budgets.map((budget) => (
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
