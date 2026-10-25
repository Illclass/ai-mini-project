"""Finite source layouts, not exemptions from citation or safety verification."""
from copy import deepcopy
import pytest
from langchain_core.documents import Document
from rag import prompt


def document(text,section=9,doc_type='msds'):
    return Document(page_content=text,metadata={'chunk_id':'SYNTH-CLOSED','doc_type':doc_type,'msds_section_no':section})


LIMITS=('차. 인화 또는 폭발 범위의 상한/하한\n'
 '인화 또는 폭발 범위의 상한 / : 인화 상한값\n인화 상한값 13 %(V)\n'
 '인화 또는 폭발 범위의 하한 / : 인화 하한값\n인화 하한값 2 %(V)')


@pytest.mark.parametrize('text,section',[
 (LIMITS,9),
 (LIMITS.replace('13 %(V)','13 %(V)\n( 200 °C) ( 1013 hPa)우수실험실운영기준 (GLP): 비해당').replace('2 %(V)','2 %(V)\n( 200 °C) ( 1013 hPa)'),9),
 ('거. n 옥탄올/물 분배계수 : 무기 물질에는 적용되지 않음',9),
 ('다. 생물 농축성\n구성성분:\nSynthetic material:\nn 옥탄올/물 분배계수 : 비고: 무기 물질에는 적용되지 않음',12),
 ('머. 분자량 : 12.34 g/몰\n금속 부식률 : 금속 부식성',9),
 ('특정표적장기 독성 - 반복 노출 : 구분 1 (간, 흉선)\n(경피)\n만성 수생환경 유해성 : 구분 3',2),
])
def test_complete_labelled_fields_are_kept_as_exact_warning_evidence(text,section):
    doc=document(text,section);before=deepcopy(doc.model_dump())
    assert prompt.incomplete_critical_chunks([doc])==set()
    assert list(prompt.critical_passages([doc]).values())==[('SYNTH-CLOSED',text)]
    assert doc.model_dump()==before


@pytest.mark.parametrize('text',[
 LIMITS.replace('13 %(V)',''),LIMITS.replace('2 %(V)','20 %(V)'),
 LIMITS.replace('13 %(V)','130 %(V)'),LIMITS.replace('13 %(V)','13 ppm'),
 LIMITS+'\n환기가 잘 되지 않는 경우',LIMITS+'\n경고: 혼합하지',
 LIMITS.replace('인화 상한값 13','인화 하한값 13'),
 LIMITS.replace('13 %(V)','13 %(V)\n(조건 확인 필요)'),
 '(경피)\n만성 수생환경 유해성 : 구분 3',
 '특정표적장기 독성 - 반복 노출 : 구분 1\n(경피)\n(흡입)',
])
def test_missing_values_reversed_limits_unknown_conditions_and_unbound_routes_stay_blocked(text):
    assert prompt.incomplete_critical_chunks([document(text)])=={'SYNTH-CLOSED'}


def regulatory_table():
    rows=['가. 산업안전보건법에 의한 규제']
    for field in ['제조 등의 금지 유해물질','허가대상 유해물질','노출기준설정 대상 유해인자',
                  '허용기준설정 대상 유해인자','관리대상유해물질','특별관리물질',
                  '작업환경측정 대상 유해인자','특수건강진단 대상 유해인자']:
        rows.extend([field,'해당없음'])
    rows.extend(['공정안전보고서(PSM)제출 대상 유해·위험물질',
        '화학물질명/분류 제조ㆍ취급 규정량 저장 규정량','가상물질(중량 20% 이상) 10,000 kg 20,000 kg',
        '산업안전보건기준에 관한 규칙 별표 1 위험물질의 종류 및 기준량','구분','부식성 물질',
        '산업안전보건기준에 관한 규칙 별표 9 위험물질의 종류 및 기준량','구분 제조ㆍ취급 규정량','부식성 물질 300 킬로그램'])
    return '\n'.join(rows)


def test_complete_regulatory_table_retains_thresholds_and_never_becomes_legal_duty():
    text=regulatory_table();doc=document(text,15)
    assert prompt.incomplete_critical_chunks([doc])==set()
    assert list(prompt.critical_passages([doc]).values())==[('SYNTH-CLOSED',text)]
    assert doc.metadata['doc_type']=='msds'
    assert '중량 20% 이상' in text and '10,000 kg 20,000 kg' in text


@pytest.mark.parametrize('edit',[
 lambda s:s.replace('제조 등의 금지 유해물질\n해당없음\n',''),
 lambda s:s.replace('허가대상 유해물질\n해당없음','허가대상 유해물질'),
 lambda s:s.replace('저장 규정량','저장 정보 미확인'),
 lambda s:s.replace('10,000 kg 20,000 kg','10,000 kg'),
 lambda s:s.replace('부식성 물질 300 킬로그램','부식성 물질'),
 lambda s:s.replace('구분\n부식성 물질','구분'),
 lambda s:s+'\n경고: 다른 물질과 혼합하지',
 lambda s:s+'\n적용 조건: 환기가 되지 않는 경우',
 lambda s:s.replace('부식성 물질 300 킬로그램','알 수 없는 종류 300 킬로그램'),
 lambda s:s.replace('부식성 물질 300 킬로그램','부식성 물질 300'),
])
def test_open_regulatory_fields_unknown_rows_and_dangling_warnings_stay_blocked(edit):
    text=edit(regulatory_table())
    assert not prompt._closed_msds_regulatory_table(text)
    assert prompt.incomplete_critical_chunks([document(text,15)])=={'SYNTH-CLOSED'}


@pytest.mark.parametrize('section,doc_type',[(14,'msds'),(15,'guide'),(15,'law')])
def test_regulatory_layout_requires_actual_msds_section(section,doc_type):
    assert prompt.incomplete_critical_chunks([document(regulatory_table(),section,doc_type)])=={'SYNTH-CLOSED'}


def test_transport_heading_does_not_append_to_previous_flight_ban():
    text=('라. 용기등급 : II\n라벨 : Class 8 - Corrosive substances\n'
          '포장 지침 (화물 수송기) : 855\n포장 지침 (여객기) : 운송금지\nIMDG-코드\n'
          '가. 유엔 번호 : UN 2031')
    doc=document(text,14)
    assert not prompt.incomplete_critical_chunks([doc])
    assert any('포장 지침 (여객기) : 운송금지' in quote for _,quote in prompt.critical_passages([doc]).values())
    cut=document('경고: 혼합하지\nIMDG-코드\n가. 유엔 번호 : UN 2031',14)
    assert prompt.incomplete_critical_chunks([cut])=={'SYNTH-CLOSED'}
