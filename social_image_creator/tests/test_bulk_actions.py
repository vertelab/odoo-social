# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo.tests.common import TransactionCase

from odoo.addons.social_image_creator.models.social_image_template import (
    BULK_ACTION_NAME,
)


class TestBulkActionSync(TransactionCase):
    """Dynamic server actions for bulk creation (spec: wizard-bulk-create,
    design decision D5). Every model bound by at least one template gets
    an action named 'Create Posts from Image Template' in its list view
    Action menu; the action disappears when no template binds the model
    anymore."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.users_model = cls.env['ir.model']._get('res.users')
        cls.template = cls.env['social.image.template'].create({
            'name': 'Bulk Action Template',
            'model_id': cls.partner_model.id,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Bulk Partner'})

    def _find_action(self, model_name):
        return self.env['ir.actions.server'].sudo().search([
            ('name', '=', BULK_ACTION_NAME),
            ('binding_model_id.model', '=', model_name),
        ])

    def test_action_created_for_bound_model(self):
        action = self._find_action('res.partner')
        self.assertEqual(len(action), 1)
        self.assertEqual(action.binding_type, 'action')
        self.assertEqual(action.state, 'code')
        self.assertIn('social.image.bulk.wizard', action.code)

    def test_action_appears_in_binding_lookup(self):
        action = self._find_action('res.partner')
        binding = self.env['ir.actions.binding'].sudo().search([
            ('action_id', '=', action.id),
        ])
        self.assertEqual(len(binding), 1)

    def test_action_removed_after_rebind(self):
        self.template.write({'model_id': self.users_model.id})
        self.assertFalse(self._find_action('res.partner'))
        self.assertTrue(self._find_action('res.users'))

    def test_action_removed_after_last_template_deleted(self):
        self.template.unlink()
        self.assertFalse(self._find_action('res.partner'))

    def test_action_kept_while_any_template_binds_model(self):
        other = self.env['social.image.template'].create({
            'name': 'Bulk Action Template 2',
            'model_id': self.partner_model.id,
        })
        self.assertEqual(len(self._find_action('res.partner')), 1)
        self.template.unlink()
        self.assertTrue(self._find_action('res.partner'))
        other.unlink()
        self.assertFalse(self._find_action('res.partner'))

    def test_sync_is_idempotent(self):
        self.env['social.image.template']._sync_bulk_actions()
        self.env['social.image.template']._sync_bulk_actions()
        self.assertEqual(len(self._find_action('res.partner')), 1)

    def test_action_opens_wizard_with_active_ids(self):
        action = self._find_action('res.partner')
        opened = action.with_context(
            active_model='res.partner',
            active_ids=self.partner.ids,
        ).run()
        self.assertEqual(opened.get('res_model'), 'social.image.bulk.wizard')
        wizard = self.env[opened['res_model']].with_context(
            **opened['context']).create({'template_id': self.template.id})
        self.assertEqual(wizard.source_model_name, 'Contact')
        self.assertEqual(wizard.source_record_count, 1)

    def test_manual_sync_button(self):
        result = self.env['social.image.template'].action_sync_bulk_actions()
        self.assertEqual(result.get('type'), 'ir.actions.client')
        self.assertEqual(result.get('tag'), 'display_notification')
        self.assertTrue(self._find_action('res.partner'))
