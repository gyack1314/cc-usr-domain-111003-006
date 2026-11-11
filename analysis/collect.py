# 用浏览器从门户逐份采集：目录浏览、详情页截图、附件与文书下载、摘要一致性校验。
# 下载内容视为不可信数据，仅写入 state/evidence 下的独立目录；本脚本不解释业务效力。
import hashlib, json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
ROOT = Path('/workspace')
DL = ROOT / 'state/evidence/downloads'
ARCH = ROOT / 'state/evidence/archive'
SHOTS = ROOT / 'state/evidence/screenshots'
for d in (DL, ARCH, SHOTS):
    d.mkdir(parents=True, exist_ok=True)

IDS = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'S1', 'CAP1', 'CAP2', 'CAP3', 'CAP4', 'CAP5']

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def main():
    collected = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1280, 'height': 900}, accept_downloads=True)

        # 1) 浏览目录两页（每页五条，共12条），确认门户可检索与分页
        page.goto(BASE + '/', wait_until='domcontentloaded')
        listing_count = page.locator('tr[data-record-id]').count()
        page.goto(BASE + '/?page=2', wait_until='domcontentloaded')
        listing_count += page.locator('tr[data-record-id]').count()
        page.goto(BASE + '/?page=3', wait_until='domcontentloaded')
        listing_count += page.locator('tr[data-record-id]').count()
        assert listing_count == 12, f'目录记录数异常: {listing_count}'

        for rid in IDS:
            # 2) 打开详情页并截图
            page.goto(f'{BASE}/record/{rid}', wait_until='domcontentloaded')
            assert page.get_by_test_id('record-id').inner_text() == rid
            page.screenshot(path=str(SHOTS / f'{rid}.png'), full_page=True)
            reference = page.get_by_test_id('reference').inner_text().strip()
            digest_on_page = page.get_by_test_id('digest').inner_text().strip()
            fields_text = page.get_by_test_id('fields').inner_text()
            assert reference == f'{rid}@{digest_on_page}'

            # 3) 下载原始材料 JSON（附件），带一次重试以隔离偶发竞争
            def grab(link_name, dest: Path):
                with page.expect_download(timeout=15000) as ev:
                    page.get_by_role('link', name=link_name).click()
                ev.value.save_as(str(dest))
            att_path = DL / f'{rid}.json'
            for attempt in (1, 2):
                try:
                    grab('下载原始材料', att_path)
                    break
                except Exception as exc:
                    if attempt == 2:
                        raise
                    print(f'{rid} 附件下载重试({attempt}): {type(exc).__name__}', file=sys.stderr)
                    page.goto(f'{BASE}/record/{rid}', wait_until='domcontentloaded')
                    page.wait_for_timeout(500)
            att_bytes = att_path.read_bytes()
            att_sha = sha256_bytes(att_bytes)
            assert att_sha == digest_on_page, f'{rid} 附件摘要与页面不一致'
            att_json = json.loads(att_bytes.decode('utf-8'))
            assert att_json['id'] == rid

            # 4) 下载文书/扫描副本，带一次重试
            doc_path = None
            for attempt in (1, 2):
                try:
                    with page.expect_download(timeout=15000) as ev2:
                        page.get_by_role('link', name='下载文书或扫描副本').click()
                    doc_name = ev2.value.suggested_filename
                    doc_path = ARCH / doc_name
                    ev2.value.save_as(str(doc_path))
                    break
                except Exception as exc:
                    if attempt == 2:
                        raise
                    print(f'{rid} 文书下载重试({attempt}): {type(exc).__name__}', file=sys.stderr)
                    page.goto(f'{BASE}/record/{rid}', wait_until='domcontentloaded')
                    page.wait_for_timeout(500)
            doc_sha = sha256_bytes(doc_path.read_bytes())

            collected[rid] = {
                'id': rid,
                'title': page.title(),
                'reference': reference,
                'record_sha256': digest_on_page,
                'attachment': str(att_path.relative_to(ROOT)),
                'attachment_sha256': att_sha,
                'document': str(doc_path.relative_to(ROOT)),
                'document_sha256': doc_sha,
                'category': att_json['category'],
                'fields': att_json['fields'],
                'fields_on_page': json.loads(fields_text),
            }
            # 页面展示字段必须与下载附件一致
            assert collected[rid]['fields_on_page'] == att_json['fields'], f'{rid} 页面字段与附件不符'

        # 栏目过滤浏览（能力/说明/暂停/时段各一次），留存检索行为证据
        category_counts = {}
        for cat in ['能力', '说明', '暂停', '时段']:
            page.goto(f'{BASE}/?category={cat}', wait_until='domcontentloaded')
            category_counts[cat] = page.locator('tr[data-record-id]').count()
        browser.close()

    out = {
        'collected_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'portal': BASE,
        'listing_records_seen': listing_count,
        'category_counts': category_counts,
        'records': collected,
    }
    (ROOT / 'state/evidence/collection.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'ok': True, 'records': len(collected), 'category_counts': category_counts},
                     ensure_ascii=False))

if __name__ == '__main__':
    main()
