import { useEffect, useState } from 'react'
import {
  isMarketSnapshot,
  type MarketSnapshot,
  type StreamConnection,
} from './marketData'

export function useMarketStream() {
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null)
  const [connection, setConnection] = useState<StreamConnection>(
    typeof EventSource === 'undefined' ? 'unsupported' : 'connecting',
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (typeof EventSource === 'undefined') {
      return
    }

    const source = new EventSource('/api/market/events')

    source.onopen = () => {
      setConnection('connected')
      setError(null)
    }

    source.onmessage = (event) => {
      try {
        const data: unknown = JSON.parse(event.data)

        if (!isMarketSnapshot(data)) {
          throw new Error('Invalid market snapshot')
        }

        setSnapshot(data)
        setConnection('connected')
        setError(null)
      } catch {
        setSnapshot(null)
        setError('An invalid market update was received.')
      }
    }

    source.onerror = () => {
      setConnection(
        source.readyState === EventSource.CLOSED
          ? 'disconnected'
          : 'reconnecting',
      )
      setError('Market updates interrupted. Reconnecting when possible.')
    }

    return () => {
      source.close()
    }
  }, [])

  return { snapshot, connection, error }
}
