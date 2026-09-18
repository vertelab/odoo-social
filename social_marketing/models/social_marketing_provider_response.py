# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

"""Normalized provider-response status.

Social platform APIs report failures in many different shapes. This module
normalizes them into a small status vocabulary so posting and backfill can
detect rate limits, expired tokens and generic errors, and back off
intelligently instead of failing silently or risking a ban.
"""


class SocialProviderResponse(object):
    """A normalized view of a social platform API response.

    Not an Odoo model — a plain value object returned by the classifier
    helpers below. ``status`` is one of the ``STATUS_*`` constants.
    """

    STATUS_OK = 'ok'
    STATUS_EXCEEDED_RATE_LIMIT = 'exceeded_rate_limit'
    STATUS_UNAUTHORIZED = 'unauthorized'
    STATUS_NO_CONTENT = 'no_content'
    STATUS_ERROR = 'error'

    def __init__(self, status=STATUS_OK, retry_after=0, about_to_exceed=False, context=None):
        self.status = status
        self.retry_after = retry_after
        self.about_to_exceed = about_to_exceed
        self.context = context or {}

    def is_ok(self):
        return self.status == self.STATUS_OK

    def has_error(self):
        return not self.is_ok()

    def has_exceeded_rate_limit(self):
        return self.status == self.STATUS_EXCEEDED_RATE_LIMIT

    def is_unauthorized(self):
        return self.status == self.STATUS_UNAUTHORIZED


def classify_response(response, rate_limit_codes=None, unauthorized_codes=None):
    """Classify a ``requests.Response`` into a :class:`SocialProviderResponse`.

    :param response: the ``requests.Response`` to classify
    :param rate_limit_codes: iterable of platform-specific error codes that
        mean "rate limit exceeded" (Facebook/LinkedIn style)
    :param unauthorized_codes: iterable of error codes that mean "token
        expired / unauthorized"
    """
    rate_limit_codes = set(rate_limit_codes or ())
    unauthorized_codes = set(unauthorized_codes or ())

    if response is None:
        return SocialProviderResponse(SocialProviderResponse.STATUS_ERROR)

    if response.status_code == 204 or (response.ok and not response.content):
        return SocialProviderResponse(SocialProviderResponse.STATUS_NO_CONTENT)

    # Parse a JSON body when possible, so we can inspect error codes.
    body = {}
    try:
        body = response.json() if response.content else {}
    except Exception:
        body = {}

    code = None
    if isinstance(body, dict):
        error = body.get('error')
        if isinstance(error, dict):
            code = error.get('code')
        # LinkedIn style: top-level serviceErrorCode
        if code is None:
            code = body.get('serviceErrorCode')

    if response.ok:
        return SocialProviderResponse(SocialProviderResponse.STATUS_OK, context=body)

    # Explicit rate-limit HTTP statuses.
    if response.status_code in (429,):
        retry_after = _extract_retry_after(response)
        return SocialProviderResponse(
            SocialProviderResponse.STATUS_EXCEEDED_RATE_LIMIT,
            retry_after=retry_after, context=body)

    if code in rate_limit_codes:
        retry_after = _extract_retry_after(response) or 60 * 60
        return SocialProviderResponse(
            SocialProviderResponse.STATUS_EXCEEDED_RATE_LIMIT,
            retry_after=retry_after, context=body)

    if code in unauthorized_codes:
        return SocialProviderResponse(
            SocialProviderResponse.STATUS_UNAUTHORIZED, context=body)

    if response.status_code in (401, 403):
        return SocialProviderResponse(
            SocialProviderResponse.STATUS_UNAUTHORIZED, context=body)

    return SocialProviderResponse(SocialProviderResponse.STATUS_ERROR, context=body)


def parse_usage_headers(response, threshold=90):
    """Parse Facebook-style usage headers into ``(about_to_exceed, retry_after)``.

    Reads ``x-app-usage`` and ``x-business-use-case-usage`` headers and
    flags ``about_to_exceed`` when usage exceeds ``threshold`` percent.
    """
    if response is None:
        return False, 0

    headers = response.headers
    usage = 0
    for header_name in ('x-app-usage', 'x-business-use-case-usage'):
        raw = headers.get(header_name)
        if not raw:
            continue
        try:
            parsed = _json_loads_first(raw)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        usage = max(
            usage,
            int(parsed.get('call_count', 0) or 0),
            int(parsed.get('total_cputime', 0) or 0),
            int(parsed.get('total_time', 0) or 0),
        )

    about_to_exceed = usage > threshold
    retry_after = _extract_retry_after(response) or (60 * 60 if about_to_exceed else 0)
    return about_to_exceed, retry_after


def _extract_retry_after(response):
    """Return ``retry_after`` seconds from a response, defaulting to 0."""
    if response is None:
        return 0
    raw = response.headers.get('Retry-After')
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def _json_loads_first(raw):
    """Parse the first JSON object from a possibly-array header value."""
    import json
    if isinstance(raw, (dict, list)):
        return raw[0] if isinstance(raw, list) and raw else raw
    try:
        data = json.loads(raw)
    except Exception:
        # Some headers are like: [{"call_count":1}]
        data = json.loads(raw.strip('[]'))
    if isinstance(data, list):
        return data[0] if data else {}
    return data
