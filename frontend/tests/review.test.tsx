import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReviewPage } from '../src/pages/Review/ReviewPage'

let revisionView = {
  document_id: 'doc-1',
  html: '<p>合同原文</p>',
  revisions: [{ del_id: 1, ins_id: 2, index: 1, operation: 'replace', before: '旧文', after: '新文' }],
}

const mutateAsync = vi.fn().mockResolvedValue({ accepted: [1], rejected: [] })

vi.mock('../src/api/hooks', () => ({
  useAllTaskDocuments: () => ({ data: [{ task_id: 'task-1', document_id: 'doc-1', name: '测试合同.docx', delivery_status: 'incomplete', downloads: { redline: '/download' } }], error: null, loading: false, refetch: vi.fn() }),
  useTaskDocument: () => ({ data: { task_id: 'task-1', document_id: 'doc-1', name: '测试合同.docx', delivery_status: 'incomplete', downloads: { redline: '/download' } }, error: null, loading: false, refetch: vi.fn() }),
  useRevisions: () => ({ data: revisionView, error: null, loading: false, refetch: vi.fn() }),
  useReviewMutation: () => ({ mutateAsync, isPending: false }),
}))

vi.mock('../src/stores/auth', () => ({
  useAuthStore: (selector: (state: unknown) => unknown) => selector({ user: { id: 'user-1', username: 'tester' } }),
}))

function renderReview() {
  return render(<MemoryRouter initialEntries={['/tasks/task-1/documents/doc-1/review']}><Routes><Route path="/tasks/:taskId/documents/:documentId/review" element={<ReviewPage />} /></Routes></MemoryRouter>)
}

describe('Review pending and draft safety', () => {
  afterEach(() => {
    cleanup()
    localStorage.clear()
    mutateAsync.mockClear()
  })

  it('keeps selected artifact generation disabled until every revision is decided', async () => {
    renderReview()
    const generate = screen.getByRole('button', { name: '生成选择版合同' })
    expect(generate).toBeDisabled()
    expect(screen.getAllByText(/待处理\s+1/).length).toBeGreaterThan(0)

    fireEvent.click(screen.getAllByRole('button', { name: '接受' })[0])
    await waitFor(() => expect(generate).toBeEnabled())
    fireEvent.click(generate)
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({
      taskId: 'task-1',
      documentId: 'doc-1',
      allAccepted: true,
      decisions: [{ del_id: 1, decision: 'accept' }],
    }))
  })

  it('does not carry an accepted draft into a changed revision fingerprint', async () => {
    const first = renderReview()
    fireEvent.click(screen.getAllByRole('button', { name: '接受' })[0])
    await waitFor(() => expect(screen.getByRole('button', { name: '生成选择版合同' })).toBeEnabled())
    first.unmount()

    revisionView = { ...revisionView, html: '<p>合同原文已更新</p>' }
    renderReview()
    expect(screen.getByRole('button', { name: '生成选择版合同' })).toBeDisabled()
    expect(screen.getAllByText(/待处理\s+1/).length).toBeGreaterThan(0)
    revisionView = { ...revisionView, html: '<p>合同原文</p>' }
  })
})
