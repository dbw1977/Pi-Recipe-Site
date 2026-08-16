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

async function req<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
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
};
