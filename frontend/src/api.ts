export type Status = 'CREATED' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
export type Summary = {
  applications: number; apps_with_differences: number; apps_with_decision_change: number; comparison_rows: number
}
export type RunItem = {
  id: number; status: Status; stage: string; processed: number; total: number; dataset_name: string;
  created_at: string; apps_with_differences: number | null; apps_with_decision_change: number | null
}
export type Config = {
  normalizer: string; comparator: string; aggregator?: string;
  normalize_params: Record<string, unknown>; compare_params: Record<string, unknown>;
  aggregate_params?: Record<string, unknown>; checks: Record<string, Record<string, unknown>>
}
export type Run = RunItem & { dataset_id: number; summary: Summary | null; error: string | null; settings: Config }
export type Dataset = { id: number; name: string; application_count: number }
export type Catalog = { normalize: string[]; compare: string[]; aggregate: string[]; checks: string[] }
export type Log = { stage: string; message: string; created_at: string }
export type Attribute = { path: string; applications: number }
export type Application = {
  APP_ID: string; DIFF_FLAG: number; DECISION_CHANGED: number; DECISION_BEFORE: string | null;
  DECISION_AFTER: string | null; PRODUCTS: string; TOP_OFFER_BEFORE: number | null; TOP_OFFER_AFTER: number | null
}
export type Change = 'SAME' | 'VALUE_CHANGED' | 'ATTRIBUTE_NEW' | 'ATTRIBUTE_LOST'
export type Comparison = {
  PATH: string; ARRAY_KEY: string; VALUE_BEFORE: string | null; VALUE_AFTER: string | null; CHANGE_TYPE: Change
}
export type Check = {
  check_id: string; LABEL: string; SOURCE: string; ARGUMENT: string; CNT: number; TOTAL: number;
  METRIC: number; APP_IDS: string[]; RESULT: 'PASS' | 'FAIL'; CONFIDENCE: 'LOW' | 'HIGH'
}
export type Page<T> = { rows: T[]; has_more: boolean }
export type Dimension = 'PREFIX' | 'CLASS' | 'SUFFIX' | 'ARRAY_KEY' | 'KEY' | 'VALUE_ADJUSTED' | 'DIFF_FLAG' | 'SOURCE'
export type Filters = Partial<Record<Dimension, string | number>>
export type PivotRow = Filters & { total: number; BEFORE?: number; AFTER?: number; same_count?: number; diff_count?: number }

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch('/api' + path, init)
  if (!response.ok) {
    let detail: unknown
    try { detail = (await response.json()).detail } catch { /* the proxy may return HTML */ }
    throw new Error(typeof detail === 'string' ? detail : `Ошибка API (${response.status})`)
  }
  return response.json()
}

export function post<T>(path: string, payload?: unknown) {
  return api<T>(path, {
    method: 'POST',
    ...(payload instanceof FormData ? { body: payload } : {
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload ?? {}),
    }),
  })
}

export function query(fields: Record<string, string | number | string[] | undefined>) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(fields)) {
    if (Array.isArray(value)) value.forEach(item => params.append(key, item))
    else if (value !== undefined) params.set(key, String(value))
  }
  const text = params.toString()
  return text ? '?' + text : ''
}

