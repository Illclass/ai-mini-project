"""Check recommendation addresses against the local index and its read-only exclusion policy.
Run from any directory using the repository .venv; never calls an LLM or rebuilds an index.
"""
import json, pickle, subprocess, sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'rag-service'))
from rag.retriever import drop_truncated
from rag.generator import preflight_result
code="""
import {recommendationEntries,faqRecommendations,lawRecommendations} from './frontend/src/api/recommendations.js';
import {availableEquipment,availableProducts,productsFor} from './frontend/src/api/scope.js';
import contract from './frontend/src/api/contract.json' with {type:'json'};
const contexts=[{},...availableEquipment.map(e=>({equipmentId:e.equipment_id})),...availableProducts.map(p=>({productId:p.product_id})),...availableEquipment.flatMap(e=>productsFor(e.equipment_id).map(p=>({equipmentId:e.equipment_id,productId:p.product_id})))];
console.log(JSON.stringify(contract.languages.flatMap(language=>[...contexts.flatMap(context=>['before','handling','storage','during','after','emergency','free'].flatMap(situation=>recommendationEntries({language,situation,...context}))),...faqRecommendations(language,contract.topics.chemical),...lawRecommendations(language)].map(e=>({...e,language})))));
"""
entries=json.loads(subprocess.check_output(['node','--input-type=module','-e',code],cwd=root,text=True))
docs=[]
for kind in ['law','msds']:
 path=root/f'rag-service/faiss_db/{kind}/index.pkl'
 if not path.exists():raise SystemExit('Local index required; see README for ingestion')
 with path.open('rb')as f:docs+=list(pickle.load(f)[0]._dict.values())
key=lambda s:''.join(s.split())
def matches_address(actual,expected):
 actual,expected=key(actual),key(expected)
 return actual.startswith(expected) and not actual[len(expected):len(expected)+1].isdigit()
errors=[];checked=set()
for entry in entries:
 if preflight_result(entry['q'],entry['language'])is not None:errors.append('Unexpected preflight hold: '+entry['q'])
 for target in entry['targets']:
  address=(target['doc_id'],target['section'])
  if address in checked:continue
  checked.add(address)
  matches=[d for d in docs if d.metadata.get('doc_id')==address[0] and matches_address(d.metadata.get('section',''),address[1])]
  if not matches:errors.append(f'Missing indexed source: {address}')
  elif not drop_truncated([{'text':d.page_content,'metadata':d.metadata,'score':0}for d in matches]):errors.append(f'All matching chunks excluded by retriever: {address}')
if errors:raise SystemExit('\n'.join(errors))
print(f'{len(entries)} questions, {len(checked)} indexed addresses: available; unexpected preflight holds: 0')
