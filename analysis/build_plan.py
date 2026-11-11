# 汇总交付 measurement_plan.json：所有数值取自 state/evidence 下已复算结果，引用带门户 SHA-256。
import json
from pathlib import Path

ROOT = Path('/workspace')
EVID = ROOT / 'state/evidence'
ev = json.loads((EVID / 'point_evaluation.json').read_text(encoding='utf-8'))
sched = json.loads((EVID / 'scheduling.json').read_text(encoding='utf-8'))
collection = json.loads((EVID / 'collection.json').read_text(encoding='utf-8'))

ref = {rid: entry['reference'] for rid, entry in collection['records'].items()}
inst_eval = {e['serial']: e for e in ev['instruments']}

def point_evidence(serial):
    e = inst_eval[serial]
    rows = []
    for pe in e['point_evaluation']:
        chosen = next((c for c in pe['candidates'] if c['status'] == 'feasible'), None)
        max_u = next((c['max_allowed_u'] for c in pe['candidates'] if c.get('max_allowed_u')), e['max_u'])
        rows.append({
            'point': pe['point'],
            'unit': e['unit'],
            'max_allowed_standard_u': max_u,
            'confirmed': pe['point_confirmed'],
            'chosen_record': chosen['record_id'] if chosen else None,
            'chosen_lab': chosen['lab'] if chosen else None,
            'formula': chosen['formula'] if chosen else None,
            'expanded_U': chosen['expanded_U_at_point'] if chosen else None,
            'k': chosen['k'] if chosen else None,
            'standard_u_cap_unit': chosen['standard_u'] if chosen else None,
            'standard_u_instrument_unit': chosen.get('standard_u_instrument_unit') if chosen else None,
            'recomputed_by_independent_decimal': chosen['recompute_match'] if chosen else None,
            'unconfirmed_reason': None if pe['point_confirmed'] else (
                next((c['reason'] for c in pe['candidates']
                      if c['status'] == 'unconfirmed' and c['record_id'] != 'L6'), None)
                or next((c['reason'] for c in pe['candidates'] if c['record_id'] == 'L6'), None)
                or '门户中无认可路径'),
            'all_candidates': [
                {'record': c['record_id'], 'lab': c['lab'], 'status': c['status'], 'reason': c['reason'],
                 'reference': ref[c['record_id']]}
                for c in pe['candidates']],
        })
    return rows

assignments_a = []
for a in sched['plan_a_baseline']['assignments']:
    assignments_a.append({
        'serial': a['serial'], 'lab': a['lab'], 'date': a['date'],
        'capability_record': a['record_id'], 'reference': ref[a['record_id']],
        'cost': a['cost'], 'occupies_one_shared_slot': f"{a['lab']}@{a['date']}",
        'points_covered_confirmed': [p['point'] for p in point_evidence(a['serial']) if p['confirmed']],
        'points_unconfirmed': [p['point'] for p in point_evidence(a['serial']) if not p['confirmed']],
    })

plan_b = []
for a in sched['plan_b_with_approval']['assignments']:
    plan_b.append({
        'serial': a['serial'], 'lab': a['lab'], 'date': a['date'],
        'capability_record': a['record_id'], 'reference': ref[a['record_id']],
        'cost': a['cost'],
        **({'approval_needed': a['approval_needed']} if 'approval_needed' in a else {}),
    })

plan = {
    'plan_name': '六台仪器集中送校建议（待人工审批，未预约）',
    'generated_business_date_basis': '业务日期依据 materials/policy.md 与 downtime.md；系统当前日期不参与效力判断',
    'policy_rules': [
        '测点误差能力以标准不确定度 u 比较；U 与 k 给定时 u=U/k；a%读数+b 按最坏线性和后再除 k',
        '实验室方法与认可范围须同时匹配；暂停条款优先；闭区间首尾可取，开区间边界不可取',
        '预约名额按 实验室@日期 共用，一台一次占一个名额，分两家占两次；仅建议不预约',
        '置信口径缺失、暂停范围不清或测点超能力时测点留作未确认，不默认机构能做',
    ],
    'source_references': {rid: ref[rid] for rid in sorted(ref)},
    'recommended_plan_A_baseline_no_window_change': {
        'groups': [
            {'group': '2026-11-18 甲组（直流电压 I2）', 'assignments': [a for a in assignments_a if a['date'] == '2026-11-18' and a['lab'] == '甲']},
            {'group': '2026-11-18 丙组（压力 I5）', 'assignments': [a for a in assignments_a if a['date'] == '2026-11-18' and a['lab'] == '丙']},
            {'group': '2026-11-19 甲组（直流电压 I1）', 'assignments': [a for a in assignments_a if a['date'] == '2026-11-19' and a['lab'] == '甲']},
            {'group': '2026-11-19 乙组（温度 I3）', 'assignments': [a for a in assignments_a if a['date'] == '2026-11-19' and a['lab'] == '乙']},
        ],
        'assignments': assignments_a,
        'capacity_check': {'tool': 'workbench.domain.capacity', 'over_limit': sched['plan_a_baseline']['capacity_over'],
                           'slot_limits': sched['slot_limits'],
                           'idle_slots': sched['plan_a_baseline']['idle_slots']},
        'total_estimated_cost': sched['plan_a_baseline']['total_cost'],
        'instruments_not_arranged': [
            {'serial': 'I4', 'reason': '19 日乙唯一名额给 I3；-20 测点虽可由乙 L3 确认但无名额，120 测点无认可路径'},
            {'serial': 'I6', 'reason': '交流电压仅有丙 L6 非认可宣传(accredited=false, k=null)，10V 测点未确认'},
        ],
    },
    'alternative_plan_B_requires_owner_approval': {
        'assignments': plan_b,
        'capacity_over_limit': sched['plan_b_with_approval']['capacity_over'],
        'total_estimated_cost': sched['plan_b_with_approval']['total_cost'],
        'approval_requests': sched['minimal_conflict']['resolution_requests'],
    },
    'tradeoff_studies': {
        'split_attempt_C': sched['plan_c_split_attempt'],
        'cheap_quote_D_rejected': sched['plan_d_cheap_quote_rejected'],
        'I3_lab_choice': {
            'options': [
                {'lab': '乙', 'record': 'L3', 'standard_u_C': '0.075', 'cost': 500, 'slot': '乙@2026-11-19'},
                {'lab': '甲', 'record': 'L5', 'standard_u_C': '0.09', 'cost': 350, 'slot': '甲@2026-11-19'},
            ],
            'decision': '选乙：甲19 名额必须留给唯一认可实验室为甲的 I1；乙 u 更小且费用差异不改变覆盖结论',
        },
    },
    'minimal_conflict_set': sched['minimal_conflict'],
    'unconfirmed_points_kept_open': [
        {'serial': 'I4', 'point': '120', 'unit': 'C',
         'reason': '乙 L3 的 120C 落在 S1 暂停[110,150]（2026-11-01 生效）；甲 L5 量程仅 [0,100]C；无其他认可记录',
         'evidence_refs': [ref['L3'], ref['L5'], ref['S1']]},
        {'serial': 'I6', 'point': '10', 'unit': 'V',
         'reason': '门户无交流电压认可能力记录；丙 L6 accredited=false 且 k=null，置信口径缺失，不能用于客户验收',
         'evidence_refs': [ref['L6']]},
    ],
    'per_point_evidence': {e['serial']: point_evidence(e['serial']) for e in ev['instruments']},
    'booking_status': 'draft_only_no_booking',
    'evidence_artifacts': {
        'collection': 'state/evidence/collection.json',
        'point_evaluation': 'state/evidence/point_evaluation.json',
        'scheduling': 'state/evidence/scheduling.json',
        'journal': 'state/evidence/journal.sqlite3',
        'screenshots': 'state/evidence/screenshots/',
        'downloads': 'state/evidence/downloads/',
        'documents': 'state/evidence/archive/',
        'manifests': 'state/evidence/manifests/',
    },
}
out = ROOT / 'measurement_plan.json'
out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('written', out, 'assignments_A=', len(assignments_a))
