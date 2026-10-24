import type { MarkerDecision } from '../document'

export interface RevisionItem {
  index?: number
  del_id: number
  ins_id?: number
  revision_ids?: number[]
  before?: string
  after?: string
  operation?: string
  rule_id?: string
  section?: string
  location?: string
  mapped?: boolean
  [key: string]: unknown
}

export type RevisionDecisions = Record<string, MarkerDecision>
