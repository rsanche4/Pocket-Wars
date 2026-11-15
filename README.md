# Pocket Wars

A small turn-based war game: plastic army men, pixel dioramas, Game Boy Advance style. © 2026 RAFFY'S PLAYGROUND

Made with Python and **Pygame**.

## Setup and running

Python 3.12+ and pygame-ce:

    py -m pip install pygame-ce
    py main.py

Keys: ARROWS move, ENTER (or Z, SPACE) select, ESC (or X) back, F11 full screen.
Your settings are kept in `settings.json` (delete it to go back to the defaults).
What the Hard CPU has learned about you is kept in `learned.json` (Options → HARD'S MEMORY erases it, or delete the file).

## Folders

| Folder | What's in it | Change it? |
|---|---|---|
| `assets/` | every picture and sound the game uses | yes: replace any file with your own (same name) |
| `data/` | unit stats (`units.json`), CPU settings (`ai.json`), colours and battle-scene timing (`style.json`), font layout (`font.json`), How to Play and editor guide text (`howto.json`, `editor_help.json`) | yes |
| `maps/` | the built-in maps, one `.json` each | yes: add or edit maps |
| `my-maps/` | maps you make in the editor. Share a map by sending its file; drop a friend's file in here to play it | yes |
| `pw/` | the Python code | |
| `tools/` | helper scripts: CPU simulations, the sound and music generators | |

## The code (`pw/`)

| File | Job |
|---|---|
| `data.py` | loads unit stats, CPU settings and maps (and saves your maps) |
| `rules.py` | the rules: one battle's state and every move a player can make. No drawing. |
| `ai.py` | the Normal and Hard CPU players (Hard thinks ahead on copies of the board and has several styles) |
| `learn.py` | Hard's memory of you: which styles beat you and which vehicles you build (`learned.json`) |
| `gfx.py` | the 320x240 screen, loading images, the pixel font, simple shapes |
| `world.py` | builds a map's ground from the terrain tiles |
| `field.py` | draws a battle: outposts, buildings, units, fog, cursor, marching groups |
| `cutin.py` | the battle scene when one unit attacks another |
| `menu.py` | the pop-up menu box |
| `play.py` | the battle screen: keys, menus, CPU turns, animations |
| `stats.py` | BATTLE STATS after a battle: a report card and turn-by-turn charts (numbers kept by `rules.py`) |
| `title.py` | the title screen, its intro, the live battle behind it and the commanders |
| `menus.py` | choose a battlefield, battle setup, options |
| `howto.py` | How to Play (and the editor's guide), with their pictures |
| `editor.py` | the map editor and the list of your maps |
| `demo.py` | make-believe battles for the title and How to Play |
| `settings.py` | loads and saves `settings.json` |
| `sound.py` | plays sound effects and music from files (missing files are just silent) |

## Pictures you can swap without touching code

Every image is a file in `assets/`, including the font (`assets/ui/font.png`, letter order in `data/font.json`).
Pictures are drawn exactly as they are (never mirrored), so Tan's art should already face left.

Each unit has three pictures, one per size, named `<unit>_<side>.png` (e.g. `tank_tan.png`):
`assets/units/battle/` (battle scenes, shown at double size), `assets/units/map/` (the battlefield)
and `assets/units/icons/` (menus and the How to Play tables). The icons folder also has `hq_green.png` and
`hq_tan.png`, the little castle in the How to Play tables (the map and battle HQs are in `assets/buildings/`).

A few extras are optional:
- `assets/ui/title_backdrop.png` (320x240): a fixed picture behind the title instead of the live battle.
- `assets/howto/<picture>.png` (292x100): your own picture for a How to Play page (names are in `data/howto.json`).
- `assets/ui/keys/<key>.png` and `<key>_pressed.png`: the keyboard keys on the How to Play controls page.
- `assets/commanders/<folder>/title.png`: a strip of square frames that animates a commander on the title
  (speed: `title_anim_fps` in `data/style.json`); `blink.png` is their closed-eye face.

## Sound effects

Every sound is a file in `assets/sfx/` (35 of them, e.g. `cursor.wav`, `shot_tank.wav`, `turn_green.wav`).
Replace any with your own: same name, WAV, OGG or MP3. A missing file is simply silent.
`tools/make_sfx.py` made the originals in a Game Boy Advance style; running it again overwrites them,
so only run it for names you haven't replaced (e.g. `py tools/make_sfx.py cursor select`).
Music is in `assets/music/` (`title`, `battle`, `victory`).

## Map files

    {"name": "Boot Camp", "theme": "grass", "blurb": "...", "art": ["o-G~G-o", "| | | |", "H-o=o-h", ...]}

`theme` is grass, desert, beach or snow. In `art`, outposts sit on even rows and columns:
`o` outpost, `G` barracks, `H` Green HQ, `h` Tan HQ. Between them: `-` `|` road, `~` river, `=` bridge,
and on odd rows and columns `/` `\` `X` diagonal roads.

## Tools

    py tools/sim.py --games 200 --level hard      # CPU vs CPU on every map, to check fairness
    py tools/make_sfx.py                          # remake the built-in sound effects
    py tools/make_music.py                        # remake the placeholder music (needs numpy and ffmpeg)
