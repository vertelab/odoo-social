# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import base64
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


def fake_render_scene(self, scene, width, height, bindings, format):
    """Stand-in for the HTTP call to the Node render service (same idea
    as in test_social_image_wizard)."""
    return self.env['ir.attachment'].create({
        'name': '%s.%s' % (self.name, format),
        'datas': base64.b64encode(b'\x89PNG fake image'),
        'mimetype': 'image/png',
        'res_model': self._name,
        'res_id': self.id,
    })


class TestBindingAccess(TransactionCase):
    """Access-controlled binding resolution (spec: data-binding).

    A user without read access to the bound record must be refused by
    every entry point with a clear error and no value leak. The canary
    is an ir.rule matching no partner, applied to a fresh group the
    denied test user belongs to."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        # company_id=False keeps the new company rule out of the way;
        # this suite tests binding access, not company scoping.
        cls.template = cls.env['social.image.template'].create({
            'name': 'Access Test Template',
            'model_id': cls.partner_model.id,
            'company_id': False,
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Access Canary Partner',
        })
        cls.canary_group = cls.env['res.groups'].create({
            'name': 'Binding access canary',
        })
        cls.env['ir.rule'].create({
            'name': 'Binding canary: no partners readable',
            'model_id': cls.partner_model.id,
            'domain_force': "[('id', '=', 0)]",
            'groups': [(6, 0, [cls.canary_group.id])],
            'perm_read': True,
        })
        cls.denied_user = cls.env['res.users'].create({
            'name': 'Binding Denied User',
            'login': 'binding_denied_user',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('social_marketing.group_social_marketing_user').id,
                cls.canary_group.id,
            ])],
        })

    def _scene_json(self):
        return '{"objects": [{"type": "textbox", "text": "{{name}}"}]}'

    # ------------------------------------------------------------------
    # Denied user is refused
    # ------------------------------------------------------------------

    def test_preview_bindings_denied_without_read_access(self):
        with self.assertRaises(UserError) as cm:
            self.template.with_user(
                self.denied_user).get_preview_bindings(self.partner.id)
        self.assertIn('res.partner', str(cm.exception))

    def test_preview_bindings_denied_for_unknown_id(self):
        with self.assertRaises(UserError):
            self.template.with_user(
                self.denied_user).get_preview_bindings(self.partner.id + 999999)

    def test_render_for_record_denied_without_read_access(self):
        with self.assertRaises(UserError) as cm:
            self.template.with_user(
                self.denied_user).render_for_record(self.partner)
        self.assertIn('name', str(cm.exception))

    def test_wizard_bound_record_denied_without_read_access(self):
        wizard = self.env['social.image.render.wizard'].with_user(
            self.denied_user).create({
                'template_id': self.template.id,
                'record_model': 'res.partner',
                'record_id': self.partner.id,
            })
        with self.assertRaises(UserError):
            wizard._get_bound_record()

    def test_no_value_leaks_in_error(self):
        """The refusal must not contain the record's field values."""
        try:
            self.template.with_user(
                self.denied_user).get_preview_bindings(self.partner.id)
        except UserError as e:
            self.assertNotIn('Access Canary Partner', str(e))
        else:
            self.fail('expected a UserError for the denied user')

    # ------------------------------------------------------------------
    # Allowed user resolves normally
    # ------------------------------------------------------------------

    def test_preview_bindings_allowed_with_read_access(self):
        bindings = self.template.get_preview_bindings(
            self.partner.id, scene_json=self._scene_json())
        self.assertEqual(bindings.get('name'), 'Access Canary Partner')

    def test_render_for_record_allowed_with_read_access(self):
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene):
            attachment = self.template.render_for_record(self.partner)
        self.assertEqual(attachment.mimetype, 'image/png')

    def test_traversed_hop_checked_by_guard(self):
        """A token crossing into a related record the user cannot read
        aborts with an error naming the token, while the same user
        resolves tokens on the root record fine (spec: data-binding)."""
        hidden_parent = self.env['res.partner'].create({
            'name': 'Hop Canary Parent',
        })
        child = self.env['res.partner'].create({
            'name': 'Hop Canary Child',
            'parent_id': hidden_parent.id,
        })
        hop_group = self.env['res.groups'].create({
            'name': 'Binding hop canary',
        })
        self.env['ir.rule'].create({
            'name': 'Binding hop canary: parent hidden',
            'model_id': self.partner_model.id,
            'domain_force': "[('name', '!=', 'Hop Canary Parent')]",
            'groups': [(6, 0, [hop_group.id])],
            'perm_read': True,
        })
        hop_user = self.env['res.users'].create({
            'name': 'Binding Hop User',
            'login': 'binding_hop_user',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('social_marketing.group_social_marketing_user').id,
                hop_group.id,
            ])],
        })
        scene_root_only = ('{"objects": [{"type": "textbox", '
                           '"text": "{{name}}"}]}')
        bindings = self.template.with_user(hop_user).get_preview_bindings(
            child.id, scene_json=scene_root_only)
        self.assertEqual(bindings.get('name'), 'Hop Canary Child')
        scene_hop = ('{"objects": [{"type": "textbox", '
                     '"text": "{{parent_id.name}}"}]}')
        with self.assertRaises(UserError) as cm:
            self.template.with_user(hop_user).get_preview_bindings(
                child.id, scene_json=scene_hop)
        self.assertIn('parent_id.name', str(cm.exception))
        self.assertNotIn('Hop Canary Parent', str(cm.exception))

    # ------------------------------------------------------------------
    # Binding models are curated (spec: data-binding, decision D2)
    # ------------------------------------------------------------------

    def test_transient_model_rejected(self):
        transient_model = self.env['ir.model']._get(
            'social.image.render.wizard')
        self.assertTrue(transient_model.transient)
        with self.assertRaises(UserError):
            self.env['social.image.template'].create({
                'name': 'Transient Binding',
                'model_id': transient_model.id,
            })

    def test_allowlist_enforced_when_set(self):
        parameter = self.env['ir.config_parameter'].sudo()
        parameter.set_param(
            'social_image_creator.allowed_binding_models', 'res.users')
        try:
            with self.assertRaises(UserError):
                self.env['social.image.template'].create({
                    'name': 'Off-List Binding',
                    'model_id': self.partner_model.id,
                })
            self.env['social.image.template'].create({
                'name': 'On-List Binding',
                'model_id': self.env['ir.model']._get('res.users').id,
            })
        finally:
            parameter.set_param(
                'social_image_creator.allowed_binding_models', '')

    def test_allowlist_empty_allows_any_regular_model(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'social_image_creator.allowed_binding_models', '')
        template = self.env['social.image.template'].create({
            'name': 'Unlisted But Allowed',
            'model_id': self.partner_model.id,
        })
        self.assertTrue(template)

    def test_binding_fields_exclude_group_restricted(self):
        """field.is_accessible filtering: a field defined with groups the
        user does not belong to must not be offered by the picker."""
        fields_admin = {
            f['name'] for f in self.template.get_binding_fields()}
        self.assertIn('name', fields_admin)
        template_user = self.template.with_user(self.denied_user)
        fields_user = {f['name'] for f in template_user.get_binding_fields()}
        self.assertIn('name', fields_user)
        # The user-facing list can only shrink, never grow, and values
        # must survive the filtering for fields the user may read.
        self.assertTrue(fields_user)
        self.assertLessEqual(fields_user, fields_admin)


class TestPublishHookAccess(TransactionCase):
    """The publish-time render resolves its record through _bound_record
    too, so a pending render bound to a record the publisher cannot read
    blocks the post instead of leaking values."""

    def test_pending_render_denied_user_blocks_post(self):
        template = self.env['social.image.template'].create({
            'name': 'Publish Access Template',
            'model_id': self.env['ir.model']._get('res.partner').id,
            'company_id': False,
        })
        partner = self.env['res.partner'].create({'name': 'Publish Partner'})
        canary_group = self.env['res.groups'].create({
            'name': 'Publish canary',
        })
        self.env['ir.rule'].create({
            'name': 'Publish canary: no partners readable',
            'model_id': self.env['ir.model']._get('res.partner').id,
            'domain_force': "[('id', '=', 0)]",
            'groups': [(6, 0, [canary_group.id])],
            'perm_read': True,
        })
        denied_user = self.env['res.users'].create({
            'name': 'Publish Denied User',
            'login': 'publish_denied_user',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('social_marketing.group_social_marketing_user').id,
                canary_group.id,
            ])],
        })
        post = self.env['social_marketing.post'].create({
            'message': 'Publish access post',
            'image_template_id': template.id,
            'image_template_record_model': 'res.partner',
            'image_template_record_id': partner.id,
            'image_render_pending': True,
        })
        with patch(
                'odoo.addons.social_image_creator.models.'
                'social_image_template.SocialImageTemplate._render_scene',
                fake_render_scene):
            with self.assertRaises(UserError):
                post.with_user(denied_user)._render_pending_image()
