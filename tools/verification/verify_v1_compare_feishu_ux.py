"""Opt-in real V1 user-path acceptance; creates two disposable accounts.

No model calls. Pass a public contract and a controlled one-paragraph revision.
Credentials and OAuth state stay in memory; screenshots mask the personal QR.
Account cleanup is an explicit operator step using usernames in result.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from pathlib import Path
from zipfile import ZipFile

from lxml import etree
from playwright.sync_api import sync_playwright, expect


def paragraphs(path: Path, *, reject=False):
    with ZipFile(path) as archive:
        assert archive.testzip() is None
        root = etree.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    query = './/w:t[not(ancestor::w:ins)] | .//w:delText' if reject else './/w:t[not(ancestor::w:del)]'
    return [''.join(node.text or '' for node in p.xpath(query, namespaces=ns))
            for p in root.xpath('//w:body//w:p', namespaces=ns)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='https://fundlex.club')
    parser.add_argument('--left', type=Path, required=True)
    parser.add_argument('--right', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    name = 'ux-v1-' + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    result = {'username': name, 'other_username': name + '-other', 'model_calls': 0,
              'credentials_retained': False, 'screenshots_mask_oauth_qr': True}
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto(args.base, wait_until='domcontentloaded')
            page.locator('#register-link').click()
            page.locator('#register-username').fill(name)
            page.locator('#register-display').fill('V1体验验收')
            page.locator('#register-password').fill(password)
            page.locator('#register-confirm').fill(password)
            page.locator('#register-submit').click()
            expect(page.locator('#login-view')).to_be_hidden()
            page.locator('#logout-btn').click()
            page.locator('#login-username').fill(name)
            page.locator('#login-password').fill(password)
            page.locator('#login-submit').click()
            expect(page.locator('#login-view')).to_be_hidden()
            page.locator('[data-nav="compare"]').click()
            page.locator('#compare-new').click()
            page.locator('#compare-name').fill('V1体验改版真实公开合同验收')
            for side, path in [('left', args.left), ('right', args.right)]:
                with page.expect_file_chooser() as pending:
                    page.locator(f'[data-compare-choose="{side}"]').click()
                pending.value.set_files(str(path))
                expect(page.locator(f'[data-file-side="{side}"] .compare-file-name')).to_have_text(path.name)
            page.locator('#compare-create').screenshot(path=str(args.out / 'create-task.png'))
            with page.expect_response(lambda r: r.url.endswith('/seal'), timeout=120000) as sealed:
                page.locator('#compare-submit').click()
            assert sealed.value.status == 200
            page.wait_for_function("document.querySelector('[data-selection-choice]') && !document.querySelector('[data-selection-choice]').disabled", timeout=180000)
            assert page.locator('[data-selection-choice="right"]').count() == 1
            task_id = page.locator('[data-compare-task]').first.get_attribute('data-compare-task')
            result['task_id'] = task_id
            page.locator('[data-selection-choice="right"]').check()
            expect(page.locator('#compare-selection-status')).to_have_text('已保存')
            page.reload(wait_until='networkidle')
            page.locator(f'[data-compare-task="{task_id}"]').click()
            expect(page.locator('[data-selection-choice="right"]')).to_be_checked()
            with page.expect_response(lambda r: r.url.endswith('/selection/generate'), timeout=120000) as generated:
                page.locator('#compare-selection-generate').click()
            assert generated.value.status == 200
            expect(page.locator('#compare-selection-status')).to_contain_text('已生成 v1')
            downloads = {}
            for kind in ['selected_final', 'selected_redline', 'selection_report_json', 'selection_report_markdown']:
                button = page.locator(f'[data-selection-download$="/{kind}"]')
                with page.expect_download() as pending:
                    button.click()
                ext = '.docx' if kind.startswith('selected_') else '.json' if kind.endswith('json') else '.md'
                path = args.out / (kind + ext)
                pending.value.save_as(path)
                downloads[kind] = hashlib.sha256(path.read_bytes()).hexdigest()
            report = json.loads((args.out / 'selection_report_json.json').read_text())
            for kind in ['selected_final', 'selected_redline']:
                assert downloads[kind] == report['outputs'][kind]['sha256']
            final = paragraphs(args.out / 'selected_final.docx')
            source = paragraphs(args.left)
            assert final == paragraphs(args.right)
            assert final == paragraphs(args.out / 'selected_redline.docx')
            assert source == paragraphs(args.out / 'selected_redline.docx', reject=True)
            assert len(source) == len(final)
            changed = [i for i, (a, b) in enumerate(zip(source, final)) if a != b]
            assert len(changed) == 1
            result.update(downloads=downloads, changed_paragraphs=changed, report_hashes_match=True,
                          accepted_redline_matches_final=True, rejected_redline_matches_source=True)
            final_url = page.locator('[data-selection-download$="/selected_final"]').get_attribute('data-selection-download')
            assert context.request.get(args.base + final_url).status == 401
            other = context.request.post(args.base + '/api/auth/register', data={
                'username': result['other_username'], 'password': password, 'display_name': '隔离验证'})
            assert other.status == 201
            assert context.request.get(args.base + final_url, headers={
                'Authorization': 'Bearer ' + other.json()['token']}).status == 404
            result['download_isolation'] = {'unauthenticated': 401, 'cross_account': 404}
            for width in [1440, 1280, 768, 390]:
                page.set_viewport_size({'width': width, 'height': 1000})
                metrics = page.evaluate('''() => {
                  const d=document.querySelector('.compare-document-area').getBoundingClientRect();
                  const r=document.querySelector('.compare-diff-rail').getBoundingClientRect();
                  return {railRight:r.x>=d.right,railBefore:r.bottom<=d.top,
                    overflow:document.documentElement.scrollWidth>innerWidth};
                }''')
                assert not metrics['overflow']
                assert metrics['railRight'] if width > 760 else metrics['railBefore']
                result.setdefault('viewports', {})[str(width)] = metrics
                page.locator('#compare-viewer').screenshot(path=str(args.out / f'reader-{width}.png'))
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.locator('[data-nav="settings"]').click()
            expect(page.locator('#feishu-binding-badge')).to_have_text('未绑定')
            assert page.locator('#feishu-binding-code-btn').count() == 0
            page.locator('#view-settings').screenshot(path=str(args.out / 'feishu-unbound.png'))
            with page.expect_response(lambda r: r.url.endswith('/oauth/start')) as started:
                page.locator('#feishu-oauth-btn').click()
            assert started.value.status == 200
            page.wait_for_function("document.querySelector('#feishu-oauth-qr img')?.naturalWidth===650")
            page.add_script_tag(url='https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js')
            decoded = page.evaluate('''() => {
              const i=document.querySelector('#feishu-oauth-qr img'),c=document.createElement('canvas');
              c.width=i.naturalWidth;c.height=i.naturalHeight;const x=c.getContext('2d');x.drawImage(i,0,0);
              const d=x.getImageData(0,0,c.width,c.height),q=jsQR(d.data,d.width,d.height);
              return {decoded:!!q,host:q?new URL(q.data).hostname:null,width:i.naturalWidth};
            }''')
            assert decoded['decoded'] and decoded['host'] == 'accounts.feishu.cn'
            result['oauth_start'] = decoded
            for width in [1440, 390]:
                page.set_viewport_size({'width': width, 'height': 1000})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                page.locator('#view-settings').screenshot(path=str(args.out / f'feishu-qr-{width}.png'), mask=[page.locator('#feishu-oauth-qr')])
            page.locator('#logout-btn').click()
            assert page.locator('#feishu-oauth-qr img').count() == 0
            result['oauth_cleanup_on_logout'] = True
            result['phone_authorization'] = 'not performed: requires account owner Feishu confirmation'
            result['passed'] = True
        except Exception as error:
            result['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            result['page_errors'] = errors
            (args.out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
            browser.close()
    assert not errors
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
