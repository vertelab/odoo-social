# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

""" The per-brand publishing killswitch.

Setting it must stop everything going out for that brand immediately, at the
point of dispatch and not merely in the interface, while leaving every other
brand publishing normally.
"""

from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

_POST_PATH = (
    'odoo.addons.social_marketing.models.social_marketing_live_post.'
    'SocialLivePost._post'
)


@tagged('post_install', '-at_install')
class TestBrandKillswitch(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['ir.config_parameter'].set_param(
            'social_publish_rate_limit_delay_seconds', '0.0')
        cls.media = cls.env['social_marketing.media'].create({
            'name': 'Killswitch Media',
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Killswitch Customer', 'is_company': True,
        })
        cls.brand_paused = cls.env['social.brand'].create({
            'name': 'Paused Brand', 'partner_id': cls.partner.id,
        })
        cls.brand_live = cls.env['social.brand'].create({
            'name': 'Live Brand', 'partner_id': cls.partner.id,
        })
        cls.account_paused = cls._make_account('Paused Account')
        cls.account_live = cls._make_account('Live Account')

    @classmethod
    def _make_account(cls, name):
        return cls.env['social_marketing.account'].create({
            'name': name,
            'media_id': cls.media.id,
            'utm_medium_id': cls.env['utm.medium'].create(
                {'name': 'Medium %s' % name}).id,
        })

    def _create_post(self, brand, account):
        return self.env['social_marketing.post'].create({
            'message': 'Killswitch test message',
            'brand_id': brand.id,
            'account_ids': [(6, 0, [account.id])],
        })

    def test_paused_brand_is_not_dispatched_while_others_are(self):
        """ One brand paused, the other keeps publishing in the same run. """
        self.brand_paused.write({
            'publishing_paused': True,
            'publishing_paused_reason': 'Customer dispute',
        })
        paused_post = self._create_post(self.brand_paused, self.account_paused)
        live_post_post = self._create_post(self.brand_live, self.account_live)

        published = []

        def publishing(live_post):
            published.append(live_post.social_account_id.id)
            return live_post.write({'state': 'posted'})

        posts = paused_post | live_post_post
        with patch(_POST_PATH, publishing):
            posts._action_post()
            # _action_post only enqueues; run every queued job inline.
            for live_post in posts.live_post_ids:
                live_post._dispatch_post()

        self.assertNotIn(
            self.account_paused.id, published,
            "Nothing may be published for a brand with publishing paused")
        self.assertEqual(
            paused_post.live_post_ids.state, 'failed')
        self.assertIn(
            'Paused Brand', paused_post.live_post_ids.failure_reason)

        self.assertEqual(
            live_post_post.live_post_ids.state, 'posted',
            "Another brand in the same run must still publish")

    def test_killswitch_stops_an_already_queued_job(self):
        """ Enforced at dispatch, so a job queued before the pause is stopped. """
        post = self._create_post(self.brand_paused, self.account_paused)
        published = []

        def publishing(live_post):
            published.append(live_post.id)
            return live_post.write({'state': 'posted'})

        with patch(_POST_PATH, publishing):
            post.action_post()
            live_post = post.live_post_ids
            live_post._dispatch_post()
            self.assertEqual(live_post.state, 'posted')

            # The killswitch is flipped after the job was created.
            self.brand_paused.publishing_paused = True
            live_post.write({'state': 'ready'})
            result = live_post._dispatch_post()

        self.assertFalse(result, "A paused brand's dispatch must not proceed")
        self.assertEqual(len(published), 1, "The second dispatch must not post")
        self.assertEqual(live_post.state, 'failed')

    def test_unpausing_restores_publishing(self):
        self.brand_paused.publishing_paused = True
        post = self._create_post(self.brand_paused, self.account_paused)

        def publishing(live_post):
            return live_post.write({'state': 'posted'})

        with patch(_POST_PATH, publishing):
            post._action_post()
            self.assertEqual(post.live_post_ids.state, 'failed')

            self.brand_paused.publishing_paused = False
            post.live_post_ids.write({'state': 'ready'})
            post.live_post_ids._dispatch_post()

        self.assertEqual(post.live_post_ids.state, 'posted')

    def test_check_publish_allowed_is_scoped_to_the_posts_brand(self):
        self.brand_paused.publishing_paused = True
        paused_post = self._create_post(self.brand_paused, self.account_paused)
        live_brand_post = self._create_post(self.brand_live, self.account_live)

        paused_live = self.env['social_marketing.live.post'].create({
            'post_id': paused_post.id,
            'social_account_id': self.account_paused.id,
        })
        live_live = self.env['social_marketing.live.post'].create({
            'post_id': live_brand_post.id,
            'social_account_id': self.account_live.id,
        })

        self.assertFalse(paused_live._check_publish_allowed()[0])
        self.assertTrue(live_live._check_publish_allowed()[0])
