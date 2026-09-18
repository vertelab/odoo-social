# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSocialPostCreation(TransactionCase):
    """ Regression tests for programmatic post creation.

    social_marketing.post._rec_name must resolve to 'message' (set on the
    post class itself, not only the template). Otherwise utm.source.mixin
    generates the utm source name from the wrong field and programmatic
    creation crashes with a null utm_source.name (NOT NULL violation).
    """

    def _create_minimal_post(self, message='Hello world'):
        """ Create a post with only a message — no name, no context. """
        return self.env['social_marketing.post'].create({
            'message': message,
        })

    def test_rec_name_is_message(self):
        self.assertEqual(
            self.env['social_marketing.post']._rec_name, 'message')

    def test_programmatic_creation_generates_utm_source_name(self):
        post = self._create_minimal_post('Hello from the regression test')
        self.assertTrue(post.source_id)
        self.assertTrue(post.source_id.name)
        # name is generated from the message (truncated to ~20 chars)
        self.assertTrue(post.source_id.name.startswith('Hello from the regre'))

    def test_programmatic_creation_without_message_raises_user_error(self):
        # An empty message is rejected with the model's own UserError, never
        # a utm_source.name NOT NULL database error.
        with self.assertRaises(UserError):
            self.env['social_marketing.post'].create({})
