/** @odoo-module **/

import { formatText } from '@mail/js/emojis_mixin';

export const SocialPostFormatterRegex = {
    REGEX_AT: /\B@([\w\dÀ-ÿ-.]+)/g,
    REGEX_HASHTAG: /(^|\s|<br>)#([a-zA-Z\d\-_]+)/g,
    REGEX_URL: /http(s)?:\/\/(www\.)?[a-zA-Z0-9@:%_+~#=~#?&/=\-;!.]{3,2000}/g,
};

export const SocialPostFormatterMixinBase = {

    /**
     * Add emojis support
     * Wraps links, #hashtag and @tag around anchors
     * Regex from: https://stackoverflow.com/questions/19484370/how-do-i-automatically-wrap-text-urls-in-anchor-tags
     *
     * @param {String} value
     * @private
     */
    _formatPost(value) {
        // add emojis support and escape HTML
        value = formatText(value);

        // highlight URLs
        value = value.replace(
            SocialPostFormatterRegex.REGEX_URL,
            "<a href='$&' class='text-truncate' target='_blank' rel='noreferrer noopener'>$&</a>");

        // Protect existing tags (emoji <img>, URL anchors) so hashtag/mention
        // highlighting never touches attributes or markup. <br> is kept literal
        // so the hashtag boundary regex still matches after line breaks.
        const placeholders = {};
        let counter = 0;
        value = value.replace(/<[^>]+>/g, (tag) => {
            if (/^<br\s*\/?>$/i.test(tag)) {
                return tag;
            }
            const ph = `\u0000${counter++}\u0000`;
            placeholders[ph] = tag;
            return ph;
        });

        // highlight hashtags
        value = value.replace(
            SocialPostFormatterRegex.REGEX_HASHTAG,
            "$1<a href='#' class='o_social_hashtag' tabindex='-1'>#$2</a>");

        // highlight @mentions
        value = value.replace(
            SocialPostFormatterRegex.REGEX_AT,
            "<a href='#' class='o_social_mention' tabindex='-1'>@$1</a>");

        // restore protected tags
        value = value.replace(/\u0000\d+\u0000/g, (ph) => placeholders[ph]);

        return value;
    },

    _getMediaType() {
        return this.props && this.props.mediaType ||
            this.props.record && this.props.record.data.media_type ||
            this.originalPost && this.originalPost.media_type.raw_value || '';
    }

};

export const SocialPostFormatterMixin = (T) => class extends T {
    _formatPost() {
        return SocialPostFormatterMixinBase._formatPost.call(this, ...arguments);
    }
    _getMediaType() {
        return SocialPostFormatterMixinBase._getMediaType.call(this, ...arguments);
    }
};
