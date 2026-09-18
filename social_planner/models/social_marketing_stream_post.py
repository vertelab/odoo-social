# -*- coding: utf-8 -*-
# Vertel Sverige AB AGPL-3

from odoo import _, api, fields, models


class SocialMarketingStreamPost(models.Model):
    """ Extend social_marketing.stream.post for AI sentiment analysis
    and auto-moderation linked to policy. """

    _inherit = 'social_marketing.stream.post'

    sentiment = fields.Selection([
        ('positive', 'Positive'),
        ('neutral', 'Neutral'),
        ('negative', 'Negative'),
    ], string='Sentiment', default='neutral')
    sentiment_score = fields.Float('Sentiment Score', digits=(3, 2))
    needs_review = fields.Boolean('Needs Review')
    policy_flag = fields.Boolean('Policy Flag')

    def action_analyze_sentiment(self):
        ai_helper = self.env['social.planner.ai']
        for post in self:
            message = post.message or ''
            if not message:
                continue
            result = ai_helper.analyze_sentiment(message)
            post.write({
                'sentiment': result.get('sentiment', 'neutral'),
                'sentiment_score': result.get('score', 0.0),
                'needs_review': result.get('sentiment') == 'negative',
            })

    def action_check_policy(self):
        policies = self.env['communication.policy'].search([
            ('state', '=', 'active'),
            ('prohibited_content', '!=', False),
        ])
        for post in self:
            message = (post.message or '').lower()
            flagged = False
            for policy in policies:
                if not policy.prohibited_content:
                    continue
                prohibited = [
                    w.strip().lower()
                    for w in policy.prohibited_content.split('\n')
                    if w.strip()
                ]
                if any(w in message for w in prohibited):
                    flagged = True
                    break
            post.policy_flag = flagged
            if flagged:
                post.needs_review = True
