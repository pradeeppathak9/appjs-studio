import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  adminListUsers,
  adminCreateUser,
  adminUpdateUser,
  adminDeleteUser,
  adminListUserApps,
  adminGrantAppUser,
  adminRevokeAppUser,
  getToken,
} from "../api";

function generatePassword(length = 14) {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%^&*";
  const bytes = new Uint32Array(length);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => chars[b % chars.length]).join("");
}

function PasswordField({ label, name, value, onChange, placeholder, required }) {
  const [visible, setVisible] = useState(false);
  const [copied, setCopied] = useState(false);

  function handleGenerate() {
    onChange({ target: { name, value: generatePassword() } });
    setVisible(true);
  }

  function handleCopy() {
    navigator.clipboard?.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <>
      <div style={modal.labelRow}>
        <label style={modal.label}>{label}</label>
        <button type="button" onClick={handleGenerate} style={modal.generateBtn}>Generate</button>
      </div>
      <div style={modal.passwordRow}>
        <input
          name={name}
          type={visible ? "text" : "password"}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          style={{ ...modal.input, flex: 1 }}
          required={required}
        />
        <button type="button" onClick={() => setVisible((v) => !v)} style={modal.toggleBtn}>
          {visible ? "Hide" : "Show"}
        </button>
        {value && (
          <button type="button" onClick={handleCopy} style={modal.toggleBtn}>
            {copied ? "✓" : "Copy"}
          </button>
        )}
      </div>
    </>
  );
}

function RoleSelect({ value, onChange, locked }) {
  return (
    <>
      <label style={modal.label}>Role</label>
      <select
        name="is_admin"
        value={value ? "admin" : "user"}
        onChange={(e) => onChange(e.target.value === "admin")}
        disabled={locked}
        style={{ ...modal.input, ...(locked ? modal.inputLocked : null) }}
      >
        <option value="user">User — dashboard access to granted apps only</option>
        <option value="admin">Admin — full access to the admin area</option>
      </select>
      {locked ? (
        <p style={modal.hint}>
          This is the primary admin account and always stays an admin. The server
          rejects the change, so the control is disabled rather than failing on save.
        </p>
      ) : value ? (
        <p style={modal.hint}>
          Admins can manage every app and user. App grants still decide what shows
          on their own dashboard.
        </p>
      ) : null}
    </>
  );
}


function CreateUserModal({ onClose, onCreate }) {
  const [form, setForm] = useState({ email: "", password: "", full_name: "", is_admin: false });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setForm((f) => ({ ...f, [name]: type === "checkbox" ? checked : value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.email.trim() || !form.password.trim()) return setError("Email and password are required");
    setLoading(true);
    setError("");
    try {
      const user = await adminCreateUser(form);
      onCreate(user);
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
        <h2 style={modal.title}>Create New User</h2>
        {error && <div style={modal.error}>{error}</div>}
        <form onSubmit={handleSubmit} style={modal.form}>
          <label style={modal.label}>Email *</label>
          <input name="email" type="email" value={form.email} onChange={handleChange} placeholder="user@company.com" style={modal.input} required />

          <PasswordField
            label="Password *"
            name="password"
            value={form.password}
            onChange={handleChange}
            placeholder="Set a password"
            required
          />

          <label style={modal.label}>Full Name</label>
          <input name="full_name" value={form.full_name} onChange={handleChange} placeholder="Optional" style={modal.input} />

          <RoleSelect
            value={form.is_admin}
            onChange={(v) => setForm((f) => ({ ...f, is_admin: v }))}
          />

          <div style={modal.actions}>
            <button type="button" onClick={onClose} style={modal.cancelBtn}>Cancel</button>
            <button type="submit" disabled={loading} style={modal.createBtn}>
              {loading ? "Creating..." : "Create User"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EditUserModal({ user, onClose, onUpdate }) {
  const [form, setForm] = useState({
    email: user.email,
    full_name: user.full_name || "",
    password: "",
    is_admin: user.is_admin,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function handleChange(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const payload = { email: form.email, full_name: form.full_name };
      if (form.password.trim()) payload.password = form.password;
      // Left out entirely for the protected account so a stray value can never
      // reach the endpoint; the server refuses it regardless.
      if (!user.is_protected) payload.is_admin = form.is_admin;
      const updated = await adminUpdateUser(user.id, payload);
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
        <h2 style={modal.title}>Edit User</h2>
        {error && <div style={modal.error}>{error}</div>}
        <form onSubmit={handleSubmit} style={modal.form}>
          <label style={modal.label}>Email</label>
          <input
            name="email"
            type="email"
            value={form.email}
            onChange={handleChange}
            disabled={user.is_protected}
            style={{ ...modal.input, ...(user.is_protected ? modal.inputLocked : null) }}
            required
          />

          <label style={modal.label}>Full Name</label>
          <input name="full_name" value={form.full_name} onChange={handleChange} style={modal.input} />

          <RoleSelect
            value={form.is_admin}
            onChange={(v) => setForm((f) => ({ ...f, is_admin: v }))}
            locked={user.is_protected}
          />

          <PasswordField
            label="New Password"
            name="password"
            value={form.password}
            onChange={handleChange}
            placeholder="Leave blank to keep current password"
          />

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

function ManageAppsModal({ user, onClose }) {
  const [apps, setApps] = useState(null);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    adminListUserApps(user.id).then(setApps).catch((e) => setError(e.message));
  }, [user.id]);

  async function toggle(app) {
    setSavingId(app.app_id);
    setError("");
    const next = !app.granted;
    try {
      if (next) await adminGrantAppUser(app.app_id, user.id);
      else await adminRevokeAppUser(app.app_id, user.id);
    } catch (e) {
      // Another admin may have made the same change between the list load and
      // this click. The server reports that as a conflict, but the end state is
      // the one we wanted, so treat it as done rather than showing an error for
      // something that is now true.
      const benign = next
        ? /already has access/i.test(e.message)
        : /not found/i.test(e.message);
      if (!benign) {
        setError(e.message);
        setSavingId(null);
        return;
      }
    }
    setApps((prev) =>
      prev.map((a) =>
        a.app_id === app.app_id
          ? { ...a, granted: next, granted_at: next ? new Date().toISOString() : null }
          : a
      )
    );
    setSavingId(null);
  }

  const grantedCount = apps ? apps.filter((a) => a.granted).length : 0;
  const q = filter.trim().toLowerCase();
  const shown = apps
    ? apps.filter((a) => !q || a.name.toLowerCase().includes(q) || a.app_id.toLowerCase().includes(q))
    : [];

  return (
    <div style={modal.overlay}>
      <div style={{ ...modal.box, maxWidth: 560 }}>
        <h2 style={modal.title}>Manage Apps</h2>
        <p style={ma.who}>
          {user.email}
          {user.full_name ? ` · ${user.full_name}` : ""}
        </p>

        {user.is_admin && (
          <div style={ma.note}>
            These grants govern this admin's own dashboard just like any other
            account — unticking one removes it from Your Apps and makes its pages
            404. Administering apps here under Admin → Apps is unaffected.
          </div>
        )}

        {error && <div style={modal.error}>{error}</div>}

        {apps === null ? (
          <p style={ma.muted}>Loading apps…</p>
        ) : apps.length === 0 ? (
          <p style={ma.muted}>No apps exist yet.</p>
        ) : (
          <>
            <div style={ma.toolbar}>
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter apps…"
                style={{ ...modal.input, flex: 1 }}
              />
              <span style={ma.count}>
                {grantedCount} of {apps.length}
              </span>
            </div>

            <div style={ma.list}>
              {shown.map((a) => (
                <label key={a.app_id} style={ma.row}>
                  <input
                    type="checkbox"
                    checked={a.granted}
                    disabled={savingId === a.app_id}
                    onChange={() => toggle(a)}
                    style={{ marginTop: 3 }}
                  />
                  <span style={ma.rowBody}>
                    <span style={ma.rowTop}>
                      <strong style={ma.name}>{a.name}</strong>
                      {a.phonepe_enabled && <span style={{ ...ma.chip, ...ma.pp }}>PhonePe</span>}
                      {a.razorpay_enabled && <span style={{ ...ma.chip, ...ma.rz }}>Razorpay</span>}
                      {!a.enabled && <span style={{ ...ma.chip, ...ma.off }}>Disabled</span>}
                      {savingId === a.app_id && <span style={ma.saving}>saving…</span>}
                    </span>
                    <code style={ma.appId}>{a.app_id}</code>
                  </span>
                </label>
              ))}
              {shown.length === 0 && <p style={ma.muted}>No app matches “{filter}”.</p>}
            </div>
          </>
        )}

        <div style={modal.actions}>
          {/* Every toggle already saved on its own, so there is nothing to
              commit here — the count goes back so the table cell stays true. */}
          <button type="button" onClick={() => onClose(apps ? grantedCount : null)} style={modal.createBtn}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}


export default function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [managingApps, setManagingApps] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!getToken()) { navigate("/login"); return; }
    adminListUsers()
      .then(setUsers)
      .catch(() => navigate("/login"))
      .finally(() => setLoading(false));
  }, [navigate]);

  async function handleDelete(userId) {
    if (confirmDeleteId !== userId) { setConfirmDeleteId(userId); return; }
    setDeletingId(userId);
    try {
      await adminDeleteUser(userId);
      setUsers((prev) => prev.filter((u) => u.id !== userId));
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
          <h1 style={s.h1}>Users</h1>
          <p style={s.sub}>Manage internal &amp; customer accounts. Role decides admin-area access; app grants decide what a user sees on their own dashboard.</p>
        </div>
        <button onClick={() => setShowCreate(true)} style={s.createBtn}>+ New User</button>
      </div>

      <div style={s.tableWrap}>
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>Email</th>
              <th style={s.th}>Full Name</th>
              <th style={s.th}>Role</th>
              <th style={s.th}>Apps</th>
              <th style={s.th}>Created</th>
              <th style={s.th}></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} style={s.tr}>
                <td style={s.td}>{u.email}</td>
                <td style={s.td}>{u.full_name || "—"}</td>
                <td style={s.td}>
                  {u.is_admin ? <span style={s.adminBadge}>Admin</span> : <span style={s.userBadge}>User</span>}
                </td>
                <td style={s.td}>{u.apps_count}</td>
                <td style={s.td}>{new Date(u.created_at).toLocaleDateString()}</td>
                <td style={{ ...s.td, textAlign: "right" }}>
                  <div style={s.rowActions}>
                    <button onClick={() => setManagingApps(u)} style={s.editBtn}>Manage Apps</button>
                    <button onClick={() => setEditingUser(u)} style={s.editBtn}>Edit</button>
                    <button
                      onClick={() => handleDelete(u.id)}
                      disabled={deletingId === u.id}
                      style={confirmDeleteId === u.id ? s.confirmDeleteBtn : s.deleteBtn}
                    >
                      {deletingId === u.id ? "..." : confirmDeleteId === u.id ? "Confirm?" : "Delete"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && <div style={s.empty}>No users yet.</div>}
      </div>

      {showCreate && (
        <CreateUserModal
          onClose={() => setShowCreate(false)}
          onCreate={(u) => setUsers((prev) => [u, ...prev])}
        />
      )}
      {managingApps && (
        <ManageAppsModal
          user={managingApps}
          onClose={(count) => {
            if (count !== null) {
              setUsers((prev) =>
                prev.map((u) => (u.id === managingApps.id ? { ...u, apps_count: count } : u))
              );
            }
            setManagingApps(null);
          }}
        />
      )}

      {editingUser && (
        <EditUserModal
          user={editingUser}
          onClose={() => setEditingUser(null)}
          onUpdate={(updated) => setUsers((prev) => prev.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)))}
        />
      )}
    </div>
  );
}

const s = {
  page: { maxWidth: 1000 },
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
  adminBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, backgroundColor: "#ede9fe", color: "#4f46e5" },
  userBadge: { padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, backgroundColor: "#f1f5f9", color: "#475569" },
  rowActions: { display: "flex", gap: 8, justifyContent: "flex-end" },
  editBtn: { padding: "6px 12px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 6, cursor: "pointer", fontSize: 13 },
  deleteBtn: { padding: "6px 12px", backgroundColor: "#fff", color: "#ef4444", border: "1px solid #fca5a5", borderRadius: 6, cursor: "pointer", fontSize: 13 },
  confirmDeleteBtn: { padding: "6px 12px", backgroundColor: "#dc2626", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 13, fontWeight: 600 },
  empty: { padding: 40, textAlign: "center", color: "#64748b" },
};

const ma = {
  who: { margin: "-12px 0 16px", fontSize: 13, color: "#64748b" },
  note: { padding: "8px 12px", backgroundColor: "#fffbeb", border: "1px solid #fde68a", borderRadius: 6, fontSize: 12, color: "#92400e", marginBottom: 14, lineHeight: 1.5 },
  muted: { fontSize: 13, color: "#64748b", margin: "12px 0" },
  toolbar: { display: "flex", alignItems: "center", gap: 10, marginBottom: 10 },
  count: { fontSize: 12, color: "#64748b", whiteSpace: "nowrap" },
  list: { maxHeight: 340, overflowY: "auto", border: "1px solid #f1f5f9", borderRadius: 8 },
  row: { display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 12px", borderBottom: "1px solid #f8fafc", cursor: "pointer" },
  rowBody: { display: "flex", flexDirection: "column", gap: 3, minWidth: 0 },
  rowTop: { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" },
  name: { fontSize: 14, color: "#1e293b", fontWeight: 600 },
  appId: { fontSize: 11, color: "#94a3b8", wordBreak: "break-all" },
  chip: { padding: "1px 7px", borderRadius: 20, fontSize: 10, fontWeight: 600 },
  pp: { backgroundColor: "#ede9fe", color: "#4f46e5" },
  rz: { backgroundColor: "#dcfce7", color: "#166534" },
  off: { backgroundColor: "#fee2e2", color: "#991b1b" },
  saving: { fontSize: 11, color: "#94a3b8" },
};

const modal = {
  overlay: { position: "fixed", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 },
  box: { backgroundColor: "#fff", borderRadius: 12, padding: 32, width: "100%", maxWidth: 440, maxHeight: "90vh", overflowY: "auto" },
  title: { margin: "0 0 20px", fontSize: 20, color: "#1e293b" },
  form: { display: "flex", flexDirection: "column", gap: 10 },
  label: { fontSize: 13, fontWeight: 600, color: "#374151" },
  input: { padding: "9px 12px", border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 14, width: "100%", boxSizing: "border-box" },
  labelRow: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  generateBtn: { padding: "3px 10px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 6, cursor: "pointer", fontSize: 12, color: "#374151" },
  passwordRow: { display: "flex", gap: 6 },
  toggleBtn: { padding: "9px 12px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 6, cursor: "pointer", fontSize: 13, whiteSpace: "nowrap" },
  checkboxRow: { display: "flex", alignItems: "center", gap: 8, fontSize: 14, color: "#374151" },
  inputLocked: { backgroundColor: "#f8fafc", color: "#94a3b8", cursor: "not-allowed" },
  hint: { margin: "-4px 0 2px", fontSize: 12, color: "#64748b", lineHeight: 1.5 },
  error: { padding: 10, backgroundColor: "#fee2e2", color: "#dc2626", borderRadius: 6, fontSize: 14 },
  actions: { display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 },
  cancelBtn: { padding: "9px 18px", backgroundColor: "#f1f5f9", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14 },
  createBtn: { padding: "9px 18px", backgroundColor: "#1e293b", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600, fontSize: 14 },
};
