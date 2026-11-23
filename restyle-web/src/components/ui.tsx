import type { ReactNode } from "react";
import { Link } from "react-router";
import { useAuthedImage } from "../lib/queries";
import type { Style } from "../lib/styles";
import { creditsLabel } from "../lib/format";
import { IconImage, IconSparkle } from "./Icons";

export function Spinner({ big }: { big?: boolean }) {
  return <div className={big ? "spinner big" : "spinner"} role="status" aria-label="Loading" />;
}

/** A style's picture: its cover from the server, else the design's colour (with an image icon on
 * cards; the big trending card shows the colour alone). */
export function StyleArt({ style, placeholder = true }: { style: Style; placeholder?: boolean }) {
  const cover = useAuthedImage(style.coverUrl);
  if (cover) return <img className="art" src={cover} alt="" />;
  return placeholder ? <IconImage className="placeholder-icon" strokeWidth={1.4} /> : null;
}

export function StyleCard({ style }: { style: Style }) {
  return (
    <Link to={`/create/${style.slug}`} className="style-card" data-testid="style-card">
      <div className="tile" style={{ background: style.color }}>
        <StyleArt style={style} />
        {style.isNew && <span className="tag light new">New</span>}
        <span className="tag">
          <IconSparkle size={12} style={{ marginRight: 4 }} />
          {creditsLabel(style.credits)}
        </span>
      </div>
      <div>
        <h3>{style.name}</h3>
        <p className="muted small">{style.meta}</p>
      </div>
    </Link>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      {icon}
      <h3>{title}</h3>
      {children && <p className="muted">{children}</p>}
    </div>
  );
}
