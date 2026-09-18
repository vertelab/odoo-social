# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPublishPipelineDispatch(TransactionCase):
    """ Core publishing pipeline: job-queue fan-out, dispatch, aggregation
    and rate limiting. Approval/policy stages are covered by social_planner
    tests (they require the communication policy layer). """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].set_param(
            'social_publish_rate_limit_delay_seconds', '0.0')
        cls.media = cls.env['social_marketing.media'].create({
            'name': 'Test Media',
        })
        cls.medium = cls.env['utm.medium'].create({'name': 'Test Medium'})
        cls.account_1 = cls.env['social_marketing.account'].create({
            'name': 'Account 1',
            'media_id': cls.media.id,
            'utm_medium_id': cls.medium.id,
        })
        cls.account_2 = cls.env['social_marketing.account'].create({
            'name': 'Account 2',
            'media_id': cls.media.id,
            'utm_medium_id': cls.medium.id,
        })

    def _create_post(self, message='Hello world', accounts=None):
        return self.env['social_marketing.post'].create({
            'message': message,
            'account_ids': [
                (6, 0, [a.id for a in (accounts or [self.account_1])])],
        })

    def test_dispatch_creates_one_job_per_account(self):
        post = self._create_post(
            accounts=[self.account_1, self.account_2])
        with patch(
            'odoo.addons.social_marketing.models.social_marketing_live_post.SocialLivePost._post',  # noqa: E501
            lambda self: self.write({'state': 'posted'}),
        ):
            post.action_post()
        self.assertEqual(post.state, 'posting')
        jobs = self.env['queue.job'].search([
            ('identity_key', 'like', 'social_publish_live_%')])
        self.assertEqual(len(jobs), 2)
        dispatched = post.pipeline_step_ids.filtered(
            lambda s: s.stage == 'dispatched')
        self.assertEqual(len(dispatched), 2)
        self.assertTrue(all(s.state == 'pending' for s in dispatched))

    def test_dispatch_completes_post(self):
        post = self._create_post(
            accounts=[self.account_1, self.account_2])
        with patch(
            'odoo.addons.social_marketing.models.social_marketing_live_post.SocialLivePost._post',  # noqa: E501
            lambda self: self.write({'state': 'posted'}),
        ):
            post.action_post()
            for live_post in post.live_post_ids:
                step = post.pipeline_step_ids.filtered(
                    lambda s, lp=live_post: s.live_post_id == lp)
                live_post._dispatch_post(step_id=step.id)
        self.assertEqual(post.state, 'posted')
        self.assertIn(
            'completed', post.pipeline_step_ids.mapped('stage'))
        published = post.pipeline_step_ids.filtered(
            lambda s: s.stage == 'published')
        self.assertEqual(len(published), 2)

    def test_partial_failure_still_completes_post(self):
        post = self._create_post(
            accounts=[self.account_1, self.account_2])

        def flaky_post(live_post):
            if live_post.social_account_id == self.account_2:
                raise Exception('API rate limited')
            return live_post.write({'state': 'posted'})

        with patch(
            'odoo.addons.social_marketing.models.social_marketing_live_post.SocialLivePost._post',  # noqa: E501
            flaky_post,
        ):
            post.action_post()
            for live_post in post.live_post_ids:
                step = post.pipeline_step_ids.filtered(
                    lambda s, lp=live_post: s.live_post_id == lp)
                try:
                    live_post._dispatch_post(step_id=step.id)
                except Exception:
                    pass
        self.assertEqual(post.state, 'posted')
        self.assertIn(
            'completed', post.pipeline_step_ids.mapped('stage'))
        failed = post.pipeline_step_ids.filtered(
            lambda s: s.stage == 'failed')
        self.assertTrue(failed)
        failed_live = post.live_post_ids.filtered(
            lambda lp: lp.state == 'failed')
        self.assertEqual(len(failed_live), 1)

    def test_rate_limit_delay_global_default(self):
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': self._create_post().id,
            'social_account_id': self.account_1.id,
        })
        self.env['ir.config_parameter'].set_param(
            'social_publish_rate_limit_delay_seconds', '0.0')
        self.assertEqual(live_post._get_rate_limit_delay(), 0.0)
        self.env['ir.config_parameter'].set_param(
            'social_publish_rate_limit_delay_seconds', '2.5')
        self.assertEqual(live_post._get_rate_limit_delay(), 2.5)

    def test_rate_limit_delay_per_media_override(self):
        live_post = self.env['social_marketing.live.post'].create({
            'post_id': self._create_post().id,
            'social_account_id': self.account_1.id,
        })
        self.env['ir.config_parameter'].set_param(
            'social_publish_rate_limit_delay_seconds', '2.5')
        limit = self.env['social.publish.rate.limit'].create({
            'media_id': self.media.id,
            'delay_seconds': 0.25,
        })
        self.assertEqual(live_post._get_rate_limit_delay(), 0.25)
        limit.unlink()
