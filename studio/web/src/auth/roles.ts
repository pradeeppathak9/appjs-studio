import type { Me, MyApp } from "../api/types";

export type AppRole = MyApp["role"];

export const ROLE_COLOR: Record<string, string> = {
  admin: "violet",
  editor: "blue",
  tester: "gray",
  user: "gray",
};

export function isAdmin(me: Pick<Me, "role"> | undefined): boolean {
  return me?.role === "admin";
}

/** Editors and admins manage an app's templates; testers only run active ones. */
export function canEdit(role: AppRole | undefined): boolean {
  return role === "editor" || role === "admin";
}

export type AppTab = { label: string; path: string; editorOnly: boolean; adminOnly?: boolean };

const APP_TABS: AppTab[] = [
  { label: "Templates", path: "", editorOnly: false },
  { label: "Test", path: "test", editorOnly: false },
  { label: "Free prompt", path: "free", editorOnly: true },
  { label: "Jobs", path: "jobs", editorOnly: false },
  { label: "Android preview", path: "preview", editorOnly: true },
  { label: "Integration guide", path: "guide", editorOnly: false },
  { label: "Users", path: "users", editorOnly: true, adminOnly: true },
  { label: "Settings", path: "settings", editorOnly: true, adminOnly: true },
];

/** tester -> Templates, Test, Jobs, Integration guide; editor/admin -> + Free prompt, Android preview;
 * global admins (`isAdmin`) -> + Users, Settings. */
export function appTabsFor(role: AppRole, globalAdmin = false): AppTab[] {
  return APP_TABS.filter((t) => (!t.editorOnly || canEdit(role)) && (!t.adminOnly || globalAdmin));
}
