"""Synthetic exact-header regression checks; no provider calls."""
from copy import deepcopy
from langchain_core.documents import Document
import pytest
from rag import prompt


@pytest.mark.parametrize('title,substance,section',[
 ('가상 MSDS','가상물질','8. 노출방지 및 개인보호구'),
 ('Synthetic MSDS','가상제품','7. 취급 및 저장방법'),
 ('가상 위험성 MSDS','교육물질','10. 안정성 및 반응성'),
])
def test_exact_ingest_wrapper_is_layout_and_warning_is_unchanged(title,substance,section):
    header=f'[{title} | {substance} | {section}]'
    body='다른 물질과 혼합할 경우 공급자에게 연락하십시오.'
    doc=Document(page_content=header+'\n'+body,metadata={'chunk_id':'SYNTH-HEADER','doc_type':'msds',
        'title':title,'substance':substance,'section':section})
    before=deepcopy(doc.model_dump());passages=prompt.critical_passages([doc])
    assert list(passages.values())==[('SYNTH-HEADER',body)]
    assert all(q in doc.page_content for _,q in passages.values())
    assert doc.model_dump()==before


@pytest.mark.parametrize('warning',[
 '[경고: 실제 작업에 사용하지 마세요.]',
 '[경고 | 다른 물질과 혼합하지 마세요.]',
])
def test_arbitrary_bracket_warning_is_not_a_metadata_header(warning):
    doc=Document(page_content=warning,metadata={'chunk_id':'SYNTH-WARNING','doc_type':'msds',
        'title':'가상 MSDS','substance':'가상물질','section':'8. 노출방지 및 개인보호구'})
    passages,incomplete=prompt._scan_critical_passages([doc])
    assert passages or 'SYNTH-WARNING' in incomplete
