# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging
import requests

from werkzeug.urls import url_join
from odoo import models, fields, _

_logger = logging.getLogger(__name__)

INSTAGRAM_ENDPOINT = 'https://graph.facebook.com/v21.0'


class SocialLivePostInstagram(models.Model):
    _inherit = 'social_marketing.live.post'

    instagram_post_id = fields.Char('Instagram Post ID')

    # Post types
    instagram_post_type = fields.Selection([
        ('feed', 'Feed Post'),
        ('story', 'Story'),
        ('reel', 'Reel'),
    ], string='Instagram Post Type', default='feed')

    # --- Post publishing ---

    def _post(self):
        instagram_live_posts = self._filter_by_media_types(['instagram'])
        super(SocialLivePostInstagram, (self - instagram_live_posts))._post()
        instagram_live_posts._post_instagram()

    def _post_instagram(self):
        for live_post in self:
            account = live_post.social_account_id
            if not account.instagram_business_account_id or not account.instagram_access_token:
                live_post.write({
                    'state': 'failed',
                    'failure_reason': _('Instagram business account not configured.')
                })
                continue

            try:
                # Steg 1: Skapa media container
                container_id = self._instagram_create_container(live_post)
                if not container_id:
                    continue  # Error already written

                # Steg 2: Publicera containern
                result = self._instagram_publish_container(live_post, container_id)
                if result:
                    live_post.write({
                        'state': 'posted',
                        'failure_reason': False,
                        'instagram_post_id': result.get('id'),
                    })
                else:
                    live_post.write({
                        'state': 'failed',
                        'failure_reason': _('Failed to publish Instagram post.')
                    })

            except Exception as e:
                live_post.write({
                    'state': 'failed',
                    'failure_reason': str(e),
                })

    def _instagram_create_container(self, live_post):
        """ Steg 1: Skapa media container på Instagram.
        Instagram kräver en tvåstegsprocess för publicering:
        1. Skapa container (POST /{ig-user-id}/media)
        2. Publicera container (POST /{ig-user-id}/media_publish) """
        account = live_post.social_account_id
        endpoint = url_join(INSTAGRAM_ENDPOINT,
            f'{account.instagram_business_account_id}/media')

        data = {
            'access_token': account.instagram_access_token,
            'caption': live_post.message or '',
        }

        # Hantera media
        images = live_post.post_id.image_ids
        if images:
            # Instagram kräver publika URLs för bilder/videos
            base_url = live_post.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
            if len(images) == 1:
                data['image_url'] = f'{base_url}/web/image/{images[0].id}'
            else:
                # Multi-image carousel
                children = []
                for img in images:
                    children.append(f'{base_url}/web/image/{img.id}')
                data['children'] = children
        else:
            # Text-only post — kräver minst en image URL
            # Använd en standard-bild
            data['image_url'] = f'{base_url}/social_marketing/static/description/icon.png'

        try:
            response = requests.post(endpoint, data=data, timeout=30)
            if response.ok:
                return response.json().get('id')
            else:
                error = response.json().get('error', {})
                _logger.warning("Instagram container creation failed: %s", response.text)
                live_post.write({
                    'state': 'failed',
                    'failure_reason': error.get('error_user_msg') or error.get('message', _('Unknown')),
                })
                return None
        except requests.exceptions.RequestException as e:
            _logger.warning("Instagram container error: %s", str(e))
            return None

    def _instagram_publish_container(self, live_post, container_id):
        """ Steg 2: Publicera containern på Instagram. """
        account = live_post.social_account_id
        endpoint = url_join(INSTAGRAM_ENDPOINT,
            f'{account.instagram_business_account_id}/media_publish')

        data = {
            'creation_id': container_id,
            'access_token': account.instagram_access_token,
        }

        try:
            response = requests.post(endpoint, data=data, timeout=15)
            if response.ok:
                return response.json()
            else:
                _logger.warning("Instagram publish failed: %s", response.text)
                return None
        except requests.exceptions.RequestException as e:
            _logger.warning("Instagram publish error: %s", str(e))
            return None

    # --- Statistics ---

    def _refresh_statistics(self):
        super(SocialLivePostInstagram, self)._refresh_statistics()
        instagram_posts = self.env['social_marketing.live.post'].sudo().search([
            ('social_account_id.media_type', '=', 'instagram'),
            ('instagram_post_id', '!=', False),
            ('state', '=', 'posted'),
        ], order='create_date DESC', limit=500)

        for post in instagram_posts:
            account = post.social_account_id
            try:
                endpoint = url_join(INSTAGRAM_ENDPOINT, post.instagram_post_id)
                params = {
                    'fields': 'like_count,comments_count,timestamp',
                    'access_token': account.instagram_access_token,
                }
                response = requests.get(endpoint, params=params, timeout=10)
                if response.ok:
                    data = response.json()
                    post.engagement = (data.get('like_count', 0) +
                                      data.get('comments_count', 0))
            except Exception:
                continue
