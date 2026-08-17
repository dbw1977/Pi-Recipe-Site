// Thin API client for the FastAPI backend. All calls are same-origin (/api/...),
// which works both in dev (Vite proxy) and in production (FastAPI serves the build).

export interface Ingredient {
  id?: number;
  quantity: number | null;
  unit: string | null;
  name: string;
  note?: string | null;
  scalable: number;
  sort_order?: number;
}

export interface Group {
  id?: number;
  name: string | null;
  sort_order?: number;
  ingredients: Ingredient[];
}

export interface Step {
  id?: number;
  text: string;
  sort_order?: number;
}

export interface Equipment {
  id?: number;
  name: string;
  inferred: number;
  sort_order?: number;
}

export interface Tag {
  id: number;
  name: string;
  category: string;
}

export interface TagCategory {
  id: number;
  name: string;
  tags: Tag[];
}

export interface Recipe {
  id: number;
  title: string;
  description: string | null;
  source_type: string | null;
  source_name: string | null;
  source_url: string | null;
  source_handle: string | null;
  hero_image: string | null;
  servings_base: number | null;
  servings_unit: string | null;
  total_time: number | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  groups: Group[];
  steps: Step[];
  equipment: Equipment[];
  tags: Tag[];
}

export interface RecipeCard {
  id: number;
  title: string;
  source_name: string | null;
  source_handle: string | null;
  hero_image: string | null;
  servings_base: number | null;
  servings_unit: string | null;
  total_time: number | null;
  status: string;
  tags: Tag[];
}

export interface DraftCard extends RecipeCard {
  duplicate: { id: number; title: string; reason: string } | null;
}

export interface ImportStatus {
  url: boolean;
  claude: boolean;
  screenshot: boolean;
  video: boolean;
  voice: boolean;
  voice_transcription: boolean;
  drive_configured: boolean;
  drive_authorized: boolean;
}

export interface ImportResponse {
  draft: Recipe;
  duplicate: { id: number; title: string; reason: string } | null;
  warning?: string;
}

export interface DriveScanSummary {
  created: { name: string; recipe_id: number }[];
  skipped: { name: string; reason: string }[];
  errors: { name: string; error: string }[];
  total_seen: number;
}

export interface FeaturedResponse {
  recipe: RecipeCard | null;
  iso_week: string;
  pinned: boolean;
}

export interface BackupEntry {
  kind: string;
  target: string;
  ok: number;
  message: string;
  size_bytes: number | null;
  created_at: string;
}

export interface BackupStatus {
  local: BackupEntry | null;
  drive: BackupEntry | null;
  drive_configured: boolean;
}

export interface RecipeInput {
  title: string;
  description?: string | null;
  source_type?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  source_handle?: string | null;
  hero_image?: string | null;
  servings_base?: number | null;
  servings_unit?: string | null;
  total_time?: number | null;
  status?: string;
  groups: Group[];
  steps: Step[];
  equipment: Equipment[];
  tag_ids: number[];
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function req<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  return handle<T>(res);
}

// Multipart POST (files) — let the browser set the multipart boundary itself.
async function postForm<T>(url: string, form: FormData): Promise<T> {
  const res = await fetch(url, { method: 'POST', body: form });
  return handle<T>(res);
}

export const api = {
  listRecipes(q?: string, tagIds?: number[]): Promise<RecipeCard[]> {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (tagIds && tagIds.length) params.set('tags', tagIds.join(','));
    const qs = params.toString();
    return req<RecipeCard[]>(`/api/recipes${qs ? `?${qs}` : ''}`);
  },
  getRecipe(id: number): Promise<Recipe> {
    return req<Recipe>(`/api/recipes/${id}`);
  },
  createRecipe(data: RecipeInput): Promise<Recipe> {
    return req<Recipe>('/api/recipes', { method: 'POST', body: JSON.stringify(data) });
  },
  updateRecipe(id: number, data: RecipeInput): Promise<Recipe> {
    return req<Recipe>(`/api/recipes/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  },
  deleteRecipe(id: number): Promise<void> {
    return req<void>(`/api/recipes/${id}`, { method: 'DELETE' });
  },
  listTags(): Promise<TagCategory[]> {
    return req<TagCategory[]>('/api/tags');
  },
  createTag(categoryId: number, name: string): Promise<Tag> {
    return req<Tag>('/api/tags', {
      method: 'POST',
      body: JSON.stringify({ category_id: categoryId, name }),
    });
  },
  deleteTag(id: number): Promise<void> {
    return req<void>(`/api/tags/${id}`, { method: 'DELETE' });
  },

  // --- Imports (Chunk B) ---
  importStatus(): Promise<ImportStatus> {
    return req<ImportStatus>('/api/imports/status');
  },
  importUrl(url: string): Promise<ImportResponse> {
    return req<ImportResponse>('/api/imports/url', { method: 'POST', body: JSON.stringify({ url }) });
  },
  importScreenshot(file: File, extra: File[] = []): Promise<ImportResponse> {
    const form = new FormData();
    form.append('file', file);
    extra.forEach((f) => form.append('extra', f));
    return postForm<ImportResponse>('/api/imports/screenshot', form);
  },
  importVoice(file: File, photos: File[] = []): Promise<ImportResponse> {
    const form = new FormData();
    form.append('file', file);
    photos.forEach((f) => form.append('photos', f));
    return postForm<ImportResponse>('/api/imports/voice', form);
  },
  driveScan(): Promise<DriveScanSummary> {
    return req<DriveScanSummary>('/api/imports/drive/scan', { method: 'POST' });
  },
  driveAuthUrl(): Promise<{ url: string; redirect_uri: string }> {
    return req<{ url: string; redirect_uri: string }>('/api/imports/drive/auth-url');
  },

  // --- Drafts queue (Chunk B) ---
  listDrafts(): Promise<DraftCard[]> {
    return req<DraftCard[]>('/api/drafts');
  },
  approveDraft(id: number): Promise<Recipe> {
    return req<Recipe>(`/api/drafts/${id}/approve`, { method: 'POST' });
  },
  approveAll(ids?: number[]): Promise<{ approved: number[]; count: number }> {
    return req('/api/drafts/approve-all', { method: 'POST', body: JSON.stringify({ ids: ids ?? null }) });
  },
  discardDraft(id: number): Promise<void> {
    return req<void>(`/api/drafts/${id}`, { method: 'DELETE' });
  },

  // --- Recipe of the Week (Chunk C) ---
  getFeatured(): Promise<FeaturedResponse> {
    return req<FeaturedResponse>('/api/featured');
  },
  pinFeatured(id: number): Promise<FeaturedResponse> {
    return req<FeaturedResponse>(`/api/featured/${id}/pin`, { method: 'POST' });
  },
  unpinFeatured(): Promise<FeaturedResponse> {
    return req<FeaturedResponse>('/api/featured/pin', { method: 'DELETE' });
  },

  // --- Backups (Chunk C) ---
  backupStatus(): Promise<BackupStatus> {
    return req<BackupStatus>('/api/backups/status');
  },
  runBackup(kind: 'local' | 'drive' | 'both'): Promise<BackupStatus> {
    return req<BackupStatus>('/api/backups/run', { method: 'POST', body: JSON.stringify({ kind }) });
  },
};
