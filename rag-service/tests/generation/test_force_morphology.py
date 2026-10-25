"""Synthetic language forms: no live provider; safety force cannot be weakened."""
import pytest
from rag import generator
from test_source_force_and_audience import run
pytestmark=pytest.mark.claim_verifier

@pytest.mark.parametrize('quote,text',[
 ('흡입하지 마십시오.','흡입하지 않는 것을 권장합니다.'),
 ('흡입하지 마시오.','흡입하지 않는 것을 권장합니다.'),
 ('즉시 의사의 검진을 받을 것.','의사의 검진을 받는 것을 권장합니다.'),
 ('보호복을 입으십시오.','보호복 착용은 선택 사항입니다.'),
 ('보호장갑을 착용한다.','보호장갑 착용을 권장합니다.'),
])
def test_source_imperative_cannot_be_weakened_even_if_verifier_would_approve(monkeypatch,quote,text):
 result,seen=run(monkeypatch,quote,text)
 assert result.handoff and not result.sources and not seen

@pytest.mark.parametrize('text',[
 'Hít phải aerosol có thể gây tổn thương.',
 'Nuốt phải hóa chất có thể gây nguy hiểm.',
 'Chạm phải chất này có thể gây kích ứng.',
 'Gặp phải nguy cơ này cần xác nhận thông tin.',
])
def test_accidental_exposure_compound_is_not_a_duty(text):
 assert not generator._has_duty_assertion(text)

@pytest.mark.parametrize('text',[
 'Hít phải hóa chất; phải liên hệ người phụ trách.',
 'Phải đeo găng tay bảo hộ.',
 'Không phải nghĩa vụ pháp lý; phải đeo găng tay theo tài liệu.',
])
def test_separate_affirmative_requirement_is_preserved(text):
 assert generator._has_duty_assertion(text)
