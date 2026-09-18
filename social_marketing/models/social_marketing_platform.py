# -*- coding: utf-8 -*-
# Vertel AB AGPL-3

from odoo import fields, models


class SocialMarketingPlatform(models.Model):
    """A social marketing platform (LinkedIn, Facebook, Instagram, Twitter,
    YouTube, Blog, ...). Templates target one or more platforms via
    ``platform_ids`` (many2many_tags); platform-specific settings live in the
    respective bridge modules (social_marketing_linkedin, ...)."""

    _name = 'social_marketing.platform'
    _description = 'Social Marketing Platform'
    _order = 'sequence, name'

    name = fields.Char('Name', required=True, translate=True)
    code = fields.Char(
        'Code', required=True,
        help="Technical code, e.g. 'linkedin', 'facebook', 'blog'.")
    sequence = fields.Integer('Sequence', default=10)
    active = fields.Boolean('Active', default=True)
    color = fields.Integer('Color')
    icon = fields.Char('Icon')
