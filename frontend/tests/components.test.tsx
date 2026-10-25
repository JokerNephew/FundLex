import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import axe from 'axe-core'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SplitPane } from '../src/components/document/SplitPane'
import { SafeCompareDocument } from '../src/pages/Compare/ComparePage'
import { AppShell } from '../src/components/layout/AppShell'

vi.mock('../src/api/hooks', () => ({
  useTasks: () => ({ data: { items: [], total: 0 }, error: null, loading: false, refreshing: false, refetch: vi.fn() }),
}))

vi.mock('../src/stores/auth', () => ({
  useAuthStore: (selector?: (state: unknown) => unknown) => {
    const state = {
      user: { id: 'user-1', username: 'tester', display_name: '测试用户', role: 'user' },
      capabilities: { app_version: 'test' },
      logout: vi.fn(),
    }
    return selector ? selector(state) : state
  },
}))

describe('responsive and accessibility component regressions', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('switches both directions between mobile split panes', () => {
    render(<SplitPane left={<p>合同原文面板</p>} right={<p>修订清单面板</p>} leftLabel="合同呈现" rightLabel="修订清单" />)
    const left = screen.getByRole('tab', { name: '合同呈现' })
    const right = screen.getByRole('tab', { name: '修订清单' })
    expect(left).toHaveAttribute('aria-selected', 'true')
    expect(right).toHaveAttribute('aria-selected', 'false')

    fireEvent.click(right)
    expect(right).toHaveAttribute('aria-selected', 'true')
    expect(left).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByText('修订清单面板').closest('section')).toHaveClass('is-mobile-visible')

    fireEvent.click(left)
    expect(left).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('合同原文面板').closest('section')).toHaveClass('is-mobile-visible')
  })

  it('keeps Compare diff activation keyboard reachable and drops unsafe markup', async () => {
    const onDiff = vi.fn()
    const { container } = render(<SafeCompareDocument
      side="left"
      html={'<p>安全文本 <span class="compare-diff modify" data-diff-id="D1">修改</span> <span class="compare-diff diff-insert" data-diff-id="D2">新增</span> <span class="compare-diff-delete" data-diff-id="D3">删除</span></p><script>window.bad=true</script><img src="/private" onerror="window.bad=true">'}
      onDiff={onDiff}
    />)
    const marker = screen.getAllByRole('button', { name: '定位此处差异' })[0]
    fireEvent.keyDown(marker, { key: 'Enter' })
    expect(onDiff).toHaveBeenCalledWith('D1')
    expect(container.querySelector('[data-diff-id="D1"]')).toHaveClass('modify')
    expect(container.querySelector('[data-diff-id="D2"]')).toHaveClass('insert')
    expect(container.querySelector('[data-diff-id="D3"]')).toHaveClass('delete')
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(results.violations).toEqual([])
  })

  it('focuses and closes the help dialog with Escape, returning focus to its trigger', async () => {
    render(<MemoryRouter initialEntries={['/tasks']}><Routes><Route path="*" element={<AppShell />} /></Routes></MemoryRouter>)
    const trigger = screen.getByRole('button', { name: '帮助中心' })
    fireEvent.click(trigger)
    const dialog = await screen.findByRole('dialog', { name: '帮助中心' })
    const close = screen.getByRole('button', { name: '关闭帮助中心' })
    await waitFor(() => expect(document.activeElement).toBe(close))
    expect(dialog).toBeInTheDocument()
    expect((document.querySelector('.shell-body') as HTMLElement).inert).toBe(true)

    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '知道了' }))
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(close)

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(document.activeElement).toBe(trigger)
  })
})
