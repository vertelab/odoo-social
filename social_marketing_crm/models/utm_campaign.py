# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import api, fields, models

from .attribution import aggregate_leads


class UtmCampaign(models.Model):
    """ Lead attribution for the campaign as a whole.

    The plain lead count is Odoo's own `crm_lead_count`, added by the crm
    module on utm.campaign. It is not redefined here. What is missing, and
    what this bridge adds, is how many of those leads were won and what
    pipeline revenue they carry.
    """
    _inherit = 'utm.campaign'

    crm_currency_id = fields.Many2one(
        'res.currency', string='Attribution Currency',
        compute='_compute_crm_currency_id',
        help='Company currency, the currency crm.lead expected revenue is stored in.')
    crm_lead_won_count = fields.Integer(
        string='Won Leads', compute='_compute_crm_attribution',
        groups='sales_team.group_sale_salesman')
    crm_expected_revenue = fields.Monetary(
        string='Expected Revenue', currency_field='crm_currency_id',
        compute='_compute_crm_attribution',
        groups='sales_team.group_sale_salesman')

    def _compute_crm_currency_id(self):
        for campaign in self:
            campaign.crm_currency_id = self.env.company.currency_id

    @api.depends_context('company')
    def _compute_crm_attribution(self):
        aggregated = aggregate_leads(self.env, 'campaign_id', self.ids)
        for campaign in self:
            dummy, won_count, revenue = aggregated.get(campaign.id, (0, 0, 0.0))
            campaign.crm_lead_won_count = won_count
            campaign.crm_expected_revenue = revenue

    def action_redirect_to_social_marketing_leads(self):
        """ Open the leads of this campaign.

        crm already ships `action_redirect_to_leads_opportunities` for exactly
        this, so it is reused rather than reimplemented.
        """
        self.ensure_one()
        return self.action_redirect_to_leads_opportunities()
