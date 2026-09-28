# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import base64
from unittest.mock import patch

from odoo.tests.common import TransactionCase


def fake_render_scene(self, scene, width, height, bindings, format):
    """Stand-in for the HTTP call to the Node render service."""
    return self.env['ir.attachment'].create({
        'name': '%s.%s' % (self.name, format),
        'datas': base64.b64encode(b'\x89PNG fake image'),
        'mimetype': 'image/png',
        'res_model': self._name,
        'res_id': self.id,
    })


class TestPreviewLifecycle(TransactionCase):
    """Preview attachments do not accumulate (spec: image-templates)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.template = cls.env['social.image.template'].create({
            'name': 'Lifecycle Template',
            'model_id': cls.env['ir.model']._get('res.partner').id,
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Lifecycle Partner',
        })
        cls.wizard = cls.env['social.image.render.wizard'].create({
            'template_id': cls.template.id,
            'record_model': 'res.partner',
            'record_id': cls.partner.id,
        })

    def _preview_attachments(self):
        return self.env['ir.attachment'].search([
            ('name', '=', 'Lifecycle Template (preview).png'),
            ('res_model', '=', 'social.image.template'),
            ('res_id', '=', self.template.id),
        ])

    def test_double_refresh_leaves_one_attachment(self):
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene):
            self.wizard.action_preview()
            self.wizard.action_preview()
        previews = self._preview_attachments()
        self.assertEqual(len(previews), 1)
        self.assertEqual(self.wizard.preview_attachment_id, previews)

    def test_cron_removes_previews_older_than_24h(self):
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene):
            self.wizard.action_preview()
        aged = self.wizard.preview_attachment_id
        self.env.cr.execute(
            "UPDATE ir_attachment SET create_date = now() - interval '25 hours'"
            " WHERE id = %s", [aged.id])
        # An unrelated old attachment and the fresh preview state must
        # survive the cleanup.
        bystander = self.env['ir.attachment'].create({
            'name': 'unrelated.png',
            'datas': base64.b64encode(b'\x89PNG fake image'),
            'mimetype': 'image/png',
        })
        self.env.cr.execute(
            "UPDATE ir_attachment SET create_date = now() - interval '25 hours'"
            " WHERE id = %s", [bystander.id])
        self.env['social.image.render.wizard']._cron_cleanup_previews()
        self.assertFalse(aged.exists())
        self.assertTrue(bystander.exists())
        self.assertFalse(self._preview_attachments())
