# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

""" Tests for the publishing hardening: idempotency, retry with backoff,
retract, pre-flight validation and token health. """

from datetime import timedelta
from unittest.mock import patch

import psycopg2

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger

_POST_PATH = (
    'odoo.addons.social_marketing.models.social_marketing_live_post.'
    'SocialLivePost._post'
)


class FakeResponse(object):
    """ Minimal stand-in for a requests.Response, enough for the classifier. """

    def __init__(self, status_code, content=b'', headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.ok = 200 <= status_code < 300

    def json(self):
        raise ValueError('no json')


class FakeApiError(Exception):
    """ A provider error carrying the HTTP response, like requests raises. """

    def __init__(self, message, response):
        super().__init__(message)
        self.response = response


class PublishHardeningCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].set_param(
            'social_publish_rate_limit_delay_seconds', '0.0')
        cls.media = cls.env['social_marketing.media'].create({
            'name': 'Hardening Media',
        })
        cls.medium = cls.env['utm.medium'].create({'name': 'Hardening Medium'})
        cls.account = cls.env['social_marketing.account'].create({
            'name': 'Hardening Account',
            'media_id': cls.media.id,
            'utm_medium_id': cls.medium.id,
        })

    def _create_post(self, message='Hello world', accounts=None, platforms=None):
        values = {
            'message': message,
            'account_ids': [
                (6, 0, [a.id for a in (accounts or [self.account])])],
        }
        if platforms is not None:
            values['platform_ids'] = [(6, 0, [p.id for p in platforms])]
        return self.env['social_marketing.post'].create(values)


@tagged('post_install', '-at_install')
class TestPublishIdempotency(PublishHardeningCommon):
    """ Publishing the same post twice must be impossible. """

    def test_double_dispatch_creates_one_live_post(self):
        """ Dispatching the same post twice yields exactly one live post. """
        post = self._create_post()
        with patch(_POST_PATH, lambda self: self.write({'state': 'posted'})):
            post.action_post()
            first_live_posts = post.live_post_ids
            self.assertEqual(len(first_live_posts), 1)

            # Second trigger of the very same post: no second published item.
            post._action_post()

        self.assertEqual(
            len(post.live_post_ids), 1,
            "A re-dispatch must not create a second live post")
        self.assertEqual(post.live_post_ids, first_live_posts)

    def test_idempotency_key_is_stable_and_derived(self):
        """ The key comes from (post, account), it is not random. """
        post = self._create_post()
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': post.id,
            'social_account_id': self.account.id,
        })
        self.assertTrue(live_post.idempotency_key)
        self.assertEqual(
            live_post.idempotency_key,
            self.env['social_marketing.live.post']._build_idempotency_key(
                post.id, self.account.id),
            "The key must be derivable from the post and the account")

    @mute_logger('odoo.sql_db')
    def test_unique_constraint_bites(self):
        """ The database refuses a second live post for the same pair. """
        post = self._create_post()
        self.env['social_marketing.live.post'].create({
            'post_id': post.id,
            'social_account_id': self.account.id,
        })
        self.env.flush_all()
        with self.assertRaises(psycopg2.IntegrityError):
            with self.cr.savepoint():
                self.env['social_marketing.live.post'].create({
                    'post_id': post.id,
                    'social_account_id': self.account.id,
                })
                self.env.flush_all()

    def test_dispatch_of_posted_live_post_does_not_repost(self):
        """ Re-running the job for an already posted item does not re-publish. """
        post = self._create_post()
        calls = []

        def counting_post(live_post):
            calls.append(live_post.id)
            return live_post.write({'state': 'posted'})

        with patch(_POST_PATH, counting_post):
            post.action_post()
            live_post = post.live_post_ids
            live_post._dispatch_post()
            self.assertEqual(live_post.state, 'posted')
            # The queue re-delivers the same job.
            live_post._dispatch_post()

        self.assertEqual(
            len(calls), 1,
            "_post must not be called again for an already posted item")


@tagged('post_install', '-at_install')
class TestPublishRetry(PublishHardeningCommon):
    """ Transient failures back off and retry, permanent ones stop. """

    def _dispatch_expecting_failure(self, live_post):
        """ Dispatch and return the exception, without a rolling-back savepoint. """
        with mute_logger(
                'odoo.addons.social_marketing.models.social_marketing_live_post'):
            try:
                live_post._dispatch_post()
            except Exception as exc:  # noqa: BLE001 - returned to the caller
                return exc
        self.fail('Expected the dispatch to raise')

    def test_transient_failure_schedules_retry(self):
        post = self._create_post()
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': post.id,
            'social_account_id': self.account.id,
        })

        def failing_post(lp):
            raise FakeApiError('upstream down', FakeResponse(503))

        with patch(_POST_PATH, failing_post):
            # Not assertRaises: Odoo wraps it in a savepoint that would roll
            # back the failure bookkeeping this test is about.
            raised = self._dispatch_expecting_failure(live_post)
        self.assertIsInstance(raised, FakeApiError)

        self.assertEqual(live_post.failure_category, 'transient')
        self.assertEqual(live_post.attempt_count, 1)
        self.assertTrue(
            live_post.next_retry_date,
            "A transient failure must schedule the next attempt")
        self.assertEqual(
            live_post.state, 'ready',
            "A retryable live post stays ready, not failed")

    def test_permanent_failure_does_not_schedule_retry(self):
        post = self._create_post()
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': post.id,
            'social_account_id': self.account.id,
        })

        def failing_post(lp):
            raise FakeApiError('content rejected', FakeResponse(400))

        with patch(_POST_PATH, failing_post):
            raised = self._dispatch_expecting_failure(live_post)
        self.assertIsInstance(raised, FakeApiError)

        self.assertEqual(live_post.failure_category, 'permanent')
        self.assertEqual(live_post.state, 'failed')
        self.assertFalse(
            live_post.next_retry_date,
            "A permanent failure must not schedule a retry")

    def test_revoked_auth_is_permanent(self):
        post = self._create_post()
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': post.id,
            'social_account_id': self.account.id,
        })
        self.assertEqual(
            live_post._classify_failure(
                FakeApiError('revoked', FakeResponse(401))),
            'permanent')

    def test_rate_limit_is_transient(self):
        post = self._create_post()
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': post.id,
            'social_account_id': self.account.id,
        })
        self.assertEqual(
            live_post._classify_failure(
                FakeApiError('slow down', FakeResponse(429))),
            'transient')

    def test_backoff_increases_and_is_capped(self):
        post = self._create_post()
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': post.id,
            'social_account_id': self.account.id,
        })
        first = live_post._get_retry_delay_seconds(1)
        second = live_post._get_retry_delay_seconds(2)
        third = live_post._get_retry_delay_seconds(3)
        self.assertLess(first, second)
        self.assertLess(second, third)
        cap = float(self.env['ir.config_parameter'].get_param(
            'social_publish_retry_max_seconds', '3600'))
        self.assertLessEqual(live_post._get_retry_delay_seconds(50), cap)

    def test_attempts_are_bounded(self):
        """ Past the attempt ceiling a transient failure is terminal. """
        post = self._create_post()
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': post.id,
            'social_account_id': self.account.id,
            'max_attempts': 2,
        })
        live_post.attempt_count = 1

        def failing_post(lp):
            raise FakeApiError('upstream down', FakeResponse(503))

        with patch(_POST_PATH, failing_post):
            raised = self._dispatch_expecting_failure(live_post)
        self.assertIsInstance(raised, FakeApiError)

        self.assertEqual(live_post.attempt_count, 2)
        self.assertEqual(live_post.failure_category, 'transient')
        self.assertEqual(
            live_post.state, 'failed',
            "Out of attempts, a transient failure is terminal too")
        self.assertFalse(live_post.next_retry_date)


@tagged('post_install', '-at_install')
class TestPublishRetract(PublishHardeningCommon):
    """ A published item must be removable from the network, by a human. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.retracting_user = cls.env['res.users'].create({
            'name': 'Retracting User',
            'login': 'retracting_user',
            'groups_id': [(6, 0, [
                cls.env.ref('social_marketing.group_social_marketing_manager').id,
            ])],
        })

    def _publish(self):
        post = self._create_post()

        def publishing(live_post):
            return live_post.write({
                'state': 'posted',
                'platform_post_id': 'urn:li:share:12345',
                'permalink': 'https://example.invalid/p/12345',
            })

        with patch(_POST_PATH, publishing):
            post.action_post()
            # action_post enqueues a job per live post; run it inline.
            live_post = post.live_post_ids
            step = post.pipeline_step_ids.filtered(
                lambda s: s.live_post_id == live_post)
            live_post._dispatch_post(step_id=step.id)
        self.assertEqual(live_post.state, 'posted')
        return post, live_post

    def test_retract_records_step_and_clears_published_state(self):
        post, live_post = self._publish()
        steps_before = len(post.pipeline_step_ids)

        live_post.with_user(self.retracting_user).action_retract()

        self.assertEqual(
            live_post.state, 'retracted',
            "Retracting must clear the published state")
        retract_steps = post.pipeline_step_ids.filtered(
            lambda s: s.stage == 'retracted')
        self.assertEqual(len(retract_steps), 1)
        self.assertEqual(retract_steps.state, 'done')
        self.assertGreater(len(post.pipeline_step_ids), steps_before)

    def test_platform_identity_is_stored_at_publish(self):
        post, live_post = self._publish()
        self.assertEqual(live_post.platform_post_id, 'urn:li:share:12345')
        self.assertEqual(
            live_post.permalink, 'https://example.invalid/p/12345')

    def test_retract_is_not_callable_by_automation(self):
        """ No cron or job may pull published content down on its own. """
        post, live_post = self._publish()
        with self.assertRaises(UserError):
            live_post.sudo().action_retract()
        self.assertEqual(live_post.state, 'posted')

    def test_retract_requires_a_published_post(self):
        post = self._create_post()
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': post.id,
            'social_account_id': self.account.id,
        })
        with self.assertRaises(UserError):
            live_post.with_user(self.retracting_user).action_retract()


@tagged('post_install', '-at_install')
class TestPreflightValidation(PublishHardeningCommon):
    """ Platform rules are checked at scheduling time, from data. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.platform = cls.env['social_marketing.platform'].create({
            'name': 'Testagram',
            'code': 'testagram',
            'max_text_length': 100,
            'max_image_count': 2,
            'allowed_media_types': 'image',
        })

    def test_too_long_text_is_rejected_at_scheduling(self):
        post = self._create_post(
            message='x' * 200, platforms=[self.platform])
        with self.assertRaises(ValidationError) as caught:
            post.action_schedule()
        message = str(caught.exception)
        self.assertIn(
            'Testagram', message,
            "The error must name the platform that rejected the post")
        self.assertIn('100', message, "The error must name the broken rule")
        self.assertEqual(
            post.state, 'draft',
            "A post failing pre-flight must not become scheduled")

    def test_within_limit_schedules_fine(self):
        post = self._create_post(
            message='x' * 50, platforms=[self.platform])
        post.action_schedule()
        self.assertEqual(post.state, 'scheduled')

    def test_no_platform_no_limit(self):
        post = self._create_post(message='x' * 5000)
        post.action_schedule()
        self.assertEqual(post.state, 'scheduled')

    def test_too_many_images_is_rejected(self):
        attachments = self.env['ir.attachment'].create([{
            'name': 'image-%s.png' % index,
            'mimetype': 'image/png',
            'datas': b'aGVsbG8=',
        } for index in range(3)])
        post = self._create_post(message='short', platforms=[self.platform])
        post.image_ids = [(6, 0, attachments.ids)]
        with self.assertRaises(ValidationError) as caught:
            post.action_schedule()
        self.assertIn('Testagram', str(caught.exception))

    def test_limits_come_from_platform_data(self):
        """ Changing the data changes the rule, no code involved. """
        post = self._create_post(
            message='x' * 200, platforms=[self.platform])
        self.platform.max_text_length = 500
        post.action_schedule()
        self.assertEqual(post.state, 'scheduled')


@tagged('post_install', '-at_install')
class TestTokenHealth(PublishHardeningCommon):
    """ Expiring credentials must be visible before publishing stops. """

    def _make_account(self, name, expiry):
        return self.env['social_marketing.account'].create({
            'name': name,
            'media_id': self.media.id,
            'utm_medium_id': self.env['utm.medium'].create(
                {'name': 'Medium %s' % name}).id,
            'token_expiry_date': expiry,
        })

    def test_warning_fires_inside_the_window(self):
        now = fields.Datetime.now()
        expiring = self._make_account('Expiring', now + timedelta(days=3))

        warned = self.env['social_marketing.account']._cron_check_token_expiry()

        self.assertIn(expiring, warned)
        self.assertTrue(expiring.token_warning_sent_date)
        self.assertEqual(expiring.token_expiry_state, 'expiring')
        self.assertTrue(
            expiring.activity_ids,
            "The warning must be visible to a human, not only in the log")

    def test_warning_does_not_fire_outside_the_window(self):
        now = fields.Datetime.now()
        healthy = self._make_account('Healthy', now + timedelta(days=60))

        warned = self.env['social_marketing.account']._cron_check_token_expiry()

        self.assertNotIn(healthy, warned)
        self.assertFalse(healthy.token_warning_sent_date)
        self.assertEqual(healthy.token_expiry_state, 'ok')
        self.assertFalse(healthy.activity_ids)

    def test_expired_token_is_flagged(self):
        now = fields.Datetime.now()
        expired = self._make_account('Expired', now - timedelta(days=1))
        self.assertEqual(expired.token_expiry_state, 'expired')

    def test_account_without_expiry_is_unknown_and_never_warned(self):
        account = self.env['social_marketing.account'].create({
            'name': 'No Expiry',
            'media_id': self.media.id,
            'utm_medium_id': self.env['utm.medium'].create(
                {'name': 'Medium No Expiry'}).id,
        })
        warned = self.env['social_marketing.account']._cron_check_token_expiry()
        self.assertEqual(account.token_expiry_state, 'unknown')
        self.assertNotIn(account, warned)

    def test_warning_is_not_repeated_for_the_same_expiry(self):
        now = fields.Datetime.now()
        expiring = self._make_account('Nagging', now + timedelta(days=2))

        first = self.env['social_marketing.account']._cron_check_token_expiry()
        self.assertIn(expiring, first)
        activities_after_first = len(expiring.activity_ids)

        second = self.env['social_marketing.account']._cron_check_token_expiry()
        self.assertNotIn(expiring, second)
        self.assertEqual(len(expiring.activity_ids), activities_after_first)
