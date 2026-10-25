"""Observed Vietnamese prohibition must not be classified as an action."""
import pytest
from langchain_core.documents import Document
from rag import prompt,generator


@pytest.mark.parametrize('text',[
 'Không cố gắng trung hòa.', 'Không thử trung hòa.',
 'Không tự ý trung hòa.', 'Không được cố gắng trung hòa.',
])
def test_negative_attempt_is_not_neutralization_instruction(text):
 assert not prompt.hazardous_response_action(text)
 assert not generator._unsafe_critical_translation(text,'중화하려고 하지 마십시오.')
 assert prompt.translation_valid('중화하려고 하지 마십시오.',text,'vi')


@pytest.mark.parametrize('text',[
 'Hãy cố gắng trung hòa.', 'Hãy thử trung hòa.',
 'Không cố gắng trung hòa; hãy trung hòa.',
 'Không cần đeo găng, hãy trung hòa.',
])
def test_attempt_or_unrelated_negation_does_not_hide_positive_action(text):
 assert prompt.hazardous_response_action(text)
 assert generator._unsafe_critical_translation(text,'중화하려고 하지 마십시오.')


def test_requirement_weakening_is_an_explicit_repair_diagnostic():
 quote='금속 용기를 사용하지 말 것.'
 d=Document(page_content=quote,metadata={'law_name':'','article_no':'','doc_type':'guide','chunk_id':'FORCE','source_url':'https://example.invalid/force'})
 draft={'supported':True,'statements':[{'kind':'information','text':'Khuyến cáo không sử dụng bình kim loại.','citations':[{'chunk_id':'FORCE','quote':quote}],'conditions':[]}]}
 feedback=generator._draft_repair_feedback(draft,[d],reason='invalid_translation',language='vi',question='자료 내용은?')
 assert any(issue['code']=='source_requirement_weakened_to_advice' and issue['path']==['statements',0,'text'] for issue in feedback['issues'])


@pytest.mark.parametrize('text',[
 'The document advises against using metal containers.',
 'The document advised using tightly closed containers.',
])
def test_mandatory_source_cannot_be_turned_into_english_advice(monkeypatch,text):
 from test_source_force_and_audience import run
 quote='금속 용기를 사용하지 말 것.' if 'against' in text else '용기를 단단히 잠글 것.'
 result,seen=run(monkeypatch,quote,text,language='en')
 assert result.handoff and result.sources==[] and result.review_reasons==['invalid_translation']
 assert seen==[]
