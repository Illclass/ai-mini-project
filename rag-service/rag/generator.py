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
from rag.diagnostics import record_failure
from rag.llm import call_llm, RAGConfigurationError, validate_timeout as _valid_timeout
from openai import APITimeoutError
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, field_validator, model_validator
from rag.prompt import (
    LANGUAGES, MODES, TEXT, critical_passages, normalized,
    translation_valid, resolve_mode,
)
from rag.schema import DocType, ENV_LLM_MODEL, DOC_TYPE_LAW, DOC_TYPE_GUIDE, DOC_TYPE_MSDS, TOPIC_LAW, Hit, Source, RagResponse

# 요청 범위 검사

# Generation preflight helpers. No classification API/provider call.
def _reported_incident(question: str) -> bool:
    """Strong positive observation markers outrank a document-location clause.

    This supplements the existing lexical guard, it does not replace it.
    Only positive event clauses are matched; no broad negation removal occurs.
    """
    compact = re.sub(r"\s+", "", question.lower())
    text = normalized(question.lower())
    ko = (
        r"눈에(?:들어|튄|튀었)|피부에(?:닿|묻|튀)|(?:눈|피부|작업복|옷).{0,12}(?:닿았|묻었|튀었|젖었)|흡입했|들이마셨|삼켰|쓰러졌|의식을잃|숨을못|호흡곤란"
        r"|(?:누출|유출|노출)(?:됐|되었|되고있|중)"
        r"|(?:누액|누출|유출)(?:이|가)?(?:보여|보이(?!지않|지못)|보입|있어|있습|있다)"
        r"|(?:배기|환기)(?:가|장치가|설비가)?(?:멈췄|멈추었|정지했|작동하지않|꺼졌)"
        r"|(?:가스|누출|유출).{0,12}(?:경보|알람).{0,12}(?:울렸|울리고|발생했|작동중)"
        r"|(?:이상한|수상한|평소와다른|알수없는).{0,6}냄새(?:가|는)?.{0,6}(?:나는데|납니다|나요|나고있|나기시작)"
    )
    # "眼睛接触/皮肤接触" alone can name an MSDS section. A reported
    # event still needs an occurrence marker, personal exposure, splash,
    # symptom, or other existing positive incident evidence. Never erase
    # a negative clause: a separate actual incident must still take priority.
    zh = (
        r"溅[到入进].{0,8}(?:眼|皮肤)|(?:正在|已经|现在).{0,8}(?:眼睛|皮肤).{0,8}(?:溅|接触)|(?:眼睛|皮肤).{0,8}(?:正在|已经).{0,8}(?:溅|接触)|误吸|误服|吞下|昏倒|(?:我|我们|工人).{0,25}(?:吸入|接触了|溅到|被.{0,8}溅)|(?:溅|接触|吸入).{0,12}(?:了|我的)|呼吸困难|失去意识"
        r"|(?:正在|已经|现在)(?:发生|出现|有|在)?(?:泄漏|渗漏|漏液|漏气|起火|呼吸困难)"
        r"|(?:看见|看到|发现).{0,18}(?:有渗漏|有泄漏|有漏液|正在漏)"
        r"|(?:排气|通风).{0,6}(?:停了|停止了|不工作了)"
        r"|(?:泄漏|漏气|气体).{0,12}(?:报警|警报).{0,8}(?:响了|正在响|触发了)"
        r"|(?:设备|机器|现场).{0,8}(?<!没)有.{0,6}(?:异味|不明气味)"
    )
    vi = (
        r"(?:ban|dinh|vang).{0,15}(?:vao|len).{0,4}(?:mat|da)|hit phai|nuot phai|bat tinh|kho tho|bi phoi nhiem|dang ro ri|bi ro ri|hoa hoan|bi bong|\b(?:toi|chung toi).{0,25}(?:hit phai|bi.{0,12}(?:ban|dinh|bong)|thay.{0,20}(?:ri quanh|ro ri))"
        r"|\b(?:bay gio|dang|da)\s+(?:(?:co|xay ra|bi)\s+)?(?:ro ri|phoi nhiem|kho tho|bat tinh)"
        r"|(?:quat hut|thong gio).{0,8}(?:da dung|ngung hoat dong)"
        r"|(?:ban|dinh|vang).{0,15}(?:vao|len).{0,4}(?:quan ao|ao bao ho|do bao ho).{0,20}(?:cua toi|roi)"
        r"|(?:chuong|bao dong|canh bao).{0,30}(?:ro ri|khi).{0,30}(?:dang keu|da keu|vang len|dang bao)"
        r"|(?<!khong )co mui (?:la|bat thuong|khong ro)"
    )
    en = (
        r"(?:splashed|got).{0,15}(?:eyes|skin)|(?:splash|spill|spatter|got).{0,20}(?:on|onto).{0,10}(?:my )?(?:clothes|clothing|uniform|coverall)|(?:gas|leak).{0,15}(?:alarm|alert).{0,15}(?:went off|is sounding|sounded|triggered|is ringing|going off)|(?:strange|unusual|unknown|weird) (?:smell|odor)|\b(?:i|we)\s+(?:can\s+)?(?:see|saw|notice|noticed)\s+(?:(?:a|the|some)\s+)?(?:liquid\s+)?(?:leak|spill)|\b(?:inhaled|swallowed|unconscious|cannot breathe)\b"
        r"|\b(?:liquid|gas|chemical|acid)\s+(?:is\s+)?(?:leaking|spilling)\b"
        r"|\b(?:exhaust|ventilation).{0,15}(?:has stopped|stopped|is not working|failed)\b"
        r"|\b(?:my|our).{0,15}(?:eyes|skin|clothes).{0,15}(?:splashed|burning|burnt)\b"
    )
    # Khmer grammar is not normalized: preserve combining marks.
    km = r"ចូលភ្នែក|ប្រឡាក់ស្បែក|ប៉ះស្បែក|ស្រូបចូល|សន្លប់|ពិបាកដកដង្ហើម|(?:ឥឡូវនេះ|ខ្ញុំឃើញ|កំពុង).{0,35}(?:លេចធ្លាយ|ប្រឡាក់|ពិបាកដកដង្ហើម|សន្លប់)"
    return bool(re.search(ko, compact) or re.search(zh, question)
                or re.search(vi, text) or re.search(en, question.lower())
                or re.search(km, question))


def _source_location_question(question: str) -> bool:
    """Explicit document locator, never an override of a reported incident.

    Mixed 'where is the SOP, and tell me the steps now' is not reference-only.
    Mere future/conditional discussion is not evidence of a current incident.
    """
    if _reported_incident(question):
        return False
    compact = re.sub(r"\s+", "", question.lower())
    text = normalized(question.lower())
    locator = (
        re.search(r"어디(?:서|에).{0,20}(?:확인|찾|나와)|어느.{0,12}(?:자료|문서|지침|항)|어떤(?:자료|문서|지침)|(?:자료|문서|지침).{0,12}(?:위치|찾아|찾을)", compact)
        or re.search(r"在哪里.{0,15}(?:查|确认|找)|(?:哪个|什么|哪些).{0,10}(?:文件|资料|章节)|(?:查阅|查找).{0,20}(?:文件|资料)|(?:指出|指明|查找|查阅|确认).{0,100}(?:所在的?(?:章节|位置)|章节(?:和|及)出处)", question)
        or re.search(r"\b(?:xem|tim).{0,160}\bo dau\b|\b(?:tai lieu nao|muc nao)\b", text)
        or re.search(r"\bwhere\b.{0,30}\b(?:find|read|check|locate)\b|\bwhich\s+(?:document|documents|manual|section|sections)\b", question.lower())
        or ("នៅឯណា" in question and any(term in question for term in ("ឯកសារ", "នីតិវិធី", "ព័ត៌មាន")))
    )
    if not locator:
        return False
    # Explicit execution, approval and personal legal decisions remain deferred.
    decision_or_execution = (
        re.search(r"(?:보호구|장갑).{0,8}없이.{0,15}(?:작업|취급)|(?:우리|저희|회사|대표|내가|제가|당사|이사고).{0,35}(?:법적책임|유죄|무죄|처벌받|책임져|책임을져)|무조건처벌|누가.{0,10}책임|(?:법적|형사|민사)책임|(?:승인|허가)해|(?:작업|가동|진입).{0,12}해도(?:돼|되)|(?:순서|비율|방법|절차)(?:를|을)?(?:알려|가르쳐|설명해)|(?:어떻게|무엇을)섞|(?:희석|중화|혼합)(?:해줘|해주세요)", compact)
        or re.search(r"不戴.{0,10}(?:手套|防护)|(?:我们|公司|我).{0,20}(?:有罪|无罪|处罚|负责|承担法律责任)|(?:法律责任|刑事责任|民事责任)|(?:批准|允许).{0,10}(?:作业|开工)|(?:告诉|教我|解释).{0,20}(?:步骤|比例|稀释方法|中和方法)", question)
        or re.search(r"khong deo.{0,15}(?:gang|bao ho)|(?:toi|cong ty|chung toi).{0,30}(?:chiu trach nhiem|bi phat|co toi)|\b(?:phe duyet|cho phep|trach nhiem phap ly|huong dan pha loang|ty le pha|huong dan trung hoa)\b", text)
        or re.search(r"\b(?:am i|are we|is our|who is).{0,35}(?:liable|guilty|legally responsible)|\b(?:approve|authorize|legally liable|safe to work|tell me (?:the )?(?:steps|ratio)|give me (?:the )?steps|how (?:do i|to) (?:mix|dilute|neutralize))\b", question.lower())
        or any(term in question for term in ("អនុម័ត", "សមាមាត្រ", "ប្រាប់ជំហាន"))
    )
    return not decision_or_execution


def is_emergency(question: str) -> bool:
    if _reported_incident(question):
        return True
    if _source_location_question(question):
        return False

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
    # 부정 표현 전체를 제거하지 않는다. 같은 질문에 실제 사고가 함께 있을 수 있다.
    # 어휘 규칙이므로 모든 표현이나 문맥을 이해하는 분류기는 아니다.
    return bool(
        re.search(ko, compact) or re.search(ko_incident, compact)
        or re.search(zh, text) or re.search(zh_incident, text)
        or re.search(vi, normalized(text)) or re.search(vi_incident, normalized(text))
        or re.search(en, text) or re.search(en_incident, text)
        or re.search(km, question)
    )

def is_prohibited_request(question: str) -> bool:
    if _source_location_question(question):
        return False
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
    if _source_location_question(question):
        return False
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
    kind: Literal["legal_obligation", "recommendation", "information"] = Field(description="Classify the claim, not the source document. legal_obligation ONLY for an explicit mandatory action in a law quote. Definitions, thresholds, meanings, and reference locations are information, even when doc_type=law. Technical MSDS requirements are information; actual advice is recommendation.")
    text: str = Field(description="One source action per sentence, preserving its force. Never weaken a prohibition/requirement to advice or recommendation, including in a Korean intermediate draft. Supplier contact is not PPE selection. A label/reference location is information, not a new must/shall requirement. For handling/storage/PPE actions use an impersonal subject such as the document, NOT a product name or product placeholder. Product identity is rendered separately from product_facts. Describe label/reference locations as information without adding must/shall.")
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


class ProductFactSelection(BaseModel):
    """Internal reference to a server-sliced source span, never an API field."""
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_id: str
    value: str = Field(description="Verbatim value of this field from the selected source span. Concentration is ONLY its numeric range/unit, never the CAS number, ingredient name, or whole table row. Preserve the complete product name, product number and original revision-date format.")


class ClaimDraft(BaseModel):
    """Internal first stage; warnings have a separate bounded translation step."""
    model_config = ConfigDict(extra="forbid", strict=True)
    supported: bool
    statements: list[EvidenceStatement]
    product_facts: list[ProductFactSelection] = Field(description="Select all four available MSDS identity fields from PRODUCT_EVIDENCE_CANDIDATES_JSON by evidence_id and verbatim value. Never write or reconstruct quotes. Return [] for non-MSDS.")


class DocumentLocationDraft(BaseModel):
    """Private ID selection, so a location answer cannot contain model prose."""
    model_config = ConfigDict(extra="forbid", strict=True)
    supported: bool
    location_ids: list[str] = Field(max_length=4, description="Only actual location_ids covering the requested topic. No duplicates or invented IDs.")
    product_facts: list[ProductFactSelection]


class DocumentLocationGenerationError(ValueError):
    """Unknown or duplicate heading selection; no model text can replace it."""


def _resolve_product_selections(selections, candidates):
    by_id = {item["evidence_id"]: item for item in candidates}
    facts = []
    for selection in selections:
        evidence = by_id.get(selection.evidence_id)
        if evidence is None:
            raise ProductEvidenceGenerationError("Unknown product evidence reference")
        facts.append(ProductFact(field=evidence["field"], value=selection.value,
                                citations=[Citation(chunk_id=evidence["chunk_id"], quote=evidence["quote"])]))
    return facts


class TranslationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    translations: list[CriticalTranslation]


class TranslationGenerationError(ValueError):
    """Private, sanitized failure of complete translation assembly."""


class ProductEvidenceGenerationError(ValueError):
    """Unknown product evidence reference; no generated quote may replace it."""


class _DocumentGenerator:
    """Production coordinator; injected providers exercise this same path in tests.

    A provider belongs to one generate_answer session. Across both draft attempts
    it permits 12 model calls, one body-translation correction, one warning
    translation correction, and 60s composition.
    Independent verification runs afterward with its existing per-call timeout.
    No request-global cache, source mutation, or reconstructed numbers/quotes.
    """
    def __init__(self, model, timeout_seconds, *, factory=None, clock=None):
        import time
        self.model, self.timeout = model, timeout_seconds
        self.factory = factory or llm.build_structured_llm
        self.clock = clock or time.monotonic
        self.started = None
        self.calls = 0
        self.correction_used = False
        self.body_correction_used = False

    def _call(self, schema, messages):
        if self.started is None:
            self.started = self.clock()
        remaining = 60.0 - (self.clock() - self.started)
        if remaining <= 0:
            raise TimeoutError("Generation composition deadline exceeded")
        if self.calls >= 12:
            raise TranslationGenerationError("Generation call budget exceeded")
        self.calls += 1
        provider = self.factory(schema, self.model, timeout_seconds=min(self.timeout, remaining))
        raw = provider.invoke(messages)
        if self.clock() - self.started > 60.0:
            raise TimeoutError("Generation composition deadline exceeded")
        return schema.model_validate(raw)

    def invoke(self, messages):
        context = prompt.message_json(messages, "GENERATION_CONTEXT_JSON")
        language = context["language"]
        docs = [Document(**d) for d in prompt.message_json(messages, "UNTRUSTED_RETRIEVED_DOCUMENTS_JSON")]
        original = {d.metadata["chunk_id"]: d for d in docs}
        candidates = prompt.product_evidence_candidates(docs)
        question = prompt.message_json(messages, "QUESTION_JSON")["question"]
        if any(d.metadata.get("doc_type") == DOC_TYPE_MSDS for d in docs) and prompt.msds_location_only_question(question):
            locations = prompt.msds_location_candidates(docs)
            if not locations:
                return EvidenceDraft(supported=False, statements=[])
            selection = self._call(DocumentLocationDraft, prompt.build_location_selection_messages(messages, locations))
            known = {item["location_id"]: item for item in locations}
            if len(selection.location_ids) != len(set(selection.location_ids)) or any(cid not in known for cid in selection.location_ids):
                raise DocumentLocationGenerationError("Unknown or duplicate document location")
            facts = _resolve_product_selections(selection.product_facts, candidates)
            statements = [EvidenceStatement(kind="information", text=prompt.msds_location_text(known[cid]["section_no"], language),
                            citations=[Citation(**c) for c in known[cid]["citations"]], conditions=[])
                          for cid in selection.location_ids]
            return EvidenceDraft(supported=selection.supported, statements=statements, product_facts=facts)
        selected_claim = self._call(ClaimDraft, prompt.build_claim_stage_messages(messages))
        facts = _resolve_product_selections(selected_claim.product_facts, candidates)
        claim = EvidenceDraft(supported=selected_claim.supported, statements=selected_claim.statements,
                              product_facts=facts, critical_translations=[])
        metadata = {cid: SourceMetadata.model_validate(d.metadata) for cid, d in original.items()}
        if any((_verify_citations(s.citations, original) and _weakens_requirement(s.text)
                and any(_source_technical_requirement(c, metadata) for c in s.citations))
                or any(c.chunk_id in original and prompt.response_reference_only(s.text, original[c.chunk_id])
                       for c in s.citations)
               for s in claim.statements):
            # Let the normal bounded draft repair diagnose the source-language
            # error. Translation must not conceal an already weakened claim.
            return claim
        claim = self._correct_body_language(claim, original, language)
        assembled = claim.model_copy(deep=True)
        if language == "ko" or not claim.supported or not claim.statements:
            return assembled
        selected = {c.chunk_id for s in claim.statements for c in s.citations}
        selected.update(c.chunk_id for s in claim.statements for condition in s.conditions for c in condition.citations)
        selected.update(c.chunk_id for f in claim.product_facts for c in f.citations)
        required = {pid: pair for pid, pair in prompt.critical_passages(docs).items()
                    if pair[0] in selected or original[pair[0]].metadata.get("doc_type") == DOC_TYPE_MSDS}
        tokens = prompt.product_name_tokens(docs)
        # Translation sees a protected view only. Validation below always uses
        # the unchanged original passage, never this view as source evidence.
        entries = [{"passage_id": pid, "chunk_id": cid,
                    "original": _protect_product_text(quote, tokens), "product_name_tokens": tokens}
                   for pid, (cid, quote) in required.items()]
        # Small complete units, never split a warning/condition to fit a limit.
        batches, batch, size = [], [], 0
        for entry in entries:
            nbytes = len(entry["original"].encode("utf-8"))
            if nbytes > 8000:
                raise TranslationGenerationError("Complete warning exceeds translation budget")
            if batch and (len(batch) == 4 or size + nbytes > 8000):
                batches.append(batch); batch, size = [], 0
            batch.append(entry); size += nbytes
        if batch:
            batches.append(batch)
        for batch in batches:
            translated = None
            for attempt in range(2):
                try:
                    result = self._call(TranslationBatch, prompt.build_translation_stage_messages(batch, language, correction=bool(attempt)))
                    result = result.model_copy(update={"translations": [item.model_copy(update={
                        "text": _restore_translation_names(item.text, tokens)}) for item in result.translations]})
                    ids = [item.passage_id for item in result.translations]
                    if len(ids) != len(batch) or set(ids) != {entry["passage_id"] for entry in batch}:
                        raise TranslationGenerationError("Missing, duplicate or unknown translation ID")
                    for item in result.translations:
                        cid, quote = required[item.passage_id]
                        if not _translation_locally_valid(quote, item.text, language, original[cid], original, claim.product_facts):
                            raise TranslationGenerationError("Warning translation failed local validation")
                    translated = result.translations
                    break
                except (TranslationGenerationError, ValidationError, OutputParserException):
                    if attempt or self.correction_used:
                        raise TranslationGenerationError("Warning translation could not be verified") from None
                    self.correction_used = True
            assembled.critical_translations.extend(translated)
        return assembled

    def _correct_body_language(self, claim, originals, language):
        """Repair mixed-script prose once, without rewriting evidence or facts.

        The complete local and semantic gates still run on the assembled result.
        Failed or repeated repair never grants approval or removes a statement.
        """
        if language == "ko" or not claim.supported:
            return claim
        # The translator receives opaque source-derived product identifiers,
        # even when the first model failed to use the requested placeholders.
        tokens = prompt.product_name_tokens(list(originals.values()))
        claim = claim.model_copy(update={"statements": [s.model_copy(update={
            "text": _protect_product_text(s.text, tokens), "conditions": [
                c.model_copy(update={"text": _protect_product_text(c.text, tokens)}) for c in s.conditions]
        }) for s in claim.statements]})
        names = tuple(f.value for f in claim.product_facts if f.field == "product_name")
        entries, targets = [], {}
        for index, statement in enumerate(claim.statements):
            values = [(f"s{index}", statement)] + [
                (f"s{index}.c{position}", condition) for position, condition in enumerate(statement.conditions)]
            for pid, value in values:
                if not _verify_citations(value.citations, originals):
                    continue  # A translator must not repair unsupported evidence.
                terms = names + _cited_ingredient_terms(value.citations, originals)
                if not translation_valid("", value.text, language, preserved_terms=terms):
                    entries.append({"passage_id": pid, "original": value.text,
                                    "citations": [c.model_dump() for c in value.citations]})
                    targets[pid] = (value, terms)
        if not entries:
            return claim
        for attempt in range(2):
            try:
                result = self._call(TranslationBatch, prompt.build_body_language_messages(entries, language, correction=bool(attempt)))
                ids = [item.passage_id for item in result.translations]
                if len(ids) != len(targets) or set(ids) != set(targets):
                    raise TranslationGenerationError("Body translation IDs could not be verified")
                corrected = {}
                for item in result.translations:
                    value, terms = targets[item.passage_id]
                    if not translation_valid(value.text, item.text, language, preserved_terms=terms,
                                             source_identifiers=_cited_cas_identifiers(value.citations, originals)):
                        raise TranslationGenerationError("Body translation could not be verified")
                    metadata = {cid: SourceMetadata.model_validate(d.metadata) for cid, d in originals.items()}
                    if (not _identities_preserved(value.text, item.text, names)
                            or (_weakens_requirement(item.text) and any(
                                _source_technical_requirement(c, metadata) for c in value.citations))):
                        raise TranslationGenerationError("Body identity or source force was changed")
                    corrected[item.passage_id] = item.text
                break
            except (TranslationGenerationError, ValidationError, OutputParserException):
                if attempt or self.body_correction_used:
                    raise TranslationGenerationError("Body translation could not be verified") from None
                self.body_correction_used = True
        statements = []
        for index, statement in enumerate(claim.statements):
            conditions = [condition.model_copy(update={"text": corrected.get(f"s{index}.c{position}", condition.text)})
                          for position, condition in enumerate(statement.conditions)]
            statements.append(statement.model_copy(update={"text": corrected.get(f"s{index}", statement.text),
                                                            "conditions": conditions}))
        return claim.model_copy(update={"statements": statements})


def _translation_locally_valid(original, value, language, document, originals, facts):
    citation = [Citation(chunk_id=document.metadata["chunk_id"], quote=original)]
    identifiers = _cited_cas_identifiers(citation, originals)
    names = tuple(f.value for f in facts if f.field == "product_name")
    return (not _unsafe_critical_translation(value, original)
            and _identities_preserved(original, value, names)
            and translation_valid(original, value, language,
                source_doc_type=document.metadata.get("doc_type"), source_identifiers=identifiers,
                preserved_terms=names + _cited_ingredient_terms(citation, originals))
            and _quantities_supported(value, citation, source_identifiers=identifiers))


def _identities_preserved(original, translated, names=()):
    """Literal product identifiers and opaque tokens cannot be translated away."""
    return (all(name in translated for name in names if name in original)
            and sorted(re.findall(r"CB_PRODUCT_NAME_\d+", original))
                == sorted(re.findall(r"CB_PRODUCT_NAME_\d+", translated)))


def _protect_product_text(text, tokens):
    parts = re.split(r"(CB_PRODUCT_NAME_\d+)", text)
    for index in range(0, len(parts), 2):
        for token, name in sorted(tokens.items(), key=lambda pair: len(pair[1]), reverse=True):
            parts[index] = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])",
                                  lambda match: token, parts[index])
    return "".join(parts)


def _restore_translation_names(text, tokens):
    return re.sub(r"CB_PRODUCT_NAME_\d+", lambda match: tokens.get(match.group(), match.group()), text)



class GenerationOutput(BaseModel):
    """Generation-only result; review diagnostics are private, not API fields."""
    model_config = ConfigDict(extra="forbid", strict=True)
    answer: str
    sources: list[SourceMetadata]
    needs_review: bool
    handoff: bool
    _review_reasons: list[str] = PrivateAttr(default_factory=list)
    _review_message: str = PrivateAttr(default="")
    _verification_failures: list[dict] = PrivateAttr(default_factory=list)

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
    return _DocumentGenerator(model, _valid_timeout(timeout_seconds))


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
    if prompt.hazardous_response_action(text):
        return True
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


def _canonicalize_citation_whitespace(draft: EvidenceDraft, originals: dict[str, Document]) -> EvidenceDraft:
    """Restore one literal contiguous source span; no fuzzy/content repair.

    Whitespace must exist at exactly the same token boundaries in both strings.
    Unknown IDs, changed punctuation/Unicode/numbers and ambiguous matches remain
    untouched so the existing exact citation validator rejects them.
    """
    def canonical(citation):
        document = originals.get(citation.chunk_id)
        if document is None or not citation.quote.strip() or citation.quote in document.page_content:
            return citation
        pattern = "".join(r"\s+" if part.isspace() else re.escape(part)
                          for part in re.split(r"(\s+)", citation.quote) if part)
        # Lookahead detects overlapping candidates too; never select the first
        # of repeated source spans based on order or semantic similarity.
        matches = list(re.finditer("(?=(" + pattern + "))", document.page_content))
        if len(matches) != 1:
            return citation
        return citation.model_copy(update={"quote": matches[0].group(1)})

    statements = [statement.model_copy(update={
        "citations": [canonical(c) for c in statement.citations],
        "conditions": [condition.model_copy(update={
            "citations": [canonical(c) for c in condition.citations]})
            for condition in statement.conditions],
    }) for statement in draft.statements]
    facts = [fact.model_copy(update={"citations": [canonical(c) for c in fact.citations]})
             for fact in draft.product_facts]
    return draft.model_copy(update={"statements": statements, "product_facts": facts})


def _verify_citations(citations: list[Citation], originals: dict[str, Document]) -> bool:
    return bool(citations) and all(
        citation.chunk_id in originals and bool(citation.quote.strip())
        and citation.quote in originals[citation.chunk_id].page_content
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


def _quantities_supported(text: str, citations: list[Citation], *, source_identifiers=()) -> bool:
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
    number = r"[+-]?\d+(?:[.,]\d+)?"
    unit = r"ppm|ppb|mg/m3|μg/m3|g/l|mg/l|°c|°f|%|kg|mg|μg|ml|l|g"
    measurements = rf"({number})\s*({unit})(?![a-z])"
    dates = r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
    return all(
        set(re.findall(pattern, claim)).issubset(set(re.findall(pattern, evidence)))
        for pattern in (number, measurements, dates)
    )


def _with_section_reference(text, citations, originals):
    """Add only a literal same-MSDS heading for an explicit section reference.

    No value/number is changed. Metadata alone cannot supply a heading. The
    independent verifier receives the added exact quote as well.
    """
    value = text.translate(prompt.KHMER_DIGITS)
    patterns = (r"제?\s*([0-9]{1,2})\s*(?:번\s*)?(?:항|섹션)",
                r"(?:section|part|phần|mục|ផ្នែក)\s*([0-9]{1,2})\b",
                r"第\s*([0-9]{1,2})\s*(?:节|項|项|章)")
    numbers = {int(n) for pattern in patterns for n in re.findall(pattern, value, re.I)}
    result = list(citations)
    for citation in citations:
        doc = originals.get(citation.chunk_id)
        if doc is None or doc.metadata.get("doc_type") != DOC_TYPE_MSDS:
            continue
        no = doc.metadata.get("msds_section_no")
        if type(no) is not int or no not in numbers:
            continue
        lines = [line.strip() for line in doc.page_content.splitlines()
                 if re.fullmatch(r"\s*" + str(no) + r"[.]\s+[^\r\n]+", line)]
        if len(lines) != 1:
            continue
        heading = lines[0]
        if not any(c.chunk_id == citation.chunk_id and heading in c.quote for c in result):
            result.append(Citation(chunk_id=citation.chunk_id, quote=heading))
    return result


def _verify_draft_support(question, draft, originals, required, translated, *,
                          language, as_of, model, timeout_seconds) -> tuple[str | None, list[dict]]:
    """Verify every rendered claim/condition/translation once, fail closed.

    Returns a private reason and bounded failed-claim IDs, or (None, []).
    This probabilistic gate is not a guarantee of factual or workplace safety.
    """
    claims = []
    for index, statement in enumerate(draft.statements):
        if any(prompt.response_reference_only(statement.text, originals[c.chunk_id])
               for c in statement.citations):
            return "invalid_evidence", []
        claims.append({"claim_id": f"s{index}", "kind": statement.kind,
                       "text": prompt.render_statement(statement, originals, language),
                       "conditions": [condition.text for condition in statement.conditions],
                       "citations": [c.model_dump() for c in _with_section_reference(statement.text, statement.citations, originals)]})
        for position, condition in enumerate(statement.conditions):
            if any(prompt.response_reference_only(condition.text, originals[c.chunk_id])
                   for c in condition.citations):
                return "invalid_evidence", []
            claims.append({"claim_id": f"s{index}.c{position}", "kind": "condition",
                           "text": condition.text,
                           "citations": [c.model_dump() for c in _with_section_reference(condition.text, condition.citations, originals)]})
    warning_claims = []
    for index, (pid, (cid, original)) in enumerate(required.items()):
        rendered = original if language == "ko" else translated[pid]
        if (prompt.response_reference_only(original, originals[cid])
                or prompt.response_reference_only(rendered, originals[cid])):
            return "invalid_evidence", []
        # Korean originals are rendered claims too. A verbatim quote still
        # needs scope/audience/output-policy verification, not execution approval.
        warning_claims.append({"claim_id": f"t{index}",
                       "kind": "source_warning" if language == "ko" else "translation",
                       "text": prompt.render_source_warning(rendered, language),
                       "citations": [{"chunk_id": cid, "quote": original}]})
    try:
        verifier = build_verification_llm(model, timeout_seconds=timeout_seconds)
        for group, builder in ((claims, prompt.build_verification_messages),
                               (warning_claims, prompt.build_warning_verification_messages)):
            if not group:
                continue
            raw = verifier.invoke(builder(question, group, list(originals.values()),
                                          language=language, as_of=as_of))
            result = EvidenceVerification.model_validate(raw)
            expected = {claim["claim_id"] for claim in group}
            ids = [item.claim_id for item in result.assessments]
            if len(ids) != len(expected) or set(ids) != expected:
                return "verification_unavailable", []
            if any(item.verdict != "supported" for item in result.assessments):
                return "claim_mismatch", [{"claim_id": item.claim_id, "verdict": item.verdict} for item in result.assessments if item.verdict != "supported"]
    except Exception as exc:
        record_failure(exc, stage="verification")
        return "verification_unavailable", []
    return None, []



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


def _force_wording(text: str) -> str:
    """A reference to a recommendation's scope is not advice about an action."""
    return re.sub(r"권고\s*사항(?:은|이)(?=[^.!?]*적용)", "문서의 사항은", text)


def _weakens_requirement(text: str) -> bool:
    """Advice is not an adequate rendering of a source requirement, in all five languages."""
    wording = normalized(_force_wording(text))
    # A single negated "optional" affirms a requirement. Keep another weakening
    # elsewhere in the claim, and conservatively reject double negation.
    wording = re.sub(
        r"\bnot\s+optional\b",
        lambda match: match[0] if re.search(r"\b(?:not|never|no)\s*$", wording[:match.start()]) else " ",
        wording, flags=re.I,
    )
    return bool(re.search(
        r"recommend|suggest|optional|\badvis(?:e|es|ed|ing|able)\b|建议|推荐|可选|khuyen|tuy chon|권장|권고|선택 사항",
        wording, re.I)) or bool(re.search(
        r"ណែនាំ(?:ឱ្យ|ឲ្យ|មិនឱ្យ|មិនឲ្យ)|ជាជម្រើស|គួរតែ", text))


def _has_duty_assertion(text: str) -> bool:
    """Conservative lexical check; not a legal entailment classifier."""
    # Vietnamese negative copula means "is not", not "must". Remove only
    # that pair; a separate phải/must/legal duty in the same text remains.
    text = re.sub(r"\bkhông\s+phải\b", " ", text, flags=re.I)
    # In exposure verbs phải marks an accidental encounter, not an obligation.
    # Keep a separate affirmative phải/must elsewhere in the sentence.
    text = re.sub(r"\b(hít|nuốt|chạm|gặp|mắc)\s+phải\b", r"\1 ", text, flags=re.I)
    return bool(re.search(
        r"하\s*여야|되\s*어야|이\s*어야|있\s*어야|없\s*어야|해\s*야\s*(?:합|함|한|할|해|되|만)|반드시|"
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
    quote = _force_wording(citation.quote)
    # Optional/advisory wording cannot justify strengthening the source action.
    if re.search(r"권장|권고|추천|불필요|필요\s*(?:가\s*)?없|필요는\s*없|선택적|선택\s*사항|"
                 r"않아도|(?:할|하는)\s*것이\s*좋", quote):
        return False
    if _has_duty_assertion(quote) or re.search(
        r"하\s*(?:시오|십시오)|[가-힣]+(?:으십시오|십시오|하시오|으시오)|하지\s*마(?:시오|십시오|세요)|"
        r"[가-힣]*(?:할|말|을)\s*것(?=\s*(?:[.!?]|$))|금지|필수", quote, re.I | re.M,
    ):
        return True
    # Procedural Korean declaratives and inflected imperative endings are
    # technical requirements, never proof of a legal duty or claim meaning.
    if re.search(r"(?:확인|설치|보관|저장|기재|사용|준수|선정|점검|분리|유지|확보|관리|비치|제공|작성|연락|교육|검토|착용)\s*한다(?=\s*(?:[.!?]|$))|"
                 r"(?:잠글|벗을)\s*것(?=\s*(?:[.!?]|$))", quote, re.M):
        return True
    # MSDS section 8 also uses nominal instructions such as "눈 보호: ... 도구 사용."
    # This is a document requirement, not a claim of legal duty. Limit it to
    # an actual PPE heading and action; advice/optional sources were rejected
    # above, and exact citations plus independent semantic verification remain.
    if (metadata[citation.chunk_id].doc_type == DOC_TYPE_MSDS
            and metadata[citation.chunk_id].msds_section_no == 8
            and re.search(r"(?:눈|손|호흡기|신체|피부)\s*보호\s*[:：]", quote)
            and re.search(r"(?:보호용\s*도구|보안경|안전안경|보호장갑|보호복|호흡기).*(?:사용|착용)\s*[.]?\s*$", quote, re.S)):
        return True
    return bool(
        metadata[citation.chunk_id].doc_type == DOC_TYPE_MSDS
        and re.search(r"(?:신체|피부)\s*(?:[/·]\s*(?:신체|피부))?\s*보호\s*[:：]", quote)
        and re.search(r"보호복|보호의|보호장갑|보안경", quote)
        and not re.search(r"권장|권고|추천|불필요|필요\s*없|착용하지\s*않아도|선택적", quote)
    )


def _claims_legal_status(text: str) -> bool:
    """Conservative legal-status wording guard, never an entailment classifier.

    Negative legal-status disclaimers also remain explicit status claims here;
    classification repair must not reinterpret or remove them.
    """
    return bool(re.search(
        r"법령|법률|법적|법정|법규|법상|시행령|시행규칙|조례|법에\s*(?:따라|의해)|법으로|"
        r"법\s*(?:제?\s*\d+\s*조|[에의상])|"
        r"法律|法定|依法|法规|法規|"
        r"\b(?:legal|legally|law|by-?law|statutory|statute|legislation|regulatory|regulations?)\b|"
        r"\b(?:phap\s+luat|phap\s+ly|theo\s+luat|luat)\b",
        normalized(text), re.I,
    )) or bool(re.search(r"ច្បាប់|អនុក្រឹត្យ|បទប្បញ្ញត្តិ|ក្រម", text))


def _with_exact_ppe_context(draft, originals, metadata):
    """Supply an omitted, unique eye-protection instruction as a second quote.

    The model's literal PPE quotation must fit inside the same actual MSDS8
    subsection. Keep that noun quote unchanged; never stitch over a PDF footer.
    No action is invented, and all citations and claims are verified afterwards.
    Advice/optional/ambiguous/other-subsection contexts stay blocked.
    """
    statements = []
    for statement in draft.statements:
        citations = list(statement.citations)
        if _has_duty_assertion(statement.text):
            for citation in statement.citations:
                meta = metadata[citation.chunk_id]
                doc = originals[citation.chunk_id]
                quote = citation.quote
                if (meta.doc_type != DOC_TYPE_MSDS or meta.msds_section_no != 8
                        or not re.search(r"안전안경|보안경", quote)
                        or doc.page_content.count(quote) != 1):
                    continue
                body = doc.page_content
                headings = list(re.finditer(r"(?m)^\s*눈\s*보호\s*[:：]", body))
                if len(headings) != 1:
                    continue
                start = headings[0].start()
                next_heading = re.search(r"(?m)^\s*[^\n:：]{1,25}보호(?:\s*[:：]|[ \t]*$)", body[headings[0].end():])
                end = headings[0].end() + next_heading.start() if next_heading else len(body)
                if not start <= body.index(quote) < body.index(quote) + len(quote) <= end:
                    continue
                region = body[start:end]
                # A later exception in the SAME subsection can qualify the
                # earlier instruction. Do not infer applicability across it.
                if re.search(r"권장|권고|추천|선택|않아도|불필요|필요\s*없|금지|하지\s*마|다만|경우|조건|제외|예외|한하여|\b(?:only|unless|except|optional|not)\b", region, re.I):
                    continue
                context = re.match(r"[\s\S]{1,500}?(?:보호용\s*도구\s*사용|안전안경\s*착용)[.]", region)
                if context is None:
                    continue
                addition = Citation(chunk_id=citation.chunk_id, quote=context[0])
                if (_verify_citations([addition], originals)
                        and _source_technical_requirement(addition, metadata)
                        and addition not in citations):
                    citations.append(addition)
        statements.append(statement.model_copy(update={"citations": citations}))
    return draft.model_copy(update={"statements": statements})


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
        elif statement.kind == "legal_obligation":
            all_citations = list(statement.citations) + [
                c for condition in statement.conditions for c in condition.citations]
            technical_only = (
                _verify_citations(statement.citations, originals)
                and all(_verify_citations(condition.citations, originals)
                        for condition in statement.conditions)
                and all(metadata[c.chunk_id].doc_type in (DOC_TYPE_GUIDE, DOC_TYPE_MSDS)
                        for c in all_citations)
                and all(_source_technical_requirement(c, metadata) for c in statement.citations)
            )
            if (technical_only and not _claims_legal_status(statement.text)
                    and not any(_claims_legal_status(c.text) for c in statement.conditions)):
                # Correct a category-only model error from verified document
                # metadata. Never rewrite text, evidence, strength or conditions.
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
    labels = prompt.PRODUCT_FACT_LABELS
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
        if fact.field == "concentration" and any(
            identifier in fact.value for identifier in _cited_cas_identifiers(fact.citations, originals)
        ):
            return False  # A CAS cell is not part of the concentration cell.
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



def _restore_product_name_tokens(draft: EvidenceDraft, documents) -> EvidenceDraft | None:
    """Bind names to exact identity evidence for the same retrieved product.

    The caller has verified product_facts first. A statement/condition may cite
    the product's PPE/storage chunk without repeating its name; attach the actual
    identity fact citations rather than inventing evidence in that chunk. Every
    original citation must still be exact MSDS evidence with the same nonempty
    product_id. Critical translations remain bound to their single passage.
    Full claim, quantity, and independent semantic checks still run afterwards.
    """
    originals = {doc.metadata.get("chunk_id"): doc for doc in documents}
    name_facts = {fact.value: fact for fact in draft.product_facts if fact.field == "product_name"}
    tokens = {key: value for key, value in prompt.product_name_tokens(documents).items() if value in name_facts}

    def restore(text, citations, *, bind_identity=False):
        bound = list(citations)

        def replace(match):
            token = match[0]
            if token not in tokens:
                raise ValueError("Unverified product name placeholder")
            name = tokens[token]
            if not bind_identity:
                if not any(name in c.quote for c in citations):
                    raise ValueError("Name absent from original warning")
                return name
            fact = name_facts[name]
            if not _verify_citations(fact.citations, originals) or not _verify_citations(citations, originals):
                raise ValueError("Invalid identity or claim citation")
            joined = list(citations) + list(fact.citations)
            product_ids = {originals[c.chunk_id].metadata.get("product_id") for c in joined}
            if (any(originals[c.chunk_id].metadata.get("doc_type") != DOC_TYPE_MSDS for c in joined)
                    or len(product_ids) != 1
                    or any(not isinstance(value, str) or not value.strip() for value in product_ids)):
                raise ValueError("Identity and claim must share a verified MSDS product")
            identity = [c for c in fact.citations if name in c.quote]
            if not identity:
                raise ValueError("Name absent from verified identity citations")
            if not any(name in c.quote for c in bound):
                for citation in identity:
                    if not any(c.chunk_id == citation.chunk_id and c.quote == citation.quote for c in bound):
                        bound.append(citation.model_copy(deep=True))
            return name

        text = re.sub(r"(?<![A-Za-z0-9_])CB_PRODUCT_NAME_[A-Za-z0-9_]+", replace, text)
        if "CB_PRODUCT_NAME_" in text:
            raise ValueError("Unresolved product name placeholder")
        return text, bound

    try:
        statements = []
        for statement in draft.statements:
            conditions = []
            for condition in statement.conditions:
                restored, citations = restore(condition.text, condition.citations, bind_identity=True)
                conditions.append(condition.model_copy(update={"text": restored, "citations": citations}))
            restored, citations = restore(statement.text, statement.citations, bind_identity=True)
            statements.append(statement.model_copy(update={
                "text": restored, "citations": citations, "conditions": conditions}))
        passages = critical_passages(documents)
        translations = []
        for item in draft.critical_translations:
            pair = passages.get(item.passage_id)
            citations = [Citation(chunk_id=pair[0], quote=pair[1])] if pair else []
            restored, _ = restore(item.text, citations)
            translations.append(item.model_copy(update={"text": restored}))
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


def _draft_repair_feedback(raw, documents, *, reason, language, question=""):
    """Private, bounded diagnostics for one correction; never validation approval.

    Uses the same local helpers only to identify fields requiring attention.
    Missing diagnostics never make a draft valid: the full pipeline and separate
    semantic verifier run again. Original/source/draft text remains untrusted.
    """
    issues = []

    def issue(path, code, **detail):
        if len(issues) < 32:
            issues.append({"path": path, "code": code, **detail})

    try:
        draft = EvidenceDraft.model_validate(raw)
    except (ValidationError, TypeError) as error:
        # Reuse the first parse error; diagnostic collection must not parse the
        # same invalid draft again or expose provider text/input values.
        if isinstance(error, ValidationError):
            for item in error.errors()[:32]:
                issue(list(item["loc"]), "schema_" + item["type"])
        else:
            issue([], "schema_invalid_type")
        return {"validation_failure": reason, "issues": issues}
    try:
        originals = {doc.metadata["chunk_id"]: doc for doc in documents}
        metadata = {cid: SourceMetadata.model_validate(doc.metadata) for cid, doc in originals.items()}
        draft = _canonicalize_citation_whitespace(draft, originals)
        restored = _restore_product_name_tokens(draft, documents)
        if restored is None:
            issue([], "product_name_token_unverified")
        else:
            draft = restored
        draft = _align_technical_kinds(draft, originals, metadata)
        names = tuple(f.value for f in draft.product_facts if f.field == "product_name")
        selected = set()

        def citations(path, values):
            if not values:
                issue(path, "citations_missing")
            valid = True
            for index, citation in enumerate(values):
                location = path + [index]
                if citation.chunk_id not in originals:
                    issue(location, "unknown_chunk_id", chunk_id=citation.chunk_id)
                    valid = False
                elif not citation.quote.strip() or citation.quote not in originals[citation.chunk_id].page_content:
                    issue(location, "quote_not_contiguous", chunk_id=citation.chunk_id)
                    valid = False
                else:
                    selected.add(citation.chunk_id)
            return bool(values) and valid

        def claim(path, text, values, kind):
            valid_citations = citations(path + ["citations"], values)
            # A condition may quote a supplier URL already present in its own
            # exact source span, just as a source warning may. Main prose still
            # forbids URLs; modified/new URLs and every other unsafe claim fail.
            unsafe = (_unsafe_critical_translation(text, "\n".join(c.quote for c in values))
                      if "conditions" in path else _unsafe_text(text))
            if unsafe:
                issue(path + ["text"], "unsafe_or_scope_assertion")
            if any(c.chunk_id in originals and prompt.response_reference_only(text, originals[c.chunk_id]) for c in values):
                issue(path + ["text"], "specialist_response_action_not_answer")
            if not valid_citations:
                return
            if not translation_valid("", text, language,
                    preserved_terms=names + _cited_ingredient_terms(values, originals)):
                issue(path + ["text"], "target_language_invalid")
            if not _quantities_supported(text, _with_section_reference(text, values, originals),
                    source_identifiers=_cited_cas_identifiers(values, originals)):
                issue(path + ["text"], "quantity_or_date_not_supported")
            if any(_source_technical_requirement(c, metadata) for c in values) and _weakens_requirement(text):
                issue(path + ["text"], "source_requirement_weakened_to_advice")
            if kind == "recommendation" and _has_duty_assertion(text):
                issue(path + ["kind"], "recommendation_contains_requirement")
            if kind != "legal_obligation" and _invalid_nonlaw_duty(text, values, metadata):
                issue(path + ["text"], "source_force_or_legal_status_unverified")
            if kind == "legal_obligation" and not _supports_legal_duty(values, metadata):
                issue(path + ["kind"], "legal_duty_requires_law_evidence")

        for index, statement in enumerate(draft.statements):
            path = ["statements", index]
            claim(path, statement.text, statement.citations, statement.kind)
            if _verify_citations(statement.citations, originals):
                authoring = any(prompt.source_purpose(originals[c.chunk_id])["authoring_or_label_guide"]
                                for c in statement.citations)
                if authoring and not re.search(r"작성|기재|표지|문구|항목|label|author|writing|example|标签|编写|示例|bien soan|ghi chep|ghi ro|nhan canh bao|vi du|ស្លាក|សរសេរ|កត់ត្រា|ឧទាហរណ៍|រៀបចំឯកសារ", statement.text if language == "km" else normalized(statement.text), re.I):
                    issue(path + ["text"], "authoring_guide_needs_explicit_writing_or_label_context")
            for position, condition in enumerate(statement.conditions):
                claim(path + ["conditions", position], condition.text, condition.citations, statement.kind)
        for index, fact in enumerate(draft.product_facts):
            citations(["product_facts", index, "citations"], fact.citations)
        if any(m.doc_type == DOC_TYPE_MSDS for m in metadata.values()):
            fields = {fact.field for fact in draft.product_facts}
            for field in ("product_name", "product_number", "concentration", "revision_date"):
                if field not in fields:
                    issue(["product_facts"], "product_fact_missing", field=field)

        passages = critical_passages(documents)
        required = {pid for pid, (cid, _) in passages.items()
                    if cid in selected or metadata[cid].doc_type == DOC_TYPE_MSDS}
        seen = set()
        for index, item in enumerate(draft.critical_translations):
            path = ["critical_translations", index]
            if item.passage_id not in passages:
                issue(path + ["passage_id"], "unknown_passage_id", passage_id=item.passage_id)
                continue
            if item.passage_id in seen:
                issue(path + ["passage_id"], "duplicate_passage_id", passage_id=item.passage_id)
            seen.add(item.passage_id)
            cid, quote = passages[item.passage_id]
            values = [Citation(chunk_id=cid, quote=quote)]
            identifiers = _cited_cas_identifiers(values, originals)
            if (_unsafe_critical_translation(item.text, quote) or not translation_valid(
                    quote, item.text, language, source_doc_type=metadata[cid].doc_type,
                    source_identifiers=identifiers,
                    preserved_terms=names + _cited_ingredient_terms(values, originals))):
                issue(path + ["text"], "critical_translation_invalid", passage_id=item.passage_id)
            if not _quantities_supported(item.text, values, source_identifiers=identifiers):
                issue(path + ["text"], "critical_quantity_or_date_not_supported", passage_id=item.passage_id)
        if language != "ko":
            for pid in sorted(required - seen):
                issue(["critical_translations"], "critical_translation_missing", passage_id=pid)
        if not issues:
            issue([], "semantic_or_product_support_requires_recheck")
    except Exception:
        # Diagnostic helpers must not change the established retry/error policy,
        # leak exceptions or become an alternate path to accepting evidence.
        issue([], "diagnostic_unavailable_recheck_original_sources")
    return {"validation_failure": reason, "issues": issues}


def _law_warning_in_cited_definition(document, warning, citations):
    """Keep all warnings unless exact numbered definition scopes prove unrelated.

    A whole article may define several unrelated terms. Never attach another
    term's exception to the cited definition. Ambiguous/repeated/cross-boundary
    spans and unscoped global conditions conservatively keep the warning.
    This only scopes rendering; it does not establish the claim's legal meaning.
    """
    body = document.page_content
    if (document.metadata.get("doc_type") != DOC_TYPE_LAW
            or not re.search(r"제\d+조\s*\(\s*정의\s*\)", body[:160])):
        return True
    headings = list(re.finditer(r'(?m)^[ \t]*\d+\.[ \t]*[“"]([^”"\n]+)[”"](?:이)?란', body))
    if len(headings) < 2:
        return True
    def scope(quote):
        spans = list(re.finditer(re.escape(quote), body)) if quote else []
        if len(spans) != 1:
            return None
        span = spans[0]
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
            if heading.start() <= span.start() and span.end() <= end:
                return index
        return None
    warning_scope = scope(warning)
    if warning_scope is None or not citations:
        return True
    scopes = [scope(quote) for quote in citations]
    if any(index is None for index in scopes):
        return True
    # Explicit references to other defined terms also keep their conditions.
    named_scopes = {index for index, heading in enumerate(headings)
                    if any(heading.group(1) in quote for quote in citations)}
    return warning_scope in set(scopes) | named_scopes


def generate_answer(
    question: str, documents: list[Document], *,
    structured_llm: DocumentStructuredLLM | None = None,
    model: str | None = None, timeout_seconds: float = 30.0,
    as_of: date | None = None, language: str = "ko", mode: str = "qa",
    product_id: str | None = None, topic: str | None = None,
) -> GenerationOutput:
    """Generate, fully validate, and allow at most one grounded draft correction.

    Every attempt follows the same local and independent semantic checks.
    Preflight, missing evidence, provider failures and verification outages are
    never retried. A second invalid draft is withheld, never auto-approved.
    The existing network timeout remains per call, not a total request budget.
    """
    class DraftSession:
        def __init__(self):
            self.provider = None
            self.last = None
            self.called = False
            self.reason = None
            self.diagnostics = None

        def invoke(self, messages):
            self.called = True
            if self.provider is None:
                self.provider = structured_llm if structured_llm is not None else build_document_llm(
                    model or os.getenv(ENV_LLM_MODEL, "gpt-4o"), timeout_seconds=timeout_seconds)
            if self.reason is not None:
                messages = list(messages) + prompt.build_repair_messages(
                    self.reason, self.last, language, diagnostics=self.diagnostics)
            raw = self.provider.invoke(messages)
            self.last = raw.model_dump() if isinstance(raw, BaseModel) else raw
            return raw

    session = DraftSession()
    kwargs = dict(structured_llm=session, model=model, timeout_seconds=timeout_seconds,
                  as_of=as_of, language=language, mode=mode, product_id=product_id, topic=topic)
    result = _generate_answer_once(question, documents, **kwargs)
    recoverable = {"invalid_evidence", "invalid_translation", "product_unverified", "claim_mismatch", "invalid_output"}
    if session.called and session.last is not None and len(result.review_reasons) == 1 and result.review_reasons[0] in recoverable:
        session.reason = result.review_reasons[0]
        session.diagnostics = _draft_repair_feedback(
            session.last, documents, reason=session.reason, language=language, question=question)
        session.diagnostics["semantic_failures"] = result._verification_failures
        result = _generate_answer_once(question, documents, **kwargs)
    return result


def _valid_location_draft(draft, documents, language):
    """Only server-constructed heading claims qualify for location rendering.

    Injected/legacy providers pass the same check: prose, extra conditions or
    warning translations cannot enter this path by merely saying 'location'.
    """
    known = {item["chunk_id"]: item for item in prompt.msds_location_candidates(documents)}
    seen = set()
    if draft.critical_translations:
        return False
    for statement in draft.statements:
        if statement.kind != "information" or statement.conditions or not statement.citations:
            return False
        cid = statement.citations[0].chunk_id
        item = known.get(cid)
        if (item is None or cid in seen
                or statement.text != prompt.msds_location_text(item["section_no"], language)
                or [c.model_dump() for c in statement.citations] != item["citations"]):
            return False
        seen.add(cid)
    return bool(seen)


def _finish_location_answer(question, draft, originals, metadata, reasons, *, language, as_of, model, timeout_seconds):
    """Verify and return only the selected location claims and real sources.

    Warning/procedure prose is not part of this response. Every emitted claim
    still uses the common independent verifier and full unchanged Documents.
    Normal safety-information answers retain their complete warning pipeline.
    """
    failure, details = _verify_draft_support(question, draft, originals, {}, {},
        language=language, as_of=as_of, model=model, timeout_seconds=timeout_seconds)
    if failure:
        result = _review_result(failure, language=language)
        result._verification_failures = details
        return result
    ids = list(dict.fromkeys(c.chunk_id for s in draft.statements for c in s.citations))
    numbers = {cid: i for i, cid in enumerate(ids, start=1)}
    lines = [f"{prompt.render_statement(s, originals, language)} [{numbers[s.citations[0].chunk_id]}]"
             for s in draft.statements]
    reasons = list(dict.fromkeys(reasons))
    result = GenerationOutput(answer="\n\n".join(lines),
        sources=[metadata[cid].model_copy(deep=True) for cid in ids], needs_review=bool(reasons), handoff=False)
    result._review_reasons = reasons
    result._review_message = " ".join(_REVIEW_MESSAGES[reason] for reason in reasons)
    return result


def _generate_answer_once(
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
    location_only = bool(msds) and prompt.msds_location_only_question(question)

    try:
        llm = structured_llm if structured_llm is not None else build_document_llm(model or os.getenv(ENV_LLM_MODEL, "gpt-4o"), timeout_seconds=timeout_seconds)
        raw = llm.invoke(build_document_messages(question, usable, as_of=reference_date, language=language, mode=mode, product_id=product_id))
    except (APITimeoutError, httpx.TimeoutException, TimeoutError) as exc:
        record_failure(exc, stage="generation")
        return review("llm_timeout")
    except RAGConfigurationError:
        return review("configuration_error")
    except TranslationGenerationError:
        return review("invalid_translation")
    except ProductEvidenceGenerationError:
        return review("product_unverified")
    except DocumentLocationGenerationError:
        return review("invalid_evidence")
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

    draft = _canonicalize_citation_whitespace(draft, originals)

    if msds and not _verified_product(draft, originals, metadata_by_id, reference_date, question):
        return review("product_unverified")

    draft = _restore_product_name_tokens(draft, usable)
    if draft is None:
        return review("invalid_translation")
    if location_only and not _valid_location_draft(draft, usable, language):
        return review("invalid_evidence")
    # Context additions use only already valid claim/condition citations. Keep
    # product checks, source text and the independent verifier unchanged.
    if any(not _verify_citations(statement.citations, originals)
           or any(not _verify_citations(condition.citations, originals)
                  for condition in statement.conditions)
           for statement in draft.statements):
        return review("invalid_evidence")
    draft = _with_exact_ppe_context(draft, originals, metadata_by_id)
    draft = _align_technical_kinds(draft, originals, metadata_by_id)
    if msds:
        draft = _without_redundant_msds_statements(draft, msds)

    # Product names were verified by _verified_product above; allow those exact
    # identifiers in translated prose without allowing arbitrary source-language text.
    preserved_terms = tuple(fact.value for fact in draft.product_facts if fact.field == "product_name") if msds else ()
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
        source_requirement = any(_source_technical_requirement(c, metadata_by_id) for c in statement.citations)
        if source_requirement and _weakens_requirement(statement.text):
            return review("invalid_translation")
        if direct_ppe and re.search(r"recommend|advis|suggest|建议|推荐|khuyen|권장", normalized(statement.text), re.I):
            return review("invalid_translation")
        authoring = any(prompt.source_purpose(originals[c.chunk_id])["authoring_or_label_guide"] for c in statement.citations)
        if authoring and not re.search(r"작성|기재|표지|문구|항목|label|author|writing|example|sections?|fields?|items?|specified|标签|编写|示例|项目|条目|注明|记录|bien soan|ghi chep|ghi ro|nhan canh bao|vi du|\bmuc\b|ស្លាក|សរសេរ|កត់ត្រា|ឧទាហរណ៍|រៀបចំឯកសារ", statement.text if language == "km" else normalized(statement.text), re.I):
            return review("claim_mismatch")
        if statement.kind == "recommendation" and _has_duty_assertion(statement.text):
            return review("invalid_evidence")
        if statement.kind != "legal_obligation" and _invalid_nonlaw_duty(statement.text, statement.citations, metadata_by_id):
            return review("invalid_evidence")
        if statement.kind == "legal_obligation" and not _supports_legal_duty(statement.citations, metadata_by_id):
            return review("invalid_evidence")
        if not _quantities_supported(statement.text, _with_section_reference(statement.text, statement.citations, originals),
                source_identifiers=_cited_cas_identifiers(statement.citations, originals)):
            return review("claim_mismatch")
        selected_ids.extend(c.chunk_id for c in statement.citations)
        if not statement.conditions:
            reasons.append("conditions_unverified")
        for condition in statement.conditions:
            if (_unsafe_critical_translation(condition.text, "\n".join(c.quote for c in condition.citations))
                    or not _verify_citations(condition.citations, originals)):
                return review("invalid_evidence")
            if not _quantities_supported(condition.text, _with_section_reference(condition.text, condition.citations, originals),
                    source_identifiers=_cited_cas_identifiers(condition.citations, originals)):
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

    if location_only:
        return _finish_location_answer(question, draft, originals, metadata_by_id, reasons,
            language=language, as_of=reference_date, model=model or os.getenv(ENV_LLM_MODEL, "gpt-4o"),
            timeout_seconds=timeout_seconds)

    if msds:
        selected_ids.extend(c.chunk_id for fact in draft.product_facts for c in fact.citations)
    warning_documents = [doc for cid, doc in originals.items()
                         if cid in selected_ids or metadata_by_id[cid].doc_type == DOC_TYPE_MSDS]
    if prompt.unresolved_response_warning_chunks(warning_documents):
        # A specialized action cannot silently take its attached prohibition
        # or hazard explanation out of the answer. Never return success after
        # dropping an inseparable warning; no new public response field.
        return review("incomplete_warning_context")
    passages = critical_passages(usable)

    def warning_required(cid, quote):
        # Preserve every retrieved MSDS warning and all selected guide warnings.
        # Only an unambiguously unrelated numbered law definition is excluded.
        if metadata_by_id[cid].doc_type == DOC_TYPE_MSDS:
            return True
        if cid not in selected_ids:
            return False
        own_quotes = [citation.quote for statement in draft.statements
                      for citation in [*statement.citations,
                          *(c for condition in statement.conditions for c in condition.citations)]
                      if citation.chunk_id == cid]
        return _law_warning_in_cited_definition(originals[cid], quote, own_quotes)

    required = {pid: pair for pid, pair in passages.items() if warning_required(*pair)}
    translated = {}
    for item in draft.critical_translations:
        if item.passage_id not in passages or item.passage_id in translated:
            return review("invalid_translation")
        if (_unsafe_critical_translation(item.text, passages[item.passage_id][1])
                or not _identities_preserved(passages[item.passage_id][1], item.text, preserved_terms)
                or not translation_valid(passages[item.passage_id][1], item.text, language,
                source_doc_type=metadata_by_id[passages[item.passage_id][0]].doc_type,
                source_identifiers=_cited_cas_identifiers(
                    [Citation(chunk_id=passages[item.passage_id][0], quote=passages[item.passage_id][1])], originals),
                preserved_terms=preserved_terms + _cited_ingredient_terms(
                    [Citation(chunk_id=passages[item.passage_id][0], quote=passages[item.passage_id][1])], originals))):
            return review("invalid_translation")
        passage_cid, passage_quote = passages[item.passage_id]
        if not _quantities_supported(item.text, [Citation(chunk_id=passage_cid, quote=passage_quote)],
                source_identifiers=_cited_cas_identifiers(
                    [Citation(chunk_id=passage_cid, quote=passage_quote)], originals)):
            return review("claim_mismatch")
        translated[item.passage_id] = item.text
    if language != "ko" and not set(required).issubset(translated):
        return review("invalid_translation")
    verification_failure, verification_details = _verify_draft_support(
        question, draft, originals, required, translated, language=language,
        as_of=reference_date, model=model or os.getenv(ENV_LLM_MODEL, "gpt-4o"),
        timeout_seconds=timeout_seconds,
    )
    if verification_failure:
        blocked = review(verification_failure)
        blocked._verification_failures = verification_details
        return blocked
    reference_only = {pid: pair for pid, pair in prompt.reference_only_passages(usable).items()
                      if pair[0] in selected_ids or metadata_by_id[pair[0]].doc_type == DOC_TYPE_MSDS}
    selected_ids.extend(cid for cid, _ in reference_only.values())
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
        parts.append(f"{prompt.render_statement(statement, originals, language).strip()} {markers(statement.citations)}")
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
            display_original = prompt.guide_translation_comparison_text(original) if metadata_by_id[cid].doc_type == DOC_TYPE_GUIDE else original
            translated_text = re.sub(r"\s+", " ", display_original).strip() if language == "ko" else translated[pid]
            parts.append(f"- {prompt.render_source_warning(translated_text, language)} [{source_numbers[cid]}]")
            if language != "ko":
                parts.append(f"  {text['original']}: {original}")
    if reference_only:
        parts.append(text["reference_notice"] + " " + " ".join(
            f"[{source_numbers[cid]}]" for cid in dict.fromkeys(cid for cid, _ in reference_only.values())))
    if any(prompt.source_purpose(originals[cid])["demo_only"] for cid in selected_ids):
        demo_labels = {"ko": "시연용 가상 자료", "zh": "演示资料", "vi": "Tài liệu minh họa", "en": "Demo material", "km": "ឯកសារសាកល្បង"}
        parts.append(demo_labels[language] + " — " + text["missing_conditions"])
    if any(source.doc_type == DOC_TYPE_LAW for source in sources):
        parts.append(text["law_review"])
    if msds:
        product_labels = {
            "ko": {"product_name": "자료의 제품명", "product_number": "제품번호", "concentration": "농도", "revision_date": "MSDS 개정일"},
            "zh": {"product_name": "资料中的产品名称", "product_number": "产品编号", "concentration": "浓度", "revision_date": "MSDS修订日期"},
            "vi": {"product_name": "Tên sản phẩm trong tài liệu", "product_number": "Mã sản phẩm", "concentration": "Nồng độ", "revision_date": "Ngày sửa đổi MSDS"},
            "en": {"product_name": "Product name in the document", "product_number": "Product number", "concentration": "Concentration", "revision_date": "MSDS revision date"},
            "km": {"product_name": "ឈ្មោះផលិតផលក្នុងឯកសារ", "product_number": "លេខផលិតផល", "concentration": "កំហាប់", "revision_date": "កាលបរិច្ឆេទកែប្រែ MSDS"},
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
        """Internal evaluation diagnostics; never serialized as API fields."""
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


def generate(question: str, hits: List[Hit], language: str, *,
             product_id: str | None = None, topic: str | None = None,
             mode: str = "qa", structured_llm=None) -> RagResponse:
    early = preflight_result(question, language)
    if early is not None:
        return RagResponse(**early.model_dump())
    documents = []
    for hit in hits:
        metadata = hit.get("metadata", {})
        # Current shared API requires a real document ID. Do not fabricate one.
        if (not isinstance(hit.get("text"), str) or not isinstance(metadata, dict)
                or not isinstance(metadata.get("doc_id"), str) or not metadata["doc_id"].strip()):
            response = GenerationAPIResponse(answer=TEXT[language]["fallback"], sources=[], needs_review=True, handoff=True, latency_ms=0)
            response._review_reasons = ["invalid_metadata"]
            return response
        documents.append(Document(page_content=hit["text"], metadata=dict(metadata)))
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
    # This validated subtype already satisfies RagResponse. Re-wrapping it
    # discards private failure reasons and repeats validation without new data.
    return payload
