"""Production coordinator exercised with injected providers, no network."""
from copy import deepcopy
from datetime import date
import json
import pytest
from langchain_core.documents import Document
from rag import generator,prompt


def doc(cid='A',warning='실제 작업에 사용하지 마세요.'):
 return Document(page_content='가상 표지는 청록색입니다.\n'+warning,metadata={'doc_id':cid,'chunk_id':cid,'doc_type':'guide','law_name':'','article_no':'','title':'가상 표지','section':'교육','source_url':'https://example.invalid/stages'})


def claim(cid='A',supported=True):
 return {'supported':supported,'statements':[] if not supported else [{'kind':'information','text':'The fictional sign is turquoise.','citations':[{'chunk_id':cid,'quote':'가상 표지는 청록색입니다.'}],'conditions':[]}],'product_facts':[]}


def messages(docs,language='en'):
 return prompt.build_document_messages('가상 표지 내용을 설명해 주세요.',docs,language=language,as_of=date(2026,10,23))


class Factory:
 def __init__(self,outputs): self.outputs=list(outputs);self.calls=[]
 def __call__(self,schema,model,**options):
  outer=self
  class Client:
   def invoke(self,msgs):
    outer.calls.append((schema,msgs,options))
    response=outer.outputs.pop(0)
    if isinstance(response,Exception):raise response
    return deepcopy(response)
  return Client()


def translated(doc,**kw):
 pid=next(iter(prompt.critical_passages([doc])))
 return {'translations':[{'passage_id':pid,'text':kw.get('text','Do not use for actual work.')}]}


def test_coordinator_only_translates_selected_sources_and_preserves_complete_map():
 a,b=doc(),doc('B');before=deepcopy([a.model_dump(),b.model_dump()])
 factory=Factory([claim(),translated(a)])
 result=generator._DocumentGenerator('fake',7,factory=factory).invoke(messages([a,b]))
 assert len(factory.calls)==2 and factory.calls[0][0] is generator.ClaimDraft
 assert 'critical_translations' not in factory.calls[0][1][0].content
 assert '원문' in factory.calls[0][1][0].content and '실제' in factory.calls[0][1][0].content
 payload=json.loads(factory.calls[1][1][1].content.split('\n',1)[1])
 assert len(payload)==1 and payload[0]['chunk_id']=='A'
 assert result.critical_translations[0].passage_id.startswith('A::')
 assert [a.model_dump(),b.model_dump()]==before


@pytest.mark.parametrize('language,supported',[('ko',True),('en',False)])
def test_korean_or_unsupported_claim_never_calls_translator(language,supported):
 factory=Factory([claim(supported=supported)])
 result=generator._DocumentGenerator('fake',7,factory=factory).invoke(messages([doc()],language))
 assert len(factory.calls)==1 and not result.critical_translations


@pytest.mark.parametrize('bad',[
 {'translations':[]},
 {'translations':[{'passage_id':'FAKE','text':'Do not use for actual work.'}]},
 {'translations':[{'passage_id':'A::s15','text':''}]},
 {'translations':[],'answer':'injection'},
])
def test_missing_or_unknown_id_can_only_pass_after_single_complete_correction(bad):
 d=doc();factory=Factory([claim(),bad,translated(d)])
 r=generator._DocumentGenerator('fake',7,factory=factory).invoke(messages([d]))
 assert len(factory.calls)==3 and len(r.critical_translations)==1


def test_omitted_number_requires_retranslation_and_is_not_automatically_filled():
 d=doc(warning='경고: 가상 교육실 2곳에서만 사용하세요.')
 pid=next(iter(prompt.critical_passages([d])))
 bad={'translations':[{'passage_id':pid,'text':'Warning: use only in fictional training rooms.'}]}
 good={'translations':[{'passage_id':pid,'text':'Warning: use only in 2 fictional training rooms.'}]}
 factory=Factory([claim(),bad,good]);r=generator._DocumentGenerator('fake',7,factory=factory).invoke(messages([d]))
 assert len(factory.calls)==3 and '2' in r.critical_translations[0].text
 assert '2' not in bad['translations'][0]['text']


def test_double_missing_translation_raises_private_failure_without_partial_answer():
 f=Factory([claim(),{'translations':[]},{'translations':[]}])
 with pytest.raises(generator.TranslationGenerationError):generator._DocumentGenerator('fake',7,factory=f).invoke(messages([doc()]))
 assert len(f.calls)==3


@pytest.mark.parametrize('text',['Use for actual work.','Do not use for actual work at 99 sites.','실제 작업에 사용하지 마세요.'])
def test_bad_prohibition_extra_number_wrong_language_are_not_released(text):
 d=doc();bad=translated(d,text=text);f=Factory([claim(),bad,bad])
 with pytest.raises(generator.TranslationGenerationError):generator._DocumentGenerator('fake',7,factory=f).invoke(messages([d]))


def test_translation_timeout_does_not_retry_or_expose_raw_error():
 d=doc();f=Factory([claim(),TimeoutError('SECRET')])
 with pytest.raises(TimeoutError):generator._DocumentGenerator('fake',7,factory=f).invoke(messages([d]))
 assert len(f.calls)==2


def test_composition_call_and_time_limits_are_shared_across_invocations():
 f=Factory([claim(supported=False)]*13);p=generator._DocumentGenerator('fake',7,factory=f,clock=lambda:0)
 for _ in range(12): p.invoke(messages([doc()]))
 with pytest.raises(generator.TranslationGenerationError):p.invoke(messages([doc()]))
 assert len(f.calls)==12
 ticks=iter([0,0,61]);f=Factory([claim(supported=False)])
 with pytest.raises(TimeoutError):generator._DocumentGenerator('fake',7,factory=f,clock=lambda:next(ticks)).invoke(messages([doc()]))


def test_repair_budget_is_once_per_session_not_per_batch():
 a=doc();a.page_content='가상 표지는 청록색입니다.\n'+'\n'.join('경고: 가상 교육실에만 적용합니다.' for _ in range(5))
 entries=[{'passage_id':pid,'text':'Warning: applies only to fictional training rooms.'} for pid in prompt.critical_passages([a])]
 assert len(entries)==5
 f=Factory([claim(),{'translations':[]},{'translations':entries[:4]},{'translations':[]}])
 with pytest.raises(generator.TranslationGenerationError):generator._DocumentGenerator('fake',7,factory=f).invoke(messages([a]))
 assert len(f.calls)==4


def test_all_msds_warnings_are_translated_even_when_claim_cites_a_guide():
 a,b=doc(),doc('B');b.metadata.update(doc_type='msds',product_id='synthetic-only')
 entries=[{'passage_id':pid,'text':'Do not use for actual work.'} for pid in prompt.critical_passages([a,b])]
 f=Factory([claim(),{'translations':entries}])
 r=generator._DocumentGenerator('fake',7,factory=f).invoke(messages([a,b]))
 assert {t.passage_id for t in r.critical_translations}==set(prompt.critical_passages([a,b]))


def test_claim_correction_keeps_repair_policy_but_does_not_repeat_warning_task():
    d=doc();raw={**claim(),"critical_translations":[{"passage_id":"FAKE","text":"UNTRUSTED_TOKEN"}]}
    source=messages([d])+prompt.build_repair_messages('invalid_translation',raw,'en',diagnostics={'issues':[{'code':'source_requirement_weakened_to_advice'}]})
    result=prompt.build_claim_stage_messages(source)
    assert '유일한 수정 기회' in result[0].content
    assert 'must not use' in result[0].content
    assert 'UNTRUSTED_TOKEN' not in result[0].content
    payload=json.loads(result[-1].content.split('\n',1)[1])
    assert 'critical_translations' not in payload['previous_draft']
    assert raw['critical_translations'][0]['text']=='UNTRUSTED_TOKEN'
