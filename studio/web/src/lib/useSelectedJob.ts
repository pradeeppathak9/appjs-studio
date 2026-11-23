import { useSearchParams } from "react-router";

/** Selected job id lives in `?job=` so a page can be reloaded or linked. */
export function useSelectedJob(): [string | undefined, (id: string) => void] {
  const [params, setParams] = useSearchParams();
  const select = (id: string) =>
    setParams(
      (p) => {
        p.set("job", id);
        return p;
      },
      { replace: true },
    );
  return [params.get("job") ?? undefined, select];
}
