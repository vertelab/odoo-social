# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3
import logging
import requests
from datetime import datetime
from urllib.parse import quote
from werkzeug.urls import url_join
from urllib.parse import urlparse
import re

from odoo import models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class SocialStreamLinkedIn(models.Model):
    _inherit = 'social_marketing.stream'

    linkedin_company_public_id = fields.Char(
        'LinkedIn Company ID',
        help='LinkedIn public identifier of the company page to scrape '
             '(e.g. "ucs-onedo" from linkedin.com/company/ucs-onedo). '
             'Only used for the "Company Page" stream type.',
    )
    linkedin_feed_max_posts = fields.Integer(
        'Max Posts per Fetch', default=50,
        help='Maximum number of posts to load when scraping (infinite scroll steps).',
    )

    def _apply_default_name(self):
        linkedin_streams = self.filtered(lambda s: s.media_id.media_type == 'linkedin')
        super(SocialStreamLinkedIn, (self - linkedin_streams))._apply_default_name()

        for stream in linkedin_streams:
            stream.write({'name': '%s: %s' % (stream.stream_type_id.name, stream.social_account_id.name)})

    def _fetch_stream_data(self):
        """Fetch stream data, return True if new data.

        We need to perform 2 HTTP requests. One to retrieve all the posts of
        the organization page and the other, in batch, to retrieve the
        statistics of all posts (there are 2 different endpoints)."""
        self.ensure_one()
        if self.media_id.media_type != 'linkedin':
            return super(SocialStreamLinkedIn, self)._fetch_stream_data()

        # Browser-scraped stream types (Playwright session on the account)
        if self.stream_type_id.stream_type in ('linkedin_company_page', 'linkedin_feed'):
            return self._fetch_linkedin_playwright()

        # retrieve post information
        if self.stream_type_id.stream_type != 'linkedin_company_post':
            raise UserError(_('Wrong stream type for "%s"', self.name))

        posts_response = self.social_account_id._linkedin_request(
            "posts",
            params={
                'q': 'author',
                'count': 100,
                'author': self.social_account_id.linkedin_account_urn,
            },
            fields=('id', 'createdAt', 'author', 'content', 'commentary')
        )

        if posts_response.status_code == 429:
            error_data = posts_response.json()
            _logger.warning(
                "LinkedIn API rate limit reached for account %s. "
                "Daily limit will reset. Error: %s",
                self.social_account_id.name,
                error_data.get('message', 'Rate limit exceeded')
            )
            # Don't disconnect account for rate limiting - it's temporary
            return False

        if posts_response.status_code != 200 or 'elements' not in posts_response.json():
            self.sudo().social_account_id._action_disconnect_accounts(posts_response.json())
            return False

        stream_post_data = posts_response.json()['elements']

        self._prepare_linkedin_stream_post_images(stream_post_data)

        linkedin_post_data = {
            stream_post_data.get('id'): self._prepare_linkedin_stream_post_values(stream_post_data)
            for stream_post_data in stream_post_data
        }

        # retrieve post statistics
        stats_endpoint = url_join(
            self.env['social_marketing.media']._LINKEDIN_ENDPOINT,
            'socialActions?ids=List(%s)' % ','.join([quote(urn) for urn in linkedin_post_data]))
        stats_response = requests.get(stats_endpoint, params={'count': 100}, headers=self.social_account_id._linkedin_bearer_headers(), timeout=5).json()

        if 'results' in stats_response:
            for post_urn, post_data in stats_response['results'].items():
                linkedin_post_data[post_urn].update({
                    'linkedin_comments_count': post_data.get('commentsSummary', {}).get('totalFirstLevelComments', 0),
                    'linkedin_likes_count': post_data.get('likesSummary', {}).get('totalLikes', 0),
                })

        # create/update post values
        existing_post_urns = {
            stream_post.linkedin_post_urn: stream_post
            for stream_post in self.env['social_marketing.stream.post'].search([
                ('stream_id', '=', self.id),
                ('linkedin_post_urn', 'in', list(linkedin_post_data.keys()))])
        }

        post_to_create = []
        for post_urn in linkedin_post_data:
            if post_urn in existing_post_urns:
                existing_post_urns[post_urn].sudo().write(linkedin_post_data[post_urn])
            else:
                post_to_create.append(linkedin_post_data[post_urn])

        if post_to_create:
            self.env['social_marketing.stream.post'].sudo().create(post_to_create)

        return bool(post_to_create)

    def _format_linkedin_name(self, json_data):
        user_name = '%s %s' % (json_data.get('localizedLastName', ''), json_data.get('localizedFirstName', ''))
        return json_data.get('localizedName', user_name)

    def _prepare_linkedin_stream_post_images(self, posts_data):
        """Fetch the images URLs and insert their URL in posts_data."""
        all_image_urns = set()
        for post in posts_data:
            # multi-images post
            images = post.get('content', {}).get('multiImage', {}).get('images', [])
            all_image_urns |= {quote(image['id']) for image in images}
            # single image post
            if image_urn := post.get('content', {}).get('media', {}).get('id'):
                all_image_urns.add(quote(image_urn))
            # article thumbnail
            if thumbnail_urn := post.get('content', {}).get('article', {}).get('thumbnail'):
                all_image_urns.add(quote(thumbnail_urn))

        if not all_image_urns:
            return

        images_endpoint = url_join(
            self.env['social_marketing.media']._LINKEDIN_ENDPOINT,
            'images?ids=List(%s)' % ",".join(all_image_urns))
        response = requests.get(
            images_endpoint,
            params={},
            headers=self.social_account_id._linkedin_bearer_headers(),
            timeout=10,
        )

        if not response.ok:
            return

        url_by_urn = {
            image: image_values["downloadUrl"]
            for image, image_values in response.json()["results"].items()
            if image_values.get("downloadUrl")
        }

        # Insert image in the result like the LinkedIn projection should do...
        for post in posts_data:
            # multi-images post
            images = post.get('content', {}).get('multiImage', {}).get('images', [])
            for image in images:
                image["downloadUrl"] = url_by_urn.get(image.get("id"))

            # single image post
            if image_urn := post.get("content", {}).get("media", {}).get("id"):
                post["content"]["media"]["downloadUrl"] = url_by_urn.get(image_urn)

            # article thumbnail
            if thumbnail_urn := post.get("content", {}).get("article", {}).get("thumbnail"):
                post["content"]["article"]["~thumbnail"] = {"downloadUrl": url_by_urn.get(thumbnail_urn)}

    def _prepare_linkedin_stream_post_values(self, post_data):
        article = post_data.get('content', {}).get('article', {})
        author_image = f"/web/image?model=social.account&id={self.social_account_id.id}&field=image"
        return {
            'stream_id': self.id,
            'author_name': self.social_account_id.name,
            'published_date': datetime.fromtimestamp(post_data.get('createdAt', 0) / 1000),
            'linkedin_post_urn': post_data.get('id'),
            'linkedin_author_urn': post_data.get('author'),
            'linkedin_author_image_url': author_image,
            'message': self._format_from_linkedin_little_text(post_data.get('commentary', '')),
            'stream_post_image_ids': [(5, 0)] + [(0, 0, image_value) for image_value in self._extract_linkedin_image(post_data)],
            **self._extract_linkedin_article(article),
        }

    def _extract_linkedin_image(self, post_data):
        # single image post
        single_image = post_data.get('content', {}).get('media', {}).get('downloadUrl')
        if single_image:
            return [{'image_url': self._enforce_url_scheme(single_image)}]

        # multi-images post
        if images := post_data.get('content', {}).get('multiImage', {}).get('images', []):
            return [
                {'image_url': self._enforce_url_scheme(image.get('downloadUrl'))}
                for image in images if image.get('downloadUrl')
            ]

        # article with thumbnail
        if thumbnail_url := post_data.get('content', {}).get('article', {}).get('~thumbnail', {}).get('downloadUrl'):
            return [{'image_url': self._enforce_url_scheme(thumbnail_url)}]

        return []

    def _extract_linkedin_article(self, article):
        if not article:
            return {}

        return {
            'link_title': article.get('title', '') or article.get('source', ''),
            'link_description': article.get('description', ''),
            'link_url': self._enforce_url_scheme(article.get('source'))
        }

    def _enforce_url_scheme(self, url):
        """Some URLs doesn't starts by "https://". But if we use those bad URLs
        in a HTML link, it will redirect the user the actual website.
        That's why we need to fix those URLs.
        e.g.:
            <a href="www.bad_url.com"/>
        """
        if not url or urlparse(url).scheme:
            return url

        return 'https://%s' % url

    def _format_from_linkedin_little_text(self, input_string):
        """
        Replaces escaped versions of the characters `(){}<>[]_` with their original characters,
        """
        pattern = "\\\\([\\(\\)\\<\\>\\{\\}\\[\\]\\_\\|\\*\\~\\#\\@])"
        output_string = re.sub(pattern, lambda match: match.group(1), input_string)
        return output_string

    # ────────────────────────────────────────────────────────────
    # Playwright (browser scraping) — linkedin_company_page / linkedin_feed
    # ────────────────────────────────────────────────────────────

    def _fetch_linkedin_playwright(self):
        """Fetch stream data by scraping LinkedIn with a real Chromium browser
        (Playwright) using the persistent session saved on the social account.

        Used by the 'linkedin_company_page' (any company page) and
        'linkedin_feed' (the user's feed) stream types — the official REST API
        cannot deliver those.

        Returns True if new posts were inserted.
        """
        self.ensure_one()
        account = self.social_account_id
        session = account._load_playwright_session()
        if not session:
            _logger.warning(
                'LinkedIn stream %s: no Playwright session on account %s. '
                'Run "Browser Login — Playwright" on the account first.',
                self.name, account.name,
            )
            return False

        if self.stream_type_id.stream_type == 'linkedin_company_page':
            if not self.linkedin_company_public_id:
                _logger.warning('LinkedIn stream %s: no company public ID set.', self.name)
                return False
            url = 'https://www.linkedin.com/company/%s/posts/' % self.linkedin_company_public_id
        else:  # linkedin_feed
            url = 'https://www.linkedin.com/feed/'

        max_scrolls = max(1, (self.linkedin_feed_max_posts or 50) // 10)

        import json
        import os
        import shutil
        import subprocess
        import tempfile

        tmpdir = tempfile.mkdtemp(prefix='linkedin_pw_')
        session_file = os.path.join(tmpdir, 'storage_state.json')
        script_file = os.path.join(tmpdir, 'scrape.py')
        try:
            with open(session_file, 'w') as f:
                json.dump(session, f)
            with open(script_file, 'w') as f:
                f.write(self._LINKEDIN_PLAYWRIGHT_SCRIPT)

            proc = subprocess.run(
                ['bash', '-c', 'ulimit -v unlimited && exec xvfb-run -a python3 "$@"',
                 'pw-run', script_file, url, str(max_scrolls), session_file],
                capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired:
            _logger.error('LinkedIn stream %s: Playwright scraping timed out.', self.name)
            return False
        except Exception as e:
            _logger.error('LinkedIn stream %s: Playwright subprocess error: %s', self.name, e)
            return False
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        if proc.returncode != 0:
            _logger.error(
                'LinkedIn stream %s: Playwright scraping failed (%s): %s',
                self.name, proc.returncode, (proc.stderr or '')[-500:],
            )
            return False

        try:
            result = json.loads(proc.stdout.strip().split('\n')[-1])
        except (ValueError, IndexError):
            _logger.error('LinkedIn stream %s: bad Playwright output: %s',
                          self.name, proc.stdout[-300:])
            return False

        if result.get('error'):
            _logger.warning('LinkedIn stream %s: %s', self.name, result['error'])
            return False

        posts = result.get('posts') or []
        if not posts:
            _logger.info('LinkedIn stream %s: no posts returned by scraper.', self.name)
            return False

        return self._process_linkedin_playwright_posts(posts)

    def _process_linkedin_playwright_posts(self, posts):
        """Create/update stream.post records from scraped post dicts.

        Dedupes on linkedin_post_urn (existing pattern).
        """
        post_vals = {}
        for p in posts:
            urn = p.get('urn') or ''
            if not urn:
                continue
            vals = self._prepare_linkedin_playwright_post_values(p)
            if vals:
                post_vals[urn] = vals

        if not post_vals:
            return False

        existing = {
            sp.linkedin_post_urn: sp
            for sp in self.env['social_marketing.stream.post'].sudo().search([
                ('stream_id', '=', self.id),
                ('linkedin_post_urn', 'in', list(post_vals)),
            ])
        }

        to_create = []
        for urn, vals in post_vals.items():
            if urn in existing:
                existing[urn].sudo().write(vals)
            else:
                to_create.append(vals)

        if to_create:
            self.env['social_marketing.stream.post'].sudo().create(to_create)
            _logger.info('LinkedIn stream %s: created %d posts', self.name, len(to_create))

        return bool(to_create)

    def _prepare_linkedin_playwright_post_values(self, post):
        """Map a scraped post dict to stream.post values."""
        urn = post.get('urn') or ''
        urn_id = urn.split(':')[-1] if ':' in urn else urn

        # author urn: from author URL (company/<id> or in/<id>)
        author_url = post.get('authorUrl') or ''
        author_urn = False
        if '/company/' in author_url:
            author_urn = 'urn:li:company:%s' % author_url.split('/company/')[-1].strip('/').split('?')[0]
        elif '/in/' in author_url:
            author_urn = 'urn:li:person:%s' % author_url.split('/in/')[-1].strip('/').split('?')[0]
        elif self.linkedin_company_public_id:
            author_urn = 'urn:li:company:%s' % self.linkedin_company_public_id

        # published date
        published = False
        dt = post.get('datetime') or ''
        if dt:
            try:
                from datetime import datetime as _dt
                published = _dt.fromisoformat(dt.replace('Z', '+00:00')).replace(tzinfo=None)
            except Exception:
                published = False

        image_vals = []
        for img_url in (post.get('images') or []):
            if img_url:
                image_vals.append((0, 0, {'image_url': img_url}))

        vals = {
            'stream_id': self.id,
            'author_name': post.get('authorName') or self.social_account_id.name,
            'published_date': published or fields.Datetime.now(),
            'linkedin_post_urn': urn,
            'linkedin_author_urn': author_urn or False,
            'message': (post.get('text') or '')[:3000],
        }
        if image_vals:
            vals['stream_post_image_ids'] = [(5, 0)] + image_vals
        if post.get('likes'):
            vals['linkedin_likes_count'] = int(post['likes'])
        if post.get('comments'):
            vals['linkedin_comments_count'] = int(post['comments'])
        if post.get('articleUrl'):
            vals.update({
                'link_url': post['articleUrl'],
                'link_title': post.get('articleTitle') or '',
            })
        return vals

    # Playwright scraping script — runs as a subprocess, HEADED under Xvfb
    # (LinkedIn serves an empty shell to headless Chromium).
    _LINKEDIN_PLAYWRIGHT_SCRIPT = r'''
import json
import random
import sys
import time
from playwright.sync_api import sync_playwright

URL = sys.argv[1]
MAX_SCROLLS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
STATE = sys.argv[3] if len(sys.argv) > 3 else '/tmp/linkedin_pw_state.json'

EXTRACT_JS = """() => {
    const out = [];
    const seen = new Set();
    const cards = document.querySelectorAll('.feed-shared-update-v2, [data-urn]');
    cards.forEach(el => {
        const urn = el.getAttribute && el.getAttribute('data-urn');
        if (!urn || seen.has(urn)) return;
        seen.add(urn);
        const authorEl = el.querySelector('.update-components-actor__name, .feed-shared-actor__name');
        const authorLink = el.querySelector('.update-components-actor__meta-link, .feed-shared-actor__meta-link, a[href*="/company/"], a[href*="/in/"]');
        const textEl = el.querySelector('.feed-shared-inline-show-more-text span, .update-components-text, .feed-shared-text');
        const timeEl = el.querySelector('time');
        const likeEl = el.querySelector('.social-details-social-counts__reactions-count');
        const commentEl = el.querySelector('.social-details-social-counts__comments');
        const imgs = [...el.querySelectorAll('.update-components-image img, .feed-shared-image img, img[src*="media.licdn.com"]')].map(i => i.src);
        const artEl = el.querySelector('.update-components-article__link, .feed-shared-article__link, a[href*="linkedin.com/posts/"]');
        out.push({
            urn: urn,
            authorName: authorEl ? authorEl.innerText.trim() : '',
            authorUrl: authorLink ? authorLink.getAttribute('href') : '',
            text: textEl ? textEl.innerText.trim() : '',
            datetime: timeEl ? (timeEl.getAttribute('datetime') || '') : '',
            likes: likeEl ? (parseInt((likeEl.getAttribute('aria-label') || likeEl.innerText).replace(/[^0-9]/g, '')) || 0) : 0,
            comments: commentEl ? (parseInt(commentEl.innerText.replace(/[^0-9]/g, '')) || 0) : 0,
            images: imgs.slice(0, 4),
            articleUrl: artEl ? artEl.getAttribute('href') : '',
            articleTitle: artEl ? (artEl.innerText.trim() || '') : '',
        });
    });
    return out;
}"""

def main():
    result = {'posts': []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ],
            )
            context = browser.new_context(
                storage_state=STATE,
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
                locale='sv-SE',
            )
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
            page.goto(URL, wait_until='domcontentloaded', timeout=45000)
            time.sleep(random.uniform(8, 14))
            for _ in range(MAX_SCROLLS):
                page.mouse.wheel(0, 1400)
                time.sleep(random.uniform(2.5, 5.5))
            time.sleep(random.uniform(3, 6))
            posts = page.evaluate(EXTRACT_JS)
            result['posts'] = posts
            result['url'] = page.url
            result['title'] = page.title()
            body = page.evaluate('document.body ? document.body.innerText.length : 0')
            if body == 0:
                result['error'] = 'empty_page'
            context.close()
            browser.close()
    except Exception as e:
        result['error'] = '%s: %s' % (type(e).__name__, str(e)[:200])
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
'''
