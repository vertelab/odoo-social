# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestUnderlag(TransactionCase):
    """Spec: social-agency-underlag."""

    def setUp(self):
        super().setUp()
        self.customer = self.env['res.partner'].create({
            'name': 'Customer', 'is_company': True,
        })
        self.brand = self.env['social.brand'].create({
            'name': 'Brand', 'partner_id': self.customer.id,
        })

    def test_document_types_are_seeded(self):
        types = self.env['social.agency.document.type'].search([
            ('name', 'in', ['Strategy', 'Brief', 'Brand Guidelines', 'Report']),
        ])
        self.assertEqual(len(types), 4)

    def test_document_requires_brand(self):
        doc_type = self.env.ref(
            'social_marketing_agency.document_type_strategy')
        with self.cr.savepoint():
            with self.assertRaises(Exception):
                self.env['social.agency.document'].create({
                    'name': 'No Brand Doc', 'type_id': doc_type.id,
                })

    def test_document_scoped_to_brand_and_attachments(self):
        doc_type = self.env.ref(
            'social_marketing_agency.document_type_brief')
        doc = self.env['social.agency.document'].create({
            'name': 'Brief Q3', 'type_id': doc_type.id,
            'brand_id': self.brand.id,
        })
        self.assertEqual(doc.brand_id, self.brand)
        self.assertEqual(doc.partner_id, self.customer)
        # brand workspace relation
        self.assertEqual(set(self.brand.document_ids.ids), {doc.id})
        self.assertEqual(self.brand.document_count, 1)

    def test_status_lifecycle(self):
        doc_type = self.env.ref(
            'social_marketing_agency.document_type_report')
        doc = self.env['social.agency.document'].create({
            'name': 'Monthly Report', 'type_id': doc_type.id,
            'brand_id': self.brand.id,
        })
        self.assertEqual(doc.status, 'draft')
        doc.action_in_review()
        self.assertEqual(doc.status, 'in_review')
        doc.action_approve()
        self.assertEqual(doc.status, 'approved')
        doc.action_archive()
        self.assertEqual(doc.status, 'archived')
        # status is tracked → chatter messages exist
        self.assertTrue(doc.message_ids)
