# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging
import requests

from werkzeug.urls import url_join
from odoo import _, models, fields, api
from odoo.addons.social_marketing.controllers.main import SocialValidationException

_logger = logging.getLogger(__name__)

INSTAGRAM_ENDPOINT = 'https://graph.facebook.com/v21.0'


class SocialAccountInstagram(models.Model):
    _inherit = 'social_marketing.account'

    instagram_business_account_id = fields.Char('Instagram Business Account ID', readonly=True)
    instagram_access_token = fields.Char('Instagram Access Token', readonly=True)
    instagram_username = fields.Char('Instagram Username', readonly=True)

    def _compute_stats_link(self):
        instagram_accounts = self._filter_by_media_types(['instagram'])
        super(SocialAccountInstagram, (self - instagram_accounts))._compute_stats_link()
        for account in instagram_accounts:
            if account.instagram_username:
                account.stats_link = f'https://www.instagram.com/{account.instagram_username}/'

    def _instagram_bearer_headers(self):
        self.ensure_one()
        if not self.instagram_access_token:
            raise SocialValidationException(_('Instagram access token is not set.'))
        return {'Authorization': f'Bearer {self.instagram_access_token}'}

    def _action_disconnect_accounts(self, disconnection_info=None):
        _logger.warning("Instagram account disconnected: %s. Reason: %s",
                        self.display_name,
                        disconnection_info or "Not provided", stack_info=True)
        self.sudo().write({'is_media_disconnected': True})

    def _fetch_inbox_messages(self):
        self.ensure_one()
        if self.media_type != 'instagram':
            return super()._fetch_inbox_messages()

        if not self.instagram_business_account_id or not self.instagram_access_token:
            return 0

        session = requests.Session()
        new_count = 0

        try:
            # GET /{ig-user-id}/conversations?fields=messages{from,message,id,timestamp}
            endpoint = url_join(INSTAGRAM_ENDPOINT,
                f'{self.instagram_business_account_id}/conversations')
            params = {
                'fields': 'messages{from,message,id,timestamp}',
                'access_token': self.instagram_access_token,
            }
            response = session.get(endpoint, params=params, timeout=15)

            if not response.ok:
                _logger.warning("Instagram inbox fetch failed: %s", response.text)
                return 0

            data = response.json()
            for conversation in data.get('data', []):
                messages = conversation.get('messages', {}).get('data', [])
                for msg in messages:
                    existing = self.env['social_marketing.message'].search_count([
                        ('external_id', '=', msg.get('id')),
                    ])
                    if existing:
                        continue

                    from_data = msg.get('from', {})
                    self.env['social_marketing.message'].create({
                        'from_name': from_data.get('username', 'Instagram User'),
                        'from_handle': f"@{from_data.get('username', 'unknown')}",
                        'body': msg.get('message', ''),
                        'external_id': msg.get('id'),
                        'media_type': 'instagram',
                        'message_type': 'dm',
                        'social_account_id': self.id,
                        'state': 'unread',
                    })
                    new_count += 1

        except requests.exceptions.RequestException as e:
            _logger.warning("Instagram inbox fetch error: %s", str(e))

        return new_count

    def _send_inbox_reply(self, message, body):
        self.ensure_one()
        if self.media_type != 'instagram':
            return super()._send_inbox_reply(message, body)

        if not self.instagram_access_token:
            return False

        try:
            endpoint = url_join(INSTAGRAM_ENDPOINT,
                f'{self.instagram_business_account_id}/messages')
            data = {
                'recipient': {'id': message.external_id},
                'message': {'text': body},
                'access_token': self.instagram_access_token,
            }
            response = requests.post(endpoint, json=data, timeout=10)
            return response.ok

        except requests.exceptions.RequestException as e:
            _logger.warning("Instagram reply error: %s", str(e))
            return False

    def _compute_statistics(self):
        instagram_accounts = self._filter_by_media_types(['instagram'])
        super(SocialAccountInstagram, (self - instagram_accounts))._compute_statistics()

        for account in instagram_accounts:
            if not account.instagram_business_account_id:
                continue
            try:
                endpoint = url_join(INSTAGRAM_ENDPOINT, account.instagram_business_account_id)
                params = {
                    'fields': 'followers_count,media_count',
                    'access_token': account.instagram_access_token,
                }
                response = requests.get(endpoint, params=params, timeout=10)
                if response.ok:
                    data = response.json()
                    account.audience = data.get('followers_count', 0)
                # Best-effort reach/impressions from Instagram insights.
                insights = account._fetch_instagram_insights()
                if insights.get('reach'):
                    account.reach = insights['reach']
                if insights.get('impressions'):
                    account.impressions = insights['impressions']
            except Exception as e:
                _logger.warning("Instagram stats fetch error for %s: %s", account.display_name, str(e))

    def _fetch_instagram_insights(self):
        """Best-effort fetch of reach/impressions Instagram insights."""
        self.ensure_one()
        try:
            endpoint = url_join(INSTAGRAM_ENDPOINT, f'{self.instagram_business_account_id}/insights')
            params = {
                'metric': 'reach,impressions',
                'period': 'day',
                'access_token': self.instagram_access_token,
            }
            response = requests.get(endpoint, params=params, timeout=10)
            if not response.ok:
                return {}
            result = {}
            for entry in response.json().get('data', []):
                metric = entry.get('name')
                total = sum(v.get('value', 0) for v in entry.get('values', []))
                if metric == 'reach':
                    result['reach'] = total
                elif metric == 'impressions':
                    result['impressions'] = total
            return result
        except Exception:
            return {}

    def _backfill_statistics(self, window_start, window_end):
        instagram_accounts = self._filter_by_media_types(['instagram'])
        super(SocialAccountInstagram, (self - instagram_accounts))._backfill_statistics(window_start, window_end)

        for account in instagram_accounts:
            if not account.instagram_business_account_id or not account.instagram_access_token:
                continue
            endpoint = url_join(INSTAGRAM_ENDPOINT, f'{account.instagram_business_account_id}/insights')
            params = {
                'metric': 'follower_count,reach,impressions',
                'period': 'day',
                'since': int(window_start.timestamp()),
                'until': int(window_end.timestamp()),
                'access_token': account.instagram_access_token,
            }
            try:
                response = account._backfill_get(endpoint, params=params)
                if not response.ok:
                    _logger.warning(
                        "Instagram backfill failed for %s: %s",
                        account.display_name, response.text[:200])
                    continue
                by_date = {}
                for entry in response.json().get('data', []):
                    name = entry.get('name')
                    for value in entry.get('values', []):
                        date = (value.get('end_time') or '')[:10]
                        if not date:
                            continue
                        by_date.setdefault(date, {})[name] = value.get('value', 0)
                metric_map = {
                    'follower_count': 'audience',
                    'reach': 'reach',
                    'impressions': 'impressions',
                }
                for date, values in by_date.items():
                    for ig_metric, stat_metric in metric_map.items():
                        if ig_metric in values:
                            account._create_stat_snapshot(stat_metric, values[ig_metric], date)
            except Exception as e:
                _logger.warning(
                    "Instagram backfill error for %s: %s", account.display_name, str(e))
