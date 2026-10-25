import { render, screen } from '@testing-library/react'
import axe from 'axe-core'
import { describe, expect, it } from 'vitest'
import { DocumentViewer } from '../src/components/document/DocumentViewer'

describe('DocumentViewer security and accessibility boundary', () => {
  it('renders inert allow-listed markup and drops active elements', () => {
    render(<DocumentViewer html={'<h2>合同条款</h2><p onclick="alert(1)">正文<script>alert(1)</script><img src="/secret" /></p><iframe src="/frame"></iframe>'} />)

    expect(screen.getByText('合同条款')).toBeInTheDocument()
    expect(screen.getByText('正文')).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
    expect(document.querySelector('img')).toBeNull()
    expect(document.querySelector('iframe')).toBeNull()
    expect(document.querySelector('[onclick]')).toBeNull()
  })

  it('has no axe violations for an empty document state', async () => {
    const { container } = render(<DocumentViewer />)
    const results = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
    expect(results.violations).toEqual([])
  })
})
