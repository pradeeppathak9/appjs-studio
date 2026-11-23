import { useState } from "react";
import { Link } from "react-router";
import { IconImage, IconSearch } from "../components/Icons";
import { Empty, Spinner, StyleArt, StyleCard } from "../components/ui";
import { creditsLabel, greeting, userMessage } from "../lib/format";
import { useStyles } from "../lib/queries";
import { useSession } from "../lib/session";
import { categories, filterStyles } from "../lib/styles";

export function Home() {
  const { token } = useSession();
  const styles = useStyles();
  const [category, setCategory] = useState("All");
  const [query, setQuery] = useState("");

  const all = styles.data ?? [];
  const shown = filterStyles(all, category, query);
  const trending = all.find((s) => s.trending);
  const filtering = category !== "All" || query.trim() !== "";

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div>
        <p className="muted">{greeting()}</p>
        <h1>Pick a style</h1>
      </div>

      <label className="field">
        <IconSearch className="muted" />
        <input
          type="search"
          placeholder="Search styles"
          aria-label="Search styles"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      {all.length > 0 && (
        <div className="pills" role="tablist" aria-label="Categories">
          {categories(all).map((c) => (
            <button key={c} role="tab" aria-selected={c === category} className={c === category ? "on" : ""} onClick={() => setCategory(c)}>
              {c}
            </button>
          ))}
        </div>
      )}

      {styles.isLoading && (
        <div className="row muted">
          <Spinner /> Loading styles…
        </div>
      )}
      {styles.error && (
        <div className="notice error">
          {userMessage(styles.error, !!token)}{" "}
          {!token && (
            <Link to="/login?next=/" style={{ fontWeight: 600 }}>
              Sign in
            </Link>
          )}
        </div>
      )}

      {trending && !filtering && (
        <Link to={`/create/${trending.slug}`} className="hero-card" style={{ background: trending.color }} data-testid="trending">
          <StyleArt style={trending} placeholder={false} />
          <div className="shade" />
          <div className="tags">
            <span className="tag light">Trending</span>
            <span className="tag">{creditsLabel(trending.credits)}</span>
          </div>
          <div className="content">
            <h2 style={{ fontSize: 26, lineHeight: "32px" }}>{trending.name}</h2>
            {trending.description && <p style={{ opacity: 0.9 }}>{trending.description}</p>}
          </div>
        </Link>
      )}

      {all.length > 0 && (
        <>
          <div className="spread">
            <h2>{filtering ? "Results" : "All templates"}</h2>
            <span className="muted small">{shown.length} styles</span>
          </div>
          {shown.length ? (
            <div className="grid">
              {shown.map((s) => (
                <StyleCard key={s.slug} style={s} />
              ))}
            </div>
          ) : (
            <Empty icon={<IconSearch size={40} />} title={`No styles match "${query.trim() || category}"`} />
          )}
        </>
      )}
      {styles.isSuccess && all.length === 0 && (
        <Empty icon={<IconImage size={40} />} title="No styles yet">
          Check back soon.
        </Empty>
      )}
    </div>
  );
}
