# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class SocialImageSize(models.Model):
    """A named canvas size preset for image template variants (design
    decision D9). Ships with standard social/Open Graph presets as data;
    users with configuration rights can add, rename and archive custom
    sizes."""

    _name = 'social.image.size'
    _description = 'Social Image Size Preset'
    _order = 'sequence, id'

    name = fields.Char('Name', required=True, translate=True)
    width = fields.Integer('Width (px)', required=True)
    height = fields.Integer('Height (px)', required=True)
    active = fields.Boolean('Active', default=True)
    sequence = fields.Integer('Sequence', default=10)
