import { useNavigate } from "react-router";
import { JobList } from "../../components/JobList";

export function AppJobsPage() {
  const navigate = useNavigate();
  return <JobList onSelect={(id) => navigate(`/jobs/${id}`)} />;
}
