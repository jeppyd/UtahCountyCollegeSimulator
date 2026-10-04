// Explore: the field pane on the left, the chosen field on the right. Every field the model tracks is a
// click away, in whichever world the lens shows.
import { useMemo } from 'react'
import { api } from '../../api'
import { useAsync } from '../../game'
import { useLens, useStore } from '../../store'
import { FieldCanvas } from './FieldCanvas'
import { FieldPane } from './FieldPane'

export default function FieldExplorer({ field, split }: { field?: string; split?: string }) {
  const { dataVersion, setRoute, registry } = useStore()
  const { u, compare, hasAlt } = useLens()
  const v = field && registry?.variables[field] ? field : 'loneliness'
  const info = useAsync(() => api.fieldsInfo(), [dataVersion > 0 ? 1 : 0])
  const sum = useAsync(() => api.fieldsSummary(u), [u, dataVersion])
  const cmp = useAsync(() => (hasAlt ? api.compareFields() : Promise.resolve(null)), [hasAlt, dataVersion])
  const tracked = useMemo(() => {
    const d: any = info.data
    return { weekly: new Set<string>(d?.weekly ?? []), person: new Set<string>([...(d?.person_history?.categorical ?? []), ...(d?.person_history?.numeric ?? [])]) }
  }, [info.data])
  return (
    <div className="explorer">
      <FieldPane value={v} onPick={x => setRoute(['explore', x])} summary={(sum.data as any)?.fields ?? null} tracked={tracked} compare={compare ? cmp.data : null} />
      <div className="ex-main">
        <FieldCanvas key={v} v={v} split0={split && registry?.variables[split] ? split : undefined} tracked={tracked} compareRow={(cmp.data as any)?.fields?.[v]} />
      </div>
    </div>
  )
}
