import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../components/ui/button";
import ProfileManager from "../components/ProfileManager";
import PromptEditor from "../components/PromptEditor";

type ScanItem = {
  index: number;
  file_path: string;
  basename: string;
  article_no: string;
  headline_raw: string;
  headline_en_gb: string;
  language: string;
  is_duplicate: boolean;
  duplicate_reason?: string | null;
  fingerprint: string;
};

type RunItem = {
  file_path: string;
  status: string;
  wp_post_id?: number | null;
  wp_link?: string | null;
  link_report?: any | null;
  errors?: string[];
};

type StageItem = {
  key: string;
  display_name?: string;
  values?: Record<string, any>;
  defaults?: Record<string, any>;
};

type LogLine = {
  ts: string;
  level: string;
  msg: string;
  stage?: string | null;
  article_id?: string | null;
};

const defaultRoot =
  "/Users/m4owen/Library/CloudStorage/GoogleDrive-gunn0r@gmail.com/Shared drives/01.Player Clothing Team Drive/02. RetroShell/13. Articles and Data/09. Feed Finder";

export default function App() {
  const apiBase = (import.meta as any).env?.VITE_API_BASE_URL || "";
  const apiUrl = (path: string) =>
    apiBase ? `${apiBase}${path.startsWith("/") ? "" : "/"}${path}` : path;
  const fetchWithTimeout = async (
    input: RequestInfo,
    init: RequestInit & { timeoutMs?: number } = {}
  ) => {
    const { timeoutMs = 90000, ...rest } = init;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(input, { ...rest, signal: controller.signal });
    } finally {
      window.clearTimeout(timeoutId);
    }
  };

  const [paths, setPaths] = useState<string[]>([defaultRoot]);
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [advancedManual, setAdvancedManual] = useState(false);
  const [items, setItems] = useState<ScanItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadCount, setUploadCount] = useState<number | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [activeRoot, setActiveRoot] = useState<string | null>(null);
  const [settings, setSettings] = useState<any>({});
  const [stageSnapshots, setStageSnapshots] = useState<Record<string, any>>({});
  const [registry, setRegistry] = useState<any[]>([]);
  const [registryDomain, setRegistryDomain] = useState("");
  const [registryType, setRegistryType] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string>("idle");
  const [connectionStatus, setConnectionStatus] = useState<string>("disconnected");
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [logFilter, setLogFilter] = useState<string>("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [currentStage, setCurrentStage] = useState<string | null>(null);
  const [currentArticle, setCurrentArticle] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ total: number; success: number; failed: number; skipped: number }>({
    total: 0,
    success: 0,
    failed: 0,
    skipped: 0,
  });
  const [articleStatuses, setArticleStatuses] = useState<Record<string, any>>({});
  const logRef = useRef<HTMLDivElement | null>(null);
  const [logPath, setLogPath] = useState<string | null>(null);
  const [logTail, setLogTail] = useState<string[]>([]);
  const [logBytes, setLogBytes] = useState<number>(0);
  const [logUpdatedAt, setLogUpdatedAt] = useState<string | null>(null);
  const [logWarning, setLogWarning] = useState<string | null>(null);
  const [scanHistory, setScanHistory] = useState<any[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [runStartTime, setRunStartTime] = useState<number | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number>(0);
  const [translating, setTranslating] = useState(false);
  const [translationProgress, setTranslationProgress] = useState({ current: 0, total: 0 });
  const [translationStartTime, setTranslationStartTime] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [translationElapsed, setTranslationElapsed] = useState<number>(0);
  const [publishedArticles, setPublishedArticles] = useState<any[]>([]);
  const [showPublishedHistory, setShowPublishedHistory] = useState(false);
  const [publishedSortField, setPublishedSortField] = useState<string>('published_at');
  const [publishedSortOrder, setPublishedSortOrder] = useState<'asc' | 'desc'>('desc');
  const [quickArticleText, setQuickArticleText] = useState("");
  const [quickArticleUrl, setQuickArticleUrl] = useState("");
  const [quickArticleImage, setQuickArticleImage] = useState<File | null>(null);
  const [quickArticleContext, setQuickArticleContext] = useState("");
  const [quickArticleLoading, setQuickArticleLoading] = useState(false);
  const [quickArticleResult, setQuickArticleResult] = useState<any>(null);
  const [activeProfile, setActiveProfile] = useState<any>(null);
  const [showProfileSection, setShowProfileSection] = useState(false);
  const [showPromptsSection, setShowPromptsSection] = useState(false);
  const [allProfiles, setAllProfiles] = useState<any[]>([]);
  const [urlToProcess, setUrlToProcess] = useState("");
  const [urlContext, setUrlContext] = useState("");
  const [processingUrl, setProcessingUrl] = useState(false);
  const [urlProcessResult, setUrlProcessResult] = useState<any>(null);

  // Tab state for main navigation
  const [activeTab, setActiveTab] = useState<'dashboard' | 'articles' | 'settings'>('dashboard');

  // Sorting state for articles table
  const [articlesSortField, setArticlesSortField] = useState<string>('article_no');
  const [articlesSortOrder, setArticlesSortOrder] = useState<'asc' | 'desc'>('asc');

  const filtered = useMemo(() => {
    const filteredItems = items.filter((item) =>
      item.headline_en_gb.toLowerCase().includes(filter.toLowerCase())
    );

    // Sort the filtered items
    return [...filteredItems].sort((a, b) => {
      let aVal: any;
      let bVal: any;

      switch (articlesSortField) {
        case 'article_no':
          aVal = parseInt(a.article_no) || 0;
          bVal = parseInt(b.article_no) || 0;
          break;
        case 'headline_en_gb':
          aVal = a.headline_en_gb.toLowerCase();
          bVal = b.headline_en_gb.toLowerCase();
          break;
        case 'selected':
          aVal = selected.has(a.file_path) ? 1 : 0;
          bVal = selected.has(b.file_path) ? 1 : 0;
          break;
        case 'status':
          aVal = articleStatuses[a.file_path]?.status || 'idle';
          bVal = articleStatuses[b.file_path]?.status || 'idle';
          break;
        default:
          aVal = a.article_no;
          bVal = b.article_no;
      }

      const compare = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
      return articlesSortOrder === 'asc' ? compare : -compare;
    });
  }, [items, filter, articlesSortField, articlesSortOrder, selected, articleStatuses]);

  const filteredTail = useMemo(() => {
    if (logFilter === "all") return logTail;
    const token = logFilter === "error" ? "error" : "warn";
    return logTail.filter((line) => line.toLowerCase().includes(token));
  }, [logTail, logFilter]);

  const toggleSelect = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };


  const loadScanHistory = async () => {
    try {
      const res = await fetch(apiUrl("/api/scan-history"));
      const data = await res.json();
      setScanHistory(data.history || []);
    } catch (err) {
      console.error("Failed to load scan history:", err);
    }
  };

  const loadPublishedArticles = async () => {
    try {
      const res = await fetch(apiUrl("/api/published-articles?limit=50"));
      const data = await res.json();
      setPublishedArticles(data.articles || []);
    } catch (err) {
      console.error("Failed to load published articles:", err);
    }
  };

  const createQuickArticle = async () => {
    setQuickArticleLoading(true);
    setQuickArticleResult(null);

    try {
      const formData = new FormData();

      if (quickArticleText) {
        formData.append("text", quickArticleText);
      }
      if (quickArticleUrl) {
        formData.append("url", quickArticleUrl);
      }
      if (quickArticleImage) {
        formData.append("image", quickArticleImage);
      }
      if (quickArticleContext) {
        formData.append("additional_context", quickArticleContext);
      }

      const res = await fetch(apiUrl("/api/quick-article"), {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      setQuickArticleResult(data);

      if (data.success && data.file_path) {
        // Auto-scan to pick up the new quick article
        await scan();
      }
    } catch (err: any) {
      setQuickArticleResult({
        success: false,
        error: err.message || "Failed to create quick article"
      });
    } finally {
      setQuickArticleLoading(false);
    }
  };

  const processUrlToWordPress = async () => {
    setProcessingUrl(true);
    setUrlProcessResult(null);

    try {
      const res = await fetch(apiUrl("/api/process-url"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: urlToProcess,
          additional_context: urlContext
        }),
      });

      const data = await res.json();
      
      if (data.success && data.run_id) {
        setUrlProcessResult(data);
        setRunId(data.run_id);
        setUrlToProcess("");
        setUrlContext("");
      } else {
        setUrlProcessResult({
          success: false,
          error: data.detail || "Failed to process URL"
        });
      }
    } catch (err: any) {
      setUrlProcessResult({
        success: false,
        error: err.message || "Failed to process URL"
      });
    } finally {
      setProcessingUrl(false);
    }
  };

  const updateStageValues = (stageKey: string, nextValues: Record<string, any>) => {
    setSettings((prev: any) => {
      const stages = Array.isArray(prev.stages)
        ? prev.stages.map((stage: StageItem) =>
            stage.key === stageKey ? { ...stage, values: nextValues } : stage
          )
        : prev.stages;
      return { ...prev, stages };
    });
  };

  const [scanAbortController, setScanAbortController] = useState<AbortController | null>(null);
  const [runAbortController, setRunAbortController] = useState<AbortController | null>(null);

  const scan = async (overridePaths?: string[]) => {
    // Clear previous items immediately to avoid stale data
    setItems([]);
    setSelected(new Set());
    setArticleStatuses({});

    setLoading(true);
    setTranslating(true);
    setScanning(true);
    setScanError(null);
    setTranslationProgress({ current: 0, total: 0 });
    setTranslationStartTime(Date.now());

    // Create abort controller for this scan
    const abortController = new AbortController();
    setScanAbortController(abortController);

    const manualPaths = (overridePaths || paths)
      .map((path) => normaliseManualPath(path))
      .filter((path) => path.length > 0);

    try {
      // Check if aborted before starting
      if (abortController.signal.aborted) {
        throw new Error("Scan cancelled");
      }

      // Step 1: Scan for files
      const scanRes = await fetchWithTimeout(apiUrl("/api/rescan"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: advancedManual ? "manual" : "upload",
          paths: advancedManual ? manualPaths : [],
          skip_duplicates: skipDuplicates,
        }),
        timeoutMs: 90000,
      });

      if (abortController.signal.aborted) {
        throw new Error("Scan cancelled");
      }

      if (!scanRes.ok) {
        const payload = await scanRes.json();
        throw new Error(payload?.detail || "Scan failed.");
      }

      const scanData = await scanRes.json();
      const scannedItems = scanData.items || [];
      setActiveRoot(scanData.root || null);
      loadScanHistory();
      setScanning(false);

      // Step 2: Translate headlines with progress tracking
      setTranslationProgress({ current: 0, total: scannedItems.length });
      const filePaths = scannedItems.map((item: any) => item.file_path);
      const translatedResults: any[] = [];

      for (let i = 0; i < filePaths.length; i++) {
        // Check for abort before each translation
        if (abortController.signal.aborted) {
          throw new Error("Translation cancelled");
        }

        try {
          const translateRes = await fetchWithTimeout(apiUrl("/api/translate_headlines"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file_paths: [filePaths[i]] }),
            timeoutMs: 60000,
          });

          const translateData = await translateRes.json();
          if (translateData.translated && translateData.translated.length > 0) {
            translatedResults.push(translateData.translated[0]);
          }
          if (translateData.errors && translateData.errors.length > 0) {
            translateData.errors.forEach((err: any) => {
              console.error(`Translate error for ${err.file_path}: ${err.error}`);
            });
          }
        } catch (err) {
          console.error(`Failed to translate ${filePaths[i]}:`, err);
        }

        setTranslationProgress({ current: i + 1, total: filePaths.length });
      }

      // Update items with translated headlines
      const translationMap = new Map<string, string>();
      translatedResults.forEach((item: any) => {
        translationMap.set(item.file_path, item.headline_en_gb);
      });

      const updatedItems = scannedItems.map((item: any) => ({
        ...item,
        headline_en_gb: translationMap.get(item.file_path) || item.headline_en_gb,
      }));

      setItems(updatedItems);

    } catch (err: any) {
      const isCancelled = err.message?.includes("cancelled");
      const message = isCancelled
        ? "Operation cancelled."
        : err?.name === "AbortError"
          ? "Request timed out while scanning/translating. Try a smaller folder or check the API connection."
          : err.message || "Translation failed.";
      if (!isCancelled) {
        setScanError(message);
      }
    }

    setSelected(new Set());
    setLoading(false);
    setTranslating(false);
    setScanning(false);
    setTranslationStartTime(null);
    setScanAbortController(null);
  };

  const cancelScan = () => {
    if (scanAbortController) {
      scanAbortController.abort();
      setScanAbortController(null);
    }
  };

  const cancelRun = async () => {
    if (runId) {
      try {
        await fetch(apiUrl(`/api/runs/${runId}/cancel`), { method: "POST" });
        setRunStatus("cancelled");
        setRunAbortController(null);
      } catch (err) {
        console.error("Failed to cancel run:", err);
      }
    }
  };

  const clearArticles = () => {
    setItems([]);
    setSelected(new Set());
    setArticleStatuses({});
    setScanError(null);
  };

  const loadRegistry = async () => {
    const params = new URLSearchParams();
    if (registryDomain) params.append("domain", registryDomain);
    if (registryType) params.append("source_type", registryType);
    const res = await fetch(apiUrl(`/api/primary-sources?${params.toString()}`));
    const data = await res.json();
    setRegistry(data.entries || []);
  };

  const loadActiveProfile = async () => {
    try {
      const res = await fetch(apiUrl("/api/profiles/active"));
      if (res.ok) {
        const data = await res.json();
        setActiveProfile(data);
      }
    } catch (err) {
      console.error("Failed to load active profile:", err);
    }
  };

  const loadAllProfiles = async () => {
    try {
      const res = await fetch(apiUrl("/api/profiles"));
      const data = await res.json();
      setAllProfiles(data.profiles || []);
    } catch (err) {
      console.error("Failed to load profiles:", err);
    }
  };

  const translate = async () => {
    setLoading(true);
    const res = await fetch(apiUrl("/api/translate_headlines"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_paths: items.map((item) => item.file_path) }),
    });
    const data = await res.json();
    if (data.translated) {
      const map = new Map<string, string>();
      data.translated.forEach((row: any) => map.set(row.file_path, row.headline_en_gb));
      setItems((prev) =>
        prev.map((item) => ({
          ...item,
          headline_en_gb: map.get(item.file_path) || item.headline_en_gb,
        }))
      );
    }
    setLoading(false);
  };

  const run = async () => {
    setLoading(true);
    setRunStatus("starting");
    setLogLines([]);
    setLogTail([]);
    setLogPath(null);
    setLogBytes(0);
    setLogUpdatedAt(null);
    setLogWarning(null);
    setRunStartTime(Date.now());
    setCurrentStage(null);
    setCurrentArticle(null);
    setArticleStatuses(
      Array.from(selected).reduce((acc, path) => {
        acc[path] = { status: "pending" };
        return acc;
      }, {} as Record<string, any>)
    );
    setProgress({ total: selected.size, success: 0, failed: 0, skipped: 0 });
    try {
      const res = await fetch(apiUrl("/api/run"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_paths: Array.from(selected) }),
      });
      if (!res.ok) {
        const payload = await res.json();
        throw new Error(payload?.detail || "Run failed to start.");
      }
      const data = await res.json();
      setRunId(data.run_id);
      window.localStorage.setItem("agent0_run_id", data.run_id);
      setRunStatus("running");
    } catch (err: any) {
      setRunStatus("failed");
      setScanError(err.message || "Run failed to start.");
    } finally {
      setLoading(false);
    }
  };

  const normaliseManualPath = (value: string) => {
    const trimmed = value.trim();
    if (
      (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
      (trimmed.startsWith("'") && trimmed.endsWith("'"))
    ) {
      return trimmed.slice(1, -1);
    }
    return trimmed;
  };

  const isValidArticleFile = (relPath: string): boolean => {
    const lowerPath = relPath.toLowerCase();

    // Check if it's a JSON or Markdown file
    const isJson = lowerPath.endsWith(".json");
    const isMarkdown = lowerPath.endsWith(".md") || lowerPath.endsWith(".markdown");

    if (!isJson && !isMarkdown) return false;

    // Exclude specific patterns
    if (lowerPath.endsWith(".json.wp.json")) return false;
    if (lowerPath.endsWith(".json.research.md")) return false;
    if (lowerPath.includes(".research")) return false;
    if (lowerPath.includes("primary_sources_registry")) return false;
    if (lowerPath.includes("primary_source_log")) return false;
    if (lowerPath.includes("used_keyphrases")) return false;
    if (lowerPath.includes("config.json")) return false;
    if (lowerPath.includes("processing_report.json")) return false;

    return true;
  };

  const collectFileList = async (files: FileList | File[]) => {
    const collected: { file: File; relPath: string }[] = [];
    const list = Array.from(files);
    for (const file of list) {
      const relPath = (file as any).webkitRelativePath || file.name;
      if (isValidArticleFile(relPath)) {
        collected.push({ file, relPath });
      }
    }
    return collected;
  };

  const uploadFiles = async (files: { file: File; relPath: string }[]) => {
    if (files.length === 0) {
      setUploadError("No JSON or Markdown files found in the selected folders.");
      setUploadCount(0);
      return;
    }
    
    console.log(`[UPLOAD] Starting upload of ${files.length} files`);
    setUploading(true);
    setUploadError(null);
    setUploadCount(null);
    setScanError(null);
    
    const form = new FormData();
    files.forEach(({ file, relPath }) => {
      form.append("files", file, relPath);
    });
    
    try {
      console.log('[UPLOAD] Sending files to server...');
      const res = await fetch(apiUrl("/api/upload"), {
        method: "POST",
        body: form,
      });
      
      if (!res.ok) {
        const payload = await res.json();
        const errorMsg = payload?.detail || "Upload failed.";
        console.error(`[UPLOAD] Server error: ${errorMsg}`);
        throw new Error(errorMsg);
      }
      
      const data = await res.json();
      console.log('[UPLOAD] Server response:', data);
      
      setUploadCount(data.saved_count || 0);
      setActiveRoot(data.root || null);
      setAdvancedManual(false);
      setSettings((prev: any) => ({ ...prev, scan_mode: "upload" }));
      
      // Display any errors from the upload
      if (data.errors && data.errors.length > 0) {
        const errorSummary = `Upload completed with warnings: ${data.errors.slice(0, 3).join('; ')}`;
        console.warn('[UPLOAD]', errorSummary);
        setScanError(errorSummary);
      }
      
      // If files were uploaded but scan failed, show what we have
      if (data.saved_count > 0 && data.scanned_items === 0 && data.errors) {
        setScanError(`${data.saved_count} files uploaded but scan failed. Check server logs.`);
      }
      
      console.log(`[UPLOAD] Success: ${data.saved_count} files saved, ${data.scanned_items} items scanned`);
      
      // Trigger a fresh scan to update the UI
      await scan();
    } catch (err: any) {
      const errorMsg = err.message || "Upload failed.";
      console.error('[UPLOAD] Error:', errorMsg);
      setUploadError(errorMsg);
    } finally {
      setUploading(false);
    }
  };

  const handleDirectoryPicker = async () => {
    setUploadError(null);
    setScanError(null);
    console.log('[PICKER] Opening directory picker...');
    
    const windowAny: any = window;
    if (windowAny.showDirectoryPicker) {
      try {
        const dirHandle = await windowAny.showDirectoryPicker();
        console.log('[PICKER] Directory selected, collecting files...');
        
        const files: { file: File; relPath: string }[] = [];
        const walk = async (handle: any, prefix: string) => {
          for await (const entry of handle.values()) {
            if (entry.kind === "file") {
              const file = await entry.getFile();
              const relPath = `${prefix}${entry.name}`;
              files.push({ file, relPath });
            } else if (entry.kind === "directory") {
              await walk(entry, `${prefix}${entry.name}/`);
            }
          }
        };
        await walk(dirHandle, "");
        
        console.log(`[PICKER] Collected ${files.length} total files`);
        const filtered = files.filter(({ relPath }) => isValidArticleFile(relPath));
        console.log(`[PICKER] Filtered to ${filtered.length} article files`);
        
        if (filtered.length === 0) {
          setUploadError("No valid article files (.json, .md, .markdown) found in the selected folder.");
          return;
        }
        
        await uploadFiles(filtered);
      } catch (err: any) {
        if (err?.name !== "AbortError") {
          const errorMsg = err.message || "Folder selection failed.";
          console.error('[PICKER] Error:', errorMsg);
          setUploadError(errorMsg);
        } else {
          console.log('[PICKER] User cancelled selection');
        }
      }
      return;
    }
    
    // Fallback for browsers without showDirectoryPicker
    console.log('[PICKER] Using fallback file input method');
    const input = document.createElement("input");
    input.type = "file";
    (input as any).webkitdirectory = true;
    input.multiple = true;
    input.onchange = async () => {
      if (input.files) {
        console.log(`[PICKER] Selected ${input.files.length} files via input`);
        const files = await collectFileList(input.files);
        console.log(`[PICKER] Collected ${files.length} valid article files`);
        
        if (files.length === 0) {
          setUploadError("No valid article files (.json, .md, .markdown) found in the selected folder.");
          return;
        }
        
        await uploadFiles(files);
      }
    };
    input.click();
  };

  const handleDrop = async (event: React.DragEvent) => {
    event.preventDefault();
    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      const collected = await collectFileList(files);
      await uploadFiles(collected);
    }
  };

  useEffect(() => {
    (async () => {
      const res = await fetch(apiUrl("/api/settings"));
      const data = await res.json();
      setSettings(data);
      const stageMap: Record<string, any> = {};
      const stages = Array.isArray(data.stages) ? data.stages : [];
      stages.forEach((stage: StageItem) => {
        stageMap[stage.key] = stage.values || {};
      });
      setStageSnapshots(stageMap);
      if (data.root_path) {
        setPaths([data.root_path]);
      }
      if (typeof data.skip_duplicates === "boolean") {
        setSkipDuplicates(data.skip_duplicates);
      }
      setActiveRoot(data.active_scan_root || null);
      setAdvancedManual(data.scan_mode === "manual");
      // Don't auto-scan on mount - user must click "Translate Headlines"
      loadRegistry();
      loadActiveProfile();
      loadAllProfiles();
      loadScanHistory(); 
      loadPublishedArticles(); // Load published articles history on mount
      loadActiveProfile(); // Load active profile on mount

      const storedRunId = window.localStorage.getItem("agent0_run_id");
      if (storedRunId) {
        setRunId(storedRunId);
        fetch(apiUrl(`/api/runs/${storedRunId}`))
          .then((resp) => resp.json())
          .then((payload) => {
            if (payload.run?.status) {
              setRunStatus(payload.run.status);
            }
            if (Array.isArray(payload.items)) {
              const statusMap: Record<string, any> = {};
              payload.items.forEach((item: any) => {
                statusMap[item.file_path] = {
                  status: item.status,
                  wp_post_id: item.wp_post_id,
                  wp_url: item.wp_link,
                  error: item.errors ? JSON.parse(item.errors || "[]").join("; ") : null,
                };
              });
              setArticleStatuses(statusMap);
            }
          })
          .catch(() => null);
      }
    })();
  }, []);

  useEffect(() => {
    if (!runId) return;
    setConnectionStatus("connecting");
    const eventsUrl = apiUrl(`/api/runs/${runId}/events`);
    const source = new EventSource(eventsUrl);
    let startTimer = window.setTimeout(() => {
      if (logLines.length === 0) {
        setLogLines((prev) => [
          ...prev,
          { ts: new Date().toISOString(), level: "info", msg: "Starting pipeline…" },
        ]);
      }
    }, 3000);

    source.addEventListener("log", (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      setLogLines((prev) => [...prev, data]);
      if (data.stage) {
        setCurrentStage(data.stage);
      }
      if (data.article_id) {
        setCurrentArticle(data.article_id);
      }
    });

    source.addEventListener("status", (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      setRunStatus(data.run_status || "running");
      if (data.progress) {
        setProgress(data.progress);
      }
      if (data.run_status === "done" || data.run_status === "failed") {
        setConnectionStatus("disconnected");
        loadRegistry();
        loadPublishedArticles();
        fetch(apiUrl("/api/runs"))
          .then((res) => res.json())
          .then((payload) => setRuns(payload.items || []))
          .catch(() => null);
      }
    });

    source.addEventListener("article", (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      setArticleStatuses((prev) => ({
        ...prev,
        [data.article_id]: {
          status: data.status,
          wp_post_id: data.wp_post_id,
          wp_url: data.wp_url,
          error: data.error,
        },
      }));
    });

    source.addEventListener("heartbeat", () => {});

    source.onopen = () => {
      window.clearTimeout(startTimer);
      setConnectionStatus("connected");
    };
    source.onerror = () => {
      setConnectionStatus("reconnecting");
    };

    return () => {
      source.close();
      window.clearTimeout(startTimer);
      setConnectionStatus("disconnected");
    };
  }, [runId]);

  useEffect(() => {
    if (!autoScroll) return;
    const node = logRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [logLines, autoScroll]);

  useEffect(() => {
    if (!runId) return;
    let timer: number | undefined;
    let lastBytes = logBytes;
    let lastUpdate = logUpdatedAt ? new Date(logUpdatedAt).getTime() : Date.now();

    const poll = async () => {
      try {
        const res = await fetch(apiUrl(`/api/runs/${runId}/log?lines=40`));
        if (!res.ok) {
          return;
        }
        const data = await res.json();
        if (Array.isArray(data.tail_lines)) {
          setLogTail(data.tail_lines);
        }
        setLogPath(data.path || null);
        setLogBytes(data.size_bytes || 0);
        setLogUpdatedAt(data.last_modified || null);
        if ((data.size_bytes || 0) !== lastBytes) {
          lastBytes = data.size_bytes || 0;
          lastUpdate = Date.now();
          setLogWarning(null);
        } else if (runStatus === "running") {
          const elapsed = (Date.now() - lastUpdate) / 1000;
          if (elapsed > 120) {
            setLogWarning("No progress detected for 120s — check network/API keys.");
          }
        }
      } catch {
        return;
      }
    };
    poll();
    timer = window.setInterval(poll, 1500);
    return () => {
      if (timer) {
        window.clearInterval(timer);
      }
    };
  }, [runId, runStatus]);

  useEffect(() => {
    if (runStatus === "running" && runStartTime) {
      const interval = window.setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - runStartTime) / 1000));
      }, 1000);
      return () => window.clearInterval(interval);
    }
  }, [runStatus, runStartTime]);

  useEffect(() => {
    if (translating && translationStartTime) {
      const interval = window.setInterval(() => {
        setTranslationElapsed(Math.floor((Date.now() - translationStartTime) / 1000));
      }, 1000);
      return () => window.clearInterval(interval);
    }
  }, [translating, translationStartTime]);

  // Helper function to handle article column sorting
  const handleArticleSort = (field: string) => {
    if (articlesSortField === field) {
      setArticlesSortOrder(articlesSortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setArticlesSortField(field);
      setArticlesSortOrder('asc');
    }
  };

  // Render sort indicator
  const renderSortIndicator = (field: string) => {
    if (articlesSortField !== field) return null;
    return <span className="ml-1">{articlesSortOrder === 'asc' ? '↑' : '↓'}</span>;
  };

  return (
    <div className="min-h-screen px-10 py-8">
      <header className="flex items-center justify-between mb-6">
        <div>
          <p className="text-sm text-slate-400">Extract'n'Source'n'Write'n'Enhance'n'publish</p>
          <h1 className="text-3xl font-display font-semibold">Agent 0 Control Room</h1>
        </div>
        <div className="flex items-center gap-4">
          {activeProfile && activeProfile.profile && (
            <div className="flex items-center gap-3 bg-slate-800/50 border border-slate-700 rounded-lg px-4 py-2">
              <span className="text-sm text-slate-400">Profile:</span>
              <select
                className="bg-slate-900 border border-slate-600 rounded px-3 py-1 text-sm font-medium text-blue-400"
                value={activeProfile.profile.id}
                onChange={async (e) => {
                  const profileId = parseInt(e.target.value);
                  try {
                    await fetch(apiUrl(`/api/profiles/${profileId}/activate`), {
                      method: "POST"
                    });
                    await loadActiveProfile();
                    await loadAllProfiles();
                    scan();
                  } catch (err) {
                    console.error("Failed to switch profile:", err);
                  }
                }}
              >
                {allProfiles.map((profile) => (
                  <option key={profile.id} value={profile.id}>
                    {profile.name}
                  </option>
                ))}
              </select>
              <span className="text-xs text-slate-500">
                {activeProfile.input_dir} → {activeProfile.output_dir}
              </span>
            </div>
          )}
        </div>
      </header>

      {/* Main Tab Navigation */}
      <nav className="flex gap-1 mb-6 border-b border-slate-700">
        <button
          className={`px-6 py-3 text-sm font-medium transition-colors ${
            activeTab === 'dashboard'
              ? 'text-accent-2 border-b-2 border-accent-2 -mb-px'
              : 'text-slate-400 hover:text-white'
          }`}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={`px-6 py-3 text-sm font-medium transition-colors flex items-center gap-2 ${
            activeTab === 'articles'
              ? 'text-accent-2 border-b-2 border-accent-2 -mb-px'
              : 'text-slate-400 hover:text-white'
          }`}
          onClick={() => setActiveTab('articles')}
        >
          Articles
          {items.length > 0 && (
            <span className="bg-slate-700 text-slate-300 text-xs px-2 py-0.5 rounded-full">
              {items.length}
            </span>
          )}
          {selected.size > 0 && (
            <span className="bg-emerald-600 text-white text-xs px-2 py-0.5 rounded-full">
              {selected.size} selected
            </span>
          )}
        </button>
        <button
          className={`px-6 py-3 text-sm font-medium transition-colors ${
            activeTab === 'settings'
              ? 'text-accent-2 border-b-2 border-accent-2 -mb-px'
              : 'text-slate-400 hover:text-white'
          }`}
          onClick={() => setActiveTab('settings')}
        >
          Settings
        </button>
      </nav>

      {/* Dashboard Tab */}
      {activeTab === 'dashboard' && (
        <>
      <section className="glass p-6 rounded-2xl mb-8">
        <h2 className="text-lg font-semibold mb-4">Quick Article Creator</h2>
        <p className="text-sm text-slate-400 mb-4">
          Create an article from a URL, image, or text snippet. The system will research primary sources and generate a complete article.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Text or Email Content</label>
            <textarea
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 min-h-[120px]"
              placeholder="Paste email text or article content here..."
              value={quickArticleText}
              onChange={(e) => setQuickArticleText(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Additional Context (Optional)</label>
            <textarea
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 min-h-[120px]"
              placeholder="Add context, background info, or specific instructions..."
              value={quickArticleContext}
              onChange={(e) => setQuickArticleContext(e.target.value)}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 mt-4">
          <div>
            <label className="block text-sm font-medium mb-2">Source URL</label>
            <input
              type="url"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
              placeholder="https://example.com/article"
              value={quickArticleUrl}
              onChange={(e) => setQuickArticleUrl(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Upload Image (OCR)</label>
            <input
              type="file"
              accept="image/*"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm"
              onChange={(e) => setQuickArticleImage(e.target.files?.[0] || null)}
            />
          </div>
        </div>
        <div className="flex gap-3 mt-4">
          <Button
            className="bg-emerald-600 text-white hover:bg-emerald-700 px-6 py-2"
            onClick={createQuickArticle}
            disabled={quickArticleLoading || (!quickArticleText && !quickArticleUrl && !quickArticleImage)}
          >
            {quickArticleLoading ? "Creating..." : "Create Article"}
          </Button>
          <Button
            className="bg-slate-700 text-white hover:bg-slate-600 px-6 py-2"
            onClick={() => {
              setQuickArticleText("");
              setQuickArticleUrl("");
              setQuickArticleImage(null);
              setQuickArticleContext("");
              setQuickArticleResult(null);
            }}
          >
            Clear
          </Button>
        </div>
        {quickArticleResult && (
          <div className={`mt-4 p-4 rounded-lg ${quickArticleResult.success ? 'bg-emerald-900/30 border border-emerald-500/50' : 'bg-rose-900/30 border border-rose-500/50'}`}>
            {quickArticleResult.success ? (
              <div>
                <p className="text-emerald-300 font-semibold mb-2">✓ {quickArticleResult.message}</p>
                <p className="text-sm text-slate-300">
                  File created: <span className="font-mono text-xs">{quickArticleResult.file_path}</span>
                </p>
                <p className="text-sm text-slate-400 mt-2">
                  The article has been added to your queue. Select it below and click "Build & Publish to WordPress" to process it.
                </p>
              </div>
            ) : (
              <div>
                <p className="text-rose-300 font-semibold mb-2">✗ Error</p>
                <p className="text-sm text-slate-300">{quickArticleResult.error}</p>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="glass p-6 rounded-2xl mb-8">
        <h2 className="text-lg font-semibold mb-4">URL to WordPress (Direct Pipeline)</h2>
        <p className="text-sm text-slate-400 mb-4">
          Process a URL directly to WordPress draft. The system will extract content, find sources, and publish automatically.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Article URL</label>
            <input
              type="url"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
              placeholder="https://example.com/news-article"
              value={urlToProcess}
              onChange={(e) => setUrlToProcess(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Additional Context (Optional)</label>
            <input
              type="text"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
              placeholder="Add any specific instructions..."
              value={urlContext}
              onChange={(e) => setUrlContext(e.target.value)}
            />
          </div>
        </div>
        <div className="flex gap-3 mt-4">
          <Button
            className="bg-blue-600 text-white hover:bg-blue-700 px-6 py-2"
            onClick={processUrlToWordPress}
            disabled={processingUrl || !urlToProcess}
          >
            {processingUrl ? "Processing..." : "Process & Publish to WordPress"}
          </Button>
          <Button
            className="bg-slate-700 text-white hover:bg-slate-600 px-6 py-2"
            onClick={() => {
              setUrlToProcess("");
              setUrlContext("");
              setUrlProcessResult(null);
            }}
          >
            Clear
          </Button>
        </div>
        {urlProcessResult && (
          <div className={`mt-4 p-4 rounded-lg ${urlProcessResult.success ? 'bg-emerald-900/30 border border-emerald-500/50' : 'bg-rose-900/30 border border-rose-500/50'}`}>
            {urlProcessResult.success ? (
              <div>
                <p className="text-emerald-300 font-semibold mb-2">✓ {urlProcessResult.message}</p>
                <p className="text-sm text-slate-300">
                  Run ID: <span className="font-mono text-xs">{urlProcessResult.run_id}</span>
                </p>
                <p className="text-sm text-slate-400 mt-2">
                  Processing started. Check the Run Console below for progress.
                </p>
              </div>
            ) : (
              <div>
                <p className="text-rose-300 font-semibold mb-2">✗ Error</p>
                <p className="text-sm text-slate-300">{urlProcessResult.error}</p>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="grid grid-cols-3 gap-6 mb-8">
        <div className="glass p-6 rounded-2xl col-span-2">
          <h2 className="text-lg font-semibold mb-4">Scan Source</h2>
          <div
            className="border border-dashed border-slate-600 rounded-2xl p-6 text-center mb-4"
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <p className="text-slate-300 mb-3">
              Drag folders or JSON files here, or choose folders to upload.
            </p>
            <Button className="bg-accent text-black hover:bg-accent" onClick={handleDirectoryPicker}>
              Choose folder(s)
            </Button>
            <p className="text-xs text-slate-500 mt-3">
              Uploaded files are stored locally in the workspace for scanning.
            </p>
          </div>
          {uploading && (
            <div className="bg-blue-900/30 border border-blue-500/50 rounded-lg p-4 mb-4">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-400"></div>
                <div>
                  <p className="text-blue-300 font-semibold">Uploading files...</p>
                  <p className="text-sm text-slate-400">Please wait while files are being uploaded and scanned</p>
                </div>
              </div>
            </div>
          )}
          {uploadCount !== null && !uploading && (
            <div className="bg-emerald-900/30 border border-emerald-500/50 rounded-lg p-4 mb-4">
              <p className="text-emerald-300 font-semibold">✓ Upload Complete</p>
              <p className="text-sm text-slate-300">Successfully uploaded {uploadCount} file{uploadCount !== 1 ? 's' : ''}</p>
            </div>
          )}
          {uploadError && (
            <div className="bg-rose-900/30 border border-rose-500/50 rounded-lg p-4 mb-4">
              <p className="text-rose-300 font-semibold">✗ Upload Error</p>
              <p className="text-sm text-slate-300">{uploadError}</p>
              <p className="text-xs text-slate-400 mt-2">Check browser console (F12) for detailed logs</p>
            </div>
          )}
          {scanError && !uploadError && (
            <div className="bg-amber-900/30 border border-amber-500/50 rounded-lg p-4 mb-4">
              <p className="text-amber-300 font-semibold">⚠ Warning</p>
              <p className="text-sm text-slate-300">{scanError}</p>
            </div>
          )}
          <div className="mt-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={advancedManual}
                onChange={(e) => setAdvancedManual(e.target.checked)}
              />
              Advanced: Manual path
            </label>
          </div>
          {advancedManual && (
            <div className="mt-4">
              {paths.map((path, idx) => (
                <div key={idx} className="flex gap-2 mb-2">
                  <input
                    className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
                    value={path}
                    onChange={(e) => {
                      const next = [...paths];
                      next[idx] = e.target.value;
                      setPaths(next);
                    }}
                  />
                  <Button onClick={() => setPaths(paths.filter((_, i) => i !== idx))}>Remove</Button>
                </div>
              ))}
              <div className="flex gap-3 mt-2">
                <Button onClick={() => setPaths([...paths, ""])}>Add Path</Button>
              </div>
            </div>
          )}
          {scanning && (
            <div className="bg-blue-900/30 border border-blue-500/50 rounded-lg p-4 mb-4">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-400"></div>
                <div>
                  <p className="text-blue-300 font-semibold">Scanning directory...</p>
                  <p className="text-sm text-slate-400">Searching for article files</p>
                </div>
              </div>
            </div>
          )}
          {translating && (
            <div className="bg-purple-900/30 border border-purple-500/50 rounded-lg p-4 mb-4">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-purple-400"></div>
                <div>
                  <p className="text-purple-300 font-semibold">Translating headlines...</p>
                  <p className="text-sm text-slate-400">
                    {translationProgress.current} / {translationProgress.total} articles
                    {translationElapsed > 0 && ` (${translationElapsed}s)`}
                  </p>
                </div>
              </div>
            </div>
          )}
          <div className="flex gap-3 mt-4 items-center">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={skipDuplicates}
                onChange={(e) => {
                  setSkipDuplicates(e.target.checked);
                  setSettings((prev: any) => ({ ...prev, skip_duplicates: e.target.checked }));
                }}
              />
              Skip duplicates
            </label>
            <Button
              className="bg-accent-2 text-black hover:bg-accent px-4 py-2 ml-auto"
              onClick={() => scan()}
              disabled={translating || loading}
            >
              {translating ? "Translating..." : "Translate Headlines"}
            </Button>
            {activeRoot && (
              <span className="text-xs text-slate-400">Current scan root: {activeRoot}</span>
            )}
          </div>
          {translating && (
            <div className="mt-4 p-4 bg-slate-900 rounded-lg border border-blue-500/50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-blue-400">
                  {scanning
                    ? "Scanning files..."
                    : `Translating headline ${translationProgress.current}/${translationProgress.total}`
                  }
                </span>
                {!scanning && translationProgress.total > 0 && (
                  <span className="text-xs font-mono text-slate-300">
                    {Math.round((translationProgress.current / translationProgress.total) * 100)}%
                  </span>
                )}
              </div>
              <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${scanning ? 'bg-blue-500 animate-pulse' : 'bg-blue-500'}`}
                  style={{
                    width: scanning ? "100%" : (
                      translationProgress.total > 0
                        ? `${(translationProgress.current / translationProgress.total) * 100}%`
                        : "0%"
                    )
                  }}
                />
              </div>
              <div className="flex items-center justify-between mt-2 text-xs">
                <div className="flex gap-4">
                  <span className="text-slate-400">
                    Time elapsed: <span className="text-slate-200 font-mono">
                      {translationStartTime ? (() => {
                        const seconds = Math.floor((Date.now() - translationStartTime) / 1000);
                        const mins = Math.floor(seconds / 60);
                        const secs = seconds % 60;
                        return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                      })() : '0s'}
                    </span>
                  </span>
                  {!scanning && translationProgress.current > 0 && translationProgress.total > translationProgress.current && (
                    <span className="text-slate-400">
                      Remaining: <span className="text-slate-200 font-mono">
                        {(() => {
                          const avgTime = (Date.now() - (translationStartTime || Date.now())) / translationProgress.current;
                          const remainingSeconds = Math.floor((avgTime * (translationProgress.total - translationProgress.current)) / 1000);
                          const mins = Math.floor(remainingSeconds / 60);
                          const secs = remainingSeconds % 60;
                          return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                        })()}
                      </span>
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  {!scanning && translationProgress.current > 0 && (
                    <span className="text-slate-500 text-xs">
                      ~{Math.round((Date.now() - (translationStartTime || Date.now())) / translationProgress.current / 1000)}s per headline
                    </span>
                  )}
                  <Button
                    className="text-xs px-3 py-1 bg-red-600 hover:bg-red-500 text-white"
                    onClick={cancelScan}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
        <div className="glass p-6 rounded-2xl">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Queue Summary</h2>
            <Button
              className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600"
              onClick={clearArticles}
              disabled={items.length === 0}
            >
              Clear List
            </Button>
          </div>
          <p className="text-slate-300">Scanned: {items.length}</p>
          <p className="text-slate-300">Selected: {selected.size}</p>
          <p className="text-slate-400 text-xs">
            Run status: {runStatus} • Connection: {connectionStatus}
          </p>
          <div className="mt-4 space-y-3">
            <div>
              <button
                className="text-sm text-accent-2 underline"
                onClick={() => setShowHistory(!showHistory)}
              >
                {showHistory ? "Hide" : "Show"} Scan History ({scanHistory.length})
              </button>
              {showHistory && (
                <div className="mt-2 max-h-40 overflow-y-auto bg-slate-900 rounded p-2">
                  {scanHistory.length === 0 ? (
                    <p className="text-xs text-slate-500">No scan history yet</p>
                  ) : (
                    <div className="space-y-1">
                      {scanHistory.map((entry: any) => (
                        <div key={entry.id} className="text-xs text-slate-400 border-b border-slate-800 pb-1">
                          <div className="flex justify-between">
                            <span className="font-mono truncate flex-1" title={entry.folder_path}>
                              {entry.folder_path.split('/').slice(-2).join('/')}
                            </span>
                            <span className="text-slate-500 ml-2">{entry.item_count} items</span>
                          </div>
                          <div className="text-slate-600 text-xs">
                            {new Date(entry.scanned_at).toLocaleString()} • {entry.scan_mode}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            <div>
              <button
                className="text-sm text-emerald-400 underline"
                onClick={() => setShowPublishedHistory(!showPublishedHistory)}
              >
                {showPublishedHistory ? "Hide" : "Show"} Published Articles ({publishedArticles.length})
              </button>
              {showPublishedHistory && (
                <div className="mt-2 max-h-96 overflow-y-auto bg-slate-900 rounded">
                  {publishedArticles.length === 0 ? (
                    <p className="text-xs text-slate-500 p-2">No published articles yet</p>
                  ) : (
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-slate-800 border-b border-slate-700">
                        <tr>
                          <th 
                            className="text-left p-2 cursor-pointer hover:bg-slate-700 transition-colors"
                            onClick={() => {
                              if (publishedSortField === 'english_headline') {
                                setPublishedSortOrder(publishedSortOrder === 'asc' ? 'desc' : 'asc');
                              } else {
                                setPublishedSortField('english_headline');
                                setPublishedSortOrder('asc');
                              }
                            }}
                          >
                            <span className="flex items-center gap-1">
                              Article
                              {publishedSortField === 'english_headline' && (
                                <span>{publishedSortOrder === 'asc' ? '↑' : '↓'}</span>
                              )}
                            </span>
                          </th>
                          <th 
                            className="text-left p-2 cursor-pointer hover:bg-slate-700 transition-colors"
                            onClick={() => {
                              if (publishedSortField === 'wp_post_id') {
                                setPublishedSortOrder(publishedSortOrder === 'asc' ? 'desc' : 'asc');
                              } else {
                                setPublishedSortField('wp_post_id');
                                setPublishedSortOrder('asc');
                              }
                            }}
                          >
                            <span className="flex items-center gap-1">
                              ID
                              {publishedSortField === 'wp_post_id' && (
                                <span>{publishedSortOrder === 'asc' ? '↑' : '↓'}</span>
                              )}
                            </span>
                          </th>
                          <th 
                            className="text-left p-2 cursor-pointer hover:bg-slate-700 transition-colors"
                            onClick={() => {
                              if (publishedSortField === 'published_at') {
                                setPublishedSortOrder(publishedSortOrder === 'asc' ? 'desc' : 'asc');
                              } else {
                                setPublishedSortField('published_at');
                                setPublishedSortOrder('desc');
                              }
                            }}
                          >
                            <span className="flex items-center gap-1">
                              Published
                              {publishedSortField === 'published_at' && (
                                <span>{publishedSortOrder === 'asc' ? '↑' : '↓'}</span>
                              )}
                            </span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                      {[...publishedArticles].sort((a, b) => {
                        const aVal = a[publishedSortField];
                        const bVal = b[publishedSortField];
                        const compare = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
                        return publishedSortOrder === 'asc' ? compare : -compare;
                      }).map((article: any) => (
                        <tr key={article.id} className="border-t border-slate-800 hover:bg-slate-800/50">
                          <td className="p-2">
                            <div className="font-medium text-emerald-300 leading-tight">
                              {article.english_headline || article.headline}
                            </div>
                            {article.primary_keyword && (
                              <div className="text-blue-400 text-xs mt-1">
                                🔑 {article.primary_keyword}
                              </div>
                            )}
                          </td>
                          <td className="p-2 text-slate-400">
                            <a
                              className="text-emerald-400 underline hover:text-emerald-300"
                              href={article.wp_url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {article.wp_post_id}
                            </a>
                          </td>
                          <td className="p-2 text-slate-400">
                            {new Date(article.published_at).toLocaleString()}
                          </td>
                        </tr>
                      ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          </div>
          {runStatus === "running" && runStartTime && (
            <div className="mt-4 p-3 bg-slate-900 rounded-lg border border-slate-700">
              <div className="text-xs space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Status:</span>
                  <div className="flex items-center gap-2">
                    <span className="text-accent-2 font-semibold">Processing</span>
                    <Button
                      className="text-xs px-2 py-0.5 bg-red-600 hover:bg-red-500 text-white"
                      onClick={cancelRun}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Elapsed:</span>
                  <span className="text-slate-200 font-mono">
                    {Math.floor(elapsedTime / 60)}:{String(elapsedTime % 60).padStart(2, '0')}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-400">Progress:</span>
                  <span className="text-slate-200 font-semibold">
                    {progress.success + progress.failed}/{progress.total} articles
                  </span>
                </div>
                {currentStage && (
                  <div className="flex justify-between items-center">
                    <span className="text-slate-400">Stage:</span>
                    <span className="text-blue-400 font-medium capitalize">{currentStage}</span>
                  </div>
                )}
                {currentArticle && (
                  <div className="mt-2 pt-2 border-t border-slate-800">
                    <span className="text-slate-400 text-xs">Current:</span>
                    <p className="text-slate-300 text-xs mt-1 truncate font-mono" title={currentArticle}>
                      {currentArticle.split('/').pop()}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
          <div className="mt-3 h-2 w-full rounded-full bg-slate-800">
            <div
              className="h-2 rounded-full bg-emerald-500"
              style={{
                width:
                  progress.total === 0
                    ? "0%"
                    : `${Math.min(
                        100,
                        ((progress.success + progress.failed) / progress.total) * 100
                      )}%`,
              }}
            />
          </div>
          <Button
            className="mt-6 w-full py-3 rounded-xl bg-accent-2 text-black font-semibold"
            onClick={run}
            disabled={loading || translating || selected.size === 0 || runStatus === "running"}
          >
            {runStatus === "running" ? "Running…" : "Build & Publish to WordPress"}
          </Button>
        </div>
      </section>

      <section className="mt-8 glass p-6 rounded-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Run Console</h2>
          <div className="flex gap-2">
            <Button onClick={() => setLogFilter("all")}>All</Button>
            <Button onClick={() => setLogFilter("warn")}>Warnings</Button>
            <Button onClick={() => setLogFilter("error")}>Errors</Button>
          </div>
        </div>
        <div className="text-xs text-slate-400 mb-3">
          Processing {progress.success + progress.failed}/{progress.total} • Current:{" "}
          {currentArticle || "—"} • Stage: {currentStage || "—"}
        </div>
        <div className="flex gap-2 mb-3">
          <Button onClick={() => setLogLines([])}>Clear</Button>
          <Button onClick={() => setAutoScroll((prev) => !prev)}>
            {autoScroll ? "Pause" : "Resume"}
          </Button>
          <Button
            onClick={() => {
              const blob = new Blob(
                [filteredTail.join("\n")],
                { type: "text/plain" }
              );
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = `run-${runId || "log"}.txt`;
              link.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download log
          </Button>
          <Button
            onClick={() => navigator.clipboard.writeText(filteredTail.join("\n"))}
          >
            Copy log
          </Button>
        </div>
        {logPath && <div className="text-xs text-slate-500 mb-2">worker.log: {logPath}</div>}
        {logWarning && <div className="text-xs text-amber-300 mb-2">{logWarning}</div>}
        <div
          ref={logRef}
          className="max-h-[320px] overflow-auto border border-slate-800 rounded-xl p-3 font-mono text-xs"
        >
          {filteredTail.length === 0 ? (
            <div className="text-slate-500">No logs yet.</div>
          ) : (
            filteredTail.map((line, idx) => (
              <div key={`${idx}-${line.slice(0, 8)}`} className="text-slate-200">
                {line}
              </div>
            ))
          )}
        </div>
      </section>
        </>
      )}

      {/* Articles Tab */}
      {activeTab === 'articles' && (
        <section className="glass p-6 rounded-2xl">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <h2 className="text-lg font-semibold">Articles</h2>
              <span className="text-sm text-slate-400">
                {filtered.length} article{filtered.length !== 1 ? 's' : ''}
                {selected.size > 0 && ` • ${selected.size} selected`}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <input
                className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
                placeholder="Search headlines"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <Button
                className="bg-slate-700 hover:bg-slate-600"
                onClick={() => {
                  if (selected.size === filtered.length) {
                    setSelected(new Set());
                  } else {
                    setSelected(new Set(filtered.map(item => item.file_path)));
                  }
                }}
              >
                {selected.size === filtered.length ? 'Deselect All' : 'Select All'}
              </Button>
              <Button
                className="bg-accent-2 text-black hover:bg-accent"
                onClick={run}
                disabled={loading || translating || selected.size === 0 || runStatus === "running"}
              >
                {runStatus === "running" ? "Running…" : `Build & Publish (${selected.size})`}
              </Button>
            </div>
          </div>
          <div className="overflow-auto" style={{ maxHeight: 'calc(100vh - 280px)' }}>
            <table className="w-full text-sm">
              <thead className="text-left text-slate-400 sticky top-0 bg-slate-900/95 backdrop-blur-sm">
                <tr>
                  <th
                    className="py-3 px-2 w-16 cursor-pointer hover:text-white transition-colors"
                    onClick={() => handleArticleSort('selected')}
                  >
                    <span className="flex items-center gap-1">
                      Select
                      {renderSortIndicator('selected')}
                    </span>
                  </th>
                  <th
                    className="py-3 px-2 cursor-pointer hover:text-white transition-colors"
                    onClick={() => handleArticleSort('headline_en_gb')}
                  >
                    <span className="flex items-center gap-1">
                      Article
                      {renderSortIndicator('headline_en_gb')}
                    </span>
                  </th>
                  <th
                    className="py-3 px-2 w-32 cursor-pointer hover:text-white transition-colors"
                    onClick={() => handleArticleSort('status')}
                  >
                    <span className="flex items-center gap-1">
                      Status
                      {renderSortIndicator('status')}
                    </span>
                  </th>
                  <th className="py-3 px-2">File Path</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr key={item.file_path} className="border-t border-slate-800 hover:bg-slate-800/30">
                    <td className="py-3 px-2">
                      <input
                        type="checkbox"
                        checked={selected.has(item.file_path)}
                        onChange={() => toggleSelect(item.file_path)}
                        className="w-4 h-4 cursor-pointer"
                      />
                    </td>
                    <td className="py-3 px-2">
                      <div className="font-medium text-white">
                        {item.article_no} - {item.headline_en_gb}
                      </div>
                      {item.is_duplicate && (
                        <span className="text-xs text-amber-300 block mt-1">
                          ⚠ {item.duplicate_reason}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-2 w-32">
                      <div className="flex flex-col gap-1">
                        <div className={`text-xs font-medium uppercase whitespace-nowrap ${
                          articleStatuses[item.file_path]?.status === 'success' ? 'text-green-400' :
                          articleStatuses[item.file_path]?.status === 'failed' ? 'text-red-400' :
                          articleStatuses[item.file_path]?.status === 'running' ? 'text-blue-400 animate-pulse' :
                          articleStatuses[item.file_path]?.status === 'pending' ? 'text-yellow-400' :
                          'text-slate-500'
                        }`}>
                          {articleStatuses[item.file_path]?.status || "idle"}
                        </div>
                        {articleStatuses[item.file_path]?.wp_url && (
                          <a
                            className="text-emerald-300 underline text-xs whitespace-nowrap"
                            href={articleStatuses[item.file_path]?.wp_url}
                            target="_blank"
                            rel="noopener"
                          >
                            View Draft →
                          </a>
                        )}
                        {articleStatuses[item.file_path]?.error && (
                          <div className="text-rose-300 text-xs break-words">
                            {articleStatuses[item.file_path]?.error}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-2 text-slate-400 text-xs font-mono max-w-md truncate" title={item.file_path}>
                      {item.file_path}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="text-center py-12 text-slate-400">
                <p className="text-lg mb-2">No articles found</p>
                <p className="text-sm">Go to the Dashboard tab to scan for articles</p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <>
      <section className="glass p-6 rounded-2xl">
        <h2 className="text-lg font-semibold mb-4">Global Settings</h2>
        <div className="grid grid-cols-2 gap-4">
          <label className="flex flex-col gap-2 text-sm">
            Root path
            <input
              className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
              value={settings.root_path || ""}
              onChange={(e) => setSettings({ ...settings, root_path: e.target.value })}
            />
          </label>
          <label className="flex items-center gap-2 text-sm mt-6">
            <input
              type="checkbox"
              checked={Boolean(settings.skip_duplicates)}
              onChange={(e) => {
                setSettings({ ...settings, skip_duplicates: e.target.checked });
                setSkipDuplicates(e.target.checked);
              }}
            />
            Skip duplicates
          </label>
          <label className="flex items-center gap-2 text-sm mt-6">
            <input
              type="checkbox"
              checked={Boolean(settings.primary_source_strict)}
              onChange={(e) =>
                setSettings({ ...settings, primary_source_strict: e.target.checked })
              }
            />
            Strict primary source validation
          </label>
          <label className="flex items-center gap-2 text-sm mt-6">
            <input
              type="checkbox"
              checked={Boolean(settings.validate_outbound_urls)}
              onChange={(e) =>
                setSettings({ ...settings, validate_outbound_urls: e.target.checked })
              }
            />
            Validate outbound URLs
          </label>
          <label className="flex items-center gap-2 text-sm mt-6">
            <input
              type="checkbox"
              checked={Boolean(settings.enforce_image_spacing)}
              onChange={(e) =>
                setSettings({ ...settings, enforce_image_spacing: e.target.checked })
              }
            />
            Enforce image spacing
          </label>
          <label className="flex flex-col gap-2 text-sm">
            Spacer height (px)
            <input
              className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
              value={settings.image_spacer_height_px || 24}
              onChange={(e) =>
                setSettings({ ...settings, image_spacer_height_px: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <div className="flex gap-3 mt-4">
          <Button
            onClick={async () => {
              const payload = {
                root_path: settings.root_path,
                skip_duplicates: settings.skip_duplicates,
                primary_source_strict: settings.primary_source_strict,
                validate_outbound_urls: settings.validate_outbound_urls,
                enforce_image_spacing: settings.enforce_image_spacing,
                image_spacer_height_px: settings.image_spacer_height_px,
                scan_mode: advancedManual ? "manual" : "upload",
              };
              await fetch(apiUrl("/api/settings"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ data: payload }),
              });
              const res = await fetch(apiUrl("/api/settings"));
              const data = await res.json();
              setSettings(data);
              const stageMap: Record<string, any> = {};
              (Array.isArray(data.stages) ? data.stages : []).forEach((stage: StageItem) => {
                stageMap[stage.key] = stage.values || {};
              });
              setStageSnapshots(stageMap);
              if (data.root_path) {
                setPaths([data.root_path]);
              }
              if (typeof data.skip_duplicates === "boolean") {
                setSkipDuplicates(data.skip_duplicates);
              }
              scan(data.root_path ? [data.root_path] : undefined);
            }}
          >
            Save settings
          </Button>
        </div>
      </section>

      <section className="mt-8 glass p-6 rounded-2xl">
        <h2 className="text-lg font-semibold mb-4">Stage Settings</h2>
        <div className="space-y-6">
          {(Array.isArray(settings.stages) ? settings.stages : []).map((stage: StageItem) => {
            const values = stage.values || {};
            const defaults = stage.defaults || {};
            return (
            <div key={stage.key} className="border border-slate-800 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold">{stage.display_name || stage.key}</h3>
                <div className="flex gap-2">
                  <Button
                    onClick={async () => {
                      const payload: any = {};
                      Object.keys(defaults).forEach((key) => {
                        payload[key] = defaults[key];
                      });
                      if (Object.keys(payload).length === 0) {
                        return;
                      }
                      await fetch(apiUrl("/api/settings"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ data: payload }),
                      });
                      const res = await fetch(apiUrl("/api/settings"));
                      const data = await res.json();
                      setSettings(data);
                      setStageSnapshots((prev) => ({
                        ...prev,
                        [stage.key]: data.stages?.find((s: StageItem) => s.key === stage.key)?.values || {},
                      }));
                    }}
                  >
                    Reset to default
                  </Button>
                  <Button
                    className="bg-accent text-black hover:bg-accent"
                    onClick={async () => {
                      const original = stageSnapshots[stage.key] || {};
                      const payload: any = {};
                      Object.keys(values).forEach((key) => {
                        if (values[key] !== original[key]) {
                          payload[key] = values[key];
                        }
                      });
                      if (Object.keys(payload).length === 0) {
                        return;
                      }
                      await fetch(apiUrl("/api/settings"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ data: payload }),
                      });
                      const res = await fetch(apiUrl("/api/settings"));
                      const data = await res.json();
                      setSettings(data);
                      setStageSnapshots((prev) => ({
                        ...prev,
                        [stage.key]: data.stages?.find((s: StageItem) => s.key === stage.key)?.values || {},
                      }));
                    }}
                  >
                    Save
                  </Button>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(values).map(([key, value]: any) => {
                  if (typeof value === "string" && value.length > 120) {
                    return (
                      <label key={key} className="flex flex-col gap-2 text-sm col-span-2">
                        {key}
                        <textarea
                          className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 min-h-[100px]"
                          value={value || ""}
                          onChange={(e) =>
                            updateStageValues(stage.key, { ...values, [key]: e.target.value })
                          }
                        />
                      </label>
                    );
                  }
                  return (
                    <label key={key} className="flex flex-col gap-2 text-sm">
                      {key}
                      <input
                        className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
                        value={value === undefined || value === null ? "" : String(value)}
                        onChange={(e) =>
                          updateStageValues(stage.key, { ...values, [key]: e.target.value })
                        }
                      />
                    </label>
                  );
                })}
              </div>
            </div>
            );
          })}
        </div>
      </section>

      <section className="mt-8 glass p-6 rounded-2xl">
        <h2 className="text-lg font-semibold mb-4">Primary Source Registry</h2>
        <div className="flex gap-3 mb-4">
          <input
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
            placeholder="Filter by domain"
            value={registryDomain}
            onChange={(e) => setRegistryDomain(e.target.value)}
          />
          <select
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2"
            value={registryType}
            onChange={(e) => setRegistryType(e.target.value)}
          >
            <option value="">All types</option>
            <option value="primary">Primary</option>
            <option value="news">News</option>
          </select>
          <Button onClick={loadRegistry}>Apply filters</Button>
        </div>
        <div className="overflow-auto max-h-[420px]">
          <table className="w-full text-sm">
            <thead className="text-left text-slate-400">
              <tr>
                <th className="py-2">URL</th>
                <th>Type</th>
                <th>Domain</th>
                <th>First Seen</th>
                <th>Last Seen</th>
                <th>Days Ago</th>
                <th>Usage</th>
                <th>Refs</th>
                <th>Copy</th>
              </tr>
            </thead>
            <tbody>
              {registry.map((entry) => {
                const domain = entry.domain || "";
                const refs = Array.isArray(entry.article_refs) ? entry.article_refs : [];
                return (
                  <tr key={entry.url} className="border-t border-slate-800">
                    <td className="py-2 text-slate-200">{entry.url}</td>
                    <td>{entry.source_type}</td>
                    <td>{domain}</td>
                    <td>{entry.first_seen}</td>
                    <td>{entry.last_seen}</td>
                    <td>{entry.last_seen_days_ago ?? "-"}</td>
                    <td>{entry.usage_count ?? (entry.article_ids || []).length}</td>
                    <td className="text-xs text-slate-400">
                      {refs.length === 0
                        ? "-"
                        : refs
                            .slice(0, 2)
                            .map((ref: any) => ref.id || ref.filename || ref.run_id || "ref")
                            .join(", ")}
                    </td>
                    <td>
                      <Button
                        onClick={() => navigator.clipboard.writeText(entry.url)}
                      >
                        Copy
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Profile Management Section */}
      <section className="mt-8 glass p-6 rounded-2xl">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold">Profile Management</h2>
            {activeProfile && activeProfile.profile && (
              <p className="text-sm text-slate-400 mt-1">
                Active: <span className="text-blue-400">{activeProfile.profile.name}</span>
                {" "}({activeProfile.input_dir} → {activeProfile.output_dir})
              </p>
            )}
          </div>
          <Button
            onClick={() => setShowProfileSection(!showProfileSection)}
            variant="outline"
          >
            {showProfileSection ? "Hide" : "Show"} Profiles
          </Button>
        </div>

        {showProfileSection && (
          <ProfileManager
            apiUrl={apiUrl}
            onProfileChange={() => {
              loadActiveProfile();
              scan();
            }}
          />
        )}
      </section>

      {/* Prompt Editor Section */}
      <section className="mt-8 glass p-6 rounded-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">LLM Prompt Customization</h2>
          <Button
            onClick={() => setShowPromptsSection(!showPromptsSection)}
            variant="outline"
          >
            {showPromptsSection ? "Hide" : "Show"} Prompts
          </Button>
        </div>

        {showPromptsSection && activeProfile && activeProfile.profile && (
          <PromptEditor
            apiUrl={apiUrl}
            profileId={activeProfile.profile.id}
          />
        )}

        {showPromptsSection && (!activeProfile || !activeProfile.profile) && (
          <p className="text-slate-400 text-sm">
            No active profile. Please activate a profile first.
          </p>
        )}
      </section>
        </>
      )}
    </div>
  );
}
