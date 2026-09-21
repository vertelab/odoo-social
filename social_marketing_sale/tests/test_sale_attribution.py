# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSaleAttribution(TransactionCase):
    """ Orders must be attributable to a campaign AND to one single post. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_currency = cls.env.company.currency_id
        cls.partner = cls.env['res.partner'].create({'name': 'Attribution Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'Attribution Service',
            'type': 'service',
            'list_price': 100.0,
        })

        # A second currency, worth a tenth of the company currency, so the
        # naive float sum and the converted sum can never look alike.
        cls.foreign_currency = cls.env['res.currency'].with_context(
            active_test=False).search([('id', '!=', cls.company_currency.id)], limit=1)
        assert cls.foreign_currency, "The rig needs at least two currencies"
        cls.foreign_currency.active = True
        cls.env['res.currency.rate'].search([
            ('currency_id', '=', cls.foreign_currency.id),
        ]).unlink()
        cls.env['res.currency.rate'].create({
            'name': '2020-01-01',
            'currency_id': cls.foreign_currency.id,
            'rate': 10.0,
            'company_id': cls.env.company.id,
        })
        cls.foreign_pricelist = cls.env['product.pricelist'].create({
            'name': 'Attribution foreign pricelist',
            'currency_id': cls.foreign_currency.id,
        })

    def _campaign(self, name):
        return self.env['utm.campaign'].create({'name': name})

    def _post(self, campaign, message):
        return self.env['social_marketing.post'].create({
            'message': message,
            'utm_campaign_id': campaign.id,
        })

    def _order(self, amount, campaign=None, source=None, confirm=True, pricelist=None):
        values = {
            'partner_id': self.partner.id,
            'campaign_id': campaign.id if campaign else False,
            'source_id': source.id if source else False,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1,
                'price_unit': amount,
                'tax_id': [(5, 0, 0)],
            })],
        }
        if pricelist:
            values['pricelist_id'] = pricelist.id
        order = self.env['sale.order'].create(values)
        if confirm:
            order.action_confirm()
        return order

    def test_campaign_counts_and_revenue(self):
        campaign = self._campaign('Autumn drive')
        self._order(1000.0, campaign)
        self._order(2500.0, campaign)
        quotation = self._order(9999.0, campaign, confirm=False)
        # An order on no campaign at all must never bleed in.
        self._order(77777.0)

        self.assertEqual(quotation.state, 'draft')
        self.assertEqual(campaign.sale_order_count, 2)
        self.assertEqual(campaign.sale_quotation_count, 3)
        self.assertEqual(campaign.sale_order_revenue, 3500.0)
        self.assertEqual(campaign.sale_currency_id, self.company_currency)

    def test_post_reports_only_its_own_source(self):
        """ The point of the module: two posts on one campaign, split correctly. """
        campaign = self._campaign('Two posts')
        first = self._post(campaign, 'First post')
        second = self._post(campaign, 'Second post')
        self.assertNotEqual(first.source_id, second.source_id)

        self._order(1200.0, campaign, first.source_id)
        self._order(800.0, campaign, first.source_id)
        self._order(300.0, campaign, second.source_id)
        # Attributed to the campaign but to neither post.
        self._order(5000.0, campaign)

        self.assertEqual(first.sale_order_count, 2)
        self.assertEqual(first.sale_order_revenue, 2000.0)
        self.assertEqual(second.sale_order_count, 1)
        self.assertEqual(second.sale_order_revenue, 300.0)

        self.assertEqual(campaign.sale_order_count, 4)
        self.assertEqual(campaign.sale_order_revenue, 7300.0)

    def test_quotations_are_not_revenue(self):
        campaign = self._campaign('Only hope')
        post = self._post(campaign, 'Hopeful post')
        self._order(4000.0, campaign, post.source_id, confirm=False)

        self.assertEqual(campaign.sale_quotation_count, 1)
        self.assertEqual(campaign.sale_order_count, 0)
        self.assertEqual(campaign.sale_order_revenue, 0.0)
        self.assertEqual(post.sale_quotation_count, 1)
        self.assertEqual(post.sale_order_revenue, 0.0)

    def test_cancelled_orders_are_excluded(self):
        campaign = self._campaign('Cancelled')
        order = self._order(1000.0, campaign)
        order._action_cancel()
        campaign.invalidate_recordset()

        self.assertEqual(order.state, 'cancel')
        self.assertEqual(campaign.sale_quotation_count, 0)
        self.assertEqual(campaign.sale_order_count, 0)
        self.assertEqual(campaign.sale_order_revenue, 0.0)

    def test_revenue_is_not_a_naive_float_sum_across_currencies(self):
        campaign = self._campaign('Two currencies')
        post = self._post(campaign, 'International post')
        home = self._order(1000.0, campaign, post.source_id)
        away = self._order(10000.0, campaign, post.source_id,
                           pricelist=self.foreign_pricelist)

        self.assertEqual(home.currency_id, self.company_currency)
        self.assertEqual(away.currency_id, self.foreign_currency)
        self.assertEqual(away.currency_rate, 10.0)

        naive_sum = home.amount_total + away.amount_total
        expected = home.amount_total + away.amount_total / away.currency_rate

        self.assertEqual(campaign.sale_order_revenue, expected)
        self.assertEqual(post.sale_order_revenue, expected)
        self.assertNotEqual(campaign.sale_order_revenue, naive_sum)

    def test_batch_read_does_not_leak_between_posts(self):
        campaign = self._campaign('Batch')
        first = self._post(campaign, 'Batch first')
        second = self._post(campaign, 'Batch second')
        self._order(250.0, campaign, first.source_id)

        (first | second).mapped('sale_order_count')
        self.assertEqual(first.sale_order_count, 1)
        self.assertEqual(second.sale_order_count, 0)
        self.assertEqual(second.sale_order_revenue, 0.0)

    def test_empty_campaign_and_post_return_zero(self):
        campaign = self._campaign('Nothing here')
        post = self._post(campaign, 'Nothing attributed')

        self.assertEqual(campaign.sale_order_count, 0)
        self.assertEqual(campaign.sale_order_revenue, 0.0)
        self.assertEqual(post.sale_quotation_count, 0)
        self.assertEqual(post.sale_order_count, 0)
        self.assertEqual(post.sale_order_revenue, 0.0)

    def test_navigation_targets_the_source(self):
        campaign = self._campaign('Navigate')
        post = self._post(campaign, 'Navigable post')
        self._order(10.0, campaign, post.source_id)

        post_action = post.action_redirect_to_orders()
        self.assertEqual(post_action['res_model'], 'sale.order')
        self.assertIn(('source_id', '=', post.source_id.id), post_action['domain'])

        campaign_action = campaign.action_redirect_to_confirmed_orders()
        self.assertEqual(campaign_action['res_model'], 'sale.order')
        self.assertIn(('campaign_id', '=', campaign.id), campaign_action['domain'])
