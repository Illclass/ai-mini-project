"""Synthetic offline tests: identity evidence binding, not real LLM quality."""
from copy import deepcopy

import pytest
from langchain_core.documents import Document
from rag import generator


NAME = '교육액-A'
TOKEN = 'CB_PRODUCT_NAME_1'


def case():
    identity = Document(page_content=f'제품명: {NAME}', metadata={
        'chunk_id': 'M:1', 'doc_type': 'msds', 'product_id': 'training-a'})
    body = Document(page_content='보호복을 착용하십시오.', metadata={
        'chunk_id': 'M:8', 'doc_type': 'msds', 'product_id': 'training-a'})
    draft = generator.EvidenceDraft.model_validate({
        'supported': True,
        'statements': [{'kind': 'information', 'text': f'Wear protective clothing for {TOKEN}.',
            'citations': [{'chunk_id': 'M:8', 'quote': body.page_content}],
            'conditions': [{'text': f'While handling {TOKEN}.',
                'citations': [{'chunk_id': 'M:8', 'quote': body.page_content}]}]}],
        'critical_translations': [],
        'product_facts': [{'field': 'product_name', 'value': NAME,
            'citations': [{'chunk_id': 'M:1', 'quote': identity.page_content}]}]})
    return [identity, body], draft


def test_composes_exact_same_product_identity_for_statement_and_condition():
    docs, draft = case()
    before = deepcopy(draft.model_dump()), deepcopy([d.model_dump() for d in docs])
    result = generator._restore_product_name_tokens(draft, docs)
    assert result is not None
    for claim in [result.statements[0], result.statements[0].conditions[0]]:
        assert NAME in claim.text and TOKEN not in claim.text
        assert [(c.chunk_id, c.quote) for c in claim.citations] == [
            ('M:8', docs[1].page_content), ('M:1', docs[0].page_content)]
    assert before == (draft.model_dump(), [d.model_dump() for d in docs])


@pytest.mark.parametrize('field,value', [
    ('product_id', None), ('product_id', ''), ('product_id', '  '),
    ('product_id', 'different-product'), ('doc_type', 'guide'),
    ('doc_type', 'law'), ('doc_type', 'web')])
def test_never_binds_unscoped_different_or_non_msds_claims(field, value):
    docs, draft = case()
    docs[1].metadata[field] = value
    assert generator._restore_product_name_tokens(draft, docs) is None


@pytest.mark.parametrize('target', ['fact', 'claim', 'condition'])
def test_rejects_forged_exact_quotes_and_missing_chunks(target):
    docs, draft = case()
    claim = {'fact': draft.product_facts[0], 'claim': draft.statements[0],
             'condition': draft.statements[0].conditions[0]}[target]
    claim.citations[0].quote += ' 원문에 없는 문장'
    assert generator._restore_product_name_tokens(draft, docs) is None
    claim.citations[0].chunk_id = 'missing'
    assert generator._restore_product_name_tokens(draft, docs) is None


def test_empty_claim_citations_cannot_become_supported_from_identity_alone():
    docs, draft = case()
    draft.statements[0].citations.clear()
    assert generator._restore_product_name_tokens(draft, docs) is None


@pytest.mark.parametrize('token', ['CB_PRODUCT_NAME_999', 'CB_PRODUCT_NAME_',
                                  'CB_PRODUCT_NAME_1_BAD', 'xCB_PRODUCT_NAME_1'])
def test_unknown_and_malformed_tokens_remain_blocked(token):
    docs, draft = case()
    draft.statements[0].text = token
    assert generator._restore_product_name_tokens(draft, docs) is None


def test_mixed_product_claim_citations_cannot_borrow_verified_identity():
    docs, draft = case()
    other = Document(page_content='혼합 제품의 원문', metadata={
        'chunk_id': 'OTHER:8', 'doc_type': 'msds', 'product_id': 'training-b'})
    docs.append(other)
    draft.statements[0].citations.append(generator.Citation(chunk_id='OTHER:8', quote=other.page_content))
    assert generator._restore_product_name_tokens(draft, docs) is None


def test_does_not_duplicate_existing_identity_evidence():
    docs, draft = case()
    draft.statements[0].citations.append(draft.product_facts[0].citations[0].model_copy())
    draft.statements[0].text += f' {TOKEN}'
    result = generator._restore_product_name_tokens(draft, docs)
    assert len(result.statements[0].citations) == 2


def test_critical_warning_cannot_borrow_identity_from_other_passage():
    docs, draft = case()
    docs[1].page_content = '경고: 보호복을 착용하십시오.'
    for claim in [draft.statements[0], draft.statements[0].conditions[0]]:
        claim.citations[0].quote = docs[1].page_content
    pid = next(pid for pid, (cid, _) in generator.critical_passages(docs).items() if cid == 'M:8')
    draft.critical_translations.append(generator.CriticalTranslation(passage_id=pid,
        text=f'Warning: wear protective clothing for {TOKEN}.'))
    assert generator._restore_product_name_tokens(draft, docs) is None


def test_mixed_product_identity_sources_are_rejected_even_when_name_is_present():
    docs, draft = case()
    duplicate = Document(page_content=docs[0].page_content,
        metadata={'chunk_id': 'B:1', 'doc_type': 'msds', 'product_id': 'training-b'})
    docs.append(duplicate)
    draft.product_facts[0].citations.append(generator.Citation(chunk_id='B:1', quote=duplicate.page_content))
    assert generator._restore_product_name_tokens(draft, docs) is None
