# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SocialAgencyDocumentType(models.Model):
    """Data-driven underlag document types (Strategy, Brief, ...)."""

    _name = 'social.agency.document.type'
    _description = 'Underlag Document Type'
    _order = 'name'

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active', default=True)
    description = fields.Text('Description')
