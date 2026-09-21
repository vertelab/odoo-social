# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models

from .attribution import aggregate_orders


class UtmCampaign(models.Model):
    """ Sales attribution for the campaign as a whole.

    sale already adds `quotation_count` and `invoiced_amount` to utm.campaign.
    Neither is redefined here. What is missing is the step between them: how
    many quotations actually became orders, and what those orders are worth
    before anyone gets round to invoicing them.
    """
    _inherit = 'utm.campaign'

    sale_currency_id = fields.Many2one(
        'res.currency', string='Sales Attribution Currency',
        compute='_compute_sale_currency_id',
        help='Company currency. Attributed revenue is converted into it.')
    sale_quotation_count = fields.Integer(
        string='Attributed Quotations', compute='_compute_sale_attribution',
        groups='sales_team.group_sale_salesman')
    sale_order_count = fields.Integer(
        string='Confirmed Orders', compute='_compute_sale_attribution',
        groups='sales_team.group_sale_salesman')
    sale_order_revenue = fields.Monetary(
        string='Attributed Revenue', currency_field='sale_currency_id',
        compute='_compute_sale_attribution',
        groups='sales_team.group_sale_salesman')

    def _compute_sale_currency_id(self):
        for campaign in self:
            campaign.sale_currency_id = self.env.company.currency_id

    @api.depends_context('company')
    def _compute_sale_attribution(self):
        aggregated = aggregate_orders(self.env, 'campaign_id', self.ids)
        for campaign in self:
            quotations, orders, revenue = aggregated.get(campaign.id, (0, 0, 0.0))
            campaign.sale_quotation_count = quotations
            campaign.sale_order_count = orders
            campaign.sale_order_revenue = revenue

    def action_redirect_to_confirmed_orders(self):
        """ Open the confirmed orders behind the attributed revenue. """
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('sale.action_orders')
        action['name'] = _('Orders from this Campaign')
        action['domain'] = [('campaign_id', '=', self.id), ('state', '=', 'sale')]
        action['context'] = {'create': False, 'default_campaign_id': self.id}
        return action
