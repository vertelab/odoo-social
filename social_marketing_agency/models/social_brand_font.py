# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

FONT_EXTENSIONS = ('.woff2', '.woff', '.ttf', '.otf')


class SocialBrandFont(models.Model):
    """A font file in a brand's kit, looked up by ``role`` by the builder."""

    _name = 'social.brand.font'
    _description = 'Social Brand Font'
    _order = 'sequence, id'

    ROLES = [
        ('heading', 'Heading'),
        ('body', 'Body'),
        ('accent', 'Accent'),
        ('other', 'Other'),
    ]

    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True, ondelete='cascade',
        index=True)
    name = fields.Char('Name', required=True)
    role = fields.Selection(
        ROLES, string='Role', required=True, default='body')
    font_file = fields.Binary('Font File', attachment=True, required=True)
    filename = fields.Char('Filename')
    sequence = fields.Integer('Sequence', default=10)

    @api.constrains('filename')
    def _check_filename(self):
        for rec in self:
            if not rec.filename:
                continue
            if not rec.filename.lower().endswith(FONT_EXTENSIONS):
                raise ValidationError(
                    _('The font file %s must be one of: woff2, woff, ttf, otf.')
                    % rec.filename)
