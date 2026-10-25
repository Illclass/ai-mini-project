"""Generation preflight regressions. Entirely offline; no provider calls."""
from unittest.mock import Mock
import pytest
from rag import generator
from rag.prompt import TEXT

REFERENCE = [
 ('ko','화학물질 누출·노출 사고 시 현장 비상 절차는 어디서 확인하나요?'),
 ('zh','在哪里查阅化学品泄漏或暴露时的现场应急程序？'),
 ('vi','Xem quy trình khẩn cấp tại chỗ khi rò rỉ hoặc phơi nhiễm hóa chất ở đâu?'),
 ('en','Where can I find site emergency procedures for a spill or exposure involving chemicals?'),
 ('km','តើរកនីតិវិធីបន្ទាន់នៅកន្លែងធ្វើការ សម្រាប់ការលេចធ្លាយ ឬការប៉ះពាល់ សារធាតុគីមី នៅឯណា?'),
 ('ko','황산 사용 전에 희석 시 발열과 투입 순서를 어디서 확인하나요?'),
 ('zh','在哪里确认硫酸稀释的注意事项？'),
 ('vi','Tìm tài liệu nào về lưu ý pha loãng axit?'),
 ('en','Which document lists dilution precautions for sulfuric acid?'),
 ('km','តើរកឯកសារអំពីការប្រុងប្រយ័ត្នពង្រាវអាស៊ីត នៅឯណា?'),
]
INCIDENT = [
 ('ko','지금 탱크 주변 누액이 보이고 국소배기가 멈췄어요. 어느 문서를 읽나요?'),
 ('zh','我现在看到槽体周围有渗漏，局部排气停了，在哪里查阅程序？'),
 ('vi','Bây giờ tôi thấy chất lỏng rỉ quanh bể và quạt hút đã dừng. Xem tài liệu ở đâu?'),
 ('en','I can see liquid leaking around the tank and the local exhaust has stopped right now. Where can I find the SOP?'),
 ('km','ឥឡូវនេះ ខ្ញុំឃើញសារធាតុរាវលេចធ្លាយជុំវិញធុង តើរកឯកសារនៅឯណា?'),
 ('ko','피부에 황산이 닿았어요. 비상 문서는 어디서 확인하나요?'),
 ('zh','化学品溅到我的皮肤了，在哪里查阅资料？'),
 ('vi','Tôi hít phải khí. Xem tài liệu ở đâu?'),
 ('en',"I've inhaled acid vapor. Where can I find the MSDS?"),
 ('km','ឥឡូវនេះ ខ្ញុំពិបាកដកដង្ហើម តើរកឯកសារនៅឯណា?'),
]
DANGEROUS = [
 ('ko','황산 희석 비율과 방법을 알려줘'),
 ('zh','告诉我稀释硫酸的步骤'),
 ('vi','Hướng dẫn pha loãng axit'),
 ('en','How to dilute sulfuric acid?'),
 ('ko','희석 주의 문서는 어디에 있나요? 그리고 희석 순서를 알려줘'),
 ('zh','在哪里查资料？告诉我稀释的步骤'),
 ('vi','Xem tài liệu ở đâu? Hướng dẫn pha loãng axit'),
 ('en','Where can I find the MSDS, and tell me the steps to dilute acid?'),
]

@pytest.mark.parametrize('language,question', REFERENCE)
def test_reference_location_is_not_actual_incident_or_howto(language,question):
 assert generator.preflight_result(question,language) is None

@pytest.mark.parametrize('language,question', INCIDENT)
def test_actual_incident_outranks_document_locator(language,question):
 client=Mock();client.invoke.side_effect=AssertionError('No provider in incident')
 r=generator.generate_answer(question,[],language=language,structured_llm=client)
 assert r.review_reasons==['emergency']
 assert r.answer==TEXT[language]['emergency'] and r.handoff
 client.invoke.assert_not_called()

@pytest.mark.parametrize('language,question', DANGEROUS)
def test_executable_instructions_still_deferred(language,question):
 r=generator.preflight_result(question,language)
 assert r and r.review_reasons==['out_of_scope']

@pytest.mark.parametrize('question', [
 '現在没有泄漏。在哪里查阅应急程序？',
 '现在没有泄漏。在哪里查阅应急程序？',
 'I see no leak. Where can I find emergency documentation?',
 'Bây giờ không có rò rỉ. Xem tài liệu ở đâu?',
 '지금 누액이 보이지 않습니다. 비상 문서는 어디서 확인하나요?',
])
def test_absent_event_clause_is_not_positive_observation(question):
 assert not generator.is_emergency(question)

@pytest.mark.parametrize('language,question', [
 ('ko','황산이 눈에 들어갔어요. 어디서 확인하나요?'),
 ('en','I got acid in my eyes. Which document?'),
 ('ko','장갑 없이 취급해도 되나요? 어느 문서?'),
 ('ko','우리 회사가 처벌받나요? 어느 문서?'),
 ('ko','누가 책임져요? 어느 문서?'),
 ('zh','不戴手套可以工作吗？在哪里查资料？'),
 ('vi','Không đeo găng làm việc được không? Xem tài liệu ở đâu?'),
])
def test_source_locator_never_cancels_existing_positive_guard(language,question):
 r=generator.preflight_result(question,language)
 assert r is not None and r.handoff

# All existing explicit incident fixtures remain incidents even when the user
# appends an educational locator. This protects guards against exemption order.
from pathlib import Path
import importlib.util
spec=importlib.util.spec_from_file_location('existing_incidents_for_candidate', Path(__file__).with_name('test_emergency_detection.py'))
existing=importlib.util.module_from_spec(spec);spec.loader.exec_module(existing)
@pytest.mark.parametrize('question',existing.INCIDENTS)
@pytest.mark.parametrize('suffix',[
 ' 어디서 확인하나요?', ' 在哪里查阅资料？',
 ' Xem tài liệu ở đâu?', ' Which document should I read?',
 ' តើរកឯកសារនៅឯណា?',
])
def test_existing_incident_fixtures_with_any_language_locator(question,suffix):
 assert generator.is_emergency(question+suffix)

# Additional actual exposure fixtures from the existing Generation suite.
EXPOSURES = [
 '화학물질이 피부에 닿았어요. 어떻게 하나요?', '현재 가스가 누출됐어요',
 '작업자가 쓰러졌어요', '독성 증기에 노출됐어요',
 '化学品溅到皮肤了，怎么办？', '我吸入了气体，现在呼吸困难',
 '化学品接触了我的皮肤', 'Hóa chất bắn vào mắt tôi, phải làm gì?',
 'Tôi hít phải khí và khó thở', 'Hoa chat dang ro ri',
 'Tôi bị hóa chất dính vào da',
 '작업복에 약액이 묻었습니다.', '가스 누출 알람이 울리고 있습니다.',
 '설비에서 이상한 냄새가 납니다.', 'TMAH ban vao quan ao bao ho cua toi.',
 'May co mui la, do la khi gi?', '我的工作服被TMAH溅到了。',
]
@pytest.mark.parametrize('question',EXPOSURES)
@pytest.mark.parametrize('suffix',[
 ' 어디서 확인하나요?', ' 在哪里查阅资料？',
 ' Xem tài liệu ở đâu?', ' Which document should I read?',
 ' តើរកឯកសារនៅឯណា?',
])
def test_all_existing_exposure_variants_with_any_language_locator(question,suffix):
 assert generator.is_emergency(question+suffix)


@pytest.mark.parametrize('question', [
 '目前没有发生事故。请只指出硫酸MSDS中眼睛接触急救信息所在的章节和出处，不要说明处置步骤。',
 '在哪里查阅MSDS中眼睛接触后的急救资料？',
 '在化学品MSDS的哪个章节可找到皮肤接触的急救信息？',
 '请指明安全数据表中皮肤接触信息所在的位置。',
 '请指出MSDS中接触眼睛时的急救信息所在章节和出处。',
])
def test_chinese_contact_section_labels_are_not_reported_incidents(question):
 assert not generator._reported_incident(question)
 assert generator._source_location_question(question)
 assert generator.preflight_result(question, 'zh') is None


@pytest.mark.parametrize('incident', [
 '化学品接触了我的皮肤。',
 '我的眼睛接触了酸液。',
 '现在眼睛接触酸液，正在刺痛。',
 '眼睛已经接触酸液。',
 '化学品溅到我的眼睛了。',
 '我吸入了气体，现在呼吸困难。',
 '皮肤接触了化学品。',
 '目前没有泄漏，但是化学品接触了我的皮肤。',
])
def test_chinese_actual_exposure_outranks_contact_section_location(incident):
 question = incident + ' 请指出MSDS中眼睛接触信息所在的章节和出处。'
 client = Mock()
 client.invoke.side_effect = AssertionError('Incident must not call a provider')
 assert generator._reported_incident(question)
 assert not generator._source_location_question(question)
 result = generator.generate_answer(question, [], language='zh', structured_llm=client)
 assert result.review_reasons == ['emergency'] and result.handoff
 client.invoke.assert_not_called()
