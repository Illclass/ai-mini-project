"""Synthetic mixed warning policy: original spans, no reconstructed advice."""
from copy import deepcopy
from datetime import date
import json
from unittest.mock import Mock
import pytest
from langchain_core.documents import Document
from rag import generator,prompt

pytestmark=pytest.mark.claim_verifier
LOCATOR='이 자료의 관련 항목을 참조합니다.'


def source(value):
 return Document(page_content=LOCATOR+'\n'+value,metadata={
  'law_name':'','article_no':'','doc_type':'guide','chunk_id':'MIXED-SYNTH',
  'title':'안전자료 읽기 안내','section':'6. 누출 사고 시 대처방법',
  'source_url':'https://example.invalid/synthetic-mixed'})


def call(monkeypatch,doc,language='ko',translations=None,verdict='supported'):
 observed=[]
 class Checker:
  def invoke(self,messages):
   data=json.loads(messages[1].content.split('\n',1)[1]);observed.append(data)
   return {'assessments':[{'claim_id':c['claim_id'],'verdict':verdict if c['claim_id'].startswith('t') else 'supported'} for c in data['claims']]}
 monkeypatch.setattr(generator,'build_verification_llm',lambda *a,**kw:Checker())
 draft={'supported':True,'statements':[{'kind':'information',
  'text':LOCATOR if language=='ko' else 'The related section can be consulted in this document.',
  'citations':[{'chunk_id':'MIXED-SYNTH','quote':LOCATOR}],'conditions':[]}],
  'product_facts':[],'critical_translations':translations or []}
 client=Mock();client.invoke.side_effect=lambda messages:deepcopy(draft)
 r=generator.generate_answer('이 자료의 해당 항목을 설명해 주세요.',[doc],
  language=language,structured_llm=client,as_of=date(2026,10,23))
 return r,observed


@pytest.mark.parametrize('mixed',[
 '누출물을 흡수시키고 물과 혼합하지 마십시오.',
 '폭발의 위험이 있으므로 거리를 유지하면서 불을 끄시오.',
 'Do not wait and collect the spilled material.',
])
def test_inseparable_action_with_prohibition_or_hazard_never_silently_succeeds(monkeypatch,mixed):
 doc=source(mixed)
 assert prompt.unresolved_response_warning_chunks([doc])=={'MIXED-SYNTH'}
 r,seen=call(monkeypatch,doc)
 assert r.handoff and r.sources==[]
 assert r.review_reasons==['incomplete_warning_context'] and seen==[]


@pytest.mark.parametrize('safe,action',[
 ('Do not add water','collect the spilled material.'),
 ('물과 혼합하지 마십시오','누출물을 흡수시키시오.'),
 ('Warning: risk of explosion','extinguish the fire.'),
])
def test_semicolon_spans_are_exact_and_protected_warning_survives(monkeypatch,safe,action):
 mixed=safe+'; '+action;doc=source(mixed);before=doc.model_dump()
 warnings=prompt.critical_passages([doc]);references=prompt.reference_only_passages([doc])
 assert list(warnings.values())==[('MIXED-SYNTH',safe)]
 assert list(references.values())==[('MIXED-SYNTH',action)]
 assert all('::p' in pid for pid in warnings)
 assert all(quote in doc.page_content for _,quote in list(warnings.values())+list(references.values()))
 assert not prompt.unresolved_response_warning_chunks([doc])
 r,seen=call(monkeypatch,doc)
 assert not r.handoff and safe in r.answer and action not in r.answer
 assert any(c['text'].endswith(safe) and c['kind']=='source_warning' for call in seen for c in call['claims'])
 assert doc.model_dump()==before


def test_restored_safe_span_requires_translation_and_independent_verdict(monkeypatch):
 doc=source('Do not add water; collect the spilled material.')
 pid=next(iter(prompt.critical_passages([doc])))
 good=[{'passage_id':pid,'text':'Do not add water'}]
 r,seen=call(monkeypatch,doc,language='en',translations=good)
 assert seen and not r.handoff
 assert any(c['kind']=='translation' and c['text'].endswith('Do not add water') for call in seen for c in call['claims'])
 r,seen=call(monkeypatch,doc,language='en',translations=good,verdict='unsupported')
 assert seen and r.handoff and r.review_reasons==['claim_mismatch']
 r,seen=call(monkeypatch,doc,language='en',translations=[])
 assert r.handoff and r.review_reasons==['invalid_translation'] and seen==[]


@pytest.mark.parametrize('action',[
 '경고: 누출물을 흡수시키시오.',
 'Warning: collect the spilled material.',
 '경고: 전문 대응 인력은 드레싱을 올리십시오.',
])
def test_generic_warning_label_does_not_make_every_specialist_reference_unsplittable(action):
 doc=source(action)
 assert prompt.reference_only_passages([doc])
 assert prompt.unresolved_response_warning_chunks([doc])==set()


def test_second_unsafe_semicolon_piece_with_its_own_prohibition_still_defers(monkeypatch):
 doc=source('Do not add water; collect the spilled material but never mix it with acid.')
 assert prompt.unresolved_response_warning_chunks([doc])=={'MIXED-SYNTH'}
 r,seen=call(monkeypatch,doc)
 assert r.handoff and r.review_reasons==['incomplete_warning_context'] and seen==[]
