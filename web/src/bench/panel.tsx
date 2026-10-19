// What a tool can put in its panel's header: its own options (a field picker, a mode switch…), drawn next to the pin.
import { createContext, useContext, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

export const PanelSlot = createContext<HTMLElement | null>(null)

/** A tool's options, shown in its panel's thin header (or in place when the tool is used outside the bench). */
export function PanelOptions({ children }: { children: ReactNode }) {
  const slot = useContext(PanelSlot)
  if (!slot) return <div className="bp-opts-inline">{children}</div>
  return createPortal(children, slot)
}
