import { ActionIcon, Badge, Button, Group, Menu, Modal, Paper, Select, Stack, Table, Text, TextInput } from "@mantine/core";
import {
  IconApps,
  IconDots,
  IconKey,
  IconLockOpen,
  IconPencil,
  IconTrash,
  IconUserCheck,
  IconUserOff,
  IconUserPlus,
} from "@tabler/icons-react";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { keys, useAdminApps, useAdminUsers, useUserApps } from "../../api/queries";
import type { UserOut } from "../../api/types";
import { RoleBadge, StatusDot, UserAvatar } from "../../components/ui";
import { useSession } from "../../auth/session";
import { CopyBlock } from "../../components/common";
import { TokenTable } from "../../components/TokenTable";
import { formatDate } from "../../lib/format";
import { fieldErrors } from "../../lib/formErrors";

type Shown = { title: string; email: string; password: string };
type GlobalRole = "user" | "admin";
type MemberRole = "editor" | "tester";

function AddUser({ onCreated }: { onCreated: (s: Shown) => void }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const form = useForm<{ email: string; name: string; role: GlobalRole }>({
    initialValues: { email: "", name: "", role: "user" },
  });
  const create = useMutation({
    meta: { quiet: true },
    mutationFn: (body: typeof form.values) => unwrap(api.POST("/v1/admin/users", { body })),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: keys.users });
      setOpen(false);
      form.reset();
      onCreated({ title: `User ${r.user.email} created`, email: r.user.email, password: r.temporary_password });
    },
    onError: (e) => {
      const { errors, rest } = fieldErrors(e, (p) => p in form.values);
      form.setErrors(rest.length ? { ...errors, email: [errors.email, ...rest].filter(Boolean).join("; ") } : errors);
    },
  });
  return (
    <>
      <Button onClick={() => setOpen(true)} leftSection={<IconUserPlus size={16} />}>
        Add user
      </Button>
      <Modal opened={open} onClose={() => setOpen(false)} title="Add user">
        <form onSubmit={form.onSubmit((v) => create.mutate(v))}>
          <Stack>
            <TextInput label="Email" type="email" required {...form.getInputProps("email")} />
            <TextInput label="Name" required {...form.getInputProps("name")} />
            <Select
              label="Role"
              data={[
                { value: "user", label: "user — works in the apps they're added to" },
                { value: "admin", label: "admin — manages users and apps, can do everything" },
              ]}
              allowDeselect={false}
              {...form.getInputProps("role")}
            />
            <Text size="xs" c="dimmed">
              After creating a user, add them to apps (as editor or tester) under Apps.
            </Text>
            <Button type="submit" loading={create.isPending}>
              Create
            </Button>
          </Stack>
        </form>
      </Modal>
    </>
  );
}

function UserTokens({ user, onClose }: { user: UserOut; onClose: () => void }) {
  const qc = useQueryClient();
  const tokens = useQuery({
    queryKey: keys.userTokens(user.id),
    queryFn: () => unwrap(api.GET("/v1/admin/users/{user_id}/tokens", { params: { path: { user_id: user.id } } })),
  });
  const revoke = useMutation({
    mutationFn: (token_id: string) =>
      unwrap(
        api.DELETE("/v1/admin/users/{user_id}/tokens/{token_id}", { params: { path: { user_id: user.id, token_id } } }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.users }),
  });
  return (
    <Modal opened onClose={onClose} title={`API tokens of ${user.name}`} size="lg">
      <TokenTable
        tokens={tokens.data ?? []}
        revoking={revoke.isPending ? revoke.variables : undefined}
        onRevoke={(t) => window.confirm(`Revoke "${t.name}"?`) && revoke.mutate(t.id)}
      />
    </Modal>
  );
}

/** The user's app memberships: change role, remove, add to another app. */
function UserApps({ user, onClose }: { user: UserOut; onClose: () => void }) {
  const qc = useQueryClient();
  const memberships = useUserApps(user.id);
  const apps = useAdminApps();
  const [app, setApp] = useState<string | null>(null);
  const [role, setRole] = useState<MemberRole>("tester");
  const refresh = () => {
    qc.invalidateQueries({ queryKey: keys.admin });
    qc.invalidateQueries({ queryKey: keys.myApps });
  };
  const put = useMutation({
    mutationFn: (v: { appId: string; role: MemberRole }) =>
      unwrap(
        api.PUT("/v1/admin/apps/{app_id}/members/{user_id}", {
          params: { path: { app_id: v.appId, user_id: user.id } },
          body: { role: v.role },
        }),
      ),
    onSuccess: () => {
      setApp(null);
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (appId: string) =>
      unwrap(
        api.DELETE("/v1/admin/apps/{app_id}/members/{user_id}", { params: { path: { app_id: appId, user_id: user.id } } }),
      ),
    onSuccess: refresh,
  });
  const inApps = new Set(memberships.data?.map((m) => m.app_id));
  const options = (apps.data ?? []).filter((a) => !inApps.has(a.id)).map((a) => ({ value: a.id, label: a.name }));

  return (
    <Modal opened onClose={onClose} title={`Apps of ${user.name}`} size="lg">
      {user.role === "admin" ? (
        <Text size="sm">Admins have the admin role in every app; they can't be added as members.</Text>
      ) : (
        <Stack data-testid="user-apps">
          <Table>
            <Table.Tbody>
              {memberships.data?.map((m) => (
                <Table.Tr key={m.app_id} data-app={m.app_slug}>
                  <Table.Td>
                    {m.app_name}{" "}
                    <Text span size="xs" c="dimmed" ff="monospace">
                      {m.app_slug}
                    </Text>
                  </Table.Td>
                  <Table.Td w={130}>
                    <Select
                      size="xs"
                      data={["editor", "tester"]}
                      value={m.role}
                      allowDeselect={false}
                      onChange={(v) => v && v !== m.role && put.mutate({ appId: m.app_id, role: v as MemberRole })}
                      aria-label={`Role in ${m.app_slug}`}
                    />
                  </Table.Td>
                  <Table.Td w={90}>
                    <Button
                      size="compact-xs"
                      color="red"
                      variant="light"
                      loading={remove.isPending && remove.variables === m.app_id}
                      onClick={() => remove.mutate(m.app_id)}
                    >
                      Remove
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
              {memberships.data?.length === 0 && (
                <Table.Tr>
                  <Table.Td>
                    <Text size="sm" c="dimmed">
                      Not in any app yet.
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
          <Group align="flex-end">
            <Select
              label="Add to app"
              placeholder={options.length ? "Pick an app" : "No other apps"}
              data={options}
              value={app}
              onChange={setApp}
              searchable
              style={{ flex: 1 }}
            />
            <Select
              label="Role"
              aria-label="Role in new app"
              data={["editor", "tester"]}
              value={role}
              onChange={(v) => v && setRole(v as MemberRole)}
              allowDeselect={false}
              w={110}
            />
            <Button disabled={!app} loading={put.isPending} onClick={() => put.mutate({ appId: app!, role })}>
              Add
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}

export function AdminUsersPage() {
  const me = useSession();
  const qc = useQueryClient();
  const users = useAdminUsers();
  const [shown, setShown] = useState<Shown | null>(null);
  const [tokensOf, setTokensOf] = useState<UserOut | null>(null);
  const [appsOf, setAppsOf] = useState<UserOut | null>(null);
  const [renaming, setRenaming] = useState<UserOut | null>(null);
  const [newName, setNewName] = useState("");
  const [deleting, setDeleting] = useState<UserOut | null>(null);

  const update = useMutation({
    mutationFn: (v: { id: string; role?: GlobalRole; is_active?: boolean; name?: string }) =>
      unwrap(
        api.PATCH("/v1/admin/users/{user_id}", {
          params: { path: { user_id: v.id } },
          body: { role: v.role, is_active: v.is_active, name: v.name },
        }),
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.admin });
      setRenaming(null);
    },
  });
  const reset = useMutation({
    mutationFn: (u: UserOut) =>
      unwrap(api.POST("/v1/admin/users/{user_id}/reset-password", { params: { path: { user_id: u.id } } })),
    onSuccess: (r, u) => {
      qc.invalidateQueries({ queryKey: keys.users });
      setShown({ title: `New temporary password for ${u.email}`, email: u.email, password: r.temporary_password });
    },
  });
  const remove = useMutation({
    mutationFn: (u: UserOut) => unwrap(api.DELETE("/v1/admin/users/{user_id}", { params: { path: { user_id: u.id } } })),
    onSuccess: (_r, u) => {
      qc.invalidateQueries({ queryKey: keys.admin });
      setDeleting(null);
      notifications.show({ color: "green", message: `Deleted ${u.email}` });
    },
  });

  const changeRole = (u: UserOut, role: GlobalRole) => {
    if (role === u.role) return;
    const msg =
      role === "admin"
        ? `Make ${u.name} an admin? Admins manage all users and apps; their app memberships are replaced by full access.`
        : `Make ${u.name} a regular user? They keep access only to apps they are a member of.`;
    if (window.confirm(msg)) update.mutate({ id: u.id, role });
  };

  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          Users sign in to the console. Add them to apps as editor or tester; admins can do everything.
        </Text>
        <AddUser onCreated={setShown} />
      </Group>
      <Paper withBorder className="table-card">
      <Table.ScrollContainer minWidth={800}>
        <Table data-testid="users-table">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>User</Table.Th>
              <Table.Th>Role</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Last login</Table.Th>
              <Table.Th>Tokens</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {users.data?.map((u) => {
              const self = u.id === me.id;
              return (
                <Table.Tr key={u.id} data-email={u.email}>
                  <Table.Td>
                    <Group gap="sm" wrap="nowrap">
                      <UserAvatar name={u.name} email={u.email} size={32} />
                      <div>
                        <Text size="sm" fw={500}>
                          {u.name}
                          {self && (
                            <Text span c="dimmed" size="xs">
                              {" "}
                              (you)
                            </Text>
                          )}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {u.email}
                        </Text>
                      </div>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    {self ? (
                      <RoleBadge role={u.role} />
                    ) : (
                      <Select
                        size="xs"
                        w={100}
                        data={["user", "admin"]}
                        value={u.role}
                        allowDeselect={false}
                        onChange={(v) => v && changeRole(u, v as GlobalRole)}
                        aria-label={`Role of ${u.email}`}
                      />
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Badge
                        color={u.is_active ? "green" : "gray"}
                        variant="light"
                        leftSection={<StatusDot color={u.is_active ? "green" : "gray"} />}
                      >
                        {u.is_active ? "active" : "deactivated"}
                      </Badge>
                      {u.must_change_password && (
                        <Badge color="yellow" variant="light">
                          temp password
                        </Badge>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>{formatDate(u.last_login_at)}</Table.Td>
                  <Table.Td>{u.active_tokens ?? 0}</Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap" justify="flex-end">
                      {u.role !== "admin" && (
                        <Button size="xs" variant="default" leftSection={<IconApps size={14} />} onClick={() => setAppsOf(u)}>
                          Apps
                        </Button>
                      )}
                      <Menu position="bottom-end">
                        <Menu.Target>
                          <ActionIcon variant="subtle" color="gray" aria-label={`Actions for ${u.email}`}>
                            <IconDots size={18} />
                          </ActionIcon>
                        </Menu.Target>
                        <Menu.Dropdown>
                          <Menu.Item
                            leftSection={<IconPencil size={16} />}
                            onClick={() => {
                              setNewName(u.name);
                              setRenaming(u);
                            }}
                          >
                            Rename
                          </Menu.Item>
                          <Menu.Item leftSection={<IconKey size={16} />} onClick={() => setTokensOf(u)}>
                            API tokens
                          </Menu.Item>
                          <Menu.Item
                            leftSection={<IconLockOpen size={16} />}
                            onClick={() =>
                              window.confirm(`Reset the password of ${u.email}? Their sessions end.`) && reset.mutate(u)
                            }
                          >
                            Reset password
                          </Menu.Item>
                          <Menu.Item
                            leftSection={u.is_active ? <IconUserOff size={16} /> : <IconUserCheck size={16} />}
                            disabled={self}
                            onClick={() =>
                              (!u.is_active ||
                                window.confirm(`Deactivate ${u.email}? Sessions and tokens stop working.`)) &&
                              update.mutate({ id: u.id, is_active: !u.is_active })
                            }
                          >
                            {u.is_active ? "Deactivate" : "Reactivate"}
                          </Menu.Item>
                          {!self && (
                            <>
                              <Menu.Divider />
                              <Menu.Item color="red" leftSection={<IconTrash size={16} />} onClick={() => setDeleting(u)}>
                                Delete user
                              </Menu.Item>
                            </>
                          )}
                        </Menu.Dropdown>
                      </Menu>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      </Paper>

      <Modal opened={!!shown} onClose={() => setShown(null)} title={shown?.title} size="lg">
        {shown && (
          <Stack>
            <Text size="sm" c="orange">
              Shown only once. Give it to the user; they must change it at first sign-in.
            </Text>
            <CopyBlock label="Email" value={shown.email} />
            <CopyBlock label="Temporary password" value={shown.password} testId="temp-password" />
            <Button onClick={() => setShown(null)}>Done</Button>
          </Stack>
        )}
      </Modal>
      <Modal opened={!!renaming} onClose={() => setRenaming(null)} title={`Rename ${renaming?.email ?? ""}`}>
        <Stack>
          <TextInput label="Name" value={newName} onChange={(e) => setNewName(e.currentTarget.value)} />
          <Button
            disabled={!newName.trim()}
            loading={update.isPending}
            onClick={() => renaming && update.mutate({ id: renaming.id, name: newName.trim() })}
          >
            Save
          </Button>
        </Stack>
      </Modal>
      <Modal opened={!!deleting} onClose={() => setDeleting(null)} title={`Delete ${deleting?.name ?? ""}?`}>
        {deleting && (
          <Stack>
            <Text size="sm">Deleting {deleting.email}:</Text>
            <Text size="sm" component="ul" m={0} pl="md">
              <li>they can't sign in any more and their sessions end;</li>
              <li>their API tokens stop working;</li>
              <li>the email address can be used for a new account;</li>
              <li>their name stays on the jobs and template versions they made.</li>
            </Text>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setDeleting(null)}>
                Cancel
              </Button>
              <Button color="red" loading={remove.isPending} onClick={() => remove.mutate(deleting)}>
                Delete user
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
      {tokensOf && <UserTokens user={tokensOf} onClose={() => setTokensOf(null)} />}
      {appsOf && <UserApps user={appsOf} onClose={() => setAppsOf(null)} />}
    </Stack>
  );
}
