"""Generate a cover image for each template of an app that has none, and save it as the cover.

Each cover is one text-to-image generation, then an upload, then a template save (a new version
with only `cover_upload` changed). `--source studio` (default) runs it on a Studio provider (a real,
paid call); `--source pollinations` uses the free public image.pollinations.ai API (FLUX).

    STUDIO_TOKEN=... uv run python scripts/template_covers.py --app <app-id> [--source pollinations]
        [--from-dir data/restyle-covers] [--only slug,slug] [--force]

`--from-dir` uploads existing `<slug>.jpg` files instead (e.g. copying covers to another server).

Prompts live in COVER_PROMPTS below; templates without one are skipped.
"""

import argparse
import io
import os
import sys
import time
import zlib
from pathlib import Path
from urllib.parse import quote

import httpx
from PIL import Image

STYLE = "Vertical 4:5 app thumbnail, one striking subject, centered, no text, no logos, no watermark."

COVER_PROMPTS = {
    "ghibli-style": "A young woman in a sundress standing in a breezy summer meadow beside a small "
    "countryside house, painted as a hand-painted Japanese anime film still: soft watercolor backgrounds, "
    "gentle cel shading, lush greenery, fluffy cumulus clouds, warm golden light.",
    "80s-style": "Portrait of a young man in a denim jacket and aviator sunglasses, 1980s synthwave poster: "
    "neon magenta and cyan rim light, striped sunset, chrome grid horizon, VHS scanlines, film grain.",
    "anime-watercolor": "Portrait of a girl with flowers in her hair, soft anime illustration in watercolor: "
    "delicate ink outlines, transparent washes of pastel color bleeding at the edges, visible paper texture.",
    "pixel-art": "A smiling person with a backpack in a city park at sunset, crisp 16-bit pixel art like a "
    "classic console game: visible pixel grid, limited vibrant palette, clean dithering.",
    "clay-figure": "Cute 3D clay figurine of a smiling young woman waving, stop-motion style: handmade "
    "modeling clay, soft rounded shapes, tiny garden set, warm soft lighting.",
    "90s-film": "Candid snapshot of friends laughing at a rooftop party, 1990s 35mm film photo: warm faded "
    "colors, lifted blacks, visible grain, a light leak, direct on-camera flash.",
    "cyber-neon": "Portrait of a woman in a reflective jacket on a rain-wet street at night, cyberpunk "
    "city: glowing pink, purple and teal neon signs, holographic accents, strong rim light, reflections.",
    "comic-pop": "Close-up of a surprised young man, bold pop-art comic book panel: thick ink outlines, "
    "flat saturated primary colors, Ben-Day halftone dots, dramatic action lines.",
    "oil-portrait": "Portrait of an elegant middle-aged man, classical oil painting: rich layered "
    "brushstrokes, canvas texture, warm chiaroscuro lighting, deep muted background, gilded-era mood.",
    "decade-portrait": "Studio portrait of a woman styled in 1970s fashion: feathered hair, wide collar "
    "blouse, warm film tones, period-correct backdrop and lighting, like a vintage magazine photo.",
    "neon-city-poster": "Illustrated poster of a confident young man in a leather jacket, retro painted art: "
    "sunset city skyline, palm trees, pink and orange neon glow, bold heroic pose.",
    "ride-a-lion": "Cinematic photo of a young woman riding a majestic lion across golden savanna grass at "
    "sunset, mane blowing in the wind, dust in the backlight, epic and joyful.",
    "wedding-guest-look": "Candid wedding-photographer portrait of a stylish couple dressed as wedding "
    "guests, he in a tailored sherwani, she in an embroidered lehenga, marigold decor, soft bokeh lights.",
    "y2k-digicam": "Friends posing at a 2003 house party photographed on an early compact digital camera: "
    "harsh flash, slightly blown highlights, cool white balance, low dynamic range, candid Y2K vibe.",
}


def from_studio(c: httpx.Client, base: str, prompt: str, provider: str, model: str) -> tuple[bytes, str]:
    """A text-to-image generation through Studio itself (a real provider call)."""
    body = {"prompt": prompt, "provider": provider, "model": model, "aspect_ratio": "4:5"}
    job = c.post(f"{base}/generations", json=body).raise_for_status().json()
    while job["status"] in ("queued", "running"):
        time.sleep(2)
        job = c.get(f"/v1/generations/{job['id']}").raise_for_status().json()
    if job["status"] != "succeeded" or not job["assets"]:
        raise RuntimeError(job.get("error"))
    asset = job["assets"][0]
    return c.get(asset["url"]).raise_for_status().content, asset["mime_type"]


def crop_watermark(data: bytes) -> bytes:
    """The free tier stamps a logo bottom-right (it ignores nologo): cut the bottom 8%, then trim the
    sides so the picture stays 4:5."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    h2 = int(h * 0.92)
    w2 = min(w, h2 * 4 // 5)
    left = (w - w2) // 2
    out = io.BytesIO()
    im.crop((left, 0, left + w2, h2)).save(out, "JPEG", quality=90)
    return out.getvalue()


def from_pollinations(prompt: str, slug: str) -> tuple[bytes, str]:
    """Free, keyless FLUX images from image.pollinations.ai (a public third-party service)."""
    url = f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}"
    params = {
        "width": 800,
        "height": 1000,
        "model": "flux",
        "nologo": "true",
        "seed": zlib.crc32(slug.encode()) % 2**31,  # must fit a signed 32-bit int
    }
    for attempt in range(4):
        r = httpx.get(url, params=params, timeout=180, follow_redirects=True)
        mime = r.headers.get("content-type", "").split(";")[0]
        if r.status_code == 200 and mime.startswith("image/"):
            return crop_watermark(r.content), "image/jpeg"
        time.sleep(10 * (attempt + 1))  # rate limited or busy
    raise RuntimeError(f"pollinations {r.status_code} {mime}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--app", required=True, help="app id (uuid)")
    p.add_argument("--url", default=os.environ.get("STUDIO_URL", "http://localhost:8010"))
    p.add_argument(
        "--source",
        choices=["studio", "pollinations"],
        default="studio",
        help="studio: a generation on --provider/--model (paid); pollinations: free public FLUX API",
    )
    p.add_argument("--from-dir", help="upload <slug>.jpg from this folder instead of generating")
    p.add_argument("--provider", default="openrouter")
    p.add_argument("--model", default="google/gemini-2.5-flash-image")
    p.add_argument("--only", help="comma-separated slugs")
    p.add_argument("--force", action="store_true", help="replace existing covers")
    args = p.parse_args()
    token = os.environ.get("STUDIO_TOKEN") or sys.exit("set STUDIO_TOKEN")
    only = set(args.only.split(",")) if args.only else None

    c = httpx.Client(base_url=args.url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    base = f"/v1/apps/{args.app}"
    templates = c.get(f"{base}/manage/templates").raise_for_status().json()

    for t in templates:
        slug = t["slug"]
        if only and slug not in only:
            continue
        if t["cover_url"] and not args.force:
            print(f"{slug}: has a cover, skipped")
            continue
        if args.from_dir:
            path = Path(args.from_dir) / f"{slug}.jpg"
            if not path.exists():
                print(f"{slug}: no {path.name} in {args.from_dir}, skipped")
                continue
            image, mime = path.read_bytes(), "image/jpeg"
        prompt = COVER_PROMPTS.get(slug)
        if not args.from_dir and not prompt:
            print(f"{slug}: no cover prompt, skipped")
            continue

        full_prompt = f"{prompt} {STYLE}"
        try:
            if args.from_dir:
                pass
            elif args.source == "pollinations":
                image, mime = from_pollinations(full_prompt, slug)
            else:
                image, mime = from_studio(c, base, full_prompt, args.provider, args.model)
        except Exception as e:  # noqa: BLE001 - report and go on to the next template
            print(f"{slug}: generation failed: {e}")
            continue
        ext = mime.split("/")[-1]
        up = (
            c.post(f"{base}/uploads", files={"file": (f"{slug}-cover.{ext}", image, mime)})
            .raise_for_status()
            .json()
        )

        full = c.get(f"{base}/manage/templates/{t['id']}").raise_for_status().json()
        cur = full["current"]
        body = {
            k: cur[k]
            for k in (
                "title", "description", "media_type", "provider", "model", "allowed_models", "prompt",
                "negative_prompt", "params", "inputs", "variables", "reference_uploads",
            )
        }  # fmt: skip
        body |= {"cover_upload": up["id"], "note": "cover image", "base_version": full["current_version"]}
        r = c.put(f"{base}/manage/templates/{t['id']}", json=body)
        if r.status_code >= 400:
            print(f"{slug}: save failed {r.status_code}: {r.text}")
            continue
        print(f"{slug}: cover set (version {r.json()['template']['current_version']})")


if __name__ == "__main__":
    main()
