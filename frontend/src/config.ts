/** Runtime URLs shared by the React shell and API client. */
export const APP_BASE_PATH = typeof window !== 'undefined'
  && (window.location.pathname === '/test' || window.location.pathname.startsWith('/test/'))
  ? '/test'
  : ''

export function appPath(path: string): string {
  if (!path.startsWith('/')) throw new Error('application path must start with /')
  return `${APP_BASE_PATH}${path}` || '/'
}
