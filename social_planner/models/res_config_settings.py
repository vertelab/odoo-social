# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    social_planner_default_policy_id = fields.Many2one(
        'communication.policy',
        string='Default Communication Policy',
        config_parameter='social_planner.default_policy_id',
        help='Default policy applied to new communication plans.')

    social_planner_inbox_refresh_interval = fields.Integer(
        string='Inbox Refresh Interval (minutes)',
        config_parameter='social_planner.inbox_refresh_interval',
        default=15,
        help='How often the unified inbox checks for new messages from connected platforms.')

    social_planner_ai_enabled = fields.Boolean(
        string='Enable AI Features',
        config_parameter='social_planner.ai_enabled',
        default=True,
        help='Enable AI-powered content generation, sentiment analysis, and hashtag suggestions.')

    social_planner_auto_approve_ai = fields.Boolean(
        string='Auto-approve AI-generated content',
        config_parameter='social_planner.auto_approve_ai',
        default=False,
        help='When enabled, AI-generated posts are automatically marked as approved.')
