"""Only real same-chunk section headings can support section references."""
from copy import deepcopy
import json
from unittest.mock import Mock
import pytest
from langchain_core.documents import Document
from rag import generator,prompt


@pytest.mark.parametrize('text',['MSDS 7항을 참조합니다.','MSDS의 7번 섹션입니다.','See section 7.','Xem phần 7.','Xem mục 7.','参阅第7节。','សូមមើលផ្នែក 7។'])
def test_explicit_section_number_gets_exact_existing_body_heading(text):
 doc=Document(page_content='7. 취급 및 저장방법\n금속 용기를 사용하지 말 것.',metadata={'chunk_id':'D-s7','doc_type':'msds','msds_section_no':7})
 c=[generator.Citation(chunk_id='D-s7',quote='금속 용기를 사용하지 말 것.')];before=deepcopy(doc.model_dump())
 result=generator._with_section_reference(text,c,{'D-s7':doc})
 assert [v.quote for v in result]==['금속 용기를 사용하지 말 것.','7. 취급 및 저장방법']
 assert c[0].quote=='금속 용기를 사용하지 말 것.' and doc.model_dump()==before


@pytest.mark.parametrize('body,metadata,text',[
 ('금속 용기를 사용하지 말 것.',{'doc_type':'msds','msds_section_no':7},'See section 7.'),
 ('8. 노출방지\n금속 용기를 사용하지 말 것.',{'doc_type':'msds','msds_section_no':8},'See section 7.'),
 ('7. 지침\n금속 용기를 사용하지 말 것.',{'doc_type':'guide','msds_section_no':7},'See section 7.'),
 ('7. 저장\n금속 용기를 사용하지 말 것.',{'doc_type':'msds','msds_section_no':7},'Use for 7 days.'),
 ('7. 저장\n7. 기타\n금속 용기를 사용하지 말 것.',{'doc_type':'msds','msds_section_no':7},'See section 7.'),
])
def test_metadata_wrong_section_ambiguous_heading_or_measurement_never_adds_evidence(body,metadata,text):
 d=Document(page_content=body,metadata={'chunk_id':'X',**metadata});c=[generator.Citation(chunk_id='X',quote='금속 용기를 사용하지 말 것.')]
 assert generator._with_section_reference(text,c,{'X':d})==c


@pytest.mark.claim_verifier
def test_same_displayed_demo_scope_is_independently_verified(monkeypatch):
 d=Document(page_content='작업허가를 확인한다.',metadata={'doc_type':'guide','chunk_id':'DEMO','title':'가상 시연용 지침','law_name':'','article_no':'','source_url':'https://example.invalid/demo'})
 draft={'supported':True,'statements':[{'kind':'information','text':'작업허가를 확인해야 합니다.','citations':[{'chunk_id':'DEMO','quote':d.page_content}],'conditions':[]}]}
 seen=[]
 class Checker:
  def invoke(self,messages):
   payload=json.loads(messages[1].content.split('\n',1)[1]);seen.extend(payload['claims'])
   return {'assessments':[{'claim_id':c['claim_id'],'verdict':'supported'} for c in payload['claims']]}
 monkeypatch.setattr(generator,'build_verification_llm',lambda *a,**kw:Checker())
 client=Mock();client.invoke.return_value=draft
 r=generator.generate_answer('이 자료의 확인 사항은?',[d],structured_llm=client)
 s=next(c for c in seen if c['claim_id']=='s0')
 assert s['text'].startswith('가상 시연 자료에 기재된 정보: ')
 assert s['text'] in r.answer and not r.handoff


@pytest.mark.claim_verifier
def test_demo_attribution_never_launders_an_unsafe_action(monkeypatch):
 action='누출물을 흡수시키시오.'
 d=Document(page_content=action,metadata={'doc_type':'guide','chunk_id':'DEMO','title':'가상 시연용 지침','law_name':'','article_no':'','source_url':'https://example.invalid/demo'})
 draft={'supported':True,'statements':[{'kind':'information','text':action,'citations':[{'chunk_id':'DEMO','quote':action}],'conditions':[]}]}
 factory=Mock();monkeypatch.setattr(generator,'build_verification_llm',factory)
 client=Mock();client.invoke.return_value=draft
 r=generator.generate_answer('이 자료의 확인 사항은?',[d],structured_llm=client)
 assert r.handoff and not r.sources
 factory.assert_not_called()
