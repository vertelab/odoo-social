# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSocialBrand(TransactionCase):
    """Spec: social-agency-brands."""

    def setUp(self):
        super().setUp()
        self.customer_a = self.env['res.partner'].create({
            'name': 'Customer A', 'is_company': True,
        })
        self.customer_b = self.env['res.partner'].create({
            'name': 'Customer B', 'is_company': True,
        })

    def _create_brand(self, name, partner):
        return self.env['social.brand'].create({
            'name': name, 'partner_id': partner.id,
        })

    def test_brand_without_customer_is_prevented(self):
        with self.cr.savepoint():
            with self.assertRaises(Exception):
                self.env['social.brand'].create({'name': 'No Customer'})

    def test_customer_can_have_multiple_brands(self):
        b1 = self._create_brand('Brand A1', self.customer_a)
        b2 = self._create_brand('Brand A2', self.customer_a)
        self.assertEqual(self.customer_a.brand_count, 2)
        self.assertEqual(
            set(self.customer_a.brand_ids.ids), {b1.id, b2.id})

    def test_brand_partner_must_be_company(self):
        person = self.env['res.partner'].create({'name': 'Person'})
        with self.cr.savepoint():
            with self.assertRaises(ValidationError):
                self.env['social.brand'].create({
                    'name': 'Bad', 'partner_id': person.id,
                })

    def test_brand_creates_dashboard_with_charts(self):
        brand = self._create_brand('Brand A1', self.customer_a)
        self.assertTrue(brand.dashboard_id)
        self.assertEqual(brand.dashboard_id.access_by, 'user')
        self.assertTrue(len(brand.dashboard_id.chart_ids) >= 1)
