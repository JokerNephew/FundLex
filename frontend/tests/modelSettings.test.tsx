import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ModelSettingsPage } from '../src/pages/Settings/ModelSettings'

const { PROVIDERS, ROLE } = vi.hoisted(() => ({
  PROVIDERS: [
    { id: 'openai', label: 'OpenAI（兼容接口）', base_url: 'https://api.openai.com/v1',
      models: ['gpt-5.5', 'gpt-5-mini'],
      deprecated_models: [
        { id: 'gpt-4.1', note: '官方列入快照退役计划（2027-01-14 起）' },
      ] },
    { id: 'moonshot', label: '月之暗面 Kimi（兼容接口）', base_url: 'https://api.moonshot.cn/v1',
      models: ['kimi-k3.1-pro'],
      deprecated_models: [
        { id: 'moonshot-v1-8k', note: '2026-08-31 官方下线' },
      ] },
    { id: 'custom', label: '其他 OpenAI 兼容服务', base_url: '', models: [], deprecated_models: [] },
  ],
  ROLE: { source: 'personal', provider: 'openai', model: '', api_key_set: false,
    base_url: '', connection_id: '', system_model: '', verified: false } as const,
}))

vi.mock('../src/api/hooks', () => {
  // 稳定引用：data 对象每次返回都必须同一实例，否则 useEffect 依赖无限打摆。
  const data = { source: 'personal', primary: ROLE, review: { ...ROLE, provider: 'moonshot' },
                 review_inherits: false, providers: PROVIDERS }
  return {
    useModelSettings: () => ({ data, error: null, refetch: vi.fn() }),
    useModelSettingsMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  }
})

describe('ModelSettings 供应商建议清单（FL-D937(7) 灰置展示）', () => {
  afterEach(cleanup)

  it('编辑态：下线条目灰置展示且不进入可选项', async () => {
    render(<ModelSettingsPage />)
    const editButtons = await screen.findAllByRole('button', { name: '修改配置' })
    fireEvent.click(editButtons[0])
    // 在售建议进入 datalist
    const datalist = document.querySelector('#model-primary-suggestions') as HTMLDataListElement
    expect(datalist).toBeTruthy()
    expect(datalist.innerHTML).toContain('gpt-5.5')
    expect(datalist.innerHTML).not.toContain('gpt-4.1')
    // 下线条目灰置如实展示（<del>）
    const hint = screen.getByText(/已停用或拟停用/)
    expect(hint.innerHTML).toContain('<del>gpt-4.1</del>')
    expect(hint.textContent).toContain('2027-01-14')
  })

  it('review 卡切到 moonshot 时展示该供应商的下线说明', async () => {
    render(<ModelSettingsPage />)
    const editButtons = await screen.findAllByRole('button', { name: '修改配置' })
    fireEvent.click(editButtons[1])
    const hint = screen.getByText(/已停用或拟停用/)
    expect(hint.innerHTML).toContain('<del>moonshot-v1-8k</del>')
    expect(hint.textContent).toContain('2026-08-31')
  })

  it('无下线记录的供应商不显示灰置条', async () => {
    render(<ModelSettingsPage />)
    const editButtons = await screen.findAllByRole('button', { name: '修改配置' })
    fireEvent.click(editButtons[0])
    const select = screen.getByLabelText('供应商') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'custom' } })
    await waitFor(() => {
      expect(screen.queryByText(/已停用或拟停用/)).toBeNull()
    })
  })
})
