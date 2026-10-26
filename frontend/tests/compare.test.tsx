import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ComparePage } from '../src/pages/Compare/ComparePage'

const mocks = vi.hoisted(() => ({
  oldTaskRefetch: vi.fn(),
  tasksRefetch: vi.fn(),
  createMutateAsync: vi.fn(),
  uploadMutateAsync: vi.fn(),
  sealMutateAsync: vi.fn(),
  refetchCompareTask: vi.fn(),
}))

vi.mock('../src/api/hooks', () => ({
  useCompareTasks: () => ({ data: { items: [], total: 0 }, error: null, loading: false, refreshing: false, refetch: mocks.tasksRefetch }),
  useCompareTask: () => ({ data: undefined, error: null, loading: false, refreshing: false, refetch: mocks.oldTaskRefetch }),
  useCompareView: () => ({ data: undefined, error: null, loading: false, refreshing: false, refetch: vi.fn() }),
  useCompareTaskMutation: () => ({ mutateAsync: mocks.createMutateAsync, isPending: false }),
  useCompareUploadMutation: () => ({ mutateAsync: mocks.uploadMutateAsync, isPending: false }),
  useCompareSealMutation: () => ({ mutateAsync: mocks.sealMutateAsync, isPending: false }),
  refetchCompareTask: mocks.refetchCompareTask,
}))

const createdTask = {
  id: 'compare-task-1',
  name: '合同对比',
  status: 'pending',
  total: 1,
  pairs: [{ id: 'pair-1', label: '合同 1', status: 'pending', left: { name: '原版.docx' }, right: { name: '修订版.docx' } }],
}

function selectFiles() {
  const inputs = Array.from(document.querySelectorAll('.compare-side-inputs input[type="file"]'))
  expect(inputs).toHaveLength(2)
  fireEvent.change(inputs[0], { target: { files: [new File(['left'], '原版.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })] } })
  fireEvent.change(inputs[1], { target: { files: [new File(['right'], '修订版.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })] } })
}

describe('Compare first-upload recovery', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    mocks.oldTaskRefetch.mockReset()
    mocks.tasksRefetch.mockReset().mockResolvedValue(undefined)
    mocks.createMutateAsync.mockReset().mockResolvedValue(createdTask)
    mocks.uploadMutateAsync.mockReset().mockResolvedValue({ receipts: [{ status: 'accepted' }, { status: 'accepted' }] })
    mocks.sealMutateAsync.mockReset().mockResolvedValue({ ...createdTask, status: 'sealed' })
    mocks.refetchCompareTask.mockReset().mockResolvedValue({ ...createdTask, status: 'sealed' })
  })

  it('refreshes the newly created task by its explicit id instead of an old undefined-task closure', async () => {
    render(<ComparePage />)
    fireEvent.click(screen.getByRole('button', { name: '＋ 新建对比任务' }))
    selectFiles()
    fireEvent.click(screen.getByRole('button', { name: '开始上传并对比' }))

    await waitFor(() => expect(mocks.sealMutateAsync).toHaveBeenCalledWith('compare-task-1'))
    await waitFor(() => expect(mocks.refetchCompareTask).toHaveBeenCalledWith('compare-task-1'))
    expect(mocks.oldTaskRefetch).not.toHaveBeenCalled()
    expect(mocks.refetchCompareTask).not.toHaveBeenCalledWith('')
    expect(mocks.refetchCompareTask).not.toHaveBeenCalledWith(undefined)
  })

  it('does not report a successful seal query failure as an upload interruption', async () => {
    mocks.refetchCompareTask.mockRejectedValueOnce(new Error('查询任务失败'))
    render(<ComparePage />)
    fireEvent.click(screen.getByRole('button', { name: '＋ 新建对比任务' }))
    selectFiles()
    fireEvent.click(screen.getByRole('button', { name: '开始上传并对比' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('任务已提交，但状态刷新失败'))
    expect(screen.getByRole('alert')).not.toHaveTextContent('上传中断')
    expect(mocks.sealMutateAsync).toHaveBeenCalledWith('compare-task-1')
  })
})
