"""Synthetic proposal tests; no real LLM calls or workplace directions."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest
from langchain_core.documents import Document

from rag import generator as g

SOURCE='가상 교육 구역에서는 표지를 확인한다.'
TEXTS=['가상 자료에서는 표지를 확인해야 합니다.',
       'The document says the sign must be checked.',
       '资料要求必须检查标志。',
       'Tài liệu yêu cầu phải kiểm tra biển báo.',
       'ឯកសារកំណត់ថាត្រូវពិនិត្យស្លាក។']
LEGAL=['법령에 따라 표지를 확인해야 합니다.',
       '산업안전보건법 제114조에 따라 표지를 확인해야 합니다.',
       '시행규칙에 따라 표지를 확인해야 합니다.',
       'The bylaw requires checking the sign.',
       'By law, the sign must be checked.',
       'This is not a legal obligation; the guide says it must be checked.',
       '法律规定必须检查标志。',
       '这不是法定义务，但法律规定必须检查标志。',
       'Theo pháp luật, phải kiểm tra biển báo.',
       'Đây không phải nghĩa vụ pháp lý; phải kiểm tra biển báo.',
       'តាមច្បាប់ ត្រូវពិនិត្យស្លាក។',
       'មិនមែនជាកាតព្វកិច្ចតាមច្បាប់ទេ។']


def fixture(kind='guide',source=SOURCE, text=TEXTS[0], conditions=None):
    doc=Document(page_content=source,metadata={'chunk_id':'A','doc_type':kind,'law_name':'가상법','article_no':'제1조','source_url':'https://example.invalid/synthetic'})
    d=g.EvidenceDraft.model_validate({'supported':True,'statements':[
        {'kind':'legal_obligation','text':text,'citations':[{'chunk_id':'A','quote':source}],
         'conditions':conditions or []}],'critical_translations':[],'product_facts':[]})
    return d,{'A':doc},{'A':g.SourceMetadata.model_validate(doc.metadata)}


def align(d,docs,md):
    before=deepcopy(d.model_dump()); docs_before={k:v.model_dump() for k,v in docs.items()}
    result=g._align_technical_kinds(d,docs,md)
    assert d.model_dump()==before
    assert {k:v.model_dump() for k,v in docs.items()}==docs_before
    changed=result.model_dump();changed['statements'][0]['kind']='legal_obligation'
    assert changed==before # only category can change
    return result.statements[0]


@pytest.mark.parametrize('kind',['guide','msds'])
@pytest.mark.parametrize('text',TEXTS)
def test_category_only_error_can_be_grounded_to_technical_information_in_all_languages(kind,text):
    d,docs,md=fixture(kind,text=text)
    st=align(d,docs,md)
    assert st.kind=='information'
    assert st.text==text and st.citations[0].quote==SOURCE


@pytest.mark.parametrize('text',LEGAL)
def test_explicit_legal_status_and_negative_legal_disclaimers_never_reclassified(text):
    assert g._claims_legal_status(text)
    assert align(*fixture(text=text)).kind=='legal_obligation'


@pytest.mark.parametrize('text',LEGAL)
def test_explicit_legal_status_in_condition_also_blocks_reclassification(text):
    conditions=[{'text':text,'citations':[{'chunk_id':'A','quote':SOURCE}]}]
    assert align(*fixture(conditions=conditions)).kind=='legal_obligation'


@pytest.mark.parametrize('source',[
    '표지를 확인할 것을 권장합니다.','표지 확인은 선택 사항입니다.',
    '표지를 확인하지 않아도 됩니다.','표지 확인은 불필요합니다.',
    '이 안내서는 표지색을 설명합니다.',
])
def test_advisory_optional_or_non_requirement_source_not_reclassified(source):
    assert align(*fixture(source=source)).kind=='legal_obligation'


def test_unknown_and_changed_citations_never_reclassified():
    for change in [{'chunk_id':'UNKNOWN'},{'quote':'실제로 없는 인용.'}]:
        d,docs,md=fixture();d.statements[0].citations[0]=d.statements[0].citations[0].model_copy(update=change)
        assert align(d,docs,md).kind=='legal_obligation'


def test_law_and_web_sources_never_reclassified():
    for kind in ['law','web']:
        assert align(*fixture(kind)).kind=='legal_obligation'


def test_mixed_law_citation_in_statement_or_condition_never_reclassified():
    for in_condition in [False,True]:
        d,docs,md=fixture();law=Document(page_content=SOURCE,metadata={**docs['A'].metadata,'chunk_id':'L','doc_type':'law'})
        docs['L']=law;md['L']=g.SourceMetadata.model_validate(law.metadata)
        cite=g.Citation(chunk_id='L',quote=SOURCE)
        if in_condition:d.statements[0].conditions=[g.EvidenceCondition(text='가상 구역 한정',citations=[cite])]
        else:d.statements[0].citations.append(cite)
        assert align(d,docs,md).kind=='legal_obligation'


def test_missing_condition_citation_never_reclassified():
    condition={'text':'가상 구역 한정','citations':[]}
    assert align(*fixture(conditions=[condition])).kind=='legal_obligation'
