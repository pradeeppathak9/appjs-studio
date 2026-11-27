import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminListApps, adminListUsers, adminCreateApp, adminUpdateApp, adminDeleteApp, getToken, adminListAppUsers, useServerGateways } from "../api";

const SLUG_RE = /^[a-z0-9](?:[a-z0-9-]{1,62}[a-z0-9])$/;

function slugify(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64).replace(/-+$/, "");
}

function CreateAppModal({ users, onClose, onCreate }) {
  const gateways = useServerGateways();
  const [form, setForm] = useState({
    user_id: users[0]?.id || "",
    name: "",
    slug: "",
    phonepe_enabled: true,
    razorpay_enabled: false,
  });
  // A server running only some gateways (AUTOREV_GATEWAYS) offers only those.
  useEffect(() => {
    setForm((f) => ({
      ...f,
      phonepe_enabled: gateways.includes("phonepe") && f.phonepe_enabled,
      razorpay_enabled: gateways.includes("razorpay") && (f.razorpay_enabled || !gateways.includes("phonepe")),
    }));
  }, [gateways]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // The slug follows the name until it is edited by hand (like AppJs Studio).
  const [slugTouched, setSlugTouched] = useState(false);

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    if (name === "slug") setSlugTouched(true);
    setForm((f) => {
      const next = { ...f, [name]: type === "checkbox" ? checked : value };
      if (name === "name" && !slugTouched) next.slug = slugify(value);
      return next;
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.name.trim()) return setError("App name is required");
    if (!SLUG_RE.test(form.slug)) return setError("Slug: 3-64 lower-case letters, digits and dashes; no dash at the ends");
    if (!form.user_id) return setError("Select an owner");
    if (!form.phonepe_enabled && !form.razorpay_enabled) return setError("Enable at least one payment gateway");
    setLoading(true);
    setError("");
    try {
      const app = await adminCreateApp({ ...form, user_id: Number(form.user_id) });
      onCreate(app);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={modal.overlay}>
      <div style={modal.box}>
        <h2 style={modal.title}>Create New App</h2>
        {error && <div style={modal.error}>{error}</div>}
        <form onSubmit={handleSubmit} style={modal.form}>
          <label style={modal.label}>Owner *</label>
          <select name="user_id" value={form.user_id} onChange={handleChange} style={modal.input} required>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.email}</option>
            ))}
          </select>

          <label style={modal.label}>App Name *</label>
          <input name="name" value={form.name} onChange={handleChange} placeholder="e.g. MarktMakrs" style={modal.input} required />

          <label style={modal.label}>Slug *</label>
          <input name="slug" value={form.slug} onChange={handleChange} placeholder="e.g. marktmakrs" style={modal.input} required />
          <p style={modal.hint}>Lower-case letters, digits and dashes. Fixed once the app is created.</p>

          <label style={modal.label}>Payment Gateways</label>
          {gateways.includes("phonepe") && (
            <label style={modal.checkboxRow}>
              <input type="checkbox" name="phonepe_enabled" checked={form.phonepe_enabled} onChange={handleChange} />
              PhonePe
            </label>
          )}
          {gateways.includes("razorpay") && (
            <label style={modal.checkboxRow}>
              <input type="checkbox" name="razorpay_enabled" checked={form.razorpay_enabled} onChange={handleChange} />
              Razorpay
            </label>
          )}
          <p style={modal.hint}>Credentials and environment are configured by the app owner on the app's Settings page.</p>

          <div style={modal.actions}>
            <button type="button" onClick={onClose} style={modal.cancelBtn}>Cancel</button>
            <button type="submit" disabled={loading} style={modal.createBtn}>
              {loading ? "Creating..." : "Create App"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EditAppModal({ app, onClose, onUpdate }) {
  const gateways = useServerGateways();
  const [enabled, setEnabled] = useState(app.enabled);
  const [phonepeEnabled, setPhonepeEnabled] = useState(app.phonepe_enabled);
  const [razorpayEnabled, setRazorpayEnabled] = useState(app.razorpay_enabled);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (!phonepeEnabled && !razorpayEnabled) return setError("Enable at least one payment gateway");
    setLoading(true);
    setError("");
    try {
      const updated = await adminUpdateApp(app.id, {
        enabled,
        phonepe_enabled: phonepeEnabled,
        razorpay_enabled: razorpayEnabled,
      });
      onUpdate(updated);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={modal.overlay}>
      <div style={modal.box}>
        <h2 style={modal.title}>Edit App</h2>
        <p style={modal.ownerLine}>{app.name} ({app.slug}) — Owner: {app.owner_email}</p>
        {error && <div style={modal.error}>{error}</div>}
        <form onSubmit={handleSubmit} style={modal.form}>
          <label style={modal.checkboxRow}>
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            App enabled
          </label>

          <label style={modal.label}>Payment Gateways</label>
          {(gateways.includes("phonepe") || phonepeEnabled) && (
            <label style={modal.checkboxRow}>
              <input type="checkbox" checked={phonepeEnabled} onChange={(e) => setPhonepeEnabled(e.target.checked)} />
              PhonePe{!gateways.includes("phonepe") && " (not offered on this server)"}
            </label>
          )}
          {(gateways.includes("razorpay") || razorpayEnabled) && (
            <label style={modal.checkboxRow}>
              <input type="checkbox" checked={razorpayEnabled} onChange={(e) => setRazorpayEnabled(e.target.checked)} />
              Razorpay{!gateways.includes("razorpay") && " (not offered on this server)"}
            </label>
          )}

          <div style={modal.actions}>
            <button type="button" onClick={onClose} style={modal.cancelBtn}>Cancel</button>
            <button type="submit" disabled={loading} style={modal.createBtn}>
              {loading ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function AdminApps() {
  const [apps, setApps] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingApp, setEditingApp] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!getToken()) { navigate("/login"); return; }
    Promise.all([adminListApps(), adminListUsers()])
      .then(([a, u]) => { setApps(a); setUsers(u); })
      .catch(() => navigate("/login"))
      .finally(() => setLoading(false));
  }, [navigate]);

  async function handleDelete(appId) {
    if (confirmDeleteId !== appId) { setConfirmDeleteId(appId); return; }
    setDeletingId(appId);
    try {
      await adminDeleteApp(appId);
      setApps((prev) => prev.filter((a) => a.id !== appId));
    } catch (err) {
      alert(err.message);
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  }

  if (loading) return <div style={s.loading}>Loading...</div>;

  return (
    <div style={s.page}>
      <div style={s.header}>
        <div>
          <h1 style={s.h1}>Apps</h1>
          <p style={s.sub}>Create, enable/disable, or remove apps on behalf of any user.</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          style={s.createBtn}
          disabled={users.length === 0}
          title={users.length === 0 ? "Create a user first" : undefined}
        >
          + New App
        </button>
      </div>

      <div style={s.tableWrap}>
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>Name</th>
              <th style={s.th}>Slug</th>
              <th style={s.th}>Owner</th>
              <th style={s.th}>Env</th>
              <th style={s.th}>Status</th>
              <th style={s.th}>Trial</th>
              <th style={s.th}>Created</th>
              <th style={s.th}></th>
            </tr>
          </thead>
          <tbody>
            {apps.map((a) => (
              <tr key={a.id} style={s.tr}>
                <td style={s.td}>{a.name}</td>
                <td style={s.td}><code>{a.slug}</code></td>
                <td style={s.td}>{a.owner_email}</td>
                <td style={s.td}>
                  <div style={s.envStack}>
                    {a.phonepe_enabled && (
                      <span style={{ ...s.envBadge, ...(a.phonepe_environment === "PROD" ? s.prodBadge : s.uatBadge) }}>
                        PhonePe · {a.phonepe_environment}
                      </span>
                    )}
                    {a.razorpay_enabled && (
                      <span style={{ ...s.envBadge, ...(a.razorpay_environment === "LIVE" ? s.prodBadge : s.uatBadge) }}>
                        Razorpay · {a.razorpay_environment}
                      </span>
                    )}
                  </div>
                </td>
                <td style={s.td}>
                  {a.enabled ? <span style={s.enabledBadge}>Enabled</span> : <span style={s.disabledBadge}>Disabled</span>}
                </td>
                <td style={s.td}>{a.trial_enabled ? "✓" : "—"}</td>
                <td style={s.td}>{new Date(a.created_at).toLocaleDateString()}</td>
                <td style={{ ...s.td, textAlign: "right" }}>
                  <div style={s.rowActions}>
                    <button onClick={() => navigate(`/admin/apps/${a.id}`)} style={s.usersBtn}>Manage Users</button>
                    <button onClick={() => setEditingApp(a)} style={s.editBtn}>Edit</button>
                    <button
                      onClick={() => handleDelete(a.id)}
                      disabled={deletingId === a.id}
                      style={confirmDeleteId === a.id ? s.confirmDeleteBtn : s.deleteBtn}
                    >
                      {deletingId === a.id ? "..." : confirmDeleteId === a.id ? "Confirm?" : "Delete"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {apps.length === 0 && <div style={s.empty}>No apps yet.</div>}
      </div>

      {showCreate && (
        <CreateAppModal
          users={users}
          onClose={() => setShowCreate(false)}
          onCreate={(app) => setApps((prev) => [app, ...prev])}
        />
      )}
      {editingApp && (
        <EditAppModal
          app={editingApp}
          onClose={() => setEditingApp(null)}
          onUpdate={(updated) => setApps((prev) => prev.map((a) => (a.id === updated.id ? updated : a)))}
        />
      )}
    </div>
  );
}

const s = {
  page: { maxWidth: 1100 },
  loading: { padding: 40, textAlign: "center", color: "#64748b" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 },
  h1: { margin: "0 0 4px", fontSize: 22, color: "#1e293b" },
  sub: { margin: 0, color: "#64748b", fontSize: 13, maxWidth: 520 },
  createBtn: { padding: "10px 20px", backgroundColor: "#1e293b", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 14, whiteSpace: "nowrap" },
  tableWrap: { backgroundColor: "#fff", borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.07)", overflow: "hidden" },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { textAlign: "left", padding: "12px 16px", fontSize: 12, fontWeight: 600, color: "#64748b", borderBottom: "1px solid #f1f5f9", textTransform: "uppercase", letterSpacing: "0.04em" },
  tr: { borderBottom: "1px solid #f8fafc" },
  td: { padding: "12px 16px", fontSize: 14, color: "#1e293b" },
  envStack: { display: "flex", flexDirection: "column", gap: 4 },
  envBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, whiteSpace: "nowrap", display: "inline-block" },
  uatBadge: { backgroundColor: "#fef9c3", color: "#854d0e" },
  prodBadge: { backgroundColor: "#dcfce7", color: "#166534" },
  enabledBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, backgroundColor: "#dcfce7", color: "#166534" },
  disabledBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, backgroundColor: "#fee2e2", color: "#991b1b" },
  rowActions: { display: "flex", gap: 8, justifyContent: "flex-end" },
  usersBtn: { padding: "6px 12px", backgroundColor: "#ede9fe", color: "#4f46e5", border: "1px solid #ddd6fe", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 500 },
  editBtn: { padding: "6px 12px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 6, cursor: "pointer", fontSize: 13 },
  deleteBtn: { padding: "6px 12px", backgroundColor: "#fff", color: "#ef4444", border: "1px solid #fca5a5", borderRadius: 6, cursor: "pointer", fontSize: 13 },
  confirmDeleteBtn: { padding: "6px 12px", backgroundColor: "#dc2626", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600 },
  empty: { padding: 40, textAlign: "center", color: "#64748b" },
};

const modal = {
  overlay: { position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 },
  box: { backgroundColor: "#fff", borderRadius: 12, padding: 32, width: "100%", maxWidth: 480, maxHeight: "90vh", overflowY: "auto" },
  title: { margin: "0 0 6px", fontSize: 20, color: "#1e293b" },
  ownerLine: { margin: "0 0 20px", fontSize: 13, color: "#64748b" },
  form: { display: "flex", flexDirection: "column", gap: 10 },
  label: { fontSize: 13, fontWeight: 600, color: "#374151" },
  input: { padding: "9px 12px", border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 14, width: "100%", boxSizing: "border-box" },
  divider: { fontSize: 13, fontWeight: 600, color: "#1e293b", borderTop: "1px solid #f1f5f9", paddingTop: 12, marginTop: 4 },
  optional: { fontWeight: 400, color: "#94a3b8" },
  hint: { margin: "2px 0 0", fontSize: 12, color: "#94a3b8" },
  checkboxRow: { display: "flex", alignItems: "center", gap: 8, fontSize: 14, color: "#374151" },
  error: { padding: 10, backgroundColor: "#fee2e2", color: "#dc2626", borderRadius: 6, fontSize: 14 },
  actions: { display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 },
  cancelBtn: { padding: "9px 18px", backgroundColor: "#f1f5f9", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14 },
  createBtn: { padding: "9px 18px", backgroundColor: "#1e293b", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600, fontSize: 14 },
};
