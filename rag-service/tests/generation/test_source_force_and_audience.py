"""Synthetic offline force/audience regressions, not real LLM quality checks."""
from copy import deepcopy
from datetime import date
import json
from unittest.mock import Mock
import pytest
from langchain_core.documents import Document
from rag import generator
pytestmark = pytest.mark.claim_verifier


def run(monkeypatch, quote, text, *, authoring=False, language='ko', kind='information', verdict='supported'):
    doc = Document(page_content=quote, metadata={
        'law_name':'','article_no':'','doc_type':'guide','chunk_id':'SYNTH-FORCE',
        'source_url':'https://example.invalid/synthetic-force',
        'title':'KOSHA 물질안전보건자료 작성 지침' if authoring else '보호구 관리 기술지침'})
    seen=[]
    class SemanticDouble:
        def invoke(self,messages):
            payload=json.loads(messages[1].content.split('\n',1)[1]);seen.append(payload)
            assert payload['claims'][0]['text']==(text if payload['claims'][0]['claim_id']=='s0' else generator.prompt.render_source_warning(quote,language))
            assert payload['claims'][0]['citations'][0]['quote']==quote
            assert payload['documents'][0]['page_content']==quote
            return {'assessments':[{'claim_id':c['claim_id'],'verdict':verdict} for c in payload['claims']]}
    monkeypatch.setattr(generator,'build_verification_llm',lambda *a,**kw:SemanticDouble())
    output={'supported':True,'statements':[{'kind':kind,'text':text,'citations':[
        {'chunk_id':'SYNTH-FORCE','quote':quote}],'conditions':[]}],
        'critical_translations':[],'product_facts':[]}
    client=Mock();client.invoke.side_effect=lambda messages:deepcopy(output)
    result=generator.generate_answer('이 지침의 해당 항목을 설명해 주세요.',[doc],
        language=language,as_of=date(2026,10,23),structured_llm=client)
    return result,seen


@pytest.mark.parametrize('kind',['information','recommendation','legal_obligation'])
def test_haeya_ham_is_technical_requirement_not_legal_duty(monkeypatch,kind):
    result,seen=run(monkeypatch,'보호복을 착용해야 함.','보호복을 착용해야 합니다.',kind=kind)
    assert seen and not result.handoff
    assert seen[0]['claims'][0]['kind']=='information'
    assert '보호복을 착용해야 합니다.' in result.answer


@pytest.mark.parametrize('source',[
    '보호복을 착용하지 않아도 됨.','보호복 착용은 선택 사항임.',
    '보호복 착용을 권장합니다.','보호복 착용은 불필요합니다.'])
def test_optional_or_advisory_source_cannot_be_strengthened(monkeypatch,source):
    result,seen=run(monkeypatch,source,'보호복을 착용해야 함.')
    assert result.handoff and result.sources==[]
    assert result.review_reasons==['invalid_evidence'] and seen==[]


def test_force_match_does_not_override_changed_ppe_target(monkeypatch):
    result,seen=run(monkeypatch,'보호복을 착용해야 함.','보호장갑을 착용해야 합니다.',verdict='unsupported')
    assert seen and result.handoff and result.sources==[]
    assert result.review_reasons==['claim_mismatch']


@pytest.mark.parametrize('language,text',[
    ('en','The section records the type of personal protective equipment.'),
    ('en','The field records the type of personal protective equipment.'),
    ('en','The item records the type of personal protective equipment.'),
    ('en','The type of personal protective equipment is specified in this document.'),
    ('zh','该项目记录个人防护用品的种类。'),
    ('zh','该条目记录个人防护用品的种类。'),
    ('zh','此处注明个人防护用品的种类。'),
    ('zh','此处记录个人防护用品的种类。'),
    ('vi','Mục này ghi rõ loại phương tiện bảo hộ cá nhân.')])
def test_document_item_description_passes_local_audience_guard(monkeypatch,language,text):
    result,seen=run(monkeypatch,'개인보호구의 종류를 항목에 기재해야 함.',text,authoring=True,language=language)
    assert seen and not result.handoff and text in result.answer
    assert result.sources[0].chunk_id=='SYNTH-FORCE'


@pytest.mark.parametrize('language,text',[
    ('en','The section requires workers at your actual site to use nitrile gloves.'),
    ('zh','该项目要求您实际工作场所的工人使用丁腈手套。'),
    ('vi','Mục này yêu cầu công nhân tại cơ sở thực tế của bạn sử dụng găng tay nitrile.')])
def test_keyword_never_overrides_negative_actual_product_applicability_verdict(monkeypatch,language,text):
    result,seen=run(monkeypatch,'개인보호구의 종류를 항목에 기재해야 함.',text,
        authoring=True,language=language,verdict='unsupported')
    assert seen and result.handoff and result.sources==[]
    assert result.review_reasons==['claim_mismatch'] and text not in result.answer
