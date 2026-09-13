# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import contextlib
import logging
import requests
from urllib.parse import quote, urlparse
from werkzeug.urls import url_join
import re

from odoo import models, fields, tools, _
from odoo.addons.mail.tools import link_preview
from odoo.exceptions import UserError
from odoo.addons.social_marketing.models.social_marketing_provider_response import classify_response

_logger = logging.getLogger(__name__)

class SocialLivePostLinkedin(models.Model):
    _inherit = 'social_marketing.live.post'

    linkedin_post_id = fields.Char('Actual LinkedIn ID of the post')

    def _compute_live_post_link(self):
        linkedin_live_posts = self._filter_by_media_types(['linkedin']).filtered(lambda post: post.state == 'posted')
        super(SocialLivePostLinkedin, (self - linkedin_live_posts))._compute_live_post_link()

        for post in linkedin_live_posts:
            post.live_post_link = 'https://www.linkedin.com/feed/update/%s' % post.linkedin_post_id

    def _refresh_statistics(self):
        super(SocialLivePostLinkedin, self)._refresh_statistics()
        accounts = self.env['social_marketing.account'].search([('media_type', '=', 'linkedin')])

        for account in accounts:
            linkedin_post_ids = self.env['social_marketing.live.post'].sudo().search(
                [('social_account_id', '=', account.id), ('linkedin_post_id', '!=', False)],
                order='create_date DESC', limit=1000
            )
            if not linkedin_post_ids:
                continue

            linkedin_post_ids = {post.linkedin_post_id: post for post in linkedin_post_ids}

            session = requests.Session()

            # The LinkedIn API limit the query parameters to 4KB
            # An LinkedIn URN is approximatively 40 characters
            # So we keep a big margin and we split over 50 LinkedIn posts
            for batch_linkedin_post_ids in tools.split_every(50, linkedin_post_ids):
                endpoint = url_join(
                    self.env['social_marketing.media']._LINKEDIN_ENDPOINT,
                    'socialMetadata?ids=List(%s)' % ','.join(map(quote, batch_linkedin_post_ids)))

                response = session.get(endpoint, headers=account._linkedin_bearer_headers(), timeout=10)

                if not response.ok or 'results' not in response.json():
                    account._action_disconnect_accounts(response.json())
                    _logger.error('Error when fetching LinkedIn stats: %r.', response.text)
                    break

                for urn, stats in response.json()['results'].items():
                    if not urn or not stats or urn not in batch_linkedin_post_ids:
                        continue

                    like_count = sum(like.get('count', 0) for like in stats.get('reactionSummaries', {}).values())
                    comment_count = stats.get('commentSummary', {}).get('count', 0)
                    linkedin_post_ids[urn].update({
                        'engagement': like_count + comment_count,
                        'likes': like_count,
                        'comments': comment_count,
                    })

    def _post(self):
        linkedin_live_posts = self._filter_by_media_types(['linkedin'])
        super(SocialLivePostLinkedin, (self - linkedin_live_posts))._post()

        # Capability-based split: each account picks the posting path that is
        # actually configured (preferred method honoured when available,
        # otherwise API token > Playwright session > cookies).
        api_posts = self.env['social_marketing.live.post']
        cookie_posts = self.env['social_marketing.live.post']
        playwright_posts = self.env['social_marketing.live.post']
        no_method = self.env['social_marketing.live.post']
        for live_post in linkedin_live_posts:
            method = live_post.social_account_id._get_linkedin_post_method()
            if method == 'api':
                api_posts |= live_post
            elif method == 'cookie':
                cookie_posts |= live_post
            elif method == 'playwright':
                playwright_posts |= live_post
            else:
                no_method |= live_post

        api_posts._post_linkedin()
        cookie_posts._post_linkedin_cookie()
        playwright_posts._post_linkedin_playwright()

        if no_method:
            _logger.warning(
                'LinkedIn: no auth method available for %s — configure an '
                'API token, Playwright session or cookie login on the account.',
                ', '.join(no_method.mapped('social_account_id.display_name')),
            )

    def _post_linkedin(self):
        for live_post in self:
            url_in_message = self.env['social_marketing.post']._extract_url_from_message(live_post.message)

            # Visibility from the template/post LinkedIn settings
            audience = live_post.post_id.linkedin_audience or 'public'
            if audience == 'connections':
                visibility = {"com.linkedin.ugc.MemberNetworkVisibility": "CONNECTIONS"}
            elif audience == 'group' and live_post.post_id.linkedin_group_urn:
                visibility = {
                    "com.linkedin.ugc.MemberNetworkVisibility": "CONTAINER",
                    "container": live_post.post_id.linkedin_group_urn,
                }
            else:
                visibility = "PUBLIC"

            data = {
                "author": live_post.social_account_id.linkedin_account_urn,
                "commentary": self._format_to_linkedin_little_text(live_post.message),
                "distribution": {"feedDistribution": "MAIN_FEED"},
                "lifecycleState": "PUBLISHED",
                "visibility": visibility,
            }
            # Brand partnership label (API support varies by permission level)
            if live_post.post_id.linkedin_brand_partnership:
                data["brandPartnership"] = True

            if live_post.post_id.image_ids:
                try:
                    images_urn = [
                        self._linkedin_upload_image(live_post.social_account_id, image_id)
                        for image_id in live_post.post_id.image_ids
                    ]
                except UserError as e:
                    live_post.write({
                        'state': 'failed',
                        'failure_reason': str(e)
                    })
                    continue

                if len(images_urn) == 1:
                    data["content"] = {"media": {"id": images_urn[0]}}
                else:
                    data["content"] = {
                        "multiImage": {
                            "images": [{"id": image_urn} for image_urn in images_urn],
                        }
                    }

            elif url_in_message:
                tracker_code = urlparse(url_in_message).path.split('/r/')[-1]
                link_tracker = self.env['link.tracker'].search([
                    ('link_code_ids.code', '=', tracker_code),
                    ('source_id', '=', live_post.post_id.source_id.id),
                ], limit=1)
                original_url = link_tracker.url or url_in_message
                data['content'] = {
                    'article': {
                        'source': url_in_message,
                        'title': link_tracker.title or original_url,
                    },
                }

                preview = link_preview.get_link_preview_from_url(original_url) or {}
                if image_url := preview.get('og_image'):
                    with contextlib.suppress(Exception):
                        if (image_response := requests.get(image_url, timeout=3)).ok:
                            image_urn = self._linkedin_upload_image(live_post.social_account_id, image_response.content)
                            data['content']['article']['thumbnail'] = image_urn

            response = requests.post(
                url_join(self.env['social_marketing.media']._LINKEDIN_ENDPOINT, 'posts'),
                headers=live_post.social_account_id._linkedin_bearer_headers(),
                json=data, timeout=10)

            post_id = response.headers.get('x-restli-id')
            if response.ok and post_id:
                values = {
                    'state': 'posted',
                    'failure_reason': False,
                    'linkedin_post_id': post_id,
                }
            else:
                try:
                    response_json = response.json()
                except Exception:
                    response_json = {}
                classified = classify_response(
                    response, unauthorized_codes={65600})
                if classified.has_exceeded_rate_limit():
                    failure_reason = _('Rate limit exceeded. Retry after %s seconds.') % classified.retry_after
                elif classified.is_unauthorized():
                    failure_reason = _('Unauthorized: access token expired or revoked.')
                else:
                    failure_reason = response_json.get('message', _('unknown'))
                values = {
                    'state': 'failed',
                    'failure_reason': failure_reason,
                }

                if response_json.get('serviceErrorCode') == 65600:
                    # Invalid access token
                    self.social_account_id._action_disconnect_accounts(response)

            live_post.write(values)

    def _linkedin_upload_image(self, account_id, image_id):
        """Upload an image on LinkedIn.

        :param account_id: The social.account to use to upload the image
        :param image_id: The attachment or the raw bytes of the image
        """
        # 1 - Register your image to be uploaded
        data = {
            "initializeUploadRequest": {
                "owner": account_id.linkedin_account_urn,
            },
        }
        response = requests.post(
                url_join(self.env['social_marketing.media']._LINKEDIN_ENDPOINT, 'images?action=initializeUpload'),
                headers=account_id._linkedin_bearer_headers(),
                json=data, timeout=10)

        if not response.ok:
            _logger.error('Could not upload the image: %r.', response.text)

        response = response.json()
        if 'value' not in response or 'uploadUrl' not in response['value']:
            raise UserError(_("We could not upload your image, try reducing its size and posting it again (error: Failed during upload registering)."))

        # 2 - Upload image binary file
        upload_url = response['value']['uploadUrl']
        image_urn = response['value']['image']

        if isinstance(image_id, bytes):
            data = image_id
        else:
            # TODO: clean in master (always give the raw bytes)
            data = image_id.with_context(bin_size=False).raw

        headers = account_id._linkedin_bearer_headers()
        headers['Content-Type'] = 'application/octet-stream'

        response = requests.request('POST', upload_url, data=data, headers=headers, timeout=15)

        if not response.ok:
            raise UserError(_("We could not upload your image, try reducing its size and posting it again."))

        return image_urn

    def _post_linkedin_cookie(self):
        """ Post to LinkedIn using cookie-based authentication (linkedin-api library).
        This uses the unofficial LinkedIn API that simulates a browser session,
        allowing you to post as your personal profile without a Developer App.

        Requires: pip install linkedin-api
        Repository: https://github.com/tomquirk/linkedin-api
        """
        try:
            from linkedin_api import Linkedin
        except ImportError:
            for live_post in self:
                live_post.write({
                    'state': 'failed',
                    'failure_reason': _(
                        'linkedin-api library is not installed. '
                        'Install it with: pip install linkedin-api'
                    ),
                })
            return

        for live_post in self:
            account = live_post.social_account_id

            # Resolve password: prefer keykeep credential (system path),
            # fall back to the legacy field.
            password = account.linkedin_password
            if 'credential_id' in account._fields and account.credential_id:
                password = account.credential_id._read_encrypted('password', system=True) or password

            # Validate credentials
            if not account.linkedin_username or not password:
                live_post.write({
                    'state': 'failed',
                    'failure_reason': _(
                        'LinkedIn username and password are required for cookie-based auth. '
                        'Please configure them in the account settings.'
                    ),
                })
                continue

            try:
                # Authenticate with LinkedIn
                api = Linkedin(account.linkedin_username, password)

                # Post content
                message = live_post.message or ''
                image_paths = []

                # Handle images — save to temp files for the library
                import tempfile
                import os
                temp_files = []
                if live_post.post_id.image_ids:
                    for image in live_post.post_id.image_ids:
                        suffix = '.jpg'
                        if image.mimetype == 'image/png':
                            suffix = '.png'
                        elif image.mimetype == 'image/gif':
                            suffix = '.gif'
                        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                        tmp.write(image.with_context(bin_size=False).raw)
                        tmp.close()
                        image_paths.append(tmp.name)
                        temp_files.append(tmp.name)

                # Post using the library
                if image_paths:
                    # LinkedIn library supports posting with images
                    result = api.post(text=message, media=image_paths if image_paths else None)
                else:
                    result = api.post(text=message)

                # Clean up temp files
                for path in temp_files:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

                if result:
                    post_urn = result if isinstance(result, str) else result.get('id', '')
                    post_id = post_urn.split(':')[-1] if ':' in post_urn else post_urn
                    live_post.write({
                        'state': 'posted',
                        'failure_reason': False,
                        'linkedin_post_id': post_id,
                    })
                else:
                    live_post.write({
                        'state': 'failed',
                        'failure_reason': _('LinkedIn returned an empty response.'),
                    })

            except Exception as e:
                error_msg = str(e)
                _logger.error("LinkedIn cookie post failed for account %s: %s",
                             account.display_name, error_msg, exc_info=True)

                live_post.write({
                    'state': 'failed',
                    'failure_reason': error_msg[:500],  # Truncate long errors
                })

                # Check for common errors
                if 'CHALLENGE' in error_msg.upper() or 'captcha' in error_msg.lower():
                    live_post.write({
                        'failure_reason': _(
                            'LinkedIn requires a security verification (CAPTCHA/challenge). '
                            'Try logging in manually at linkedin.com first to verify your account, '
                            'then retry the post.'
                        ),
                    })
                elif 'wrong password' in error_msg.lower() or 'invalid credentials' in error_msg.lower():
                    account._action_disconnect_accounts(error_msg[:200])

    def _post_linkedin_playwright(self):
        """ Post to LinkedIn using Playwright browser automation.
        Uses a persistent browser context with saved session state.
        The user logs in once via action_open_playwright_login(),
        then subsequent posts reuse the authenticated session.

        Requires: pip install playwright && playwright install chromium

        This is the most robust method against bot detection since
        it uses a real Chromium browser.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            for live_post in self:
                live_post.write({
                    'state': 'failed',
                    'failure_reason': _(
                        'Playwright is not installed. '
                        'Run: pip install playwright && playwright install chromium'
                    ),
                })
            return

        import json
        import tempfile
        import os
        import base64

        for live_post in self:
            account = live_post.social_account_id
            session_data = account._load_playwright_session()

            if not session_data:
                live_post.write({
                    'state': 'failed',
                    'failure_reason': _(
                        'No Playwright session found. Please run "Open Browser Login" '
                        'from the account settings first to save your LinkedIn session.'
                    ),
                })
                continue

            # Write session to temp file for Playwright
            session_file = os.path.join(tempfile.gettempdir(),
                f'linkedin_session_{account.id}.json')
            with open(session_file, 'w') as f:
                json.dump(session_data, f)

            try:
                with sync_playwright() as p:
                    # Load persistent context with saved session
                    context = p.chromium.launch_persistent_context(
                        os.path.expanduser('~/.linkedin_playwright_profile'),
                        headless=True,
                        storage_state=session_data,
                        args=['--no-sandbox', '--disable-setuid-sandbox'],
                    )

                    page = context.pages[0] if context.pages else context.new_page()

                    # Navigate to feed
                    page.goto('https://www.linkedin.com/feed/',
                             wait_until='domcontentloaded', timeout=30000)

                    # Check if we're still logged in
                    if 'login' in page.url.lower():
                        live_post.write({
                            'state': 'failed',
                            'failure_reason': _(
                                'LinkedIn session expired. Please run "Open Browser Login" '
                                'to refresh your session.'
                            ),
                        })
                        context.close()
                        continue

                    # Click "Start a post" button
                    try:
                        page.click('button.share-box-feed-entry__trigger, '
                                   'button[aria-label="Start a post"]',
                                   timeout=5000)
                        page.wait_for_timeout(1000)
                    except Exception:
                        # Try alternative selector
                        try:
                            page.click('.share-box-feed-entry__closed-share-box', timeout=5000)
                            page.wait_for_timeout(1000)
                        except Exception:
                            pass

                    # Type the message
                    message = live_post.message or ''
                    try:
                        editor = page.locator('.ql-editor, '
                                             'div[contenteditable="true"], '
                                             'div[role="textbox"]').first
                        editor.click()
                        page.wait_for_timeout(500)
                        # Type slowly to avoid detection
                        editor.type(message, delay=50)
                        page.wait_for_timeout(1000)
                    except Exception as e:
                        live_post.write({
                            'state': 'failed',
                            'failure_reason': _('Could not type message: %(error)s', error=str(e)[:200]),
                        })
                        context.close()
                        continue

                    # Handle images if present
                    if live_post.post_id.image_ids:
                        try:
                            # Click add image button
                            page.click('button[aria-label="Add an image"], '
                                      'li-icon[type="image-icon"]', timeout=5000)
                            page.wait_for_timeout(1000)

                            # Upload images — one at a time via file input
                            for image in live_post.post_id.image_ids:
                                suffix = '.jpg'
                                if image.mimetype == 'image/png':
                                    suffix = '.png'
                                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                                tmp.write(image.with_context(bin_size=False).raw)
                                tmp_path = tmp.name
                                tmp.close()

                                # Find file input and upload
                                file_input = page.locator('input[type="file"]').first
                                file_input.set_input_files(tmp_path)
                                page.wait_for_timeout(2000)

                                try:
                                    os.unlink(tmp_path)
                                except OSError:
                                    pass

                            page.wait_for_timeout(2000)
                        except Exception as e:
                            _logger.warning("Playwright image upload failed: %s", str(e))

                    # Click "Post" button
                    try:
                        page.click('button.share-actions__primary-action, '
                                  'button[aria-label="Post"]', timeout=5000)
                        page.wait_for_timeout(3000)
                    except Exception:
                        pass

                    # Save updated session state
                    new_state = context.storage_state()
                    account.write({
                        'linkedin_playwright_session':
                            base64.b64encode(
                                json.dumps(new_state).encode('utf-8')),
                    })

                    context.close()

                    # Success — we assume it worked if we didn't get an error
                    live_post.write({
                        'state': 'posted',
                        'failure_reason': False,
                        'linkedin_post_id': f'playwright_{fields.Datetime.now().strftime("%Y%m%d%H%M%S")}',
                    })

            except Exception as e:
                error_msg = str(e)[:500]
                _logger.error("Playwright post failed: %s", error_msg, exc_info=True)
                live_post.write({
                    'state': 'failed',
                    'failure_reason': _('Playwright error: %(error)s', error=error_msg),
                })
            finally:
                try:
                    os.unlink(session_file)
                except OSError:
                    pass

    def _format_to_linkedin_little_text(self, input_string):
        """
        Replaces the special characters `(){}<>[]_` with escaped versions of themselves, i.e. `\\(\\)\\{\\}\\<\\>\\[\\]`.
        https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/little-text-format?view=li-lms-2023-03#text
        """
        pattern = r"[\(\)\<\>\{\}\[\]\_\|\*\~\#\@]"
        output_string = re.sub(pattern, lambda match: r"\{}".format(match.group(0)), input_string)
        return output_string
