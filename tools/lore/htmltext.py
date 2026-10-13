"""A wiki page's rendered HTML -> readable text, headings as '== X ==' so the same sectioning applies as to wikitext.
Wikis that build pages with Lua modules (Dead by Daylight's perks) have almost no wikitext: the rendered page is the content."""
import html.parser, re

SKIP_TAGS = {'script', 'style', 'noscript', 'img', 'svg', 'sup', 'button', 'input', 'form', 'audio', 'video', 'iframe', 'nav'}
SKIP_CLASS = re.compile(r'\b(navbox|toc|mw-editsection|noprint|tooltiptext|printfooter|catlinks|reference|references|gallery|mw-empty-elt|'
                        r'mobileView|metadata|hatnote|mbox|ambox)\b')
BLOCK = {'p', 'div', 'br', 'ul', 'ol', 'table', 'section', 'tr', 'dl', 'dt', 'dd', 'pre', 'blockquote', 'aside', 'figure'}
VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'wbr', 'col'}
HEADS = ('h1', 'h2', 'h3', 'h4')


class Text(html.parser.HTMLParser):
    """Collects the article body (the div.mw-parser-output), skipping what isn't prose: navigation, tooltips, scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.stack, self.in_content, self.depth = [], 0, [], False, 0

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get('class', '') or ''
        if not self.in_content:
            if tag == 'div' and 'mw-parser-output' in cls.split():
                self.in_content, self.depth = True, 1
            return
        if tag in VOID:
            if tag == 'br' and not self.skip:
                self.out.append('\n')
            return
        self.depth += tag == 'div'
        self.stack.append((tag, bool(SKIP_CLASS.search(cls)) or tag in SKIP_TAGS))
        self.skip += self.stack[-1][1]
        if self.skip:
            return
        if tag in HEADS:
            self.out.append('\n\n' + '=' * min(4, max(2, int(tag[1]))) + ' ')
        elif tag == 'li':
            self.out.append('\n- ')
        elif tag in ('td', 'th'):
            self.out.append(' | ')
        elif tag in BLOCK:
            self.out.append('\n')

    def handle_endtag(self, tag):
        if not self.in_content or tag in VOID or not any(t == tag for t, _ in self.stack):
            return
        while self.stack[-1][0] != tag:   # tolerate unclosed tags
            self.skip -= self.stack.pop()[1]
        self.skip -= self.stack.pop()[1]
        if tag == 'div':
            self.depth -= 1
            if self.depth <= 0:
                self.in_content = False
        if self.skip:
            return
        if tag in HEADS:
            self.out.append(' ' + '=' * min(4, max(2, int(tag[1]))) + '\n')
        elif tag in BLOCK or tag == 'li':
            self.out.append('\n')

    def handle_data(self, data):
        if self.in_content and not self.skip:
            self.out.append(data)


def html_text(page):
    end = re.search(r'printfooter|NewPP limit report|id="catlinks"', page)   # where the article ends and the site's own footer starts
    t = Text()
    t.feed(page[:end.start()] if end else page)
    text = re.sub('[\u200b-\u200f\u2060\ufeff\u00ad]', '', ''.join(t.out))   # zero-width spaces and soft hyphens: wikis are full of them
    text = re.sub(r'[ \t\xa0]+', ' ', text)
    text = re.sub(r'(?m)^[ |]+|[ |]+$', '', text)
    text = re.sub(r'(?m)^(={2,4}) *(.*?) *=+$', lambda m: f'{m[1]} {m[2]} {m[1]}', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()
