# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase

# A one pixel payload is enough; the kit models never decode the content.
DUMMY_FILE = base64.b64encode(b'brand kit test payload')


class TestBrandKit(TransactionCase):
    """Spec: social-agency-brand-kit."""

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

    def _build_kit(self, brand):
        """Give the brand one colour, font, logo and asset of each kind."""
        self.env['social.brand.color'].create([
            {'brand_id': brand.id, 'name': 'Ink', 'role': 'primary',
             'hex': '#1A2B3C'},
            {'brand_id': brand.id, 'name': 'Sand', 'role': 'background',
             'hex': '#FFEECC'},
        ])
        self.env['social.brand.font'].create({
            'brand_id': brand.id, 'name': 'Heading font', 'role': 'heading',
            'font_file': DUMMY_FILE, 'filename': 'heading.woff2',
        })
        self.env['social.brand.logo'].create([
            {'brand_id': brand.id, 'name': 'Main logo', 'variant': 'primary',
             'image': DUMMY_FILE},
            {'brand_id': brand.id, 'name': 'Dark logo', 'variant': 'inverted',
             'image': DUMMY_FILE},
        ])
        self.env['social.brand.asset'].create({
            'brand_id': brand.id, 'name': 'Press kit', 'asset_type': 'document',
            'file': DUMMY_FILE, 'filename': 'press.pdf',
        })

    def test_kit_counts(self):
        self._build_kit(self.brand_a)
        self.brand_a.invalidate_recordset()
        self.assertEqual(self.brand_a.color_count, 2)
        self.assertEqual(self.brand_a.font_count, 1)
        self.assertEqual(self.brand_a.logo_count, 2)
        self.assertEqual(self.brand_a.asset_count, 1)

    def test_hex_constraint_rejects_bad_input(self):
        for bad in ('1A2B3C', '#12345', '#GGGGGG', 'red'):
            with self.subTest(hex=bad):
                with self.cr.savepoint():
                    with self.assertRaises(ValidationError):
                        self.env['social.brand.color'].create({
                            'brand_id': self.brand_a.id, 'name': 'Bad',
                            'role': 'primary', 'hex': bad,
                        })

    def test_hex_constraint_accepts_lower_and_upper_case(self):
        color = self.env['social.brand.color'].create({
            'brand_id': self.brand_a.id, 'name': 'Mixed',
            'role': 'accent', 'hex': '#aB12Ef',
        })
        self.assertEqual(color.hex, '#aB12Ef')

    def test_font_extension_constraint(self):
        with self.cr.savepoint():
            with self.assertRaises(ValidationError):
                self.env['social.brand.font'].create({
                    'brand_id': self.brand_a.id, 'name': 'Wrong type',
                    'role': 'body', 'font_file': DUMMY_FILE,
                    'filename': 'body.pdf',
                })
        font = self.env['social.brand.font'].create({
            'brand_id': self.brand_a.id, 'name': 'Upper case extension',
            'role': 'body', 'font_file': DUMMY_FILE, 'filename': 'BODY.TTF',
        })
        self.assertEqual(font.filename, 'BODY.TTF')

    def test_get_kit_color(self):
        self._build_kit(self.brand_a)
        self.assertEqual(self.brand_a.get_kit_color('primary'), '#1A2B3C')
        self.assertEqual(self.brand_a.get_kit_color('background'), '#FFEECC')
        self.assertFalse(self.brand_a.get_kit_color('text'))
        self.assertFalse(self.brand_b.get_kit_color('primary'))

    def test_get_kit_color_returns_first_by_sequence(self):
        self.env['social.brand.color'].create([
            {'brand_id': self.brand_a.id, 'name': 'Second', 'role': 'primary',
             'hex': '#222222', 'sequence': 20},
            {'brand_id': self.brand_a.id, 'name': 'First', 'role': 'primary',
             'hex': '#111111', 'sequence': 5},
        ])
        self.assertEqual(self.brand_a.get_kit_color('primary'), '#111111')

    def test_get_kit_logo(self):
        self._build_kit(self.brand_a)
        logo = self.brand_a.get_kit_logo('inverted')
        self.assertEqual(logo.name, 'Dark logo')
        self.assertEqual(logo._name, 'social.brand.logo')
        missing = self.brand_a.get_kit_logo('wordmark')
        self.assertFalse(missing)
        self.assertEqual(missing._name, 'social.brand.logo')

    def test_agency_user_cannot_read_other_brand_kit(self):
        self._build_kit(self.brand_a)
        self._build_kit(self.brand_b)
        agency_group = self.env.ref(
            'social_marketing_agency.group_social_agency_brand_user')
        user_a = self.env['res.users'].create({
            'name': 'Agency user A',
            'login': 'agency.a@example.com',
            'groups_id': [(6, 0, [agency_group.id])],
            'brand_ids': [(6, 0, [self.brand_a.id])],
        })
        for model in ('social.brand.color', 'social.brand.font',
                      'social.brand.logo', 'social.brand.asset'):
            with self.subTest(model=model):
                records = self.env[model].with_user(user_a).search([])
                self.assertTrue(records)
                self.assertEqual(
                    set(records.mapped('brand_id').ids), {self.brand_a.id})
                other = self.env[model].search(
                    [('brand_id', '=', self.brand_b.id)], limit=1)
                with self.assertRaises(AccessError):
                    other.with_user(user_a).read(['name'])

    def test_customer_user_cannot_read_other_brand_kit(self):
        self._build_kit(self.brand_a)
        self._build_kit(self.brand_b)
        contact_a = self.env['res.partner'].create({
            'name': 'Alice', 'parent_id': self.customer_a.id,
            'email': 'alice.kit@a.example',
        })
        user_a = self.env['res.users'].create({
            'partner_id': contact_a.id,
            'login': contact_a.email,
            'groups_id': [(6, 0, [
                self.env.ref('base.group_portal').id,
                self.env.ref(
                    'social_marketing_agency.group_social_customer_approver').id,
            ])],
        })
        colors = self.env['social.brand.color'].with_user(user_a).search([])
        self.assertEqual(
            set(colors.mapped('brand_id').ids), {self.brand_a.id})
