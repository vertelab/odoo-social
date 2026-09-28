# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCrmAttribution(TransactionCase):
    """ Leads must be attributable to a campaign AND to one single post. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.won_stage = cls.env['crm.stage'].search([('is_won', '=', True)], limit=1)
        if not cls.won_stage:
            cls.won_stage = cls.env['crm.stage'].create({'name': 'Won', 'is_won': True})
        cls.open_stage = cls.env['crm.stage'].search([('is_won', '=', False)], limit=1)
        if not cls.open_stage:
            cls.open_stage = cls.env['crm.stage'].create({'name': 'New', 'is_won': False})

    def _campaign(self, name):
        return self.env['utm.campaign'].create({'name': name})

    def _post(self, campaign, message):
        return self.env['social_marketing.post'].create({
            'message': message,
            'utm_campaign_id': campaign.id,
        })

    def _lead(self, name, campaign=None, source=None, revenue=0.0, won=False):
        return self.env['crm.lead'].create({
            'name': name,
            'type': 'opportunity',
            'campaign_id': campaign.id if campaign else False,
            'source_id': source.id if source else False,
            'expected_revenue': revenue,
            'stage_id': (self.won_stage if won else self.open_stage).id,
        })

    def test_campaign_counts_and_revenue(self):
        campaign = self._campaign('Autumn drive')
        self._lead('Open one', campaign, revenue=1000.0)
        self._lead('Open two', campaign, revenue=2500.0)
        self._lead('Closed', campaign, revenue=500.0, won=True)
        # A lead on no campaign at all must never bleed in.
        self._lead('Unattributed', revenue=99999.0)

        self.assertEqual(campaign.crm_lead_count, 3)
        self.assertEqual(campaign.crm_lead_won_count, 1)
        self.assertEqual(campaign.crm_expected_revenue, 4000.0)
        self.assertEqual(campaign.crm_currency_id, self.env.company.currency_id)

    def test_post_reports_only_its_own_source(self):
        """ The point of the module: two posts on one campaign, split correctly. """
        campaign = self._campaign('Two posts')
        first = self._post(campaign, 'First post')
        second = self._post(campaign, 'Second post')
        self.assertTrue(first.source_id)
        self.assertNotEqual(first.source_id, second.source_id)

        self._lead('From first A', campaign, first.source_id, revenue=1000.0)
        self._lead('From first B', campaign, first.source_id, revenue=1500.0, won=True)
        self._lead('From second', campaign, second.source_id, revenue=400.0)
        # Attributed to the campaign but to neither post.
        self._lead('Campaign only', campaign, revenue=7000.0)

        self.assertEqual(first.crm_lead_count, 2)
        self.assertEqual(first.crm_lead_won_count, 1)
        self.assertEqual(first.crm_expected_revenue, 2500.0)

        self.assertEqual(second.crm_lead_count, 1)
        self.assertEqual(second.crm_lead_won_count, 0)
        self.assertEqual(second.crm_expected_revenue, 400.0)

        # The campaign sees all four, the posts only their own share.
        self.assertEqual(campaign.crm_lead_count, 4)
        self.assertEqual(campaign.crm_expected_revenue, 9900.0)

    def test_batch_read_does_not_leak_between_posts(self):
        campaign = self._campaign('Batch')
        first = self._post(campaign, 'Batch first')
        second = self._post(campaign, 'Batch second')
        self._lead('Only on first', campaign, first.source_id, revenue=250.0)

        posts = first | second
        posts.mapped('crm_lead_count')
        self.assertEqual(first.crm_lead_count, 1)
        self.assertEqual(second.crm_lead_count, 0)
        self.assertEqual(second.crm_expected_revenue, 0.0)

    def test_empty_campaign_and_post_return_zero(self):
        campaign = self._campaign('Nothing here')
        post = self._post(campaign, 'Nothing attributed')

        self.assertEqual(campaign.crm_lead_count, 0)
        self.assertEqual(campaign.crm_lead_won_count, 0)
        self.assertEqual(campaign.crm_expected_revenue, 0.0)
        self.assertEqual(post.crm_lead_count, 0)
        self.assertEqual(post.crm_lead_won_count, 0)
        self.assertEqual(post.crm_expected_revenue, 0.0)

    def test_lost_lead_still_counts_but_carries_no_revenue(self):
        campaign = self._campaign('Lost deal')
        lead = self._lead('Went nowhere', campaign, revenue=5000.0)
        lead.write({'probability': 0, 'active': False})
        campaign.invalidate_recordset()

        self.assertFalse(lead.active)
        self.assertEqual(campaign.crm_lead_count, 1)
        self.assertEqual(campaign.crm_lead_won_count, 0)
        self.assertEqual(campaign.crm_expected_revenue, 0.0)

    def test_navigation_targets_the_source(self):
        campaign = self._campaign('Navigate')
        post = self._post(campaign, 'Navigable post')
        self._lead('Reachable', campaign, post.source_id, revenue=10.0)

        post_action = post.action_redirect_to_leads()
        self.assertEqual(post_action['res_model'], 'crm.lead')
        self.assertIn(('source_id', '=', post.source_id.id), post_action['domain'])

        campaign_action = campaign.action_redirect_to_social_marketing_leads()
        self.assertEqual(campaign_action['res_model'], 'crm.lead')
        self.assertIn(('campaign_id', 'in', campaign.ids), campaign_action['domain'])
