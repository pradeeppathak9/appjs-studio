/** Output shapes, as on Android: the photo is cropped to the shape first, so the template (aspect
 * ratio "auto") returns an image of the same shape. */
export type Ratio = { id: "1:1" | "4:5" | "9:16"; label: string; hint: string; w: number; h: number };

export const RATIOS: Ratio[] = [
  { id: "1:1", label: "1:1", hint: "Post", w: 1, h: 1 },
  { id: "4:5", label: "4:5", hint: "Portrait", w: 4, h: 5 },
  { id: "9:16", label: "9:16", hint: "Story", w: 9, h: 16 },
];

export const MAX_SIDE = 2048; // the server downscales to this anyway: don't upload more
export const MAX_BYTES = 10 * 1024 * 1024;

/** The centred crop of a `width`×`height` image with the ratio's shape, scaled to fit `maxSide`. */
export function cropBox(width: number, height: number, ratio: Ratio, maxSide = MAX_SIDE) {
  const target = ratio.w / ratio.h;
  let sw = width;
  let sh = height;
  if (width / height > target) sw = Math.round(height * target);
  else sh = Math.round(width / target);
  const sx = Math.round((width - sw) / 2);
  const sy = Math.round((height - sh) / 2);
  const scale = Math.min(1, maxSide / Math.max(sw, sh));
  return { sx, sy, sw, sh, dw: Math.round(sw * scale), dh: Math.round(sh * scale) };
}

/** Decode (EXIF orientation applied), crop to the ratio and encode as JPEG. */
export async function cropToRatio(file: Blob, ratio: Ratio): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  try {
    const b = cropBox(bitmap.width, bitmap.height, ratio);
    const canvas = document.createElement("canvas");
    canvas.width = b.dw;
    canvas.height = b.dh;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("no canvas");
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bitmap, b.sx, b.sy, b.sw, b.sh, 0, 0, b.dw, b.dh);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("encode failed"))), "image/jpeg", 0.9),
    );
  } finally {
    bitmap.close();
  }
}

export function isImage(file: File): boolean {
  return ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"].includes(file.type) || /\.(jpe?g|png|webp|heic|heif)$/i.test(file.name);
}
