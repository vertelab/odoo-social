# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import base64

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

# Render service bound: a font file is registered per template render and
# node-canvas keeps it in memory, so 5 MB per family is generous.
MAX_FONT_SIZE = 5 * 1024 * 1024

# Formats node-canvas can register; woff/woff2 depend on the container's
# fontconfig (see render_service/fonts/README.md).
ALLOWED_FONT_EXTENSIONS = ('ttf', 'otf', 'woff', 'woff2')

# Magic signatures of the font containers we accept, longest first so
# e.g. the TTF 00 01 00 00 sfnt version is checked before 'true'.
# Content validation, not the file name, decides: a renamed payload is
# refused (spec: agency-brand-kit).
FONT_MAGIC_SIGNATURES = (
    (b'\x00\x01\x00\x00', 'TTF'),
    (b'true', 'TTF'),
    (b'OTTO', 'OTF'),
    (b'wOFF', 'WOFF'),
    (b'wOF2', 'WOFF2'),
)

FONT_FORMAT_LABELS = 'TTF, OTF, WOFF, WOFF2'


def sniff_font_format(data):
    """Return the font format name for raw file bytes ('TTF', 'OTF',
    'WOFF' or 'WOFF2'), or None when the content does not carry a known
    font signature. Kept pure (no Odoo imports touch it) so check-style
    tests can import it directly."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        return None
    for magic, label in FONT_MAGIC_SIGNATURES:
        if data[:len(magic)] == magic:
            return label
    return None


class SocialBrandFont(models.Model):
    """Adds content validation and a render-service download to the brand
    font model owned by ``social_marketing_agency`` (spec: agency-brand-kit).

    The base model and its ``font_file``/``role`` fields live in
    ``social_marketing_agency``; this module only extends it. Until
    2026-09-29 this class declared ``_name = 'social.brand.font'``, which
    collided with the base model: Odoo loaded the base first (it is a
    dependency) so the redefinition was never applied, this file was dead
    code and its constraints protected nothing. It also redefined ``name``
    to mean "family name", conflicting with the base field of the same name
    meaning "display name", and the view shipped here rendered ``role``,
    which only the base model defines, so the module could not even be
    installed. It is now an ``_inherit`` extension.

    The font file is stored as a binary attachment; the render service
    cannot read Odoo attachments, so deployment is a manual copy: use the
    row's "Download for render service" button, drop the file into
    ``render_service/fonts/`` and POST ``/fonts/reload`` (or restart the
    service). See README.md.
    """

    _inherit = 'social.brand.font'

    def _decode_font_binary(self):
        """Return the raw font bytes for this record.

        A Binary field read through the ORM returns base64-encoded bytes
        (the value lives in an attachment), not the raw file content. Both
        the size and the magic-byte checks need the decoded bytes:
        comparing base64 text against raw magic signatures rejects every
        font.
        """
        self.ensure_one()
        return base64.b64decode(self.font_file)

    @api.constrains('font_file')
    def _check_file_size(self):
        for font in self:
            if not font.font_file:
                continue
            if len(font._decode_font_binary()) > MAX_FONT_SIZE:
                raise ValidationError(_(
                    "Font file %s is larger than 5 MB.") %
                    (font.filename or font.name or ''))

    @api.constrains('font_file')
    def _check_file_signature(self):
        for font in self:
            if not font.font_file:
                continue
            if sniff_font_format(font._decode_font_binary()) is None:
                raise ValidationError(_(
                    "File %(name)s is not a valid font: its content does "
                    "not match any of the supported formats "
                    "(%(formats)s). A renamed file is not enough, upload "
                    "a real font binary.") % {
                    'name': font.filename or font.name or '',
                    'formats': FONT_FORMAT_LABELS})

    @api.constrains('filename')
    def _check_extension(self):
        for font in self:
            if not font.filename:
                continue
            extension = font.filename.rsplit('.', 1)[-1].lower() \
                if '.' in font.filename else ''
            if extension not in ALLOWED_FONT_EXTENSIONS:
                raise ValidationError(_(
                    "Unsupported font file type .%(ext)s on %(name)s. "
                    "Use one of: %(types)s.") % {
                    'ext': extension, 'name': font.filename,
                    'types': ', '.join(ALLOWED_FONT_EXTENSIONS)})

    def action_download_for_render_service(self):
        """Download the font file with the correct basename so it can be
        dropped straight into render_service/fonts/. The family name in the
        editor must match the basename without extension."""
        self.ensure_one()
        attachment = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'font_file'),
        ], limit=1)
        if not attachment:
            raise UserError(_(
                "No font file is stored on %s yet. Upload one first.") %
                self.name)
        attachment.write({'name': self.filename or '%s.ttf' % self.name})
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
