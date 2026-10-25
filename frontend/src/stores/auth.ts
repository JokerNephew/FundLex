import { create } from 'zustand'
import { api } from '../api/endpoints'
import { AUTH_TOKEN_KEY, DEV_USER_KEY, SessionExpiredError } from '../api/client'
import type { Capabilities, User } from '../types'

interface AuthState {
  user: User | null
  token: string
  capabilities: Capabilities | null
  ready: boolean
  error: unknown
  setSession: (token: string, user: User) => void
  clearSession: () => void
  setCapabilities: (capabilities: Capabilities) => void
  load: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, displayName?: string) => Promise<void>
  logout: () => Promise<void>
  handleError: (error: unknown) => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  token: sessionStorage.getItem(AUTH_TOKEN_KEY) || '',
  capabilities: null,
  ready: false,
  error: null,
  setSession: (token, user) => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, token)
    set({ token, user, error: null })
    window.dispatchEvent(new CustomEvent('fundlex:auth-changed'))
  },
  clearSession: () => {
    sessionStorage.removeItem(AUTH_TOKEN_KEY)
    window.dispatchEvent(new CustomEvent('fundlex:auth-cleared'))
    set({ token: '', user: null })
  },
  setCapabilities: (capabilities) => set({ capabilities }),
  load: async () => {
    // The dev identity header is required even for the initial capabilities
    // request. Password mode ignores this header, so setting the local default
    // before the probe keeps both auth modes on the same bootstrap path.
    if (!get().token && !localStorage.getItem(DEV_USER_KEY)) {
      localStorage.setItem(DEV_USER_KEY, 'local-dev')
    }
    set({ ready: false, error: null })
    try {
      const capabilities = await api.capabilities()
      set({ capabilities })
      if (capabilities.login_required && get().token) {
        try { set({ user: await api.me() }) } catch { get().clearSession() }
      }
      set({ ready: true, error: null })
    } catch (error) {
      set({ ready: true, error })
    }
  },
  login: async (username, password) => {
    const session = await api.login(username, password)
    get().setSession(session.token, session.user)
  },
  register: async (username, password, displayName) => {
    const session = await api.register(username, password, displayName)
    get().setSession(session.token, session.user)
  },
  logout: async () => {
    try { await api.logout() } finally { get().clearSession() }
  },
  handleError: (error) => {
    if (error instanceof SessionExpiredError) get().clearSession()
  },
}))

if (typeof window !== 'undefined') {
  window.addEventListener('fundlex:session-expired', () => {
    useAuthStore.getState().clearSession()
  })
}

export const useAuth = useAuthStore
