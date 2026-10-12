import { useEffect, useState } from 'react'

/** Fica true só depois que `flag` permanece true por `delayMs` (ex.: detectar API lenta). */
export function useDelayedFlag(flag: boolean, delayMs: number): boolean {
  const [delayed, setDelayed] = useState(false)
  useEffect(() => {
    if (!flag) {
      setDelayed(false)
      return
    }
    const timer = setTimeout(() => setDelayed(true), delayMs)
    return () => clearTimeout(timer)
  }, [flag, delayMs])
  return delayed
}
