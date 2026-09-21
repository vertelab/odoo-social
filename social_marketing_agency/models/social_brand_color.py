# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')


class SocialBrandColor(models.Model):
    """A single colour in a brand's kit.

    The image builder looks colours up by ``role`` (see
    ``social.brand.get_kit_color``), so a brand normally carries one colour
    per role plus any number of extras with role ``other``.
    """

    _name = 'social.brand.color'
    _description = 'Social Brand Color'
    _order = 'sequence, id'

    ROLES = [
        ('primary', 'Primary'),
        ('secondary', 'Secondary'),
        ('accent', 'Accent'),
        ('background', 'Background'),
        ('text', 'Text'),
        ('other', 'Other'),
    ]

    brand_id = fields.Many2one(
        'social.brand', string='Brand', required=True, ondelete='cascade',
        index=True)
    name = fields.Char('Name', required=True)
    hex = fields.Char(
        'Hex', required=True,
        help="Six digit hex colour including the leading hash, e.g. #1A2B3C.")
    role = fields.Selection(
        ROLES, string='Role', required=True, default='other')
    sequence = fields.Integer('Sequence', default=10)

    @api.constrains('hex')
    def _check_hex(self):
        for rec in self:
            if not HEX_COLOR_RE.match(rec.hex or ''):
                raise ValidationError(
                    _('The colour %s must be a hex value like #1A2B3C.')
                    % (rec.name or ''))
