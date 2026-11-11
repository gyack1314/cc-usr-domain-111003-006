# 排程与名额校验：
#  规则（materials/policy.md + downtime.md）：
#   - 名额按 实验室@日期 共用，一台一次占一个名额，分两家占两次；不超用共享名额；
#   - I2/I5/I6 仅 18 日，I3/I4 仅 19 日，I1 可 18 或 19 日；未经负责人批准不扩大窗口；
#   - 仅制定建议，不实际预约。
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, '/workspace')
from workbench.domain import capacity

ROOT = Path('/workspace')
EVID = ROOT / 'state/evidence'
eval_report = json.loads((EVID / 'point_evaluation.json').read_text(encoding='utf-8'))
collection = json.loads((EVID / 'collection.json').read_text(encoding='utf-8'))

LIMITS = eval_report['lab_slots']  # {"甲@2026-11-18": 1, ...}
COST = {rid: f['fields'].get('cost') for rid, f in collection['records'].items()
        if f['category'] == '能力'}
LAB_BY_RECORD = {rid: f['fields']['lab'] for rid, f in collection['records'].items()
                 if f['category'] == '能力'}

def check(assignments, label):
    over = capacity(assignments, LIMITS)
    print(f'[{label}] 名额校验 capacity() -> {over if over else "无超额"}')
    return over

# 仪器可行实验室（来自逐点评估，必须覆盖全部已确认测点）
feasible = {e['serial']: e['feasible_labs_for_all_points'] for e in eval_report['instruments']}
unconfirmed_points = {e['serial']: [p['point'] for p in e['point_evaluation'] if not p['point_confirmed']]
                      for e in eval_report['instruments']}
print('整仪器全覆盖实验室:', json.dumps(feasible, ensure_ascii=False))
print('未确认测点:', json.dumps(unconfirmed_points, ensure_ascii=False))
print('名额上限:', LIMITS)

# ---------------- 方案 A（基线，不放宽任何停用窗口，不超名额） ----------------
plan_a = [
    {'serial': 'I2', 'lab': '甲', 'date': '2026-11-18', 'record_id': 'L1', 'cost': COST['L1']},
    {'serial': 'I5', 'lab': '丙', 'date': '2026-11-18', 'record_id': 'L4', 'cost': COST['L4']},
    {'serial': 'I1', 'lab': '甲', 'date': '2026-11-19', 'record_id': 'L1', 'cost': COST['L1']},
    {'serial': 'I3', 'lab': '乙', 'date': '2026-11-19', 'record_id': 'L3', 'cost': COST['L3']},
]
over_a = check(plan_a, '方案A 基线')
cost_a = sum(x['cost'] for x in plan_a)

# ---------------- 方案 B（请求批准扩大停用窗口后的集中/再平衡） ----------------
# I4 的 -20 测点仅乙可做且只能 19 日；乙19名额给 I3 后 I4 无处可排。
# 若负责人批准 I4 增加 18 日停用：把 I4 放乙 18（当前闲置），乙19 仍给 I3。
plan_b = plan_a + [
    {'serial': 'I4', 'lab': '乙', 'date': '2026-11-18', 'record_id': 'L3', 'cost': COST['L3'],
     'approval_needed': '设备负责人批准 I4 停用窗口由 19 日扩至 18 日（仅 -20 测点可校，120 仍未确认）'},
]
over_b = check(plan_b, '方案B 扩窗后')
cost_b = sum(x['cost'] for x in plan_b)

# ---------------- 方案 C（拆分对照：I3 改甲19、I1 改甲18 的不可行性验证） ----------------
# I2 锁死甲18（I2 只能18且只有甲能做），甲18 名额=1，I1 无法再进甲18 → 拆分不可行
plan_c_attempt = [
    {'serial': 'I2', 'lab': '甲', 'date': '2026-11-18'},
    {'serial': 'I1', 'lab': '甲', 'date': '2026-11-18'},  # 试图把 I1 拆到18日甲
]
over_c = check(plan_c_attempt, '方案C 拆分尝试(预期超额)')

# ---------------- 方案 D（便宜报价对照：I1 若按乙 L2 宣传最大量程选） ----------------
# L2 是开区间 (0,10)V：I1 的 10V 边界不可取；且 I2 的 10/100V 全部超界 → 不能选
plan_d_note = {
    'claim': '乙 L2 报价 200 元低于甲 L1 的 400 元，且宣传覆盖低压',
    'reject_reasons': [
        'L2 closed=false，量程为开区间 (0,10)V，I1 的 10V 与 I2 的 10V 边界测点按规程不可取',
        'I2 的 100V 超出 L2 上限，乙对 I2 无任何认可测点',
        '即使 I1 的 1V 测点乙可做(u=0.002V)，单台拆两家将占两个名额且 10V 仍须甲，不构成可接受方案'],
}

# ---------------- 最小冲突集合 ----------------
conflict = {
    'contention': '乙@2026-11-19 唯一名额（CAP3, slots=1）',
    'minimal_conflict_set': ['I3', 'I4'],
    'why': 'I3、I4 均只能 19 日停用；19 日乙仅 1 名额。甲19 名额被 I1 占用（I2 锁死甲18，I1 无其他认可实验室）。'
           'I4 在乙仅 -20 测点可确认，120 测点因 S1 暂停且甲 L5 仅到 100C 而无认可路径。',
    'resolution_requests': [
        '请求设备负责人批准 I4 增加 2026-11-18 停用，使用乙18 闲置名额（CAP5）完成 -20 测点（方案B）',
        '或批准 I3 增加 2026-11-18 停用改走乙18，乙19 留给 I4 的 -20 测点（同属一次扩窗请求，成本相同）',
        'I4 的 120C 测点与 I6 的 10V 交流测点本轮无法确认，须另行寻找具备认可资质的实验室，不在本次名额内占位'],
}

out = {
    'slot_limits': LIMITS,
    'plan_a_baseline': {'assignments': plan_a, 'capacity_over': over_a, 'total_cost': cost_a,
                        'booked_slots': sorted(f"{x['lab']}@{x['date']}" for x in plan_a),
                        'idle_slots': sorted(set(LIMITS) - {f"{x['lab']}@{x['date']}" for x in plan_a})},
    'plan_b_with_approval': {'assignments': plan_b, 'capacity_over': over_b, 'total_cost': cost_b},
    'plan_c_split_attempt': {'assignments': plan_c_attempt, 'capacity_over': over_c,
                             'conclusion': '甲18 名额被 I2 独占，I1 拆入必然超额，拆分不可行'},
    'plan_d_cheap_quote_rejected': plan_d_note,
    'minimal_conflict': conflict,
    'unconfirmed': unconfirmed_points,
    'booking_state': '仅建议，未预约（门户无预约接口，草稿保持待人工审批）',
}
(EVID / 'scheduling.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(out, ensure_ascii=False, indent=2))
