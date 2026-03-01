import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SilkRoute Dashboard",
  description: "AI agent orchestrator for Chinese LLMs",
};

function NavLink({ href, label, icon }: { href: string; label: string; icon: string }) {
  return (
    <a href={href} className="flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors">
      <span className="text-lg">{icon}</span>
      <span>{label}</span>
    </a>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen">
        {/* Sidebar */}
        <aside className="w-60 border-r border-neutral-800 p-4 flex flex-col gap-1">
          <div className="px-4 py-3 mb-4">
            <h1 className="text-lg font-bold text-amber-500">SilkRoute</h1>
            <p className="text-xs text-neutral-500">Chinese LLM Orchestrator</p>
          </div>
          <NavLink href="/" label="Overview" icon="📊" />
          <NavLink href="/projects" label="Projects" icon="📁" />
          <NavLink href="/models" label="Models" icon="🤖" />
          <NavLink href="/budget" label="Budget" icon="💰" />
          <div className="mt-auto px-4 py-3 text-xs text-neutral-600">
            v0.1.0
          </div>
        </aside>
        {/* Main content */}
        <main className="flex-1 p-8 overflow-auto">
          {children}
        </main>
      </body>
    </html>
  );
}
