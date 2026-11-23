import { Link } from "react-router";
import { IconImage } from "../components/Icons";
import { Empty, Spinner } from "../components/ui";
import type { Job } from "../lib/api";
import { userMessage } from "../lib/format";
import { useAuthedImage, useJobs } from "../lib/queries";
import { useSession } from "../lib/session";

function Thumb({ job }: { job: Job }) {
  const url = job.status === "succeeded" ? job.assets[0]?.url : job.inputs[0]?.url;
  const img = useAuthedImage(url);
  const label = { queued: "Waiting…", running: "Applying…", failed: "Didn't work", succeeded: "" }[job.status];
  return (
    <Link to={`/result/${job.id}`} className="thumb" data-testid="creation">
      <div className="img" style={job.status !== "succeeded" ? { opacity: 0.55 } : undefined}>
        {img ? <img src={img} alt="" /> : <Spinner />}
      </div>
      <div className="spread small">
        <span style={{ fontWeight: 600 }}>{job.template?.title ?? "Creation"}</span>
        <span className="muted">{label || new Date(job.created_at).toLocaleDateString()}</span>
      </div>
    </Link>
  );
}

export function Creations() {
  const { token } = useSession();
  const jobs = useJobs();
  return (
    <div className="stack" style={{ gap: 20 }}>
      <h1>My creations</h1>
      {jobs.isLoading && <Spinner />}
      {jobs.error && <p className="notice error">{userMessage(jobs.error, !!token)}</p>}
      {jobs.data && jobs.data.length === 0 && (
        <Empty icon={<IconImage size={40} />} title="Nothing here yet">
          Images you make will show up here. <Link to="/">Pick a style</Link>
        </Empty>
      )}
      {jobs.data && jobs.data.length > 0 && (
        <div className="thumbs">
          {jobs.data.map((j) => (
            <Thumb key={j.id} job={j} />
          ))}
        </div>
      )}
    </div>
  );
}
