# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import base64
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


def fake_render_scene(self, scene, width, height, bindings, format):
    """Stand-in for the HTTP call to the Node render service: store a
    fake PNG as an attachment, exactly like the real _render_scene."""
    return self.env['ir.attachment'].create({
        'name': '%s.%s' % (self.name, format),
        'datas': base64.b64encode(b'\x89PNG fake image'),
        'mimetype': 'image/png',
    })


class TestSocialImageRenderWizard(TransactionCase):

    def setUp(self):
        super().setUp()
        model_partner = self.env['ir.model']._get('res.partner')
        self.template = self.env['social.image.template'].create({
            'name': 'Wizard Test Template',
            'model_id': model_partner.id,
        })
        self.partner = self.env['res.partner'].create({'name': 'Wizard Partner'})

    def _new_wizard(self, post=None, **values):
        context = {}
        if post is not None:
            context = {
                'active_id': post.id,
                'active_model': 'social_marketing.post',
            }
        values.setdefault('template_id', self.template.id)
        values.setdefault('record_model', 'res.partner')
        values.setdefault('record_id', self.partner.id)
        return self.env['social.image.render.wizard'].with_context(
            **context).create(values)

    def test_render_now_attaches_png_to_post(self):
        post = self.env['social_marketing.post'].create({
            'message': 'Wizard target post',
        })
        wizard = self._new_wizard(post=post)
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene):
            wizard.action_render()
        self.assertEqual(len(post.image_ids), 1)
        self.assertEqual(post.image_ids.mimetype, 'image/png')

    def test_on_publish_stores_pending_render(self):
        post = self.env['social_marketing.post'].create({
            'message': 'Wizard publish post',
        })
        wizard = self._new_wizard(
            post=post, render_timing='on_publish', variant_index=1)
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene):
            wizard.action_render()
        self.assertFalse(post.image_ids)
        self.assertTrue(post.image_render_pending)
        self.assertEqual(post.image_template_id, self.template)
        self.assertEqual(post.image_template_record_model, 'res.partner')
        self.assertEqual(post.image_template_record_id, self.partner.id)
        self.assertEqual(post.image_variant_index, 1)

    def test_preview_marks_attachment_as_preview(self):
        wizard = self._new_wizard()
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene):
            wizard.action_preview()
        self.assertTrue(wizard.preview_attachment_id)
        self.assertIn('(preview)', wizard.preview_attachment_id.name)
        self.assertFalse(wizard.preview_error)

    def test_binding_mismatch_refused(self):
        template_users = self.env['social.image.template'].create({
            'name': 'Users Template',
            'model_id': self.env['ir.model']._get('res.users').id,
        })
        wizard = self.env['social.image.render.wizard'].create({
            'template_id': template_users.id,
            'record_model': 'res.partner',
            'record_id': self.partner.id,
        })
        self.assertTrue(wizard.binding_mismatch)
        with self.assertRaises(UserError):
            wizard.action_render()

    def test_free_form_template_uses_placeholder_lines(self):
        free_template = self.env['social.image.template'].create({
            'name': 'Free Form Template',
        })
        wizard = self.env['social.image.render.wizard'].create({
            'template_id': free_template.id,
        })
        self.assertFalse(wizard.has_binding_model)
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene):
            wizard.action_render()
        attachment = self.env['ir.attachment'].search([
            ('name', '=', 'Free Form Template.png'),
        ])
        self.assertEqual(len(attachment), 1)


class TestSocialImageBulkWizard(TransactionCase):

    def setUp(self):
        super().setUp()
        model_partner = self.env['ir.model']._get('res.partner')
        self.template = self.env['social.image.template'].create({
            'name': 'Bulk Test Template',
            'model_id': model_partner.id,
        })
        self.partners = self.env['res.partner'].create([
            {'name': 'Bulk Partner %s' % index} for index in range(3)
        ])

    def _new_bulk_wizard(self, records, **values):
        values.setdefault('template_id', self.template.id)
        return self.env['social.image.bulk.wizard'].with_context(
            active_model=records._name,
            active_ids=records.ids,
        ).create(values)

    def test_bulk_creates_draft_posts_with_images(self):
        wizard = self._new_bulk_wizard(self.partners)
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene):
            wizard.action_create_posts()
        self.assertEqual(wizard.state, 'done')
        self.assertEqual(wizard.created_count, 3)
        posts = wizard.created_post_ids
        self.assertEqual(len(posts), 3)
        self.assertEqual(set(posts.mapped('state')), {'draft'})
        self.assertEqual(
            set(posts.mapped('image_template_record_id')),
            set(self.partners.ids),
        )
        for post in posts:
            self.assertEqual(len(post.image_ids), 1)
            self.assertEqual(post.image_ids.mimetype, 'image/png')

    def test_bulk_model_mismatch_refused_before_creating(self):
        users = self.env['res.users'].search([], limit=2)
        wizard = self._new_bulk_wizard(users)
        posts_before = self.env['social_marketing.post'].search_count([])
        with self.assertRaises(UserError):
            wizard.action_create_posts()
        self.assertEqual(
            self.env['social_marketing.post'].search_count([]),
            posts_before,
        )

    def test_bulk_partial_failure_keeps_successes(self):
        doomed = self.partners[1]
        original = type(self.template).render_for_record

        def flaky_render(self, record, format='png', variant_index=0):
            if record.id == doomed.id:
                raise UserError('missing required image')
            return original(self, record, format=format,
                            variant_index=variant_index)

        wizard = self._new_bulk_wizard(self.partners)
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene), \
             patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate.render_for_record',
                flaky_render):
            wizard.action_create_posts()
        self.assertEqual(wizard.created_count, 2)
        self.assertIn(doomed.name, wizard.failure_details)
        self.assertIn('missing required image', wizard.failure_details)
        posts = self.env['social_marketing.post'].search([
            ('image_template_id', '=', self.template.id),
        ])
        self.assertEqual(len(posts), 2)

    def test_bulk_all_fail_raises_with_list(self):
        def broken_render(self, record, format='png', variant_index=0):
            raise UserError('render service unreachable')

        wizard = self._new_bulk_wizard(self.partners)
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate.render_for_record',
                broken_render):
            with self.assertRaises(UserError) as cm:
                wizard.action_create_posts()
        for partner in self.partners:
            self.assertIn(partner.name, str(cm.exception))
        posts = self.env['social_marketing.post'].search([
            ('image_template_id', '=', self.template.id),
        ])
        self.assertFalse(posts)
