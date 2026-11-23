import type { ProviderInfo } from "../api/types";

/** What the form can offer for the chosen provider ("server default" = union of all providers). */
export function capabilitiesFor(providers: ProviderInfo[], name: string, media: "image" | "video") {
  const p = providers.find((x) => x.name === name);
  const all = p ? [p] : providers;
  const uniq = (xs: string[]) => [...new Set(xs)];
  return {
    provider: p,
    media: { image: all.some((x) => x.image), video: all.some((x) => x.video) },
    models: uniq(all.flatMap((x) => (media === "image" ? x.known_image_models : x.known_video_models))),
    ratios: uniq(all.flatMap((x) => (media === "image" ? x.image_aspect_ratios : x.video_aspect_ratios))),
    durations: [...new Set(all.flatMap((x) => x.video_durations))].sort((a, b) => a - b),
    maxImages: p ? p.max_images : Math.max(1, ...providers.map((x) => x.max_images)),
    negative: p ? p.supports_negative_prompt : false,
    seed: p ? p.supports_seed : false,
  };
}
