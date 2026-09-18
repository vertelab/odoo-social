# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import fields, models
from odoo.http import request
from odoo.tools import hmac


class SocialMedia(models.Model):
    """ A social_marketing.media represents the actual Media, ex: Facebook, Twitter, etc...
    As opposed to social_marketing.account that represents an existing account on this media.
    Ex: Odoo Social Facebook Page, Mitchell Admin Twitter Account, ...

    The social_marketing.media is used to store global media configuration (API keys, ...).
    It's also used to install the modules related to that social media (social_marketing_facebook, social_marketing_twitter, ...). """

    _name = 'social_marketing.media'
    _description = 'Social Media'
    _inherit = ['mail.thread']

    name = fields.Char('Name', readonly=True, required=True, translate=True)
    media_description = fields.Char('Description', readonly=True)
    image = fields.Binary('Image', readonly=True)
    media_type = fields.Selection([], readonly=True,
        help="Used to make comparisons when we need to restrict some features to a specific media ('facebook', 'twitter', ...).")
    csrf_token = fields.Char('CSRF Token', compute='_compute_csrf_token',
        help="This token can be used to verify that an incoming request from a social provider has not been forged.")
    account_ids = fields.One2many('social_marketing.account', 'media_id', string="Social Accounts")
    accounts_count = fields.Integer('# Accounts', compute='_compute_accounts_count')
    has_streams = fields.Boolean('Streams Enabled', default=True, readonly=True, required=True,
        help="Controls if social streams are handled on this social media.")
    can_link_accounts = fields.Boolean('Can link accounts?', default=True, readonly=True, required=True,
        help="Controls if we can link accounts or not.")
    stream_type_ids = fields.One2many('social_marketing.stream.type', 'media_id', string="Stream Types")
    max_post_length = fields.Integer('Max Post Length',
        help="Set a maximum number of characters can be posted in post. 0 for no limit.")

    def _compute_accounts_count(self):
        for media in self:
            media.accounts_count = len(media.account_ids)

    def _compute_csrf_token(self):
        for media in self:
            media.csrf_token = hmac(self.env(su=True), 'social_marketing_social-account-csrf-token', media.id)

    def action_add_account(self, company_id=None):
        # Set the company of the futures new accounts (see <social_marketing.account>::_get_default_company)
        if company_id is None:
            company_id = self.env.company.id
        request.session['social_marketing_company_id'] = company_id
        return self._action_add_account()

    def _action_add_account(self):
        """ Every social module should override this method.
        Usually redirects to the social media links that allows accounts to be read by our app. """
        pass
