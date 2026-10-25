"""답변 생성·검증 — 담당: 박진근.

팀 진입점 generate(question, hits, language)는 그대로 유지한다.
문서 직접 입력은 generate_answer, 프롬프트는 prompt.py, 모델 호출은 llm.py가 맡는다.
검색·적재·JWT·라우팅은 수행하지 않는다. 인용 검사는 의미적 정확성을 보증하지 않는다.
"""
from __future__ import annotations

from datetime import date, datetime
import re
from collections import Counter
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
from rag.diagnostics import record_failure
from rag.llm import call_llm, RAGConfigurationError, validate_timeout as _valid_timeout, DEFAULT_MODEL as DEFAULT_LLM_MODEL
from openai import APITimeoutError
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, field_validator, model_validator
from rag.prompt import (
    LANGUAGES, MODES, TEXT, critical_passages, normalized,
    translation_valid, resolve_mode,
)
from rag.schema import DocType, ENV_LLM_MODEL, DOC_TYPE_GUIDE, DOC_TYPE_LAW, DOC_TYPE_MSDS, TOPIC_LAW, Hit, Source, RagResponse

# 요청 범위 검사

def is_emergency(question: str) -> bool:
    text = question.lower()
    compact = re.sub(r"\s+", "", text)
    ko = r"눈에(?:들어|튄|튀었)|피부에(?:닿|묻|튀)|흡입했|들이마셨|삼켰|쓰러|의식이없|의식을잃|숨을못|호흡곤란|노출(?:됐|되었)|누출(?:됐|되었|중|사고)|새고있|불이났|화재가|폭발했|화상을입|(?:긴급|응급|비상)(?:상황|사고|노출)"
    zh = r"溅[到入进].{0,8}(?:眼|皮肤)|(?:眼睛|皮肤).{0,8}(?:溅|接触)|接触.{0,8}(?:皮肤|眼)|吸入了|误吸|误服|吞下|昏倒|失去意识|无法呼吸|呼吸困难|正在泄漏|泄漏了|发生泄漏|发生火灾|起火了|紧急|(?:化学品|气体)泄漏"
    vi = r"(?:ban|dinh|vang).{0,15}(?:vao|len).{0,4}(?:mat|da)|hit phai|nuot phai|bat tinh|kho tho|bi phoi nhiem|dang ro ri|bi ro ri|hoa hoan|khan cap|bi bong"
    en = r"(?:chemical|gas|acid).{0,30}(?:leak|spill)|(?:splashed|got).{0,15}(?:eyes|skin)|inhaled|swallowed|unconscious|cannot breathe"
    # en · km 사고 신호 (김규빈 추가, ko · zh · vi 규칙과 같은 범위). 크메르어는 normalized() 가 결합 문자를 지워 원문으로 검사한다.
    en_incident = (
        r"(?:splash|spill|spatter|got).{0,20}(?:on|onto).{0,10}(?:my )?(?:clothes|clothing|uniform|coverall)"
        r"|(?:gas|leak).{0,15}(?:alarm|alert).{0,15}(?:went off|is sounding|sounded|triggered|is ringing|going off)"
        r"|(?:strange|unusual|unknown|weird) (?:smell|odor)"
    )
    km = r"ចូលភ្នែក|ប្រឡាក់ស្បែក|ប៉ះស្បែក|លេចធ្លាយ|សំឡេងរោទិ៍|ក្លិនចម្លែក|ស្រូបចូល|សន្លប់|ពិបាកដកដង្ហើម"
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
    # 몸에 묻음·튐·삼킴을 과거형으로 말한 경우 (김규빈 추가). "황산이 손에 묻었어요", "황산을 마셨어요"가
    # 일반 질문으로 처리됐다. "묻으면"처럼 가정하는 말은 여기서 잡지 않는다.
    contact = r"(?:묻었|묻어서|묻어있|묻고|튀었|튀어서|튀고|닿았|닿아서|닿고|들어갔|들어가서|뒤집어썼)"
    body = r"(?:눈|피부|손|손등|손가락|손목|팔|다리|발|얼굴|몸|목|입|등|가슴|머리)"
    ko_body = (
        rf"{body}(?:에|에도|으로|쪽에)\S{{0,15}}{contact}"
        rf"|(?:산|약품|약액|용액|시약|물질|가스)(?:이|가)\S{{0,12}}{contact}"
        r"|(?:마셨|마셔버|먹었|먹어버|삼켰|삼켜버|흡입했)"
    )
    zh_body = r"(?:溅|沾|碰)到?了?.{0,6}(?:手|脸|胳膊|腿|身上)|(?:喝|吃)了.{0,8}(?:酸|碱|药液|化学品)|(?:酸|碱|药液|化学品).{0,8}(?:喝|吃)了"
    vi_body = r"(?:ban|dinh|vang).{0,15}(?:vao|len).{0,4}(?:tay|mat toi|chan|nguoi)|(?:uong|nuot) phai"
    en_body = r"(?:on|onto|into) my (?:hand|hands|arm|arms|face|skin|leg|eye|eyes)|\b(?:drank|ingested)\b"
    # 부정 표현 전체를 제거하지 않는다. 같은 질문에 실제 사고가 함께 있을 수 있다.
    # 어휘 규칙이므로 모든 표현이나 문맥을 이해하는 분류기는 아니다.
    return bool(
        re.search(ko, compact) or re.search(ko_incident, compact) or re.search(ko_body, compact)
        or re.search(zh_body, text) or re.search(vi_body, normalized(text)) or re.search(en_body, text)
        or re.search(zh, text) or re.search(zh_incident, text)
        or re.search(vi, normalized(text)) or re.search(vi_incident, normalized(text))
        or re.search(en, text) or re.search(en_incident, text)
        or re.search(km, question)
    )

def is_prohibited_request(question: str) -> bool:
    compact = re.sub(r"\s+", "", question.lower())
    text = normalized(question)
    ko = r"(?:우리|저희|회사|대표|내가|제가|당사|이사고).{0,35}(?:법적책임|유죄|무죄|처벌받|책임져|책임을져)|무조건처벌|(?:법적|형사|민사)책임.{0,8}(?:판단|확정|결정)|누가.{0,10}책임|(?:작업|가동|진입|재가동)(?!을?(?:멈추|중지|중단|그만))(?!.{0,20}(?:멈추|중지|중단|대피))(?:.{0,20})(?:승인해|허가해|해도돼|해도되|안전한지판단)|(?:중화|희석|혼합|누출차단).{0,20}(?:방법|순서|절차|비율|해줘|알려)|(?:보호구|장갑).{0,8}없이.{0,15}(?:작업|취급)|(?:불산|황산|화학물질).{0,20}(?:섞는법|처리순서)"
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
        re.search(r"(?:작업|가동|재가동|입장|진입)(?!을?(?:멈추|중지|중단|그만))(?!.{0,20}(?:멈추|중지|중단|대피))(?:.{0,20})(?:승인(?:을)?해|허가(?:를)?해|해도돼|해도되|해도될|안전하다고|안전한지판단)", compact)
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
    text: str = Field(description="One source action per sentence, preserving its force. Supplier contact is not PPE selection. A label/reference location is information, not a new must/shall requirement. For handling/storage/PPE actions use an impersonal subject such as the document, NOT a product name or product placeholder. Product identity is rendered separately from product_facts. Describe label/reference locations as information without adding must/shall.")
    citations: list[Citation] = Field(description="Exact contiguous source quotes including indentation and line breaks. Use only the source lines directly needed for the action and its conditions. Every identifier asserted in text must also be supported by an exact source citation.")
    conditions: list[EvidenceCondition] = Field(description="Include every cited source applicability condition or exception, with its exact quote, even when already mentioned in text. Use [] only when the source gives no condition; never invent one.")


class EvidenceDraft(BaseModel):
    """LLM output; never includes source metadata, review flags, or handoff."""
    model_config = ConfigDict(extra="forbid", strict=True)
    supported: bool
    statements: list[EvidenceStatement]
    critical_translations: list["CriticalTranslation"] = Field(default_factory=list, description="Translate EVERY exact ID in CRITICAL_PASSAGES_JSON once; never omit a warning even if the question asks only product identity. Keep all quantities unchanged. Return [] if that map is empty; never use a chunk_id as a passage_id.")
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




def build_document_llm(model: str = DEFAULT_LLM_MODEL, *, timeout_seconds: float = 30.0) -> DocumentStructuredLLM:
    """생성 출력 규격을 llm.py의 공급자 팩토리에 전달한다."""
    return llm.build_structured_llm(EvidenceDraft, model, timeout_seconds=timeout_seconds)


def build_verification_llm(model: str = DEFAULT_LLM_MODEL, *, timeout_seconds: float = 30.0):
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


def _unsafe_critical_translation(text: str, original: str) -> bool:
    """Allow only the original supplier URLs in a warning translation.

    New/extended URLs and all other unsafe assertions still fail locally;
    independent semantic verification compares the untouched translation.
    """
    url_characters = r"A-Za-z0-9./?=&%_~#:+@-"
    for url in re.findall(r"(?:https?://|www\.)[" + url_characters + r"]+", original):
        text = re.sub(re.escape(url) + r"(?![" + url_characters + r"])", " ", text)
    return _unsafe_text(text)


def _same_text(quote: str, source: str) -> bool:
    """원문 인용 일치. PDF 줄바꿈·공백 차이만 무시한다 (글자·순서는 그대로 일치해야 함).
    PDF 는 단어 중간에서도 줄을 바꾸므로("추정하\n지") 공백을 모두 지우고 비교한다. 법령의 한자 병기 "과(科)한다" 도 무시.
    숫자 사이 공백은 경계로 남긴다 ("10 0" 이 "100" 으로 붙지 않도록)."""
    squash = lambda s: re.sub(r"\s+|[(（][\u4e00-\u9fff]{1,4}[)）]", "", re.sub(r"(?<=\d)\s+(?=\d)", "|", s))
    return quote in source or squash(quote) in squash(source)


def _verify_citations(citations: list[Citation], originals: dict[str, Document]) -> bool:
    return bool(citations) and all(
        citation.chunk_id in originals and bool(citation.quote.strip())
        and _same_text(citation.quote, originals[citation.chunk_id].page_content)
        for citation in citations
    )


def _cited_cas_identifiers(citations, originals) -> tuple[str, ...]:
    """Recognize chemical IDs only in actual citations of CAS-labelled MSDS.

    A checksum-valid CAS number is an identifier, not an impossible calendar
    date. Exact source quotes and all numeric/semantic comparisons still apply.
    """
    identifiers = []
    for citation in citations:
        doc = originals.get(citation.chunk_id)
        if (doc is None or doc.metadata.get("doc_type") != DOC_TYPE_MSDS
                or citation.quote not in doc.page_content
                or not re.search(r"\bCAS\b", doc.page_content, re.I)):
            continue
        for value in re.findall(r"(?<![\w-])[1-9][0-9]{1,6}-[0-9]{2}-[0-9](?![\w-])", citation.quote):
            digits = value.replace("-", "")
            if sum(int(digit) * weight for weight, digit in enumerate(reversed(digits[:-1]), 1)) % 10 == int(digits[-1]):
                identifiers.append(value)
    return tuple(dict.fromkeys(identifiers))


MAX_CHUNK_WARNINGS = 3   # 지침·법령 청크에서 경고를 전부 붙이는 상한 (넘으면 인용과 겹치는 것만)


def _is_hazard_statement(passage, metadata_by_id) -> bool:
    """MSDS 2항의 유해·위험 문구 (H314 피부에 심한 화상… 처럼 H 로 시작). 예방조치 P 문구는 넣지 않는다."""
    cid, quote = passage
    meta = metadata_by_id[cid]
    return (meta.doc_type == DOC_TYPE_MSDS and meta.msds_section_no == 2
            and bool(re.match(r"\s*:?\s*H\d{3}", quote)))


def _cited_headers(citations, originals) -> str:
    """인용한 청크의 첫 줄 머리글 "[KOSHA K-1-2023 … 7.2 응급조치]". 답변이 출처 문서·조항 번호를 말할 때의 숫자 근거."""
    heads = []
    for cid in dict.fromkeys(c.chunk_id for c in citations):
        first = (originals[cid].page_content.split("\n", 1)[0] if cid in originals else "").strip()
        if first.startswith("[") and first.endswith("]"):
            heads.append(first)
    return "\n".join(heads)


def _quantities_supported(text: str, citations: list[Citation], *, source_identifiers=(), source_headers: str = "") -> bool:
    """Reject new numeric facts/units/dates using ONLY this claim's quotes.

    Conservative: no unit conversion or inferred shelf life. Omission can be a
    valid summary; negation, bounds and meaning are checked by the verifier.
    """
    def canonical(value):
        return unicodedata.normalize("NFKC", value).lower().replace("−", "-").translate(prompt.KHMER_DIGITS)

    claim = prompt.calendar_text_with_identifiers(canonical(text), source_identifiers)
    evidence = prompt.calendar_text_with_identifiers(canonical("\n".join(c.quote for c in citations)), source_identifiers)
    if claim is None or evidence is None:
        return False
    # 문서·조항 번호(K-1-2023, 7.2)는 인용 청크 머리글에서도 찾는다. 수치·단위·날짜 비교에는 쓰지 않는다
    headers = canonical(source_headers)
    number = r"[+-]?\d+(?:[.,]\d+)?"
    unit = r"ppm|ppb|mg/m3|μg/m3|g/l|mg/l|°c|°f|%|kg|mg|μg|ml|l|g"
    measurements = rf"({number})\s*({unit})(?![a-z])"
    dates = r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
    return all(
        set(re.findall(pattern, claim)).issubset(
            set(re.findall(pattern, evidence)) | (set(re.findall(pattern, headers)) if pattern == number else set()))
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
    except Exception as exc:
        record_failure(exc, stage="verification")
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



def _cited_ingredient_terms(citations, originals) -> tuple[str, ...]:
    """Script exceptions for name cells in actually cited MSDS table rows only.

    Require a header identifying both the name and concentration columns.
    Do not use metadata, another chunk, an uncited row, or arbitrary prose.
    Exact row/value citations and semantic support are checked independently.
    """
    terms = []
    for citation in citations:
        doc = originals.get(citation.chunk_id)
        if (doc is None or doc.metadata.get("doc_type") != DOC_TYPE_MSDS
                or not citation.quote.strip() or citation.quote not in doc.page_content):
            continue
        name_index = None
        width = 0
        for line in doc.page_content.splitlines():
            row = line.strip()
            if "|" not in row:
                name_index = None
                continue
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            header_names = [i for i, cell in enumerate(cells)
                            if re.fullmatch(r"구성성분(?:의 명칭)?|성분명|화학물질명|ingredient(?: name)?|chemical name", cell, re.I)]
            if header_names and any(re.search(r"함유량|농도|concentration|content", cell, re.I) for cell in cells):
                name_index, width = header_names[0], len(cells)
                continue
            if name_index is None:
                continue
            if all(re.fullmatch(r"[: -]+", cell) for cell in cells):
                continue  # Markdown separator row.
            if len(cells) != width:
                name_index = None
                continue
            name = cells[name_index]
            if (row in citation.quote and 1 < len(name) <= 80
                    and re.fullmatch(r"[\w ()\[\],+./%-]+", name)
                    and not re.search(r"[.!?]$", name)):
                terms.append(name)
    return tuple(dict.fromkeys(terms))


def _has_duty_assertion(text: str) -> bool:
    """Conservative lexical check; not a legal entailment classifier."""
    # Vietnamese negative copula means "is not", not "must". Remove only
    # that pair; a separate phải/must/legal duty in the same text remains.
    text = re.sub(r"\bkhông\s+phải\b", " ", text, flags=re.I)
    return bool(re.search(
        r"하\s*여야|되\s*어야|이\s*어야|있\s*어야|없\s*어야|해\s*야\s*(?:합|한|할|해|되|만)|져\s*야\s*(?:합|한|할|하)|반드시|"
        r"의무\s*(?:입니다|이다|가\s*있|를\s*진|를\s*부담)|"
        r"\bmust\b|\bshall\b|required\s+to|必须|有义务|应当|\bphải\b|có nghĩa vụ", text, re.IGNORECASE,
    ))


def _invalid_nonlaw_duty(text: str, citations, metadata) -> bool:
    """Separate explicit law claims from faithfully quoted MSDS instructions."""
    if not _has_duty_assertion(text):
        return False
    # Remove only explicit negative legal-status phrases, never the action
    # clause. A separate affirmative "by law" claim must still be rejected.
    nonlegal_text = re.sub(
        r"법적\s*의무(?:라는\s*뜻은\s*아니(?:며|고|다)|는?\s*아니(?:며|고|다)|로\s*단정하지\s*않(?:으며|고|습니다))|"
        r"\bnot\s+(?:a\s+)?(?:legal|statutory)\s+obligation\b|"
        r"(?:不是|并非|不属于)\s*(?:法定|法律)义务|"
        r"không\s+phải\s+(?:là\s+)?nghĩa\s+vụ\s+pháp\s+lý",
        " ", text, flags=re.I,
    )
    wording = normalized(nonlegal_text)
    explicit_law = re.search(
        r"법령|법률|법적|법정|법에\s*(?:따라|의해)|法律|法定|依法|有义务|"
        r"\blegal\b|\blaw\b|\bstatutory\b|phap luat|theo luat|nghia vu phap ly", wording, re.I,
    ) or re.search(r"ច្បាប់", nonlegal_text)
    if explicit_law:
        return True
    # A technical requirement can be mandatory without claiming legal status.
    # Keep source-force checks locally AND independent semantic verification.
    if not citations or any(metadata[c.chunk_id].doc_type == DOC_TYPE_LAW for c in citations):
        return True
    return not any(_source_technical_requirement(citation, metadata) for citation in citations)


def _source_technical_requirement(citation, metadata) -> bool:
    """Syntactic source-force check, never proof of the generated claim's meaning."""
    if metadata[citation.chunk_id].doc_type == DOC_TYPE_LAW:
        return False
    quote = citation.quote
    if _has_duty_assertion(quote) or re.search(
        r"하\s*(?:시오|십시오)|입으십시오|(?:할|말)\s*것(?=\s*(?:[.!?]|$))|금지|필수", quote, re.I | re.M,
    ):
        return True
    # KOSHA 지침의 번호 항목 "(5) …를 철저하게 착용한다." 와 "…착용을 해야 …" 도 지침의 요구 문체다
    if metadata[citation.chunk_id].doc_type == DOC_TYPE_GUIDE and (
        (re.match(r"\s*(?:\(\d+\)|\d+\)|[가-하]\.)\s", quote) and re.search(r"한다\.?\s*$", quote))
        or re.search(r"해\s*야(?=\s)", quote)
    ):
        return True
    return bool(
        metadata[citation.chunk_id].doc_type == DOC_TYPE_MSDS
        and re.search(r"(?:신체|피부)\s*(?:[/·]\s*(?:신체|피부))?\s*보호\s*[:：]", quote)
        and re.search(r"보호복|보호의|보호장갑|보안경", quote)
        and not re.search(r"권장|권고|추천|불필요|필요\s*없|착용하지\s*않아도|선택적", quote)
    )


def _align_technical_kinds(draft, originals, metadata):
    """Keep actual technical requirements out of the recommendation heading.

    Only already valid source quotes can change the internal category. Text,
    citation, strength and applicability are still independently verified.
    Never change a legal claim into a technical claim to make it pass.
    """
    statements = []
    for statement in draft.statements:
        if (statement.kind == "recommendation"
                and _verify_citations(statement.citations, originals)
                and all(metadata[c.chunk_id].doc_type != DOC_TYPE_LAW for c in statement.citations)
                and any(_source_technical_requirement(c, metadata) for c in statement.citations)):
            statement = statement.model_copy(update={"kind": "information"})
        statements.append(statement)
    return draft.model_copy(update={"statements": statements})


def _supports_legal_duty(citations: list[Citation], metadata: dict[str, SourceMetadata]) -> bool:
    # Every supporting citation must be law; one unrelated law citation cannot
    # launder guidance into a legal duty. Reject if the quoted law has no clear
    # mandatory wording. This deliberately errs toward deferring ambiguous text.
    return all(metadata[c.chunk_id].doc_type == DOC_TYPE_LAW for c in citations) and any(
        _has_duty_assertion(c.quote) for c in citations
    )


_DUTY_CHAPEAU = re.compile(r"[^.\n]*(?:\n[^.\n]*){0,3}다음\s*각\s*호[^.]{0,40}?(?:하여야|해야)\s*한다\.")


def _with_duty_chapeau(statement, originals, metadata):
    """법령 '다음 각 호' 목록(1. 2. …)만 인용한 의무 문장에, 같은 조문 청크의 '…다음 각 호에 따른 조치를 하여야 한다.'
    본문을 인용으로 덧붙인다. 목록 항목은 그 본문의 의무 내용이므로 의무 문구는 원문에서 그대로 가져온다."""
    if statement.kind != "legal_obligation" or _supports_legal_duty(statement.citations, metadata):
        return statement
    if not statement.citations or not all(
        metadata[c.chunk_id].doc_type == DOC_TYPE_LAW and re.match(r"\s*1\.\s", c.quote) for c in statement.citations
    ):
        return statement
    extra = []
    for cid in dict.fromkeys(c.chunk_id for c in statement.citations):
        match = _DUTY_CHAPEAU.search(originals[cid].page_content)
        if match is None:
            return statement
        extra.append(Citation(chunk_id=cid, quote=match.group(0).strip()))
    return statement.model_copy(update={"citations": extra + list(statement.citations)})


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
        raise ValueError("language must be one of " + ", ".join(LANGUAGES))
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
        # MSDS tables can put the concentration header above the cited row.
        # The value must still match this exact quote; only its label may come
        # from elsewhere in that same cited chunk, never from another chunk.
        if not any(
            value_pattern.search(c.quote)
            and re.search(
                labels[fact.field],
                originals[c.chunk_id].page_content if fact.field == "concentration" else c.quote,
                re.I,
            )
            for c in fact.citations
        ):
            return False
        if fact.field == "product_name" and not any(
            fact.value in prompt.product_name_tokens([originals[c.chunk_id]]).values()
            and fact.value in c.quote for c in fact.citations
        ):
            return False  # A wrapped product identifier must not be truncated.
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



def _source_product_facts(documents) -> list[ProductFact]:
    """MSDS 1·3·16항 원문에서 제품 식별 4항목을 서버가 직접 뽑는다 (LLM 추출이 빠지거나 흔들릴 때의 대안).

    값과 인용은 원문 부분 문자열 그대로이고, 결과는 _verified_product 의 같은 검증을 다시 통과해야 쓰인다.
    MSDS 가 한 제품일 때만 만든다. 하나라도 못 찾으면 [] (→ 기존대로 보류).
    """
    msds = [d for d in documents if d.metadata.get("doc_type") == DOC_TYPE_MSDS]
    if len({d.metadata.get("product_id") for d in msds}) != 1:
        return []
    cas = msds[0].metadata.get("cas_no") or ""
    found = {}

    def add(field, doc, match, group=1):
        value = match.group(group).strip()
        if field not in found and value:
            found[field] = ProductFact(field=field, value=value, citations=[
                Citation(chunk_id=doc.metadata["chunk_id"], quote=match.group(0).strip())])

    for doc in sorted(msds, key=lambda d: d.metadata.get("chunk_id", "")):
        text, no = doc.page_content, doc.metadata.get("msds_section_no")
        if no == 1:
            if m := prompt.PRODUCT_NAME_RE.search(text):
                add("product_name", doc, m)
            if m := re.search(r"(?:제품\s*번호|product\s*(?:number|code))[ \t]*[:：][ \t]*([\w.\-]+)", text, re.I):
                add("product_number", doc, m)
        elif no == 3 and cas and re.search(r"농도|함유량", text):
            if m := re.search(r"^[^\n]*" + re.escape(cas) + r"[ \t]+([^\n]*\d[^\n]*)$", text, re.M):
                add("concentration", doc, m)
        elif no == 16:
            if m := re.search(r"최종\s*개정\s*일자?[ \t]*[:：][ \t]*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})", text):
                add("revision_date", doc, m)
    return list(found.values()) if len(found) == 4 else []


def _restore_product_name_tokens(draft: EvidenceDraft, documents) -> EvidenceDraft | None:
    """Restore text only from already source-validated product name facts.

    Never repair a mistranslated literal or modify quotes/facts/metadata. Unknown
    tokens, absent product facts and names not evidenced by that text's citations
    fail closed. All normal evidence/semantic checks run on the restored text.
    """
    verified = {fact.value for fact in draft.product_facts if fact.field == "product_name"}
    tokens = {key: value for key, value in prompt.product_name_tokens(documents).items() if value in verified}

    def restore(text, citations):
        def replace(match):
            token = match[0]
            if token not in tokens or not any(tokens[token] in c.quote for c in citations):
                raise ValueError("Unverified product name placeholder")
            return tokens[token]

        text = re.sub(r"(?<![A-Za-z0-9_])CB_PRODUCT_NAME_[A-Za-z0-9_]+", replace, text)
        if "CB_PRODUCT_NAME_" in text:
            raise ValueError("Unresolved product name placeholder")
        return text

    try:
        statements = []
        for statement in draft.statements:
            conditions = [condition.model_copy(update={"text": restore(condition.text, condition.citations)})
                          for condition in statement.conditions]
            statements.append(statement.model_copy(update={
                "text": restore(statement.text, statement.citations), "conditions": conditions}))
        passages = critical_passages(documents)
        translations = []
        for item in draft.critical_translations:
            pair = passages.get(item.passage_id)
            citations = [Citation(chunk_id=pair[0], quote=pair[1])] if pair else []
            translations.append(item.model_copy(update={"text": restore(item.text, citations)}))
        return draft.model_copy(update={"statements": statements, "critical_translations": translations})
    except ValueError:
        return None


def _without_redundant_msds_statements(draft: EvidenceDraft, documents) -> EvidenceDraft:
    """Render verified product names and complete PPE warnings once, separately.

    Only exact, already verified name-fact citations can replace a name-only
    statement. A PPE duplicate is omitted only when a matching dedicated warning
    translation exists; that translation still passes every downstream check.
    Statements with conditions or legal claims are never omitted here.
    """
    names = {(c.chunk_id, c.quote) for fact in draft.product_facts if fact.field == "product_name"
             for c in fact.citations}
    passages = critical_passages(documents)
    translated_ids = {item.passage_id for item in draft.critical_translations}
    translated_quotes = {pair for pid, pair in passages.items() if pid in translated_ids}
    kept = []
    for statement in draft.statements:
        citations = {(c.chunk_id, c.quote) for c in statement.citations}
        eligible = statement.kind != "legal_obligation" and not statement.conditions and bool(citations)
        name_duplicate = eligible and citations.issubset(names)
        ppe_duplicate = eligible and citations.issubset(translated_quotes) and all(
            re.search(r"보호장갑|보호구|보안경", quote)
            and re.search(r"착용하(?:시오|십시오)[.!]?$", quote.strip()) for _, quote in citations
        )
        if not (name_duplicate or ppe_duplicate):
            kept.append(statement)
    return draft.model_copy(update={"statements": kept})


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
        if product_id is None:
            # A selected equipment or retrieved MSDS is not a selected product.
            # Keep existing response fields/reason; the UI owns product selection.
            return _review_result("product_unverified", answer=text["product_selection_required"], language=language)
        if not msds or any(doc.metadata.get("product_id") != product_id for doc in msds):
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
        llm = structured_llm if structured_llm is not None else build_document_llm(model or os.getenv(ENV_LLM_MODEL, DEFAULT_LLM_MODEL), timeout_seconds=timeout_seconds)
        raw = llm.invoke(build_document_messages(question, usable, as_of=reference_date, language=language, mode=mode, product_id=product_id))
    except (APITimeoutError, httpx.TimeoutException, TimeoutError) as exc:
        record_failure(exc, stage="generation")
        return review("llm_timeout")
    except RAGConfigurationError:
        return review("configuration_error")
    except (ValidationError, OutputParserException):
        return review("invalid_output")
    except Exception as exc:
        record_failure(exc, stage="generation")
        return review("llm_error")
    try:
        draft = EvidenceDraft.model_validate(raw)
    except (ValidationError, TypeError):
        return review("invalid_output")
    if not draft.supported or not draft.statements:
        return review("no_evidence")

    if msds and not _verified_product(draft, originals, metadata_by_id, reference_date, question):
        # LLM 이 식별 항목을 빠뜨리거나 잘못 뽑았으면 서버가 원문에서 뽑은 값으로 같은 검증을 한 번 더 한다
        draft = draft.model_copy(update={"product_facts": _source_product_facts(usable)})
        if not _verified_product(draft, originals, metadata_by_id, reference_date, question):
            return review("product_unverified")

    draft = _restore_product_name_tokens(draft, usable)
    if draft is None:
        return review("invalid_translation")
    draft = _align_technical_kinds(draft, originals, metadata_by_id)
    if msds:
        draft = _without_redundant_msds_statements(draft, msds)

    # Product names were verified by _verified_product above; allow those exact
    # identifiers in translated prose without allowing arbitrary source-language text.
    draft = draft.model_copy(update={"statements": [
        _with_duty_chapeau(st, originals, metadata_by_id) for st in draft.statements]})
    # 적용범위·정의 조문처럼 의무 문구가 없는 법령 인용을 '법적 의무'로 분류했으면 보류 대신 일반 정보로 낮춘다
    draft = draft.model_copy(update={"statements": [
        st.model_copy(update={"kind": "information"})
        if st.kind == "legal_obligation" and not _supports_legal_duty(st.citations, metadata_by_id)
        and all(metadata_by_id[c.chunk_id].doc_type == DOC_TYPE_LAW for c in st.citations)
        and not _has_duty_assertion(st.text)
        and not re.search(r"규정|의무|하도록|obligat|requir|规定|义务|quy định|nghĩa vụ", st.text, re.I) else st
        for st in draft.statements]})
    # 같은 종류 문장을 한데 모은다 (처음 나온 종류 순서, 종류 안에서는 원래 순서). 종류가 번갈아 나오면
    # 권고 꼬리표가 문단마다 반복됐다 (김규빈 2026-10-25). 출처 번호도 이 순서로 매긴다.
    kind_order = list(dict.fromkeys(st.kind for st in draft.statements))
    draft = draft.model_copy(update={"statements": sorted(draft.statements, key=lambda st: kind_order.index(st.kind))})
    preserved_terms =tuple(fact.value for fact in draft.product_facts if fact.field == "product_name") if msds else ()
    selected_ids = []
    reasons = ["msds_applicability_unverified"] if msds else []
    if mode == "precheck":
        reasons.append("precheck_requires_review")
    for statement in draft.statements:
        if _unsafe_text(statement.text) or not _verify_citations(statement.citations, originals):
            return review("invalid_evidence")
        if not translation_valid("", statement.text, language,
                                 preserved_terms=preserved_terms + _cited_ingredient_terms(statement.citations, originals)):
            return review("invalid_translation")
        # A product-name claim must use the verified identifier, not a translation.
        identity_claim = re.search(r"제품명|产品名|产品名称|product name|ten san pham", normalized(statement.text), re.I) or "ឈ្មោះផលិតផល" in statement.text
        if identity_claim and any(term not in statement.text and any(term in c.quote for c in statement.citations) for term in preserved_terms):
            return review("invalid_translation")
        # Guard the observed PPE failure: a source instruction must not become
        # a mere recommendation. Full semantic support is still checked below.
        direct_ppe = all(
            metadata_by_id[c.chunk_id].doc_type == DOC_TYPE_MSDS
            and re.search(r"보호장갑|보호구|보안경", c.quote)
            and re.search(r"착용하(?:시오|십시오)[.!]?$", c.quote.strip())
            for c in statement.citations
        )
        if direct_ppe and re.search(r"recommend|advis|suggest|建议|推荐|khuyen|권장", normalized(statement.text), re.I):
            return review("invalid_translation")
        if (statement.kind == "recommendation" and _has_duty_assertion(statement.text)
                and not any(_has_duty_assertion(c.quote) for c in statement.citations)):
            return review("invalid_evidence")
        if statement.kind != "legal_obligation" and _invalid_nonlaw_duty(statement.text, statement.citations, metadata_by_id):
            return review("invalid_evidence")
        if statement.kind == "legal_obligation" and not _supports_legal_duty(statement.citations, metadata_by_id):
            return review("invalid_evidence")
        if not _quantities_supported(statement.text, statement.citations,
                source_identifiers=_cited_cas_identifiers(statement.citations, originals),
                source_headers=_cited_headers(statement.citations, originals)):
            return review("claim_mismatch")
        selected_ids.extend(c.chunk_id for c in statement.citations)
        if not statement.conditions:
            reasons.append("conditions_unverified")
        for condition in statement.conditions:
            if _unsafe_text(condition.text) or not _verify_citations(condition.citations, originals):
                return review("invalid_evidence")
            if not _quantities_supported(condition.text, condition.citations,
                    source_identifiers=_cited_cas_identifiers(condition.citations, originals),
                    source_headers=_cited_headers(condition.citations, originals)):
                return review("claim_mismatch")
            if not translation_valid("", condition.text, language,
                                     preserved_terms=preserved_terms + _cited_ingredient_terms(condition.citations, originals)):
                return review("invalid_translation")
            if statement.kind != "legal_obligation" and _invalid_nonlaw_duty(condition.text, condition.citations, metadata_by_id):
                return review("invalid_evidence")
            if statement.kind == "legal_obligation" and not all(
                metadata_by_id[c.chunk_id].doc_type == DOC_TYPE_LAW for c in condition.citations
            ):
                return review("invalid_evidence")
            selected_ids.extend(c.chunk_id for c in condition.citations)

    if msds:
        selected_ids.extend(c.chunk_id for fact in draft.product_facts for c in fact.citations)
    passages = critical_passages(usable)
    # 답변에 붙이는 경고: 답변이 인용한 청크의 경고 + MSDS 2항 유해·위험 문구(H코드: 물질의 기본 위험).
    # 예전에는 검색된 MSDS 청크의 경고를 전부 붙여, 보호구 질문에도 흡입·누출 처리 경고 10여 개가 나왔다 (김규빈 2026-10-24, 팀 결정).
    # MSDS 청크는 항목별로 짧아 인용한 청크의 경고를 모두 둔다. 지침·법령 청크도 경고가 3개 이하면 모두 둔다
    # (인용 문장 바로 옆의 "실제 작업에 사용하지 마세요" 같은 경고가 빠지지 않도록).
    # 그보다 많으면(KOSHA 목록 청크는 10여 개) 답변이 실제로 인용한 문장과 겹치는 경고만 둔다.
    quotes = [c.quote for st in draft.statements for c in [*st.citations, *(x for cond in st.conditions for x in cond.citations)]]
    per_chunk = Counter(cid for cid, _ in passages.values())
    def cited_warning(cid, original):
        if cid not in selected_ids:
            return False
        if metadata_by_id[cid].doc_type == DOC_TYPE_MSDS or per_chunk[cid] <= MAX_CHUNK_WARNINGS:
            return True
        return any(_same_text(q, original) or _same_text(original, q) for q in quotes)
    required = {pid: pair for pid, pair in passages.items()
                if cited_warning(*pair) or _is_hazard_statement(pair, metadata_by_id)}
    translated = {}
    for item in draft.critical_translations:
        if item.passage_id not in passages or item.passage_id in translated:
            return review("invalid_translation")
        if _unsafe_critical_translation(item.text, passages[item.passage_id][1]) or not translation_valid(passages[item.passage_id][1], item.text, language,
                source_doc_type=metadata_by_id[passages[item.passage_id][0]].doc_type,
                source_identifiers=_cited_cas_identifiers(
                    [Citation(chunk_id=passages[item.passage_id][0], quote=passages[item.passage_id][1])], originals),
                preserved_terms=preserved_terms + _cited_ingredient_terms(
                    [Citation(chunk_id=passages[item.passage_id][0], quote=passages[item.passage_id][1])], originals)):
            return review("invalid_translation")
        passage_cid, passage_quote = passages[item.passage_id]
        if not _quantities_supported(item.text, [Citation(chunk_id=passage_cid, quote=passage_quote)],
                source_identifiers=_cited_cas_identifiers(
                    [Citation(chunk_id=passage_cid, quote=passage_quote)], originals)):
            return review("claim_mismatch")
        translated[item.passage_id] = item.text
    if language != "ko" and not set(required).issubset(translated):
        return review("invalid_translation")
    verification_failure = _verify_draft_support(
        question, draft, originals, required, translated, language=language,
        as_of=reference_date, model=model or os.getenv(ENV_LLM_MODEL, DEFAULT_LLM_MODEL),
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

    # 답변 모양 (김규빈 2026-10-25): 문단 = 문장 종류 하나 (위에서 종류별로 모아 일반 정보 / 권고 / 법령이 각각 최대 한 문단).
    # 문단마다 소제목을 한 번 달고 문장은 "- " 목록으로 쓴다. 의무와 권고를 섞지 않는 안전 규칙은 그대로.
    # 일반 정보만 있는 짧은 답에는 소제목을 달지 않는다 (제목 한 줄이 오히려 군더더기).
    parts, paragraph = [], []

    def flush():
        if paragraph:
            parts.append("\n".join(paragraph)); paragraph.clear()

    if mode != "qa":
        parts.append(text[mode])
    headed = len(kind_order) > 1 or kind_order[:1] != ["information"] or bool(required)
    previous_kind = None
    for statement in draft.statements:
        if statement.kind != previous_kind:
            flush()
            if headed:
                paragraph.append(labels[statement.kind])
        paragraph.append(f"- {statement.text.strip()} {markers(statement.citations)}")
        previous_kind = statement.kind
        if statement.conditions:
            paragraph.append("  " + text["conditions"] + " " + " / ".join(
                f"{condition.text.strip()} {markers(condition.citations)}" for condition in statement.conditions))
    flush()
    if required:
        # 한국어는 본문이 이미 인용한 경고 문장은 다시 싣지 않는다 (같은 내용 반복 방지). 번역 답변은 번역 확인을 위해 모두 싣는다.
        quoted = [c.quote for st in draft.statements for c in [*st.citations, *(x for cond in st.conditions for x in cond.citations)]]
        lines = []
        for pid, (cid, original) in required.items():
            if language == "ko" and any(_same_text(q, original) or _same_text(original, q) for q in quoted):
                continue
            # Display soft line breaks as spaces; citation evidence stays verbatim.
            translated_text = re.sub(r"\s+", " ", original) if language == "ko" else translated[pid]
            lines.append(f"- {translated_text} [{source_numbers[cid]}]")
            if language != "ko":
                lines.append(f"  {text['original']}: {original}")
        if lines:
            parts.append(text["warnings"] + "\n" + "\n".join(lines))
    closing = []
    if msds:
        product_labels = {
            "ko": {"product_number": "제품번호", "concentration": "농도", "revision_date": "개정"},
            "zh": {"product_number": "产品编号", "concentration": "浓度", "revision_date": "修订"},
            "vi": {"product_number": "Mã", "concentration": "Nồng độ", "revision_date": "Sửa đổi"},
            "en": {"product_number": "No.", "concentration": "Conc.", "revision_date": "Rev."},
            "km": {"product_number": "លេខ", "concentration": "កំហាប់", "revision_date": "កែប្រែ"},
        }
        facts = {fact.field: re.sub(r"\s+", " ", fact.value).strip() for fact in draft.product_facts}
        if language == "ko" and "concentration" in facts:
            facts["concentration"] = _readable_range_ko(facts["concentration"])
        details = [f"{product_labels[language][field]} {facts[field]}"
                   for field in ("product_number", "concentration", "revision_date") if field in facts]
        # 제품 정보 출처(MSDS 1·3·16항)는 화면 출처 목록에 그대로 남기고, 이 줄에는 번호를 달지 않는다 (김규빈 2026-10-25:
        # "[3] [4] [5]"가 같은 MSDS 를 세 번 가리켜 읽기 어려웠다). 제품명 뒤 괄호에 나머지 항목을 모은다.
        name = facts.get("product_name") or ""
        parts.append(f"{text['basis']}: {name} ({' · '.join(details)})" if details else f"{text['basis']}: {name}")
        closing.append(text["msds_review"])   # 실제 제품과 같은지 확인
    if "conditions_unverified" in reasons:
        closing.append(text["missing_conditions"])
    if any(source.doc_type == DOC_TYPE_LAW for source in sources):
        closing.append(text["law_review"])
    if "effective_date_future" in reasons:
        closing.append(text["future"])
    if "law_version_conflict" in reasons:
        closing.append(text["versions"])
    if closing:
        parts.append(" ".join(closing))
    result = GenerationOutput(
        answer="\n\n".join(parts), sources=sources,
        needs_review=bool(reasons), handoff=False,
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
    _review_reasons: list[str] = PrivateAttr(default_factory=list)

    @property
    def review_reasons(self) -> list[str]:
        """보류 이유 (화면 진단용 응답 머리글에만 쓰고 JSON 필드로는 내보내지 않음)"""
        return list(self._review_reasons)


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
    response = GenerationAPIResponse(
        answer=result.answer,
        sources=sources,
        needs_review=result.needs_review,
        handoff=result.handoff,
        latency_ms=latency_ms,
    )
    response._review_reasons = result.review_reasons
    return response


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


_RANGE_WORDS_KO = {">=": "이상", "≥": "이상", ">": "초과", "<=": "이하", "≤": "이하", "<": "미만"}


def _readable_range_ko(value: str) -> str:
    """MSDS 농도 표기 ">= 45 - < 50" → "45 이상 50 미만". 모양이 다르면 원문 그대로 둔다 (숫자는 바꾸지 않음)."""
    op = r"(>=|<=|≥|≤|>|<)"
    both = re.fullmatch(rf"{op}\s*([\d.,]+)\s*(%?)\s*-\s*{op}\s*([\d.,]+)\s*(%?)", value.strip())
    if both:
        a_op, a, a_pct, b_op, b, b_pct = both.groups()
        pct = a_pct or b_pct   # "%"가 뒤에만 있어도 두 숫자 모두 %
        return f"{a}{pct} {_RANGE_WORDS_KO[a_op]} {b}{pct} {_RANGE_WORDS_KO[b_op]}"
    one = re.fullmatch(rf"{op}\s*([\d.,]+)\s*(%?)", value.strip())
    if one:
        a_op, a, a_pct = one.groups()
        return f"{a}{a_pct} {_RANGE_WORDS_KO[a_op]}"
    return value


GENERATION_RETRIES = int(os.getenv("GENERATION_RETRIES", "1"))   # 0 이면 재시도 안 함
# 검증 시간 초과(verification_unavailable)는 다시 하면 대기 시간만 두 배라 넣지 않는다
RETRYABLE_REASONS = {"claim_mismatch", "invalid_evidence", "invalid_translation", "product_unverified", "invalid_output"}


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
    # LLM 초안은 실행마다 달라서, 같은 질문이 한 번은 검증을 통과하고 한 번은 보류된다 (화면 추천 질문 14개 중 3~5개).
    # 검증 실패로 보류됐으면 한 번 더 생성한다. 다시 만든 초안도 같은 검증을 모두 거치므로 기준은 낮아지지 않는다.
    # "근거 없음"(no_evidence)은 LLM 이 답할 수 없다고 판단한 것이라 다시 묻지 않는다.
    for _ in range(GENERATION_RETRIES):
        if result.sources or not RETRYABLE_REASONS.intersection(result.review_reasons):
            break
        result = generate_answer(question, documents, language=language, mode=mode,
                                 product_id=product_id, topic=topic, structured_llm=structured_llm)
    if {"llm_timeout", "llm_error", "configuration_error"}.intersection(result.review_reasons):
        # Preserve app.main's existing 503 policy without exposing raw errors.
        error = GenerationUnavailable("Generation provider is temporarily unavailable")
        error.reason = result.review_reasons[0]
        raise error
    ids = {doc.metadata.get("chunk_id"): doc.metadata["doc_id"] for doc in documents}
    payload = build_api_response(result, latency_ms=0, doc_id_by_chunk_id=ids)
    if not hits:
        payload._review_reasons = ["retrieval_empty", *result.review_reasons]
    # 다시 RagResponse 로 감싸면 보류 이유(화면 진단용)가 사라진다. 이 하위 형식도 RagResponse 계약을 그대로 만족한다.
    return payload
