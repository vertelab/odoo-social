# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import logging
import requests

from werkzeug.urls import url_join
from odoo import models, fields

_logger = logging.getLogger(__name__)

INSTAGRAM_ENDPOINT = 'https://graph.facebook.com/v21.0'


class SocialStreamInstagram(models.Model):
    _inherit = 'social_marketing.stream'

    def _fetch_stream_data(self):
        self.ensure_one()
        if self.social_account_id.media_type != 'instagram':
            return super()._fetch_stream_data()

        return self._fetch_instagram_stream()

    def _fetch_instagram_stream(self):
        account = self.social_account_id
        if not account.instagram_business_account_id or not account.instagram_access_token:
            return False

        new_content = False
        stream_type = self.stream_type_id.stream_type

        try:
            if stream_type == 'instagram_feed':
                endpoint = url_join(INSTAGRAM_ENDPOINT,
                    f'{account.instagram_business_account_id}/media')
                params = {
                    'fields': 'id,caption,timestamp,permalink,media_url,'
                             'like_count,comments_count,media_type',
                    'limit': 25,
                    'access_token': account.instagram_access_token,
                }
                response = requests.get(endpoint, params=params, timeout=20)

                if not response.ok:
                    _logger.warning("Instagram stream fetch failed: %s", response.text)
                    return False

                data = response.json()
                for item in data.get('data', []):
                    created = fields.Datetime.from_string(
                        item.get('timestamp', '').replace('T', ' ').split('+')[0])

                    existing = self.env['social_marketing.stream.post'].search_count([
                        ('stream_id', '=', self.id),
                        ('external_id', '=', item.get('id')),
                    ])
                    if existing:
                        continue

                    stream_post = self.env['social_marketing.stream.post'].create({
                        'stream_id': self.id,
                        'message': item.get('caption', ''),
                        'author_name': account.instagram_username or 'Instagram',
                        'published_date': created,
                        'external_id': item.get('id'),
                        'external_url': item.get('permalink', ''),
                        'engagement': (item.get('like_count', 0) +
                                      item.get('comments_count', 0)),
                        'likes_count': item.get('like_count', 0),
                        'comments_count': item.get('comments_count', 0),
                    })

                    # Ladda media
                    if item.get('media_url'):
                        try:
                            img_response = requests.get(item['media_url'], timeout=10)
                            if img_response.ok:
                                self.env['social_marketing.stream.post.image'].create({
                                    'stream_post_id': stream_post.id,
                                    'image': img_response.content,
                                })
                        except Exception:
                            pass

                    new_content = True

        except requests.exceptions.RequestException as e:
            _logger.warning("Instagram stream fetch error: %s", str(e))

        return new_content
