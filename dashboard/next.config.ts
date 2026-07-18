import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8787/:path*",
      },
    ];
  },
  async redirects() {
    // The AV/Edge Demo moved to "/" (the new landing page); everything else
    // moved under /ops/*. Not `permanent` — this is still an active
    // reorganization, no reason to let it get cached forever this early.
    return [
      { source: "/demo", destination: "/", permanent: false },
      { source: "/models", destination: "/ops/models", permanent: false },
      { source: "/budget", destination: "/ops/budget", permanent: false },
      { source: "/tasks", destination: "/ops/tasks", permanent: false },
      { source: "/autonomy", destination: "/ops/autonomy", permanent: false },
      { source: "/projects", destination: "/ops/projects", permanent: false },
    ];
  },
};

export default nextConfig;
