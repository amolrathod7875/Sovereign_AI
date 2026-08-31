import { useEffect, useState } from 'react'
import { Shield, CheckCircle, XCircle, Activity, AlertCircle, Wifi, WifiOff } from 'lucide-react'
import { apiClient } from '../lib/api/client'
import { useSystemStore } from '../lib/store'
import type { NetworkEvent, NetworkMonitorState } from '../lib/api/types'

export default function NetworkMonitor() {
  const status = useSystemStore((s) => s.status)
  const [events, setEvents] = useState<NetworkEvent[]>([])
  const [connectionState, setConnectionState] = useState<NetworkMonitorState>('disconnected')
  const [externalCallsLive, setExternalCallsLive] = useState<number | null>(null)
  const [blockedLive, setBlockedLive] = useState<number | null>(null)

  // Helper to determine if a destination is local
  const isLocalDestination = (host: string): boolean => {
    return host === 'localhost' || 
           host === '127.0.0.1' || 
           host.startsWith('192.168.') ||
           host.startsWith('10.') ||
           host.startsWith('172.') ||
           host.includes('qdrant') ||
           host.includes('postgres') ||
           host.includes('piston') ||
           host.includes('vllm')
  }

  useEffect(() => {
    let cleanup: (() => void) | null = null

    const initializeConnection = async () => {
      // Load initial events
      try {
        const initialEvents = await apiClient.getNetworkEvents(100)
        setEvents(initialEvents)
      } catch (error) {
        console.error('Failed to load initial network events:', error)
      }

      // Start SSE connection
      setConnectionState('connecting')
      cleanup = apiClient.createNetworkMonitorStream(
        (event: NetworkEvent) => {
          // Add new event to the beginning of the list
          setEvents(prev => [event, ...prev.slice(0, 99)]) // Keep last 100 events
          
          // Update live counters based on event type
          if (event.action === 'BLOCKED') {
            setBlockedLive(prev => (prev ?? 0) + 1)
          }
          
          // Check if this is an external API call (not local/internal)
          if (event.action !== 'LOCAL' && !isLocalDestination(event.destination_host)) {
            setExternalCallsLive(prev => (prev ?? 0) + 1)
          }
        },
        (error: Error) => {
          console.error('Network monitor SSE error:', error)
          setConnectionState('error')
        },
        () => {
          setConnectionState('connected')
        },
        () => {
          setConnectionState('disconnected')
        }
      )
    }

    initializeConnection()

    return () => {
      cleanup?.()
    }
  }, [isLocalDestination])

  const externalCalls = externalCallsLive ?? status?.external_api_calls ?? 0
  const blocked = blockedLive ?? status?.blocked_connections ?? 0

  const formatEventTime = (timestamp: string): string => {
    try {
      return new Date(timestamp).toLocaleTimeString()
    } catch {
      return timestamp
    }
  }

  const getConnectionStateIndicator = () => {
    switch (connectionState) {
      case 'connected':
        return <Wifi className="w-4 h-4 text-accent-success" />
      case 'connecting':
        return <Wifi className="w-4 h-4 text-accent-primary animate-pulse" />
      case 'reconnecting':
        return <Wifi className="w-4 h-4 text-accent-warning animate-pulse" />
      case 'error':
        return <WifiOff className="w-4 h-4 text-accent-danger" />
      case 'disconnected':
      default:
        return <WifiOff className="w-4 h-4 text-text-secondary" />
    }
  }

  const getConnectionStateText = (): string => {
    switch (connectionState) {
      case 'connected': return 'Live monitoring active'
      case 'connecting': return 'Connecting to network monitor...'
      case 'reconnecting': return 'Reconnecting...'
      case 'error': return 'Connection failed'
      case 'disconnected': return 'Disconnected'
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-background-secondary rounded-lg border border-border p-6 text-center">
        <div className="flex items-center justify-center gap-2 text-accent-sovereign mb-4">
          <Shield className="w-8 h-8" />
          <span className="text-xl font-bold">SOVEREIGN RUNTIME</span>
        </div>
        <div className="flex items-center justify-center gap-2 mb-2">
          <div className="w-3 h-3 rounded-full bg-accent-sovereign animate-pulse" />
          <span className="text-lg font-bold text-text-primary">LOCAL / AIR-GAPPED</span>
        </div>
        <p className="text-xs text-text-secondary">
          Status is reported by the backend probe — localhost/loopback traffic is not counted as external.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-center">
          <p className="text-3xl font-bold text-accent-success">{externalCalls}</p>
          <p className="text-xs text-text-secondary">External AI Calls</p>
        </div>
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-center">
          <p className="text-3xl font-bold text-accent-primary">{blocked}</p>
          <p className="text-xs text-text-secondary">Blocked Connections</p>
        </div>
        <div className="bg-background-secondary rounded-lg border border-border p-4 text-center">
          <p className="text-3xl font-bold text-text-primary">local</p>
          <p className="text-xs text-text-secondary">Connection Scope</p>
        </div>
      </div>

      <div className="bg-background-secondary rounded-lg border border-border">
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-text-secondary" />
            <h3 className="text-sm font-semibold text-text-primary">Live Network Events</h3>
          </div>
          <div className="flex items-center gap-2">
            {getConnectionStateIndicator()}
            <span className="text-xs text-text-secondary">{getConnectionStateText()}</span>
          </div>
        </div>
        <div className="p-4">
          {events.length === 0 ? (
            <div className="text-center py-6">
              <CheckCircle className="w-12 h-12 mx-auto mb-3 text-accent-success opacity-50" />
              <p className="text-sm text-text-secondary">No outbound connections detected since system start</p>
              <p className="text-xs text-text-secondary mt-1">
                {connectionState === 'connected' ? 'Monitoring live...' : 'Waiting for connection...'}
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              <div className="grid grid-cols-4 gap-4 text-xs font-semibold text-text-secondary border-b border-border pb-2 mb-2">
                <span>Time</span>
                <span>Destination</span>
                <span>Action</span>
                <span>Process</span>
              </div>
              {events.slice(0, 20).map((e) => (
                <div key={e.id} className="grid grid-cols-4 gap-4 text-xs font-mono items-center py-1">
                  <div className="flex items-center gap-2">
                    {e.action === 'BLOCKED' ? (
                      <XCircle className="w-3 h-3 text-accent-danger flex-shrink-0" />
                    ) : e.action === 'LOCAL' ? (
                      <CheckCircle className="w-3 h-3 text-accent-success flex-shrink-0" />
                    ) : (
                      <AlertCircle className="w-3 h-3 text-accent-warning flex-shrink-0" />
                    )}
                    <span className="text-text-primary">{formatEventTime(e.timestamp)}</span>
                  </div>
                  <span className="text-text-primary">
                    {e.destination_host}:{e.destination_port}
                  </span>
                  <span className={`font-semibold ${
                    e.action === 'BLOCKED' ? 'text-accent-danger' :
                    e.action === 'LOCAL' ? 'text-accent-success' :
                    'text-accent-warning'
                  }`}>
                    {e.action}
                  </span>
                  <span className="text-text-secondary">{e.process || 'unknown'}</span>
                </div>
              ))}
              {events.length > 20 && (
                <div className="text-xs text-text-secondary text-center pt-2 border-t border-border">
                  Showing latest 20 of {events.length} events
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
