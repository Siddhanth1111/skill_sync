import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../api/index.js'
import { setUnauthorizedHandler, tokenStore } from '../api/client.js'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export const homeFor = (role) => ({ recruiter: '/recruiter', student: '/student', admin: '/admin' }[role] || '/login')

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [booting, setBooting] = useState(!!tokenStore.get())

  const signOut = useCallback(() => { tokenStore.clear(); setUser(null) }, [])

  useEffect(() => {
    setUnauthorizedHandler(signOut) // an expired or revoked token signs the user out everywhere
    if (!tokenStore.get()) return
    api.me().then(setUser).catch(() => tokenStore.clear()).finally(() => setBooting(false))
  }, [signOut])

  const accept = (res) => { tokenStore.set(res.access_token); setUser(res.user); return res.user }
  const value = useMemo(() => ({
    user, booting, signOut,
    login: async (email, password) => accept(await api.login({ email, password })),
    register: async (body) => accept(await api.register(body)),
  }), [user, booting, signOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
