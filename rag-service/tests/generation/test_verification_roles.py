"""Direct answer relevance and reference warning fidelity are separate gates."""
from copy import deepcopy
import json
from unittest.mock import Mock
import pytest
from langchain_core.documents import Document
from rag import generator,prompt
pytestmark=pytest.mark.claim_verifier


def case():
 d=Document(page_content='가상 표지는 청록색입니다.\n실제 작업에 사용하지 마세요.',metadata={'law_name':'','article_no':'','doc_type':'guide','chunk_id':'ROLES','source_url':'https://example.invalid/roles'})
 draft={'supported':True,'statements':[{'kind':'information','text':'가상 표지는 청록색입니다.','citations':[{'chunk_id':'ROLES','quote':'가상 표지는 청록색입니다.'}],'conditions':[]}]}
 return d,draft


@pytest.mark.parametrize('bad',['negative','missing','duplicate','unknown','timeout'])
def test_warning_gate_failure_with_supported_direct_answer_is_always_withheld(monkeypatch,bad):
 d,draft=case();seen=[]
 class Verifier:
  def invoke(self,messages):
   data=json.loads(messages[1].content.split('\n',1)[1]);seen.append((messages[0].content,data))
   if data['claims'][0]['claim_id'].startswith('t'):
    if bad=='timeout':raise TimeoutError('SECRET')
    items=[{'claim_id':'t0','verdict':'unsupported' if bad=='negative' else 'supported'}]
    if bad=='missing':items=[]
    if bad=='duplicate':items*=2
    if bad=='unknown':items[0]['claim_id']='FAKE'
    return {'assessments':items}
   return {'assessments':[{'claim_id':c['claim_id'],'verdict':'supported'} for c in data['claims']]}
 monkeypatch.setattr(generator,'build_verification_llm',lambda *a,**kw:Verifier())
 client=Mock();client.invoke.side_effect=lambda _:deepcopy(draft)
 result=generator.generate_answer('가상 표지 내용을 설명해 주세요.',[d],structured_llm=client)
 assert result.handoff and not result.sources and 'SECRET' not in result.model_dump_json()
 assert seen[0][1]['claims'][0]['claim_id']=='s0'
 assert seen[1][1]['claims'][0]['claim_id']=='t0'
 assert seen[0][0]!=seen[1][0]


def test_main_rejection_never_calls_warning_gate_or_releases_warning(monkeypatch):
 d,draft=case();seen=[]
 class Verifier:
  def invoke(self,messages):
   data=json.loads(messages[1].content.split('\n',1)[1]);seen.append(data)
   return {'assessments':[{'claim_id':c['claim_id'],'verdict':'contradicted'} for c in data['claims']]}
 monkeypatch.setattr(generator,'build_verification_llm',lambda *a,**kw:Verifier())
 client=Mock();client.invoke.side_effect=lambda _:deepcopy(draft)
 result=generator.generate_answer('가상 표지 내용을 설명해 주세요.',[d],structured_llm=client)
 assert result.handoff and all(c['claim_id']=='s0' for p in seen for c in p['claims'])


def test_framed_warning_is_rendered_exactly_as_independently_checked(monkeypatch):
 d,draft=case();seen=[]
 class Verifier:
  def invoke(self,messages):
   data=json.loads(messages[1].content.split('\n',1)[1]);seen.extend(data['claims'])
   return {'assessments':[{'claim_id':c['claim_id'],'verdict':'supported'} for c in data['claims']]}
 monkeypatch.setattr(generator,'build_verification_llm',lambda *a,**kw:Verifier())
 client=Mock();client.invoke.side_effect=lambda _:deepcopy(draft)
 result=generator.generate_answer('가상 표지 내용을 설명해 주세요.',[d],structured_llm=client)
 assert not result.handoff
 w=next(c for c in seen if c['claim_id']=='t0')
 assert w['text']==prompt.render_source_warning('실제 작업에 사용하지 마세요.','ko')
 assert w['text'] in result.answer
 assert w['citations']==[{'chunk_id':'ROLES','quote':'실제 작업에 사용하지 마세요.'}]
