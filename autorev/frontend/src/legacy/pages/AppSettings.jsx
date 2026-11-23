import React, { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { updateApp, resetApiKey, testPhonePe, testRazorpay } from "../api";
import WebhooksSection from "../components/WebhooksSection";

function copyToClipboard(text) {
  if (navigator.clipboard) {
    return navigator.clipboard.writeText(text);
  }
  // HTTP fallback
  const el = document.createElement("textarea");
  el.value = text;
  el.style.position = "fixed";
  el.style.opacity = "0";
  document.body.appendChild(el);
  el.select();
  document.execCommand("copy");
  document.body.removeChild(el);
  return Promise.resolve();
}

function CopyAppId({ appId }) {
  const [copied, setCopied] = useState(false);
  function handleCopy() {
    copyToClipboard(appId);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <button onClick={handleCopy} style={ak.copyBtn}>
      {copied ? "✓ Copied" : "Copy"}
    </button>
  );
}

function ApiKeySection({ app, setApp }) {
  const [visible, setVisible] = useState(false);
  const [copied, setCopied] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);

  function handleCopy() {
    copyToClipboard(app.api_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  async function handleReset() {
    if (!confirmReset) { setConfirmReset(true); return; }
    setResetting(true);
    try {
      const updated = await resetApiKey(app.id);
      setApp(updated);
      setVisible(true);
      setConfirmReset(false);
    } finally {
      setResetting(false);
    }
  }

  const masked = app.api_key.slice(0, 8) + "•".repeat(24) + app.api_key.slice(-8);

  return (
    <section style={s.section}>
      <h2 style={s.sectionTitle}>App Credentials</h2>
      <p style={s.sectionDesc}>
        Include the API key as <code style={s.inlineCode}>Authorization: Bearer &lt;key&gt;</code> in every API request.
      </p>

      <div style={ak.row}>
        <div style={ak.fieldLabel}>App ID</div>
        <div style={ak.keyBox}>
          <code style={ak.keyValue}>{app.id}</code>
          <CopyAppId appId={app.id} />
        </div>
      </div>

      <div style={{ ...ak.row, marginTop: 12 }}>
        <div style={ak.fieldLabel}>API Key</div>
        <div style={ak.keyBox}>
          <code style={ak.keyValue}>{visible ? app.api_key : masked}</code>
          <button onClick={() => setVisible((v) => !v)} style={ak.iconBtn}>
            {visible ? "Hide" : "Reveal"}
          </button>
          <button onClick={handleCopy} style={ak.copyBtn}>
            {copied ? "✓ Copied" : "Copy"}
          </button>
        </div>
      </div>

      <div style={ak.resetRow}>
        {confirmReset && (
          <span style={ak.warn}>
            This will invalidate the current key. All existing integrations will break.
          </span>
        )}
        <button
          onClick={confirmReset ? () => setConfirmReset(false) : undefined}
          style={confirmReset ? ak.cancelBtn : { display: "none" }}
        >
          Cancel
        </button>
        <button onClick={handleReset} disabled={resetting} style={confirmReset ? ak.confirmBtn : ak.resetBtn}>
          {resetting ? "Resetting..." : confirmReset ? "Yes, reset key" : "Reset Key"}
        </button>
      </div>
    </section>
  );
}

function PhonePeSection({ app, form, handleChange, showSecret, setShowSecret }) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(await testPhonePe(app.id));
    } catch (err) {
      setTestResult({ success: false, error: err.message });
    } finally {
      setTesting(false);
    }
  }

  return (
    <section style={s.section}>
      <div style={s.sectionHeader}>
        <div>
          <h2 style={s.sectionTitle}>PhonePe Credentials</h2>
          <p style={s.sectionDesc}>Used to authenticate with the PhonePe payment gateway.</p>
        </div>
        <button
          type="button"
          onClick={handleTest}
          disabled={testing || !app.phonepe_client_id}
          style={testing ? s.testingBtn : s.testBtn}
          title={!app.phonepe_client_id ? "Save credentials first" : "Test saved credentials"}
        >
          {testing ? "Testing…" : "Test Connection"}
        </button>
      </div>

      {testResult && (
        <div style={testResult.success ? s.testSuccess : testResult.stage === "api_access" ? s.testWarn : s.testError}>
          {testResult.success
            ? `✓ Connected — ${testResult.environment} OAuth and Subscription API access confirmed`
            : testResult.stage === "api_access"
            ? `⚠ OAuth valid, but ${testResult.error}`
            : `✗ Failed — ${testResult.error}`}
        </div>
      )}

      <div style={s.field}>
        <label style={s.label}>Environment</label>
        <select name="phonepe_environment" value={form.phonepe_environment} onChange={handleChange} style={s.input}>
          <option value="UAT">UAT (Sandbox)</option>
          <option value="PROD">PROD (Production)</option>
        </select>
      </div>

      <div style={s.field}>
        <label style={s.label}>Client ID</label>
        <input name="phonepe_client_id" value={form.phonepe_client_id} onChange={handleChange} placeholder="Enter PhonePe client_id" style={s.input} />
      </div>

      <div style={s.field}>
        <label style={s.label}>Client Secret</label>
        <div style={s.secretRow}>
          <input
            name="phonepe_client_secret"
            value={form.phonepe_client_secret}
            onChange={handleChange}
            type={showSecret ? "text" : "password"}
            placeholder="Enter PhonePe client_secret"
            style={{ ...s.input, flex: 1 }}
          />
          <button type="button" onClick={() => setShowSecret((v) => !v)} style={s.toggleBtn}>
            {showSecret ? "Hide" : "Show"}
          </button>
        </div>
      </div>

      <div style={s.field}>
        <label style={s.label}>Merchant ID</label>
        <input name="phonepe_merchant_id" value={form.phonepe_merchant_id} onChange={handleChange} placeholder="Enter PhonePe merchant_id" style={s.input} />
      </div>

      <div style={s.divider}>Trial</div>
      <label style={s.checkboxRow}>
        <input type="checkbox" name="trial_enabled" checked={form.trial_enabled} onChange={handleChange} />
        Enable trial for new subscriptions
      </label>

      {form.trial_enabled && (
        <div style={s.row}>
          <div style={s.field}>
            <label style={s.label}>Trial Amount (paise)</label>
            <input
              name="trial_amount"
              type="number"
              min="1"
              value={form.trial_amount}
              onChange={handleChange}
              placeholder="e.g. 100"
              style={s.input}
            />
          </div>
          <div style={s.field}>
            <label style={s.label}>Trial Period (days)</label>
            <input
              name="trial_period_days"
              type="number"
              min="1"
              value={form.trial_period_days}
              onChange={handleChange}
              placeholder="e.g. 7"
              style={s.input}
            />
          </div>
        </div>
      )}
      {form.trial_enabled && (
        <p style={s.sectionDesc}>
          Applies as the default when a subscription setup request doesn't explicitly pass its own amount or trail_days.
        </p>
      )}
    </section>
  );
}

function RazorpaySection({ app, form, handleChange, showSecret, setShowSecret }) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  async function handleTest() {
    setTesting(true);
    setTestResult(null);
    try {
      setTestResult(await testRazorpay(app.id));
    } catch (err) {
      setTestResult({ success: false, error: err.message });
    } finally {
      setTesting(false);
    }
  }

  return (
    <section style={s.section}>
      <div style={s.sectionHeader}>
        <div>
          <h2 style={s.sectionTitle}>Razorpay Credentials</h2>
          <p style={s.sectionDesc}>Used to authenticate with the Razorpay payment gateway.</p>
        </div>
        <button
          type="button"
          onClick={handleTest}
          disabled={testing || !app.razorpay_key_id}
          style={testing ? s.testingBtn : s.testBtn}
          title={!app.razorpay_key_id ? "Save credentials first" : "Test saved credentials"}
        >
          {testing ? "Testing…" : "Test Connection"}
        </button>
      </div>

      {testResult && (
        <div style={testResult.success ? s.testSuccess : testResult.stage === "api_access" ? s.testWarn : s.testError}>
          {testResult.success
            ? `✓ Connected — ${testResult.environment} key_id/key_secret confirmed`
            : `✗ Failed — ${testResult.error}`}
        </div>
      )}

      <div style={s.field}>
        <label style={s.label}>Environment</label>
        <select name="razorpay_environment" value={form.razorpay_environment} onChange={handleChange} style={s.input}>
          <option value="TEST">TEST (Sandbox)</option>
          <option value="LIVE">LIVE (Production)</option>
        </select>
      </div>

      <div style={s.field}>
        <label style={s.label}>Key ID</label>
        <input name="razorpay_key_id" value={form.razorpay_key_id} onChange={handleChange} placeholder="rzp_test_xxxxxxxx" style={s.input} />
      </div>

      <div style={s.field}>
        <label style={s.label}>Key Secret</label>
        <div style={s.secretRow}>
          <input
            name="razorpay_key_secret"
            value={form.razorpay_key_secret}
            onChange={handleChange}
            type={showSecret ? "text" : "password"}
            placeholder="Enter Razorpay key_secret"
            style={{ ...s.input, flex: 1 }}
          />
          <button type="button" onClick={() => setShowSecret((v) => !v)} style={s.toggleBtn}>
            {showSecret ? "Hide" : "Show"}
          </button>
        </div>
      </div>

      <div style={s.field}>
        <label style={s.label}>Webhook Secret</label>
        <input
          name="razorpay_webhook_secret"
          value={form.razorpay_webhook_secret}
          onChange={handleChange}
          type={showSecret ? "text" : "password"}
          placeholder="Enter Razorpay webhook secret"
          style={s.input}
        />
      </div>
    </section>
  );
}

export default function AppSettings() {
  const { app, setApp } = useOutletContext();
  const phonepeEnabled = app.phonepe_enabled;
  const razorpayEnabled = app.razorpay_enabled;
  const [form, setForm] = useState({
    name: app.name,
    phonepe_client_id: app.phonepe_client_id || "",
    phonepe_client_secret: app.phonepe_client_secret || "",
    phonepe_merchant_id: app.phonepe_merchant_id || "",
    phonepe_environment: app.phonepe_environment || "UAT",
    razorpay_key_id: app.razorpay_key_id || "",
    razorpay_key_secret: app.razorpay_key_secret || "",
    razorpay_webhook_secret: app.razorpay_webhook_secret || "",
    razorpay_environment: app.razorpay_environment || "TEST",
    trial_enabled: app.trial_enabled || false,
    trial_amount: app.trial_amount ?? "",
    trial_period_days: app.trial_period_days ?? "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [showSecret, setShowSecret] = useState(false);

  function handleChange(e) {
    const { name, value, type, checked } = e.target;
    setForm((f) => ({ ...f, [name]: type === "checkbox" ? checked : value }));
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      const payload = {
        ...form,
        trial_amount: form.trial_amount === "" ? null : Number(form.trial_amount),
        trial_period_days: form.trial_period_days === "" ? null : Number(form.trial_period_days),
      };
      const updated = await updateApp(app.id, payload);
      setApp(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={s.page}>
      <h1 style={s.h1}>Settings</h1>

      <div style={s.col}>
        {/* App Credentials */}
        <ApiKeySection app={app} setApp={setApp} />

        {error && <div style={s.error}>{error}</div>}

        <form onSubmit={handleSave}>
          <section style={s.section}>
            <h2 style={s.sectionTitle}>App Name</h2>
            <input name="name" value={form.name} onChange={handleChange} style={s.input} />
          </section>

          {phonepeEnabled && (
            <PhonePeSection app={app} form={form} handleChange={handleChange} showSecret={showSecret} setShowSecret={setShowSecret} />
          )}

          {razorpayEnabled && (
            <RazorpaySection app={app} form={form} handleChange={handleChange} showSecret={showSecret} setShowSecret={setShowSecret} />
          )}

          {!phonepeEnabled && !razorpayEnabled && (
            <section style={s.section}>
              <p style={s.sectionDesc}>No payment gateway is enabled for this app. Contact an admin to enable PhonePe or Razorpay.</p>
            </section>
          )}

          <div style={s.saveRow}>
            {saved && <span style={s.savedMsg}>✓ Changes saved</span>}
            <button type="submit" disabled={saving} style={s.saveBtn}>
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </form>

        {/* Outside the form above on purpose: this section saves through its
            own endpoint, and a button inside that form would submit it. */}
        <WebhooksSection app={app} styles={s} />

      </div>
    </div>
  );
}

const s = {
  page: {},
  col: { maxWidth: 620, display: "flex", flexDirection: "column" },
  h1: { margin: "0 0 24px", fontSize: 22, color: "#1e293b" },
  section: { backgroundColor: "#fff", borderRadius: 12, padding: 24, marginBottom: 24, boxShadow: "0 1px 3px rgba(0,0,0,0.07)" },
  sectionHeader: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 },
  sectionTitle: { margin: "0 0 6px", fontSize: 16, color: "#1e293b", fontWeight: 600 },
  sectionDesc: { margin: "0 0 16px", color: "#64748b", fontSize: 13 },
  testBtn: { padding: "8px 18px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 500, color: "#1e293b", whiteSpace: "nowrap", flexShrink: 0 },
  testingBtn: { padding: "8px 18px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 8, cursor: "not-allowed", fontSize: 13, color: "#94a3b8", whiteSpace: "nowrap", flexShrink: 0 },
  testSuccess: { padding: "10px 14px", backgroundColor: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, fontSize: 13, color: "#166534", marginBottom: 16 },
  testWarn: { padding: "10px 14px", backgroundColor: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, fontSize: 13, color: "#92400e", marginBottom: 16 },
  testError: { padding: "10px 14px", backgroundColor: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, fontSize: 13, color: "#991b1b", marginBottom: 16 },
  inlineCode: { backgroundColor: "#e2e8f0", padding: "1px 5px", borderRadius: 4, fontSize: 12 },
  form: { display: "flex", flexDirection: "column", gap: 16 },
  row: { display: "flex", gap: 16 },
  field: { display: "flex", flexDirection: "column", gap: 6, flex: 1, marginBottom: 16 },
  label: { fontSize: 13, fontWeight: 600, color: "#374151" },
  divider: { fontSize: 13, fontWeight: 600, color: "#4f46e5", borderTop: "1px solid #f1f5f9", paddingTop: 12, marginTop: 4 },
  checkboxRow: { display: "flex", alignItems: "center", gap: 8, fontSize: 14, color: "#374151", marginBottom: 12 },
  input: { padding: "9px 12px", border: "1px solid #e2e8f0", borderRadius: 8, fontSize: 14, width: "100%", boxSizing: "border-box" },
  secretRow: { display: "flex", gap: 8 },
  toggleBtn: { padding: "9px 14px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 8, cursor: "pointer", fontSize: 13, whiteSpace: "nowrap" },
  saveRow: { display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 16 },
  savedMsg: { color: "#16a34a", fontSize: 14 },
  saveBtn: { padding: "9px 24px", backgroundColor: "#4f46e5", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontWeight: 600, fontSize: 14 },
  error: { padding: 10, backgroundColor: "#fee2e2", color: "#dc2626", borderRadius: 8, fontSize: 14, marginBottom: 12 },
};


const ak = {
  row: { display: "flex", alignItems: "center", gap: 12 },
  fieldLabel: { fontSize: 12, fontWeight: 600, color: "#64748b", width: 56, flexShrink: 0 },
  keyBox: { flex: 1, display: "flex", alignItems: "center", gap: 10, backgroundColor: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 14px" },
  keyValue: { flex: 1, fontSize: 13, color: "#1e293b", wordBreak: "break-all", letterSpacing: "0.03em" },
  iconBtn: { padding: "4px 12px", backgroundColor: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 6, cursor: "pointer", fontSize: 12, whiteSpace: "nowrap", flexShrink: 0 },
  copyBtn: { padding: "4px 12px", backgroundColor: "#4f46e5", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12, whiteSpace: "nowrap", flexShrink: 0 },
  resetRow: { display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 10, marginTop: 14 },
  warn: { fontSize: 13, color: "#b45309", backgroundColor: "#fef9c3", padding: "6px 12px", borderRadius: 6, flex: 1 },
  resetBtn: { padding: "7px 16px", backgroundColor: "#fff", border: "1px solid #fca5a5", color: "#dc2626", borderRadius: 8, cursor: "pointer", fontSize: 13 },
  confirmBtn: { padding: "7px 16px", backgroundColor: "#dc2626", color: "#fff", border: "none", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 600 },
  cancelBtn: { padding: "7px 16px", backgroundColor: "#f1f5f9", border: "none", borderRadius: 8, cursor: "pointer", fontSize: 13 },
};
