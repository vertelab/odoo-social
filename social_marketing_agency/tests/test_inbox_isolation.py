# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Brand isolation of the unified inbox.

Inbox items carry other people's names, messages and profile links. A leak
here is a leak of third party personal data, so every access path is checked
separately. A single search() assertion is not evidence of anything: the
social.brand leak fixed earlier passed exactly that assertion the whole time
it was leaking through search_count(), read_group() and browse().
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class InboxIsolationCommon(TransactionCase):

    def setUp(self):
        super().setUp()
        Partner = self.env['res.partner']
        self.cust_a = Partner.create({'name': 'Inbox Cust A', 'is_company': True})
        self.cust_b = Partner.create({'name': 'Inbox Cust B', 'is_company': True})
        Brand = self.env['social.brand']
        self.brand_a = Brand.create({
            'name': 'Inbox Brand A', 'partner_id': self.cust_a.id})
        self.brand_b = Brand.create({
            'name': 'Inbox Brand B', 'partner_id': self.cust_b.id})

        self.media = self.env['social_marketing.media'].create({
            'name': 'Inbox Media'})
        self.stream_type = self.env['social_marketing.stream.type'].create({
            'name': 'Inbox Comments',
            'stream_type': 'inbox_test_comments',
            'media_id': self.media.id,
            'interaction_type': 'comment',
        })
        self.stream_a = self._stream(self.brand_a, 'Account A')
        self.stream_b = self._stream(self.brand_b, 'Account B')
        self.item_a = self._item(self.stream_a, 'Message for A', 'Anna Outside')
        self.item_b = self._item(self.stream_b, 'Message for B', 'Bertil Outside')

    def _stream(self, brand, account_name):
        account = self.env['social_marketing.account'].create({
            'name': account_name, 'media_id': self.media.id})
        return self.env['social_marketing.stream'].create({
            'media_id': self.media.id,
            'social_account_id': account.id,
            'stream_type_id': self.stream_type.id,
            'brand_id': brand.id,
        })

    def _item(self, stream, message, author):
        return self.env['social_marketing.stream.post'].create({
            'stream_id': stream.id,
            'message': message,
            'author_name': author,
        })

    def _agency_user(self, login, brands, extra_groups=()):
        groups = [self.env.ref(
            'social_marketing_agency.group_social_agency_brand_user').id]
        groups += [self.env.ref(x).id for x in extra_groups]
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, groups)],
            'brand_ids': [(6, 0, [b.id for b in brands])],
        })


class TestInboxBrandField(InboxIsolationCommon):

    def test_brand_comes_from_the_stream(self):
        self.assertEqual(self.item_a.brand_id, self.brand_a)
        self.assertEqual(self.item_b.brand_id, self.brand_b)

    def test_brand_is_stored_and_searchable(self):
        field = self.env['social_marketing.stream.post']._fields['brand_id']
        self.assertTrue(field.store, "brand_id must be stored for ir.rule to use it")
        found = self.env['social_marketing.stream.post'].search(
            [('brand_id', '=', self.brand_a.id)])
        self.assertEqual(found, self.item_a)

    def test_brand_follows_the_stream(self):
        self.stream_a.brand_id = self.brand_b
        self.assertEqual(self.item_a.brand_id, self.brand_b)


class TestInboxAgencyIsolation(InboxIsolationCommon):
    """An agency user scoped to brand A must not reach brand B's items.

    One test per access path on purpose.
    """

    def setUp(self):
        super().setUp()
        self.user_a = self._agency_user('inbox_agency_a', [self.brand_a])

    def _as_a(self):
        return self.env['social_marketing.stream.post'].with_user(self.user_a)

    def test_search_returns_only_own_brand(self):
        self.assertEqual(self._as_a().search([]), self.item_a)

    def test_search_count_does_not_leak(self):
        self.assertEqual(self._as_a().search_count([]), 1)

    def test_read_group_does_not_leak(self):
        groups = self._as_a().read_group([], ['id'], ['brand_id'])
        brand_ids = [g['brand_id'][0] for g in groups if g['brand_id']]
        self.assertNotIn(self.brand_b.id, brand_ids)

    def test_browse_other_brand_is_refused(self):
        with self.assertRaises(AccessError):
            self._as_a().browse(self.item_b.id).message

    def test_read_other_brand_is_refused(self):
        with self.assertRaises(AccessError):
            self._as_a().browse(self.item_b.id).read(['message', 'author_name'])

    def test_explicit_domain_on_other_brand_returns_nothing(self):
        found = self._as_a().search([('brand_id', '=', self.brand_b.id)])
        self.assertFalse(found)

    def test_write_on_other_brand_is_refused(self):
        with self.assertRaises(AccessError):
            self._as_a().browse(self.item_b.id).action_inbox_close()

    def test_own_brand_stays_workable(self):
        self._as_a().browse(self.item_a.id).action_inbox_assign()
        self.assertEqual(self.item_a.inbox_state, 'assigned')
        self.assertEqual(self.item_a.assigned_user_id, self.user_a)

    def test_second_brand_becomes_visible_when_assigned(self):
        self.user_a.brand_ids = [(4, self.brand_b.id)]
        self.assertEqual(
            self._as_a().search_count([]), 2,
            "adding the brand to the user must be the only way in")


class TestInboxSocialUserIsolation(InboxIsolationCommon):
    """Holding the plain Social User group must not widen the agency scope.

    Record rules of different groups are ORed. A user in both the social user
    group and the agency group would get the union of both domains, so the
    social user rule is itself brand scoped, with brandless items (a plain
    non agency feed) as its only extra reach.
    """

    def test_social_user_plus_agency_user_still_cannot_see_other_brand(self):
        user = self._agency_user(
            'inbox_both_groups', [self.brand_a],
            extra_groups=('social_marketing.group_social_marketing_user',))
        Post = self.env['social_marketing.stream.post'].with_user(user)
        self.assertEqual(Post.search([]), self.item_a)
        self.assertEqual(Post.search_count([]), 1)
        with self.assertRaises(AccessError):
            Post.browse(self.item_b.id).message

    def test_manager_sees_every_brand(self):
        manager = self.env['res.users'].create({
            'name': 'Inbox Manager',
            'login': 'inbox_manager_test',
            'groups_id': [(6, 0, [
                self.env.ref('social_marketing.group_social_marketing_manager').id,
                self.env.ref(
                    'social_marketing_agency.group_social_agency_brand_user').id,
            ])],
        })
        found = self.env['social_marketing.stream.post'].with_user(manager).search([])
        self.assertIn(self.item_a, found)
        self.assertIn(self.item_b, found)


class TestInboxCustomerIsolation(InboxIsolationCommon):
    """A customer user reaches the items of their own brands, read only."""

    def setUp(self):
        super().setUp()
        contact = self.env['res.partner'].create({
            'name': 'Customer Contact A', 'parent_id': self.cust_a.id,
            'email': 'inbox.customer.a@example.com'})
        self.customer_a = self.env['res.users'].create({
            'partner_id': contact.id,
            'login': 'inbox_customer_a',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_portal').id,
                self.env.ref(
                    'social_marketing_agency.group_social_customer_approver').id,
            ])],
        })

    def _as_customer(self):
        return self.env['social_marketing.stream.post'].with_user(self.customer_a)

    def test_customer_search_only_own_brand(self):
        self.assertEqual(self._as_customer().search([]), self.item_a)

    def test_customer_search_count_does_not_leak(self):
        self.assertEqual(self._as_customer().search_count([]), 1)

    def test_customer_browse_other_brand_is_refused(self):
        with self.assertRaises(AccessError):
            self._as_customer().browse(self.item_b.id).message

    def test_customer_cannot_write(self):
        with self.assertRaises(AccessError):
            self._as_customer().browse(self.item_a.id).write(
                {'inbox_state': 'closed'})
