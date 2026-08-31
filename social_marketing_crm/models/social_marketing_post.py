# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models

from .attribution import aggregate_leads


class SocialMarketingPost(models.Model):
    """ Lead attribution for one single post.

    Every social_marketing.post owns its own utm.source (utm.source.mixin),
    and the tracked links published with the post carry that source. A lead
    created from such a link therefore has source_id pointing at this post and
    at no other, which is what makes per post attribution possible at all.
    The campaign figures are the sum over its posts plus whatever else on the
    campaign produced leads, these figures are the post's own share.
    """
    _inherit = 'social_marketing.post'

    crm_currency_id = fields.Many2one(
        'res.currency', string='Attribution Currency',
        compute='_compute_crm_currency_id')
    crm_lead_count = fields.Integer(
        string='Leads', compute='_compute_crm_attribution',
        groups='sales_team.group_sale_salesman')
    crm_lead_won_count = fields.Integer(
        string='Won Leads', compute='_compute_crm_attribution',
        groups='sales_team.group_sale_salesman')
    crm_expected_revenue = fields.Monetary(
        string='Expected Revenue', currency_field='crm_currency_id',
        compute='_compute_crm_attribution',
        groups='sales_team.group_sale_salesman')

    def _compute_crm_currency_id(self):
        for post in self:
            post.crm_currency_id = post.company_id.currency_id or self.env.company.currency_id

    @api.depends('source_id')
    def _compute_crm_attribution(self):
        posts_with_source = self.filtered('source_id')
        aggregated = aggregate_leads(
            self.env, 'source_id', posts_with_source.mapped('source_id').ids)
        for post in self:
            lead_count, won_count, revenue = aggregated.get(post.source_id.id, (0, 0, 0.0))
            post.crm_lead_count = lead_count
            post.crm_lead_won_count = won_count
            post.crm_expected_revenue = revenue

    def action_redirect_to_leads(self):
        """ Open only the leads attributed to this post, through its source. """
        self.ensure_one()
        view = 'crm.crm_lead_all_leads' if self.env.user.has_group('crm.group_use_lead') \
            else 'crm.crm_lead_opportunities'
        action = self.env['ir.actions.act_window']._for_xml_id(view)
        action['name'] = _('Leads from this Post')
        action['view_mode'] = 'list,kanban,graph,pivot,form,calendar'
        action['domain'] = [('source_id', '=', self.source_id.id)]
        action['context'] = {'active_test': False, 'create': False}
        return action
