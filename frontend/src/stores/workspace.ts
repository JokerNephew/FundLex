import { create } from 'zustand'

interface WorkspaceState {
  selectedTaskId: string | null
  selectedDocumentId: string | null
  notice: { kind: 'info' | 'error' | 'success'; message: string } | null
  setTask: (id: string | null) => void
  setDocument: (id: string | null) => void
  notify: (message: string, kind?: 'info' | 'error' | 'success') => void
  clearNotice: () => void
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedTaskId: null,
  selectedDocumentId: null,
  notice: null,
  setTask: (selectedTaskId) => set({ selectedTaskId, selectedDocumentId: null }),
  setDocument: (selectedDocumentId) => set({ selectedDocumentId }),
  notify: (message, kind = 'info') => set({ notice: { message, kind } }),
  clearNotice: () => set({ notice: null }),
}))

export const useWorkspace = useWorkspaceStore
