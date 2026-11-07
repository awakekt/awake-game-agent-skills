# Moving canvas screen UI to Compose

A game that started its HUD and windows on the scene canvas and added Compose windows later runs two
UI systems with a bridge between them: canvas units against pixels, two scales, drag and drop from a
canvas slot onto a Compose window, and windows registered in two places. Bugs collect at that bridge.
Move the screen UI to Compose piece by piece until the bridge is gone; leave on the canvas only what
follows the world.

## What moves, what stays

| Moves to Compose | Stays on the canvas |
|---|---|
| Windows and dialogs, movable or not | Nameplates and bars over entities |
| HUD bars, unit and party frames, the skill bar and its slots | Floating damage and heal text |
| Chat, tooltips, menus, the screen's corner buttons | Target and quest markers in the world |
| Everything the player drags, drops, types into or opens | Prefabs an editor authors and saves as data |

## Order

1. **The skin first.** Draw the old look in Compose before moving any window, so a moved window
   looks the same. Pixel-art frames, title bars, buttons and slots are nine-slice art: draw them with
   `ImageFill` and `drawImageFill`, a gauge's fill with `drawImageFillBar` (its end caps stay whole),
   and set `FilterQuality.None` so the art stays crisp. `drawImageFill` puts every piece on whole
   pixels, so a fractional scale such as 1.5 opens no seam.
2. **One window or HUD piece per change.** Build it in Compose from the same state, keep its
   behaviour (actions, drag and drop, keyboard, touch), and delete its canvas copy in the same change.
   Never keep a hidden canvas copy: it still costs every frame and a second copy can draw over the
   new one.
3. **Pieces that trade drag and drop together move together**, or the drop crosses the bridge in
   between: a skill bar and the window you drag skills from, an item grid and the slots you equip to.
4. **Remove the bridge last**: the conversion between canvas units and pixels, any second scale,
   and the canvas window registry, once no screen UI is left on the canvas.

## Prove each step

- A screenshot test per moved piece, against the canvas original: the same pixels, or a difference
  that is deliberate and shown in the change. Draw it at a fractional density (1.25 or 1.5) as well
  as 1, where seams and off-by-one sizes show.
- A test for its behaviour through the real input path: a drag dropped on a slot lands in the slot at
  density 2, a button press reaches the system once.

## Guard it

While the move is under way, keep the remaining canvas screen UI from growing:

- List what is left (the canvas windows in prefabs, the code that hosts a canvas window) in a check
  that fails on anything new, and also on a listed piece that is gone, so the list only shrinks.
- Deprecate your own canvas window helpers, so a new use warns.
- Say it where people and agents look first: the game's UI doc and its agent guide.
