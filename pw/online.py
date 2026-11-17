"""The screens around online play (the connection itself is in net.py, the battle in play.py):
PLAYER VS PLAYER (HOTSEAT or ONLINE), ONLINE (host, join, help), the host's lobby with the invite code and what the
router said, the join screen where you type or paste a code, and ONLINE HELP (pages from data/online_help.json)."""
import pygame

from . import sound, net
from .data import load_json, parse_map
from .gfx import C, SW, SH, rect, box, text, wrap
from .menu import Pages
from .menus import ListScreen
from .settings import S


def copy_text(s):
    try:
        pygame.scrap.put_text(s)
        return True
    except (pygame.error, AttributeError):
        return False


def paste_text():
    try:
        return pygame.scrap.get_text() or ''
    except (pygame.error, AttributeError):
        return ''


class PlayerVsPlayer(ListScreen):
    title_text = 'PLAYER VS PLAYER'
    sub = 'HOTSEAT: ONE COMPUTER · ONLINE: TWO COMPUTERS'

    def items(self):
        return [{'l': 'HOTSEAT', 'f': lambda: self.app.choose_map('hot')},
                {'l': 'ONLINE', 'f': self.app.online_menu},
                {'l': 'BACK', 'f': self.back}]


class OnlineMenu(ListScreen):
    title_text = 'ONLINE'
    sub = 'THE HOST MAY NEED AN OPEN PORT · SEE ONLINE HELP'

    def items(self):
        return [{'l': 'HOST A BATTLE', 'f': self.app.host_setup},
                {'l': 'JOIN A BATTLE', 'f': self.app.join_game},
                {'l': 'ONLINE HELP', 'f': lambda: self.app.online_help(self.app.online_menu)},
                {'l': 'BACK', 'f': self.back}]

    def back(self):
        self.app.pvp()


class OnlineHelp(Pages):
    """Pages of plain text: how online play works, opening a port, the firewall, and what to do when it won't work."""
    def __init__(self, app, on_exit):
        self.app, self.page, self.on_exit = app, 0, on_exit
        self.pages = load_json('data', 'online_help.json')['pages']
        sound.music('title')

    def draw(self, surf, now):
        page = self.pages[self.page]
        self.frame(surf, page['title'])
        y = 33
        for para in page['text']:
            for line in wrap(para, 48):
                text(surf, line, 16, y, C['ink'])
                y += 9
            y += 5


def lobby_box(surf, app, now, title):
    app.backdrop.draw(surf, now, pygame.Color(12, 15, 8, 170))
    box(surf, 10, 10, SW - 20, SH - 20)
    rect(surf, 12, 12, SW - 24, 14, C['olive'])
    text(surf, title, SW / 2, 15, C['white'], 1, 'c', C['ink'])


def draw_items(surf, items, sel, y):
    for k, label in enumerate(items):
        yy = y + k * 13
        if k == sel:
            rect(surf, 40, yy - 2, SW - 80, 12, C['highlight'])
        text(surf, label, SW / 2, yy, C['ink'], 1, 'c')


class HostLobby:
    """Hosting: waits for the friend, showing the invite code and whether the router opened the port."""
    ITEMS = ['COPY INVITE CODE', 'ONLINE HELP', 'CANCEL']

    def __init__(self, app):
        self.app, self.sel, self.note, self.note_at = app, 0, None, -9
        self.m = app.chosen_map()
        self.start_hosting()
        sound.music('title')

    def start_hosting(self):
        self.app.end_online()
        self.host = self.app.online = net.Host()

    def say(self, note):
        self.note, self.note_at = note, self.app.now

    def key(self, k):
        if k in 'ud':
            self.sel = (self.sel + (-1 if k == 'u' else 1)) % len(self.ITEMS)
            sound.play('cursor')
        elif k == 'b':
            sound.play('back')
            self.cancel()
        elif k == 'e':
            sound.play('select')
            item = self.ITEMS[self.sel]
            if item == 'COPY INVITE CODE':
                if self.host.code and copy_text(self.host.code):
                    self.say('COPIED! SEND IT TO YOUR FRIEND')
                else:
                    sound.play('error')
            elif item == 'ONLINE HELP':
                self.app.online_help(lambda: setattr(self.app, 'scene', self))
            else:
                self.cancel()

    def cancel(self):
        self.app.end_online()
        self.app.setup()

    def update(self, now, dt):
        link = self.host.link
        if not link:
            return
        for msg in link.poll():
            if msg.get('t') == 'hello':
                if msg.get('v') != net.game_id():
                    link.send({'t': 'nope', 'why': 'YOUR GAMES ARE DIFFERENT VERSIONS'})
                    self.say('YOUR FRIEND HAS A DIFFERENT VERSION')
                    self.start_hosting()
                    return
                self.begin(link)
                return
            if msg.get('t') == 'gone':
                self.say('YOUR FRIEND LEFT. STILL WAITING...')
                self.start_hosting()
                return

    def begin(self, link):
        from .play import Play
        m = self.m
        settings = {'mode': 'host', 'cpu': 'normal', 'fog': S['fog'], 'timer': S['timer'], 'anim': S['anim']}
        play = Play(self.app, m, settings, link)
        link.send({'t': 'start', 'map': {'name': m.name, 'theme': m.theme, 'art': m.art, 'blurb': m.blurb},
                   'fog': S['fog'], 'timer': S['timer'], 'snap': play.g.to_wire(1)})
        self.app.circle_to(play)

    def draw(self, surf, now):
        h = self.host
        lobby_box(surf, self.app, now, f'HOSTING: {self.m.name.upper()}')
        if h.error:
            for k, line in enumerate(wrap(h.error, 44)):
                text(surf, line, SW / 2, 50 + k * 10, C['red'], 1, 'c')
        else:
            text(surf, 'INVITE CODE', SW / 2, 34, C['dim'], 1, 'c')
            if h.code:
                text(surf, h.code, SW / 2, 45, C['ink'], 2, 'c')
            else:
                text(surf, 'WORKING IT OUT' + '.' * (int(now * 3) % 3 + 1), SW / 2, 49, C['dim'], 1, 'c')
            router = {'trying': ('ASKING YOUR ROUTER TO OPEN THE PORT...', C['dim']),
                      'open': ('ROUTER: PORT OPENED. FRIENDS ANYWHERE CAN JOIN.', C['olive']),
                      'closed': ("ROUTER: COULDN'T OPEN THE PORT. SAME WI-FI WORKS;"
                                 f" OVER THE INTERNET, FORWARD PORT {h.port} (SEE ONLINE HELP).", C['red']),
                      'shared': ('YOUR INTERNET PROVIDER SHARES YOUR ADDRESS, SO FRIENDS OUTSIDE CAN\'T REACH YOU.'
                                 ' SAME WI-FI WORKS. SEE ONLINE HELP.', C['red'])}[h.router]
            y = 70
            for line in wrap(router[0], 46):
                text(surf, line, SW / 2, y, router[1], 1, 'c')
                y += 9
            text(surf, f'THIS COMPUTER: {h.local}  PORT {h.port}', SW / 2, y + 4, C['dim'], 1, 'c')
            text(surf, 'WAITING FOR YOUR FRIEND' + '.' * (int(now * 2) % 3 + 1), SW / 2, y + 20, C['ink'], 1, 'c')
        draw_items(surf, self.ITEMS, self.sel, 160)
        if self.note and now - self.note_at < 3:
            text(surf, self.note, SW / 2, 204, C['olive'], 1, 'c')
        text(surf, 'WINDOWS MAY ASK TO ALLOW NETWORK ACCESS: ALLOW IT', SW / 2, SH - 24, C['dim'], 1, 'c')


class JoinScreen:
    """Type (or paste) the host's invite code, then JOIN. A plain address like 192.168.1.5 works too."""
    ITEMS = ['CODE', 'JOIN!', 'PASTE CODE', 'ONLINE HELP', 'BACK']
    TYPEABLE = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.:-')

    def __init__(self, app, code=''):
        self.app, self.code, self.sel = app, code, 0
        self.join, self.error, self.hello = None, None, False
        sound.music('title')

    def typed(self, e):
        """Keys typed into the code (the App hands every key here first). True = used."""
        if self.sel != 0 or self.join:
            return False
        if e.key == pygame.K_BACKSPACE:
            self.code = self.code[:-1]
        elif e.key == pygame.K_v and e.mod & pygame.KMOD_CTRL:
            self.paste()
        elif e.unicode and e.unicode.upper() in self.TYPEABLE and len(self.code) < 24:
            self.code += e.unicode.upper()
        else:
            return False
        self.error = None
        sound.play('cursor')
        return True

    def paste(self):
        got = ''.join(c for c in paste_text().upper() if c in self.TYPEABLE)[:24]
        if got:
            self.code, self.error = got, None

    def key(self, k):
        if self.join:                      # connecting: only ESC (give up)
            if k == 'b':
                self.stop()
            return
        if k in 'ud':
            self.sel = (self.sel + (-1 if k == 'u' else 1)) % len(self.ITEMS)
            sound.play('cursor')
        elif k == 'b':
            sound.play('back')
            self.app.online_menu()
        elif k == 'e':
            item = self.ITEMS[self.sel]
            if item in ('CODE', 'JOIN!'):
                self.start()
            elif item == 'PASTE CODE':
                sound.play('select')
                self.paste()
            elif item == 'ONLINE HELP':
                sound.play('select')
                self.app.online_help(lambda: setattr(self.app, 'scene', self))
            else:
                sound.play('back')
                self.app.online_menu()

    def start(self):
        places = net.read_code(self.code)
        if not places:
            sound.play('error')
            self.error = "THAT CODE DOESN'T LOOK RIGHT. IT HAS 16 LETTERS AND NUMBERS."
            return
        sound.play('select')
        self.error, self.hello = None, False
        self.join = self.app.online = net.Join(places)

    def stop(self, error=None):
        self.app.end_online()
        self.join, self.error = None, error
        sound.play('error' if error else 'back')

    def update(self, now, dt):
        j = self.join
        if not j:
            return
        if j.state == 'failed':
            self.stop("COULDN'T REACH THE HOST. CHECK THE CODE, THAT THE HOST IS WAITING, AND THAT THEIR PORT IS OPEN"
                      " (SEE ONLINE HELP).")
            return
        if j.state != 'ok':
            return
        if not self.hello:
            j.link.send({'t': 'hello', 'v': net.game_id()})
            self.hello = True
        for msg in j.link.poll():
            if msg.get('t') == 'start':
                self.begin(j.link, msg)
                return
            if msg.get('t') == 'nope':
                self.stop(msg.get('why', 'THE HOST SAID NO'))
                return
            if msg.get('t') == 'gone':
                self.stop('THE HOST CLOSED THE CONNECTION.')
                return

    def begin(self, link, msg):
        from .play import Play
        m = parse_map(msg['map'])
        settings = {'mode': 'guest', 'cpu': 'normal', 'fog': msg['fog'], 'timer': msg['timer'], 'anim': S['anim']}
        play = Play(self.app, m, settings, link)
        play.g.from_wire(msg['snap'], play.me)
        self.app.circle_to(play)

    def draw(self, surf, now):
        lobby_box(surf, self.app, now, 'JOIN A BATTLE')
        text(surf, "TYPE OR PASTE (CTRL+V) YOUR FRIEND'S INVITE CODE", SW / 2, 34, C['dim'], 1, 'c')
        on = self.sel == 0 and not self.join
        rect(surf, 40, 48, SW - 80, 22, C['ink'])
        rect(surf, 41, 49, SW - 82, 20, C['highlight'] if on else C['paper'])
        shown = self.code + ('_' if on and int(now / .4) % 2 else '')
        text(surf, shown or ('' if on else 'NO CODE YET'), SW / 2, 53, C['ink'] if self.code else C['dim'], 2 if len(self.code) <= 19 else 1, 'c')
        if self.join:
            text(surf, 'CONNECTING' + '.' * (int(now * 3) % 3 + 1), SW / 2, 90, C['ink'], 1, 'c')
            text(surf, 'ESC: GIVE UP', SW / 2, 104, C['dim'], 1, 'c')
            return
        draw_items(surf, self.ITEMS[1:], self.sel - 1, 84)
        if self.error:
            for k, line in enumerate(wrap(self.error, 46)):
                text(surf, line, SW / 2, 152 + k * 9, C['red'], 1, 'c')
        text(surf, 'THE HOST PICKS THE MAP: YOU GET IT AUTOMATICALLY', SW / 2, SH - 24, C['dim'], 1, 'c')
