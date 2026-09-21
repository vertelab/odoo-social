# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

import json
import logging
import os
import shutil
import subprocess
import tempfile

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SocialMarketingAccountLinkedIn(models.Model):
    """ LinkedIn inbox integration — fetch and reply to DMs.

    The official LinkedIn DM API requires special partner approval, so we
    scrape the messaging UI with a real Chromium browser (Playwright) using
    the persistent session saved on the account (`linkedin_playwright_session`).
    """

    _inherit = 'social_marketing.account'

    def _fetch_inbox_messages(self):
        """Hämta LinkedIn-meddelanden via Playwright-skrapning av /messaging/.

        Uses the account's Playwright session (storage_state). Creates/updates
        `social_marketing.message` records (Unified Inbox), deduped on the
        message URN. Returns the number of NEW incoming messages.
        """
        self.ensure_one()
        if self.media_type != 'linkedin':
            return super()._fetch_inbox_messages()

        session = self._load_playwright_session()
        if not session:
            _logger.warning(
                'LinkedIn inbox %s: no Playwright session. Run '
                '"Browser Login — Playwright" on the account first.',
                self.display_name,
            )
            return 0

        tmpdir = tempfile.mkdtemp(prefix='linkedin_inbox_')
        session_file = os.path.join(tmpdir, 'storage_state.json')
        script_file = os.path.join(tmpdir, 'inbox.py')
        try:
            with open(session_file, 'w') as f:
                json.dump(session, f)
            with open(script_file, 'w') as f:
                f.write(self._LINKEDIN_INBOX_SCRIPT)

            proc = subprocess.run(
                ['bash', '-c', 'ulimit -v unlimited && exec xvfb-run -a python3 "$@"',
                 'pw-inbox', script_file, session_file],
                capture_output=True, text=True, timeout=240,
            )
        except subprocess.TimeoutExpired:
            _logger.error('LinkedIn inbox %s: Playwright scraping timed out.', self.display_name)
            return 0
        except Exception as e:
            _logger.error('LinkedIn inbox %s: subprocess error: %s', self.display_name, e)
            return 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        if proc.returncode != 0:
            _logger.error(
                'LinkedIn inbox %s: Playwright failed (%s): %s',
                self.display_name, proc.returncode, (proc.stderr or '')[-500:],
            )
            return 0

        try:
            result = json.loads(proc.stdout.strip().split('\n')[-1])
        except (ValueError, IndexError):
            _logger.error('LinkedIn inbox %s: bad output: %s',
                          self.display_name, proc.stdout[-300:])
            return 0

        if result.get('error'):
            _logger.warning('LinkedIn inbox %s: %s', self.display_name, result['error'])
            return 0

        conversations = result.get('conversations') or []
        if not conversations:
            _logger.info('LinkedIn inbox %s: no conversations found.', self.display_name)
            return 0

        return self._process_linkedin_inbox_conversations(conversations)

    def _process_linkedin_inbox_conversations(self, conversations):
        """Create/update social_marketing.message records from scraped data."""
        Message = self.env['social_marketing.message'].sudo()
        new_count = 0

        for conv in conversations:
            peer_name = (conv.get('name') or '').strip()
            thread_url = conv.get('threadUrl') or 'https://www.linkedin.com/messaging/'
            parent = False
            for msg in conv.get('messages') or []:
                urn = msg.get('urn') or ''
                if not urn:
                    continue
                text = (msg.get('text') or '').strip()
                is_incoming = msg.get('direction') == 'incoming'

                existing = Message.search([('external_id', '=', urn)], limit=1)
                if existing:
                    # refresh body/state only if still unread and body changed
                    if text and text != existing.body:
                        existing.write({'body': text[:10000]})
                    continue

                vals = {
                    'from_name': peer_name or self.name,
                    'body': text[:10000],
                    'external_id': urn,
                    'external_url': thread_url,
                    'media_type': 'linkedin',
                    'message_type': 'dm',
                    'social_account_id': self.id,
                    'is_incoming': is_incoming,
                    'state': 'unread' if is_incoming else 'read',
                }
                if parent:
                    vals['parent_id'] = parent.id
                message = Message.create(vals)
                if not parent:
                    parent = message
                if is_incoming:
                    new_count += 1

        _logger.info(
            'LinkedIn inbox %s: processed %d conversations, %d new incoming',
            self.display_name, len(conversations), new_count,
        )
        return new_count

    @api.model
    def refresh_linkedin_inbox(self):
        """Refresh the inbox for all LinkedIn accounts (cron entry point).

        Keeps browser launches limited to LinkedIn accounts only.
        """
        accounts = self.search([
            ('media_type', '=', 'linkedin'),
            ('active', '=', True),
            ('is_media_disconnected', '=', False),
        ])
        new_total = 0
        for account in accounts:
            try:
                new_total += account._fetch_inbox_messages()
            except Exception as e:
                _logger.error('LinkedIn inbox refresh failed for %s: %s',
                              account.display_name, e)
        _logger.info('LinkedIn inbox refresh: %d accounts, %d new messages',
                     len(accounts), new_total)
        return {'accounts': len(accounts), 'new': new_total}

    def _send_inbox_reply(self, message, body):
        """Skicka svar via LinkedIn (Playwright).

        NOTE: not implemented yet — LinkedIn DM send requires composing in
        the messaging UI. Future enhancement.
        """
        self.ensure_one()
        if self.media_type != 'linkedin':
            return super()._send_inbox_reply(message, body)
        _logger.info('LinkedIn reply for %s: send via Playwright not implemented yet.',
                     message.id)
        return False

    # ────────────────────────────────────────────────────────────
    # Playwright script — scrapes /messaging/ (headed under Xvfb)
    # ────────────────────────────────────────────────────────────
    _LINKEDIN_INBOX_SCRIPT = r'''
import json
import random
import sys
import time
from playwright.sync_api import sync_playwright

STATE = sys.argv[1] if len(sys.argv) > 1 else '/tmp/linkedin_inbox_state.json'
MAX_CONVOS = 10

CONVO_JS = """() => {
    const out = [];
    document.querySelectorAll('.msg-conversation-listitem').forEach(li => {
        const nameEl = li.querySelector('[data-anonymize="participant-name"], .msg-conversation-listitem__participant-names, .msg-conversation-listitem__name');
        const previewEl = li.querySelector('.msg-conversation-listitem__message-preview, .msg-conversation-listitem__message');
        out.push({
            name: nameEl ? nameEl.innerText.trim() : '',
            preview: previewEl ? previewEl.innerText.trim() : '',
        });
    });
    return out;
}"""

MSG_JS = """() => {
    const out = [];
    document.querySelectorAll('.msg-s-event-listitem').forEach(el => {
        const urn = el.getAttribute('data-event-urn') || '';
        const textEl = el.querySelector('.msg-s-event-listitem__body, .msg-event-card__message');
        const timeEl = el.querySelector('time');
        const cls = el.className || '';
        out.push({
            urn: urn,
            direction: cls.includes('--other') ? 'incoming' : 'outgoing',
            text: textEl ? textEl.innerText.trim() : '',
            datetime: timeEl ? (timeEl.getAttribute('datetime') || '') : '',
        });
    });
    return out;
}"""

def safe_evaluate(page, js, retries=4):
    for i in range(retries):
        try:
            return page.evaluate(js)
        except Exception:
            time.sleep(2)
    return []

def main():
    result = {'conversations': []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                executable_path='/var/lib/odoo/browsers/ab-chrome-152/chrome',
                args=['--disable-blink-features=AutomationControlled',
                      '--disable-dev-shm-usage', '--no-sandbox'],
            )
            context = browser.new_context(
                storage_state=STATE,
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
                locale='sv-SE',
            )
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
            page.goto('https://www.linkedin.com/messaging/', wait_until='domcontentloaded',
                      timeout=45000)
            try:
                page.wait_for_load_state('networkidle', timeout=20000)
            except Exception:
                pass
            time.sleep(random.uniform(3, 6))
            # wait for conversation list (SPA render + possible redirect to active thread)
            convos = []
            try:
                page.wait_for_selector('.msg-conversation-listitem', timeout=30000)
            except Exception:
                pass
            for _ in range(15):
                time.sleep(2)
                convos = safe_evaluate(page, CONVO_JS)
                if convos:
                    break
            if not convos:
                # maybe we landed straight on the thread URL — wait a bit more
                time.sleep(5)
                convos = safe_evaluate(page, CONVO_JS)
            if not convos:
                result['error'] = 'no_conversations'
                print(json.dumps(result, ensure_ascii=False))
                return
            result['conversations'] = []
            for idx, convo in enumerate(convos[:MAX_CONVOS]):
                # re-query list items fresh each iteration (SPA re-renders)
                items = page.query_selector_all('.msg-conversation-listitem')
                if idx >= len(items):
                    break
                try:
                    items[idx].click()
                except Exception:
                    continue
                time.sleep(random.uniform(3, 6))
                msgs = safe_evaluate(page, MSG_JS)
                result['conversations'].append({
                    'name': convo.get('name', ''),
                    'threadUrl': page.url,
                    'messages': msgs,
                })
            context.close()
            browser.close()
    except Exception as e:
        result['error'] = '%s: %s' % (type(e).__name__, str(e)[:200])
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
'''
