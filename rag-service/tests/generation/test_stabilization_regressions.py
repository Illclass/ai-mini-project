"""Small offline regressions for reproduced integration errors; no provider calls."""
from copy import deepcopy
import json
from unittest.mock import Mock
import pytest
from langchain_core.documents import Document
from rag import generator, chain
from rag.schema import RagRequest, RagResponse, TOPIC_LAW


@pytest.mark.parametrize('text,weakened', [
    ('Protective gloves must be worn. They are not optional.', False),
    ('Protective gloves are NOT OPTIONAL.', False),
    ('Not optional.', False),
    ('Gloves are optional.', True),
    ('Gloves are not not optional.', True),
    ('Gloves are never not optional.', True),
    ('Gloves are not optional; goggles are optional.', True),
    ('Gloves are not optional, but I recommend avoiding them.', True),
    ('Gloves are recommended.', True),
    ('Gloves are not optional; clothing is suggested.', True),
    ('必须佩戴防护手套。', False),
    ('建议佩戴防护手套。', True),
    ('Phải đeo găng tay bảo hộ.', False),
    ('Khuyến nghị đeo găng tay bảo hộ.', True),
    ('보호장갑을 착용해야 합니다.', False),
    ('보호장갑 착용을 권장합니다.', True),
])
def test_requirement_force_negation_is_scoped(text, weakened):
    assert generator._weakens_requirement(text) is weakened


def doc():
    return Document(page_content='이 안내서 표지는 청록색입니다.', metadata={
        'doc_id':'STABLE-GUIDE','doc_type':'guide','chunk_id':'STABLE-GUIDE-1',
        'title':'교육 안내서','section':'표지','source_url':'https://example.invalid/stable',
        'law_name':'','article_no':''})


def draft():
    d=doc()
    return {'supported':True,'statements':[{'kind':'information','text':d.page_content,
        'conditions':[], 'citations':[{'chunk_id':d.metadata['chunk_id'],'quote':d.page_content}]}]}


@pytest.mark.parametrize('case,reason', [('unsupported','no_evidence'),('parse','invalid_output'),
                                        ('verifier','verification_unavailable'),('valid','conditions_unverified')])
def test_chain_retains_private_reasons_without_public_contract_change(monkeypatch,case,reason):
    d=doc();before=deepcopy(d.model_dump())
    provider=Mock();provider.invoke.return_value=(
        {'supported':False,'statements':[]} if case=='unsupported' else
        {'supported':True,'statements':'malformed'} if case=='parse' else draft())
    monkeypatch.setattr(generator,'build_document_llm',lambda *a,**k:provider)
    monkeypatch.setattr(chain,'retrieve',lambda *a,**k:[{'text':d.page_content,'metadata':d.metadata,'score':0.0}])
    if case=='verifier':
        verifier=Mock();verifier.invoke.side_effect=TimeoutError('DO_NOT_EXPOSE')
        monkeypatch.setattr(generator,'build_verification_llm',lambda *a,**k:verifier)
    result=chain.answer(RagRequest(question='교육 안내서 표지 설명',topic=TOPIC_LAW))
    assert isinstance(result,RagResponse) and reason in result.review_reasons
    assert set(result.model_dump())==set(RagResponse.model_fields)
    assert 'review_reasons' not in result.model_dump_json() and 'DO_NOT_EXPOSE' not in result.model_dump_json()
    reasons=result.review_reasons;reasons.append('tamper');assert 'tamper' not in result.review_reasons
    assert d.model_dump()==before


def test_retrieval_empty_is_distinct_from_provider_supported_false(monkeypatch):
    monkeypatch.setattr(chain,'retrieve',lambda *a,**k:[])
    result=chain.answer(RagRequest(question='교육 안내서 표지 설명',topic=TOPIC_LAW))
    assert 'retrieval_empty' in result.review_reasons and result.handoff
    assert not result.sources


def test_provider_timeout_reason_is_sanitized_on_exception(monkeypatch):
    provider=Mock();provider.invoke.side_effect=TimeoutError('DO_NOT_EXPOSE')
    monkeypatch.setattr(generator,'build_document_llm',lambda *a,**k:provider)
    d=doc()
    with pytest.raises(generator.GenerationUnavailable) as error:
        generator.generate('교육 안내서 설명',[{'text':d.page_content,'metadata':d.metadata,'score':0.0}], 'ko', topic=TOPIC_LAW)
    assert error.value.reason=='llm_timeout' and 'DO_NOT_EXPOSE' not in str(error.value)


def test_malformed_hit_stays_fail_closed_and_has_internal_metadata_reason():
    result=generator.generate('교육 안내서 설명',[{'text':'text','metadata':{}}], 'ko', topic=TOPIC_LAW)
    assert result.handoff and not result.sources and result.review_reasons==['invalid_metadata']
    assert set(result.model_dump())==set(RagResponse.model_fields)


@pytest.mark.claim_verifier
@pytest.mark.parametrize('verdict,held',[('supported',False),('contradicted',True)])
def test_not_optional_never_bypasses_independent_semantic_gate(monkeypatch,verdict,held):
    quote='보호장갑을 착용하시오.'
    d=Document(page_content=quote,metadata={'doc_id':'PPE-GUIDE','doc_type':'guide',
        'chunk_id':'PPE-GUIDE-1','title':'보호구 관리 기술지침','section':'보호구',
        'source_url':'https://example.invalid/ppe-guide','law_name':'','article_no':''})
    passage_id=next(iter(generator.prompt.critical_passages([d])))
    response={'supported':True,'statements':[{'kind':'information',
        'text':'Protective gloves must be worn. They are not optional.',
        'citations':[{'chunk_id':'PPE-GUIDE-1','quote':quote}],'conditions':[]}],
        'critical_translations':[{'passage_id':passage_id,'text':'Protective gloves must be worn.'}],
        'product_facts':[]}
    seen=[]
    class V:
        def invoke(self,messages):
            data=json.loads(messages[1].content.split('\n',1)[1]);seen.append(data)
            return {'assessments':[{'claim_id':c['claim_id'],'verdict':verdict} for c in data['claims']]}
    monkeypatch.setattr(generator,'build_verification_llm',lambda *a,**k:V())
    provider=Mock();provider.invoke.side_effect=lambda *a:deepcopy(response)
    r=generator.generate_answer('이 지침의 보호장갑 요구사항을 설명해 주세요.',[d],
        structured_llm=provider,language='en',topic=TOPIC_LAW)
    assert seen and r.handoff is held
    if held:assert r.review_reasons==['claim_mismatch'] and not r.sources
    else:assert 'not optional' in r.answer and r.sources[0].chunk_id=='PPE-GUIDE-1'
