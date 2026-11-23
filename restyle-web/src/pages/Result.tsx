import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { IconBack, IconDownload, IconRefresh } from "../components/Icons";
import { Spinner } from "../components/ui";
import { ApiError } from "../lib/api";
import { userMessage } from "../lib/format";
import { keys, useAuthedImage, useJob } from "../lib/queries";

export function Result() {
  const { jobId } = useParams();
  const job = useJob(jobId);
  const qc = useQueryClient();
  const [view, setView] = useState<"result" | "original">("result");
  const j = job.data;
  const done = j?.status === "succeeded" || j?.status === "failed";
  const result = useAuthedImage(j?.status === "succeeded" ? j.assets[0]?.url : null);
  const original = useAuthedImage(j?.inputs[0]?.url);

  // a finished job changed the balance (a failure refunds it) and the creations list
  useEffect(() => {
    if (done) {
      qc.invalidateQueries({ queryKey: keys.me });
      qc.invalidateQueries({ queryKey: keys.jobs });
    }
  }, [done, qc]);

  const title = j?.template?.title ?? "your style";
  const fileName = `restyle-${j?.template?.slug ?? "image"}-${jobId?.slice(0, 8)}.${j?.assets[0]?.mime_type === "image/jpeg" ? "jpg" : "png"}`;

  return (
    <div className="stack narrow" style={{ gap: 20 }}>
      <Link to="/creations" className="row muted" style={{ gap: 4, width: "fit-content" }}>
        <IconBack size={18} /> My creations
      </Link>

      {job.error && <p className="notice error">{userMessage(job.error, true)}</p>}

      {j && !done && (
        <div className="result-frame" style={{ minHeight: 420 }}>
          <div className="stack" style={{ alignItems: "center", textAlign: "center", padding: 24 }}>
            <Spinner big />
            <h2>Applying {title}…</h2>
            <p className="muted">This usually takes a few seconds.</p>
          </div>
        </div>
      )}

      {j?.status === "failed" && (
        <div className="stack">
          <h1>Couldn't make this one</h1>
          <p className="notice error">{userMessage(new ApiError(200, j.error?.code ?? "failed", j.error?.message ?? ""))}</p>
          <Link to="/" className="btn block">
            Try another style
          </Link>
        </div>
      )}

      {j?.status === "succeeded" && (
        <>
          <div className="spread">
            <h1>Your creation</h1>
            {original && (
              <div className="segmented" style={{ width: 220 }}>
                <button className={view === "result" ? "on" : ""} onClick={() => setView("result")}>
                  Result
                </button>
                <button className={view === "original" ? "on" : ""} onClick={() => setView("original")}>
                  Original
                </button>
              </div>
            )}
          </div>
          <div className="result-frame">
            {view === "result" ? (
              result ? <img src={result} alt={`Your photo in ${title}`} data-testid="result-image" /> : <Spinner big />
            ) : (
              original && <img src={original} alt="Your original photo" />
            )}
          </div>
          <p className="muted small">{title}</p>
          <div className="row" style={{ flexWrap: "wrap" }}>
            <a className={result ? "btn" : "btn disabled"} href={result} download={fileName} style={{ flex: 1 }} aria-disabled={!result}>
              <IconDownload /> Download
            </a>
            <Link to="/" className="btn outline" style={{ flex: 1 }}>
              <IconRefresh /> Try another style
            </Link>
          </div>
        </>
      )}

      {!j && job.isLoading && <Spinner />}
    </div>
  );
}
