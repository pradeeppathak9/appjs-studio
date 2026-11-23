import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type DragEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { IconBack, IconSparkle, IconUpload } from "../components/Icons";
import { Empty, Spinner, StyleArt } from "../components/ui";
import { api, type Account } from "../lib/api";
import { drafts, useDraft } from "../lib/draft";
import { creditsLabel, userMessage } from "../lib/format";
import { cropToRatio, isImage, MAX_BYTES, RATIOS } from "../lib/image";
import { keys, useMe, useStyles } from "../lib/queries";
import { useSession } from "../lib/session";

export function Create() {
  const { slug } = useParams();
  const { token } = useSession();
  const styles = useStyles();
  const me = useMe();
  const { photo, previewUrl, ratio } = useDraft();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (styles.isLoading) return <Spinner />;
  const style = styles.data?.find((s) => s.slug === slug);
  if (!style)
    return (
      <Empty icon={<IconSparkle size={40} />} title="This style isn't available">
        <Link to="/">Browse styles</Link>
      </Empty>
    );

  const credits = me.data?.credits ?? 0;
  const needsSignIn = !token && style.credits > 0;
  const canAfford = credits >= style.credits;

  const pick = (file: File | undefined) => {
    setError(null);
    if (!file) return;
    if (!isImage(file)) return setError("Pick a JPG, PNG or WebP image.");
    if (file.size > MAX_BYTES * 3) return setError("That photo is too large. Pick one under 30 MB.");
    drafts.setPhoto(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    pick(e.dataTransfer.files[0]);
  };

  const generate = async () => {
    if (!photo) return;
    setBusy(true);
    setError(null);
    try {
      const cropped = await cropToRatio(photo, ratio).catch(() => {
        throw new Error("decode");
      });
      const job = await api.run(style.slug, style.slot, cropped);
      if (typeof job.credits === "number") {
        // the server charged the run: show its new balance now
        qc.setQueryData<Account>(keys.me, (a) => (a ? { ...a, credits: job.credits! } : a));
      }
      qc.invalidateQueries({ queryKey: keys.jobs });
      navigate(`/result/${job.id}`);
    } catch (e) {
      setError(e instanceof Error && e.message === "decode" ? "This photo couldn't be opened. Try a JPG or PNG." : userMessage(e, !!token));
      setBusy(false);
    }
  };

  return (
    <div className="stack" style={{ gap: 20 }}>
      <Link to="/" className="row muted" style={{ gap: 4, width: "fit-content" }}>
        <IconBack size={18} /> Back to templates
      </Link>
      <h1>New creation</h1>

      <div className="two-col">
        <div className="stack">
          {photo && previewUrl ? (
            <div className="preview" style={{ aspectRatio: `${ratio.w} / ${ratio.h}`, maxWidth: ratio.id === "9:16" ? 360 : 520 }}>
              <img src={previewUrl} alt="Your selected photo" />
              <button className="btn outline small change" onClick={() => input.current?.click()}>
                Change
              </button>
            </div>
          ) : (
            <div
              className={over ? "drop over" : "drop"}
              role="button"
              tabIndex={0}
              onClick={() => input.current?.click()}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setOver(true);
              }}
              onDragLeave={() => setOver(false)}
              onDrop={onDrop}
              data-testid="drop"
            >
              <IconUpload size={36} className="muted" />
              <h3>Add your photo</h3>
              <p className="muted small">A clear, well-lit photo of a face or scene works best.</p>
              <span className="btn small" style={{ marginTop: 6 }}>
                Upload a photo
              </span>
              <p className="muted small">JPG or PNG, up to 10 MB</p>
            </div>
          )}
          <input ref={input} type="file" accept="image/*" hidden onChange={(e) => pick(e.target.files?.[0] ?? undefined)} />

          <div>
            <p className="small muted" style={{ marginBottom: 6, fontWeight: 600 }}>
              Shape
            </p>
            <div className="segmented" role="radiogroup" aria-label="Shape">
              {RATIOS.map((r) => (
                <button key={r.id} role="radio" aria-checked={r.id === ratio.id} className={r.id === ratio.id ? "on" : ""} onClick={() => drafts.setRatio(r)}>
                  {r.label}
                  <small>{r.hint}</small>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="stack">
          <div className="card stack">
            <div className="summary">
              <div className="swatch" style={{ background: style.color, position: "relative", display: "grid", placeItems: "center" }}>
                <StyleArt style={style} />
              </div>
              <div>
                <p className="muted small" style={{ fontWeight: 600, letterSpacing: 0.5 }}>
                  STYLE
                </p>
                <h3>{style.name}</h3>
                <p className="muted small">{creditsLabel(style.credits)} per image</p>
              </div>
            </div>
            {style.description && <p className="muted">{style.description}</p>}
            {token && (
              <div className="spread small">
                <span className="muted">Balance: {creditsLabel(credits)}</span>
                {canAfford && style.credits > 0 && <span className="muted">After this: {creditsLabel(credits - style.credits)}</span>}
              </div>
            )}

            {error && <p className="error">{error}</p>}

            {needsSignIn ? (
              <Link className="btn block" to={`/login?next=/create/${style.slug}`}>
                Sign in to create
              </Link>
            ) : token && !canAfford ? (
              <>
                <p className="notice">You have {creditsLabel(credits)}. Subscribe to get fresh credits every month.</p>
                <Link className="btn block" to="/subscribe">
                  Get credits to create
                </Link>
              </>
            ) : (
              <button className="btn block" disabled={!photo || busy} onClick={generate} data-testid="generate">
                {busy ? <Spinner /> : `Generate · ${creditsLabel(style.credits)}`}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
