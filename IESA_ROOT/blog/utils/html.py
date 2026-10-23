"""Allow rich text without allowing active content or arbitrary HTML attributes."""
import nh3

_CLEANER = nh3.Cleaner(
    tags={'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'blockquote', 'pre', 'code',
          'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'a', 'img', 'figure',
          'figcaption', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'hr', 'span'},
    attributes={'a': {'href', 'title'}, 'img': {'src', 'alt', 'width', 'height'},
                'th': {'colspan', 'rowspan'}, 'td': {'colspan', 'rowspan'}},
    clean_content_tags={'script', 'style', 'iframe', 'object', 'svg', 'math'},
    url_schemes={'https', 'http', 'mailto'},
    link_rel='noopener noreferrer',
)


def sanitize_post_html(value):
    return _CLEANER.clean(value or '')
