# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import api, fields, models


class UtmCampaign(models.Model):
    """ Reporting bridge between the social and the email channel.

    Both sides already hang off utm.campaign: social_marketing.post through
    utm_campaign_id, mailing.mailing through campaign_id. Nothing new is
    computed here, the mailing figures are read straight off mailing.mailing
    so the bridge can never drift from what the Mailing app itself reports.
    """
    _inherit = 'utm.campaign'

    mailing_sent_total = fields.Integer(
        compute='_compute_mailing_totals', string='Emails Sent',
        groups='mass_mailing.group_mass_mailing_user')
    mailing_delivered_total = fields.Integer(
        compute='_compute_mailing_totals', string='Emails Delivered',
        groups='mass_mailing.group_mass_mailing_user')
    mailing_opened_total = fields.Integer(
        compute='_compute_mailing_totals', string='Emails Opened',
        groups='mass_mailing.group_mass_mailing_user')
    mailing_clicked_total = fields.Integer(
        compute='_compute_mailing_totals', string='Emails Clicked',
        groups='mass_mailing.group_mass_mailing_user')
    mailing_replied_total = fields.Integer(
        compute='_compute_mailing_totals', string='Emails Replied',
        groups='mass_mailing.group_mass_mailing_user')

    @api.depends('mailing_mail_ids')
    def _compute_mailing_totals(self):
        """ Sum the per mailing statistics that mass_mailing already exposes.

        `sent`, `delivered`, `opened`, `clicked` and `replied` are non stored
        computes on mailing.mailing, so they cannot be read grouped. They do
        compute in one batch over the whole recordset, which is why the search
        below is done once for all campaigns in self.
        """
        totals = {campaign.id: [0, 0, 0, 0, 0] for campaign in self}

        mailings = self.env['mailing.mailing'].search([
            ('campaign_id', 'in', self.ids),
            ('mailing_type', '=', 'mail'),
        ])
        for mailing in mailings:
            campaign_totals = totals.get(mailing.campaign_id.id)
            if campaign_totals is None:
                continue
            campaign_totals[0] += mailing.sent
            campaign_totals[1] += mailing.delivered
            campaign_totals[2] += mailing.opened
            campaign_totals[3] += mailing.clicked
            campaign_totals[4] += mailing.replied

        for campaign in self:
            sent, delivered, opened, clicked, replied = totals[campaign.id]
            campaign.mailing_sent_total = sent
            campaign.mailing_delivered_total = delivered
            campaign.mailing_opened_total = opened
            campaign.mailing_clicked_total = clicked
            campaign.mailing_replied_total = replied

    def action_redirect_to_mailings(self):
        """ Open the mailings of this campaign, using the Mailing app action. """
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'mass_mailing.action_view_mass_mailings_from_campaign')
        action['domain'] = [('campaign_id', '=', self.id), ('mailing_type', '=', 'mail')]
        action['context'] = {'default_campaign_id': self.id}
        return action
