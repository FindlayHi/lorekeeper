"""Things said to Lorekeeper itself, handled at once with no AI. parse(text) -> (action, arg) or None."""
import re

RULES = [
    ('stop', r'(?:stop|shush|quiet|be quiet|shut up|never ?mind|cancel)'),
    ('repeat', r'(?:repeat(?: that)?|say (?:that|it) again|what did you say|come again)'),
    ('clip', r'(?:clip (?:it|that|this)|save (?:a |that |the )?clip|(?:make|take) a clip|clip the last .+)'),
    ('listen_on', r'(?:listen mode on|(?:start|keep) listening|listen to me|turn on listen(?:ing| mode))'),
    ('listen_off', r'(?:listen mode off|stop listening|turn off listen(?:ing| mode)|go to sleep)'),
    ('spoil', r'(?:(?:ok(?:ay)?,? )?spoil (?:it|that|away)(?: for me)?|spoilers? on|go ahead and spoil(?: it)?)'),
    ('playing', r"(?:i'?m|i am|we'?re) (?:now )?playing (.+)"),
    ('auto', r'(?:detect (?:the )?game|auto(?:matic)?(?: detect)?|forget (?:the|which) game)'),
    ('unnote', r"(?:forget|delete|remove|scratch|undo|drop) (?:that|the|this|the last|your last|my last) note|that note'?s wrong|don'?t note that"),
    ('gear_save', r'(?:save|remember|store|log|record|track) (?:this|that|it)(?: item| one)? (?:as|for) (my .+)'),
    ('gear_save', r'(?:this|that) is my (?:new )?(.+)'),
    ('gear_save', r"(?:i )?(?:just )?equipped (?:this|that|it) (?:as|for|in) (my .+)"),
    ('gear_forget', r'(?:forget|clear|delete|remove) my (?!notes)(.+)'),
    ('gear_list', r"(?:what(?:'s| is) my gear|what gear (?:do i have|have i saved)|list my gear|what (?:have i|did i) (?:saved|save))"),
    ('snap', r'(?:remember|save|keep|screenshot|snap) (?:this|that)(?: screen| spot| place| map| clue| puzzle| code| sign| page)?(?: (?:as|for|called) (.+))?'),
    ('snap', r'take a (?:screenshot|picture|snap)(?: (?:of this|as|for|called) ?(.*))?'),
    ('note', r'(?:note|remember|note that|make a note|take a note)[:,]? (.+)'),
    ('note', r"((?:i'?m|i am) (?:at|in|on|up to|past) .+|i (?:just )?(?:beat|killed|finished|defeated|reached|unlocked|chose|picked|sided with|got to) .+)"),
]
NOT_PROGRESS = re.compile(r'\b(what|where|how|who|why|which|should|does|is it|can i)\b', re.I)


LEAD = re.compile(r"^(?:(?:hey|hi|ok(?:ay)?|yo|um+|uh+|so|and|lorekeeper|keeper|please|"
                  r"(?:can|could|would|will) you(?: please)?|i want you to|go ahead and)[,:]?\s+)+", re.I)
TAIL = re.compile(r'(?:[,\s]+(?:please|for me|now|real quick|thanks|thank you|lorekeeper))+$', re.I)


def clean(text):
    """What's said, without the asking around it: "Hey, can you clip it please?" -> "clip it"."""
    t = re.sub(r'\s+', ' ', text.strip()).strip(' .!?')
    return TAIL.sub('', LEAD.sub('', t)).strip(' ,.!?')


def parse(text):
    t = clean(text)
    for action, rx in RULES:
        m = re.fullmatch(rx, t, re.I)
        if m:
            arg = (m.group(1) or '').strip(' .') if m.groups() else ''
            if action == 'note' and NOT_PROGRESS.search(arg) and not t.lower().startswith(('note', 'remember', 'make a note', 'take a note')):
                return None   # "I'm at Stormveil, where do I go?" is a question
            if action == 'playing' and NOT_PROGRESS.search(arg):
                return None
            return action, arg
    return None
