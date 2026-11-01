import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import axe from 'axe-core'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Listbox } from '../src/components/ui'

// Headless UI 的 anchor 定位（floating-ui）在 jsdom 下需要 ResizeObserver 兜底。
class ResizeObserverStub {
  observe() { /* jsdom 无布局，无需实际观测 */ }
  unobserve() { /* 同上 */ }
  disconnect() { /* 同上 */ }
}
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
}

const FRUITS = [
  { value: 'apple', label: '苹果' },
  { value: 'banana', label: '香蕉' },
  { value: 'cherry', label: '樱桃' },
]

describe('Listbox（FL-D991 统一下拉）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('渲染当前选中项并可经 aria label 定位', () => {
    render(<Listbox label="水果" value="banana" onChange={() => undefined} options={FRUITS} />)
    const button = screen.getByRole('button', { name: '水果' })
    expect(button).toHaveTextContent('香蕉')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('点击打开面板并用鼠标选择，onChange 直传值', () => {
    const onChange = vi.fn()
    render(<Listbox label="水果" value="apple" onChange={onChange} options={FRUITS} />)
    fireEvent.click(screen.getByRole('button', { name: '水果' }))
    const listbox = screen.getByRole('listbox')
    expect(listbox).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '苹果' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('option', { name: '樱桃' }))
    expect(onChange).toHaveBeenCalledWith('cherry')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('数值型值原样回传（分页每页条数场景）', () => {
    const onChange = vi.fn()
    render(<Listbox label="每页条数" value={20} onChange={onChange} options={[20, 50, 100].map((n) => ({ value: n, label: n }))} />)
    fireEvent.click(screen.getByRole('button', { name: '每页条数' }))
    fireEvent.click(screen.getByRole('option', { name: '50' }))
    expect(onChange).toHaveBeenCalledWith(50)
  })

  it('键盘可达：Space 打开、方向键导航、Enter 选取', async () => {
    const onChange = vi.fn()
    render(<Listbox label="水果" value="apple" onChange={onChange} options={FRUITS} />)
    const button = screen.getByRole('button', { name: '水果' })
    button.focus()
    fireEvent.keyDown(button, { key: ' ' })
    // 打开后焦点落在 listbox 容器，选中项异步获得 data-focus（Headless UI 状态机经 rAF 就位）
    await waitFor(() => expect(screen.getByRole('option', { name: '苹果' })).toHaveAttribute('data-focus'))
    const active = () => document.activeElement as HTMLElement
    fireEvent.keyDown(active(), { key: 'ArrowDown' })
    await waitFor(() => expect(screen.getByRole('option', { name: '香蕉' })).toHaveAttribute('data-focus'))
    fireEvent.keyDown(active(), { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith('banana')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('Esc 关闭且不改值', async () => {
    const onChange = vi.fn()
    render(<Listbox label="水果" value="apple" onChange={onChange} options={FRUITS} />)
    const button = screen.getByRole('button', { name: '水果' })
    button.focus()
    fireEvent.keyDown(button, { key: ' ' })
    await waitFor(() => expect(screen.getByRole('option', { name: '苹果' })).toHaveAttribute('data-focus'))
    fireEvent.keyDown(document.activeElement as HTMLElement, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument())
    expect(onChange).not.toHaveBeenCalled()
  })

  it('禁用态不可打开', () => {
    render(<Listbox label="水果" value="apple" onChange={() => undefined} options={FRUITS} disabled />)
    const button = screen.getByRole('button', { name: '水果' })
    expect(button).toBeDisabled()
    fireEvent.click(button)
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('表单内开合与选取不触发提交', () => {
    const onSubmit = vi.fn((event: Event) => event.preventDefault())
    const onChange = vi.fn()
    render(<form onSubmit={(event) => { event.preventDefault(); onSubmit(event.nativeEvent) }}>
      <Listbox label="水果" value="apple" onChange={onChange} options={FRUITS} />
    </form>)
    fireEvent.click(screen.getByRole('button', { name: '水果' }))
    fireEvent.click(screen.getByRole('option', { name: '樱桃' }))
    expect(onChange).toHaveBeenCalledWith('cherry')
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('屏幕阅读器语义：haspopup/expanded/listbox/option/selected', async () => {
    render(<Listbox label="水果" value="banana" onChange={() => undefined} options={FRUITS} />)
    const button = screen.getByRole('button', { name: '水果' })
    expect(button).toHaveAttribute('aria-haspopup', 'listbox')
    expect(button).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(screen.getAllByRole('option')).toHaveLength(3)
    expect(screen.getByRole('option', { name: '香蕉' })).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('listbox')))
  })

  it('label 文字包裹时可作为无障碍名称（Tasks/CompareCard 用法）', () => {
    render(<label>状态<Listbox value="" onChange={() => undefined} options={[{ value: '', label: '全部状态' }, { value: 'queued', label: '排队中' }]} /></label>)
    // label 文字提供无障碍名称（与原生 select 语义等同：名称=标签，当前值由读屏在展开/导航时播报）
    expect(screen.getByRole('button', { name: '状态' })).toBeInTheDocument()
  })

  it('axe 审计：打开状态无违规（屏幕阅读器/色彩结构）', async () => {
    const { container } = render(<Listbox label="水果" value="apple" onChange={() => undefined} options={FRUITS} />)
    fireEvent.click(screen.getByRole('button', { name: '水果' }))
    await waitFor(() => expect(screen.getByRole('option', { name: '苹果' })).toHaveAttribute('data-focus'))
    // region/color-contrast 与 components.test.tsx 同约定豁免：孤立渲染无 landmark、令牌配色另由视觉截图把关
    const results = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } })
    expect(results.violations).toEqual([])
    expect(container).toBeTruthy()
  })

  it('value 不在 options 时展示首项，不回显原始码', () => {
    render(<Listbox label="水果" value="MISSING_CODE" onChange={() => undefined} options={FRUITS} />)
    const button = screen.getByRole('button', { name: '水果' })
    expect(button).toHaveTextContent('苹果')
    expect(button).not.toHaveTextContent('MISSING_CODE')
  })
})
