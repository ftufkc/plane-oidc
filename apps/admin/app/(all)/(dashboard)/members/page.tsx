/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState, useEffect } from "react";
import { observer } from "mobx-react";
import { Trash2, UserX, UserCheck, Plus, X } from "lucide-react";
import { PageWrapper } from "@/components/common/page-wrapper";

import type { Route } from "./+types/page";

type TUser = {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  date_joined: string;
  last_login: string | null;
};

const MembersPage = observer(function MembersPage() {
  const [users, setUsers] = useState<TUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
    password: "",
  });
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/instances/users/", { credentials: "include" });
      if (!res.ok) throw new Error("Failed to fetch users");
      const data = await res.json();
      setUsers(data.results || data);
    } catch {
      setError("Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const toggleActive = async (userId: string, isActive: boolean) => {
    try {
      const response = await fetch(`/api/instances/users/${userId}/`, {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !isActive }),
      });
      if (!response.ok) throw new Error("Update rejected");
      await fetchUsers();
    } catch {
      setError("Failed to update user");
    }
  };

  const deleteUser = async (userId: string, email: string) => {
    if (!confirm(`Delete ${email}? This cannot be undone.`)) return;
    try {
      const response = await fetch(`/api/instances/users/${userId}/`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) throw new Error("Deletion rejected");
      await fetchUsers();
    } catch {
      setError("Failed to delete user");
    }
  };

  const createUser = async () => {
    setCreateError(null);
    if (!createForm.email || !createForm.first_name || !createForm.password) {
      setCreateError("Email, first name and password are required.");
      return;
    }
    setCreating(true);
    try {
      const res = await fetch("/api/instances/users/", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(createForm),
      });
      const data = await res.json();
      if (!res.ok) {
        setCreateError(data.error || "Failed to create user");
        return;
      }
      setShowCreateModal(false);
      setCreateForm({ email: "", first_name: "", last_name: "", password: "" });
      await fetchUsers();
    } catch {
      setCreateError("Failed to create user");
    } finally {
      setCreating(false);
    }
  };

  const filtered = users.filter(
    (u) =>
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      `${u.first_name} ${u.last_name}`.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <PageWrapper
      header={{
        title: "Members",
        description: "Manage all users on this instance.",
      }}
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <input
            type="text"
            placeholder="Search by name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="border-border-primary text-sm focus:border-accent-primary max-w-md flex-1 rounded-md border bg-layer-1 px-3 py-2 text-primary outline-none"
          />
          <button
            onClick={() => setShowCreateModal(true)}
            className="text-sm flex items-center gap-2 rounded-md bg-accent-primary px-3 py-2 font-medium text-white hover:opacity-90"
          >
            <Plus className="h-4 w-4" />
            Create User
          </button>
        </div>

        {loading && <div className="text-sm text-secondary">Loading...</div>}
        {error && <div className="text-red-500 text-sm">{error}</div>}

        {!loading && (
          <div className="border-border-primary overflow-hidden rounded-lg border">
            <table className="text-sm w-full">
              <thead className="border-border-primary border-b bg-layer-1">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-secondary">Name</th>
                  <th className="px-4 py-3 text-left font-medium text-secondary">Email</th>
                  <th className="px-4 py-3 text-left font-medium text-secondary">Status</th>
                  <th className="px-4 py-3 text-left font-medium text-secondary">Joined</th>
                  <th className="px-4 py-3 text-left font-medium text-secondary">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((user) => (
                  <tr key={user.id} className="border-border-primary border-b last:border-0 hover:bg-layer-1">
                    <td className="px-4 py-3 text-primary">
                      {user.first_name} {user.last_name}
                    </td>
                    <td className="px-4 py-3 text-secondary">{user.email}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs inline-flex items-center rounded-full px-2 py-0.5 font-medium ${
                          user.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                        }`}
                      >
                        {user.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-secondary">{new Date(user.date_joined).toLocaleDateString()}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => toggleActive(user.id, user.is_active)}
                          className="rounded p-1.5 text-secondary transition-colors hover:bg-layer-2 hover:text-primary"
                          title={user.is_active ? "Deactivate" : "Activate"}
                        >
                          {user.is_active ? <UserX className="h-4 w-4" /> : <UserCheck className="h-4 w-4" />}
                        </button>
                        <button
                          onClick={() => deleteUser(user.id, user.email)}
                          className="hover:text-red-500 rounded p-1.5 text-secondary transition-colors hover:bg-layer-2"
                          title="Delete user"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-secondary">
                      No users found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="shadow-xl w-full max-w-md rounded-lg bg-layer-1 p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-16 font-medium text-primary">Create User</h2>
              <button
                onClick={() => {
                  setShowCreateModal(false);
                  setCreateError(null);
                }}
                className="rounded p-1 text-secondary hover:bg-layer-2"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex flex-col gap-3">
              <input
                type="text"
                placeholder="First name *"
                value={createForm.first_name}
                onChange={(e) => setCreateForm({ ...createForm, first_name: e.target.value })}
                className="border-border-primary text-sm focus:border-accent-primary rounded-md border bg-layer-2 px-3 py-2 text-primary outline-none"
              />
              <input
                type="text"
                placeholder="Last name"
                value={createForm.last_name}
                onChange={(e) => setCreateForm({ ...createForm, last_name: e.target.value })}
                className="border-border-primary text-sm focus:border-accent-primary rounded-md border bg-layer-2 px-3 py-2 text-primary outline-none"
              />
              <input
                type="email"
                placeholder="Email *"
                value={createForm.email}
                onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                className="border-border-primary text-sm focus:border-accent-primary rounded-md border bg-layer-2 px-3 py-2 text-primary outline-none"
              />
              <input
                type="password"
                placeholder="Password *"
                value={createForm.password}
                onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                className="border-border-primary text-sm focus:border-accent-primary rounded-md border bg-layer-2 px-3 py-2 text-primary outline-none"
              />
              {createError && <div className="text-red-500 text-sm">{createError}</div>}
              <div className="flex gap-3 pt-2">
                <button
                  onClick={createUser}
                  disabled={creating}
                  className="text-sm flex-1 rounded-md bg-accent-primary px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50"
                >
                  {creating ? "Creating..." : "Create"}
                </button>
                <button
                  onClick={() => {
                    setShowCreateModal(false);
                    setCreateError(null);
                  }}
                  className="border-border-primary text-sm flex-1 rounded-md border px-4 py-2 text-secondary hover:bg-layer-2"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </PageWrapper>
  );
});

export const meta: Route.MetaFunction = () => [{ title: "Members - God Mode" }];
export default MembersPage;
