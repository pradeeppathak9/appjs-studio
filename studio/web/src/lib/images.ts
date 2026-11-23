export const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export type Picked = { file: File; url: string };

export function pick(file: File): Picked {
  return { file, url: URL.createObjectURL(file) };
}
