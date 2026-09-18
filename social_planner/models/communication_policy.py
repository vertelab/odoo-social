# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models


class CommunicationPolicy(models.Model):
    """ Communication policy — defines *how* the organization communicates.
    The policy is the foundation that governs all communication planning,
    approval workflows, and AI-generated content. """

    _name = 'communication.policy'
    _description = 'Communication Policy'
    _order = 'name'

    name = fields.Char('Policy Name', required=True, translate=True)
    description = fields.Text('Description',
        help="Overall description of the policy's purpose and scope.")
    active = fields.Boolean('Active', default=True)

    # Tone & Brand Voice
    tone_of_voice = fields.Html('Tone of Voice',
        help="Guidelines for tone — formal, personal, humorous, etc.")
    brand_voice_guidelines = fields.Html('Brand Voice Guidelines',
        help="Specific brand voice — words to use/avoid, language rules, style guide.")

    # Publication Rules
    hashtag_policy = fields.Html('Hashtag Policy',
        help="Guidelines for hashtag usage — brand-specific, industry, max per post.")
    posting_frequency_max_daily = fields.Integer('Max Daily Posts',
        help="Maximum posts per channel per day. 0 = no limit.",
        default=5)
    posting_frequency_max_weekly = fields.Integer('Max Weekly Posts',
        help="Maximum posts per channel per week. 0 = no limit.",
        default=20)
    image_guidelines = fields.Html('Image Guidelines',
        help="Guidelines for images — format, size, brand colors, alt-text requirements.")
    prohibited_content = fields.Text('Prohibited Content',
        help="Forbidden topics, words or phrases — one per line. Posts containing "
             "these are automatically flagged.")

    # Approval Chain
    approval_chain = fields.Json('Approval Chain',
        help="Step chain for approval. "
             "Example: [{'role': 'creator', 'action': 'submit'}, "
             "{'role': 'approver', 'action': 'approve'}]")
    response_time_target = fields.Integer('Response Time Target',
        help="Target response time in minutes for comments/DMs.",
        default=60)

    # Crisis Protocol
    crisis_response_protocol = fields.Html('Crisis Response Protocol',
        help="Protocol for crisis management — escalation, channel freeze, "
             "response times, contact persons.")

    # Metadata
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', required=True)
    version = fields.Integer('Version', default=1, readonly=True,
        help="Version number. Auto-incremented on content change.")
    company_id = fields.Many2one('res.company', string='Company',
        default=lambda self: self.env.company)
    owner_id = fields.Many2one('res.users', string='Owner',
        default=lambda self: self.env.user,
        help="Owner/responsible for the policy.")

    # Relations
    plan_ids = fields.One2many('communication.plan', 'policy_id',
        string='Communication Plans',
        help="Plans that follow this policy.")
    plan_count = fields.Integer('Number of Plans', compute='_compute_plan_count')

    @api.depends('plan_ids')
    def _compute_plan_count(self):
        for policy in self:
            policy.plan_count = len(policy.plan_ids)

    # Mirrors the policy content fields whose change increments the version
    # in write() below. Used by the publishing pipeline to flag in-flight
    # posts for compliance re-check.
    _POLICY_CONTENT_FIELDS = [
        'tone_of_voice', 'brand_voice_guidelines', 'hashtag_policy',
        'posting_frequency_max_daily', 'posting_frequency_max_weekly',
        'image_guidelines', 'prohibited_content', 'approval_chain',
        'response_time_target', 'crisis_response_protocol',
    ]

    def write(self, vals):
        """ Auto-increment version on actual policy content change. """
        policy_fields = [
            'tone_of_voice', 'brand_voice_guidelines', 'hashtag_policy',
            'posting_frequency_max_daily', 'posting_frequency_max_weekly',
            'image_guidelines', 'prohibited_content', 'approval_chain',
            'response_time_target', 'crisis_response_protocol',
        ]
        if any(field in vals for field in policy_fields):
            vals['version'] = self.version + 1
        res = super().write(vals)
        # Publishing pipeline: flag in-flight posts for re-check when policy
        # content changes. Completed posts are never re-checked — their
        # snapshot remains authoritative.
        if any(field in vals for field in self._POLICY_CONTENT_FIELDS):
            posts = self.env['social_marketing.post'].search([
                ('policy_id', 'in', self.ids),
                ('approval_state', 'in', [
                    'pending_approval', 'approved', 'awaiting_customer']),
                ('state', 'in', ['draft', 'scheduled', 'posting']),
            ])
            posts.write({'needs_recheck': True})
            for post in posts:
                post._pipeline_log(
                    'needs_recheck', state='pending',
                    result=_('Policy changed to version %s',
                             post.policy_id.version))
        return res

    def action_activate(self):
        self.write({'state': 'active'})

    def action_archive(self):
        self.write({'state': 'archived'})

    def action_draft(self):
        self.write({'state': 'draft'})
