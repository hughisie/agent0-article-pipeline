import React, { useEffect, useState } from "react";
import { Button } from "./ui/button";

type Profile = {
  id: number;
  name: string;
  input_dir: string;
  output_dir: string;
  created_at: string;
  is_active: number;
  description?: string;
};

type ProfileManagerProps = {
  apiUrl: (path: string) => string;
  onProfileChange?: () => void;
};

export default function ProfileManager({ apiUrl, onProfileChange }: ProfileManagerProps) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeProfileId, setActiveProfileId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingProfile, setEditingProfile] = useState<Profile | null>(null);

  // Form state
  const [formName, setFormName] = useState("");
  const [formInputDir, setFormInputDir] = useState("");
  const [formOutputDir, setFormOutputDir] = useState("");
  const [formDescription, setFormDescription] = useState("");

  useEffect(() => {
    loadProfiles();
  }, []);

  const loadProfiles = async () => {
    try {
      const res = await fetch(apiUrl("/api/profiles"));
      const data = await res.json();
      setProfiles(data.profiles || []);
      setActiveProfileId(data.active_profile_id);
    } catch (err) {
      console.error("Failed to load profiles:", err);
    }
  };

  const handleActivateProfile = async (profileId: number) => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl(`/api/profiles/${profileId}/activate`), {
        method: "POST",
      });
      if (res.ok) {
        await loadProfiles();
        if (onProfileChange) onProfileChange();
      }
    } catch (err) {
      console.error("Failed to activate profile:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateProfile = async () => {
    if (!formName || !formInputDir || !formOutputDir) {
      alert("Name, input directory, and output directory are required");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(apiUrl("/api/profiles"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formName,
          input_dir: formInputDir,
          output_dir: formOutputDir,
          description: formDescription,
        }),
      });

      if (res.ok) {
        await loadProfiles();
        setShowCreateForm(false);
        setFormName("");
        setFormInputDir("");
        setFormOutputDir("");
        setFormDescription("");
      } else {
        const data = await res.json();
        alert(`Failed to create profile: ${data.detail || "Unknown error"}`);
      }
    } catch (err) {
      console.error("Failed to create profile:", err);
      alert("Failed to create profile");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateProfile = async () => {
    if (!editingProfile) return;

    setLoading(true);
    try {
      const res = await fetch(apiUrl(`/api/profiles/${editingProfile.id}`), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: formName,
          input_dir: formInputDir,
          output_dir: formOutputDir,
          description: formDescription,
        }),
      });

      if (res.ok) {
        await loadProfiles();
        setEditingProfile(null);
        setFormName("");
        setFormInputDir("");
        setFormOutputDir("");
        setFormDescription("");
      } else {
        const data = await res.json();
        alert(`Failed to update profile: ${data.detail || "Unknown error"}`);
      }
    } catch (err) {
      console.error("Failed to update profile:", err);
      alert("Failed to update profile");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteProfile = async (profileId: number) => {
    if (!confirm("Are you sure you want to delete this profile?")) return;

    setLoading(true);
    try {
      const res = await fetch(apiUrl(`/api/profiles/${profileId}`), {
        method: "DELETE",
      });

      if (res.ok) {
        await loadProfiles();
      } else {
        const data = await res.json();
        alert(`Failed to delete profile: ${data.detail || "Unknown error"}`);
      }
    } catch (err) {
      console.error("Failed to delete profile:", err);
      alert("Failed to delete profile");
    } finally {
      setLoading(false);
    }
  };

  const startEdit = (profile: Profile) => {
    setEditingProfile(profile);
    setFormName(profile.name);
    setFormInputDir(profile.input_dir);
    setFormOutputDir(profile.output_dir);
    setFormDescription(profile.description || "");
    setShowCreateForm(false);
  };

  const cancelEdit = () => {
    setEditingProfile(null);
    setFormName("");
    setFormInputDir("");
    setFormOutputDir("");
    setFormDescription("");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Profiles</h2>
        {!showCreateForm && !editingProfile && (
          <Button
            onClick={() => setShowCreateForm(true)}
            size="sm"
            disabled={loading}
          >
            + New Profile
          </Button>
        )}
      </div>

      {/* Create/Edit Form */}
      {(showCreateForm || editingProfile) && (
        <div className="border border-slate-700 rounded-lg p-4 space-y-3 bg-slate-800/50">
          <h3 className="font-medium text-slate-100">
            {editingProfile ? "Edit Profile" : "Create New Profile"}
          </h3>

          <div>
            <label className="block text-sm font-medium mb-1 text-slate-300">Name *</label>
            <input
              type="text"
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="e.g., Barcelona News"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1 text-slate-300">
              Input Directory * (relative to project root)
            </label>
            <input
              type="text"
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500"
              value={formInputDir}
              onChange={(e) => setFormInputDir(e.target.value)}
              placeholder="e.g., current/barcelona"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1 text-slate-300">
              Output Directory * (relative to project root)
            </label>
            <input
              type="text"
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500"
              value={formOutputDir}
              onChange={(e) => setFormOutputDir(e.target.value)}
              placeholder="e.g., output/barcelona"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1 text-slate-300">
              Description
            </label>
            <textarea
              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500"
              rows={2}
              value={formDescription}
              onChange={(e) => setFormDescription(e.target.value)}
              placeholder="Optional description"
            />
          </div>

          <div className="flex gap-2">
            <Button
              onClick={editingProfile ? handleUpdateProfile : handleCreateProfile}
              disabled={loading}
            >
              {editingProfile ? "Update" : "Create"}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setShowCreateForm(false);
                cancelEdit();
              }}
              disabled={loading}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Profile List */}
      <div className="space-y-2">
        {profiles.map((profile) => (
          <div
            key={profile.id}
            className={`border rounded-lg p-4 ${
              profile.id === activeProfileId
                ? "border-blue-500 bg-blue-900/20"
                : "border-slate-700 bg-slate-800/30"
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-medium text-slate-100">{profile.name}</h3>
                  {profile.id === activeProfileId && (
                    <span className="text-xs bg-blue-500 text-white px-2 py-0.5 rounded">
                      ACTIVE
                    </span>
                  )}
                </div>
                {profile.description && (
                  <p className="text-sm text-slate-400 mt-1">{profile.description}</p>
                )}
                <div className="text-sm text-slate-400 mt-2 space-y-1">
                  <div>
                    <span className="font-medium text-slate-300">Input:</span> {profile.input_dir}
                  </div>
                  <div>
                    <span className="font-medium text-slate-300">Output:</span> {profile.output_dir}
                  </div>
                </div>
              </div>

              <div className="flex gap-2 ml-4">
                {profile.id !== activeProfileId && (
                  <Button
                    size="sm"
                    onClick={() => handleActivateProfile(profile.id)}
                    disabled={loading}
                  >
                    Activate
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => startEdit(profile)}
                  disabled={loading}
                >
                  Edit
                  </Button>
                {profile.id !== activeProfileId && (
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={() => handleDeleteProfile(profile.id)}
                    disabled={loading}
                  >
                    Delete
                  </Button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
