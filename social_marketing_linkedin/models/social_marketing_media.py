# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
import uuid
import requests
from werkzeug.urls import url_encode, url_join
from odoo import _, models, fields
from odoo.exceptions import UserError


class SocialMediaLinkedin(models.Model):
    _inherit = 'social_marketing.media'

    _LINKEDIN_ENDPOINT = 'https://api.linkedin.com/rest/'
    _LINKEDIN_SCOPE = ('openid profile email w_member_social '
                       'r_organization_social rw_organization_social '
                       'w_organization_social r_organization_analytics')

    # TODO in master: remove all projections
    # Control the fields returned by the LinkedIn API
    # https://docs.microsoft.com/en-us/linkedin/shared/api-guide/concepts/decoration
    _LINKEDIN_ORGANIZATION_PROJECTION = 'localizedName,vanityName,logoV2(original~:playableStreams)'
    _LINKEDIN_PERSON_PROJECTION = 'id,localizedFirstName,localizedLastName,vanityName,profilePicture(displayImage~:playableStreams)'
    _LINKEDIN_TAG_PROJECTION = 'start,length,value(com.linkedin.common.MemberAttributedEntity(member~(vanityName)),com.linkedin.common.CompanyAttributedEntity(company~(vanityName)))'
    _LINKEDIN_COMMENT_PROJECTION = 'id,comments,$URN,content,message(text,attributes*(%s)),likesSummary,created(time, actor~person(%s)~organization(%s)),commentsSummary(totalFirstLevelComments,selectedComments(~comment(id,$URN,created)) )' % (
        _LINKEDIN_TAG_PROJECTION, _LINKEDIN_PERSON_PROJECTION, _LINKEDIN_ORGANIZATION_PROJECTION)
    _LINKEDIN_STREAM_POST_PROJECTION = 'id,totalShareStatistics,createdAt,content,author~person(%s)~organization(%s), commentary,content(media(id~($URN)),multiImage(images*(id~($URN))),article(thumbnail(id~(downloadUrl)), source, title, description))' % (
        _LINKEDIN_PERSON_PROJECTION, _LINKEDIN_ORGANIZATION_PROJECTION)

    media_type = fields.Selection(selection_add=[('linkedin', 'LinkedIn')])

    def _action_add_account(self):
        self.ensure_one()
        if self.media_type != 'linkedin':
            return super(SocialMediaLinkedin, self)._action_add_account()

        linkedin_use_own_account = self.env['ir.config_parameter'].sudo().get_param(
            'social_marketing.linkedin_use_own_account')
        linkedin_app_id = self.env['ir.config_parameter'].sudo().get_param('social_marketing.linkedin_app_id')
        linkedin_client_secret = self.env['ir.config_parameter'].sudo().get_param(
            'social_marketing.linkedin_client_secret')

        if linkedin_use_own_account:
            if linkedin_app_id and linkedin_client_secret:
                return self._add_linkedin_accounts_from_configuration(linkedin_app_id)
            raise UserError(_(
                "linkedin_app_id and linkedin_client_secret missing. Configure "
                "them under Social settings (LinkedIn)."))
        # No default (Odoo-provided) LinkedIn app is available in this build —
        # require the user's own app configuration instead of silently doing
        # nothing.
        raise UserError(_(
            "No LinkedIn app is configured. Enable 'Use your own LinkedIn "
            "Account' under Social settings and provide an App ID and App "
            "Secret, then use 'Link account' again."))

    def _add_linkedin_accounts_from_configuration(self, linkedin_app_id):
        params = {
            'response_type': 'code',
            'client_id': linkedin_app_id,
            'redirect_uri': self._get_linkedin_redirect_uri(),
            'state': self.csrf_token,
            'scope': self._LINKEDIN_SCOPE,
        }

        return {
            'type': 'ir.actions.act_url',
            'url': 'https://www.linkedin.com/oauth/v2/authorization?%s' % url_encode(params),
            'target': 'self'
        }

    def _get_linkedin_redirect_uri(self):
        return url_join(self.get_base_url(), 'social_marketing_linkedin/callback')