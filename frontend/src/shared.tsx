import { useEffect, useState, type ReactNode } from 'react'
import { api, type Status, type Change } from './api'

export const numbers = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 8 })
export const fmt = (value: number | null | undefined) => value == null ? '—' : numbers.format(value)
export const date = (value: string) => new Intl.DateTimeFormat('ru-RU', {
  dateStyle: 'medium', timeStyle: 'short',
}).format(new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z'))
export const statuses: Record<Status, string> = {
  CREATED: 'Черновик', QUEUED: 'В очереди', RUNNING: 'Выполняется', SUCCEEDED: 'Завершён', FAILED: 'Ошибка',
}
export const stages: Record<string, string> = {
  created: 'Конфигурация сохранена', queued: 'Ожидание worker', processing: 'Нормализация и сравнение',
  checks: 'Автоматические проверки', aggregating: 'Агрегация фактов', done: 'Завершено', failed: 'Ошибка',
}
export const changes: Record<Change, string> = {
  SAME: 'Совпадает', VALUE_CHANGED: 'Значение изменилось', ATTRIBUTE_NEW: 'Новый атрибут', ATTRIBUTE_LOST: 'Атрибут исчез',
}
export const decision = (value: string | null) => ({ APPROVE: 'Одобрено', REJECT: 'Отказ', VERIFICATION: 'Проверка' }[value ?? ''] ?? value ?? '—')

export function useData<T>(path: string, interval = 0) {
  const [state, setState] = useState<{ path: string; data?: T; error?: string }>({ path: '' })
  const [revision, refresh] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function load() {
      try {
        const data = await api<T>(path, { signal: controller.signal })
        if (!controller.signal.aborted) setState({ path, data })
      } catch (error) {
        if (!controller.signal.aborted) setState({ path, error: (error as Error).message })
      }
      if (interval && !controller.signal.aborted) timer = setTimeout(load, interval)
    }
    void load()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [path, interval, revision])
  return { ...(state.path === path ? state : {}), reload: () => refresh(value => value + 1) }
}

const paths = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  plus: 'M12 5v14M5 12h14', arrow: 'M5 12h14m-6-6 6 6-6 6', back: 'M19 12H5m6-6-6 6 6 6',
  pulse: 'M3 12h4l3-7 4 14 3-7h4', layers: 'm12 3 9 5-9 5-9-5 9-5zm-9 9 9 5 9-5m-18 5 9 5 9-5',
  table: 'M3 4h18v16H3z M3 9h18M9 9v11M15 9v11', check: 'M5 12l4 4L19 6',
  list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01', code: 'm8 6-6 6 6 6m8-12 6 6-6 6m-2-15-4 18',
  download: 'M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4',
}
export function Icon({ name }: { name: keyof typeof paths }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}
export function Badge({ status }: { status: Status }) {
  return <span className={`badge badge-${status.toLowerCase()}`}><i />{statuses[status]}</span>
}
export function Title({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle?: string; action?: ReactNode }) {
  return <header className="page-title"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{subtitle && <p className="subtitle">{subtitle}</p>}</div>{action}</header>
}
export function Feedback({ error, children }: { error?: string; children?: ReactNode }) {
  return error ? <div className="notice error" role="alert">{error}</div> : <div className="notice" role="status">{children ?? 'Загрузка…'}</div>
}
export function Table({ columns, children, empty }: { columns: string[]; children: ReactNode; empty?: boolean }) {
  return <div className="table-scroll"><table><thead><tr>{columns.map(column => <th key={column} scope="col">{column}</th>)}</tr></thead>
    <tbody>{empty ? <tr><td colSpan={columns.length} className="empty">Данных для этого представления нет</td></tr> : children}</tbody>
  </table></div>
}
export function Pager({ offset, size, next, set }: { offset: number; size: number; next: boolean; set: (offset: number) => void }) {
  if (!offset && !next) return null
  return <div className="pager"><button className="btn secondary" disabled={!offset} onClick={() => set(Math.max(0, offset - size))}>Назад</button>
    <span>Страница {Math.floor(offset / size) + 1}</span><button className="btn secondary" disabled={!next} onClick={() => set(offset + size)}>Далее</button></div>
}

