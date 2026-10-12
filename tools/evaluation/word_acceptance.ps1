param([string]$FixtureDirectory = 'var/evaluation/word_fixture')
$ErrorActionPreference = 'Stop'
$folder = (Resolve-Path -LiteralPath $FixtureDirectory).Path
$result = [ordered]@{ engine='Microsoft Word COM'; hidden=$true; manual_visual_inspection=$false; status='blocked'; word_version=$null; word_build=$null }
$word = $null
$documents = @()
$inputHashes = [ordered]@{}
foreach ($name in @('source.docx','redline.docx','final.docx')) { $inputHashes[$name] = (Get-FileHash -LiteralPath (Join-Path $folder $name) -Algorithm SHA256).Hash }
function Get-Stories($document) {
    $values = [ordered]@{}
    foreach ($story in $document.StoryRanges) {
        $next = $story
        $index = 0
        while ($null -ne $next) {
            $values["$($story.StoryType):$index"] = [string]$next.Text
            $next = $next.NextStoryRange
            $index++
        }
    }
    return $values
}
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $word.Options.UpdateLinksAtOpen = $false
    $result.word_version = [string]$word.Version
    $result.word_build = [string]$word.Build
    $source = $word.Documents.Open((Join-Path $folder 'source.docx'), $false, $true)
    $documents += $source
    $redline = $word.Documents.Open((Join-Path $folder 'redline.docx'), $false, $false)
    $documents += $redline
    $final = $word.Documents.Open((Join-Path $folder 'final.docx'), $false, $true)
    $documents += $final
    $result.opened = @('source','redline','final')
    $result.source_revision_count = $source.Revisions.Count
    $result.redline_revision_count_before = $redline.Revisions.Count
    $result.final_revision_count = $final.Revisions.Count
    $authors = @()
    foreach ($revision in $redline.Revisions) { $authors += [string]$revision.Author }
    $result.revision_authors = @($authors | Sort-Object -Unique)
    if ($source.Revisions.Count -ne 0 -or $final.Revisions.Count -ne 0) { throw 'Unexpected source/final revisions' }
    if ($redline.Revisions.Count -eq 0 -or @($authors | Where-Object { $_ -ne 'FundLexAcceptance' }).Count -gt 0) { throw 'Unexpected revision author or empty revisions' }
    # Input has zero old revisions, and every Word revision author is this fixture author.
    $redline.AcceptAllRevisions()
    $result.redline_revision_count_after = $redline.Revisions.Count
    $result.main_content_equal = ([string]$redline.Content.Text -ceq [string]$final.Content.Text)
    $sourceStories = Get-Stories $source
    $acceptedStories = Get-Stories $redline
    $finalStories = Get-Stories $final
    $result.story_keys = @($acceptedStories.Keys)
    $storyEqual = $acceptedStories.Count -eq $finalStories.Count
    foreach ($key in $acceptedStories.Keys) { if (-not $finalStories.Contains($key) -or $acceptedStories[$key] -cne $finalStories[$key]) { $storyEqual = $false } }
    $result.all_stories_equal = $storyEqual
    $otherStories = $true
    foreach ($key in $sourceStories.Keys) { if (-not $key.StartsWith('1:') -and $sourceStories[$key] -cne $acceptedStories[$key]) { $otherStories = $false } }
    $result.non_main_stories_unchanged = $otherStories
    $checks = [ordered]@{}
    foreach ($token in @('NON_TARGET_原有重复文本与收费条款。','TABLE_NON_TARGET','APPENDIX_NON_TARGET','第一部分 正文……1')) {
        $checks[$token] = ([string]$source.Content.Text).Contains($token) -and ([string]$redline.Content.Text).Contains($token) -and ([string]$final.Content.Text).Contains($token)
    }
    $result.non_target_tokens = $checks
    $result.toc_count_source = $source.TablesOfContents.Count
    $result.toc_count_accepted = $redline.TablesOfContents.Count
    $result.toc_count_final = $final.TablesOfContents.Count
    $result.toc_updated = $false
    $redline.SaveAs2((Join-Path $folder 'word_accepted.docx'), 16)
    $acceptedStories | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $folder 'word_accepted_stories.json') -Encoding utf8
    $finalStories | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $folder 'word_final_stories.json') -Encoding utf8
    $result.status = if ($result.main_content_equal -and $storyEqual -and $otherStories -and $result.redline_revision_count_after -eq 0 -and -not ($checks.Values -contains $false)) { 'passed' } else { 'failed' }
} catch {
    $result.error_type = $_.Exception.GetType().FullName
    $result.error = $_.Exception.Message
    $result.hresult = $_.Exception.HResult
} finally {
    foreach ($document in $documents) { try { $document.Close(0) } catch {} }
    if ($null -ne $word) { try { $word.Quit(0) } catch {}; [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) }
    $result.input_sha256_before = $inputHashes
    $result.input_sha256_after = [ordered]@{}
    $hashesEqual = $true
    foreach ($name in $inputHashes.Keys) {
        $hash = (Get-FileHash -LiteralPath (Join-Path $folder $name) -Algorithm SHA256).Hash
        $result.input_sha256_after[$name] = $hash
        if ($hash -cne $inputHashes[$name]) { $hashesEqual = $false }
    }
    $result.input_files_unchanged = $hashesEqual
    if (-not $hashesEqual) { $result.status = 'failed' }
    $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $folder 'word_acceptance.json') -Encoding utf8
}
$result | ConvertTo-Json -Depth 10
if ($result.status -ne 'passed') { exit 1 }
