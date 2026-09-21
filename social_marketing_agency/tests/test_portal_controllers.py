# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""The customer portal for post approval, exercised over real HTTP.

The routes are the part of this module that people outside the company can
reach, so they are tested as requests and not as python calls: a method that
behaves when called directly proves nothing about a route that is reachable
with a guessed id, a forged token, or a plain GET.
"""

import base64
import json

from odoo import fields, http
from odoo.tests.common import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestSocialPostPortal(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner']
        cls.customer_a = Partner.create({
            'name': 'Portal Customer A', 'is_company': True})
        cls.customer_b = Partner.create({
            'name': 'Portal Customer B', 'is_company': True})
        cls.contact_a = Partner.create({
            'name': 'Portal Alice', 'parent_id': cls.customer_a.id,
            'email': 'portal.alice@example.com'})
        cls.contact_b = Partner.create({
            'name': 'Portal Bob', 'parent_id': cls.customer_b.id,
            'email': 'portal.bob@example.com'})

        Brand = cls.env['social.brand']
        cls.brand_a = Brand.create({
            'name': 'Portal Brand A', 'partner_id': cls.customer_a.id})
        cls.brand_b = Brand.create({
            'name': 'Portal Brand B', 'partner_id': cls.customer_b.id})

        cls.user_a = cls._make_customer_user(cls.contact_a, 'portal_alice')
        cls.user_b = cls._make_customer_user(cls.contact_b, 'portal_bob')

        cls.post_a = cls._make_awaiting_post(cls.brand_a, 'Post for brand A')
        cls.post_b = cls._make_awaiting_post(cls.brand_b, 'Post for brand B')

    # -- fixtures ------------------------------------------------------

    @classmethod
    def _make_customer_user(cls, contact, login):
        groups = [
            cls.env.ref('base.group_portal').id,
            cls.env.ref(
                'social_marketing_agency.group_social_customer_approver').id,
        ]
        return cls.env['res.users'].create({
            'name': contact.name,
            'partner_id': contact.id,
            'login': login,
            'password': login,
            'groups_id': [(6, 0, groups)],
        })

    @classmethod
    def _make_awaiting_post(cls, brand, message, accounts=None, images=None):
        policy = cls.env['communication.policy'].create({
            'name': 'Portal policy %s' % brand.name,
            'state': 'active',
            'brand_id': brand.id,
            'approval_chain': json.dumps([
                {'role': 'creator', 'action': 'submit'},
                {'role': 'customer', 'action': 'approve'},
            ]),
        })
        plan = cls.env['communication.plan'].create({
            'name': 'Portal plan %s' % brand.name,
            'policy_id': policy.id,
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today(),
        })
        line = cls.env['communication.plan.line'].create({
            'plan_id': plan.id,
            'channel': 'linkedin',
            'content_type': 'post',
            'date': fields.Date.today(),
        })
        vals = {
            'message': '<p>%s</p>' % message,
            'brand_id': brand.id,
            'plan_line_id': line.id,
        }
        if accounts is not None:
            vals['account_ids'] = [(6, 0, accounts.ids)]
        if images is not None:
            vals['image_ids'] = [(6, 0, images.ids)]
        post = cls.env['social_marketing.post'].create(vals)
        post.action_submit_for_approval()
        post.action_approve()
        assert post.approval_state == 'awaiting_customer'
        return post

    def _csrf(self):
        return http.Request.csrf_token(self)

    # -- isolation -----------------------------------------------------

    def test_customer_cannot_open_other_customers_post_by_id(self):
        self.authenticate('portal_alice', 'portal_alice')
        response = self.url_open(
            '/my/social-posts/%s' % self.post_b.id, allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers['Location'].endswith('/my'))

    def test_customer_can_open_own_post_by_id(self):
        self.authenticate('portal_alice', 'portal_alice')
        response = self.url_open('/my/social-posts/%s' % self.post_a.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Post for brand A', response.text)

    def test_wrong_token_does_not_open_other_customers_post(self):
        real_token = self.post_b._portal_ensure_token()
        self.authenticate('portal_alice', 'portal_alice')
        for token in ('', 'not-a-token', real_token[:-1] + 'x'):
            response = self.url_open(
                '/my/social-posts/%s?access_token=%s' % (self.post_b.id, token),
                allow_redirects=False)
            self.assertEqual(
                response.status_code, 303,
                'token %r must not open another customer post' % token)
            self.assertTrue(response.headers['Location'].endswith('/my'))

    def test_list_shows_only_own_brand_posts(self):
        self.authenticate('portal_alice', 'portal_alice')
        response = self.url_open('/my/social-posts?filterby=all')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Post for brand A', response.text)
        self.assertNotIn('Post for brand B', response.text)

        self.authenticate('portal_bob', 'portal_bob')
        response = self.url_open('/my/social-posts?filterby=all')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Post for brand B', response.text)
        self.assertNotIn('Post for brand A', response.text)

    # -- approve -------------------------------------------------------

    def test_approve_moves_state_and_records_the_actor(self):
        self.authenticate('portal_alice', 'portal_alice')
        response = self.url_open(
            '/my/social-posts/%s/approve' % self.post_a.id,
            data={'csrf_token': self._csrf()}, allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('message=approved', response.headers['Location'])
        self.post_a.invalidate_recordset()
        self.assertEqual(self.post_a.approval_state, 'approved')
        self.assertEqual(self.post_a.write_uid, self.user_a)
        bodies = self.post_a.message_ids.mapped('body')
        self.assertTrue(
            any('Portal Alice' in (body or '') for body in bodies),
            'the chatter must record which customer user approved')

    def test_approve_refused_for_other_customers_post(self):
        self.authenticate('portal_alice', 'portal_alice')
        response = self.url_open(
            '/my/social-posts/%s/approve' % self.post_b.id,
            data={'csrf_token': self._csrf()}, allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.post_b.invalidate_recordset()
        self.assertEqual(self.post_b.approval_state, 'awaiting_customer')

    def test_approve_refused_when_not_awaiting_customer(self):
        post = self._make_awaiting_post(self.brand_a, 'Second post brand A')
        post.write({'approval_state': 'approved'})
        self.authenticate('portal_alice', 'portal_alice')
        self.url_open(
            '/my/social-posts/%s/approve' % post.id,
            data={'csrf_token': self._csrf()})
        post.invalidate_recordset()
        self.assertEqual(post.approval_state, 'approved')

    def test_get_cannot_change_state(self):
        self.authenticate('portal_alice', 'portal_alice')
        for suffix in ('approve', 'reject?reason=nope'):
            response = self.url_open(
                '/my/social-posts/%s/%s' % (self.post_a.id, suffix),
                allow_redirects=False)
            self.assertEqual(
                response.status_code, 405,
                'a GET on %s must not be routed' % suffix)
        self.post_a.invalidate_recordset()
        self.assertEqual(self.post_a.approval_state, 'awaiting_customer')

    def test_post_without_csrf_token_is_refused(self):
        self.authenticate('portal_alice', 'portal_alice')
        response = self.url_open(
            '/my/social-posts/%s/approve' % self.post_a.id,
            data={'nothing': '1'}, allow_redirects=False)
        self.assertEqual(response.status_code, 400)
        self.post_a.invalidate_recordset()
        self.assertEqual(self.post_a.approval_state, 'awaiting_customer')

    # -- reject --------------------------------------------------------

    def test_reject_with_reason_records_the_reason(self):
        self.authenticate('portal_alice', 'portal_alice')
        response = self.url_open(
            '/my/social-posts/%s/reject' % self.post_a.id,
            data={'csrf_token': self._csrf(), 'reason': 'Wrong tone of voice'},
            allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('message=rejected', response.headers['Location'])
        self.post_a.invalidate_recordset()
        self.assertEqual(self.post_a.approval_state, 'rejected')
        self.assertEqual(self.post_a.rejection_reason, 'Wrong tone of voice')
        page = self.url_open('/my/social-posts/%s' % self.post_a.id)
        self.assertIn('Wrong tone of voice', page.text)

    def test_reject_with_empty_reason_is_refused(self):
        self.authenticate('portal_alice', 'portal_alice')
        for reason in ('', '   ', '\t\n '):
            response = self.url_open(
                '/my/social-posts/%s/reject' % self.post_a.id,
                data={'csrf_token': self._csrf(), 'reason': reason},
                allow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertIn('message=reason_required',
                          response.headers['Location'])
            self.post_a.invalidate_recordset()
            self.assertEqual(self.post_a.approval_state, 'awaiting_customer')

    def test_reject_reason_is_not_rendered_as_markup(self):
        self.authenticate('portal_alice', 'portal_alice')
        payload = '<img src=x onerror="alert(1)">bad'
        response = self.url_open(
            '/my/social-posts/%s/reject' % self.post_a.id,
            data={'csrf_token': self._csrf(), 'reason': payload},
            allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('message=rejected', response.headers['Location'])
        self.post_a.invalidate_recordset()
        self.assertEqual(self.post_a.rejection_reason, payload)
        # The reason is echoed on the page, escaped, never as a live tag.
        page = self.url_open('/my/social-posts/%s' % self.post_a.id)
        self.assertNotIn('<img src=x onerror', page.text)
        self.assertIn('&lt;img src=x onerror', page.text)
        # And the chatter body it was copied into carries no live tag either.
        for body in self.post_a.message_ids.mapped('body'):
            self.assertNotIn('<img', body or '')

    # -- rendering -----------------------------------------------------

    def test_detail_page_renders_accounts_and_images(self):
        """A real post carries accounts and images, so render one.

        Both are read through record rules that only allow the customer's own
        brand, so a missing access right shows up here as a 500 rather than as
        a silently empty page.
        """
        media = self.env['social_marketing.media'].create({
            'name': 'Portalgram'})
        account = self.env['social_marketing.account'].create({
            'name': 'Brand A on Portalgram',
            'media_id': media.id,
            'brand_id': self.brand_a.id,
            'utm_medium_id': self.env['utm.medium'].create(
                {'name': 'Portalgram medium'}).id,
        })
        image = self.env['ir.attachment'].create({
            'name': 'shot.png',
            'mimetype': 'image/png',
            'datas': base64.b64encode(b'not really a png'),
        })
        post = self._make_awaiting_post(
            self.brand_a, 'Post with accounts and images',
            accounts=account, images=image)

        self.authenticate('portal_alice', 'portal_alice')
        response = self.url_open('/my/social-posts/%s' % post.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Post with accounts and images', response.text)
        self.assertIn('Brand A on Portalgram', response.text)
        self.assertIn('Portalgram', response.text)
        self.assertIn('/web/image/%s' % image.id, response.text)

    # -- home counter --------------------------------------------------

    def test_home_counter_counts_only_own_awaiting_posts(self):
        self.authenticate('portal_alice', 'portal_alice')
        response = self.url_open(
            '/my/counters',
            data=json.dumps({
                'jsonrpc': '2.0', 'method': 'call',
                'params': {'counters': ['social_post_count']},
            }),
            headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        result = response.json()['result']
        self.assertEqual(result['social_post_count'], 1)
