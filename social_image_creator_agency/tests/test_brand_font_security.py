# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import base64

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase

from odoo.addons.social_image_creator_agency.models.social_brand_font import (
    sniff_font_format,
)


class TestFontSignature(TransactionCase):
    """Magic-byte validation of uploaded brand fonts (spec:
    agency-brand-kit). Content decides, not the file name."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.brand = cls.env['social.brand'].create({
            'name': 'Font Test Brand',
            'partner_id': cls.env['res.partner'].create({
                'name': 'Font Test Customer',
                'is_company': True,
            }).id,
        })

    def test_pure_helper_accepts_known_signatures(self):
        self.assertEqual(sniff_font_format(b'\x00\x01\x00\x00' + b'\x00' * 40),
                         'TTF')
        self.assertEqual(sniff_font_format(b'true' + b'\x00' * 40), 'TTF')
        self.assertEqual(sniff_font_format(b'OTTO' + b'\x00' * 40), 'OTF')
        self.assertEqual(sniff_font_format(b'wOFF' + b'\x00' * 40), 'WOFF')
        self.assertEqual(sniff_font_format(b'wOF2' + b'\x00' * 40), 'WOFF2')

    def test_pure_helper_rejects_non_fonts(self):
        self.assertIsNone(sniff_font_format(b'\x89PNG\r\n\x1a\n' + b'\x00' * 40))
        self.assertIsNone(sniff_font_format(b'not a font at all'))
        self.assertIsNone(sniff_font_format(b''))
        self.assertIsNone(sniff_font_format(None))

    def _create_font(self, name, payload, filename):
        return self.env['social.brand.font'].create({
            'brand_id': self.brand.id,
            'name': name,
            'role': 'body',
            'filename': filename,
            'font_file': base64.b64encode(payload),
        })

    def test_valid_ttf_bytes_accepted(self):
        font = self._create_font(
            'FontTestTTF', b'\x00\x01\x00\x00' + b'\x00' * 40, 'FontTestTTF.ttf')
        self.assertTrue(font)
        self.assertEqual(sniff_font_format(base64.b64decode(font.font_file)),
                         'TTF')

    def test_renamed_payload_rejected(self):
        """A PNG renamed to .ttf must be refused by the constraint."""
        with self.assertRaises(ValidationError):
            self._create_font(
                'FontTestFake', b'\x89PNG\r\n\x1a\n' + b'\x00' * 40,
                'FontTestFake.ttf')

    def test_plain_internal_user_denied(self):
        """Without the marketing or customer groups a plain internal user
        must not read brand font binaries."""
        font = self._create_font(
            'FontTestACL', b'\x00\x01\x00\x00' + b'\x00' * 40, 'FontTestACL.ttf')
        plain_user = self.env['res.users'].create({
            'name': 'Font Plain User',
            'login': 'font_plain_user',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        with self.assertRaises(AccessError):
            self.env['social.brand.font'].with_user(plain_user).search(
                [('id', '=', font.id)])
