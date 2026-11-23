import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  adminListAppUsers,
  adminListUsers,
  adminGrantAppUser,
  adminRevokeAppUser,
  adminListApps,
  getToken,
} from "../api";

function AddUserModal({ appUsers, allUsers, onClose, onAdd }) {
  const [userId, setUserId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const existingIds = new Set(appUsers.map((u) => u.user_id));
  const available = allUsers.filter((u) => !existingIds.has(u.id));

  async function handleSubmit(e) {
    e.preventDefault();
    if (!userId) return setError("Select a user");
    setLoading(true);
    setError("");
    try {
      const granted = await onAdd(Number(userId));
      onClose(granted);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={modal.overlay}>
      <div style={modal.box}>
        <h2 style={modal.title}>Grant Access</h2>
        {error && <div style={modal.error}>{error}</div>}
        {available.length === 0 ? (
          <p style={modal.empty}>All users already have access to this app.</p>
        ) : (
          <form onSubmit={handleSubmit} style={modal.form}>
            <label style={modal.label}>Select User *</label>
            <select value={userId} onChange={(e) => setUserId(e.target.value)} style={modal.input} required>
              <option value="">— choose a user —</option>
              {available.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.email}{u.full_name ? ` (${u.full_name})` : ""}
                </option>
              ))}
            </select>

            <div style={modal.actions}>
              <button type="button" onClick={() => onClose(null)} style={modal.cancelBtn}>Cancel</button>
              <button type="submit" disabled={loading} style={modal.grantBtn}>
                {loading ? "Granting..." : "Grant Access"}
              </button>
            </div>
          </form>
        )}
        {available.length === 0 && (
          <div style={modal.actions}>
            <button onClick={() => onClose(null)} style={modal.cancelBtn}>Close</button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function AdminAppUsers() {
  const { appId } = useParams();
  const navigate = useNavigate();
  const [app, setApp] = useState(null);
  const [appUsers, setAppUsers] = useState([]);
  const [allUsers, setAllUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [revokingId, setRevokingId] = useState(null);
  const [confirmRevokeId, setConfirmRevokeId] = useState(null);

  useEffect(() => {
    if (!getToken()) { navigate("/login"); return; }
    Promise.all([adminListApps(), adminListAppUsers(appId), adminListUsers()])
      .then(([apps, users, allU]) => {
        const found = apps.find((a) => a.id === appId);
        setApp(found || null);
        setAppUsers(users);
        setAllUsers(allU);
      })
      .catch(() => navigate("/login"))
      .finally(() => setLoading(false));
  }, [appId, navigate]);

  async function handleRevoke(userId) {
    if (confirmRevokeId !== userId) { setConfirmRevokeId(userId); return; }
    setRevokingId(userId);
    try {
      await adminRevokeAppUser(appId, userId);
      setAppUsers((prev) => prev.filter((u) => u.user_id !== userId));
    } catch (err) {
      alert(err.message);
    } finally {
      setRevokingId(null);
      setConfirmRevokeId(null);
    }
  }

  function handleAddClose(granted) {
    setShowAdd(false);
    if (granted) setAppUsers((prev) => [...prev, granted]);
  }

  if (loading) return <div style={s.loading}>Loading...</div>;
  if (!app) return <div style={s.loading}>App not found.</div>;

  return (
    <div style={s.page}>
      <div style={s.breadcrumb}>
        <button onClick={() => navigate("/admin/apps")} style={s.backBtn}>← Apps</button>
        <span style={s.breadcrumbSep}>/</span>
        <span style={s.breadcrumbCurrent}>{app.name}</span>
      </div>

      <div style={s.header}>
        <div>
          <div style={s.titleRow}>
            <div style={s.appIcon}>{app.name[0].toUpperCase()}</div>
            <h1 style={s.h1}>{app.name}</h1>
            {app.phonepe_enabled && (
              <span style={{ ...s.envBadge, ...(app.phonepe_environment === "PROD" ? s.prodBadge : s.uatBadge) }}>
                PhonePe · {app.phonepe_environment}
              </span>
            )}
            {app.razorpay_enabled && (
              <span style={{ ...s.envBadge, ...(app.razorpay_environment === "LIVE" ? s.prodBadge : s.uatBadge) }}>
                Razorpay · {app.razorpay_environment}
              </span>
            )}
            {!app.enabled && <span style={s.disabledBadge}>Disabled</span>}
          </div>
          <p style={s.sub}>
            {appUsers.length} user{appUsers.length !== 1 ? "s" : ""} with access
          </p>
        </div>
        <button onClick={() => setShowAdd(true)} style={s.addBtn}>+ Add User</button>
      </div>

      <div style={s.tableWrap}>
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>Email</th>
              <th style={s.th}>Full Name</th>
              <th style={s.th}>Role</th>
              <th style={s.th}>Access Granted</th>
              <th style={s.th}></th>
            </tr>
          </thead>
          <tbody>
            {appUsers.map((u) => (
              <tr key={u.user_id} style={s.tr}>
                <td style={s.td}>{u.email}</td>
                <td style={s.td}>{u.full_name || "—"}</td>
                <td style={s.td}>
                  {u.is_admin
                    ? <span style={s.adminBadge}>Admin</span>
                    : <span style={s.userBadge}>User</span>}
                </td>
                <td style={s.td}>{new Date(u.created_at).toLocaleDateString()}</td>
                <td style={{ ...s.td, textAlign: "right" }}>
                  <button
                    onClick={() => handleRevoke(u.user_id)}
                    disabled={revokingId === u.user_id}
                    style={confirmRevokeId === u.user_id ? s.confirmRevokeBtn : s.revokeBtn}
                  >
                    {revokingId === u.user_id
                      ? "..."
                      : confirmRevokeId === u.user_id
                      ? "Confirm?"
                      : "Revoke"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {appUsers.length === 0 && (
          <div style={s.empty}>No users have access yet. Add one above.</div>
        )}
      </div>

      {showAdd && (
        <AddUserModal
          appUsers={appUsers}
          allUsers={allUsers}
          onClose={handleAddClose}
          onAdd={(uid) => adminGrantAppUser(appId, uid)}
        />
      )}
    </div>
  );
}

const s = {
  page: { maxWidth: 900 },
  loading: { padding: 40, textAlign: "center", color: "#64748b" },
  breadcrumb: { display: "flex", alignItems: "center", gap: 8, marginBottom: 24 },
  backBtn: { background: "none", border: "none", color: "#4f46e5", cursor: "pointer", fontSize: 14, padding: 0, fontWeight: 500 },
  breadcrumbSep: { color: "#cbd5e1", fontSize: 14 },
  breadcrumbCurrent: { color: "#1e293b", fontSize: 14, fontWeight: 600 },
  header: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 },
  titleRow: { display: "flex", alignItems: "center", gap: 10, marginBottom: 4 },
  appIcon: { width: 36, height: 36, borderRadius: 8, backgroundColor: "#ede9fe", color: "#4f46e5", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 16, flexShrink: 0 },
  h1: { margin: 0, fontSize: 20, color: "#1e293b" },
  envBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600 },
  uatBadge: { backgroundColor: "#fef9c3", color: "#854d0e" },
  prodBadge: { backgroundColor: "#dcfce7", color: "#166534" },
  disabledBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, backgroundColor: "#fee2e2", color: "#991b1b" },
  sub: { margin: 0, color: "#64748b", fontSize: 13 },
  addBtn: { padding: "10px 20px", backgroundColor: "#1e293b", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 14, whiteSpace: "nowrap" },
  tableWrap: { backgroundColor: "#fff", borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.07)", overflow: "hidden" },
  table: { width: "100%", borderCollapse: "collapse" },
  th: { textAlign: "left", padding: "12px 16px", fontSize: 12, fontWeight: 600, color: "#64748b", borderBottom: "1px solid #f1f5f9", textTransform: "uppercase", letterSpacing: "0.04em" },
  tr: { borderBottom: "1px solid #f8fafc" },
  td: { padding: "12px 16px", fontSize: 14, color: "#1e293b" },
  adminBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, backgroundColor: "#ede9fe", color: "#4f46e5" },
  userBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, backgroundColor: "#f1f5f9", color: "#475569" },
  revokeBtn: { padding: "6px 12px", backgroundColor: "#fff", color: "#ef4444", border: "1px solid #fca5a5", borderRadius: 6, cursor: "pointer", fontSize: 13 },
  confirmRevokeBtn: { padding: "6px 12px", backgroundColor: "#dc2626", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600 },
  empty: { padding: 40, textAlign: "center", color: "#64748b" },
};

const modal = {
  overlay: { position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 },
  box: { backgroundColor: "#fff", borderRadius: 12, padding: 32, width: "100%", maxWidth: 420, maxHeight: "90vh", overflowY: "auto" },
  title: { margin: "0 0 20px", fontSize: 20, color: "#1e293b" },
  form: { display: "flex", flexDirection: "column", gap: 10 },
  label: { fontSize: 13, fontWeight: 600, color: "#374151" },
  input: { padding: "9px 12px", border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 14, width: "100%", boxSizing: "border-box" },
  error: { padding: 10, backgroundColor: "#fee2e2", color: "#dc2626", borderRadius: 6, fontSize: 14 },
  empty: { color: "#64748b", fontSize: 14 },
  actions: { display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 },
  cancelBtn: { padding: "9px 18px", backgroundColor: "#f1f5f9", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14 },
  grantBtn: { padding: "9px 18px", backgroundColor: "#1e293b", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600, fontSize: 14 },
};
