# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

"""Name-based variant selection in both wizards (spec: wizard-bulk-create,
design decision D4). The stored field is the variant NAME; the index the
render path needs is resolved server-side at render time, falling back to
the primary variant with a warning when the name no longer exists."""

import base64
from unittest.mock import patch

from odoo.tests.common import TransactionCase

RENDER_SCENE_PATH = (
    'odoo.addons.social_image_creator.models.'
    'social_image_template.SocialImageTemplate._render_scene'
)


def capture_render_scene(calls):
    """Stand-in for the HTTP call to the Node render service: remember
    the canvas size of every render and store a fake attachment."""
    def fake(self, scene, width, height, bindings, format):
        calls.append((width, height))
        return self.env['ir.attachment'].create({
            'name': '%s.%s' % (self.name, format),
            'datas': base64.b64encode(b'\x89PNG fake image'),
            'mimetype': 'image/png',
        })
    return fake


TWO_VARIANTS = [
    {'name': 'Primary', 'width': 1200, 'height': 630,
     'scene_json': '{}', 'is_primary': True},
    {'name': 'Story', 'width': 1080, 'height': 1920,
     'scene_json': '{}', 'is_primary': False},
]

RENAMED_VARIANTS = [
    {'name': 'Primary', 'width': 1200, 'height': 630,
     'scene_json': '{}', 'is_primary': True},
    {'name': 'Tall', 'width': 1080, 'height': 1920,
     'scene_json': '{}', 'is_primary': False},
]


class TestRenderWizardVariantSelection(TransactionCase):

    def setUp(self):
        super().setUp()
        model_partner = self.env['ir.model']._get('res.partner')
        self.template = self.env['social.image.template'].create({
            'name': 'Variant Wizard Template',
            'model_id': model_partner.id,
            'variants': [dict(v) for v in TWO_VARIANTS],
        })
        self.partner = self.env['res.partner'].create({'name': 'Variant Partner'})

    def _new_wizard(self, **values):
        values.setdefault('template_id', self.template.id)
        values.setdefault('record_model', 'res.partner')
        values.setdefault('record_id', self.partner.id)
        return self.env['social.image.render.wizard'].create(values)

    def test_named_variant_renders_chosen_size(self):
        calls = []
        wizard = self._new_wizard(variant_name='Story')
        self.assertEqual(wizard.variant_index, 1)
        self.assertFalse(wizard.variant_fallback)
        with patch(RENDER_SCENE_PATH, capture_render_scene(calls)):
            wizard.action_render()
        self.assertEqual(calls, [(1080, 1920)])

    def test_primary_variant_preselected_on_template_change(self):
        wizard = self._new_wizard(variant_name='Story')
        wizard._onchange_template_id()
        self.assertEqual(wizard.variant_name, 'Primary')
        self.assertFalse(wizard.variant_fallback)

    def test_primary_fallback_after_variant_rename(self):
        calls = []
        wizard = self._new_wizard(variant_name='Story')
        self.template.set_variants([dict(v) for v in RENAMED_VARIANTS])
        self.assertTrue(wizard.variant_fallback)
        self.assertEqual(wizard.variant_index, 0)
        self.assertIn('Story', wizard.variant_fallback_message)
        with patch(RENDER_SCENE_PATH, capture_render_scene(calls)):
            wizard.action_render()
        self.assertEqual(calls, [(1200, 630)])

    def test_single_variant_preselected(self):
        template = self.env['social.image.template'].create({
            'name': 'Single Variant Template',
            'model_id': self.env['ir.model']._get('res.partner').id,
        })
        wizard = self.env['social.image.render.wizard'].create({
            'template_id': template.id,
        })
        self.assertFalse(wizard.variant_name)
        wizard._onchange_template_id()
        self.assertEqual(wizard.variant_name, 'Primary')
        self.assertFalse(wizard.variant_fallback)

    def test_legacy_index_write_still_resolves(self):
        """API callers that still pass the old integer keep working: the
        inverse maps the index back to the variant name (decision D4)."""
        wizard = self._new_wizard()
        wizard.variant_index = 1
        self.assertEqual(wizard.variant_name, 'Story')
        self.assertEqual(wizard.variant_index, 1)


class TestBulkWizardVariantSelection(TransactionCase):

    def setUp(self):
        super().setUp()
        model_partner = self.env['ir.model']._get('res.partner')
        self.template = self.env['social.image.template'].create({
            'name': 'Variant Bulk Template',
            'model_id': model_partner.id,
            'variants': [dict(v) for v in TWO_VARIANTS],
        })
        self.partners = self.env['res.partner'].create([
            {'name': 'Bulk Variant %s' % index} for index in range(2)
        ])

    def _new_bulk_wizard(self, records, **values):
        values.setdefault('template_id', self.template.id)
        return self.env['social.image.bulk.wizard'].with_context(
            active_model=records._name,
            active_ids=records.ids,
        ).create(values)

    def test_named_variant_used_for_every_post(self):
        calls = []
        wizard = self._new_bulk_wizard(self.partners, variant_name='Story')
        self.assertEqual(wizard.variant_index, 1)
        with patch(RENDER_SCENE_PATH, capture_render_scene(calls)):
            wizard.action_create_posts()
        self.assertEqual(calls, [(1080, 1920)] * 2)
        self.assertEqual(wizard.created_count, 2)
        self.assertEqual(
            set(wizard.created_post_ids.mapped('image_variant_index')), {1})

    def test_primary_fallback_after_variant_rename(self):
        calls = []
        wizard = self._new_bulk_wizard(self.partners, variant_name='Story')
        self.template.set_variants([dict(v) for v in RENAMED_VARIANTS])
        self.assertTrue(wizard.variant_fallback)
        self.assertIn('Story', wizard.variant_fallback_message)
        with patch(RENDER_SCENE_PATH, capture_render_scene(calls)):
            wizard.action_create_posts()
        self.assertEqual(calls, [(1200, 630)] * 2)
        self.assertEqual(
            set(wizard.created_post_ids.mapped('image_variant_index')), {0})

    def test_single_variant_preselected(self):
        template = self.env['social.image.template'].create({
            'name': 'Single Variant Bulk Template',
            'model_id': self.env['ir.model']._get('res.partner').id,
        })
        wizard = self.env['social.image.bulk.wizard'].with_context(
            active_model='res.partner',
            active_ids=self.partners.ids,
        ).create({'template_id': template.id})
        self.assertFalse(wizard.variant_name)
        wizard._onchange_template_id()
        self.assertEqual(wizard.variant_name, 'Primary')
        self.assertFalse(wizard.variant_fallback)
