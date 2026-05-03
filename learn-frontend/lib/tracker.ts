import api from './api'

class EventTracker {
  private sessionId: string = ''
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null
  private videoCompletedNodes = new Set<string>()

  async startSession() {
    try {
      const res = await api.post('/auth/google', {})
      this.sessionId = res.data.session_id
      this.startHeartbeat()
    } catch {}
  }

  setSessionId(id: string) {
    this.sessionId = id
    this.startHeartbeat()
  }

  startHeartbeat() {
    if (this.heartbeatInterval) return
    this.heartbeatInterval = setInterval(async () => {
      if (this.sessionId) {
        try { await api.post('/auth/heartbeat', { session_id: this.sessionId }) } catch {}
      }
    }, 30000)
  }

  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval)
      this.heartbeatInterval = null
    }
  }

  getSessionId() { return this.sessionId }

  async log(eventType: string, entityId: string, value: number, metadata: object = {}) {
    if (!this.sessionId) return
    try {
      await api.post('/events/log', {
        session_id: this.sessionId,
        event_type: eventType,
        entity_id: entityId,
        value,
        metadata: { ...metadata, timestamp: new Date().toISOString() }
      })
    } catch {}
  }

  initScrollTracking(nodeId: string) {
    const milestones = [25, 50, 75, 100]
    const logged = new Set<number>()
    const handler = () => {
      const scrollPct = Math.round(
        (window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100
      )
      milestones.forEach(m => {
        if (scrollPct >= m && !logged.has(m)) {
          logged.add(m)
          this.log('scroll_milestone', nodeId, m / 100)
        }
      })
    }
    window.addEventListener('scroll', handler)
    return () => window.removeEventListener('scroll', handler)
  }

  initAudioTracking(audioElement: HTMLAudioElement, nodeId: string) {
    audioElement.addEventListener('play', () => this.log('audio_play', nodeId, 0))
    audioElement.addEventListener('pause', () => {
      const pct = audioElement.currentTime / audioElement.duration
      this.log('audio_pause', nodeId, pct)
    })
    audioElement.addEventListener('ended', () => this.log('audio_complete', nodeId, 1.0))
  }
}

export const tracker = new EventTracker()

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => tracker.stopHeartbeat())
}