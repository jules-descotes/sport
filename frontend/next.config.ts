import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Le service worker doit pouvoir être remplacé sans purge de cache navigateur.
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
};

export default nextConfig;
