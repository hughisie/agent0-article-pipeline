import React, { useEffect, useState } from "react";
import { Button } from "./ui/button";

type PromptData = {
  value: string;
  is_custom: boolean;
  default_value: string;
  description: string;
  model: string;
  default_model: string;
};

type ModelOption = {
  id: string;
  name: string;
  provider: string;
};

type PromptEditorProps = {
  apiUrl: (path: string) => string;
  profileId: number;
};

export default function PromptEditor({ apiUrl, profileId }: PromptEditorProps) {
  const [prompts, setPrompts] = useState<Record<string, PromptData>>({});
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedPrompt, setExpandedPrompt] = useState<string | null>(null);
  const [editingPrompt, setEditingPrompt] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editModel, setEditModel] = useState("");

  useEffect(() => {
    loadPrompts();
  }, [profileId]);

  const loadPrompts = async () => {
    setLoading(true);
    try {
      const res = await fetch(apiUrl(`/api/profiles/${profileId}/prompts`));
      const data = await res.json();
      setPrompts(data.prompts || {});
      setAvailableModels(data.available_models || []);
    } catch (err) {
      console.error("Failed to load prompts:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSavePrompt = async (promptKey: string) => {
    setLoading(true);
    try {
      const res = await fetch(
        apiUrl(`/api/profiles/${profileId}/prompts/${promptKey}`),
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value: editValue, model: editModel }),
        }
      );

      if (res.ok) {
        await loadPrompts();
        setEditingPrompt(null);
        setEditValue("");
      } else {
        const data = await res.json();
        alert(`Failed to save prompt: ${data.detail || "Unknown error"}`);
      }
    } catch (err) {
      console.error("Failed to save prompt:", err);
      alert("Failed to save prompt");
    } finally {
      setLoading(false);
    }
  };

  const handleResetPrompt = async (promptKey: string) => {
    if (!confirm("Reset this prompt to default?")) return;

    setLoading(true);
    try {
      const res = await fetch(
        apiUrl(`/api/profiles/${profileId}/prompts/${promptKey}`),
        {
          method: "DELETE",
        }
      );

      if (res.ok) {
        await loadPrompts();
      } else {
        const data = await res.json();
        alert(`Failed to reset prompt: ${data.detail || "Unknown error"}`);
      }
    } catch (err) {
      console.error("Failed to reset prompt:", err);
      alert("Failed to reset prompt");
    } finally {
      setLoading(false);
    }
  };

  const startEdit = (promptKey: string, currentValue: string, currentModel: string) => {
    setEditingPrompt(promptKey);
    setEditValue(currentValue);
    setEditModel(currentModel);
  };

  const cancelEdit = () => {
    setEditingPrompt(null);
    setEditValue("");
    setEditModel("");
  };

  // Group prompts by category
  const promptCategories = [
    {
      name: "Translation & Analysis",
      keys: ["PROMPT_TRANSLATION_SYSTEM", "PROMPT_TRANSLATION_USER"],
    },
    {
      name: "Primary Source Finding",
      keys: ["PROMPT_PRIMARY_SYSTEM", "PROMPT_PRIMARY_USER"],
    },
    {
      name: "Article Writing",
      keys: ["PROMPT_ARTICLE_SYSTEM", "PROMPT_ARTICLE_USER"],
    },
    {
      name: "Related Articles",
      keys: ["PROMPT_RELATED_SYSTEM", "PROMPT_RELATED_USER"],
    },
    {
      name: "Headline Translation",
      keys: ["PROMPT_HEADLINE_SYSTEM", "PROMPT_HEADLINE_USER"],
    },
    {
      name: "Yoast SEO Optimization",
      keys: ["PROMPT_YOAST_SYSTEM", "PROMPT_YOAST_USER"],
    },
    {
      name: "Tag Generation",
      keys: ["PROMPT_TAG_GEN_SYSTEM", "PROMPT_TAG_GEN_USER"],
    },
    {
      name: "Taxonomy Assignment",
      keys: ["PROMPT_TAXONOMY_SYSTEM", "PROMPT_TAXONOMY_USER"],
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold mb-2 text-slate-100">LLM Prompts</h2>
        <p className="text-sm text-slate-400">
          Customize the prompts used at each stage of article processing.
          System prompts set the overall behavior, User prompts provide specific instructions.
        </p>
      </div>

      {loading && <div className="text-center py-4 text-slate-300">Loading prompts...</div>}

      {!loading && (
        <div className="space-y-6">
          {promptCategories.map((category) => (
            <div key={category.name} className="border border-slate-700 rounded-lg p-4 bg-slate-800/30">
              <h3 className="font-medium mb-4 text-slate-100">{category.name}</h3>

              <div className="space-y-4">
                {category.keys.map((key) => {
                  const prompt = prompts[key];
                  if (!prompt) return null;

                  const isExpanded = expandedPrompt === key;
                  const isEditing = editingPrompt === key;
                  const promptName = key.replace("PROMPT_", "").replace(/_/g, " ");

                  return (
                    <div key={key} className="border-l-2 border-slate-600 pl-4">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() =>
                                setExpandedPrompt(isExpanded ? null : key)
                              }
                              className="text-sm font-medium text-slate-200 hover:text-blue-400"
                            >
                              {promptName}
                              {isExpanded ? " ▼" : " ▶"}
                            </button>
                            {prompt.is_custom && (
                              <span className="text-xs bg-yellow-500/20 text-yellow-300 px-2 py-0.5 rounded border border-yellow-500/30">
                                CUSTOM
                              </span>
                            )}
                            <span className="text-xs bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded border border-blue-500/30">
                              {availableModels.find(m => m.id === prompt.model)?.name || prompt.model}
                            </span>
                          </div>
                          {prompt.description && (
                            <p className="text-xs text-slate-400 mt-1">
                              {prompt.description}
                            </p>
                          )}
                        </div>

                        <div className="flex gap-2 ml-4">
                          {!isEditing && (
                            <>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => startEdit(key, prompt.value, prompt.model)}
                                disabled={loading}
                              >
                                Edit
                              </Button>
                              {prompt.is_custom && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => handleResetPrompt(key)}
                                  disabled={loading}
                                >
                                  Reset
                                </Button>
                              )}
                            </>
                          )}
                        </div>
                      </div>

                      {isExpanded && !isEditing && (
                        <div className="mt-2">
                          <pre className="text-xs bg-slate-900/50 p-3 rounded-lg border border-slate-700 overflow-x-auto whitespace-pre-wrap text-slate-300">
                            {prompt.value || "(empty)"}
                          </pre>
                        </div>
                      )}

                      {isEditing && (
                        <div className="mt-2 space-y-2">
                          <div className="mb-2">
                            <label className="block text-xs text-slate-400 mb-1">LLM Model:</label>
                            <select
                              className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-100"
                              value={editModel}
                              onChange={(e) => setEditModel(e.target.value)}
                            >
                              {availableModels.map((model) => (
                                <option key={model.id} value={model.id}>
                                  {model.name} ({model.provider})
                                </option>
                              ))}
                            </select>
                          </div>
                          <textarea
                            className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg font-mono text-sm text-slate-100 placeholder-slate-500"
                            rows={12}
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                          />
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={() => handleSavePrompt(key)}
                              disabled={loading}
                            >
                              Save
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={cancelEdit}
                              disabled={loading}
                            >
                              Cancel
                            </Button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
