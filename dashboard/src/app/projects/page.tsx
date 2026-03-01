import { fetchProjects } from "@/lib/api";
import type { Project } from "@/lib/types";

async function getProjects(): Promise<{ projects: Project[]; total: number }> {
  try {
    return await fetchProjects();
  } catch {
    return { projects: [], total: 0 };
  }
}

export default async function ProjectsPage() {
  const { projects, total } = await getProjects();

  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Projects</h1>
      <p className="text-neutral-500 text-sm mb-8">
        {total} project{total !== 1 ? "s" : ""} with budget governance.
      </p>

      {projects.length === 0 ? (
        <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-8 text-center">
          <p className="text-neutral-400">No projects found.</p>
          <p className="text-neutral-600 text-sm mt-2">
            Create a project via the CLI: <code className="text-amber-500">silkroute projects create</code>
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectCard({ project }: { project: Project }) {
  const budgetPct = project.budget_monthly_usd > 0
    ? 0  // Will show actual spend when budget API is wired
    : 0;

  return (
    <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-5 hover:border-neutral-700 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="font-semibold">{project.name}</h3>
          <p className="text-xs text-neutral-500 font-mono">{project.id}</p>
        </div>
        {project.github_repo && (
          <span className="text-xs px-2 py-1 rounded-full bg-neutral-800 text-neutral-400">
            {project.github_repo}
          </span>
        )}
      </div>

      {project.description && (
        <p className="text-sm text-neutral-400 mb-3">{project.description}</p>
      )}

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>
          <p className="text-neutral-500 text-xs">Monthly Budget</p>
          <p className="font-mono">${project.budget_monthly_usd.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-neutral-500 text-xs">Daily Budget</p>
          <p className="font-mono">${project.budget_daily_usd.toFixed(2)}</p>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-neutral-800">
        <p className="text-xs text-neutral-600">
          Created {new Date(project.created_at).toLocaleDateString() || "—"}
        </p>
      </div>
    </div>
  );
}
