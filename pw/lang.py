"""Languages: ENGLISH or ESPAÑOL (OPTIONS > LANGUAGE).

The game is written in English. Every piece of text the game draws goes through tr() (gfx.text, text_width and wrap
call it), which looks the English up in data/lang/es.json:
  words     exact text -> its translation. '#' stands for any number: "PLACE # SOLDIERS" covers PLACE 3 SOLDIERS
            (put #1, #2... in the translation to change the order).
  patterns  [regular expression, translation]: for text with other changing parts (a map name, a player's code).
            {1}, {2}... in the translation are the captured parts, themselves translated if they can be.
            Text made of pieces joined with ' · ' is translated piece by piece.
Longer texts (MANUAL pages, the tutorial, the editor guide, ONLINE HELP) have their own copies in data/lang/es/.
Text that isn't in the table stays in English, so a missing translation never breaks anything.
"""
import os
import re

from .data import ROOT, load_json
from .settings import S

LANGUAGES = {'en': 'ENGLISH', 'es': 'ESPAÑOL'}
_tables, _cache = {}, {}


def language():
    return S.get('language', 'en') if S.get('language') in LANGUAGES else 'en'


def table(code):
    if code not in _tables:
        try:
            t = load_json('data', 'lang', f'{code}.json')
        except (OSError, ValueError):
            t = {}
        words = {k.upper(): v for k, v in t.get('words', {}).items()}
        patterns = [(re.compile(rx), out) for rx, out in t.get('patterns', [])]
        _tables[code] = (words, patterns)
    return _tables[code]


def tr(s):
    """The text in the chosen language (s is upper case, as the game draws it)."""
    code = language()
    if code == 'en' or not s:
        return s
    cache = _cache.setdefault(code, {})
    if s not in cache:
        cache[s] = translate(s, *table(code)).upper()       # (the font only has capitals)
    return cache[s]


def translate(s, words, patterns):
    if s in words:
        return words[s]
    nums = re.findall(r'\d+', s)
    if nums:
        key = re.sub(r'\d+', '#', s)
        if key in words:
            out = words[key]
            if re.search(r'#\d', out):                       # numbered: #1, #2... in any order
                return re.sub(r'#(\d)', lambda m: nums[int(m.group(1)) - 1], out)
            parts = out.split('#')
            return ''.join(p + (nums[k] if k < len(nums) else '') for k, p in enumerate(parts[:-1])) + parts[-1]
    for rx, out in patterns:
        m = rx.fullmatch(s)
        if m:
            return re.sub(r'\{(\d)\}', lambda g: tr(m.group(int(g.group(1))) or ''), out)
    if ' · ' in s:                                           # pieces joined with dots: each on its own
        return ' · '.join(tr(part) for part in s.split(' · '))
    return s


def load_text(name):
    """One of the long texts in data/ (howto.json...), in the chosen language when it has its own copy."""
    code = language()
    if code != 'en' and os.path.exists(os.path.join(ROOT, 'data', 'lang', code, name)):
        return load_json('data', 'lang', code, name)
    return load_json('data', name)

