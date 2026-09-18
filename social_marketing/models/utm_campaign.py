# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models
from odoo.osv import expression


class UtmCampaign(models.Model):
    _inherit = 'utm.campaign'

    social_marketing_post_ids = fields.One2many('social_marketing.post', 'utm_campaign_id', string="All related social media posts", groups="social_marketing.group_social_marketing_user")
    social_marketing_posts_count = fields.Integer(compute="_compute_social_marketing_posts_count", string='Social Media Posts', groups="social_marketing.group_social_marketing_user")
    social_marketing_engagement = fields.Integer(compute="_compute_social_marketing_engagement", string='Number of interactions (likes, shares, comments ...) with the social_marketing.posts', groups="social_marketing.group_social_marketing_user")

    def _compute_social_marketing_engagement(self):
        campaigns_engagement = {campaign.id: 0 for campaign in self}

        posts_data = self.env['social_marketing.post'].search_read(
            [('utm_campaign_id', 'in', self.ids)],
            ['utm_campaign_id', 'engagement']
        )

        for datum in posts_data:
            campaign_id = datum['utm_campaign_id'][0]
            campaigns_engagement[campaign_id] += datum['engagement']

        for campaign in self:
            campaign.social_marketing_engagement = campaigns_engagement[campaign.id]

    def _compute_social_marketing_posts_count(self):
        domain = expression.AND([self._get_social_marketing_posts_domain(), [('utm_campaign_id', 'in', self.ids)]])
        post_data = self.env['social_marketing.post']._read_group(
            domain,
            ['utm_campaign_id'], ['__count']
        )

        mapped_data = {utm_campaign.id: count for utm_campaign, count in post_data}

        for campaign in self:
            campaign.social_marketing_posts_count = mapped_data.get(campaign.id, 0)

    def action_create_new_post(self):
        action = self.env["ir.actions.actions"]._for_xml_id("social.action_social_marketing_post")
        action['views'] = [[False, 'form']]
        action['context'] = {
            'default_utm_campaign_id': self.id,
            'default_account_ids': self.env['social_marketing.account'].search(self._get_social_marketing_media_accounts_domain()).ids
        }
        return action

    def action_redirect_to_social_marketing_media_posts(self):
        action = self.env["ir.actions.actions"]._for_xml_id("social.action_social_marketing_post")
        action['domain'] = self._get_social_marketing_posts_domain()
        action['context'] = {
            "searchpanel_default_state": "posted",
            "search_default_utm_campaign_id": self.id,
            "default_utm_campaign_id": self.id
        }
        return action

    def _get_social_marketing_posts_domain(self):
        """This method will need to be overriden in social_marketing_push_notifications to filter out posts who only are push notifications"""
        return []

    def _get_social_marketing_media_accounts_domain(self):
        """This method will need to be overriden in social_marketing_push_notifications to filter out push_notifications medium"""
        return []
