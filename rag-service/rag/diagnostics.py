"""Private failure diagnostics. Never record prompts, credentials or raw errors.

JSON response contracts stay unchanged; the API may expose bounded status
headers for its UI. Request-local capture is reset even when generation fails.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Mapping
import re

import httpx
from openai import APIError, APITimeoutError

_active_failures = ContextVar('chembridge_failure_diagnostics', default=None)
_IDENTIFIER = re.compile(r'[a-z][a-z0-9_]{0,79}\Z')
_REQUEST_ID = re.compile(r'req_[A-Za-z0-9_-]{1,120}\Z')
_EXPERIMENT_REASONS = frozenset({
    'provider_halted', 'http_count', 'input_token_limit', 'incremental_budget',
    'cumulative_budget', 'unapproved_destination', 'unapproved_model_or_stream',
    'unapproved_request', 'unapproved_source', 'experiment_scope',
})
_VALIDATION_REASONS = frozenset({
    'invalid_evidence', 'claim_mismatch', 'invalid_translation', 'invalid_output',
    'invalid_metadata', 'incomplete_warning_context',
})
_PUBLIC_REASONS = _EXPERIMENT_REASONS | _VALIDATION_REASONS | frozenset({
    'no_evidence', 'retrieval_empty', 'verification_unavailable', 'product_unverified',
    'llm_timeout', 'llm_error', 'configuration_error',
})
HEADER_NAMES = (
    'X-ChemBridge-Outcome', 'X-ChemBridge-Reason', 'X-ChemBridge-Request-Id',
    'X-ChemBridge-Provider-Status', 'X-ChemBridge-Provider-Code',
)


class ExperimentStopped(RuntimeError):
    """Local approval boundary; not an OpenAI/provider failure."""
    def __init__(self, reason):
        self.reason = reason if reason in _EXPERIMENT_REASONS else 'experiment_scope'
        super().__init__('Approved experiment is stopped')


def _identifier(value):
    # Preserve future machine-readable error codes, not arbitrary messages.
    if (isinstance(value, str) and _IDENTIFIER.fullmatch(value)
            and not value.startswith(('sk_', 'bearer', 'eyj'))):
        return value
    return None


def provider_details(status, body, headers=None):
    """Only structured provider fields and bounded support/rate identifiers."""
    result = {'category': 'provider_error'}
    if type(status) is int and 100 <= status <= 599:
        result['provider_status'] = status
    error = body.get('error', body) if isinstance(body, Mapping) else {}
    if isinstance(error, Mapping):
        for source, target in [('code', 'provider_code'), ('type', 'provider_type')]:
            value = _identifier(error.get(source))
            if value:
                result[target] = value
    headers = headers or {}
    request_id = headers.get('x-request-id', '')
    if isinstance(request_id, str) and _REQUEST_ID.fullmatch(request_id):
        result['provider_request_id'] = request_id
    retry_after = headers.get('retry-after', '')
    if isinstance(retry_after, str) and re.fullmatch(r'\d{1,6}(?:\.\d{1,3})?', retry_after):
        result['retry_after_seconds'] = retry_after
    for name in ('requests', 'tokens'):
        value = headers.get('x-ratelimit-remaining-' + name, '')
        if isinstance(value, str) and re.fullmatch(r'\d{1,12}', value):
            result['remaining_' + name] = int(value)
    return result


def exception_details(error, *, stage):
    result = {'stage': stage if stage in {'generation', 'verification', 'chain'} else 'chain'}
    if isinstance(error, ExperimentStopped):
        result.update(category='experiment_stopped', reason=error.reason)
    elif isinstance(error, APIError):
        body = error.body if isinstance(error.body, Mapping) else {}
        body = body.get('error', body)
        if not isinstance(body, Mapping):
            body = {}
        body = {**body, 'code': getattr(error, 'code', None) or body.get('code'),
                'type': getattr(error, 'type', None) or body.get('type')}
        response = getattr(error, 'response', None)
        result.update(provider_details(getattr(error, 'status_code', None), body,
                                       getattr(response, 'headers', None)))
        if isinstance(error, APITimeoutError):
            result['reason'] = 'llm_timeout'
    elif isinstance(error, (httpx.HTTPError, TimeoutError)):
        result['category'] = 'provider_error'
        if isinstance(error, (httpx.TimeoutException, TimeoutError)):
            result['reason'] = 'llm_timeout'
    else:
        result['category'] = 'verifier_unavailable' if stage == 'verification' else 'generation_error'
    return result


@contextmanager
def capture_failures():
    failures = []
    token = _active_failures.set(failures)
    try:
        yield failures
    finally:
        _active_failures.reset(token)


def record_failure(error, *, stage):
    details = exception_details(error, stage=stage)
    failures = _active_failures.get()
    if failures is not None:
        failures.append(details)
    return details


def result_details(result):
    reasons = [reason for reason in getattr(result, 'review_reasons', [])
               if reason in _PUBLIC_REASONS]
    if any(reason in _VALIDATION_REASONS for reason in reasons):
        return {'category': 'verification_failed', 'reason': next(r for r in reasons if r in _VALIDATION_REASONS)}
    for group, category in [({'verification_unavailable'}, 'verifier_unavailable'),
                            ({'no_evidence', 'retrieval_empty'}, 'insufficient_evidence'),
                            ({'product_unverified'}, 'product_unverified')]:
        if any(reason in group for reason in reasons):
            return {'category': category, 'reason': next(r for r in reasons if r in group)}
    return {'category': 'review_required' if result.handoff or result.needs_review else 'answer'}


def response_headers(details, request_id):
    headers = {HEADER_NAMES[0]: details['category'], HEADER_NAMES[2]: request_id}
    reason = details.get('reason')
    if reason in _PUBLIC_REASONS:
        headers[HEADER_NAMES[1]] = reason
    if 'provider_status' in details:
        headers[HEADER_NAMES[3]] = str(details['provider_status'])
    if details.get('provider_code'):
        headers[HEADER_NAMES[4]] = details['provider_code']
    return headers
