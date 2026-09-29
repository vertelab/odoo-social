# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

"""Palette validation for the agency brand kit (spec: agency-brand-kit,
design decision D5). The pure parser is unit-tested without an Odoo
environment; the constraint path is covered with a TransactionCase."""

import unittest

try:
    from odoo.addons.social_image_creator_agency.models.social_brand import (
        PALETTE_EXAMPLE, parse_palette)
except ImportError:
    # The agency glue module is not installed in this database; the
    # constraint tests below skip instead of breaking the suite.
    PALETTE_EXAMPLE = None
    parse_palette = None

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


@unittest.skipIf(parse_palette is None,
                 'social_image_creator_agency is not installed')
class TestParsePalette(unittest.TestCase):

    def test_valid_list_accepted(self):
        self.assertEqual(
            parse_palette(['#003366', '#ff6600']), ['#003366', '#ff6600'])

    def test_uppercase_hex_accepted(self):
        self.assertEqual(parse_palette(['#FF6600']), ['#FF6600'])

    def test_valid_json_text_accepted(self):
        self.assertEqual(
            parse_palette('["#003366", "#ff6600"]'),
            ['#003366', '#ff6600'])

    def test_empty_list_accepted(self):
        self.assertEqual(parse_palette([]), [])

    def test_malformed_json_text_refused(self):
        for bad in ('not json at all', '["#003366"', '{"#003366"}'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_palette(bad)

    def test_non_list_refused(self):
        for bad in ('"#003366"', '42', '{"a": 1}', '["#003366", ]'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_palette(bad)

    def test_non_hex_entries_refused(self):
        for bad in (
                ['#fff'], ['#00336'], ['003366'], ['#gggggg'], ['red'],
                [''], [42], [None], ['#003366', 'blue']):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_palette(bad)


@unittest.skipIf(parse_palette is None,
                 'social_image_creator_agency is not installed')
class TestBrandPaletteConstraint(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand_model = cls.env.registry.get('social.brand')
        if not brand_model or 'palette' not in brand_model._fields:
            raise unittest.SkipTest(
                'social_image_creator_agency is not installed')
        cls.customer = cls.env['res.partner'].create({
            'name': 'Palette Customer',
            'is_company': True,
        })

    def _new_brand(self, **values):
        values.setdefault('name', 'Palette Brand')
        values.setdefault('partner_id', self.customer.id)
        return self.env['social.brand'].create(values)

    def test_valid_palette_accepted(self):
        brand = self._new_brand(palette=['#003366', '#FF6600'])
        self.assertEqual(brand.palette, ['#003366', '#FF6600'])

    def test_hand_typed_palette_normalized_to_list(self):
        """Odoo 18 keeps hand-typed JSON widget text a string; the model
        normalizes it to a real list so the editor swatches keep working."""
        brand = self._new_brand(palette='["#003366", "#ff6600"]')
        self.assertEqual(brand.palette, ['#003366', '#ff6600'])

    def test_bad_palette_refused_with_example(self):
        cases = [
            ['#00336'],                # too short
            ['#003366', 'red'],        # non-hex entry
            ['#003366', 42],           # non-string entry
            '#003366',                 # JSON string, not a list
            {'colors': ['#003366']},   # mapping, not a list
            'not json at all',         # malformed JSON text
        ]
        for bad in cases:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError) as cm:
                    self._new_brand(palette=bad)
                self.assertIn(PALETTE_EXAMPLE, str(cm.exception))

    def test_bad_palette_refused_on_write(self):
        brand = self._new_brand(palette=['#003366'])
        with self.assertRaises(ValidationError):
            brand.write({'palette': ['#003366', '#oops']})
        self.assertEqual(brand.palette, ['#003366'])

    def test_hand_typed_bad_text_refused_on_write(self):
        brand = self._new_brand(palette=['#003366'])
        with self.assertRaises(ValidationError) as cm:
            brand.write({'palette': '[#003366]'})
        self.assertIn(PALETTE_EXAMPLE, str(cm.exception))

    def test_palette_can_be_cleared(self):
        brand = self._new_brand(palette=['#003366'])
        brand.write({'palette': False})
        self.assertFalse(brand.palette)
        brand.write({'palette': '   '})
        self.assertFalse(brand.palette)
