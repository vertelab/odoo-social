# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging
import requests

from werkzeug.urls import url_join
from odoo import _, models, fields, api
from odoo.addons.social_marketing.controllers.main import SocialValidationException
from odoo.addons.social_marketing.models.social_marketing_provider_response import parse_usage_headers

_logger = logging.getLogger(__name__)

FACEBOOK_ENDPOINT = 'https://graph.facebook.com/v21.0'


class SocialAccountFacebook(models.Model):
    _inherit = 'social_marketing.account'

    facebook_page_id = fields.Char('Facebook Page ID', readonly=True)
    facebook_page_access_token = fields.Char('Page Access Token', readonly=True)
    facebook_page_name = fields.Char('Page Name', readonly=True)

    def _compute_stats_link(self):
        facebook_accounts = self._filter_by_media_types(['facebook'])
        super(SocialAccountFacebook, (self - facebook_accounts))._compute_stats_link()
        for account in facebook_accounts:
            if account.facebook_page_id:
                account.stats_link = f'https://www.facebook.com/{account.facebook_page_id}/insights'

    def _facebook_bearer_headers(self):
        """ Return headers with page access token for Graph API calls. """
        self.ensure_one()
        if not self.facebook_page_access_token:
            raise SocialValidationException(_('Facebook page access token is not set.'))
        return {
            'Authorization': f'Bearer {self.facebook_page_access_token}',
            'Content-Type': 'application/json',
        }

    def _action_disconnect_accounts(self, disconnection_info=None):
        _logger.warning("Facebook account disconnected: %s. Reason: %s",
                        self.display_name,
                        disconnection_info or "Not provided",
                        stack_info=True)
        self.sudo().write({'is_media_disconnected': True})

    def _fetch_inbox_messages(self):
        """ Fetch Facebook Page conversations via Graph API. """
        self.ensure_one()
        if self.media_type != 'facebook':
            return super()._fetch_inbox_messages()

        if not self.facebook_page_id or not self.facebook_page_access_token:
            return 0

        session = requests.Session()
        new_count = 0

        try:
            # GET /{page-id}/conversations?fields=messages{from,message,created_time}
            endpoint = url_join(FACEBOOK_ENDPOINT, f'{self.facebook_page_id}/conversations')
            params = {
                'fields': 'messages{from,message,created_time,id},updated_time',
                'access_token': self.facebook_page_access_token,
            }
            response = session.get(endpoint, params=params, timeout=15)

            if not response.ok:
                _logger.warning("Facebook inbox fetch failed: %s", response.text)
                return 0

            data = response.json()
            for conversation in data.get('data', []):
                messages = conversation.get('messages', {}).get('data', [])
                for msg in messages:
                    # Check for existing
                    existing = self.env['social_marketing.message'].search_count([
                        ('external_id', '=', msg.get('id')),
                    ])
                    if existing:
                        continue

                    from_data = msg.get('from', {})
                    self.env['social_marketing.message'].create({
                        'from_name': from_data.get('name', 'Facebook User'),
                        'from_handle': f"@{from_data.get('name', 'unknown')}",
                        'body': msg.get('message', ''),
                        'external_id': msg.get('id'),
                        'media_type': 'facebook',
                        'message_type': 'dm',
                        'social_account_id': self.id,
                        'state': 'unread',
                    })
                    new_count += 1

        except requests.exceptions.RequestException as e:
            _logger.warning("Facebook inbox fetch error: %s", str(e))

        return new_count

    def _send_inbox_reply(self, message, body):
        """ Send reply via Facebook Messenger API. """
        self.ensure_one()
        if self.media_type != 'facebook':
            return super()._send_inbox_reply(message, body)

        if not self.facebook_page_access_token:
            return False

        try:
            # POST /{page-id}/messages
            endpoint = url_join(FACEBOOK_ENDPOINT, f'{self.facebook_page_id}/messages')
            data = {
                'recipient': {'id': message.external_id},
                'message': {'text': body},
                'access_token': self.facebook_page_access_token,
            }
            response = requests.post(endpoint, json=data, timeout=10)

            if response.ok:
                return True
            else:
                _logger.warning("Facebook reply failed: %s", response.text)
                return False

        except requests.exceptions.RequestException as e:
            _logger.warning("Facebook reply error: %s", str(e))
            return False

    def _compute_statistics(self):
        facebook_accounts = self._filter_by_media_types(['facebook'])
        super(SocialAccountFacebook, (self - facebook_accounts))._compute_statistics()

        for account in facebook_accounts:
            if not account.facebook_page_id:
                continue
            try:
                endpoint = url_join(FACEBOOK_ENDPOINT, f'{account.facebook_page_id}')
                params = {
                    'fields': 'fan_count,engagement',
                    'access_token': account.facebook_page_access_token,
                }
                response = requests.get(endpoint, params=params, timeout=10)
                if response.ok:
                    data = response.json()
                    account.audience = data.get('fan_count', 0)
                    account.engagement = data.get('engagement', {}).get('count', 0)
                about_to_exceed, retry_after = parse_usage_headers(response)
                if about_to_exceed:
                    _logger.warning(
                        "Facebook rate limit about to be exceeded for %s (retry after %s s).",
                        account.display_name, retry_after)
                # Best-effort reach/impressions from the insights endpoint.
                insights = account._fetch_facebook_insights()
                if insights.get('reach'):
                    account.reach = insights['reach']
                if insights.get('impressions'):
                    account.impressions = insights['impressions']
            except Exception as e:
                _logger.warning("Facebook stats fetch error for %s: %s", account.display_name, str(e))

    def _fetch_facebook_insights(self):
        """Best-effort fetch of reach/impressions insights.

        Facebook deprecates individual page insights over time; failures here
        are non-fatal and simply leave reach/impressions unpopulated.
        """
        self.ensure_one()
        try:
            endpoint = url_join(FACEBOOK_ENDPOINT, f'{self.facebook_page_id}/insights')
            params = {
                'metric': 'page_impressions,page_reach',
                'period': 'day',
                'access_token': self.facebook_page_access_token,
            }
            response = requests.get(endpoint, params=params, timeout=10)
            if not response.ok:
                return {}
            result = {}
            for entry in response.json().get('data', []):
                metric = entry.get('name')
                total = sum(v.get('value', 0) for v in entry.get('values', []))
                if metric == 'page_impressions':
                    result['impressions'] = total
                elif metric == 'page_reach':
                    result['reach'] = total
            return result
        except Exception:
            return {}

    def _backfill_statistics(self, window_start, window_end):
        facebook_accounts = self._filter_by_media_types(['facebook'])
        super(SocialAccountFacebook, (self - facebook_accounts))._backfill_statistics(window_start, window_end)

        for account in facebook_accounts:
            if not account.facebook_page_id or not account.facebook_page_access_token:
                continue
            endpoint = url_join(FACEBOOK_ENDPOINT, f'{account.facebook_page_id}/insights')
            params = {
                'metric': 'page_fans,page_impressions,page_engaged_users',
                'period': 'day',
                'since': int(window_start.timestamp()),
                'until': int(window_end.timestamp()),
                'access_token': account.facebook_page_access_token,
            }
            try:
                response = account._backfill_get(endpoint, params=params)
                if not response.ok:
                    _logger.warning(
                        "Facebook backfill failed for %s: %s",
                        account.display_name, response.text[:200])
                    continue
                # Normalize daily values into date -> {metric: value}.
                by_date = {}
                for entry in response.json().get('data', []):
                    name = entry.get('name')
                    for value in entry.get('values', []):
                        date = (value.get('end_time') or '')[:10]
                        if not date:
                            continue
                        by_date.setdefault(date, {})[name] = value.get('value', 0)
                metric_map = {
                    'page_fans': 'audience',
                    'page_impressions': 'impressions',
                    'page_engaged_users': 'engagement',
                }
                for date, values in by_date.items():
                    for fb_metric, stat_metric in metric_map.items():
                        if fb_metric in values:
                            account._create_stat_snapshot(stat_metric, values[fb_metric], date)
            except Exception as e:
                _logger.warning(
                    "Facebook backfill error for %s: %s", account.display_name, str(e))
