"""Online play: one player HOSTS and their game is the boss (it holds the real board, checks every move and rolls the
dice); the other JOINS with the host's invite code. Nothing else is needed: no server, no accounts.

The two games talk over one TCP connection, one JSON message per line (see Play.apply / Play.on_message for what they
say). A background thread reads the line; the game picks messages up each frame with poll(), so it never freezes.

Home routers block connections coming in, so the host's game asks its router to open the port by itself (UPnP, see
open_port); when the router won't, ONLINE HELP explains port forwarding. The invite code holds the host's internet
address, its address on the home network and the port, so one code works both over the internet and on the same Wi-Fi.
Only Python's own modules are used.
"""
import functools
import hashlib
import ipaddress
import json
import os
import queue
import re
import socket
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .data import ROOT, load_json

PORT = 47123                         # the port the host listens on (and asks its router to open)
PROTOCOL = 1                         # bump when the messages change, so old and new games refuse to mix
LETTERS = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'      # invite code letters: no I, L, O or U (they look like 1, 0 and V)
IP_LOOKUP = 'https://api.ipify.org'  # asked for the host's internet address only when the router doesn't say it
MAX_LINE = 2_000_000                 # a message bigger than this is nonsense: hang up


@functools.cache
def game_id():
    """Both games must have the same rules and unit stats: this fingerprint of them is compared when a guest joins,
    and kept in recordings. It is taken from the stats themselves, so how the file is laid out (its line endings, which
    git changes from one computer to another, or its spacing) doesn't count."""
    stats = json.dumps(load_json('data', 'units.json'), sort_keys=True, separators=(',', ':'))
    return f'{PROTOCOL}-{hashlib.sha1(stats.encode()).hexdigest()[:10]}'


@functools.cache
def same_stats(fingerprint):
    """Was a recording made with these unit stats? Recordings from before game_id looked at the stats themselves hold
    a fingerprint of the file as it was, with either kind of line endings: those match too."""
    with open(os.path.join(ROOT, 'data', 'units.json'), 'rb') as f:
        lf = f.read().replace(b'\r\n', b'\n')
    old = {f'{PROTOCOL}-{hashlib.sha1(b).hexdigest()[:10]}' for b in (lf, lf.replace(b'\n', b'\r\n'))}
    return fingerprint == game_id() or fingerprint in old


# ---------------------------------------------------------------------------------------------- the connection
class Link:
    """One open connection to the other player's game."""
    def __init__(self, sock):
        self.sock = sock
        self.inbox = queue.Queue()
        self.alive = True
        self.lock = threading.Lock()
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        buf = b''
        try:
            while True:
                data = self.sock.recv(65536)
                if not data:
                    break
                buf += data
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    if line.strip():
                        self.inbox.put(json.loads(line))
                if len(buf) > MAX_LINE:
                    break
        except (OSError, ValueError):
            pass
        self.gone()

    def gone(self):
        if self.alive:
            self.alive = False
            self.inbox.put({'t': 'gone'})

    def send(self, msg):
        if not self.alive:
            return
        try:
            with self.lock:
                self.sock.sendall((json.dumps(msg, separators=(',', ':')) + '\n').encode())
        except OSError:
            self.gone()

    def poll(self):
        """Every message that has arrived since the last poll."""
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self):
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


# ---------------------------------------------------------------------------------------------- invite codes
def make_code(public, local, port=PORT):
    """16 letters (shown as 4 groups of 4) holding the internet address, the home-network address and the port."""
    raw = ipaddress.IPv4Address(public or '0.0.0.0').packed + ipaddress.IPv4Address(local or '0.0.0.0').packed
    n = int.from_bytes(raw + port.to_bytes(2, 'big'), 'big')
    s = ''.join(LETTERS[(n >> (5 * k)) & 31] for k in range(15, -1, -1))
    return '-'.join(s[k:k + 4] for k in range(0, 16, 4))


def read_code(text):
    """[(address, port), ...] to try, in order, from an invite code or a typed address (like 192.168.1.5 or
    100.101.2.3:47123). None if it doesn't make sense."""
    t = text.strip().upper()
    m = re.fullmatch(r'(\d{1,3}(?:\.\d{1,3}){3})(?::(\d{1,5}))?', t)
    if m:
        try:
            ipaddress.IPv4Address(m.group(1))
        except ValueError:
            return None
        return [(m.group(1), int(m.group(2) or PORT))]
    s = re.sub(r'[^0-9A-Z]', '', t).replace('O', '0').replace('I', '1').replace('L', '1').replace('U', 'V')
    if len(s) != 16 or any(c not in LETTERS for c in s):
        return None
    n = 0
    for c in s:
        n = n * 32 + LETTERS.index(c)
    raw = n.to_bytes(10, 'big')
    public, local = str(ipaddress.IPv4Address(raw[:4])), str(ipaddress.IPv4Address(raw[4:8]))
    port = int.from_bytes(raw[8:], 'big')
    out = [(ip, port) for ip in (local, public) if ip != '0.0.0.0']    # the same Wi-Fi first: it answers fastest
    return out or None


# ---------------------------------------------------------------------------------------------- addresses
def local_address():
    """This computer's address on the home network (no data is sent: connecting a UDP socket just picks the route)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()


def shared_address(ip):
    """True for addresses that can't be reached from the internet: home-network ones, and the range internet
    providers use when many homes share one address (CGNAT)."""
    a = ipaddress.IPv4Address(ip)
    return a.is_private or a in ipaddress.IPv4Network('100.64.0.0/10')


def ask_internet_address():
    try:
        with urllib.request.urlopen(IP_LOOKUP, timeout=4) as r:
            ip = r.read().decode().strip()
        ipaddress.IPv4Address(ip)
        return ip
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------- the router (UPnP)
SSDP = ('239.255.255.250', 1900)
WAN = ('urn:schemas-upnp-org:service:WANIPConnection:2', 'urn:schemas-upnp-org:service:WANIPConnection:1',
       'urn:schemas-upnp-org:service:WANPPPConnection:1')


def find_router(wait=2.5):
    """(control URL, service type) of the router's port-opening service, or None."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(wait)
    places = []
    try:
        for target in ('urn:schemas-upnp-org:device:InternetGatewayDevice:1', 'upnp:rootdevice'):
            ask = (f'M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\n'
                   f'ST: {target}\r\n\r\n')
            s.sendto(ask.encode(), SSDP)
        while True:
            data, _ = s.recvfrom(4096)
            m = re.search(rb'(?im)^location:\s*(\S+)', data)
            if m and m.group(1).decode() not in places:
                places.append(m.group(1).decode())
    except OSError:
        pass
    finally:
        s.close()
    for place in places:
        try:
            with urllib.request.urlopen(place, timeout=3) as r:
                tree = ET.fromstring(r.read())
        except (OSError, ET.ParseError, ValueError):
            continue
        for svc in tree.iter():
            if not svc.tag.endswith('service'):
                continue
            fields = {c.tag.split('}')[-1]: (c.text or '').strip() for c in svc}
            if fields.get('serviceType') in WAN and fields.get('controlURL'):
                return urllib.parse.urljoin(place, fields['controlURL']), fields['serviceType']
    return None


def soap(router, action, args=()):
    url, service = router
    body = ''.join(f'<{k}>{v}</{k}>' for k, v in args)
    envelope = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
                's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
                f'<u:{action} xmlns:u="{service}">{body}</u:{action}></s:Body></s:Envelope>')
    req = urllib.request.Request(url, envelope.encode(), {'Content-Type': 'text/xml; charset="utf-8"',
                                                          'SOAPAction': f'"{service}#{action}"'})
    with urllib.request.urlopen(req, timeout=4) as r:
        return r.read().decode(errors='replace')


def open_port(port, local):
    """Ask the router to send connections on this port to this computer. Returns (router, its internet address)
    or (None, None) when there's no router that will."""
    router = find_router()
    if not router:
        return None, None
    try:
        soap(router, 'AddPortMapping', (('NewRemoteHost', ''), ('NewExternalPort', port), ('NewProtocol', 'TCP'),
                                        ('NewInternalPort', port), ('NewInternalClient', local), ('NewEnabled', 1),
                                        ('NewPortMappingDescription', 'Pocket Wars'), ('NewLeaseDuration', 0)))
    except OSError:
        return None, None
    try:
        m = re.search(r'<NewExternalIPAddress>([\d.]+)<', soap(router, 'GetExternalIPAddress'))
        return router, (m.group(1) if m else None)
    except OSError:
        return router, None


def close_port(router, port):
    try:
        soap(router, 'DeletePortMapping', (('NewRemoteHost', ''), ('NewExternalPort', port), ('NewProtocol', 'TCP')))
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------- hosting / joining
class Host:
    """Listens for one guest, and meanwhile gets the port opened and works out the invite code.
    router: 'trying', 'open' (the router opened the port), 'closed' (it didn't: port forwarding needed, unless your
    friend is on the same Wi-Fi) or 'shared' (the internet provider shares the address: hosting over the internet
    can't work from here). code: None until worked out."""
    def __init__(self, port=PORT):
        self.port, self.local = port, local_address()
        self.router, self.code, self.public, self.link, self.error = 'trying', None, None, None, None
        self.upnp = None
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.server.bind(('', port))
            self.server.listen(1)
        except OSError:
            self.error = f'PORT {port} IS BUSY (IS POCKET WARS ALREADY HOSTING?)'
            self.server.close()
            return
        threading.Thread(target=self.wait_for_guest, daemon=True).start()
        threading.Thread(target=self.reach_out, daemon=True).start()

    def reach_out(self):
        self.upnp, outside = open_port(self.port, self.local)
        looked_up = ask_internet_address()
        self.public = looked_up or outside
        if self.upnp and outside and (shared_address(outside) or (looked_up and looked_up != outside)):
            self.router = 'shared'           # the router sits behind another one it doesn't control
        else:
            self.router = 'open' if self.upnp else 'closed'
        self.code = make_code(self.public, self.local, self.port)

    def wait_for_guest(self):
        try:
            sock, _ = self.server.accept()
        except OSError:
            return
        self.link = Link(sock)
        self.server.close()                  # one guest per battle

    def close(self):
        try:
            self.server.close()
        except OSError:
            pass
        if self.link:
            self.link.close()
        if self.upnp:                        # ask the router to close the port again (in the background)
            threading.Thread(target=close_port, args=(self.upnp, self.port)).start()
            self.upnp = None


class Join:
    """Tries each address from the code in turn. state: 'trying', 'ok' (link is set) or 'failed'."""
    def __init__(self, places):
        self.state, self.link = 'trying', None
        threading.Thread(target=self.reach, args=(places,), daemon=True).start()

    def reach(self, places):
        for ip, port in places:
            try:
                sock = socket.create_connection((ip, port), timeout=2.5 if shared_address(ip) else 6)
            except OSError:
                continue
            self.link, self.state = Link(sock), 'ok'
            return
        self.state = 'failed'

    def close(self):
        if self.link:
            self.link.close()
