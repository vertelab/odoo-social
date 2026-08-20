# -*- coding: utf-8 -*-
# Vertel AB AGPL-3

from odoo import _, api, fields, models


class SocialMarketingMediaAsset(models.Model):
    """ Media library — reusable images/videos for social posts. """

    _name = 'social_marketing.media.asset'
    _description = 'Media Asset'
    _order = 'create_date desc'

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active', default=True)
    attachment_id = fields.Many2one('ir.attachment', string='File',
        required=True, ondelete='cascade')
    mimetype = fields.Char(related='attachment_id.mimetype', string='Type')
    file_size = fields.Integer(related='attachment_id.file_size', string='Size')

    asset_type = fields.Selection([
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('other', 'Other'),
    ], string='Asset Type', compute='_compute_asset_type', store=True)
    tags = fields.Char('Tags')
    category = fields.Selection([
        ('product', 'Product'),
        ('lifestyle', 'Lifestyle'),
        ('behind_scenes', 'Behind the Scenes'),
        ('team', 'Team'),
        ('event', 'Event'),
        ('quote', 'Quote / Text'),
        ('other', 'Other'),
    ], string='Category', default='other')

    policy_id = fields.Many2one('communication.policy', string='Policy')
    policy_approved = fields.Boolean('Policy Approved')
    usage_count = fields.Integer('Times Used', compute='_compute_usage_count')
    ai_tags = fields.Text('AI Tags')
    ai_description = fields.Text('AI Description')
    company_id = fields.Many2one('res.company', string='Company',
        default=lambda self: self.env.company)

    @api.depends('mimetype')
    def _compute_asset_type(self):
        for asset in self:
            if asset.mimetype:
                if asset.mimetype.startswith('image'):
                    asset.asset_type = 'image'
                elif asset.mimetype.startswith('video'):
                    asset.asset_type = 'video'
                else:
                    asset.asset_type = 'document'
            else:
                asset.asset_type = 'other'

    def _compute_usage_count(self):
        for asset in self:
            asset.usage_count = self.env['social_marketing.post'].search_count([
                ('image_ids', 'in', [asset.attachment_id.id]),
            ])
