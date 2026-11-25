import React from "react";
import { API_BASE } from "../config";

function authHeaders(token) {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  if (res.status === 204) return null;
  return res.json();
}

export function getToken() {
  const token = localStorage.getItem("token");
  if (!token || token === "undefined") return null;
  return token;
}

export async function login(email, password) {
  return request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function getMe() {
  return request("/api/auth/me", { headers: authHeaders(getToken()) });
}

export async function changePassword(currentPassword, newPassword) {
  return request("/api/auth/change-password", {
    method: "POST",
    headers: authHeaders(getToken()),
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

// The gateways this server offers (AUTOREV_GATEWAYS); public, no sign-in.
export async function getServerConfig() {
  return request("/api/config");
}

/** The gateways this server offers; both until the server answers, or if it can't be reached. */
export function useServerGateways() {
  const [gateways, setGateways] = React.useState(["phonepe", "razorpay"]);
  React.useEffect(() => {
    getServerConfig()
      .then((c) => Array.isArray(c?.gateways) && setGateways(c.gateways))
      .catch(() => {});
  }, []);
  return gateways;
}

// Apps
export async function listApps() {
  return request("/api/apps", { headers: authHeaders(getToken()) });
}

export async function getApp(appId) {
  return request(`/api/apps/${appId}`, { headers: authHeaders(getToken()) });
}

export async function updateApp(appId, data) {
  return request(`/api/apps/${appId}`, {
    method: "PATCH",
    headers: authHeaders(getToken()),
    body: JSON.stringify(data),
  });
}

export async function resetApiKey(appId) {
  return request(`/api/apps/${appId}/reset-key`, {
    method: "POST",
    headers: authHeaders(getToken()),
  });
}

export async function testPhonePe(appId) {
  return request(`/api/apps/${appId}/test-phonepe`, {
    method: "POST",
    headers: authHeaders(getToken()),
  });
}

export async function testRazorpay(appId) {
  return request(`/api/apps/${appId}/test-razorpay`, {
    method: "POST",
    headers: authHeaders(getToken()),
  });
}

// Webhooks
export async function getWebhookConfig(appId) {
  return request(`/api/apps/${appId}/webhook`, { headers: authHeaders(getToken()) });
}

export async function updateWebhookConfig(appId, data) {
  return request(`/api/apps/${appId}/webhook`, {
    method: "PUT",
    headers: authHeaders(getToken()),
    body: JSON.stringify(data),
  });
}

export async function rotateWebhookSecret(appId) {
  return request(`/api/apps/${appId}/webhook/rotate-secret`, {
    method: "POST",
    headers: authHeaders(getToken()),
  });
}

export async function sendWebhookTest(appId) {
  return request(`/api/apps/${appId}/webhook/test`, {
    method: "POST",
    headers: authHeaders(getToken()),
  });
}

export async function listWebhookDeliveries(appId, params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/apps/${appId}/webhook/deliveries${qs ? `?${qs}` : ""}`, {
    headers: authHeaders(getToken()),
  });
}

export async function retryWebhookDelivery(appId, deliveryId) {
  return request(`/api/apps/${appId}/webhook/deliveries/${deliveryId}/retry`, {
    method: "POST",
    headers: authHeaders(getToken()),
  });
}

// Dashboard
export async function getAppSummary(appId, params = {}) {
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)));
  return request(`/api/apps/${appId}/summary?${qs}`, { headers: authHeaders(getToken()) });
}

export async function listSubscriptions(appId, params = {}) {
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)));
  return request(`/api/apps/${appId}/subscriptions?${qs}`, { headers: authHeaders(getToken()) });
}

export async function getSubscriptionStateCounts(appId, params = {}) {
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)));
  return request(`/api/apps/${appId}/subscriptions/state-counts?${qs}`, { headers: authHeaders(getToken()) });
}

export async function getScheduledStateCounts(appId, params = {}) {
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)));
  return request(`/api/apps/${appId}/scheduled/state-counts?${qs}`, { headers: authHeaders(getToken()) });
}

export async function listTransactions(appId, params = {}) {
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)));
  return request(`/api/apps/${appId}/transactions?${qs}`, { headers: authHeaders(getToken()) });
}

export async function listScheduled(appId, params = {}) {
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)));
  return request(`/api/apps/${appId}/scheduled?${qs}`, { headers: authHeaders(getToken()) });
}

// Paged variants: same query as the plain list helpers, but they also surface the
// X-Total-Count header so a caller can drive a pager without downloading every
// row. The array-returning helpers above are left alone — other callers
// (e.g. SubscriptionDetailsModal) rely on their shape.
async function requestPage(path) {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders(getToken()) });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  const rows = await res.json();
  const header = res.headers.get("X-Total-Count");
  // null means "no count in this response" — either the caller passed
  // with_count=false while paging, or the header was stripped. Callers keep their
  // previous total in that case rather than mistaking a page length for a total.
  const total = header == null ? null : Number(header);
  return { rows, total: Number.isFinite(total) ? total : null };
}

function toQuery(params) {
  return new URLSearchParams(
    Object.fromEntries(Object.entries(params).filter(([, v]) => v != null))
  );
}

export async function listSubscriptionsPage(appId, params = {}) {
  return requestPage(`/api/apps/${appId}/subscriptions?${toQuery(params)}`);
}

export async function listScheduledPage(appId, params = {}) {
  return requestPage(`/api/apps/${appId}/scheduled?${toQuery(params)}`);
}

export async function listRazorpaySubscriptions(appId, params = {}) {
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)));
  return request(`/api/apps/${appId}/razorpay-subscriptions?${qs}`, { headers: authHeaders(getToken()) });
}

export async function listRazorpayTransactions(appId, params = {}) {
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null)));
  return request(`/api/apps/${appId}/razorpay-transactions?${qs}`, { headers: authHeaders(getToken()) });
}

export async function getPhonePeStatus(appId, apiKey, phoneNumber) {
  return request(`/api/v1/${appId}/phonepay/${phoneNumber}/status`, {
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
  });
}

export async function getScheduledAttempts(appId, scheduledTransactionId) {
  return request(`/api/apps/${appId}/scheduled/${scheduledTransactionId}/attempts`, { headers: authHeaders(getToken()) });
}

export async function getSubscription(appId, subscriptionId) {
  return request(`/api/apps/${appId}/subscriptions/${subscriptionId}`, { headers: authHeaders(getToken()) });
}

export async function revokeSubscription(appId, subscriptionId) {
  return request(`/api/apps/${appId}/subscriptions/${subscriptionId}/revoke`, {
    method: "POST",
    headers: authHeaders(getToken()),
  });
}

export async function getSubscriptionTransactions(appId, subscriptionId) {
  return request(`/api/apps/${appId}/subscriptions/${subscriptionId}/transactions`, { headers: authHeaders(getToken()) });
}

export async function getRazorpaySubscriptionTransactions(appId, subscriptionId) {
  return request(`/api/apps/${appId}/razorpay-subscriptions/${subscriptionId}/transactions`, { headers: authHeaders(getToken()) });
}

// Admin
export async function adminListUsers() {
  return request("/api/admin/users", { headers: authHeaders(getToken()) });
}

export async function adminCreateUser(data) {
  return request("/api/admin/users", {
    method: "POST",
    headers: authHeaders(getToken()),
    body: JSON.stringify(data),
  });
}

export async function adminUpdateUser(userId, data) {
  return request(`/api/admin/users/${userId}`, {
    method: "PATCH",
    headers: authHeaders(getToken()),
    body: JSON.stringify(data),
  });
}

export async function adminDeleteUser(userId) {
  return request(`/api/admin/users/${userId}`, {
    method: "DELETE",
    headers: authHeaders(getToken()),
  });
}

export async function adminListApps() {
  return request("/api/admin/apps", { headers: authHeaders(getToken()) });
}

export async function adminCreateApp(data) {
  return request("/api/admin/apps", {
    method: "POST",
    headers: authHeaders(getToken()),
    body: JSON.stringify(data),
  });
}

export async function adminUpdateApp(appId, data) {
  return request(`/api/admin/apps/${appId}`, {
    method: "PATCH",
    headers: authHeaders(getToken()),
    body: JSON.stringify(data),
  });
}

export async function adminDeleteApp(appId) {
  return request(`/api/admin/apps/${appId}`, {
    method: "DELETE",
    headers: authHeaders(getToken()),
  });
}

export async function adminListUserApps(userId) {
  return request(`/api/admin/users/${userId}/apps`, { headers: authHeaders(getToken()) });
}

export async function adminListAppUsers(appId) {
  return request(`/api/admin/apps/${appId}/users`, { headers: authHeaders(getToken()) });
}

export async function adminGrantAppUser(appId, userId) {
  return request(`/api/admin/apps/${appId}/users`, {
    method: "POST",
    headers: authHeaders(getToken()),
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function adminRevokeAppUser(appId, userId) {
  return request(`/api/admin/apps/${appId}/users/${userId}`, {
    method: "DELETE",
    headers: authHeaders(getToken()),
  });
}

// Redis
export async function adminRedisKeys() {
  return request("/api/admin/redis/keys", { headers: authHeaders(getToken()) });
}

export async function adminRedisKey(key) {
  return request(`/api/admin/redis/keys/${encodeURIComponent(key)}`, { headers: authHeaders(getToken()) });
}

export async function adminRedisDeleteKey(key) {
  return request(`/api/admin/redis/keys/${encodeURIComponent(key)}`, {
    method: "DELETE",
    headers: authHeaders(getToken()),
  });
}
