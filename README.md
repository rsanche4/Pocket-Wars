# Pocket Wars

A small turn-based war game: plastic army men, pixel dioramas, Game Boy Advance style.
Made with Python and pygame-ce. © 2026 RAFFY'S PLAYGROUND

## Running it

Python 3.12+ and pygame-ce:

    py -m pip install pygame-ce
    py main.py

Keys: ARROWS move, ENTER (or Z, SPACE) select, ESC (or X) back, F11 full screen.

## What's in the game

- **Tutorial**: the Green Commander teaches the game on Boot Camp, one step at a time.
- **Player vs CPU**: Normal or Hard (Hard tries its best moves on copies of the board, your reply included, before choosing).
- **Player vs Player**: HOTSEAT on one computer, or ONLINE on two (see below).
- **Recordings**: turn RECORD on in the battle setup, then watch battles back from RECORDINGS.
- **Manual**: how to play, page by page.
- **Map editor**: build your own maps, or let GENERATE MAP make one. With BALANCE: FAIR it plays quick CPU-vs-CPU
  test games first, so neither side is favoured (RANDOM skips that and can give lopsided, more surprising maps).
- **Options**: sound, music, full screen, and LANGUAGE (English or Spanish).

Your settings are kept in `settings.json` (delete it to go back to the defaults).

## Playing online

One player hosts: they pick the map and settings, their game runs the battle, and they get an invite code.
The other joins by typing or pasting the code and receives the map automatically.

The host's game listens on TCP port 47123 and asks the router to open it by itself. If the router won't,
ONLINE HELP (in the game) explains port forwarding step by step. To make the invite code, the host's game may ask
`api.ipify.org` for its internet address. With fog of war on, the guest's game only receives what it can see.

## Folders

| Folder | What's in it |
|---|---|
| `assets/` | every picture, sound and music file (replace any with your own, same name) |
| `data/` | unit stats, CPU settings, colours, font layout, and the texts of the Manual, tutorial, editor guide and online help |
| `data/lang/` | the Spanish translation: `es.json` for buttons and messages, `es/` for the longer texts |
| `maps/` | every map, one `.json` each. Share a map by sending its file |
| `data/default-maps/` | untouched copies of the built-in maps (for RESET TO DEFAULT) |
| `recordings/` | saved battles, one small `.json` each. Share them like maps |
| `pw/` | the code |
| `tools/` | helper scripts |

## The code (`pw/`)

| File | Job |
|---|---|
| `rules.py` | the rules: one battle's state and every move. No drawing |
| `ai.py` | the CPU players |
| `play.py` | the battle screen: keys, menus, turns, animations |
| `field.py`, `world.py` | drawing the battlefield and building its ground |
| `cutin.py` | the battle scene when one unit attacks another |
| `tutorial.py` | the tutorial's lessons, talk box and scripted Tan |
| `net.py`, `online.py` | online play: the connection, invite codes, and its screens |
| `recordings.py` | saving recordings, the list, and the playback screen |
| `title.py`, `menus.py`, `menu.py` | the title screen, the other menus, and the pop-up menu box |
| `howto.py`, `stats.py` | the Manual and the battle stats |
| `editor.py`, `mapgen.py` | the map editor and the map generator |
| `demo.py` | the little battles behind the title and in the Manual |
| `gfx.py`, `sound.py`, `lang.py` | drawing helpers and the pixel font, sounds and music, translations |
| `data.py`, `settings.py` | loading data and maps, and the settings file |

## Changing the art and sounds

Every picture is a file in `assets/` and is used exactly as it is, so you can paint over any of them.
Units have three sizes (`assets/units/battle/`, `map/` and `icons/`), named `<unit>_<side>.png`.
Each map theme has its tiles in `assets/terrain/<theme>/`. The font is `assets/ui/font.png`
(its letter order is in `data/font.json`). Colours are in `data/style.json`.

Sounds are in `assets/sfx/` (WAV, OGG or MP3) and music in `assets/music/`. A missing file is simply silent.

Some originals were made by scripts in `tools/`. Running one again overwrites those files, so pass the names of
only the ones you want remade, e.g. `py tools/make_ui.py cursor` or `py tools/make_sfx.py select`.

## Map files

    {"name": "Boot Camp", "theme": "grass", "blurb": "...", "art": ["o-G~G-o", "| | | |", "H-o=o-h", ...]}

`theme` is grass, desert, beach or snow. In `art`, outposts sit on even rows and columns:
`o` outpost, `G` barracks, `H` Green HQ, `h` Tan HQ. Between them: `-` `|` road, `~` river, `=` bridge,
and `/` `\` `X` diagonal roads. A diagonal road with a river next to it in the drawing (`~` or `=` right beside it)
crosses that river on a bridge by itself, drawn with the theme's `bridge_diagonal.png`.

## Tools

    py tools/sim.py --games 200 --level hard      # CPU vs CPU on every map, to check fairness
    py tools/make_ui.py NAME ...                  # remake some interface pictures
    py tools/make_sfx.py NAME ...                 # remake some sound effects
    py tools/make_music.py                        # remake the placeholder music (needs numpy and ffmpeg)
