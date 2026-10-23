"""Export public frontend constants from the team's unchanged Python schema."""
import importlib.util
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('chembridge_schema', root / 'rag-service/rag/schema.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
question = module.RagRequest.model_json_schema()['properties']['question']
contract = {
    'topics': {'chemical': module.TOPIC_CHEMICAL, 'law': module.TOPIC_LAW},
    'languages': list(module.LANGUAGES),
    'question': {'minLength': question['minLength'], 'maxLength': question['maxLength']},
    'requestFields': list(module.RagRequest.model_fields),
    'nullableFields': [name for name, field in module.RagRequest.model_fields.items() if not field.is_required() and field.default is None],
    'responseFields': list(module.RagResponse.model_fields),
    'sourceFields': list(module.Source.model_fields),
}
output = root / 'frontend/src/api/contract.json'
text = json.dumps(contract, ensure_ascii=False, indent=2) + '\n'
if '--check' in sys.argv:
    if not output.exists() or output.read_text() != text:
        raise SystemExit('Frontend contract differs from rag/schema.py. Regenerate it.')
    print('Frontend contract matches rag/schema.py')
else:
    output.write_text(text)
    print('Generated public frontend contract')
