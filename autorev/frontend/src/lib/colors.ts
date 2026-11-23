// Shades dark enough for white initials in both themes (no lime/yellow/cyan; red is kept for danger).
const PALETTE = ["indigo", "violet", "grape", "pink", "teal", "blue", "green"];

/** A stable Mantine color for a string (app slug, user email), for avatars. */
export function colorFor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

/** "Pixel Fun" -> "PF", "dana@x.com" -> "DA". */
export function initials(name: string): string {
  const words = name.trim().split(/[\s._@-]+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}
