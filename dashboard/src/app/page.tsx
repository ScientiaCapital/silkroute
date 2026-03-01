import { ALL_MODELS } from "@/lib/models";
import { fetchGlobalBudget } from "@/lib/api";

async function getBudgetStats() {
  try {
    const budget = await fetchGlobalBudget();
    return {
      todaySpend: `$${budget.daily_spent_usd.toFixed(2)}`,
      dailyBudget: `$${budget.daily_limit_usd.toFixed(2)}`,
    };
  } catch {
    return { todaySpend: "$0.00", dailyBudget: "$10.00" };
  }
}

export default async function DashboardPage() {
  const { todaySpend, dailyBudget } = await getBudgetStats();

  const stats = [
    { label: "Total Models", value: ALL_MODELS.length.toString(), sub: "across 4 providers" },
    { label: "Free Models", value: ALL_MODELS.filter(m => m.isFree).length.toString(), sub: "zero cost" },
    { label: "Today's Spend", value: todaySpend, sub: `budget: ${dailyBudget}/day` },
    { label: "Active Sessions", value: "0", sub: "idle" },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Dashboard Overview</h1>
      <p className="text-neutral-500 text-sm mb-8">The fastest route from task to done — powered by China&apos;s best AI.</p>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((stat) => (
          <div key={stat.label} className="bg-neutral-900 border border-neutral-800 rounded-xl p-5">
            <p className="text-xs text-neutral-500 uppercase tracking-wider">{stat.label}</p>
            <p className="text-3xl font-bold mt-1">{stat.value}</p>
            <p className="text-xs text-neutral-600 mt-1">{stat.sub}</p>
          </div>
        ))}
      </div>

      {/* Tier Breakdown */}
      <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4">Model Tier Breakdown</h2>
        <div className="space-y-3">
          {([
            { tier: "Free", count: ALL_MODELS.filter(m => m.tier === "free").length, color: "bg-green-500", desc: "Rate-limited, zero cost" },
            { tier: "Standard", count: ALL_MODELS.filter(m => m.tier === "standard").length, color: "bg-blue-500", desc: "$0.06 — $1.00/M tokens" },
            { tier: "Premium", count: ALL_MODELS.filter(m => m.tier === "premium").length, color: "bg-amber-500", desc: "$0.22 — $3.20/M tokens" },
          ]).map((row) => (
            <div key={row.tier} className="flex items-center gap-4">
              <span className={`w-3 h-3 rounded-full ${row.color}`} />
              <span className="w-24 font-medium">{row.tier}</span>
              <span className="text-neutral-400">{row.count} models</span>
              <span className="text-neutral-600 text-sm ml-auto">{row.desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
