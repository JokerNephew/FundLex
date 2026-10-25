import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
})

if (typeof window !== 'undefined') {
  const clear = () => { void queryClient.clear() }
  window.addEventListener('fundlex:auth-cleared', clear)
  window.addEventListener('fundlex:auth-changed', clear)
  window.addEventListener('fundlex:session-expired', clear)
}
