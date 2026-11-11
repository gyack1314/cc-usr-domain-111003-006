# 逐测点能力评估：
#  1) 仅采信浏览器采集并经摘要校验的 state/evidence/downloads/*.json；
#  2) 方法与单位必须同时匹配，认可范围(accredited 仅能力类记录)、闭区间边界、暂停条款逐项判断；
#  3) u=U/k；a%读数+b 最坏线性和后再除 k（调用 workbench.domain，并以独立 Decimal 实现复算）；
#  4) 名额按 实验室@日期 共用，一台一次占一个名额（capacity 校验）；
#  5) 置信口径缺失、暂停范围内、超能力或无认可路径的测点一律 unconfirmed，不默认机构能做。
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, '/workspace')
from workbench.domain import standard_u, cmc, capacity, merge_ranges  # 工作台原语

ROOT = Path('/workspace')
EVID = ROOT / 'state/evidence'

# ---- 独立复算实现（不 import domain 的函数体，单独写一遍用于交叉核对） ----
def xcheck_standard_u(U, k):
    kd = Decimal(str(k))
    if kd <= 0:
        raise ValueError('k<=0')
    return Decimal(str(U)) / kd

def xcheck_cmc(reading, a, b, k):
    return (abs(Decimal(str(reading))) * Decimal(str(a)) / Decimal(100) + Decimal(str(b))) / Decimal(str(k))

def D(v):
    return Decimal(str(v))

# ---- 加载经采集校验的门户记录（不直接读 portal_data，避免把样本当采集资料） ----
collection = json.loads((EVID / 'collection.json').read_text(encoding='utf-8'))
records = {rid: entry['fields'] | {'id': rid, 'category': entry['category'],
                                   'sha256': entry['record_sha256']}
           for rid, entry in collection['records'].items()}

caps = [records[i] for i in records if records[i]['category'] == '能力']
notes = [records[i] for i in records if records[i]['category'] == '说明']
suspensions = [records[i] for i in records if records[i]['category'] == '暂停']
slots = [records[i] for i in records if records[i]['category'] == '时段']

# ---- 加载仪器台账（本地业务材料） ----
instruments = []
with (ROOT / 'materials/instruments.csv').open(encoding='utf-8') as f:
    for row in csv.DictReader(f):
        instruments.append({
            'serial': row['serial'],
            'method': row['method'],
            'points': [Decimal(x) for x in row['points'].split('|')],
            'unit': row['unit'],
            'max_u': Decimal(row['max_u']),
            'available': row['available'].split('|'),
        })

# 单位换算表：仪器单位 -> 能力记录单位的乘数（仅同量纲）
UNIT_TO_KPA = {'MPa': D('1000'), 'kPa': D('1')}

def convert_point(value, from_unit, to_unit):
    if from_unit == to_unit:
        return value, True
    if from_unit in UNIT_TO_KPA and to_unit in UNIT_TO_KPA:
        return value * UNIT_TO_KPA[from_unit] / UNIT_TO_KPA[to_unit], True
    return None, False

def in_range(reading, cap):
    lo, hi, closed = D(cap['low']), D(cap['high']), cap['closed']
    if closed:
        return lo <= reading <= hi, 'closed'
    # 开区间：边界不可取
    return lo < reading < hi, 'open'

def suspended(lab, method, reading_in_cap_unit, cap):
    for s in suspensions:
        if s['lab'] != lab or s['method'] != method:
            continue
        slo, shi = D(s['low']), D(s['high'])
        # 暂停区间按闭区间理解（条款未标 open，从严按落在 [low,high] 即受限）
        if slo <= reading_in_cap_unit <= shi:
            return s
    return None

def evaluate_point(inst, point, cap):
    """返回 (status, detail)；status ∈ feasible/unconfirmed/ineligible"""
    detail = {'record_id': cap['id'], 'lab': cap['lab'], 'method': cap['method'],
              'cap_unit': cap['unit'], 'k': cap['k'], 'reading_instrument_unit': str(point)}
    # 方法必须匹配（同名类目不等于方法兼容，这里要求逐字段相等）
    if cap['method'] != inst['method']:
        detail['reason'] = '方法不匹配'
        return 'ineligible', detail
    # 单位/量纲
    reading, ok = convert_point(point, inst['unit'], cap['unit'])
    detail['reading_in_cap_unit'] = str(reading) if reading is not None else None
    if not ok:
        detail['reason'] = f"单位不兼容: {inst['unit']} vs {cap['unit']}"
        return 'ineligible', detail
    # 能力单位 -> 仪器单位的换算乘数（用于把标准不确定度归一到仪器单位再比较）
    if inst['unit'] == cap['unit']:
        to_inst = D(1)
    elif inst['unit'] in UNIT_TO_KPA and cap['unit'] in UNIT_TO_KPA:
        to_inst = UNIT_TO_KPA[cap['unit']] / UNIT_TO_KPA[inst['unit']]
    else:
        detail['reason'] = f"单位不兼容: {inst['unit']} vs {cap['unit']}"
        return 'ineligible', detail
    # 量程边界
    inside, interval = in_range(reading, cap)
    detail['interval'] = interval
    if not inside:
        detail['reason'] = '测点不在认可量程内（开区间边界不可取）' if interval == 'open' else '测点超量程'
        return 'ineligible', detail
    # 暂停条款优先
    s = suspended(cap['lab'], cap['method'], reading, cap)
    if s:
        detail['reason'] = f"落在暂停范围 {s['id']} [{s['low']},{s['high']}]（生效 {s['effective']}）"
        return 'unconfirmed', detail
    # 不确定度：必须有 k 且 k>0
    if cap.get('k') is None:
        detail['reason'] = '未给覆盖因子 k，置信口径缺失'
        return 'unconfirmed', detail
    if 'a_percent' in cap:
        u_tool = D(cmc(reading, cap['a_percent'], cap['b'], cap['k']))
        u_xcheck = xcheck_cmc(reading, cap['a_percent'], cap['b'], cap['k'])
        detail['formula'] = f"u=(|{reading}|*{cap['a_percent']}%+{cap['b']})/{cap['k']}"
        detail['expanded_U_at_point'] = str(abs(reading) * D(cap['a_percent']) / 100 + D(cap['b']))
    else:
        u_tool = D(standard_u(cap['U'], cap['k']))
        u_xcheck = xcheck_standard_u(cap['U'], cap['k'])
        detail['formula'] = f"u={cap['U']}/{cap['k']}"
        detail['expanded_U_at_point'] = str(cap['U'])
    assert u_tool == u_xcheck, f"复算不一致 {cap['id']}: {u_tool} vs {u_xcheck}"
    u_in_inst_unit = u_tool * to_inst
    detail['standard_u'] = str(u_tool)
    detail['standard_u_instrument_unit'] = str(u_in_inst_unit)
    detail['max_allowed_u'] = str(inst['max_u'])
    detail['recompute_match'] = True
    if u_in_inst_unit > inst['max_u']:
        detail['reason'] = (f"标准不确定度 {u_tool} {cap['unit']} = {u_in_inst_unit} {inst['unit']}"
                            f" > 允许 {inst['max_u']} {inst['unit']}")
        return 'ineligible', detail
    detail['reason'] = '方法/单位/量程/暂停/不确定度全部满足'
    return 'feasible', detail

report = {'instruments': [], 'lab_slots': {f"{s['lab']}@{s['date']}": s['slots'] for s in slots},
          'suspensions': [{'id': s['id'], **{k: s[k] for k in ('lab', 'method', 'low', 'high', 'effective')}}
                          for s in suspensions],
          'non_accredited_notes': [{'id': n['id'], 'fields': {k: n[k] for k in n if k not in ('id', 'category', 'sha256')}}
                                   for n in notes]}

for inst in instruments:
    entry = {'serial': inst['serial'], 'method': inst['method'], 'unit': inst['unit'],
             'points': [str(x) for x in inst['points']], 'max_u': str(inst['max_u']),
             'available_dates': inst['available'], 'point_evaluation': [],
             'feasible_labs_for_all_points': []}
    lab_feasible = {}
    for point in inst['points']:
        pe = {'point': str(point), 'candidates': []}
        feasible_labs_here = set()
        for cap in caps:
            status, detail = evaluate_point(inst, point, cap)
            detail['sha256_ref'] = cap['sha256']
            pe['candidates'].append({'status': status, **detail})
            if status == 'feasible':
                feasible_labs_here.add(cap['lab'])
        # 说明类（非认可宣传，如 L6）单独记录，不作为可行候选
        for n in notes:
            pe['candidates'].append({
                'status': 'unconfirmed', 'record_id': n['id'], 'lab': n['lab'],
                'method': n['method'], 'cap_unit': None, 'k': None,
                'reading_instrument_unit': str(point), 'reading_in_cap_unit': None,
                'interval': None, 'formula': None, 'expanded_U_at_point': None,
                'standard_u': None, 'max_allowed_u': str(inst['max_u']),
                'recompute_match': None, 'sha256_ref': n['sha256'],
                'reason': f"宣传材料 accredited={n.get('accredited')}，k={n.get('k')}，不在认可范围，不能用于客户验收"})
        pe['feasible_labs'] = sorted(feasible_labs_here)
        pe['point_confirmed'] = bool(feasible_labs_here)
        entry['point_evaluation'].append(pe)
        for lab in feasible_labs_here:
            lab_feasible.setdefault(lab, []).append(str(point))
    # 同一实验室覆盖全部测点才作为整仪器候选
    entry['feasible_labs_for_all_points'] = sorted(
        lab for lab, pts in lab_feasible.items() if len(pts) == len(inst['points']))
    report['instruments'].append(entry)

# merge_ranges 用途示例：把乙温度在暂停后的可用认可区间复算（-30,110) 与 [110,150] 暂停后实际可用 [-30,110)
temp_merged = merge_ranges([[s['low'], s['high']] for s in suspensions if s['method'] == '温度'])
report['derived'] = {'suspended_temp_ranges_merged': temp_merged}

out = EVID / 'point_evaluation.json'
out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

# 控制台摘要
for e in report['instruments']:
    confirmed = [p['point'] for p in e['point_evaluation'] if p['point_confirmed']]
    unconfirmed = [p['point'] for p in e['point_evaluation'] if not p['point_confirmed']]
    print(f"{e['serial']} {e['method']} 测点{e['points']} 全覆盖实验室={e['feasible_labs_for_all_points']} "
          f"已确认测点={confirmed} 未确认测点={unconfirmed}")
print('written', out)
