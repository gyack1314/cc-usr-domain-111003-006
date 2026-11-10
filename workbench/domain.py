from decimal import Decimal
def standard_u(U,k):
    if Decimal(str(k))<=0:raise ValueError('覆盖因子必须大于零')
    return str(Decimal(str(U))/Decimal(str(k)))
def cmc(reading,a_percent,b,k):
    return standard_u(abs(Decimal(str(reading)))*Decimal(str(a_percent))/100+Decimal(str(b)),k)
def capacity(assignments,limits):
    counts={}
    for a in assignments:
        key=a['lab']+'@'+a['date'];counts[key]=counts.get(key,0)+1
    return {k:v for k,v in counts.items() if v>limits.get(k,0)}
def merge_ranges(ranges):
    result=[]
    for lo,hi in sorted(ranges):
        if lo>hi:raise ValueError('量程倒置')
        if result and lo<=result[-1][1]:result[-1][1]=max(result[-1][1],hi)
        else:result.append([lo,hi])
    return result
TOOLS={'merge_ranges':merge_ranges,'standard_u':standard_u,'cmc':cmc,'capacity':capacity}
