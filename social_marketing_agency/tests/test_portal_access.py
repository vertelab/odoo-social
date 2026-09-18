# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestPortalAccess(TransactionCase):
    """Spec: social-agency-portal — data isolation and rights levels."""

    def setUp(self):
        super().setUp()
        self.customer_a = self.env['res.partner'].create({
            'name': 'Customer A', 'is_company': True,
        })
        self.customer_b = self.env['res.partner'].create({
            'name': 'Customer B', 'is_company': True,
        })
        self.brand_a = self.env['social.brand'].create({
            'name': 'Brand A', 'partner_id': self.customer_a.id,
        })
        self.brand_b = self.env['social.brand'].create({
            'name': 'Brand B', 'partner_id': self.customer_b.id,
        })
        self.contact_a = self.env['res.partner'].create({
            'name': 'Alice', 'parent_id': self.customer_a.id,
            'email': 'alice@a.example',
        })
        self.contact_b = self.env['res.partner'].create({
            'name': 'Bob', 'parent_id': self.customer_b.id,
            'email': 'bob@b.example',
        })
        self.doc_type = self.env.ref(
            'social_marketing_agency.document_type_strategy')
        self.doc_a = self.env['social.agency.document'].create({
            'name': 'Strategy A', 'type_id': self.doc_type.id,
            'brand_id': self.brand_a.id,
        })
        self.doc_b = self.env['social.agency.document'].create({
            'name': 'Strategy B', 'type_id': self.doc_type.id,
            'brand_id': self.brand_b.id,
        })

    def _create_customer_user(self, contact, group_xmlid):
        group = self.env.ref(group_xmlid)
        portal = self.env.ref('base.group_portal')
        return self.env['res.users'].create({
            'partner_id': contact.id,
            'login': contact.email,
            'groups_id': [(6, 0, [portal.id, group.id])],
        })

    def test_customer_sees_only_own_brands(self):
        user_a = self._create_customer_user(
            self.contact_a, 'social_marketing_agency.group_social_customer_approver')
        docs = self.env['social.agency.document'].with_user(user_a).search([])
        self.assertEqual(set(docs.ids), {self.doc_a.id})

    def test_customer_does_not_see_agency_internal_records(self):
        # Agency-internal records have no brand. communication.policy allows
        # an empty brand; customers must never see those records.
        internal = self.env['communication.policy'].sudo().create({
            'name': 'Internal only', 'brand_id': False,
        })
        user_a = self._create_customer_user(
            self.contact_a, 'social_marketing_agency.group_social_customer_approver')
        policies = self.env['communication.policy'].with_user(user_a).search([])
        self.assertNotIn(internal.id, policies.ids)

    def test_approver_cannot_write(self):
        user_a = self._create_customer_user(
            self.contact_a, 'social_marketing_agency.group_social_customer_approver')
        with self.assertRaises(AccessError):
            self.doc_a.with_user(user_a).write({'name': 'Hacked'})

    def test_editor_can_write_own_but_not_other_brand(self):
        user_a = self._create_customer_user(
            self.contact_a, 'social_marketing_agency.group_social_customer_editor')
        self.doc_a.with_user(user_a).write({'name': 'Edited by customer'})
        self.assertEqual(self.doc_a.name, 'Edited by customer')
        with self.assertRaises(AccessError):
            self.doc_b.with_user(user_a).write({'name': 'Hack other'})

    def test_invite_assigns_group_from_brand_setting(self):
        self.brand_a.customer_edit_enabled = False
        wizard = self.env['social.agency.invite'].create({
            'brand_id': self.brand_a.id,
            'partner_id': self.contact_a.id,
            'email': self.contact_a.email,
        })
        wizard.action_invite()
        user = self.env['res.users'].search(
            [('partner_id', '=', self.contact_a.id)], limit=1)
        self.assertTrue(user.has_group(
            'social_marketing_agency.group_social_customer_approver'))
        self.assertFalse(user.has_group(
            'social_marketing_agency.group_social_customer_editor'))

        self.brand_a.customer_edit_enabled = True
        contact2 = self.env['res.partner'].create({
            'name': 'Alice 2', 'parent_id': self.customer_a.id,
            'email': 'alice2@a.example',
        })
        wizard2 = self.env['social.agency.invite'].create({
            'brand_id': self.brand_a.id,
            'partner_id': contact2.id,
            'email': contact2.email,
        })
        wizard2.action_invite()
        user2 = self.env['res.users'].search(
            [('partner_id', '=', contact2.id)], limit=1)
        self.assertTrue(user2.has_group(
            'social_marketing_agency.group_social_customer_editor'))
