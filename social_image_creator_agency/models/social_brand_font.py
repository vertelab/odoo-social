# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Render service bound: a font file is registered per template render and
# node-canvas keeps it in memory, so 5 MB per family is generous.
MAX_FONT_SIZE = 5 * 1024 * 1024

# Formats node-canvas can register; woff/woff2 depend on the container's
# fontconfig (see render_service/fonts/README.md).
ALLOWED_FONT_EXTENSIONS = ('ttf', 'otf', 'woff', 'woff2')


class SocialBrandFont(models.Model):
    """An uploaded brand font (spec: agency-brand-kit).

    ``name`` is the family name used in Fabric (editor ``fontFamily``,
    scene JSON) and MUST equal the file basename without extension, which is
    exactly how the render service registers files from
    ``render_service/fonts/`` (design decision D6). The file is stored as a
    binary attachment; the render service cannot read Odoo attachments, so
    deployment is a manual copy: use the line's "Download for render
    service" button, drop the file into ``render_service/fonts/`` and POST
    ``/fonts/reload`` (or restart the service). See README.md.
    """

    _name = 'social.brand.font'
    _description = 'Brand Font'
    _order = 'sequence, id'

    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True, ondelete='cascade')
    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char(
        'Family Name', required=True,
        help="Family name in Fabric: fontFamily, scene JSON. Must equal the "
             "file basename without extension, e.g. BrandonGrotesque-Bold "
             "for BrandonGrotesque-Bold.ttf (render service convention).")
    filename = fields.Char(
        'File Name',
        help="Original file name, e.g. BrandonGrotesque-Bold.ttf. Saved as "
             "the attachment name so the download carries the right basename.")
    file = fields.Binary('Font File', attachment=True, required=True)

    @api.constrains('file')
    def _check_file_size(self):
        for font in self:
            # Binary fields come back as raw bytes.
            if font.file and len(font.file) > MAX_FONT_SIZE:
                raise ValidationError(_(
                    "Font file %s is larger than 5 MB.") %
                    (font.filename or font.name or ''))

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
            ('res_field', '=', 'file'),
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
