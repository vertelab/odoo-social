# -*- coding: utf-8 -*-
# Vertel AB AGPL-3

import json
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SocialPlannerAI(models.AbstractModel):
    """ AI-helper för social_planner — integration med ai_agent för
    innehållsgenerering, sentimentanalys och optimering. """

    _name = 'social.planner.ai'
    _description = 'Social Planner AI Helper'

    @api.model
    def generate_post_content(self, post_id):
        """ Generera innehåll för en social_marketing.post med AI.
        Använder ai_agent för att skapa innehåll baserat på planens
        målgrupp, policyns tonalitet, och radens tema. """
        post = self.env['social_marketing.post'].browse(post_id)
        if not post.exists():
            return False

        # Bygg prompt från kontext
        system_prompt = self._build_system_prompt(post)
        user_prompt = self._build_user_prompt(post)

        # Försök anropa ai_agent om tillgängligt
        try:
            generated = self._call_ai_agent(system_prompt, user_prompt)
            if generated:
                post.write({
                    'message': generated,
                    'ai_generated': True,
                    'ai_prompt': f"System: {system_prompt}\n\nUser: {user_prompt}",
                })
                return True
        except Exception as e:
            _logger.warning("AI generation failed for post %s: %s", post.id, str(e))
            # Fallback: markera att AI försöktes men misslyckades
            post.write({
                'ai_generated': False,
                'ai_prompt': f"System: {system_prompt}\n\nUser: {user_prompt}",
            })
        return False

    @api.model
    def _build_system_prompt(self, post):
        """ Bygg systemprompt från policy-kontext. """
        policy = post.policy_id
        plan = post.plan_id
        line = post.plan_line_id

        parts = []
        parts.append("You are a professional social media content creator.")

        if policy:
            parts.append(f"Tone of voice: {policy.tone_of_voice or 'Professional and engaging'}")
            parts.append(f"Brand voice: {policy.brand_voice_guidelines or 'Clear and concise'}")
            if policy.hashtag_policy:
                parts.append(f"Hashtag rules: {policy.hashtag_policy}")
            if policy.prohibited_content:
                parts.append(f"Avoid these words/topics: {policy.prohibited_content}")

        if plan:
            parts.append(f"Target audience: {plan.target_audience or 'General audience'}")

        if line:
            channel = dict(line._fields['channel']._description_selection(self.env)).get(line.channel, line.channel)
            content_type = dict(line._fields['content_type']._description_selection(self.env)).get(line.content_type, line.content_type)
            parts.append(f"Channel: {channel}")
            parts.append(f"Content type: {content_type}")

        return '\n'.join(parts)

    @api.model
    def _build_user_prompt(self, post):
        """ Bygg användarprompt från plan/rad-kontext. """
        plan = post.plan_id
        line = post.plan_line_id

        parts = []

        if plan:
            parts.append(f"Create a social media post for the campaign: '{plan.name}'")
            if plan.goal:
                parts.append(f"Campaign goals: {plan.goal}")

        if line:
            parts.append(f"Theme: {line.theme or 'General update'}")
            if line.notes:
                parts.append(f"Additional notes: {line.notes}")

        if post and post.message:
            parts.append(f"Draft content to refine: {post.message}")

        parts.append("Write engaging, platform-appropriate content ready to post.")
        parts.append("Include relevant emojis if the brand voice allows it.")

        return '\n'.join(parts)

    @api.model
    def _call_ai_agent(self, system_prompt, user_prompt):
        """ Anropa ai_agent för att generera innehåll.
        Detta är en enkel implementation — kan ersättas med full ai.coworker-integration. """
        # Försök hitta en AI-agent att använda
        agent = self.env['ai.agent'].search([
            ('generic_agent', '=', True),
        ], limit=1)

        if not agent:
            agent = self.env['ai.agent'].search([], limit=1)

        if not agent:
            _logger.warning("No AI agent found for content generation")
            return False

        try:
            # Skapa en enkel session för engångsgenerering
            # Detta är en förenklad approach — full integration kräver
            # en dedicated ai.coworker med rätt config
            result = agent.trigger_prompt(
                message=f"{system_prompt}\n\n---\n\n{user_prompt}",
            )
            if result:
                return result.strip()
        except Exception as e:
            _logger.warning("AI agent call failed: %s", str(e))
            return False

        return False

    @api.model
    def analyze_sentiment(self, text):
        """ Analysera sentiment för en text (kommentar/post).
        Returnerar: {'sentiment': 'positive'|'neutral'|'negative', 'score': float} """
        if not text:
            return {'sentiment': 'neutral', 'score': 0.0}

        system_prompt = (
            "You are a sentiment analysis tool. "
            "Classify the sentiment of the following text as 'positive', 'neutral', or 'negative'. "
            "Respond with ONLY a JSON object: {\"sentiment\": \"positive|neutral|negative\", \"score\": 0.0-1.0}"
        )

        try:
            agent = self.env['ai.agent'].search([
                ('generic_agent', '=', True),
            ], limit=1) or self.env['ai.agent'].search([], limit=1)

            if agent:
                result = agent.trigger_prompt(message=f"{system_prompt}\n\nText: {text}")
                if result:
                    try:
                        return json.loads(result)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        return {'sentiment': 'neutral', 'score': 0.0}

    @api.model
    def suggest_best_time(self, plan_id):
        """ Föreslå bästa tid att posta baserat på historisk engagement-data.
        Returnerar dict med kanal → tid. """
        plan = self.env['communication.plan'].browse(plan_id)
        if not plan.exists():
            return {}

        # Analysera historisk engagement per kanal (senaste 90 dagar)
        suggestions = {}
        channels = ['linkedin', 'facebook', 'instagram', 'twitter', 'youtube']

        for channel in channels:
            posts = self.env['social_marketing.post'].search([
                ('plan_line_id.plan_id.policy_id', '=', plan.policy_id.id),
                ('state', '=', 'posted'),
                ('create_date', '>=', fields.Datetime.now() - fields.Datetime.timedelta(days=90)),
            ])

            if not posts:
                suggestions[channel] = 10.0  # Default 10:00
                continue

            # Enkel heuristik — hitta timmen med högst average engagement
            # (I verklig produktion skulle detta vara mer sofistikerat)
            engagement_by_hour = {}
            for post in posts:
                hour = post.scheduled_date.hour if post.scheduled_date else 10
                engagement_by_hour[hour] = engagement_by_hour.get(hour, 0) + post.engagement

            if engagement_by_hour:
                best_hour = max(engagement_by_hour, key=engagement_by_hour.get)
                suggestions[channel] = float(best_hour)
            else:
                suggestions[channel] = 10.0

        return suggestions

    @api.model
    def suggest_hashtags(self, post_id):
        """ Föreslå hashtags baserat på innehåll och policy. """
        post = self.env['social_marketing.post'].browse(post_id)
        if not post.exists() or not post.message:
            return []

        system_prompt = (
            "You are a social media hashtag expert. "
            "Based on the post content and brand guidelines, suggest 3-5 relevant hashtags. "
            "Respond with ONLY a JSON array: [\"#tag1\", \"#tag2\", ...]"
        )

        user_prompt = f"Content: {post.message}\n"
        if post.policy_id and post.policy_id.hashtag_policy:
            user_prompt += f"Hashtag rules: {post.policy_id.hashtag_policy}"

        try:
            agent = self.env['ai.agent'].search([
                ('generic_agent', '=', True),
            ], limit=1) or self.env['ai.agent'].search([], limit=1)

            if agent:
                result = agent.trigger_prompt(message=f"{system_prompt}\n\n{user_prompt}")
                if result:
                    try:
                        hashtags = json.loads(result)
                        if isinstance(hashtags, list):
                            return hashtags
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

        return []
