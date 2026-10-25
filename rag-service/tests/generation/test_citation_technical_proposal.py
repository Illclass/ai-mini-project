"""Synthetic local-only tests for proposed Generation changes, no LLM calls."""
import importlib.util
import sys
from pathlib import Path

import pytest
from langchain_core.documents import Document

from rag import generator as g


def draft(quote, cid='A'):
    citation={'chunk_id':cid,'quote':quote}
    return g.EvidenceDraft.model_validate({'supported':True,'statements':[
        {'kind':'information','text':'가상 안내문입니다.','citations':[citation],
         'conditions':[{'text':'가상 조건입니다.','citations':[citation]}]}],
        'product_facts':[{'field':'product_number','value':'DEMO-001','citations':[citation]}]})


def all_quotes(result):
    return [result.statements[0].citations[0],result.statements[0].conditions[0].citations[0],result.product_facts[0].citations[0]]


def test_restore_every_citation_from_unique_whitespace_variant_without_mutation():
    source='문서 시작\n제품 번호 : DEMO-001\n 조건은\n  같아야 한다.\n문서 끝'
    quote='제품 번호 : DEMO-001 조건은 같아야 한다.'
    literal='제품 번호 : DEMO-001\n 조건은\n  같아야 한다.'
    doc=Document(page_content=source);before=doc.model_dump();original=draft(quote);snapshot=original.model_dump()
    result=g._canonicalize_citation_whitespace(original,{'A':doc})
    assert all(c.quote==literal for c in all_quotes(result))
    assert all(g._verify_citations([c],{'A':doc}) for c in all_quotes(result))
    assert original.model_dump()==snapshot and doc.model_dump()==before


@pytest.mark.parametrize('source,quote',[
    ('보관\n 온도 10 °C','보관 온도 20 °C'),
    ('보관\n 온도 10 °C','보관 온도 10 °F'),
    ('농도\n >= 95 %','농도 > 95 %'),
    ('온도\n 10 μg/m3','온도 10 ug/m3'),
    ('사용\n 하지 마시오.','사용 하지마시오.'),
    ('사용하지\n 마시오.','사용 하지 마시오.'),
    ('첫째\n OMIT 둘째','첫째 둘째'),
    ('가\n 나. 가\t나.','가 나.'),
    ('A\n B A\tB A\n B','A B A'),
    ('가\n 나','가\u200b나'),
    ('가\n Ａ','가 A'),
])
def test_never_repair_changed_content_tokens_units_gaps_or_ambiguous_spans(source,quote):
    result=g._canonicalize_citation_whitespace(draft(quote),{'A':Document(page_content=source)})
    assert all(c.quote==quote for c in all_quotes(result))
    assert not g._verify_citations(result.statements[0].citations,{'A':Document(page_content=source)})


def test_unknown_chunk_id_stays_invalid():
    result=g._canonicalize_citation_whitespace(draft('가 나','UNKNOWN'),{'A':Document(page_content='가\n나')})
    assert result.statements[0].citations[0].chunk_id=='UNKNOWN'
    assert not g._verify_citations(result.statements[0].citations,{'A':Document(page_content='가\n나')})


def test_exact_quotes_and_normal_verifier_stay_unchanged():
    original=draft('가\n 나');doc=Document(page_content='가\n 나')
    assert g._canonicalize_citation_whitespace(original,{'A':doc}).model_dump()==original.model_dump()
    assert not g._verify_citations(draft('가 나').statements[0].citations,{'A':doc})


def metadata(kind='guide'):
    return {'A':g.SourceMetadata(law_name='가상 법령',article_no='가상 제1조',source_url='https://example.test/synthetic',doc_type=kind,chunk_id='A')}


@pytest.mark.parametrize('quote',[
    '작업 전 공급라인을 확인한다.', '필요한 경보설비를 설치한다.',
    '구분된 위치에 보관한다.', '단단히 잠글 것', '오염된 옷을 벗을 것.',
    '작업 전 공급라인을 확인\n한다.',
])
@pytest.mark.parametrize('kind',['guide','msds'])
def test_attested_procedural_requirements_keep_force_without_legal_status(quote,kind):
    citation=g.Citation(chunk_id='A',quote=quote);md=metadata(kind)
    assert g._source_technical_requirement(citation,md)
    assert not g._invalid_nonlaw_duty('자료에서는 확인해야 합니다.',[citation],md)
    assert g._invalid_nonlaw_duty('법에 따라 확인해야 합니다.',[citation],md)
    assert not g._supports_legal_duty([citation],md)


@pytest.mark.parametrize('quote',[
    '확인할 것을 권장합니다.', '설치를 권고합니다.', '별도 보관을 추천합니다.',
    '확인하지 않는다.', '설치하지 않는다.', '보관하지 않는다.',
    '잠글 필요는 없다.', '벗을 필요가 없다.', '확인하지 않아도 됩니다.',
    '확인은 선택 사항입니다.', '보관할 것이 좋습니다.',
    '잠글 것을 권장합니다.', '벗을 것을 권고합니다.',
    '반드시 확인할 필요는 없다.',
])
def test_advisory_negated_and_optional_action_never_supports_must(quote):
    c=g.Citation(chunk_id='A',quote=quote)
    assert not g._source_technical_requirement(c,metadata())
    assert g._invalid_nonlaw_duty('반드시 확인해야 합니다.',[c],metadata())


def test_legal_document_does_not_enter_technical_rule():
    assert not g._source_technical_requirement(g.Citation(chunk_id='A',quote='확인한다.'),metadata('law'))
