import { createElement, forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import { DocumentMarker, type MarkerDecision } from './DocumentMarker'

export interface DocumentViewerHandle {
  scrollToRevision: (revisionId: string) => void
}

interface DocumentViewerProps {
  html?: string | null
  activeRevisionId?: string | null
  activeRevisionIds?: string[]
  decisions?: Record<string, MarkerDecision>
  onRevisionClick?: (revisionId: string) => void
  className?: string
}

const allowedTags = new Set([
  'article', 'aside', 'blockquote', 'br', 'caption', 'col', 'colgroup', 'dd', 'del', 'div',
  'dl', 'dt', 'em', 'figcaption', 'figure', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i',
  'ins', 'li', 'main', 'ol', 'p', 'pre', 'q', 'section', 'small', 'span', 'strong', 'sub',
  'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'u', 'ul',
])
const dropTags = new Set(['audio', 'canvas', 'embed', 'form', 'iframe', 'img', 'input', 'link', 'meta', 'object', 'script', 'select', 'style', 'svg', 'textarea', 'video'])
const voidTags = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'])
const allowedAttributes = new Set(['class', 'colspan', 'rowspan', 'scope', 'title'])

// The revisions endpoint owns this markup. We intentionally parse it into a
// small HTML allow-list and copy only inert presentation attributes; scripts,
// URLs, event handlers, forms and embedded resources never enter React.

function safeAttributes(element: Element): Record<string, string> {
  const attributes: Record<string, string> = {}
  for (const attribute of Array.from(element.attributes)) {
    const name = attribute.name.toLowerCase()
    if (allowedAttributes.has(name)) {
      if (name === 'class') attributes.className = attribute.value
      else attributes[name] = attribute.value
    }
  }
  return attributes
}

function renderNode(
  node: Node,
  key: string,
  activeRevisionId: string | null | undefined,
  activeRevisionIds: string[],
  decisions: Record<string, MarkerDecision>,
  onRevisionClick?: (revisionId: string) => void,
): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent
  if (node.nodeType !== Node.ELEMENT_NODE) return null
  const element = node as Element
  const tag = element.tagName.toLowerCase()
  if (dropTags.has(tag)) return null
  const children = Array.from(element.childNodes).map((child, index) => renderNode(child, `${key}-${index}`, activeRevisionId, activeRevisionIds, decisions, onRevisionClick))
  const revisionId = element.getAttribute('data-rev')
  if (revisionId) {
    const ids = revisionId.split(/[\s,]+/).filter(Boolean)
    const primaryId = ids[0]
    return <DocumentMarker
      key={key}
      revisionId={primaryId}
      decision={decisions[primaryId] || 'pending'}
      active={ids.some((id) => activeRevisionIds.includes(id)) || ids.includes(String(activeRevisionId || ''))}
      onClick={onRevisionClick}
    >{children}</DocumentMarker>
  }
  if (!allowedTags.has(tag)) return <span key={key}>{children}</span>
  // React forbids passing children to HTML void elements. DOMParser accepts
  // markup such as <hr>, and passing the recursively-built (even empty) array
  // as the third createElement argument makes React 19 throw error #137.
  if (voidTags.has(tag)) return createElement(tag, { key, ...safeAttributes(element) })
  return requireTag(tag, key, safeAttributes(element), children)
}

function requireTag(tag: string, key: string, attributes: Record<string, string>, children: ReactNode[]): ReactNode {
  // Keeping this factory in one place makes the parser's tag allow-list auditable.
  return createElement(tag, { key, ...attributes }, children)
}

export const DocumentViewer = forwardRef<DocumentViewerHandle, DocumentViewerProps>(function DocumentViewer({
  html,
  activeRevisionId,
  activeRevisionIds = activeRevisionId ? [activeRevisionId] : [],
  decisions = {},
  onRevisionClick,
  className = '',
}, ref) {
  const rootRef = useRef<HTMLDivElement>(null)
  const content = useMemo(() => {
    if (!html || typeof DOMParser === 'undefined') return []
    const document = new DOMParser().parseFromString(html, 'text/html')
    return Array.from(document.body.childNodes).map((node, index) => renderNode(node, String(index), activeRevisionId, activeRevisionIds, decisions, onRevisionClick))
  }, [activeRevisionId, activeRevisionIds, decisions, html, onRevisionClick])

  useImperativeHandle(ref, () => ({
    scrollToRevision(revisionId) {
      const target = rootRef.current?.querySelector(`[data-document-marker="${CSS.escape(revisionId)}"]`)
      target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    },
  }), [])

  useEffect(() => {
    if (activeRevisionId) {
      rootRef.current?.querySelector(`[data-document-marker="${CSS.escape(activeRevisionId)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [activeRevisionId])

  return <div ref={rootRef} className={`fundlex-document-viewer ${className}`.trim()} tabIndex={0} aria-label="合同原文与修订呈现">
    {content.length ? content : <p className="fundlex-muted">暂无可呈现的合同原文。</p>}
  </div>
})
