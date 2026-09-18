# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging
import requests

from werkzeug.urls import url_join
from odoo import models, fields

_logger = logging.getLogger(__name__)

FACEBOOK_ENDPOINT = 'https://graph.facebook.com/v21.0'


class SocialStreamFacebook(models.Model):
    _inherit = 'social_marketing.stream'

    def _fetch_stream_data(self):
        self.ensure_one()
        if self.social_account_id.media_type != 'facebook':
            return super()._fetch_stream_data()

        return self._fetch_facebook_stream()

    def _fetch_facebook_stream(self):
        account = self.social_account_id
        if not account.facebook_page_id or not account.facebook_page_access_token:
            return False

        new_content = False
        stream_type = self.stream_type_id.stream_type

        try:
            if stream_type == 'facebook_page_feed':
                endpoint = url_join(FACEBOOK_ENDPOINT,
                    f'{account.facebook_page_id}/feed')
                params = {
                    'fields': 'id,message,created_time,permalink_url,'
                             'reactions.summary(true),comments.summary(true),'
                             'shares,full_picture',
                    'limit': 25,
                    'access_token': account.facebook_page_access_token,
                }
                response = requests.get(endpoint, params=params, timeout=20)

                if not response.ok:
                    _logger.warning("Facebook stream fetch failed: %s", response.text)
                    return False

                data = response.json()
                for item in data.get('data', []):
                    created = fields.Datetime.from_string(
                        item.get('created_time', '').replace('T', ' ').split('+')[0])

                    # Kolla om posten redan finns
                    existing = self.env['social_marketing.stream.post'].search_count([
                        ('stream_id', '=', self.id),
                        ('external_id', '=', item.get('id')),
                    ])
                    if existing:
                        continue

                    reactions = item.get('reactions', {}).get('summary', {}).get('total_count', 0)
                    comments = item.get('comments', {}).get('summary', {}).get('total_count', 0)
                    shares = item.get('shares', {}).get('count', 0)

                    stream_post = self.env['social_marketing.stream.post'].create({
                        'stream_id': self.id,
                        'message': item.get('message', ''),
                        'author_name': account.facebook_page_name or 'Facebook Page',
                        'published_date': created,
                        'external_id': item.get('id'),
                        'external_url': item.get('permalink_url', ''),
                        'engagement': reactions + comments + shares,
                        'likes_count': reactions,
                        'comments_count': comments,
                    })

                    # Ladda bild
                    if item.get('full_picture'):
                        try:
                            img_response = requests.get(item['full_picture'], timeout=10)
                            if img_response.ok:
                                self.env['social_marketing.stream.post.image'].create({
                                    'stream_post_id': stream_post.id,
                                    'image': img_response.content,
                                })
                        except Exception:
                            pass

                    new_content = True

        except requests.exceptions.RequestException as e:
            _logger.warning("Facebook stream fetch error: %s", str(e))

        return new_content
