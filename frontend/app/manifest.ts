import type { MetadataRoute } from "next";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Sport";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${APP_NAME} — surf, training, nutrition`,
    short_name: APP_NAME,
    description:
      "Suivi surf, training et nutrition. Utilisable une main, sur la plage.",
    // Un seul hôte déclaré partout : le scope reste relatif à l'origine servie.
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0d171e",
    theme_color: "#0d171e",
    lang: "fr",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
