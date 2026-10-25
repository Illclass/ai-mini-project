"""Synthetic captured-failure shapes; no real chemical instructions are executed.

Provider verdicts are explicit mocks. Original warning text still needs output
scope checking even when it is copied perfectly from the source.
"""
from copy import deepcopy
from datetime import date
import json
from unittest.mock import Mock

from langchain_core.documents import Document
import pytest
from rag import generator,prompt

pytestmark=pytest.mark.claim_verifier
LOCATOR='이 자료의 응급조치 항목에서 관련 정보를 확인할 수 있습니다.'


def document(body,section='4. 응급조치 요령'):
 return Document(page_content=body,metadata={
  'law_name':'','article_no':'','doc_type':'guide','chunk_id':'SYNTH-RESPONSE',
  'source_url':'https://example.invalid/synthetic-response','title':'안전자료 읽기 안내',
  'section':section})


def output(doc,text=LOCATOR,quote=LOCATOR):
 return {'supported':True,'statements':[{'kind':'information','text':text,
  'citations':[{'chunk_id':doc.metadata['chunk_id'],'quote':quote}],'conditions':[]}],
  'critical_translations':[],'product_facts':[]}


def run(monkeypatch,doc,draft,verdict='supported'):
 seen=[]
 class Checker:
  def invoke(self,messages):
   data=json.loads(messages[1].content.split('\n',1)[1]);seen.append(data)
   return {'assessments':[{'claim_id':c['claim_id'],'verdict':verdict if c['claim_id'].startswith('t') else 'supported'} for c in data['claims']]}
 monkeypatch.setattr(generator,'build_verification_llm',lambda *a,**kw:Checker())
 client=Mock();client.invoke.side_effect=lambda messages:deepcopy(draft)
 result=generator.generate_answer('이 자료의 해당 항목을 설명해 주세요.',[doc],
  structured_llm=client,as_of=date(2026,10,23))
 return result,seen


@pytest.mark.parametrize('action',[
 '경고: 글루콘산 칼슘 겔이 없는 경우 용액으로 적신 드레싱을 올리십시오.',
 '경고: 피부에\n겔을 바르십시오.',
 '경고: 화재 시 불을 끄기 위해 소화제를 사용하시오.',
 '경고: 사용 후 개인보호구를 즉시 중화하고 세척해야 합니다.',
 'P390 물질손상을 방지하기 위해 누출물을 흡수시키시오.',
 '경고: 피부에 접촉한 경우 물로 씻으십시오.',
])
def test_source_response_commands_are_reference_only_not_auto_rendered(monkeypatch,action):
 prohibition='중화하지 마십시오.'
 risk='경고: 피부 접촉 시 심한 화상을 일으킬 수 있습니다.'
 doc=document('\n'.join([LOCATOR,action,prohibition,risk]))
 before=doc.model_dump()
 refs=prompt.reference_only_passages([doc]);safe=prompt.critical_passages([doc])
 assert any(action in quote for _,quote in refs.values())
 assert any(prohibition in quote for _,quote in safe.values())
 result,seen=run(monkeypatch,doc,output(doc))
 assert not result.handoff and result.sources
 assert action not in result.answer
 assert prohibition in result.answer and risk in result.answer
 assert any(c['kind']=='source_warning' and c['text'].endswith(prohibition) for call in seen for c in call['claims'])
 assert doc.model_dump()==before


@pytest.mark.parametrize('action',[
 '개인보호구를 즉시 중화해야 합니다.',
 '누출물을 흡수시키시오.',
 '피부에 겔을 문지르십시오.',
 '불을 끄기 위해 거품 소화제를 사용하시오.',
])
def test_generated_response_action_is_blocked_even_with_literal_citation(monkeypatch,action):
 doc=document(action)
 result,seen=run(monkeypatch,doc,output(doc,action,action))
 assert result.handoff and result.sources==[]
 assert result.review_reasons==['invalid_evidence']
 assert action not in result.answer and seen==[]


def test_korean_original_warning_is_independently_verified_and_rejection_fails_closed(monkeypatch):
 warning='경고: 가상 교육실에만 적용합니다.'
 doc=document(LOCATOR+'\n'+warning)
 result,seen=run(monkeypatch,doc,output(doc),verdict='unsupported')
 assert result.handoff and result.sources==[]
 assert seen and any(c['kind']=='source_warning' and c['text'].endswith(warning) for call in seen for c in call['claims'])
 assert result.review_reasons==['claim_mismatch']


@pytest.mark.parametrize('section,number',[
 ('4. 응급조치 요령',4),('5. 폭발·화재시 대처방법',5),('6. 누출 사고 시 대처방법',6),
])
def test_msds_response_section_metadata_constrains_positive_action_without_new_api_fields(section,number):
 doc=document('피부를 물로 씻으십시오.',section)
 doc.metadata.update(doc_type='msds',msds_section_no=number)
 assert prompt.response_reference_only(doc.page_content,doc)
 assert not prompt.response_reference_only('관련 자료는 이 MSDS의 해당 항목에서 확인할 수 있습니다.',doc)
 assert not prompt.response_reference_only('경고: 피부에 심한 화상을 일으킬 수 있습니다.',doc)
 assert not prompt.response_reference_only('피부를 문지르지 마십시오.',doc)


@pytest.mark.parametrize('positive,negative',[
 ('Collect the leaked material.','Do not collect leaked material.'),
 ('Apply calcium gel.','Do not apply calcium gel.'),
 ('Extinguish the fire.','Do not extinguish the fire.'),
 ('收集泄漏的物质。','不要收集泄漏的物质。'),
 ('涂抹凝胶。','不要涂抹凝胶。'),
 ('Dập lửa.','Không dập lửa.'),
 ('Trung hòa găng tay.','Không trung hòa găng tay.'),
 ('ប្រមូលសារធាតុដែលលេចធ្លាយ។','កុំប្រមូលសារធាតុដែលលេចធ្លាយ។'),
 ('ពន្លត់ភ្លើង។','កុំពន្លត់ភ្លើង។'),
])
def test_action_specific_negation_remains_a_safety_warning(positive,negative):
 assert prompt.hazardous_response_action(positive)
 assert not prompt.hazardous_response_action(negative)


def test_reference_notice_has_each_supported_language_and_no_new_response_field():
 notices={language:prompt.TEXT[language]['reference_notice'] for language in prompt.LANGUAGES}
 assert len(set(notices.values()))==len(prompt.LANGUAGES)
 for language,value in notices.items():
  assert isinstance(value,str) and value.strip()
  assert prompt.translation_valid('',value,language)
 assert notices['en'].isascii()
 assert 'Nguồn' in notices['vi']
 assert any('\u1780'<=ch<='\u17ff' for ch in notices['km'])
 assert set(generator.GenerationOutput.model_fields)=={'answer','sources','needs_review','handoff'}


@pytest.mark.parametrize('action',[
 '내용물을 회수하시오.', 'Collect the material.', '收集物质。',
 'Thu gom vật liệu.', 'ប្រមូលសារធាតុ។',
])
def test_response_section_can_supply_context_without_repeated_spill_noun(action):
 doc=document(action,section='6. 누출 사고 시 대처방법')
 assert prompt.response_reference_only(action,doc)
