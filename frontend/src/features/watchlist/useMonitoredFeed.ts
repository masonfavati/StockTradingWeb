import { useEffect, useState } from 'react'
import { isMonitoredFeed, type MonitoredFeed } from './monitoring'

type Connection = 'connecting' | 'connected' | 'reconnecting' | 'unsupported'

export function useMonitoredFeed() {
  const [feed, setFeed] = useState<MonitoredFeed | null>(null)
  const [connection, setConnection] = useState<Connection>(
    typeof EventSource === 'undefined' ? 'unsupported' : 'connecting',
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (typeof EventSource === 'undefined') return
    const source = new EventSource('/api/market/monitored/events')
    source.onopen = () => {
      setConnection('connected')
      setError(null)
    }
    source.onmessage = (event) => {
      try {
        const parsed: unknown = JSON.parse(event.data)
        if (!isMonitoredFeed(parsed)) throw new Error('Malformed market-data snapshot')
        setFeed(parsed)
        setError(null)
      } catch {
        setFeed(null)
        setError('The market feed sent an invalid update. Prices are unavailable.')
      }
    }
    source.onerror = () => {
      setConnection('reconnecting')
      setError('Market updates interrupted. Attempting to reconnect.')
    }
    return () => source.close()
  }, [])

  return { feed, connection, error }
}
