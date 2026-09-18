# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CommunicationPlan(models.Model):
    """ Communication plan — a campaign-level plan that groups planned posts
    across multiple channels, governed by a communication policy. """

    _name = 'communication.plan'
    _description = 'Communication Plan'
    _order = 'start_date desc, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Plan Name', required=True)
    description = fields.Text('Description',
        help="Purpose and description of the plan.")
    active = fields.Boolean('Active', default=True)

    # Policy link
    policy_id = fields.Many2one('communication.policy', string='Communication Policy',
        required=True, ondelete='restrict', tracking=True,
        help="The policy defining tone, rules and approval chain.")
    policy_state = fields.Selection(related='policy_id.state', string='Policy Status')

    # Timeframe
    start_date = fields.Date('Start Date', required=True, default=fields.Date.today)
    end_date = fields.Date('End Date', required=True)

    # Goals & Audience
    goal = fields.Text('Goal',
        help="Measurable goals for the plan (e.g. increase reach by 25%, generate 50 leads).")
    target_audience = fields.Text('Target Audience',
        help="Description of the target audience for this plan.")

    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', required=True, tracking=True)
    color = fields.Integer('Color', default=0,
        help="Color for calendar display.")

    # Metadata
    company_id = fields.Many2one('res.company', string='Company',
        default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Responsible',
        default=lambda self: self.env.user, tracking=True)

    # Lines
    line_ids = fields.One2many('communication.plan.line', 'plan_id',
        string='Plan Lines', copy=True)
    line_count = fields.Integer('Number of Lines', compute='_compute_line_count')
    post_count = fields.Integer('Number of Posts', compute='_compute_post_count')

    # Completion tracking
    completion_percentage = fields.Float('Completion %', compute='_compute_completion_percentage',
        store=True)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for plan in self:
            plan.line_count = len(plan.line_ids)

    @api.depends('line_ids.post_ids')
    def _compute_post_count(self):
        for plan in self:
            plan.post_count = len(plan.line_ids.mapped('post_ids'))

    @api.depends('line_ids.status', 'line_ids')
    def _compute_completion_percentage(self):
        for plan in self:
            lines = plan.line_ids
            if not lines:
                plan.completion_percentage = 0.0
            else:
                completed = len(lines.filtered(lambda l: l.status == 'completed'))
                plan.completion_percentage = (completed / len(lines)) * 100

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for plan in self:
            if plan.start_date and plan.end_date and plan.start_date > plan.end_date:
                raise ValidationError(_('Start date must be before end date.'))

    def action_activate(self):
        self.write({'state': 'active'})

    def action_complete(self):
        self.write({'state': 'completed'})

    def action_archive(self):
        self.write({'state': 'archived'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_view_posts(self):
        """ Open all posts related to this plan. """
        self.ensure_one()
        post_ids = self.line_ids.mapped('post_ids').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Posts'),
            'res_model': 'social_marketing.post',
            'view_mode': 'kanban,calendar,tree,form',
            'domain': [('id', 'in', post_ids)],
        }

    def _check_plan_completion(self):
        """ Called when a line or post changes status. If all lines are completed,
        automatically complete the plan. """
        for plan in self:
            if plan.line_ids and all(l.status == 'completed' for l in plan.line_ids):
                plan.action_complete()
