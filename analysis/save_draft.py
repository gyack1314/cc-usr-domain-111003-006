# 通过浏览器表单在门户保存送校建议草稿（待人工审批，不预约），保存后回读核对序列与测点。
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path('/workspace')
BASE = 'http://127.0.0.1:8765'
collection = json.loads((ROOT / 'state/evidence/collection.json').read_text())
plan = json.loads((ROOT / 'measurement_plan.json').read_text())
DRAFT_KEY = 'calibration-2026-11-sendout'

refs = [collection['records'][rid]['reference']
        for rid in ['L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'S1', 'CAP1', 'CAP2', 'CAP3', 'CAP4', 'CAP5']]
assert len(refs) == 12 and len(set(refs)) == 12

body = f"""【送校建议（待人工审批，未预约）】编制依据 materials/policy.md、downtime.md；业务日期 2026-11-18/19。

一、推荐方案A（不扩窗、不超名额，capacity 校验无超额，费用合计1600元）：
1) 2026-11-18 甲实验室 L1：I2 直流电压 10V/100V（u=0.0015/0.006V，允许0.01V），占甲@18名额；
2) 2026-11-18 丙实验室 L4：I5 压力 0.1/1MPa（u=1kPa=0.001MPa，允许0.002MPa），占丙@18名额；
3) 2026-11-19 甲实验室 L1：I1 直流电压 1V/10V（u=0.00105/0.0015V，允许0.003V），占甲@19名额；
4) 2026-11-19 乙实验室 L3：I3 温度 0/50/100C（u=0.075C，允许0.1C），占乙@19名额。

二、方案取舍：
- 拆分尝试（I1改18日甲）与I2争甲@18唯一名额，capacity返回超额，不可行；
- 乙L2报价更低但为开区间(0,10)V，10V边界不可取且不覆盖I2，拒绝按报价表选机构；
- I3选乙不选甲：甲@19须留给唯一认可实验室为甲的I1，且乙u=0.075C优于甲u=0.09C。

三、最小冲突集合 {{I3,I4}} 争用乙@2026-11-19唯一名额。
请求负责人批准（二选一，均为一次扩窗）：
(a) I4停用窗口扩至18日，启用闲置乙@18名额(CAP5)校-20C（方案B，+500元，capacity无超额）；
(b) I3扩窗至18日走乙@18，乙@19留给I4的-20C。

四、未确认测点（保留开放，不占位、不默认机构能做）：
- I4 120C：乙L3该点落S1暂停[110,150]（2026-11-01生效），甲L5仅[0,100]C，无认可路径；
- I6 10V交流：仅丙L6宣传材料 accredited=false、k=null，无认可范围与置信口径。

五、状态：本草稿仅为建议，门户无预约接口；全部引用附编号@SHA256，复算见 state/evidence/point_evaluation.json。
"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1280, 'height': 1000})
    page.goto(BASE + '/draft/new', wait_until='domcontentloaded')
    page.get_by_label('草稿编号').fill(DRAFT_KEY)
    page.get_by_label('标题', exact=True).fill('2026-11 集中送校分组与实验室日期建议（待审批）')
    page.get_by_label('正文', exact=True).fill(body)
    page.get_by_label('资料引用，每行一项 编号@摘要').fill('\n'.join(refs))
    page.screenshot(path=str(ROOT / 'state/evidence/screenshots/draft-before-save.png'), full_page=True)
    page.get_by_role('button', name='保存预审草稿').click()
    expect(page.get_by_test_id('draft-status')).to_have_text('待人工审批')
    saved_url = page.url
    page.screenshot(path=str(ROOT / 'state/evidence/screenshots/draft-after-save.png'), full_page=True)

    # 重新打开草稿核对：仪器序列 I1..I6 与测点无串换
    page.goto(BASE + '/drafts', wait_until='domcontentloaded')
    expect(page.get_by_role('link', name='2026-11 集中送校分组与实验室日期建议（待审批）')).to_have_count(1)
    page.goto(f'{BASE}/draft/{DRAFT_KEY}', wait_until='domcontentloaded')
    saved_body = page.get_by_label('正文', exact=True).input_value()
    saved_refs = page.get_by_label('资料引用，每行一项 编号@摘要').input_value().splitlines()
    status = page.get_by_test_id('draft-status').inner_text()

    expect_serials = ['I1', 'I2', 'I3', 'I4', 'I5', 'I6']
    missing = [s for s in expect_serials if s not in saved_body]
    assert not missing, f'草稿缺少仪器 {missing}'
    # 测点串换核对：关键绑定关系必须出现在保存后的正文中
    bindings = ['I2 直流电压 10V/100V', 'I5 压力 0.1/1MPa', 'I1 直流电压 1V/10V',
                'I3 温度 0/50/100C', 'I4 120C', 'I6 10V交流']
    bad = [b for b in bindings if b not in saved_body]
    assert not bad, f'测点绑定缺失/串换: {bad}'
    assert saved_refs == refs, '回读引用与提交不一致'
    assert status == '待人工审批'
    print(json.dumps({'draft_key': DRAFT_KEY, 'url': saved_url, 'status': status,
                      'refs': len(saved_refs), 'serial_check': 'pass', 'point_binding_check': 'pass'},
                     ensure_ascii=False))
    browser.close()
