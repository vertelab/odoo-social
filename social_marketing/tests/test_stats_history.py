# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from datetime import timedelta
from unittest.mock import Mock

from odoo import fields
from odoo.tests.common import TransactionCase

from odoo.addons.social_marketing.models.social_marketing_provider_response import (
    SocialProviderResponse,
    classify_response,
    parse_usage_headers,
)


class TestDecaySchedule(TransactionCase):

    def test_decay_gap_boundaries(self):
        live_post = self.env['social_marketing.live.post']
        self.assertEqual(live_post._snapshot_gap_days(3), 1)
        self.assertEqual(live_post._snapshot_gap_days(7), 1)
        self.assertEqual(live_post._snapshot_gap_days(8), 7)
        self.assertEqual(live_post._snapshot_gap_days(90), 7)
        self.assertEqual(live_post._snapshot_gap_days(91), 30)
        self.assertEqual(live_post._snapshot_gap_days(365), 30)


class TestProviderResponse(TransactionCase):

    def test_classify_ok(self):
        resp = Mock(ok=True, status_code=200, content=b'{}')
        resp.json.return_value = {}
        classified = classify_response(resp)
        self.assertEqual(classified.status, SocialProviderResponse.STATUS_OK)

    def test_classify_rate_limit_http_429(self):
        resp = Mock(ok=False, status_code=429, content=b'{}', headers={'Retry-After': '3600'})
        resp.json.return_value = {}
        classified = classify_response(resp)
        self.assertEqual(classified.status, SocialProviderResponse.STATUS_EXCEEDED_RATE_LIMIT)
        self.assertEqual(classified.retry_after, 3600)

    def test_classify_unauthorized_code(self):
        resp = Mock(ok=False, status_code=400, content=b'{}', headers={})
        resp.json.return_value = {'serviceErrorCode': 65600}
        classified = classify_response(resp, unauthorized_codes={65600})
        self.assertEqual(classified.status, SocialProviderResponse.STATUS_UNAUTHORIZED)

    def test_classify_rate_limit_code(self):
        resp = Mock(ok=False, status_code=400, content=b'{}', headers={})
        resp.json.return_value = {'error': {'code': 4}}
        classified = classify_response(resp, rate_limit_codes={4})
        self.assertEqual(classified.status, SocialProviderResponse.STATUS_EXCEEDED_RATE_LIMIT)

    def test_usage_headers_about_to_exceed(self):
        resp = Mock(headers={'x-app-usage': '{"call_count":95,"total_cputime":10,"total_time":10}'})
        about, retry = parse_usage_headers(resp, threshold=90)
        self.assertTrue(about)
        self.assertGreater(retry, 0)

    def test_usage_headers_below_threshold(self):
        resp = Mock(headers={'x-app-usage': '{"call_count":10,"total_cputime":5,"total_time":5}'})
        about, _retry = parse_usage_headers(resp, threshold=90)
        self.assertFalse(about)


class TestSnapshotIdempotency(TransactionCase):

    def _create_account(self, audience=100, engagement=50, stories=10):
        media = self.env['social_marketing.media'].create({'name': 'Test Media'})
        return self.env['social_marketing.account'].create({
            'name': 'Test Account',
            'media_id': media.id,
            'audience': audience,
            'engagement': engagement,
            'stories': stories,
        })

    def test_account_snapshot_no_duplicates(self):
        account = self._create_account()
        account._snapshot_statistics()
        account._snapshot_statistics()
        stats = self.env['social_marketing.account.stat'].search([
            ('social_account_id', '=', account.id),
            ('date', '=', fields.Date.context_today(account)),
        ])
        self.assertEqual(len(stats.filtered(lambda s: s.metric == 'audience')), 1)
        self.assertEqual(len(stats.filtered(lambda s: s.metric == 'engagement')), 1)
        self.assertEqual(len(stats.filtered(lambda s: s.metric == 'stories')), 1)

    def test_trend_from_snapshots(self):
        account = self._create_account(audience=100, engagement=0, stories=0)
        today = fields.Date.context_today(account)
        stat_model = self.env['social_marketing.account.stat']
        # Simulate a snapshot 30 days ago and one today.
        stat_model.create({
            'social_account_id': account.id,
            'metric': 'audience',
            'value': 80,
            'date': today - timedelta(days=30),
        })
        account.audience = 100
        account._snapshot_statistics()
        trend = account._compute_trend_from_snapshots('audience', days=30)
        # (100 - 80) / 80 * 100 = 25.0
        self.assertAlmostEqual(trend, 25.0)


class TestBackfill(TransactionCase):

    def _create_account(self):
        media = self.env['social_marketing.media'].create({'name': 'Test Media'})
        return self.env['social_marketing.account'].create({
            'name': 'Test Account',
            'media_id': media.id,
        })

    def test_backfill_resumable(self):
        account = self._create_account()
        end = fields.Date.today()
        # Base _backfill_statistics is a no-op; this exercises window iteration
        # and the advancing last_backfilled_date cursor.
        account._backfill_account_statistics(retention_days=10, window_days=5, end=end)
        self.assertEqual(account.last_backfilled_date, end)

        # A second run is a no-op: cursor == end.
        account._backfill_account_statistics(retention_days=10, window_days=5, end=end)
        self.assertEqual(account.last_backfilled_date, end)

    def test_backfill_snapshot_idempotent(self):
        account = self._create_account()
        date = fields.Date.today()
        account._create_stat_snapshot('audience', 100, date)
        account._create_stat_snapshot('audience', 120, date)
        stats = self.env['social_marketing.account.stat'].search([
            ('social_account_id', '=', account.id),
            ('metric', '=', 'audience'),
            ('date', '=', date),
        ])
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats.value, 120)
