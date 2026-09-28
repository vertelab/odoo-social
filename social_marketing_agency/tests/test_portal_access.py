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


class TestInviteBrandScope(TransactionCase):
    """An agency user must not reach invites for a brand they do not hold.

    Every other brand-scoped model restricts group_social_agency_brand_user to
    user.brand_ids. social.agency.invite had no rule at all, which let an
    agency user scoped to one brand create an invitation into another. That is
    privilege escalation, not merely a visibility leak: the invitation is what
    grants a contact access to a brand.
    """

    def setUp(self):
        super().setUp()
        Partner = self.env['res.partner']
        self.cust_a = Partner.create({'name': 'Scope Cust A', 'is_company': True})
        self.cust_b = Partner.create({'name': 'Scope Cust B', 'is_company': True})
        self.contact_b = Partner.create({
            'name': 'Contact B', 'parent_id': self.cust_b.id,
            'email': 'contact.b@example.com'})
        Brand = self.env['social.brand']
        self.brand_a = Brand.create({
            'name': 'Scope Brand A', 'partner_id': self.cust_a.id})
        self.brand_b = Brand.create({
            'name': 'Scope Brand B', 'partner_id': self.cust_b.id})
        self.agency_user = self.env['res.users'].create({
            'name': 'Agency Scoped',
            'login': 'agency_scoped_test',
            'groups_id': [(4, self.env.ref(
                'social_marketing_agency.group_social_agency_brand_user').id)],
            'brand_ids': [(6, 0, [self.brand_a.id])],
        })

    def test_agency_user_cannot_create_invite_for_other_brand(self):
        with self.assertRaises(AccessError):
            self.env['social.agency.invite'].with_user(
                self.agency_user).create({
                    'brand_id': self.brand_b.id,
                    'partner_id': self.contact_b.id,
                })

    def test_agency_user_cannot_read_other_brand_invite(self):
        invite = self.env['social.agency.invite'].sudo().create({
            'brand_id': self.brand_b.id,
            'partner_id': self.contact_b.id,
        })
        found = self.env['social.agency.invite'].with_user(
            self.agency_user).search([])
        self.assertNotIn(invite.id, found.ids)


class TestBrandRecordRule(TransactionCase):
    """social.brand must isolate agency users through a record rule.

    The model overrides search() to filter on user.brand_ids. That override
    reads like an access control and is not one: search_count, name_search,
    read_group and browse all reach the ORM through _search and never pass
    through it. Before the rule existed, an agency user scoped to one brand
    could browse another brand's record and read it in full.

    Each method below is checked separately on purpose. A single search()
    assertion passed the whole time the data was leaking.
    """

    def setUp(self):
        super().setUp()
        Partner = self.env['res.partner']
        cust_a = Partner.create({'name': 'Rule Cust A', 'is_company': True})
        cust_b = Partner.create({'name': 'Rule Cust B', 'is_company': True})
        Brand = self.env['social.brand']
        self.brand_a = Brand.create({
            'name': 'Rule Brand A', 'partner_id': cust_a.id})
        self.brand_b = Brand.create({
            'name': 'Rule Brand B', 'partner_id': cust_b.id})
        self.agency_user = self.env['res.users'].create({
            'name': 'Rule Agency',
            'login': 'rule_agency_test',
            'groups_id': [(4, self.env.ref(
                'social_marketing_agency.group_social_agency_brand_user').id)],
            'brand_ids': [(6, 0, [self.brand_a.id])],
        })

    def _as_agency(self):
        return self.env['social.brand'].with_user(self.agency_user)

    def test_search_returns_only_own_brand(self):
        self.assertEqual(self._as_agency().search([]), self.brand_a)

    def test_search_count_does_not_leak_other_brands(self):
        self.assertEqual(self._as_agency().search_count([]), 1)

    def test_name_search_does_not_leak_other_brands(self):
        names = [name for _id, name in self._as_agency().name_search()]
        self.assertNotIn(self.brand_b.name, names)

    def test_read_group_does_not_leak_other_brands(self):
        groups = self._as_agency().read_group([], ['id'], ['partner_id'])
        partner_ids = [g['partner_id'][0] for g in groups if g['partner_id']]
        self.assertNotIn(self.brand_b.partner_id.id, partner_ids)

    def test_browse_other_brand_is_refused(self):
        with self.assertRaises(AccessError):
            self._as_agency().browse(self.brand_b.id).name

    def test_manager_still_sees_every_brand(self):
        manager = self.env['res.users'].create({
            'name': 'Rule Manager',
            'login': 'rule_manager_test',
            'groups_id': [
                (4, self.env.ref(
                    'social_marketing.group_social_marketing_manager').id),
                (4, self.env.ref(
                    'social_marketing_agency.group_social_agency_brand_user').id),
            ],
        })
        found = self.env['social.brand'].with_user(manager).search([])
        self.assertIn(self.brand_a, found)
        self.assertIn(self.brand_b, found)
