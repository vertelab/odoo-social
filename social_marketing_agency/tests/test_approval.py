# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestCustomerApproval(TransactionCase):
    """Spec: social-agency-portal — customer approval step."""

    def setUp(self):
        super().setUp()
        self.customer = self.env['res.partner'].create({
            'name': 'Customer', 'is_company': True,
        })
        self.brand = self.env['social.brand'].create({
            'name': 'Brand', 'partner_id': self.customer.id,
        })
        self.contact = self.env['res.partner'].create({
            'name': 'Carol', 'parent_id': self.customer.id,
            'email': 'carol@example.com',
        })
        approver = self.env.ref(
            'social_marketing_agency.group_social_customer_approver')
        portal = self.env.ref('base.group_portal')
        self.customer_user = self.env['res.users'].create({
            'partner_id': self.contact.id,
            'login': 'carol@example.com',
            'groups_id': [(6, 0, [portal.id, approver.id])],
        })

    def _create_policy(self, with_customer_step=True):
        chain = [
            {'role': 'creator', 'action': 'submit'},
        ]
        if with_customer_step:
            chain.append({'role': 'customer', 'action': 'approve'})
        return self.env['communication.policy'].create({
            'name': 'Policy',
            'state': 'active',
            'brand_id': self.brand.id,
            'approval_chain': json.dumps(chain),
        })

    def _create_post(self, policy):
        plan = self.env['communication.plan'].create({
            'name': 'Plan',
            'policy_id': policy.id,
            'start_date': fields.Date.today(),
            'end_date': fields.Date.today(),
        })
        line = self.env['communication.plan.line'].create({
            'plan_id': plan.id,
            'channel': 'linkedin',
            'content_type': 'post',
            'date': fields.Date.today(),
        })
        return self.env['social_marketing.post'].create({
            'message': '<p>Hello world</p>',
            'brand_id': self.brand.id,
            'plan_line_id': line.id,
        })

    def test_post_waits_for_customer_approval(self):
        policy = self._create_policy(with_customer_step=True)
        post = self._create_post(policy)
        post.action_submit_for_approval()
        self.assertEqual(post.approval_state, 'pending_approval')
        post.action_approve()
        self.assertEqual(post.approval_state, 'awaiting_customer')

    def test_customer_approve_makes_post_publishable(self):
        policy = self._create_policy(with_customer_step=True)
        post = self._create_post(policy)
        post.action_submit_for_approval()
        post.action_approve()
        self.assertEqual(post.approval_state, 'awaiting_customer')
        # Publishing is blocked while awaiting customer approval
        with self.assertRaises(UserError):
            post.action_post()
        # The customer approves
        post.with_user(self.customer_user).action_customer_approve()
        self.assertEqual(post.approval_state, 'approved')

    def test_customer_reject_returns_post_with_reason(self):
        policy = self._create_policy(with_customer_step=True)
        post = self._create_post(policy)
        post.action_submit_for_approval()
        post.action_approve()
        post.with_user(self.customer_user).action_customer_reject(
            'Not on brand')
        self.assertEqual(post.approval_state, 'rejected')
        self.assertEqual(post.rejection_reason, 'Not on brand')

    def test_customer_cannot_approve_other_brand(self):
        other_customer = self.env['res.partner'].create({
            'name': 'Other', 'is_company': True,
        })
        other_brand = self.env['social.brand'].create({
            'name': 'Other Brand', 'partner_id': other_customer.id,
        })
        policy = self._create_policy(with_customer_step=True)
        post = self._create_post(policy)
        post.write({'brand_id': other_brand.id})
        post.action_submit_for_approval()
        post.action_approve()
        with self.assertRaises(UserError):
            post.with_user(self.customer_user).action_customer_approve()

    def test_policy_without_customer_step_skips_customer_approval(self):
        policy = self._create_policy(with_customer_step=False)
        post = self._create_post(policy)
        post.action_submit_for_approval()
        post.action_approve()
        self.assertEqual(post.approval_state, 'approved')
