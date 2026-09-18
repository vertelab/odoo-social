# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging
import requests

from werkzeug.urls import url_join
from odoo import models, fields, _

_logger = logging.getLogger(__name__)

FACEBOOK_ENDPOINT = 'https://graph.facebook.com/v21.0'


class SocialLivePostFacebook(models.Model):
    _inherit = 'social_marketing.live.post'

    facebook_post_id = fields.Char('Facebook Post ID')

    # --- Post publishing ---

    def _post(self):
        facebook_live_posts = self._filter_by_media_types(['facebook'])
        super(SocialLivePostFacebook, (self - facebook_live_posts))._post()
        facebook_live_posts._post_facebook()

    def _get_facebook_token(self, account):
        """Resolve Facebook page access token (keykeep credential → legacy fallback)."""
        token = account.facebook_page_access_token
        if 'credential_id' in account._fields and account.credential_id:
            token = account.credential_id._read_encrypted('key_value', system=True) or token
        return token

    def _post_facebook(self):
        for live_post in self:
            account = live_post.social_account_id
            if not account.facebook_page_id or not self._get_facebook_token(account):
                live_post.write({
                    'state': 'failed',
                    'failure_reason': _('Facebook page not configured.')
                })
                continue

            # Bygg payload
            data = {
                'message': live_post.message or '',
                'access_token': self._get_facebook_token(account),
            }

            # Hantera bilder
            if live_post.post_id.image_ids:
                # Facebook kräver separata POST-anrop för foton
                try:
                    posted = self._facebook_post_photos(live_post)
                    live_post.write({'state': 'posted', 'failure_reason': False})
                    live_post.facebook_post_id = posted.get('id')
                    continue
                except Exception as e:
                    live_post.write({
                        'state': 'failed',
                        'failure_reason': str(e)
                    })
                    continue

            # Text + länk post
            endpoint = url_join(FACEBOOK_ENDPOINT, f'{account.facebook_page_id}/feed')
            try:
                response = requests.post(endpoint, data=data, timeout=15)

                if response.ok:
                    result = response.json()
                    live_post.write({
                        'state': 'posted',
                        'failure_reason': False,
                        'facebook_post_id': result.get('id'),
                    })
                else:
                    error = response.json().get('error', {})
                    live_post.write({
                        'state': 'failed',
                        'failure_reason': error.get('message', _('Unknown error')),
                    })
                    if error.get('code') in (190, 463, 464):  # Token expired/invalid
                        account._action_disconnect_accounts(response.json())

            except requests.exceptions.RequestException as e:
                live_post.write({
                    'state': 'failed',
                    'failure_reason': str(e),
                })

    def _facebook_post_photos(self, live_post):
        """ Post images to Facebook. Facebook supports multi-image posts
        via the /photos endpoint with published=false, then /feed with attached_media. """
        account = live_post.social_account_id
        images = live_post.post_id.image_ids

        if len(images) == 1:
            # Singelbild — posta direkt
            endpoint = url_join(FACEBOOK_ENDPOINT, f'{account.facebook_page_id}/photos')
            data = {
                'url': f'/web/image/{images[0].id}',
                'caption': live_post.message or '',
                'access_token': self._get_facebook_token(account),
            }
            response = requests.post(endpoint, data=data, timeout=15)
            if response.ok:
                return response.json()
            else:
                raise Exception(response.json().get('error', {}).get('message', 'Unknown'))

        # Multi-image — ladda upp som opublicerade, skapa sen feed-post
        photo_ids = []
        for img in images:
            endpoint = url_join(FACEBOOK_ENDPOINT, f'{account.facebook_page_id}/photos')
            data = {
                'url': f'/web/image/{img.id}',
                'published': 'false',
                'access_token': self._get_facebook_token(account),
            }
            response = requests.post(endpoint, data=data, timeout=15)
            if response.ok:
                photo_ids.append({'media_fbid': response.json().get('id')})
            else:
                _logger.warning("Facebook photo upload failed: %s", response.text)

        if not photo_ids:
            raise Exception(_('Failed to upload any images.'))

        # Skapa feed-post med attached_media
        endpoint = url_join(FACEBOOK_ENDPOINT, f'{account.facebook_page_id}/feed')
        data = {
            'message': live_post.message or '',
            'attached_media': photo_ids,
            'access_token': self._get_facebook_token(account),
        }
        response = requests.post(endpoint, json=data, timeout=15)
        if response.ok:
            return response.json()
        else:
            raise Exception(response.json().get('error', {}).get('message', 'Unknown'))

    # --- Statistics ---

    def _refresh_statistics(self):
        super(SocialLivePostFacebook, self)._refresh_statistics()
        facebook_posts = self.env['social_marketing.live.post'].sudo().search([
            ('social_account_id.media_type', '=', 'facebook'),
            ('facebook_post_id', '!=', False),
            ('state', '=', 'posted'),
        ], order='create_date DESC', limit=500)

        for post in facebook_posts:
            account = post.social_account_id
            try:
                endpoint = url_join(FACEBOOK_ENDPOINT, post.facebook_post_id)
                params = {
                    'fields': 'reactions.summary(true),comments.summary(true),shares',
                    'access_token': self._get_facebook_token(account),
                }
                response = requests.get(endpoint, params=params, timeout=10)
                if response.ok:
                    data = response.json()
                    reactions = data.get('reactions', {}).get('summary', {}).get('total_count', 0)
                    comments = data.get('comments', {}).get('summary', {}).get('total_count', 0)
                    shares = data.get('shares', {}).get('count', 0)
                    post.engagement = reactions + comments + shares
            except Exception:
                continue
