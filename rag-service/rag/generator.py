"""답변 생성·검증 — 담당: 박진근.

팀 진입점 generate(question, hits, language)는 그대로 유지한다.
문서 직접 입력은 generate_answer, 프롬프트는 prompt.py, 모델 호출은 llm.py가 맡는다.
검색·적재·JWT·라우팅은 수행하지 않는다. 인용 검사는 의미적 정확성을 보증하지 않는다.
"""
from __future__ import annotations

from datetime import date, datetime
import re
import unicodedata
from typing import Any, Literal, Protocol, List
from collections.abc import Mapping
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
import os

import httpx
from langchain_core.documents import Document
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import BaseMessage
from rag import prompt, llm
from rag.llm import call_llm, RAGConfigurationError, validate_timeout as _valid_timeout
from openai import APITimeoutError
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, field_validator, model_validator
from rag.prompt import (
    LANGUAGES, MODES, TEXT, critical_passages, normalized,
    translation_valid, resolve_mode,
)
from rag.schema import DocType, ENV_LLM_MODEL, DOC_TYPE_LAW, DOC_TYPE_MSDS, TOPIC_LAW, Hit, Source, RagResponse

# 요청 범위 검사

def is_emergency(question: str) -> bool:
    text = question.lower()
    compact = re.sub(r"\s+", "", text)
    ko = r"눈에(?:들어|튄|튀었)|피부에(?:닿|묻|튀)|흡입했|들이마셨|삼켰|쓰러|의식이없|의식을잃|숨을못|호흡곤란|노출(?:됐|되었)|누출(?:됐|되었|중|사고)|새고있|불이났|화재가|폭발했|화상을입|(?:긴급|응급|비상)(?:상황|사고|노출)"
    zh = r"溅[到入进].{0,8}(?:眼|皮肤)|(?:眼睛|皮肤).{0,8}(?:溅|接触)|接触.{0,8}(?:皮肤|眼)|吸入了|误吸|误服|吞下|昏倒|失去意识|无法呼吸|呼吸困难|正在泄漏|泄漏了|发生泄漏|发生火灾|起火了|紧急|(?:化学品|气体)泄漏"
    vi = r"(?:ban|dinh|vang).{0,15}(?:vao|len).{0,4}(?:mat|da)|hit phai|nuot phai|bat tinh|kho tho|bi phoi nhiem|dang ro ri|bi ro ri|hoa hoan|khan cap|bi bong"
    en = r"(?:chemical|gas|acid).{0,30}(?:leak|spill)|(?:splashed|got).{0,15}(?:eyes|skin)|inhaled|swallowed|unconscious|cannot breathe"
    # 기존 노출·누출 규칙을 유지하고, 장비 작업 중 보고되는 신호를 추가한다.
    # 단순히 "작업복", "경보", "냄새"가 있다는 이유만으로 비상 처리하지 않는다.
    ko_incident = (
        r"(?:작업복|보호복|의복|옷)(?:에|으로).{0,12}(?:튀었|튄|묻었|묻어있|젖었)"
        r"|(?:가스|누출|유출).{0,12}(?:경보|알람).{0,12}(?:발생했|울렸|울리고|작동중)"
        r"|(?:이상한|수상한|평소와다른|알수없는).{0,6}냄새(?:가|는)?.{0,6}"
        r"(?:나는데|납니다|나요|나고있|나기시작)"
    )
    zh_incident = (
        r"(?:溅到|溅上|沾到).{0,12}(?:工作服|衣服|防护服)"
        r"|(?:工作服|衣服|防护服).{0,15}(?:溅到|沾到|沾上)"
        r"|(?:泄漏|漏气|气体).{0,12}(?:报警|警报).{0,8}(?:响了|正在响|触发了)"
        r"|(?:设备|机器|现场).{0,8}(?<!没)有.{0,6}(?:异味|不明气味)"
    )
    vi_incident = (
        r"(?:ban|dinh|vang).{0,15}(?:vao|len).{0,4}(?:quan ao|ao bao ho|do bao ho)"
        r".{0,20}(?:cua toi|roi)"
        r"|(?:chuong|bao dong|canh bao).{0,30}(?:ro ri|khi).{0,30}"
        r"(?:dang keu|da keu|vang len|dang bao)"
        r"|(?<!khong )co mui (?:la|bat thuong|khong ro)"
    )
    # 부정 표현 전체를 제거하지 않는다. 같은 질문에 실제 사고가 함께 있을 수 있다.
    # 어휘 규칙이므로 모든 표현이나 문맥을 이해하는 분류기는 아니다.
    return bool(
        re.search(ko, compact) or re.search(ko_incident, compact)
        or re.search(zh, text) or re.search(zh_incident, text)
        or re.search(vi, normalized(text)) or re.search(vi_incident, normalized(text))
        or re.search(en, text)
    )

def is_prohibited_request(question: str) -> bool:
    compact = re.sub(r"\s+", "", question.lower())
    text = normalized(question)
    ko = r"(?:우리|저희|회사|대표|내가|제가|당사|이사고).{0,35}(?:법적책임|유죄|무죄|처벌받|책임져|책임을져)|무조건처벌|(?:법적|형사|민사)책임.{0,8}(?:판단|확정|결정)|누가.{0,10}책임|(?:작업|가동|진입|재가동).{0,20}(?:승인해|허가해|해도돼|해도되|안전한지판단)|(?:중화|희석|혼합|누출차단).{0,20}(?:방법|순서|절차|비율|해줘|알려)|(?:보호구|장갑).{0,8}없이.{0,15}(?:작업|취급)|(?:불산|황산|화학물질).{0,20}(?:섞는법|처리순서)"
    zh = r"(?:法律责任|刑事责任|民事责任).{0,12}(?:判断|确定|谁|承担)|(?:我们|公司|我).{0,20}(?:有罪|无罪|处罚|负责|承担法律责任)|(?:批准|允许).{0,12}(?:作业|工作|开机)|可以.{0,12}(?:开工|进入|重启)|(?:中和|稀释|混合).{0,15}(?:步骤|比例|方法)|不戴.{0,10}(?:手套|防护)"
    vi = r"(?:toi|cong ty|chung toi).{0,30}(?:chiu trach nhiem|bi phat|co toi)|(?:phe duyet|cho phep).{0,20}(?:lam viec|van hanh)|(?:cach|huong dan|ty le).{0,20}(?:trung hoa|pha loang|tron axit)|khong deo.{0,15}(?:gang|bao ho)"
    en = r"(?:am i|are we|is our|who is).{0,35}(?:liable|guilty|legally responsible)|(?:approve|authorize|safe to).{0,35}(?:work|enter|operate|restart)|(?:how to|steps to|ratio).{0,20}(?:neutralize|dilute|mix acid)"
    return bool(re.search(ko, compact) or re.search(zh, question) or re.search(vi, text) or re.search(en, text))

def product_question(question: str) -> bool:
    """Product-specific safety requests; general SDS access/education is allowed."""
    text = normalized(question)
    return bool(re.search(r"불산|황산|염산|암모니아|이\s*제품|이\s*물질|氢氟酸|硫酸|盐酸|这个产品|这种化学品|axit|san pham nay|hoa chat nay|hydrofluoric|sulfuric", text))


# 근거·출처 데이터와 검증

class SourceMetadata(BaseModel):
    """Team metadata; never synthesize missing fields from model output.

    Non-law documents may use empty law_name/article_no when inapplicable.
    Extra metadata keys are excluded from sources; absent optional fields are None.
    """
    model_config = ConfigDict(extra="ignore", strict=True)
    law_name: str = ""
    article_no: str = ""
    source_url: str
    doc_type: DocType
    chunk_id: str = Field(min_length=1)
    article_title: str | None = None
    effective_date: str | None = None
    paragraph: str | None = None
    doc_id: str | None = None
    title: str | None = None
    section: str | None = None
    topic: str | None = None
    product_id: str | None = None
    substance: str | None = None
    cas_no: str | None = None
    supplier: str | None = None
    msds_section_no: int | None = None

    @model_validator(mode="before")
    @classmethod
    def legacy_or_team_metadata(cls, data):
        # Team schema makes law-specific names inapplicable to MSDS. Legacy
        # callers still need their original required keys, not invented values.
        if isinstance(data, dict) and not all(isinstance(data.get(k), str) and data[k].strip() for k in ("doc_id", "title", "section")):
            if "law_name" not in data or "article_no" not in data:
                raise ValueError("legacy metadata requires law_name and article_no")
        return data

    @field_validator("source_url")
    @classmethod
    def valid_source_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("source_url must be an original http(s) URL without credentials")
        return value

    @field_validator("chunk_id")
    @classmethod
    def nonblank_chunk_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("chunk_id cannot be blank")
        return value

    @model_validator(mode="after")
    def law_fields(self):
        if self.doc_type == DOC_TYPE_LAW and (not self.law_name.strip() or not self.article_no.strip()):
            raise ValueError("law documents require law_name and article_no")
        return self

class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    chunk_id: str
    quote: str


NO_EVIDENCE_MESSAGE = "제공된 자료에서 질문에 답할 충분한 근거를 확인하지 못했습니다."
OUT_OF_SCOPE_MESSAGE = (
    "이 서비스는 자료에 근거한 일반 정보만 안내합니다. 법적 책임 판단, "
    "실제 화학사고의 대응 지시, 작업 안전 승인 요청에는 답변하지 않습니다. "
    "현장 담당자 또는 해당 분야의 자격을 갖춘 전문가에게 확인해 주세요."
)


def _is_out_of_scope(question: str) -> bool:
    """Reject explicit decisions/emergency instructions before provider calls.

    This small lexical guard is intentionally not a safety classifier. The LLM
    receives the same scope restriction for requests this guard does not catch.
    """
    text = re.sub(r"\s+", " ", question.strip().lower())
    compact = re.sub(r"\s+", "", text)
    approval = bool(
        re.search(r"(?:작업|가동|재가동|입장|진입).{0,20}(?:승인(?:을)?해|허가(?:를)?해|해도돼|해도되|해도될|안전하다고|안전한지판단)", compact)
        or re.search(r"(?:승인|허가)(?:을|를)?(?:해줘|해주세요|해주십시오|해줄래|해주시겠|요청합니다|바랍니다).{0,12}(?:작업|가동)", compact)
        or re.search(r"(?:approve|authorize|safe to).{0,35}(?:work|enter|operate|restart)", text)
    )
    responsibility = bool(
        re.search(r"(?:우리|저희|내가|제가|당사|대표|관리자|이사고|이번사고).{0,35}(?:책임|유죄|무죄|위법|처벌).{0,20}(?:판단|결정|인가|있나|있어|있을|받나|받을|해줘|입니까|져야하|지나요|집니까|지는지)", compact)
        or re.search(r"(?:누가|누구).{0,12}(?:법적|형사|민사)?책임", compact)
        or re.search(r"(?:법적|형사|민사)책임(?:을)?(?:판단|결정)해", compact)
        or re.search(r"(?:am i|are we|is our|who is).{0,35}(?:liable|guilty|legally responsible)", text)
    )
    incident = bool(
        re.search(r"(?:지금|방금|현재|현장에서|실제로).{0,40}(?:누출|유출|화학사고|가스|화학물질|염산|불산|황산|암모니아|염소).{0,50}(?:어떻게|대응|조치|중화|처리|막|멈추|들어가|행동)", compact)
        or (
            re.search(r"(?:가스|화학|염산|불산|황산|암모니아|염소)", compact)
            and re.search(r"(?:누출됐|누출되었|누출중|새고있|유출됐|사고가났)", compact)
            and re.search(r"(?:어떻게|대응|조치|중화|처리|막|멈추|들어가|행동)", compact)
        )
        or re.search(r"(?:chemical|gas|acid|ammonia|chlorine).{0,30}(?:leak|spill).{0,50}(?:right now|what should|how do|how to)", text)
    )
    if approval or responsibility or incident:
        return True
    return False

class EvidenceCondition(BaseModel):
    """An applicability condition supported by exact source quotes."""
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str
    citations: list[Citation]


class EvidenceStatement(BaseModel):
    """One claim, its type, its sources, and any evidenced conditions."""
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["legal_obligation", "recommendation", "information"]
    text: str
    citations: list[Citation]
    conditions: list[EvidenceCondition]


class EvidenceDraft(BaseModel):
    """LLM output; never includes source metadata, review flags, or handoff."""
    model_config = ConfigDict(extra="forbid", strict=True)
    supported: bool
    statements: list[EvidenceStatement]
    critical_translations: list["CriticalTranslation"] = Field(default_factory=list, description="Translate only exact IDs in CRITICAL_PASSAGES_JSON. Return [] if that map is empty; never use a chunk_id as a passage_id.")
    product_facts: list["ProductFact"] = Field(default_factory=list, description="For MSDS, extract ALL FOUR available identity fields regardless of what the user asked: product_name, product_number, concentration, revision_date. Quote only page_content. For non-MSDS return [].")


class ClaimAssessment(BaseModel):
    """Internal verifier result; never exposed as new API response fields."""
    model_config = ConfigDict(extra="forbid", strict=True)
    claim_id: str
    verdict: Literal["supported", "unsupported", "contradicted"]


class EvidenceVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    assessments: list[ClaimAssessment]


class CriticalTranslation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    passage_id: str
    text: str


class ProductFact(BaseModel):
    """Internal extraction with verbatim evidence, not new metadata/API keys."""
    model_config = ConfigDict(extra="forbid", strict=True)
    field: Literal["product_name", "product_number", "concentration", "revision_date"]
    value: str
    citations: list[Citation]


EvidenceDraft.model_rebuild()



class GenerationOutput(BaseModel):
    """Generation-only result; review diagnostics are private, not API fields."""
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str
    sources: list[SourceMetadata]
    needs_review: bool
    handoff: bool
    _review_reasons: list[str] = PrivateAttr(default_factory=list)
    _review_message: str = PrivateAttr(default="")

    @property
    def review_reasons(self) -> list[str]:
        """Copy of internal diagnostics for logging/HTTP mapping after agreement."""
        return list(self._review_reasons)

    @property
    def review_message(self) -> str:
        return self._review_message


class DocumentStructuredLLM(Protocol):
    def invoke(self, messages: list[BaseMessage]) -> EvidenceDraft | dict[str, Any]: ...




_REVIEW_MESSAGES = {
    "no_evidence": "질문에 답할 자료 근거를 확보한 뒤 다시 검토해야 합니다.",
    "invalid_evidence": "인용 또는 의무 구분을 검증하지 못해 답변을 보류했습니다.",
    "claim_mismatch": "답변의 주장과 원문 근거가 일치하지 않아 답변을 보류했습니다.",
    "verification_unavailable": "주장별 근거 검증을 완료하지 못해 답변을 보류했습니다.",
    "invalid_output": "LLM 응답 형식을 검증하지 못해 답변을 보류했습니다.",
    "invalid_metadata": "검색 문서의 팀 메타데이터 또는 chunk_id 중복을 확인해야 합니다.",
    "out_of_scope": "담당자 검토가 필요한 범위 밖 요청입니다. 자동 판단이나 승인을 수행하지 않습니다.",
    "llm_timeout": "LLM 호출 시간이 초과되었습니다. 재시도 여부를 확인해야 합니다.",
    "llm_error": "LLM 제공자 호출에 실패했습니다. 제공자 상태와 설정을 확인해야 합니다.",
    "configuration_error": "LLM 키 또는 모델 설정을 확인해야 합니다.",
    "conditions_unverified": "자료에서 확인되지 않은 적용 조건은 담당자 검토가 필요합니다.",
    "law_currentness_unverified": "법령의 현행성과 해당 현장의 적용 여부는 공식 원문 대조가 필요합니다.",
    "effective_date_missing": "법령 자료의 시행일을 확인하지 못했습니다.",
    "effective_date_invalid": "법령 자료의 시행일 형식을 확인하지 못했습니다.",
    "effective_date_future": "기준일보다 미래 시행일인 자료가 있어 현재 의무로 판단하지 않습니다.",
    "law_version_conflict": "같은 법령 조문의 서로 다른 시행일 자료가 있어 적용 버전을 확인해야 합니다.",
    "emergency": "검색·LLM을 기다리지 않고 현장 비상절차와 긴급 신고를 우선해야 합니다.",
    "product_unverified": "제품명·제품번호·농도·개정일 또는 현장 제품 일치 여부가 미확인입니다.",
    "invalid_translation": "경고·조건·수치의 번역을 확인해야 합니다.",
    "incomplete_warning_context": "검색 문서의 경고·조건이 잘려 전체 문맥을 확인해야 합니다.",
    "msds_applicability_unverified": "MSDS 제품·농도·개정본과 실제 현장 제품의 일치를 별도로 확인해야 합니다.",
    "precheck_requires_review": "작업 전 정보 확인은 현장 승인 또는 완료된 안전 점검이 아닙니다.",
}


def _review_result(reason: str, answer: str | None = None, *, language: str = "ko") -> GenerationOutput:
    result = GenerationOutput(
        answer=answer or TEXT[language].get(reason, TEXT[language]["fallback"]), sources=[],
        needs_review=True, handoff=True,
    )
    result._review_reasons = [reason]
    result._review_message = _REVIEW_MESSAGES[reason]
    return result




def build_document_llm(model: str = "gpt-4o", *, timeout_seconds: float = 30.0) -> DocumentStructuredLLM:
    """생성 출력 규격을 llm.py의 공급자 팩토리에 전달한다."""
    return llm.build_structured_llm(EvidenceDraft, model, timeout_seconds=timeout_seconds)


def build_verification_llm(model: str = "gpt-4o", *, timeout_seconds: float = 30.0):
    """Use a separate structured call; the generator cannot approve its own draft."""
    return llm.build_structured_llm(EvidenceVerification, model, timeout_seconds=timeout_seconds)


def build_document_messages(
    question: str, documents: list[Document], *, as_of: date,
    language: str = "ko", mode: str = "qa", product_id: str | None = None,
) -> list[BaseMessage]:
    """Compatibility entry point; prompt.py owns all prompt text and assembly."""
    return prompt.build_document_messages(
        question, documents, as_of=as_of, language=language, mode=mode, product_id=product_id,
    )


def _unsafe_text(text: str) -> bool:
    """Reject overt fabrications; semantic support still needs evaluation."""
    return not text.strip() or bool(re.search(
        r"https?://|www\.|현행\s*(?:법령|법률|법|규정)(?:에\s*따르면|입니다|상|으로)|"
        r"현재\s*시행\s*중(?:인|입니다)|under\s+(?:the\s+)?current\s+law|"
        r"current\s+law\s+requires|is\s+currently\s+in\s+force|"
        r"폐지(?:되었습니다|됐습니다|되어|되었으므로|된\s*법령입니다)|"
        r"효력이\s*없(?:습니다|다)|더\s*이상\s*유효하지\s*않|"
        r"(?:has\s+been|is)\s+repealed|no\s+longer\s+(?:valid|in\s+force)", text, re.IGNORECASE,
    )) or bool(re.search(r"现行法律要求|目前有效|已被废止|luật hiện hành yêu cầu|đã bị bãi bỏ|작업해도\s*됩니다|작업을\s*승인합니다|可以安全作业|批准作业|được phép làm việc", text, re.I))


def _verify_citations(citations: list[Citation], originals: dict[str, Document]) -> bool:
    return bool(citations) and all(
        citation.chunk_id in originals and bool(citation.quote.strip())
        and citation.quote in originals[citation.chunk_id].page_content
        for citation in citations
    )


def _quantities_supported(text: str, citations: list[Citation]) -> bool:
    """Reject new numeric facts/units/dates using ONLY this claim's quotes.

    Conservative: no unit conversion or inferred shelf life. Omission can be a
    valid summary; negation, bounds and meaning are checked by the verifier.
    """
    def canonical(value):
        return unicodedata.normalize("NFKC", value).lower().replace("−", "-")

    claim = canonical(text)
    evidence = canonical("\n".join(c.quote for c in citations))
    number = r"[+-]?\d+(?:[.,]\d+)?"
    unit = r"ppm|ppb|mg/m3|μg/m3|g/l|mg/l|°c|°f|%|kg|mg|μg|ml|l|g"
    measurements = rf"({number})\s*({unit})(?![a-z])"
    dates = r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
    return all(
        set(re.findall(pattern, claim)).issubset(set(re.findall(pattern, evidence)))
        for pattern in (number, measurements, dates)
    )


def _verify_draft_support(question, draft, originals, required, translated, *,
                          language, as_of, model, timeout_seconds) -> str | None:
    """Verify every rendered claim/condition/translation once, fail closed.

    Returns a private review reason, or None on complete supported verdicts.
    This probabilistic gate is not a guarantee of factual or workplace safety.
    """
    claims = []
    for index, statement in enumerate(draft.statements):
        claims.append({"claim_id": f"s{index}", "kind": statement.kind,
                       "text": statement.text,
                       "conditions": [condition.text for condition in statement.conditions],
                       "citations": [c.model_dump() for c in statement.citations]})
        for position, condition in enumerate(statement.conditions):
            claims.append({"claim_id": f"s{index}.c{position}", "kind": "condition",
                           "text": condition.text,
                           "citations": [c.model_dump() for c in condition.citations]})
    for index, (pid, (cid, original)) in enumerate(required.items()):
        if language != "ko":
            claims.append({"claim_id": f"t{index}", "kind": "translation",
                           "text": translated[pid],
                           "citations": [{"chunk_id": cid, "quote": original}]})
    try:
        verifier = build_verification_llm(model, timeout_seconds=timeout_seconds)
        raw = verifier.invoke(prompt.build_verification_messages(
            question, claims, list(originals.values()), language=language, as_of=as_of,
        ))
        result = EvidenceVerification.model_validate(raw)
    except Exception:
        # Timeouts, configuration/provider errors and malformed verdicts must
        # never release the original answer or expose raw exception contents.
        return "verification_unavailable"
    expected = {claim["claim_id"] for claim in claims}
    ids = [item.claim_id for item in result.assessments]
    if len(ids) != len(expected) or set(ids) != expected:
        return "verification_unavailable"
    if any(item.verdict != "supported" for item in result.assessments):
        return "claim_mismatch"
    return None


def _has_duty_assertion(text: str) -> bool:
    """Conservative lexical check; not a legal entailment classifier."""
    return bool(re.search(
        r"하여야|되어야|이어야|해야\s*(?:합|한|할|해|되|만)|반드시|"
        r"의무\s*(?:입니다|이다|가\s*있|를\s*진|를\s*부담)|"
        r"\bmust\b|\bshall\b|required\s+to|必须|有义务|应当|\bphải\b|có nghĩa vụ", text, re.IGNORECASE,
    ))


def _supports_legal_duty(citations: list[Citation], metadata: dict[str, SourceMetadata]) -> bool:
    # Every supporting citation must be law; one unrelated law citation cannot
    # launder guidance into a legal duty. Reject if the quoted law has no clear
    # mandatory wording. This deliberately errs toward deferring ambiguous text.
    return all(metadata[c.chunk_id].doc_type == DOC_TYPE_LAW for c in citations) and any(
        _has_duty_assertion(c.quote) for c in citations
    )


def _law_review_reasons(sources: list[SourceMetadata], as_of: date) -> list[str]:
    reasons, versions = [], {}
    for source in sources:
        if source.doc_type != DOC_TYPE_LAW:
            continue
        reasons.append("law_currentness_unverified")
        value = source.effective_date
        if not value:
            reasons.append("effective_date_missing")
            continue
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError
            effective_date = date.fromisoformat(value)
        except ValueError:
            reasons.append("effective_date_invalid")
            continue
        if effective_date > as_of:
            reasons.append("effective_date_future")
        versions.setdefault((source.law_name, source.article_no), set()).add(value)
    if any(len(dates) > 1 for dates in versions.values()):
        reasons.append("law_version_conflict")
    # No age threshold: an old commencement date does not establish repeal.
    return list(dict.fromkeys(reasons))


def preflight_result(question: str, language: str = "ko") -> GenerationOutput | None:
    """Run BEFORE retrieval/query translation. No network, keys, or indexes."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question cannot be blank")
    if language not in LANGUAGES:
        raise ValueError("language must be ko, zh, or vi")
    if is_emergency(question):
        return _review_result("emergency", language=language)
    if is_prohibited_request(question) or _is_out_of_scope(question):
        return _review_result("out_of_scope", language=language)
    return None


def _parse_msds_revision_date(value: str | None) -> date:
    """Compare explicit YYYY-MM-DD / YYYY.MM.DD without rewriting evidence.

    Reject partial/ambiguous dates, mixed separators and invalid calendar dates.
    This is only a format conversion, not proof of currentness or applicability.
    """
    if not isinstance(value, str):
        raise ValueError("MSDS revision date is missing")
    match = re.fullmatch(r"([0-9]{4})([-.])([0-9]{2})\2([0-9]{2})", value)
    if match is None:
        raise ValueError("Unsupported MSDS revision date format")
    return date(int(match[1]), int(match[3]), int(match[4]))


def _verified_product(draft: EvidenceDraft, originals, metadata_by_id, reference_date: date, question: str) -> bool:
    fields = {}
    labels = {
        "product_name": r"제품명|product\s*(?:name|identifier)|产品名称|tên\s*sản\s*phẩm",
        "product_number": r"제품\s*번호|product\s*(?:number|code)|产品编号|mã\s*sản\s*phẩm",
        "concentration": r"농도|함유량|concentration|浓度|nồng\s*độ",
        "revision_date": r"개정일|최종\s*개정|revision\s*date|修订日期|ngày\s*sửa\s*đổi",
    }
    for fact in draft.product_facts:
        if not fact.value.strip() or not _verify_citations(fact.citations, originals):
            return False
        if any(metadata_by_id[c.chunk_id].doc_type != DOC_TYPE_MSDS for c in fact.citations):
            return False
        value_pattern = re.compile(r"(?<![\w.%-])" + re.escape(fact.value) + r"(?![\w.%-])")
        if not any(value_pattern.search(c.quote) and re.search(labels[fact.field], c.quote, re.I) for c in fact.citations):
            return False
        if fact.field in fields and fields[fact.field] != fact.value:
            return False
        fields[fact.field] = fact.value
    if set(fields) != {"product_name", "product_number", "concentration", "revision_date"}:
        return False
    if any(re.search(r"unknown|not available|미상|미확인|기재\s*없|n/a|不明|未知|không rõ", value, re.I) for value in fields.values()):
        return False
    if not re.search(r"\d", fields["concentration"]):
        return False
    requested_percentages = set(re.findall(r"\d+(?:\.\d+)?\s*%", question))
    if requested_percentages and {value.replace(" ", "") for value in requested_percentages} != set(re.findall(r"\d+(?:\.\d+)?%", fields["concentration"].replace(" ", ""))):
        return False
    try:
        # Original values/quotes have already passed exact evidence checks.
        # Normalize only for comparison; preserve original metadata and display.
        revision = _parse_msds_revision_date(fields["revision_date"])
        dates = {_parse_msds_revision_date(m.effective_date)
                 for m in metadata_by_id.values() if m.doc_type == DOC_TYPE_MSDS}
    except ValueError:
        return False
    if revision > reference_date:
        return False
    return dates == {revision}


def generate_answer(
    question: str,
    documents: list[Document],
    *,
    structured_llm: DocumentStructuredLLM | None = None,
    model: str | None = None,
    timeout_seconds: float = 30.0,
    as_of: date | None = None,
    language: str = "ko",
    mode: str = "qa",
    product_id: str | None = None,
    topic: str | None = None,
) -> GenerationOutput:
    """Generate from retrieved Documents, with no retrieval or API-side effects.

    Returns exactly answer, sources, needs_review, handoff (via model_dump()).
    Operational/evidence failures are review results with distinct reason codes.
    Invalid programmer inputs raise ValueError/TypeError. No credentials or raw
    provider exception messages enter the result. The existing HTTP response schema is untouched.
    """
    early = preflight_result(question, language)
    if mode not in MODES:
        raise ValueError("mode must be qa, learn, or precheck")
    mode = resolve_mode(question, mode)
    if product_id is not None and (not isinstance(product_id, str) or not product_id.strip()):
        raise ValueError("product_id must be a nonblank string or None")
    if early is not None:
        return early
    if not isinstance(documents, list) or any(not isinstance(doc, Document) for doc in documents):
        raise TypeError("documents must be a list[Document]")
    _valid_timeout(timeout_seconds)
    if as_of is not None and type(as_of) is not date:
        raise TypeError("as_of must be a date")
    reference_date = as_of or datetime.now(ZoneInfo("Asia/Seoul")).date()
    def review(reason):
        return _review_result(reason, language=language)

    text = TEXT[language]
    usable = [doc for doc in documents if doc.page_content.strip()]
    msds = [doc for doc in usable if doc.metadata.get("doc_type") == DOC_TYPE_MSDS]
    product_specific = bool(msds) or (topic != TOPIC_LAW and product_question(question)) or product_id is not None
    if product_specific:
        if not product_id or not msds or any(doc.metadata.get("product_id") != product_id for doc in msds):
            return review("product_unverified")
        # Refuse known cross-substance retrieval mismatches, even with a supplied ID.
        aliases = [("불산", "氢氟酸", "hydrofluoric", "flohydric"),
                   ("황산", "硫酸", "sulfuric", "sunfuric"), ("염산", "盐酸", "hydrochloric", "clohydric")]
        corpus = " ".join(doc.page_content + " " + str(doc.metadata.get("substance", "")) for doc in msds).lower()
        for group in aliases:
            if any(alias in question.lower() for alias in group) and not any(alias in corpus for alias in group):
                return review("product_unverified")
    if not usable:
        return review("no_evidence")

    originals, metadata_by_id = {}, {}
    for doc in usable:
        try:
            metadata = SourceMetadata.model_validate(doc.metadata)
        except (ValidationError, ValueError):
            return review("invalid_metadata")
        previous = originals.get(metadata.chunk_id)
        if previous is not None and (previous.page_content != doc.page_content or previous.metadata != doc.metadata):
            return review("invalid_metadata")
        originals[metadata.chunk_id] = doc
        metadata_by_id[metadata.chunk_id] = metadata

    if prompt.incomplete_critical_chunks(msds):
        return review("incomplete_warning_context")

    try:
        llm = structured_llm if structured_llm is not None else build_document_llm(model or os.getenv(ENV_LLM_MODEL, "gpt-4o"), timeout_seconds=timeout_seconds)
        raw = llm.invoke(build_document_messages(question, usable, as_of=reference_date, language=language, mode=mode, product_id=product_id))
    except (APITimeoutError, httpx.TimeoutException, TimeoutError):
        return review("llm_timeout")
    except RAGConfigurationError:
        return review("configuration_error")
    except (ValidationError, OutputParserException):
        return review("invalid_output")
    except Exception:
        return review("llm_error")
    try:
        draft = EvidenceDraft.model_validate(raw)
    except (ValidationError, TypeError):
        return review("invalid_output")
    if not draft.supported or not draft.statements:
        return review("no_evidence")

    if msds and not _verified_product(draft, originals, metadata_by_id, reference_date, question):
        return review("product_unverified")

    selected_ids = []
    reasons = ["msds_applicability_unverified"] if msds else []
    if mode == "precheck":
        reasons.append("precheck_requires_review")
    for statement in draft.statements:
        if _unsafe_text(statement.text) or not _verify_citations(statement.citations, originals):
            return review("invalid_evidence")
        if not translation_valid("", statement.text, language):
            return review("invalid_translation")
        if statement.kind != "legal_obligation" and _has_duty_assertion(statement.text):
            return review("invalid_evidence")
        if statement.kind == "legal_obligation" and not _supports_legal_duty(statement.citations, metadata_by_id):
            return review("invalid_evidence")
        if not _quantities_supported(statement.text, statement.citations):
            return review("claim_mismatch")
        selected_ids.extend(c.chunk_id for c in statement.citations)
        if not statement.conditions:
            reasons.append("conditions_unverified")
        for condition in statement.conditions:
            if _unsafe_text(condition.text) or not _verify_citations(condition.citations, originals):
                return review("invalid_evidence")
            if not _quantities_supported(condition.text, condition.citations):
                return review("claim_mismatch")
            if not translation_valid("", condition.text, language):
                return review("invalid_translation")
            if statement.kind != "legal_obligation" and _has_duty_assertion(condition.text):
                return review("invalid_evidence")
            if statement.kind == "legal_obligation" and not all(
                metadata_by_id[c.chunk_id].doc_type == DOC_TYPE_LAW for c in condition.citations
            ):
                return review("invalid_evidence")
            selected_ids.extend(c.chunk_id for c in condition.citations)

    if msds:
        selected_ids.extend(c.chunk_id for fact in draft.product_facts for c in fact.citations)
    passages = critical_passages(usable)
    required = {pid: pair for pid, pair in passages.items()
                if pair[0] in selected_ids or metadata_by_id[pair[0]].doc_type == DOC_TYPE_MSDS}
    translated = {}
    for item in draft.critical_translations:
        if item.passage_id not in passages or item.passage_id in translated:
            return review("invalid_translation")
        if _unsafe_text(item.text) or not translation_valid(passages[item.passage_id][1], item.text, language):
            return review("invalid_translation")
        passage_cid, passage_quote = passages[item.passage_id]
        if not _quantities_supported(item.text, [Citation(chunk_id=passage_cid, quote=passage_quote)]):
            return review("claim_mismatch")
        translated[item.passage_id] = item.text
    if language != "ko" and not set(required).issubset(translated):
        return review("invalid_translation")
    verification_failure = _verify_draft_support(
        question, draft, originals, required, translated, language=language,
        as_of=reference_date, model=model or os.getenv(ENV_LLM_MODEL, "gpt-4o"),
        timeout_seconds=timeout_seconds,
    )
    if verification_failure:
        return review(verification_failure)
    selected_ids.extend(cid for cid, _ in required.values())
    selected_ids = list(dict.fromkeys(selected_ids))
    sources = [metadata_by_id[chunk_id].model_copy(deep=True) for chunk_id in selected_ids]
    reasons.extend(_law_review_reasons(sources, reference_date))
    reasons = list(dict.fromkeys(reasons))
    source_numbers = {chunk_id: i for i, chunk_id in enumerate(selected_ids, start=1)}
    labels = text

    def markers(citations: list[Citation]) -> str:
        return " ".join(f"[{source_numbers[chunk_id]}]" for chunk_id in dict.fromkeys(c.chunk_id for c in citations))

    parts = []
    if mode != "qa":
        parts.append(text[mode])
    previous_kind = None
    for statement in draft.statements:
        if statement.kind != previous_kind:
            parts.append(labels[statement.kind])
        parts.append(f"{statement.text.strip()} {markers(statement.citations)}")
        previous_kind = statement.kind
        if statement.conditions:
            parts.append(text["conditions"])
            parts.extend(f"- {condition.text.strip()} {markers(condition.citations)}" for condition in statement.conditions)
    if "conditions_unverified" in reasons:
        parts.append(text["missing_conditions"])
    if required:
        parts.append(text["warnings"])
        for pid, (cid, original) in required.items():
            # Display soft line breaks as spaces; citation evidence stays verbatim.
            translated_text = re.sub(r"\s+", " ", original) if language == "ko" else translated[pid]
            parts.append(f"- {translated_text} [{source_numbers[cid]}]")
            if language != "ko":
                parts.append(f"  {text['original']}: {original}")
    if any(source.doc_type == DOC_TYPE_LAW for source in sources):
        parts.append(text["law_review"])
    if msds:
        product_labels = {
            "ko": {"product_name": "자료의 제품명", "product_number": "제품번호", "concentration": "농도", "revision_date": "MSDS 개정일"},
            "zh": {"product_name": "资料中的产品名称", "product_number": "产品编号", "concentration": "浓度", "revision_date": "MSDS修订日期"},
            "vi": {"product_name": "Tên sản phẩm trong tài liệu", "product_number": "Mã sản phẩm", "concentration": "Nồng độ", "revision_date": "Ngày sửa đổi MSDS"},
        }
        for fact in draft.product_facts:
            parts.append(f"{product_labels[language][fact.field]}: {fact.value} {markers(fact.citations)}")
        parts.append(text["msds_review"])
    if "effective_date_future" in reasons:
        parts.append(text["future"])
    if "law_version_conflict" in reasons:
        parts.append(text["versions"])
    result = GenerationOutput(
        answer="\n\n".join(parts), sources=sources,
        needs_review=bool(reasons), handoff=bool(reasons),
    )
    result._review_reasons = reasons
    result._review_message = " ".join(_REVIEW_MESSAGES[reason] for reason in reasons)
    return result


# 팀 API 응답 변환

class APISource(Source):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("doc_id")
    @classmethod
    def nonblank_doc_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("doc_id cannot be blank")
        return value


class GenerationAPIResponse(RagResponse):
    """User-confirmed API contract; distinct from the internal team metadata."""
    model_config = ConfigDict(extra="forbid", strict=True)
    sources: list[APISource]
    latency_ms: int = Field(ge=0)


def _section(source: SourceMetadata) -> str:
    if source.section:
        return source.section
    article, paragraph = source.article_no, source.paragraph
    compact_article = "".join(article.split())
    if not paragraph or "".join(paragraph.split()) in compact_article:
        return article
    # Merge a shared article suffix / paragraph prefix at a legal unit boundary,
    # e.g. 제2조 제2항 + 제2항 제1호. Keep the original strings otherwise.
    boundaries = [m.start() for m in re.finditer(r"제\s*\d+\s*(?:조|항|호)|[가-하]\s*목", paragraph)]
    for boundary in reversed(boundaries[1:]):
        if compact_article.endswith("".join(paragraph[:boundary].split())):
            return f"{article} {paragraph[boundary:]}".strip()
    return f"{article} {paragraph}".strip()


def build_api_response(
    result: GenerationOutput,
    *,
    latency_ms: int,
    doc_id_by_chunk_id: Mapping[str, str],
) -> GenerationAPIResponse:
    """Convert validated sources, preserving answer markers and source order.

    ``doc_id_by_chunk_id`` must explicitly cover every cited chunk. It may map
    several chunks to one document; do not deduplicate those source entries.
    No default ID convention is assumed. Metadata stays in the original result.
    ``latency_ms`` is caller-measured whole-request time, rounded to integer ms.

    Missing mappings/invalid IDs or latency raise ValueError (including Pydantic
    ValidationError); malformed caller types raise TypeError. No HTTP policy is
    imposed here. A failed conversion must not be sent as a successful response.
    """
    if not isinstance(result, GenerationOutput):
        raise TypeError("result must be a GenerationOutput")
    if not isinstance(doc_id_by_chunk_id, Mapping):
        raise TypeError("doc_id_by_chunk_id must be a mapping")
    if type(latency_ms) is not int or latency_ms < 0:
        raise ValueError("latency_ms must be a nonnegative integer")

    sources = []
    for source in result.sources:
        if source.chunk_id not in doc_id_by_chunk_id:
            raise ValueError("doc_id mapping is missing for a cited chunk")
        sources.append(APISource(
            doc_id=doc_id_by_chunk_id[source.chunk_id],
            section=_section(source),
            # Prefer the original law/document name. A guide may only have an
            # article title; keep empty if neither exists rather than invent one.
            title=source.title or source.law_name or source.article_title or "",
            url=source.source_url,
        ))
    return GenerationAPIResponse(
        answer=result.answer,
        sources=sources,
        needs_review=result.needs_review,
        handoff=result.handoff,
        latency_ms=latency_ms,
    )


# 기존 팀 Hit 입력 연결

class GenerationUnavailable(RuntimeError):
    """Sanitized provider failure for the existing API's HTTP 503 handler."""


def needs_review(hits: List[Hit], answer_text: str) -> bool:
    """Legacy helper retained; full citation validation happens in generate()."""
    return (not hits or any(h.get("metadata", {}).get("doc_type") in
                           (DOC_TYPE_LAW, DOC_TYPE_MSDS) for h in hits)
            or bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|ppm|mg|㎎|℃|°C|시간|분)", answer_text)))


def needs_handoff(question: str, hits: List[Hit]) -> bool:
    """Legacy Korean preflight helper; generate() applies multilingual checks."""
    return not hits or preflight_result(question, "ko") is not None


def generate(question: str, hits: List[Hit], language: str, *,
             product_id: str | None = None, topic: str | None = None,
             mode: str = "qa", structured_llm=None) -> RagResponse:
    early = preflight_result(question, language)
    if early is not None:
        return RagResponse(**early.model_dump())
    documents = []
    for hit in hits:
        metadata = hit.get("metadata", {})
        if not isinstance(hit.get("text"), str) or not isinstance(metadata, dict):
            return RagResponse(answer=TEXT[language]["fallback"], needs_review=True, handoff=True)
        # Current shared API requires a real document ID. Legacy metadata must
        # be enriched by the data owner; do not fabricate a doc_id from chunk_id.
        if not isinstance(metadata.get("doc_id"), str) or not metadata["doc_id"].strip():
            return RagResponse(answer=TEXT[language]["fallback"], needs_review=True, handoff=True)
        documents.append(Document(page_content=hit["text"], metadata=dict(metadata)))
    result = generate_answer(question, documents, language=language, mode=mode,
                             product_id=product_id, topic=topic, structured_llm=structured_llm)
    if {"llm_timeout", "llm_error", "configuration_error"}.intersection(result.review_reasons):
        # Preserve app.main's existing 503 policy without exposing raw errors.
        raise GenerationUnavailable("Generation provider is temporarily unavailable")
    ids = {doc.metadata.get("chunk_id"): doc.metadata["doc_id"] for doc in documents}
    payload = build_api_response(result, latency_ms=0, doc_id_by_chunk_id=ids)
    return RagResponse(**payload.model_dump())
