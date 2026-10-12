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
  rating?: number | null; // our 1-5 stars; null/absent = not rated
  groups: Group[];
  steps: Step[];
  equipment: Equipment[];
  tags: Tag[];
  generated?: number;
  derived_from_recipe_id?: number | null;
  derived_from_title?: string | null;
  generation_prompt?: string | null;
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
  generated?: number;
  rating?: number | null;
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

export interface PlaceImportResponse {
  draft: Place;
  duplicate: null;
  warning?: string;
}

export interface GoogleStatus {
  configured: boolean;
  authorized: boolean;
  drive_import_folder: boolean;
  drive_backup_folder: boolean;
  drive_import_ready: boolean;
  drive_backup_ready: boolean;
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

export interface BackupSettings {
  enabled: boolean; // weekly automatic backups (manual "Back up now" always works)
  local_enabled: boolean;
  local_dir: string;
  drive_enabled: boolean;
  drive_folder_name: string;
  include_media: boolean; // photos too — needed to rebuild the library on a new Pi
  day: number; // 0 = Monday … 6 = Sunday
  hour: number; // 0-23, the Pi's local time
}

export interface BackupStatus {
  settings: BackupSettings;
  day_names: string[];
  local: BackupEntry | null;
  drive: BackupEntry | null;
  running: boolean;
  step: string; // live progress while running, e.g. "Packing photos… 12 of 80"
  next_run: string | null; // local time, ISO minutes
  media: { files: number; bytes: number } | null; // null while a backup is running
  local_same_disk: boolean; // true = the backup folder is on the Pi's own disk
  google: { configured: boolean; authorized: boolean };
}

// --- Places (Chunk D) -------------------------------------------------------
export interface Dish {
  id?: number;
  name: string;
  note?: string | null;
  must_order: number;
  sort_order?: number;
}

export interface Place {
  id: number;
  name: string;
  place_type: string | null;
  city: string | null;
  address: string | null;
  maps_url: string | null;
  maps_place_id: string | null;
  phone: string | null;
  website: string | null;
  price_level: number | null;
  our_rating: number | null;
  our_notes: string | null;
  source_name: string | null;
  source_url: string | null;
  hero_image: string | null;
  visited: number;
  status: string;
  created_at: string | null;
  updated_at: string | null;
  dishes: Dish[];
  tags: Tag[];
}

export interface PlaceCard {
  id: number;
  name: string;
  place_type: string | null;
  city: string | null;
  price_level: number | null;
  our_rating: number | null;
  hero_image: string | null;
  visited: number;
  status: string;
  tags: Tag[];
}

export interface PlaceInput {
  name: string;
  place_type?: string | null;
  city?: string | null;
  address?: string | null;
  maps_url?: string | null;
  phone?: string | null;
  website?: string | null;
  price_level?: number | null;
  our_rating?: number | null;
  our_notes?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  hero_image?: string | null;
  visited: number;
  status?: string;
  dishes: Dish[];
  tag_ids: number[];
}

// --- Meal planner + grocery (Chunk E) --------------------------------------
export interface MealPlanCard {
  id: number;
  start_date: string;
  title: string | null;
  entry_count: number;
}

export interface PlanEntry {
  id: number;
  day_index: number;
  meal_slot: string | null;
  scale: number;
  sort_order: number | null;
  kind: 'recipe' | 'place';
  recipe_id: number | null;
  place_id: number | null;
  title: string;
  hero_image: string | null;
}

export interface MealPlan {
  id: number;
  start_date: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  entries: PlanEntry[];
}

export interface GroceryItem {
  id: number;
  name: string;
  unit: string | null;
  display: string | null;
  base: number | null;
  family: string;
  aisle: string;
  checked: number;
  manual: number;
  recipes: string[];
  sort_order: number | null;
}

export interface GroceryLineInput {
  name: string;
  unit: string | null;
  display: string | null;
  base: number | null;
  family: string;
  aisle: string;
  recipes: string[];
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

/** Sort orders the Cook and Eat Out libraries understand (server-validated). 'relevance' only applies to a search. */
export type ListSort =
  | 'relevance'
  | 'newest'
  | 'oldest'
  | 'title_asc'
  | 'title_desc'
  | 'rating_desc'
  | 'rating_asc';

export interface Page<T> {
  items: T[];
  total: number; // everything matching, across all pages
}
export type RecipePage = Page<RecipeCard>;

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

// A list endpoint that reports its total (ignoring limit/offset) in the X-Total-Count header.
async function fetchPage<T>(url: string): Promise<Page<T>> {
  const res = await fetch(url);
  const items = await handle<T[]>(res);
  const total = Number(res.headers.get('X-Total-Count'));
  return { items, total: Number.isFinite(total) && total >= 0 ? total : items.length };
}

export const api = {
  listRecipes(q?: string, tagIds?: number[]): Promise<RecipeCard[]> {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (tagIds && tagIds.length) params.set('tags', tagIds.join(','));
    const qs = params.toString();
    return req<RecipeCard[]>(`/api/recipes${qs ? `?${qs}` : ''}`);
  },
  /** One page of the library; `total` comes from the X-Total-Count header. */
  listRecipesPage(opts: {
    q?: string;
    tagIds?: number[];
    sort?: ListSort;
    limit: number;
    offset: number;
  }): Promise<Page<RecipeCard>> {
    const params = new URLSearchParams();
    if (opts.q) params.set('q', opts.q);
    if (opts.tagIds && opts.tagIds.length) params.set('tags', opts.tagIds.join(','));
    if (opts.sort) params.set('sort', opts.sort);
    params.set('limit', String(opts.limit));
    params.set('offset', String(opts.offset));
    return fetchPage<RecipeCard>(`/api/recipes?${params.toString()}`);
  },
  setRecipeRating(id: number, rating: number | null): Promise<Recipe> {
    return req<Recipe>(`/api/recipes/${id}/rating`, {
      method: 'PUT',
      body: JSON.stringify({ rating }),
    });
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
  createVariation(recipeId: number, instruction: string): Promise<ImportResponse> {
    return req<ImportResponse>(`/api/recipes/${recipeId}/variations`, {
      method: 'POST',
      body: JSON.stringify({ instruction }),
    });
  },
  setRecipeHero(recipeId: number, heroImage: string): Promise<Recipe> {
    return req<Recipe>(`/api/recipes/${recipeId}/hero`, {
      method: 'POST',
      body: JSON.stringify({ hero_image: heroImage }),
    });
  },
  uploadPhoto(file: File): Promise<{ path: string }> {
    const form = new FormData();
    form.append('file', file);
    return postForm<{ path: string }>('/api/media/upload', form);
  },
  listTags(collection: 'recipe' | 'place' | 'all' = 'recipe'): Promise<TagCategory[]> {
    return req<TagCategory[]>(`/api/tags?collection=${collection}`);
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
  // One or more source images (read together as one recipe) or a single video,
  // plus an optional cover photo used as the hero image.
  importScreenshot(files: File[], cover?: File): Promise<ImportResponse> {
    const form = new FormData();
    files.forEach((f) => form.append('file', f));
    if (cover) form.append('extra', cover);
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

  // --- Google account (OAuth; powers Drive import + Drive backup) ---
  googleStatus(): Promise<GoogleStatus> {
    return req<GoogleStatus>('/api/google/status');
  },
  googleAuthUrl(): Promise<{ url: string; redirect_uri: string }> {
    return req<{ url: string; redirect_uri: string }>('/api/google/auth-url');
  },
  googleConnect(code: string): Promise<{ authorized: boolean }> {
    return req('/api/google/connect', { method: 'POST', body: JSON.stringify({ code }) });
  },
  googleDisconnect(): Promise<{ authorized: boolean }> {
    return req('/api/google/disconnect', { method: 'POST' });
  },

  // --- Places (Chunk D) ---
  listPlaces(q?: string, tagIds?: number[], city?: string): Promise<PlaceCard[]> {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (tagIds && tagIds.length) params.set('tags', tagIds.join(','));
    if (city) params.set('city', city);
    const qs = params.toString();
    return req<PlaceCard[]>(`/api/places${qs ? `?${qs}` : ''}`);
  },
  /** One page of Eat Out; `total` comes from the X-Total-Count header. */
  listPlacesPage(opts: {
    q?: string;
    tagIds?: number[];
    sort?: ListSort;
    limit: number;
    offset: number;
  }): Promise<Page<PlaceCard>> {
    const params = new URLSearchParams();
    if (opts.q) params.set('q', opts.q);
    if (opts.tagIds && opts.tagIds.length) params.set('tags', opts.tagIds.join(','));
    if (opts.sort) params.set('sort', opts.sort);
    params.set('limit', String(opts.limit));
    params.set('offset', String(opts.offset));
    return fetchPage<PlaceCard>(`/api/places?${params.toString()}`);
  },
  getPlace(id: number): Promise<Place> {
    return req<Place>(`/api/places/${id}`);
  },
  createPlace(data: PlaceInput): Promise<Place> {
    return req<Place>('/api/places', { method: 'POST', body: JSON.stringify(data) });
  },
  updatePlace(id: number, data: PlaceInput): Promise<Place> {
    return req<Place>(`/api/places/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  },
  deletePlace(id: number): Promise<void> {
    return req<void>(`/api/places/${id}`, { method: 'DELETE' });
  },
  listPlaceDrafts(): Promise<PlaceCard[]> {
    return req<PlaceCard[]>('/api/places/drafts');
  },
  approvePlace(id: number): Promise<Place> {
    return req<Place>(`/api/places/${id}/approve`, { method: 'POST' });
  },
  listCities(): Promise<string[]> {
    return req<string[]>('/api/places/cities');
  },
  placesMeta(): Promise<{ home_city: string | null; cities: string[] }> {
    return req<{ home_city: string | null; cities: string[] }>('/api/places/meta');
  },
  importPlaceScreenshot(files: File[], cover?: File): Promise<PlaceImportResponse> {
    const form = new FormData();
    files.forEach((f) => form.append('file', f));
    if (cover) form.append('extra', cover);
    return postForm<PlaceImportResponse>('/api/imports/place/screenshot', form);
  },

  // --- Meal planner + grocery (Chunk E) ---
  listMealPlans(): Promise<MealPlanCard[]> {
    return req<MealPlanCard[]>('/api/meal-plans');
  },
  createMealPlan(startDate: string, title?: string): Promise<MealPlan> {
    return req<MealPlan>('/api/meal-plans', { method: 'POST', body: JSON.stringify({ start_date: startDate, title: title ?? null }) });
  },
  getMealPlan(id: number): Promise<MealPlan> {
    return req<MealPlan>(`/api/meal-plans/${id}`);
  },
  deleteMealPlan(id: number): Promise<void> {
    return req<void>(`/api/meal-plans/${id}`, { method: 'DELETE' });
  },
  addPlanEntry(planId: number, e: { day_index: number; recipe_id?: number; place_id?: number; scale?: number; meal_slot?: string }): Promise<PlanEntry> {
    return req<PlanEntry>(`/api/meal-plans/${planId}/entries`, { method: 'POST', body: JSON.stringify(e) });
  },
  updatePlanEntry(planId: number, entryId: number, patch: { scale?: number; day_index?: number; meal_slot?: string }): Promise<void> {
    return req<void>(`/api/meal-plans/${planId}/entries/${entryId}`, { method: 'PATCH', body: JSON.stringify(patch) });
  },
  deletePlanEntry(planId: number, entryId: number): Promise<void> {
    return req<void>(`/api/meal-plans/${planId}/entries/${entryId}`, { method: 'DELETE' });
  },
  getGrocery(planId: number): Promise<GroceryItem[]> {
    return req<GroceryItem[]>(`/api/meal-plans/${planId}/grocery`);
  },
  generateGrocery(planId: number, items: GroceryLineInput[]): Promise<GroceryItem[]> {
    return req<GroceryItem[]>(`/api/meal-plans/${planId}/grocery/generate`, { method: 'POST', body: JSON.stringify({ items }) });
  },
  addGroceryItem(planId: number, name: string, aisle = 'Other'): Promise<GroceryItem> {
    return req<GroceryItem>(`/api/meal-plans/${planId}/grocery/items`, { method: 'POST', body: JSON.stringify({ name, aisle }) });
  },
  setGroceryChecked(planId: number, itemId: number, checked: boolean): Promise<void> {
    return req<void>(`/api/meal-plans/${planId}/grocery/items/${itemId}`, { method: 'PATCH', body: JSON.stringify({ checked }) });
  },
  deleteGroceryItem(planId: number, itemId: number): Promise<void> {
    return req<void>(`/api/meal-plans/${planId}/grocery/items/${itemId}`, { method: 'DELETE' });
  },
  categorizeAisles(names: string[]): Promise<{ available: boolean; aisles: Record<string, string> }> {
    return req(`/api/meal-plans/grocery/categorize`, { method: 'POST', body: JSON.stringify({ names }) });
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
  saveBackupSettings(patch: Partial<BackupSettings>): Promise<BackupStatus> {
    return req<BackupStatus>('/api/backups/settings', { method: 'PUT', body: JSON.stringify(patch) });
  },
  /** Starts a backup of every destination that's switched on; poll backupStatus() for progress. */
  runBackup(): Promise<BackupStatus> {
    return req<BackupStatus>('/api/backups/run', { method: 'POST', body: JSON.stringify({ kind: 'enabled' }) });
  },
};
