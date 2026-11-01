import { useState, type ChangeEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card } from '../../components/ui'
import { useCompareSealMutation, useCompareTaskMutation, useCompareUploadMutation, refetchCompareTask } from '../../api/hooks'
import type { ComparePairManifest } from '../../types'
import { PairInput, fileName, messageOf, relativePath, type PairDraft, type UploadDraft } from './shared'

// P2 新建比对（FL-D846：/compare/new）：任务名、A/B 文件夹配对、逐组文件与断点续传。
// 提交成功后进入 /compare/:taskId 比对工作台。
export function CompareNewPage() {
  const navigate = useNavigate()
  const createMutation = useCompareTaskMutation()
  const uploadMutation = useCompareUploadMutation()
  const sealMutation = useCompareSealMutation()
  const [pairs, setPairs] = useState<PairDraft[]>([{}])
  const [taskName, setTaskName] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [uploadDraft, setUploadDraft] = useState<UploadDraft>()
  const [folderFiles, setFolderFiles] = useState<{ left: File[]; right: File[] }>({ left: [], right: [] })

  const selectFiles = (index: number, side: 'left' | 'right', file?: File) => setPairs((current) => current.map((pair, itemIndex) => itemIndex === index ? { ...pair, [side]: file } : pair))
  const applyFolder = (side: 'left' | 'right', event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []).filter((file) => /\.docx$/i.test(file.name)).sort((a, b) => relativePath(a).localeCompare(relativePath(b)))
    if (!files.length) return
    const nextFolders = { ...folderFiles, [side]: files }
    setFolderFiles(nextFolders)
    const left = nextFolders.left; const right = nextFolders.right
    if (!left.length || !right.length) return
    const rightMap = new Map(right.map((file) => [relativePath(file), file])); const used = new Set<File>()
    const next: PairDraft[] = left.map((file) => { const match = rightMap.get(relativePath(file)); if (match) used.add(match); return { left: file, right: match } })
    for (const file of right) if (!used.has(file)) next.push({ left: undefined, right: file })
    setPairs(next)
    setMessage(`配成了 ${next.filter((pair) => pair.left && pair.right).length} 对；还有 ${next.filter((pair) => !pair.left || !pair.right).length} 个文件配不上对。`)
  }

  const continueUpload = async (draft: UploadDraft) => {
    setError(''); setMessage('')
    try {
      for (let index = draft.next; index < draft.files.length; index += 1) {
        const files = draft.files[index]; const manifest = draft.manifests[index]
        if (!files.left || !files.right) throw new Error(`第 ${index + 1} 组缺少原版或对比版文件。`)
        setMessage(`正在上传第 ${index + 1} / ${draft.files.length} 组…`)
        const result = await uploadMutation.mutateAsync({ id: draft.task.id, files: [files.left, files.right], clientIds: [manifest.left.client_id, manifest.right.client_id] })
        const receipts = result.receipts || []
        if (receipts.some((receipt) => !['accepted', 'already_accepted'].includes(receipt.status))) throw new Error(`第 ${index + 1} 对还没上传完。`)
        draft.next = index + 1; setUploadDraft({ ...draft })
      }
      await sealMutation.mutateAsync(draft.task.id)
    } catch (nextError) {
      setError(`上传断了：${messageOf(nextError, '文件没传完')}；传好的没丢，继续传就行。`)
      return
    }
    // 已进入工作台后再取不到任务由任务页自己轮询补齐；刷缓存失败仅作提示（保持原语义）。
    const notice = '已提交，对比任务正在处理。'
    let warning = ''
    try {
      await refetchCompareTask(draft.task.id)
    } catch (nextError) {
      warning = `任务已提交，但状态刷新失败：${messageOf(nextError, '服务暂时不可用')}。请稍后刷新。`
    }
    navigate(`/compare/${draft.task.id}`, { state: { notice, warning } })
  }

  const createTask = async () => {
    if (!pairs.length || pairs.some((pair) => !pair.left || !pair.right)) { setError('每组都需要同时选择原版和对比版 DOCX。'); return }
    const manifests: ComparePairManifest[] = pairs.map((pair, index) => ({ client_pair_id: `P${index + 1}`, label: `合同 ${index + 1}`, left: { client_id: `L${index}-${crypto.randomUUID()}`, name: fileName(pair.left), size: pair.left?.size || 0 }, right: { client_id: `R${index}-${crypto.randomUUID()}`, name: fileName(pair.right), size: pair.right?.size || 0 } }))
    try {
      const created = await createMutation.mutateAsync({ name: taskName.trim() || '合同对比', pairs: manifests, key: `compare-${crypto.randomUUID()}` })
      const draft = { task: created, manifests, files: pairs, next: 0 }; setUploadDraft(draft); await continueUpload(draft)
    } catch (nextError) { setError(`创建任务失败：${messageOf(nextError, '对比任务创建未完成')}`) }
  }

  return <div className="fundlex-compare-page">
    <div className="page-heading"><div><Button type="button" variant="quiet" onClick={() => navigate('/compare')}>← 返回对比任务列表</Button><h1>新建对比任务</h1></div></div>
    {error && <div className="error-state" role="alert">{error}</div>}{message && <div className="fundlex-message" role="status">{message}</div>}
    <Card className="compare-create"><label className="compare-task-name">任务名称<input value={taskName} maxLength={200} onChange={(event) => setTaskName(event.target.value)} placeholder="例如：法务与产品部合同差异" /></label><div className="compare-folder-actions"><label className="ui-button"><span>选择原版文件夹</span><input type="file" {...{ webkitdirectory: '', directory: '' } as Record<string, string>} multiple hidden onChange={(event) => applyFolder('left', event)} /></label><label className="ui-button"><span>选择对比版文件夹</span><input type="file" {...{ webkitdirectory: '', directory: '' } as Record<string, string>} multiple hidden onChange={(event) => applyFolder('right', event)} /></label><span className="muted">按相同相对路径配对；未配对文件可以手工补齐。</span></div>{pairs.map((pair, index) => <PairInput key={index} pair={pair} index={index} onChange={(side, file) => selectFiles(index, side, file)} onRemove={() => setPairs((current) => current.length > 1 ? current.filter((_, itemIndex) => itemIndex !== index) : current)} />)}<div className="action-row"><Button type="button" onClick={() => setPairs((current) => [...current, {}])}>＋ 添加一组</Button><Button type="button" variant="primary" disabled={createMutation.isPending || uploadMutation.isPending || sealMutation.isPending} onClick={() => void (uploadDraft ? continueUpload(uploadDraft) : createTask())}>{uploadDraft ? '继续上传' : '开始上传并对比'}</Button></div></Card>
  </div>
}
