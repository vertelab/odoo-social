# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
"""Inbox semantics on social_marketing.stream.post.

The stream post is the incoming item. These tests cover the queue behaviour
added on top of it: the state an item lands in, the interaction type derived
from the stream type, and the transitions with their bookkeeping.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class InboxCommon(TransactionCase):

    def setUp(self):
        super().setUp()
        self.media = self.env['social_marketing.media'].create({
            'name': 'Test Media',
        })
        self.account = self.env['social_marketing.account'].create({
            'name': 'Test Account',
            'media_id': self.media.id,
        })

    def _stream_type(self, technical, interaction_type=None):
        vals = {
            'name': technical,
            'stream_type': technical,
            'media_id': self.media.id,
        }
        if interaction_type is not None:
            vals['interaction_type'] = interaction_type
        return self.env['social_marketing.stream.type'].create(vals)

    def _stream(self, stream_type):
        return self.env['social_marketing.stream'].create({
            'media_id': self.media.id,
            'social_account_id': self.account.id,
            'stream_type_id': stream_type.id,
        })

    def _post(self, stream, **vals):
        values = {
            'stream_id': stream.id,
            'message': 'Hello',
            'author_name': 'Someone Outside',
            'published_date': fields.Datetime.now(),
        }
        values.update(vals)
        return self.env['social_marketing.stream.post'].create(values)


class TestInboxIntake(InboxCommon):

    def test_item_lands_new(self):
        stream = self._stream(self._stream_type('t_comments', 'comment'))
        post = self._post(stream)
        self.assertEqual(post.inbox_state, 'new')
        self.assertFalse(post.assigned_user_id)
        self.assertFalse(post.answered_by_user_id)
        self.assertFalse(post.answered_date)

    def test_interaction_type_follows_stream_type(self):
        for technical, interaction in [
            ('t_comment', 'comment'),
            ('t_like', 'like'),
            ('t_share', 'share'),
            ('t_mention', 'mention'),
            ('t_dm', 'direct_message'),
        ]:
            stream = self._stream(self._stream_type(technical, interaction))
            post = self._post(stream)
            self.assertEqual(post.interaction_type, interaction)

    def test_unknown_stream_type_defaults_to_other(self):
        # A stream type that declares nothing must not be guessed at.
        stream = self._stream(self._stream_type('t_undeclared'))
        post = self._post(stream)
        self.assertEqual(post.interaction_type, 'other')
        self.assertFalse(post.is_private)

    def test_direct_message_is_private(self):
        stream = self._stream(self._stream_type('t_dm_private', 'direct_message'))
        post = self._post(stream)
        self.assertTrue(post.is_private)

    def test_public_interaction_is_not_private(self):
        for interaction in ('comment', 'like', 'share', 'mention', 'other'):
            stream = self._stream(
                self._stream_type('t_pub_%s' % interaction, interaction))
            self.assertFalse(self._post(stream).is_private)

    def test_newest_first(self):
        stream = self._stream(self._stream_type('t_order', 'comment'))
        now = fields.Datetime.now()
        older = self._post(stream, published_date=now - timedelta(days=2))
        newer = self._post(stream, published_date=now)
        found = self.env['social_marketing.stream.post'].search(
            [('stream_id', '=', stream.id)])
        self.assertEqual(found.ids[:2], [newer.id, older.id])


class TestInboxTransitions(InboxCommon):

    def setUp(self):
        super().setUp()
        self.stream = self._stream(self._stream_type('t_flow', 'comment'))
        self.post = self._post(self.stream)
        self.handler = self.env['res.users'].create({
            'name': 'Inbox Handler',
            'login': 'inbox_handler_test',
            'groups_id': [(4, self.env.ref(
                'social_marketing.group_social_marketing_user').id)],
        })

    def test_assign_to_current_user(self):
        self.post.with_user(self.handler).action_inbox_assign()
        self.assertEqual(self.post.inbox_state, 'assigned')
        self.assertEqual(self.post.assigned_user_id, self.handler)

    def test_assign_to_named_user(self):
        self.post.action_inbox_assign(user_id=self.handler.id)
        self.assertEqual(self.post.inbox_state, 'assigned')
        self.assertEqual(self.post.assigned_user_id, self.handler)

    def test_answer_records_who_and_when(self):
        before = fields.Datetime.now()
        self.post.with_user(self.handler).action_inbox_answered()
        self.assertEqual(self.post.inbox_state, 'answered')
        self.assertEqual(self.post.answered_by_user_id, self.handler)
        self.assertTrue(self.post.answered_date)
        self.assertGreaterEqual(self.post.answered_date, before)

    def test_close(self):
        self.post.action_inbox_close()
        self.assertEqual(self.post.inbox_state, 'closed')

    def test_ignore(self):
        self.post.action_inbox_ignore()
        self.assertEqual(self.post.inbox_state, 'ignored')
        self.assertFalse(self.post.answered_by_user_id)

    def test_reopen(self):
        self.post.action_inbox_close()
        self.post.action_inbox_reopen()
        self.assertEqual(self.post.inbox_state, 'new')

    def test_full_sequence_keeps_the_answer_record(self):
        self.post.with_user(self.handler).action_inbox_assign()
        self.post.with_user(self.handler).action_inbox_answered()
        self.post.with_user(self.handler).action_inbox_close()
        self.assertEqual(self.post.inbox_state, 'closed')
        self.assertEqual(self.post.assigned_user_id, self.handler)
        self.assertEqual(self.post.answered_by_user_id, self.handler)


class TestInboxRetention(InboxCommon):
    """Direct messages are personal data and must not be kept forever.

    Public items are a different category and are never touched by the cron.
    """

    def setUp(self):
        super().setUp()
        self.dm_stream = self._stream(
            self._stream_type('t_ret_dm', 'direct_message'))
        self.public_stream = self._stream(
            self._stream_type('t_ret_comment', 'comment'))
        self.Post = self.env['social_marketing.stream.post']
        self.env['ir.config_parameter'].sudo().set_param(
            'social_marketing.dm_retention_days', '30')

    def _aged(self, stream, days):
        return self._post(
            stream, published_date=fields.Datetime.now() - timedelta(days=days))

    def test_expired_private_item_is_deleted(self):
        old_dm = self._aged(self.dm_stream, 60)
        deleted = self.Post._cron_delete_expired_private_posts()
        self.assertEqual(deleted, 1)
        self.assertFalse(old_dm.exists())

    def test_recent_private_item_is_kept(self):
        recent_dm = self._aged(self.dm_stream, 5)
        self.Post._cron_delete_expired_private_posts()
        self.assertTrue(recent_dm.exists())

    def test_old_public_item_is_kept(self):
        old_comment = self._aged(self.public_stream, 400)
        self.Post._cron_delete_expired_private_posts()
        self.assertTrue(old_comment.exists())

    def test_private_item_without_published_date_ages_on_create_date(self):
        dm = self._post(self.dm_stream, published_date=False)
        self.assertTrue(dm.is_private)
        # Fresh record: create_date is now, so it must survive.
        self.Post._cron_delete_expired_private_posts()
        self.assertTrue(dm.exists())
        # Backdate the creation and it must go.
        self.env.cr.execute(
            "UPDATE social_marketing_stream_post SET create_date = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(days=90), dm.id))
        dm.invalidate_recordset()
        self.Post._cron_delete_expired_private_posts()
        self.assertFalse(dm.exists())

    def test_running_twice_does_not_error(self):
        old_dm = self._aged(self.dm_stream, 60)
        recent_dm = self._aged(self.dm_stream, 1)
        old_comment = self._aged(self.public_stream, 400)
        first = self.Post._cron_delete_expired_private_posts()
        second = self.Post._cron_delete_expired_private_posts()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertFalse(old_dm.exists())
        self.assertTrue(recent_dm.exists())
        self.assertTrue(old_comment.exists())

    def test_retention_period_is_configurable(self):
        dm = self._aged(self.dm_stream, 45)
        self.env['ir.config_parameter'].sudo().set_param(
            'social_marketing.dm_retention_days', '90')
        self.assertEqual(self.Post._cron_delete_expired_private_posts(), 0)
        self.assertTrue(dm.exists())
        self.env['ir.config_parameter'].sudo().set_param(
            'social_marketing.dm_retention_days', '10')
        self.assertEqual(self.Post._cron_delete_expired_private_posts(), 1)
        self.assertFalse(dm.exists())

    def test_zero_disables_deletion(self):
        dm = self._aged(self.dm_stream, 3650)
        self.env['ir.config_parameter'].sudo().set_param(
            'social_marketing.dm_retention_days', '0')
        self.assertEqual(self.Post._cron_delete_expired_private_posts(), 0)
        self.assertTrue(dm.exists())

    def test_unparseable_value_deletes_nothing(self):
        dm = self._aged(self.dm_stream, 3650)
        self.env['ir.config_parameter'].sudo().set_param(
            'social_marketing.dm_retention_days', 'thirty')
        self.assertEqual(self.Post._cron_delete_expired_private_posts(), 0)
        self.assertTrue(dm.exists())

    def test_cron_record_points_at_the_method(self):
        cron = self.env.ref('social_marketing.ir_cron_delete_expired_private_posts')
        self.assertEqual(cron.model_id.model, 'social_marketing.stream.post')
        self.assertIn('_cron_delete_expired_private_posts', cron.code)
