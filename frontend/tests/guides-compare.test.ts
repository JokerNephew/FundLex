import { describe, expect, it } from 'vitest'
import { defaultCompareTargets } from '../src/pages/Guides/CompareCard'
import type { GuideSummary } from '../src/types'

function guide(id: string, status = 'parsed', extra: Partial<GuideSummary> = {}): GuideSummary {
  return { id, built_in: false, filename: `${id}.docx`, status, ...extra }
}

describe('defaultCompareTargets', () => {
  it('defaults to the current version against its parent reparse chain', () => {
    const items = [guide('builtin-v1', 'released', { built_in: true }),
      guide('v2', 'parsed', { parent_version_id: 'v1', current: true }),
      guide('v1', 'parsed')]
    expect(defaultCompareTargets(items, 'v2')).toEqual({ target: 'v2', against: 'v1' })
  })

  it('falls back to the previous parsed version in the list', () => {
    const items = [guide('builtin-v1', 'released', { built_in: true }),
      guide('v2', 'parsed'), guide('v1', 'parsed')]
    expect(defaultCompareTargets(items, 'v2')).toEqual({ target: 'v2', against: 'v1' })
  })

  it('uses the first parsed version when nothing is current', () => {
    const items = [guide('builtin-v1', 'released', { built_in: true }), guide('v1', 'parsed')]
    const result = defaultCompareTargets(items, undefined)
    expect(['builtin-v1', 'v1']).toContain(result.against)
    expect(result.target).not.toEqual(result.against)
  })

  it('skips unparsed and failed versions', () => {
    const items = [guide('builtin-v1', 'released', { built_in: true }),
      guide('broken', 'failed'), guide('v1', 'parsed')]
    const result = defaultCompareTargets(items, 'v1')
    expect(result).toEqual({ target: 'v1', against: 'builtin-v1' })
  })

  it('returns empty targets with fewer than two parsed versions', () => {
    expect(defaultCompareTargets([guide('builtin-v1', 'released')], undefined))
      .toEqual({ target: 'builtin-v1', against: '' })
    expect(defaultCompareTargets([], undefined)).toEqual({ target: '', against: '' })
  })
})

