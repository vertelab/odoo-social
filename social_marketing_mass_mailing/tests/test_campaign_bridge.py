# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCampaignBridge(TransactionCase):
    """ The campaign must report both channels, and each one on its own. """

    def _create_campaign(self, name):
        return self.env['utm.campaign'].create({'name': name})

    def _create_post(self, campaign, message='Hello world'):
        return self.env['social_marketing.post'].create({
            'message': message,
            'utm_campaign_id': campaign.id,
        })

    def _create_mailing(self, campaign, subject='Newsletter'):
        return self.env['mailing.mailing'].create({
            'subject': subject,
            'campaign_id': campaign.id,
            'mailing_model_id': self.env['ir.model']._get_id('res.partner'),
            'body_html': '<p>Hello</p>',
        })

    def test_both_channels_counted(self):
        campaign = self._create_campaign('Both channels')
        self._create_post(campaign, 'First social post')
        self._create_post(campaign, 'Second social post')
        mailings = self._create_mailing(campaign, 'First mailing')
        mailings |= self._create_mailing(campaign, 'Second mailing')
        mailings |= self._create_mailing(campaign, 'Third mailing')

        self.assertEqual(campaign.social_marketing_posts_count, 2)
        self.assertEqual(campaign.mailing_mail_count, 3)
        # The totals are the mailing figures themselves, never recomputed.
        self.assertEqual(campaign.mailing_sent_total, sum(mailings.mapped('sent')))
        self.assertEqual(campaign.mailing_opened_total, sum(mailings.mapped('opened')))
        self.assertEqual(campaign.mailing_clicked_total, sum(mailings.mapped('clicked')))
        self.assertEqual(campaign.mailing_replied_total, sum(mailings.mapped('replied')))
        self.assertEqual(campaign.mailing_delivered_total, sum(mailings.mapped('delivered')))

    def test_social_only_campaign(self):
        campaign = self._create_campaign('Social only')
        self._create_post(campaign, 'Lonely social post')

        self.assertEqual(campaign.social_marketing_posts_count, 1)
        self.assertEqual(campaign.mailing_mail_count, 0)
        self.assertEqual(campaign.mailing_sent_total, 0)
        self.assertEqual(campaign.mailing_opened_total, 0)

    def test_mailing_only_campaign(self):
        campaign = self._create_campaign('Mailing only')
        self._create_mailing(campaign, 'Lonely mailing')

        self.assertEqual(campaign.social_marketing_posts_count, 0)
        self.assertEqual(campaign.social_marketing_engagement, 0)
        self.assertEqual(campaign.mailing_mail_count, 1)
        self.assertEqual(campaign.mailing_sent_total, 0)

    def test_empty_campaign_does_not_error(self):
        campaign = self._create_campaign('Empty')

        self.assertEqual(campaign.social_marketing_posts_count, 0)
        self.assertEqual(campaign.mailing_mail_count, 0)
        self.assertEqual(campaign.mailing_replied_total, 0)

    def test_totals_are_per_campaign(self):
        first = self._create_campaign('First')
        second = self._create_campaign('Second')
        self._create_post(first, 'Post on the first campaign')
        self._create_mailing(second, 'Mailing on the second campaign')

        campaigns = first | second
        # Read as a batch, the compute must not leak between campaigns.
        campaigns.mapped('mailing_sent_total')
        self.assertEqual(first.mailing_mail_count, 0)
        self.assertEqual(second.mailing_mail_count, 1)
        self.assertEqual(first.social_marketing_posts_count, 1)
        self.assertEqual(second.social_marketing_posts_count, 0)

    def test_action_redirect_to_mailings(self):
        campaign = self._create_campaign('Navigation')
        self._create_mailing(campaign, 'Reachable mailing')

        action = campaign.action_redirect_to_mailings()
        self.assertEqual(action['res_model'], 'mailing.mailing')
        self.assertIn(('campaign_id', '=', campaign.id), action['domain'])
