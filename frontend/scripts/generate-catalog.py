"""Export the team's equipment map and MSDS ingest manifest; no index/key needed."""
import json, shlex, sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
source = json.loads((root / 'rag-service/data/equipment_map.json').read_text())
products = []
for line in (root / 'rag-service/ingest_all.sh').read_text().splitlines():
    if not line.startswith('msds D'):
        continue
    args = shlex.split(line)
    products.append({'product_id': args[3], 'name': args[4], 'title': args[8], 'doc_id': args[2]})
ids = {p['product_id'] for p in products}
assert len(ids) == len(products) and products
assert all(set(e['product_ids']) <= ids for e in source['equipment'])
output = json.dumps({**source, 'products': products}, ensure_ascii=False, indent=2) + '\n'
target = root / 'frontend/src/api/catalog.json'
if '--check' in sys.argv:
    if not target.exists() or target.read_text() != output:
        raise SystemExit('Catalog changed: run frontend/scripts/generate-catalog.py')
else:
    target.write_text(output)
