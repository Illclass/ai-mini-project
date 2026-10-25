"""Synthetic physical-page cases. Never reconstruct missing MSDS safety text."""
from pathlib import Path
from unittest.mock import Mock
import pytest
from ingest import ingest_msds


def footer(page, total=2, product='TEST-001'):
    return (f'SIGALD- {product}    쪽 {page} / {total}\n\n'
            'The life science business of Merck operates as MilliporeSigma in\n'
            'the US and Canada\n')


def original():
    return '경고: 다른 물질과 혼합하지\n'+footer(1)+'\f마시오.\n'+footer(2)+'\f'


def test_verified_footer_removal_preserves_all_safety_text_in_order():
    clean = ingest_msds.remove_verified_page_footers(original())
    assert clean == '경고: 다른 물질과 혼합하지\n\n마시오.\n'
    assert '혼합하지' in clean and '마시오.' in clean
    # No inferred words, punctuation or changed values.
    assert clean.replace('\n','') == '경고: 다른 물질과 혼합하지마시오.'


@pytest.mark.parametrize('edit', [
    lambda s:s.replace('쪽 2 / 2','쪽 1 / 2'),
    lambda s:s.replace('쪽 2 / 2','쪽 2 / 3'),
    lambda s:s.replace('쪽 2 / 2','쪽 2 / 1'),
    lambda s:s.replace(footer(2),footer(2,product='OTHER')),
    lambda s:s.replace('the US and Canada\n','the US and\n',1),
    lambda s:s.replace(footer(2),'잘린 꼬리말'),
    lambda s:s.replace('\f','\n'),
    lambda s:s.replace(footer(1),footer(1)+'추가 안전 조건이 있습니다.\n'),
    lambda s:s.replace('SIGALD-', 'UnverifiedBrand-'),
])
def test_unverified_page_structure_is_returned_without_deleting_anything(edit):
    text = edit(original())
    assert ingest_msds.remove_verified_page_footers(text) == text


def test_single_page_or_footer_like_body_text_is_not_exempted():
    for text in ['경고: 혼합하지\n'+footer(1,1), '경고: 혼합하지\n'+footer(1)+'추가 조건']:
        assert ingest_msds.remove_verified_page_footers(text) == text


def test_non_pdf_read_path_keeps_existing_text_contract(monkeypatch):
    reader=Mock(return_value='가상 텍스트 원문\n조건을 보존합니다.')
    monkeypatch.setattr(ingest_msds,'read_input',reader)
    assert ingest_msds.read_msds_input(Path('synthetic.txt')) == reader.return_value
    reader.assert_called_once_with(Path('synthetic.txt'),layout=True)


def test_pdf_reader_keeps_page_breaks_until_verified_cleanup(monkeypatch):
    monkeypatch.setattr(ingest_msds.shutil,'which',lambda name:'/synthetic/pdftotext')
    command=Mock(return_value=Mock(returncode=0,stdout=original()))
    monkeypatch.setattr(ingest_msds.subprocess,'run',command)
    clean=ingest_msds.read_msds_input(Path('synthetic.pdf'))
    assert '혼합하지' in clean and '마시오.' in clean and '쪽 1' not in clean
    assert command.call_args.args[0] == ['pdftotext','-layout','synthetic.pdf','-']


def test_fallback_pdf_reader_uses_layout_without_adding_or_losing_pages(monkeypatch):
    import pypdf
    monkeypatch.setattr(ingest_msds.shutil,'which',lambda name:None)
    pages=[Mock(),Mock()]
    pages[0].extract_text.return_value='경고: 혼합하지\n'+footer(1)
    pages[1].extract_text.return_value='마시오.\n'+footer(2)
    monkeypatch.setattr(pypdf,'PdfReader',Mock(return_value=Mock(pages=pages)))
    text=ingest_msds.read_msds_input(Path('synthetic.pdf'))
    assert '혼합하지' in text and '마시오.' in text and '쪽 1' not in text
    for page in pages:page.extract_text.assert_called_once_with(extraction_mode='layout')
