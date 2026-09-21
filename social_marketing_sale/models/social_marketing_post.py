# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models

from .attribution import aggregate_orders


class SocialMarketingPost(models.Model):
    """ Sales attribution for one single post.

    A post owns its own utm.source, so an order created from a link published
    with that post carries source_id pointing at this post and no other. This
    is the figure the whole product exists to produce: not that the post got
    clicks, but that it produced orders worth this much.
    """
    _inherit = 'social_marketing.post'

    sale_currency_id = fields.Many2one(
        'res.currency', string='Sales Attribution Currency',
        compute='_compute_sale_currency_id')
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
        for post in self:
            post.sale_currency_id = post.company_id.currency_id or self.env.company.currency_id

    @api.depends('source_id')
    def _compute_sale_attribution(self):
        posts_with_source = self.filtered('source_id')
        aggregated = aggregate_orders(
            self.env, 'source_id', posts_with_source.mapped('source_id').ids)
        for post in self:
            quotations, orders, revenue = aggregated.get(post.source_id.id, (0, 0, 0.0))
            post.sale_quotation_count = quotations
            post.sale_order_count = orders
            post.sale_order_revenue = revenue

    def action_redirect_to_orders(self):
        """ Open only the confirmed orders attributed to this post. """
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('sale.action_orders')
        action['name'] = _('Orders from this Post')
        action['domain'] = [('source_id', '=', self.source_id.id), ('state', '=', 'sale')]
        action['context'] = {'create': False}
        return action
