# Copyright (C) 2026 Vertel Sverige AB.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Customer portal for social post approval.

The customer of the agency signs in at /my/ and approves or rejects the posts
drafted for their brand. Everything here is reachable from outside the
company, so the rules are strict and stated once:

* Listing is done as the signed-in user. The record rules in security.xml
  restrict a customer to the brands of their own commercial partner, and the
  domain repeats that restriction so a mistake in one of the two cannot widen
  the list on its own.
* A single post is fetched through ``_document_check_access``, which lets the
  record through only when the signed-in user may read it, or when a correct
  access token is presented (compared in constant time).
* Approving and rejecting are POST only and go through the model as the
  signed-in user, never elevated. The model checks the caller's group and
  brand, and the record rules limit the write to posts of the customer's own
  brands that are awaiting customer approval. A token that is good enough to
  read a page is deliberately not good enough to change its state.
"""

from odoo import _, http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request

from odoo.addons.portal.controllers import portal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class SocialCustomerPortal(portal.CustomerPortal):
    """Portal pages for the customer approval step on social posts."""

    # ------------------------------------------------------------------
    # Home counter
    # ------------------------------------------------------------------

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'social_post_count' in counters:
            Post = request.env['social_marketing.post']
            values['social_post_count'] = Post.search_count(
                self._prepare_social_posts_domain(filterby='awaiting')
            ) if Post.has_access('read') else 0
        return values

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prepare_social_posts_domain(self, filterby='awaiting'):
        """Domain of the posts the signed-in customer may act on.

        The brand clause duplicates the record rule on purpose: the list must
        stay correct even if the rule is later loosened by mistake.
        """
        partner = request.env.user.partner_id.commercial_partner_id
        domain = [('brand_id.partner_id', '=', partner.id)]
        state = self._get_social_searchbar_filters().get(
            filterby, {}).get('approval_state')
        if state:
            domain.append(('approval_state', '=', state))
        return domain

    def _get_social_searchbar_sortings(self):
        return {
            'date': {'label': _('Newest'), 'order': 'create_date desc'},
            'scheduled': {
                'label': _('Planned date'), 'order': 'scheduled_date desc'},
        }

    def _get_social_searchbar_filters(self):
        return {
            'awaiting': {
                'label': _('Waiting for you'),
                'approval_state': 'awaiting_customer',
                'sequence': 10,
            },
            'approved': {
                'label': _('Approved'),
                'approval_state': 'approved',
                'sequence': 20,
            },
            'rejected': {
                'label': _('Rejected'),
                'approval_state': 'rejected',
                'sequence': 30,
            },
            'all': {
                'label': _('All'),
                'approval_state': None,
                'sequence': 40,
            },
        }

    def _social_post_get_page_view_values(self, post_sudo, access_token,
                                          **kwargs):
        values = {
            'page_name': 'social_post',
            'post': post_sudo,
            'message': kwargs.get('message'),
        }
        return self._get_page_view_values(
            post_sudo, access_token, values, 'my_social_posts_history', False,
            **kwargs)

    def _social_post_act(self, post_id, access_token):
        """Return the post to act on, as the signed-in user.

        Raises AccessError or MissingError when the caller has no business
        being here.
        """
        post_sudo = self._document_check_access(
            'social_marketing.post', post_id, access_token=access_token)
        # Deliberately not the sudo record: the write goes through the
        # customer's own rights so the record rules and the model's
        # _check_customer_rights both apply.
        return request.env['social_marketing.post'].browse(post_sudo.id)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    @http.route(['/my/social-posts', '/my/social-posts/page/<int:page>'],
                type='http', auth='user', website=True)
    def portal_my_social_posts(self, page=1, sortby=None, filterby=None,
                               **kwargs):
        Post = request.env['social_marketing.post']
        values = self._prepare_portal_layout_values()

        searchbar_sortings = self._get_social_searchbar_sortings()
        searchbar_filters = self._get_social_searchbar_filters()
        if sortby not in searchbar_sortings:
            sortby = 'date'
        if filterby not in searchbar_filters:
            filterby = 'awaiting'

        domain = self._prepare_social_posts_domain(filterby=filterby)
        url = '/my/social-posts'
        url_args = {'sortby': sortby, 'filterby': filterby}

        readable = Post.has_access('read')
        pager_values = portal_pager(
            url=url,
            total=Post.search_count(domain) if readable else 0,
            page=page,
            step=self._items_per_page,
            url_args=url_args,
        )
        posts = Post.search(
            domain,
            order=searchbar_sortings[sortby]['order'],
            limit=self._items_per_page,
            offset=pager_values['offset'],
        ) if readable else Post

        request.session['my_social_posts_history'] = posts.ids[:100]

        values.update({
            'posts': posts,
            'page_name': 'social_post',
            'default_url': url,
            'pager': pager_values,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': dict(sorted(
                searchbar_filters.items(),
                key=lambda item: item[1]['sequence'])),
            'filterby': filterby,
        })
        return request.render(
            'social_marketing_agency.portal_my_social_posts', values)

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------

    @http.route(['/my/social-posts/<int:post_id>'], type='http',
                auth='public', website=True)
    def portal_social_post_page(self, post_id, access_token=None, **kwargs):
        try:
            post_sudo = self._document_check_access(
                'social_marketing.post', post_id, access_token=access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        values = self._social_post_get_page_view_values(
            post_sudo, access_token, **kwargs)
        return request.render(
            'social_marketing_agency.portal_social_post_page', values)

    # ------------------------------------------------------------------
    # Approve and reject
    # ------------------------------------------------------------------

    def _social_post_redirect(self, post_id, message=None):
        url = '/my/social-posts/%s' % (post_id,)
        if message:
            url = '%s?message=%s' % (url, message)
        return request.redirect(url)

    @http.route(['/my/social-posts/<int:post_id>/approve'], type='http',
                auth='user', methods=['POST'], website=True)
    def portal_social_post_approve(self, post_id, access_token=None, **kwargs):
        try:
            post = self._social_post_act(post_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        try:
            post.action_customer_approve()
        except (AccessError, UserError):
            return self._social_post_redirect(post_id, 'action_refused')
        return self._social_post_redirect(post_id, 'approved')

    @http.route(['/my/social-posts/<int:post_id>/reject'], type='http',
                auth='user', methods=['POST'], website=True)
    def portal_social_post_reject(self, post_id, access_token=None,
                                  reason=None, **kwargs):
        try:
            post = self._social_post_act(post_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        reason = (reason or '').strip()
        if not reason:
            return self._social_post_redirect(post_id, 'reason_required')
        try:
            post.action_customer_reject(reason=reason)
        except (AccessError, UserError):
            return self._social_post_redirect(post_id, 'action_refused')
        return self._social_post_redirect(post_id, 'rejected')
