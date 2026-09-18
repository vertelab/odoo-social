# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import json
import logging
import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SocialLivePostPostiz(models.Model):
    """ Publish social media posts through Postiz Public API.
    Postiz handles all platform-specific OAuth, rate limiting, and retries. """

    _inherit = 'social_marketing.live.post'

    postiz_post_id = fields.Char('Postiz Post ID')

    def _post(self):
        """ Route posts through Postiz API when account has a Postiz integration. """
        postiz_live_posts = self.filtered(
            lambda p: p.social_account_id.postiz_integration_id)
        super(SocialLivePostPostiz, (self - postiz_live_posts))._post()
        postiz_live_posts._post_postiz()

    def _post_postiz(self):
        """ Post to the actual platform via Postiz Public API.
        POST /public/v1/posts with platform-specific settings. """
        for live_post in self:
            account = live_post.social_account_id
            post = live_post.post_id

            # Build the API payload
            payload = self._build_postiz_payload(live_post)

            # Send to Postiz
            try:
                url = f"{account._postiz_api_url()}/posts"
                headers = account._postiz_headers()

                _logger.info("Posting via Postiz: integration=%s platform=%s",
                           account.postiz_integration_id,
                           account.media_id.postiz_provider)

                response = requests.post(url, headers=headers, json=payload, timeout=30)

                if response.status_code == 201:
                    result = response.json()
                    live_post.write({
                        'state': 'posted',
                        'failure_reason': False,
                        'postiz_post_id': result.get('id', ''),
                    })
                elif response.status_code == 429:
                    live_post.write({
                        'state': 'failed',
                        'failure_reason': _(
                            'Postiz rate limit reached. The post will be '
                            'retried on the next scheduled run.'),
                    })
                elif response.status_code == 413:
                    live_post.write({
                        'state': 'failed',
                        'failure_reason': _(
                            'Image too large for Postiz (max 50 MB). '
                            'Resize images and retry, or pre-upload via the '
                            '/public/v1/upload endpoint.'),
                    })
                else:
                    error_text = response.text[:500]
                    _logger.error("Postiz post failed: %s %s",
                                response.status_code, error_text)
                    live_post.write({
                        'state': 'failed',
                        'failure_reason': _(
                            'Postiz API error %(code)s: %(error)s',
                            code=response.status_code,
                            error=error_text),
                    })
                    if response.status_code == 401:
                        live_post.write({
                            'failure_reason': _(
                                'Postiz API key is invalid or expired. '
                                'Check your API key in Settings.'),
                        })

            except requests.exceptions.ConnectionError:
                live_post.write({
                    'state': 'failed',
                    'failure_reason': _(
                        'Could not connect to Postiz server. Check that the '
                        'server is running and the API URL is correct in Settings.'),
                })
            except requests.exceptions.Timeout:
                live_post.write({
                    'state': 'failed',
                    'failure_reason': _(
                        'Postiz API request timed out. The post will be '
                        'retried on the next scheduled run.'),
                })
            except Exception as e:
                _logger.exception("Postiz post unexpected error")
                live_post.write({
                    'state': 'failed',
                    'failure_reason': str(e)[:500],
                })

    def _build_postiz_payload(self, live_post):
        """ Build the Postiz API payload for a live post.
        Maps Odoo social_marketing.post fields to Postiz post structure.

        Postiz API payload structure:
        {
            "type": "now" | "schedule",
            "date": "ISO 8601",
            "shortLink": false,
            "tags": [],
            "posts": [{
                "integration": {"id": "postiz-integration-uuid"},
                "value": [{"content": "...", "image": [...]}],
                "settings": {"__type": "platform", ...}
            }]
        }
        """
        account = live_post.social_account_id
        post = live_post.post_id
        provider = account.media_id.postiz_provider or account.media_type

        # Determine post type
        post_type = 'schedule'
        date = fields.Datetime.now().isoformat() + 'Z'
        if post.post_method == 'now':
            post_type = 'now'
        elif post.scheduled_date:
            date = post.scheduled_date.isoformat() + 'Z'

        # Build image references
        images = []
        for img in post.image_ids:
            # Postiz API supports pre-uploaded images or URLs
            base_url = self.env['ir.config_parameter'].sudo().get_param(
                'web.base.url', '')
            image_url = f"{base_url}/web/image/{img.id}"
            images.append({
                'id': str(img.id),
                'path': image_url,
            })

        # Build platform-specific settings
        settings = self._build_postiz_settings(live_post, provider)

        # Build the complete payload
        payload = {
            'type': post_type,
            'date': date,
            'shortLink': False,
            'tags': [],
            'posts': [{
                'integration': {'id': account.postiz_integration_id},
                'value': [{
                    'content': live_post.message or '',
                    'image': images,
                }],
                'settings': settings,
            }],
        }

        _logger.debug("Postiz payload: %s", json.dumps(payload, indent=2))
        return payload

    def _build_postiz_settings(self, live_post, provider):
        """ Build platform-specific settings for the Postiz API payload.
        Each platform has its own settings schema defined by Postiz. """
        post = live_post.post_id
        settings = {'__type': provider}

        # Platform-specific extras
        if provider == 'x':  # Twitter/X
            settings['who_can_reply_post'] = 'everyone'

        elif provider in ('instagram', 'instagram-standalone'):
            # Determine post type from plan_line
            if post.plan_line_id and post.plan_line_id.content_type == 'story':
                settings['post_type'] = 'story'
            elif post.plan_line_id and post.plan_line_id.content_type == 'reel':
                settings['post_type'] = 'reel'
            else:
                settings['post_type'] = 'post'

        elif provider in ('linkedin', 'linkedin-page'):
            settings['post_type'] = 'post'

        elif provider == 'youtube':
            settings['title'] = post.display_name
            settings['privacy'] = 'public'

        elif provider == 'medium':
            settings['title'] = post.display_name
            settings['subtitle'] = ''
            settings['tags'] = []

        elif provider == 'wordpress':
            settings['title'] = post.display_name

        elif provider == 'gmb':  # Google My Business
            settings['topicType'] = 'STANDARD'

        elif provider == 'pinterest':
            settings['title'] = post.display_name
            settings['link'] = ''

        return settings
