import { Listbox as HeadlessListbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/react'
import type { ReactNode } from 'react'

export type ListboxOptionItem<T extends string | number = string> = {
  value: T
  label: ReactNode
  disabled?: boolean
}

export type ListboxProps<T extends string | number = string> = {
  /** 当前值，应与 options 某项相等；不等时按钮展示首项（与原生 select 一致），不会回显原始码 */
  value: T
  /** 直接回传所选值（非事件对象），类型与 options[].value 一致（string | number） */
  onChange: (value: T) => void
  options: ReadonlyArray<ListboxOptionItem<T>>
  /** 无可见文字包裹时的无障碍名称；被 <label> 文字包裹时可省略 */
  label?: string
  /** 附加到按钮上的样式类（如紧凑变体） */
  className?: string
  disabled?: boolean
}

// 统一下拉（FL-D991）：@headlessui/react Listbox 封装，替代原生 <select>。
// 键盘可达（↑/↓ 导航、Enter/Space 开合、Esc 关闭、字符定位）、焦点环与 --ctl-*
// 控件令牌矩阵一致，选项面板走 --surface/--shadow-overlay 令牌；面板用
// var(--button-width) 与按钮等宽，anchor="bottom start" 贴按钮下缘展开。
export function Listbox<T extends string | number>({ value, onChange, options, label, className = '', disabled }: ListboxProps<T>) {
  const current = options.find((option) => option.value === value)
  return (
    <HeadlessListbox value={value} onChange={onChange} disabled={disabled}>
      <ListboxButton type="button" className={`ui-listbox-button ${className}`.trim()} aria-label={label}>
        <span className="ui-listbox-value">{current ? current.label : options[0]?.label ?? ''}</span>
        <span className="ui-listbox-chevron" aria-hidden="true" />
      </ListboxButton>
      <ListboxOptions anchor="bottom start" className="ui-listbox-options">
        {options.map((option) => (
          <ListboxOption key={option.value} value={option.value} disabled={option.disabled} className="ui-listbox-option">
            <span className="ui-listbox-option-label">{option.label}</span>
            <span className="ui-listbox-option-check" aria-hidden="true" />
          </ListboxOption>
        ))}
      </ListboxOptions>
    </HeadlessListbox>
  )
}
