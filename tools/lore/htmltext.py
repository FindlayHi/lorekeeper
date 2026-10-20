"""A wiki page's rendered HTML -> readable text, headings as '== X ==' so the same sectioning applies as to wikitext.
Wikis that build pages with Lua modules (Dead by Daylight's perks) have almost no wikitext: the rendered page is the content.
A table row stays on one line ('Shotgun | Hellwalker | Cassius | Jakobs Estate'), so a list of drops keeps each item with its
source, and a Fandom infobox becomes 'Label: value' lines between the markers clean.py puts round a wikitext infobox."""
import html.parser, re

SKIP_TAGS = {'script', 'style', 'noscript', 'img', 'svg', 'sup', 'button', 'input', 'form', 'audio', 'video', 'iframe', 'nav'}
SKIP_CLASS = re.compile(r'\b(navbox|toc|mw-editsection|noprint|tooltiptext|printfooter|catlinks|reference|references|gallery|mw-empty-elt|'
                        r'mobileView|metadata|hatnote|mbox|ambox|'
                        r'pi-title|pi-image|pi-image-collection|table-progress-checkbox-cell|header_icon|'   # Fandom: the infobox's picture tabs, tick boxes
                        r'trfc\d+|quick-answers)\b')   # Fandom's "Quick Answers": written by Fandom's AI, not by the wiki's editors
INFOBOX = re.compile(r'\bportable-infobox\b')
BLOCK = {'p', 'div', 'br', 'ul', 'ol', 'table', 'section', 'tr', 'dl', 'dt', 'dd', 'pre', 'blockquote', 'aside', 'figure'}
VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'wbr', 'col'}
HEADS = ('h1', 'h2', 'h3', 'h4')


class Text(html.parser.HTMLParser):
    """Collects the article body (the div.mw-parser-output), skipping what isn't prose: navigation, tooltips, scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.stack, self.in_content, self.depth = [], 0, [], False, 0
        self.box = self.inline = 0   # inside an infobox; inside a table cell or an infobox value (kept to one line)

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get('class', '') or ''
        if not self.in_content:
            if tag == 'div' and 'mw-parser-output' in cls.split():
                self.in_content, self.depth = True, 1
            return
        if tag in VOID:
            if tag == 'br' and not self.skip:
                self.out.append(' ' if self.inline else '\n')
            return
        self.depth += tag == 'div'
        role = ('box' if INFOBOX.search(cls) else 'label' if self.box and 'pi-data-label' in cls else
                'value' if self.box and 'pi-data-value' in cls else 'cell' if tag in ('td', 'th') else '')
        self.stack.append((tag, bool(SKIP_CLASS.search(cls)) or tag in SKIP_TAGS, role))
        self.skip += self.stack[-1][1]
        if self.skip:
            return
        if role == 'box':
            self.box += 1
            self.out.append('\n@@INFOBOX@@\n')
        elif role == 'label':
            self.out.append('\n')
        elif role in ('value', 'cell'):
            self.inline += 1
            self.out.append(' | ' if role == 'cell' else '')
        elif self.inline and (tag in BLOCK or tag == 'li'):
            self.out.append(' ')
        elif tag in HEADS and not self.box:
            self.out.append('\n\n' + '=' * min(4, max(2, int(tag[1]))) + ' ')
        elif tag == 'li':
            self.out.append('\n- ')
        elif tag in BLOCK or tag in HEADS:
            self.out.append('\n')

    def handle_endtag(self, tag):
        if not self.in_content or tag in VOID or not any(t == tag for t, _, _ in self.stack):
            return
        while self.stack[-1][0] != tag:   # tolerate unclosed tags
            self._close(*self.stack.pop())
        self._close(*self.stack.pop())
        if tag == 'div':
            self.depth -= 1
            if self.depth <= 0:
                self.in_content = False

    def _close(self, tag, skipped, role):
        self.skip -= skipped
        if self.skip or skipped:
            return
        if role == 'box':
            self.box -= 1
            self.out.append('\n@@END@@\n')
        elif role == 'label':
            self.out.append(' ' if ''.join(self.out[-2:]).rstrip().endswith(':') else ': ')   # some wikis put the colon in the label
        elif role in ('value', 'cell'):
            self.inline -= 1
            self.out.append('\n' if role == 'value' else '')
        elif self.inline and (tag in BLOCK or tag == 'li'):
            self.out.append(' ')
        elif tag in HEADS and not self.box:
            self.out.append(' ' + '=' * min(4, max(2, int(tag[1]))) + '\n')
        elif tag in BLOCK or tag == 'li' or tag in HEADS:
            self.out.append('\n')

    def handle_data(self, data):
        if self.stack and self.stack[-1][0] in ('table', 'tbody', 'thead', 'tr') and not data.strip():
            return   # the line breaks between a row's cells
        if self.in_content and not self.skip:
            self.out.append(re.sub(r'\s+', ' ', data) if self.inline or self.box else data)


def html_text(page):
    end = re.search(r'printfooter|NewPP limit report|id="catlinks"', page)   # where the article ends and the site's own footer starts
    t = Text()
    t.feed(page[:end.start()] if end else page)
    text = re.sub('[​-‏⁠﻿­]', '', ''.join(t.out))   # zero-width spaces and soft hyphens: wikis are full of them
    text = re.sub(r'[ \t\xa0]+', ' ', text)
    text = re.sub(r'(?m)^[ |]+|[ |]+$', '', text)
    text = re.sub(r'(?m)^(={2,4}) *(.*?) *=+$', lambda m: f'{m[1]} {m[2]} {m[1]}', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()
