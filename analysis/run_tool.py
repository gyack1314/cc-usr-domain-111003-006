import json, sys
sys.path.insert(0, '/workspace')
from workbench.domain import TOOLS
from workbench.evidence import Journal, manifest, verify, atomic_json
from pathlib import Path
cmd = sys.argv[1]
if cmd == 'call':
    tool, infile = sys.argv[2], Path(sys.argv[3])
    payload = json.loads(infile.read_text(encoding='utf-8'))
    print(json.dumps(TOOLS[tool](**payload), ensure_ascii=False, indent=2))
elif cmd == 'manifest':
    root, out = Path(sys.argv[2]), Path(sys.argv[3])
    atomic_json(out, manifest(root)); print('manifest written', out)
elif cmd == 'verify':
    root, mf = Path(sys.argv[2]), Path(sys.argv[3])
    issues = verify(root, json.loads(mf.read_text(encoding='utf-8')))
    print(json.dumps({'mismatch': issues}, ensure_ascii=False)); sys.exit(2 if issues else 0)
elif cmd == 'note':
    db, key, infile = sys.argv[2], sys.argv[3], Path(sys.argv[4])
    seq = Journal(db).append(key, json.loads(infile.read_text(encoding='utf-8')))
    print(json.dumps({'sequence': seq}, ensure_ascii=False))
elif cmd == 'notes':
    print(json.dumps(Journal(sys.argv[2]).read(), ensure_ascii=False, indent=2))
