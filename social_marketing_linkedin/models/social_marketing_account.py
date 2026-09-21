# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
import logging
import base64
import requests
from datetime import datetime, timedelta
from urllib.parse import quote
from werkzeug.urls import url_join
from odoo.addons.social_marketing_linkedin.utils import urn_to_id, id_to_urn
from odoo import _, models, fields, api
from odoo.addons.social_marketing.controllers.main import SocialValidationException

_logger = logging.getLogger(__name__)

class SocialAccountLinkedin(models.Model):
    _inherit = 'social_marketing.account'

    linkedin_account_urn = fields.Char('LinkedIn Account URN', readonly=True, help='LinkedIn Account URN')
    linkedin_account_id = fields.Char('LinkedIn Account ID', compute='_compute_linkedin_account_id')
    linkedin_access_token = fields.Char('LinkedIn access token', readonly=True, help='The access token is used to '
                                                                                     'perform request to the REST API')

    # Alternative: Cookie-based auth (linkedin-api library by Tom Quirk)
    # Plus Playwright browser automation
    linkedin_auth_method = fields.Selection([
        ('api', 'Official LinkedIn API'),
        ('cookie', 'Browser Login — Cookie-based (linkedin-api)'),
        ('playwright', 'Browser Login — Playwright (Persistent Session)'),
    ], string='LinkedIn Auth Method', default='api', required=True,
        help="""Choose how this account authenticates with LinkedIn:
- Official LinkedIn API: Uses OAuth 2.0 with a LinkedIn Developer App.
  Requires App Review. Posts on behalf of a Company Page.
- Browser Login — Cookie-based: Uses the linkedin-api library.
  Simulates a mobile browser session. Good for simple posting.
- Browser Login — Playwright: Opens a real Chromium browser.
  You log in once, the session is saved. Most resistant to bot detection.
  Ideal for long-term use. Supports multiple employees.""")
    linkedin_username = fields.Char('LinkedIn Username',
        help='Your LinkedIn login email. Only needed for Cookie-based method.')
    linkedin_password = fields.Char('LinkedIn Password',
        help='Your LinkedIn login password. Stored encrypted. Only needed for Cookie-based method.')

    # Capability badges — each auth path is an independent capability on the
    # same account (official API + Playwright session + cookies can coexist).
    linkedin_has_api = fields.Boolean(
        'Official API', compute='_compute_linkedin_capabilities',
        help='OAuth access token configured — can post via the official API.')
    linkedin_has_playwright = fields.Boolean(
        'Playwright Session', compute='_compute_linkedin_capabilities',
        help='Browser session saved — can scrape feeds/company pages/inbox.')
    linkedin_has_cookie = fields.Boolean(
        'Cookie Login', compute='_compute_linkedin_capabilities',
        help='Username/password configured — can post via linkedin-api (cookies).')

    # Playwright browser automation
    linkedin_playwright_session = fields.Binary('Playwright Session State',
        attachment=True,
        help='Stored browser session state from Playwright persistent context. '
             'Generated after first manual login. This lets Playwright reuse your '
             'logged-in session so you stay authenticated across script runs.')

    @api.depends('linkedin_account_urn')
    def _compute_linkedin_account_id(self):
        """Depending on the used LinkedIn endpoint, we sometimes need the full URN, sometimes only the ID part.

        e.g.: "urn:li:person:12365" -> "12365"
        """
        for social_account in self:
            if social_account.linkedin_account_urn:
                social_account.linkedin_account_id = social_account.linkedin_account_urn.split(':')[-1]
            else:
                social_account.linkedin_account_id = False

    def _compute_stats_link(self):
        linkedin_accounts = self._filter_by_media_types(['linkedin'])
        super(SocialAccountLinkedin, (self - linkedin_accounts))._compute_stats_link()

        for account in linkedin_accounts:
            account.stats_link = 'https://www.linkedin.com/company/%s/admin/analytics/visitors/' % account.linkedin_account_id

    def _compute_statistics(self):
        linkedin_accounts = self._filter_by_media_types(['linkedin'])
        super(SocialAccountLinkedin, (self - linkedin_accounts))._compute_statistics()

        for account in linkedin_accounts:
            all_stats_dict = account._compute_statistics_linkedin()
            # Trends are computed from stored snapshots (see
            # social_marketing.account._compute_snapshot_trends), so we no
            # longer double-fetch the last-30-days window here.
            account.write(all_stats_dict)

    def _linkedin_fetch_followers_count(self):
        """Fetch number of followers from the LinkedIn API."""
        self.ensure_one()
        if not self.linkedin_account_urn.startswith('urn:li:organization:'):
            # Person-konton har inget organization networkSizes-endpoint.
            return 0
        endpoint = url_join(self.env['social_marketing.media']._LINKEDIN_ENDPOINT, 'networkSizes/urn:li:organization:%s' % self.linkedin_account_id)
        # removing X-Restli-Protocol-Version header for this endpoint as it is not required according to LinkedIn Doc.
        # using this header with an endpoint that doesn't support it will cause the request to fail
        headers = self._linkedin_bearer_headers()
        headers.pop('X-Restli-Protocol-Version', None)
        response = requests.get(
            endpoint,
            params={'edgeType': 'COMPANY_FOLLOWED_BY_MEMBER'},
            headers=headers,
            timeout=3)
        if response.status_code != 200:
            return 0
        return response.json().get('firstDegreeSize', 0)

    def _compute_statistics_linkedin(self, last_30d=False):
        """Fetch statistics from the LinkedIn API.

        :param last_30d: If `True`, return the statistics of the last 30 days
                      Else, return the statistics of all the time.

            If we want statistics for the month, we need to choose the granularity
            "month". The time range has to be bigger than the granularity and
            if we have result over 1 month and 1 day (e.g.), the API will return
            2 results (one for the month and one for the day).
            To avoid this, we simply move the end date in the future, so we have
            result  only for this month, in one simple dict.
        """
        self.ensure_one()

        endpoint = url_join(self.env['social_marketing.media']._LINKEDIN_ENDPOINT, 'organizationalEntityShareStatistics')
        params = {
            'q': 'organizationalEntity',
            'organizationalEntity': self.linkedin_account_urn
        }

        if last_30d:
            # The LinkedIn API take timestamp in milliseconds
            end = int((datetime.now() + timedelta(days=2)).timestamp() * 1000)
            start = int((datetime.now() - timedelta(days=30)).timestamp() * 1000)
            endpoint += '?timeIntervals=%s' % '(timeRange:(start:%i,end:%i),timeGranularityType:MONTH)' % (start, end)

        response = requests.get(
            endpoint,
            params=params,
            headers=self._linkedin_bearer_headers(),
            timeout=5)

        if response.status_code != 200:
            return {}

        data = response.json().get('elements', [{}])[0].get('totalShareStatistics', {})

        return {
            'audience': self._linkedin_fetch_followers_count(),
            'engagement': data.get('clickCount', 0) + data.get('likeCount', 0) + data.get('commentCount', 0),
            'stories': data.get('shareCount', 0) + data.get('shareMentionsCount', 0),
        }

    def _backfill_statistics(self, window_start, window_end):
        linkedin_accounts = self._filter_by_media_types(['linkedin'])
        super(SocialAccountLinkedin, (self - linkedin_accounts))._backfill_statistics(window_start, window_end)
        for account in linkedin_accounts:
            if not account.linkedin_account_urn:
                continue
            account._backfill_linkedin_share_stats(window_start, window_end)
            account._backfill_linkedin_follower_stats(window_start, window_end)

    def _backfill_linkedin_share_stats(self, window_start, window_end):
        """Fetch daily share statistics (engagement + impressions) for a window."""
        self.ensure_one()
        endpoint = url_join(
            self.env['social_marketing.media']._LINKEDIN_ENDPOINT,
            'organizationalEntityShareStatistics')
        start_ms = int(window_start.timestamp() * 1000)
        end_ms = int(window_end.timestamp() * 1000)
        endpoint += '?timeIntervals=%s' % '(timeRange:(start:%i,end:%i),timeGranularityType:DAY)' % (start_ms, end_ms)
        params = {'q': 'organizationalEntity', 'organizationalEntity': self.linkedin_account_urn}
        try:
            response = self._backfill_get(endpoint, params=params, headers=self._linkedin_bearer_headers())
            if not response.ok:
                _logger.warning(
                    "LinkedIn share backfill failed for %s: %s", self.display_name, response.text[:200])
                return
            for element in response.json().get('elements', []):
                start = (element.get('timeRange') or {}).get('start')
                if not start:
                    continue
                date = datetime.utcfromtimestamp(start / 1000).strftime('%Y-%m-%d')
                stats = element.get('totalShareStatistics', {})
                engagement = (stats.get('clickCount', 0) + stats.get('likeCount', 0)
                              + stats.get('commentCount', 0) + stats.get('shareCount', 0))
                self._create_stat_snapshot('engagement', engagement, date)
                if stats.get('impressionCount') is not None:
                    self._create_stat_snapshot('impressions', stats.get('impressionCount', 0), date)
        except Exception as e:
            _logger.warning("LinkedIn share backfill error for %s: %s", self.display_name, str(e))

    def _backfill_linkedin_follower_stats(self, window_start, window_end):
        """Best-effort fetch of daily follower statistics for a window."""
        self.ensure_one()
        endpoint = url_join(
            self.env['social_marketing.media']._LINKEDIN_ENDPOINT,
            'organizationalEntityFollowerStatistics')
        start_ms = int(window_start.timestamp() * 1000)
        end_ms = int(window_end.timestamp() * 1000)
        endpoint += '?timeIntervals=%s' % '(timeRange:(start:%i,end:%i),timeGranularityType:DAY)' % (start_ms, end_ms)
        params = {'q': 'organizationalEntity', 'organizationalEntity': self.linkedin_account_urn}
        try:
            response = self._backfill_get(endpoint, params=params, headers=self._linkedin_bearer_headers())
            if not response.ok:
                return
            for element in response.json().get('elements', []):
                start = (element.get('timeRange') or {}).get('start')
                if not start:
                    continue
                date = datetime.utcfromtimestamp(start / 1000).strftime('%Y-%m-%d')
                counts = element.get('followerCountsByDay') or element.get('followerCounts')
                if counts:
                    # take the last entry of the day
                    follower = counts[-1].get('followerCounts', {}).get('organicFollowerCount', 0)
                    self._create_stat_snapshot('audience', follower, date)
        except Exception as e:
            _logger.warning("LinkedIn follower backfill error for %s: %s", self.display_name, str(e))

    @api.model_create_multi
    def create(self, vals_list):
        res = super(SocialAccountLinkedin, self).create(vals_list)

        linkedin_accounts = res.filtered(lambda account: account.media_type == 'linkedin')
        if linkedin_accounts:
            linkedin_accounts._create_default_stream_linkedin()

        return res

    def _linkedin_bearer_headers(self, linkedin_access_token=None):
        if linkedin_access_token is None:
            linkedin_access_token = self.linkedin_access_token
        return {
            'Authorization': 'Bearer %s' % linkedin_access_token,
            'cache-control': 'no-cache',
            'X-Restli-Protocol-Version': '2.0.0',
            'LinkedIn-Version': '202505',
        }

    def _get_linkedin_accounts(self, linkedin_access_token):
        """Get all LinkedIn accounts linkable with the access token.

        Prefers the organization (Company Page) accounts — that requires the
        Community Management API product. The personal/member account is ALWAYS
        added as a fallback (only needs Share on LinkedIn + Sign In), so
        linking works even when the org scopes/products are not authorized.
        """
        _logger.info("=== Getting LinkedIn Accounts ===")
        accounts = []
        try:
            accounts.extend(
                self._get_linkedin_organization_accounts(linkedin_access_token))
        except Exception as exc:  # noqa: BLE001 — fallback, never block linking
            _logger.warning(
                "LinkedIn: org account fetch failed (no Community Management "
                "API?): %s — continuing with the member account.", exc)
        member = self._get_linkedin_member_account(linkedin_access_token)
        if member:
            accounts.append(member)
        return accounts

    def _get_linkedin_organization_accounts(self, linkedin_access_token):
        """Company Page accounts where the user is an admin.

        Requires the Community Management API product. Returns [] when the
        scopes/products are missing instead of raising, so the member fallback
        can still link a personal account.
        """
        # Get organizations where user is admin
        response = self._linkedin_request(
            'organizationAcls',
            params={
                'q': 'roleAssignee',
                'role': 'ADMINISTRATOR',
                'state': 'APPROVED',
            },
            linkedin_access_token=linkedin_access_token,
        )
        _logger.info("organizationAcls response status: %s", response.status_code)
        _logger.info("organizationAcls response: %s", response.text)
        if not response.ok:
            _logger.warning("LinkedIn organizationAcls failed: %s", response.text)
            return []

        account_ids = [
            urn_to_id(organization['organization'])
            for organization in response.json().get('elements', [])
        ]

        response = self._linkedin_request(
            'organizations',
            object_ids=account_ids,
            fields=('id', 'name', 'localizedName', 'vanityName', 'logoV2:(original)'),
            linkedin_access_token=linkedin_access_token,
        )
        if not response.ok:
            _logger.warning("LinkedIn organizations failed: %s", response.text)
            return []

        organization_results = response.json().get('results', {})

        images_urns = [
            values.get('logoV2', {}).get('original')
            for values in organization_results.values()
        ]
        image_url_by_id = self._linkedin_request_images(images_urns, linkedin_access_token)

        accounts = []
        for account_id, organization in organization_results.items():
            image_id = urn_to_id(organization.get('logoV2', {}).get('original'))
            image_url = image_id and image_url_by_id.get(image_id)
            image_data = image_url and requests.get(image_url, timeout=10).content
            accounts.append({
                'name': organization.get('localizedName'),
                'linkedin_account_urn': f"urn:li:organization:{account_id}",
                'linkedin_access_token': linkedin_access_token,
                'social_account_handle': organization.get('vanityName'),
                'image': base64.b64encode(image_data) if image_data else False,
            })
        return accounts

    def _get_linkedin_member_account(self, linkedin_access_token):
        """Personal/member account via the OIDC userinfo endpoint.

        Only needs the 'Sign In with LinkedIn (OpenID Connect)' + 'Share on
        LinkedIn' products (openid/profile/email + w_member_social) — no
        Community Management API required. Returns None on failure.
        """
        headers = self._linkedin_bearer_headers(linkedin_access_token)
        try:
            resp = requests.get(
                'https://api.linkedin.com/v2/userinfo',
                headers=headers, timeout=20)
            if not resp.ok:
                _logger.warning("LinkedIn userinfo failed: %s", resp.text)
                return None
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("LinkedIn userinfo error: %s", exc)
            return None
        sub = data.get('sub')
        if not sub:
            return None
        name = data.get('name') or ' '.join(
            filter(None, (data.get('given_name'), data.get('family_name')))) \
            or 'LinkedIn Profile'
        image_data = False
        picture_url = data.get('picture')
        if picture_url:
            try:
                image_data = base64.b64encode(
                    requests.get(picture_url, timeout=10).content)
            except Exception:  # noqa: BLE001
                image_data = False
        return {
            'name': name,
            'linkedin_account_urn': f"urn:li:person:{sub}",
            'linkedin_access_token': linkedin_access_token,
            'social_account_handle': data.get('preferred_username') or sub,
            'image': image_data,
        }

    def _create_linkedin_accounts(self, access_token, media):
        linkedin_accounts = self._get_linkedin_accounts(access_token)
        if not linkedin_accounts:
            message = _('No LinkedIn account could be linked. Make sure your app has the '
                        'Share on LinkedIn product (for personal posting) or the Community '
                        'Management API product (for Company Pages).')
            raise SocialValidationException(message)

        social_accounts = self.sudo().with_context(active_test=False).search([
            ('media_id', '=', media.id),
            ('linkedin_account_urn', 'in', [l.get('linkedin_account_urn') for l in linkedin_accounts])])

        error_message = social_accounts._get_multi_company_error_message()
        if error_message:
            raise SocialValidationException(error_message)

        existing_accounts = {
            account.linkedin_account_urn: account
            for account in social_accounts
            if account.linkedin_account_urn
        }

        accounts_to_create = []
        for account in linkedin_accounts:
            if account['linkedin_account_urn'] in existing_accounts:
                existing_accounts[account['linkedin_account_urn']].write({
                    'active': True,
                    'linkedin_access_token': account.get('linkedin_access_token'),
                    'social_account_handle': account.get('social_account_handle'),
                    'is_media_disconnected': False,
                    'image': account.get('image')
                })
            else:
                account.update({
                    'media_id': media.id,
                    'is_media_disconnected': False,
                    # Organisation-konton har statistik/trends-endpoints;
                    # person-konton (urn:li:person:*) hoppas över.
                    'has_trends': account['linkedin_account_urn'].startswith('urn:li:organization:'),
                    'has_account_stats': account['linkedin_account_urn'].startswith('urn:li:organization:'),
                })
                accounts_to_create.append(account)

        self.create(accounts_to_create)

    def _create_default_stream_linkedin(self):
        """Create a stream for each organization page."""
        page_posts_stream_type = self.env.ref('social_marketing_linkedin.stream_type_linkedin_company_post')

        streams_to_create = [{
            'media_id': account.media_id.id,
            'stream_type_id': page_posts_stream_type.id,
            'account_id': account.id
        } for account in self
            if account.linkedin_account_urn
            and account.linkedin_account_urn.startswith('urn:li:organization:')]

        if streams_to_create:
            self.env['social_marketing.stream'].create(streams_to_create)

    def _extract_linkedin_picture_url(self, json_data):
        # TODO: remove in master
        return ''

    def _get_linkedin_post_method(self):
        """Return which posting path to use for this account.

        Capability-based: each auth path is an independent capability stored
        on the SAME account record. The preferred ``linkedin_auth_method`` is
        honoured when its capability exists; otherwise we fall back to any
        available capability (API token > Playwright session > cookies).

        Returns 'api', 'cookie', 'playwright' or False (no path available).
        """
        self.ensure_one()
        preferred = self.linkedin_auth_method
        capabilities = {
            'api': bool(self.linkedin_access_token),
            'cookie': bool(self.linkedin_username and self.linkedin_password),
            'playwright': bool(self.linkedin_playwright_session),
        }
        if capabilities.get(preferred):
            return preferred
        for method in ('api', 'playwright', 'cookie'):
            if capabilities.get(method):
                return method
        return False

    @api.depends('linkedin_access_token', 'linkedin_playwright_session',
                 'linkedin_username', 'linkedin_password')
    def _compute_linkedin_capabilities(self):
        """Capability badges shown on the account form (independent auth paths)."""
        for account in self:
            account.linkedin_has_api = bool(account.linkedin_access_token)
            account.linkedin_has_playwright = bool(account.linkedin_playwright_session)
            account.linkedin_has_cookie = bool(
                account.linkedin_username and account.linkedin_password)

    def action_open_playwright_login(self):
        """ Open a Chromium browser via Playwright for manual LinkedIn login.
        The session state (cookies, localStorage) is saved and stored on the account.
        Subsequent posts reuse this session — no re-login needed.

        Requires: pip install playwright && playwright install chromium
        """
        self.ensure_one()

        # Load existing session if available
        session_data = {}
        if self.linkedin_playwright_session:
            import json
            try:
                session_data = json.loads(base64.b64decode(self.linkedin_playwright_session).decode('utf-8'))
            except Exception:
                pass

        # Open browser with persistent context
        import subprocess
        import tempfile
        import os
        import time

        # Create a temp file for the session state
        session_file = os.path.join(tempfile.gettempdir(),
            f'linkedin_playwright_{self.id}.json')

        # Write existing session if available
        if session_data:
            with open(session_file, 'w') as f:
                json.dump(session_data, f)

        # Build a small Python script that Playwright will execute
        # This runs in a subprocess because Playwright needs its own event loop
        script = f'''
import asyncio
import json
import os
from playwright.sync_api import sync_playwright

SESSION_FILE = {repr(session_file)}

def main():
    with sync_playwright() as p:
        # Use persistent context — this saves cookies/session to disk
        user_data_dir = os.path.expanduser("~/.linkedin_playwright_profile")

        context = None
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, 'r') as f:
                    state = json.load(f)
                context = p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    storage_state=state,
                )
            except Exception:
                pass

        if not context:
            context = p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
            )

        page = context.pages[0] if context.pages else context.new_page()

        # Navigate to LinkedIn feed (if already logged in via cookies, it works)
        page.goto("https://www.linkedin.com/feed/")

        print("\\n" + "="*60)
        print("PLAYWRIGHT BROWSER OPEN — LOG IN TO LINKEDIN NOW")
        print("The browser window is open. Please:")
        print("1. Log in to LinkedIn if not already logged in")
        print("2. Complete any security verification (CAPTCHA, 2FA)")
        print("3. Once you see your feed, close the browser window")
        print("="*60 + "\\n")

        # Wait for the user to close the browser
        try:
            page.wait_for_event("close", timeout=300000)  # 5 min timeout
        except Exception:
            pass

        # Save session state
        state = context.storage_state()
        with open(SESSION_FILE, 'w') as f:
            json.dump(state, f)

        print("\\nSession saved successfully! You can now close this terminal.")
        context.close()

if __name__ == "__main__":
    main()
'''

        # Write script to temp file and execute
        script_file = os.path.join(tempfile.gettempdir(),
            f'linkedin_playwright_script_{self.id}.py')
        with open(script_file, 'w') as f:
            f.write(script)

        # Run in background so Odoo doesn't block
        subprocess.Popen(
            ['python3', script_file],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Schedule a job to read back the session file after a delay
        self.env.ref('social_marketing.ir_cron_post_scheduled')._trigger(
            at=fields.Datetime.now() + fields.Datetime.timedelta(minutes=1))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Playwright Browser Opened',
                'message': (
                    'A Chromium browser window should open shortly. '
                    'Log in to LinkedIn, then close the browser. '
                    'The session will be saved automatically.'
                ),
                'type': 'info',
                'sticky': True,
            }
        }

    def _load_playwright_session(self):
        """ Load and return the Playwright session state. """
        self.ensure_one()
        if not self.linkedin_playwright_session:
            return None
        import json
        try:
            return json.loads(
                base64.b64decode(self.linkedin_playwright_session).decode('utf-8'))
        except Exception:
            return None

    ################
    # External API #
    ################

    def _linkedin_request(self, endpoint, params=None, linkedin_access_token=None,
                          object_ids=None, fields=None, method="GET", json=None):
        if not linkedin_access_token:
            self.ensure_one()

        url = url_join(self.env['social_marketing.media']._LINKEDIN_ENDPOINT, endpoint)

        # need to be added manually, so requests doesn't escape them
        get_params = []
        if object_ids:
            get_params.append("ids=List(%s)" % ','.join(map(quote, object_ids)))
        if fields:
            get_params.append('fields=%s' % ','.join(fields))
        if get_params:
            url += "?" + "&".join(get_params)

        return requests.request(
            method,
            url,
            params=params,
            json=json,
            headers=self._linkedin_bearer_headers(linkedin_access_token),
            timeout=5,
        )

    def _linkedin_request_images(self, images_ids, linkedin_access_token=None):
        """Make an API call to get the downloadable URL of the images.

        :param images_ids: Image ids (li:image or digital asset)
        :param linkedin_access_token: Access token to use
        """
        images_urns = [
            f"urn:li:image:{images_id.split(':')[-1]}"
            for images_id in images_ids
            if images_id
        ]
        if not images_urns:
            return {}
        response = self._linkedin_request(
            'images',
            object_ids=images_urns,
            fields=('downloadUrl',),
            linkedin_access_token=linkedin_access_token,
        )
        return {
            image_urn.split(':')[-1]: image_values['downloadUrl']
            for image_urn, image_values in response.json().get('results', {}).items()
        } if response.ok else {}
