import React, { useEffect, useState, useCallback } from "react";
import { adminRedisKeys, adminRedisKey, adminRedisDeleteKey } from "../api";

const TYPE_COLORS = {
  string: { bg: "#eff6ff", color: "#1d4ed8" },
  hash:   { bg: "#fdf4ff", color: "#7e22ce" },
  list:   { bg: "#fff7ed", color: "#c2410c" },
  set:    { bg: "#f0fdf4", color: "#166534" },
  zset:   { bg: "#fefce8", color: "#854d0e" },
};

function ttlLabel(ttl) {
  if (ttl === -1) return "no expiry";
  if (ttl === -2) return "expired";
  if (ttl < 60)  return `${ttl}s`;
  if (ttl < 3600) return `${Math.floor(ttl / 60)}m ${ttl % 60}s`;
  return `${Math.floor(ttl / 3600)}h ${Math.floor((ttl % 3600) / 60)}m`;
}

function ValuePane({ keyName, onDeleted }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const [deleting, setDeleting] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);

  useEffect(() => {
    setState({ loading: true, data: null, error: null });
    adminRedisKey(keyName)
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((err) => setState({ loading: false, data: null, error: err.message }));
  }, [keyName]);

  async function handleDelete() {
    if (!confirmDel) { setConfirmDel(true); return; }
    setDeleting(true);
    try {
      await adminRedisDeleteKey(keyName);
      onDeleted(keyName);
    } catch (err) {
      alert(err.message);
      setDeleting(false);
      setConfirmDel(false);
    }
  }

  return (
    <div style={vp.wrap}>
      <div style={vp.toolbar}>
        <span style={vp.keyLabel}>{keyName}</span>
        <div style={vp.actions}>
          <button
            onClick={() => setConfirmDel(false) || handleDelete()}
            disabled={deleting || state.loading}
            style={confirmDel ? vp.confirmBtn : vp.deleteBtn}
          >
            {deleting ? "Deleting…" : confirmDel ? "Confirm delete?" : "Delete key"}
          </button>
          {confirmDel && (
            <button onClick={() => setConfirmDel(false)} style={vp.cancelBtn}>Cancel</button>
          )}
        </div>
      </div>

      {state.loading && <div style={vp.msg}>Loading…</div>}
      {state.error  && <div style={{ ...vp.msg, color: "#dc2626" }}>{state.error}</div>}
      {state.data && (
        <div style={vp.meta}>
          <span style={{ ...vp.typeBadge, ...TYPE_COLORS[state.data.type] }}>{state.data.type}</span>
          <span style={vp.ttl}>TTL: {ttlLabel(state.data.ttl)}</span>
        </div>
      )}
      {state.data && (
        <pre style={vp.pre}>{JSON.stringify(state.data.value, null, 2)}</pre>
      )}
    </div>
  );
}

export default function AdminRedis() {
  const [keys, setKeys]             = useState([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(null);
  const [selected, setSelected]     = useState(null);
  const [filter, setFilter]         = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    adminRedisKeys()
      .then(({ keys: ks }) => { setKeys(ks); setLoading(false); })
      .catch((err) => { setError(err.message); setLoading(false); });
  }, []);

  useEffect(() => { load(); }, [load]);

  function handleDeleted(key) {
    setKeys((prev) => prev.filter((k) => k.key !== key));
    if (selected === key) setSelected(null);
  }

  const filtered = filter
    ? keys.filter((k) => k.key.toLowerCase().includes(filter.toLowerCase()))
    : keys;

  return (
    <div style={s.page}>
      <div style={s.header}>
        <div>
          <h1 style={s.h1}>Redis Cache</h1>
          <p style={s.sub}>{keys.length} key{keys.length !== 1 ? "s" : ""} in store</p>
        </div>
        <button onClick={load} disabled={loading} style={s.refreshBtn}>
          {loading ? "Loading…" : "↻ Refresh"}
        </button>
      </div>

      {error && <div style={s.error}>{error}</div>}

      <div style={s.layout}>
        {/* Key list */}
        <div style={s.listCol}>
          <input
            style={s.search}
            placeholder="Filter keys…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <div style={s.tableWrap}>
            {loading && !keys.length ? (
              <div style={s.empty}>Loading…</div>
            ) : filtered.length === 0 ? (
              <div style={s.empty}>{filter ? "No matching keys." : "No keys in Redis."}</div>
            ) : (
              <table style={s.table}>
                <thead>
                  <tr>
                    <th style={s.th}>Key</th>
                    <th style={{ ...s.th, width: 64 }}>Type</th>
                    <th style={{ ...s.th, width: 80, textAlign: "right" }}>TTL</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((k) => (
                    <tr
                      key={k.key}
                      onClick={() => setSelected(selected === k.key ? null : k.key)}
                      style={{
                        ...s.tr,
                        ...(selected === k.key ? s.trActive : {}),
                      }}
                    >
                      <td style={s.td}>
                        <span style={s.keyName}>{k.key}</span>
                      </td>
                      <td style={s.td}>
                        <span style={{ ...s.typeBadge, ...TYPE_COLORS[k.type] }}>{k.type}</span>
                      </td>
                      <td style={{ ...s.td, textAlign: "right", color: "#94a3b8", fontSize: 12 }}>
                        {ttlLabel(k.ttl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Value pane */}
        <div style={s.valueCol}>
          {selected ? (
            <ValuePane key={selected} keyName={selected} onDeleted={handleDeleted} />
          ) : (
            <div style={s.placeholder}>
              <div style={s.placeholderIcon}>⬡</div>
              <p style={s.placeholderText}>Select a key to inspect its value</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const s = {
  page: { maxWidth: 1200 },
  header: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 },
  h1: { margin: "0 0 4px", fontSize: 22, color: "#1e293b", fontWeight: 700 },
  sub: { margin: 0, color: "#64748b", fontSize: 13 },
  refreshBtn: { padding: "9px 18px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 500, color: "#1e293b" },
  error: { padding: "10px 14px", backgroundColor: "#fee2e2", color: "#dc2626", borderRadius: 8, fontSize: 13, marginBottom: 16 },
  layout: { display: "flex", gap: 20, alignItems: "flex-start" },
  listCol: { flex: "0 0 44%", minWidth: 0 },
  valueCol: { flex: 1, minWidth: 0 },
  search: { width: "100%", padding: "9px 12px", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 14, boxSizing: "border-box", marginBottom: 10, outline: "none", fontFamily: "inherit" },
  tableWrap: { backgroundColor: "#fff", borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.07)", overflow: "hidden" },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { textAlign: "left", padding: "10px 14px", fontSize: 11, fontWeight: 600, color: "#64748b", borderBottom: "1px solid #f1f5f9", textTransform: "uppercase", letterSpacing: "0.04em" },
  tr: { borderBottom: "1px solid #f8fafc", cursor: "pointer", transition: "background 0.1s" },
  trActive: { backgroundColor: "#f0f9ff" },
  td: { padding: "10px 14px", fontSize: 13, color: "#1e293b", verticalAlign: "middle" },
  keyName: { fontFamily: "'Fira Code', 'Cascadia Code', monospace", fontSize: 12, wordBreak: "break-all" },
  typeBadge: { padding: "2px 7px", borderRadius: 20, fontSize: 11, fontWeight: 600 },
  empty: { padding: 40, textAlign: "center", color: "#94a3b8", fontSize: 13 },
  placeholder: { backgroundColor: "#fff", borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.07)", padding: "80px 32px", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 },
  placeholderIcon: { fontSize: 36, color: "#cbd5e1" },
  placeholderText: { margin: 0, color: "#94a3b8", fontSize: 14 },
};

const vp = {
  wrap: { backgroundColor: "#fff", borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.07)", overflow: "hidden" },
  toolbar: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 16px", borderBottom: "1px solid #f1f5f9", gap: 10 },
  keyLabel: { fontFamily: "'Fira Code', 'Cascadia Code', monospace", fontSize: 12, color: "#1e293b", wordBreak: "break-all", flex: 1 },
  actions: { display: "flex", gap: 8, flexShrink: 0 },
  deleteBtn: { padding: "6px 12px", backgroundColor: "#fff", color: "#ef4444", border: "1px solid #fca5a5", borderRadius: 6, cursor: "pointer", fontSize: 12 },
  confirmBtn: { padding: "6px 12px", backgroundColor: "#dc2626", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 600 },
  cancelBtn: { padding: "6px 12px", backgroundColor: "#f1f5f9", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12 },
  meta: { display: "flex", alignItems: "center", gap: 10, padding: "10px 16px", borderBottom: "1px solid #f1f5f9", backgroundColor: "#f8fafc" },
  typeBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600 },
  ttl: { fontSize: 12, color: "#64748b" },
  pre: { margin: 0, padding: "16px", fontSize: 12.5, lineHeight: 1.65, color: "#1e293b", overflowX: "auto", fontFamily: "'Fira Code', 'Cascadia Code', 'Consolas', monospace", whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: "calc(100vh - 260px)", overflowY: "auto" },
  msg: { padding: "20px 16px", fontSize: 13, color: "#64748b" },
};
