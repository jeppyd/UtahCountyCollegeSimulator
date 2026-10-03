import cytoscape from 'cytoscape'
import { useEffect, useRef } from 'react'
import { cssVar } from './components'

export function CyGraph({ elements, style, layout, height = 420, onTap }: { elements: any[]; style?: any[]; layout?: any; height?: number; onTap?: (id: string, data: any) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const cy = useRef<cytoscape.Core | null>(null)
  useEffect(() => {
    if (!ref.current) return
    const text = cssVar('--text-secondary'), edge = cssVar('--axis'), surface = cssVar('--surface-1')
    cy.current = cytoscape({
      container: ref.current, elements, wheelSensitivity: 0.25, minZoom: 0.2, maxZoom: 3,
      style: [
        { selector: 'node', style: { 'background-color': 'data(color)', width: 'data(size)', height: 'data(size)', 'border-width': 2, 'border-color': surface, label: 'data(label)', 'font-size': 9, color: text, 'text-valign': 'bottom', 'text-margin-y': 3, 'min-zoomed-font-size': 7 } as any },
        { selector: 'edge', style: { width: 'data(width)', 'line-color': 'data(color)', 'curve-style': 'haystack', opacity: 0.7 } as any },
        { selector: 'node:selected', style: { 'border-color': cssVar('--text-primary'), 'border-width': 3 } as any },
        ...(style ?? []),
      ] as any,
      layout: layout ?? { name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 70, numIter: 800 },
    })
    if (onTap) cy.current.on('tap', 'node', e => onTap(e.target.id(), e.target.data()))
    return () => { cy.current?.destroy() }
  }, [elements])
  return <div ref={ref} style={{ height, width: '100%', background: 'var(--surface-2)', borderRadius: 8 }} />
}
