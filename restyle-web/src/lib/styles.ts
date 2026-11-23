/** A style the user can apply: one of the app's templates in AppJs Studio, plus the design's category
 * and card colour. The server decides which styles exist, their order and price; these hints only
 * decorate (same table as the Android app's `Templates.hints`). */
import type { Template } from "./api";

export type Style = {
  slug: string;
  name: string;
  meta: string;
  description: string;
  category: string;
  color: string;
  credits: number;
  isNew: boolean;
  trending: boolean;
  coverUrl: string | null;
  slot: string;
};

type Hint = { category: string; meta: string; color: string; isNew?: boolean };

const HINTS: Record<string, Hint> = {
  "ghibli-style": { category: "Anime", meta: "Anime · Hand-painted", color: "#3C5A3A" },
  "anime-watercolor": { category: "Anime", meta: "Anime · Popular", color: "#2F4B3A" },
  "80s-style": { category: "Retro", meta: "Retro · Synthwave", color: "#3B1F5C" },
  "80s-retro": { category: "Retro", meta: "Retro · Synthwave", color: "#3B1F5C" },
  "oil-portrait": { category: "Painting", meta: "Painting · Classic", color: "#7A3B1D" },
  "comic-pop": { category: "Cartoon", meta: "Cartoon · Bold ink", color: "#1E3A5F" },
  "clay-figure": { category: "3D", meta: "3D · Playful", color: "#8A4B2E", isNew: true },
  "pixel-art": { category: "Retro", meta: "Retro · 16-bit", color: "#24364F" },
  "90s-film": { category: "Retro", meta: "Retro · Grainy", color: "#5A4632", isNew: true },
  "cyber-neon": { category: "3D", meta: "3D · Night city", color: "#2B1640" },
};

const PALETTE = ["#2F4B3A", "#3B1F5C", "#7A3B1D", "#1E3A5F", "#8A4B2E", "#24364F", "#5A4632", "#2B1640"];

/** Java's String.hashCode, so a slug gets the same colour as on Android. */
export function javaHash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return h;
}

export function toStyle(t: Template, index: number): Style {
  const hint = HINTS[t.slug];
  return {
    slug: t.slug,
    name: t.title,
    meta: hint?.meta ?? (t.description || "Style"),
    description: t.description,
    category: hint?.category ?? "More",
    color: hint?.color ?? PALETTE[Math.abs(javaHash(t.slug)) % PALETTE.length],
    credits: t.credit_cost,
    isNew: hint?.isNew ?? false,
    trending: index === 0,
    coverUrl: t.cover_url,
    slot: t.inputs[0]?.name ?? "photo",
  };
}

export function categories(styles: Style[]): string[] {
  return ["All", ...new Set(styles.map((s) => s.category))];
}

export function filterStyles(styles: Style[], category: string, query: string): Style[] {
  const q = query.trim().toLowerCase();
  return styles.filter(
    (s) =>
      (category === "All" || s.category === category) &&
      (!q || s.name.toLowerCase().includes(q) || s.meta.toLowerCase().includes(q)),
  );
}
