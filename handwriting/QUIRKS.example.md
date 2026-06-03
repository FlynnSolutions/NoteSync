# Handwriting profile

Copy this to `QUIRKS.md` (gitignored) and fill it in for *your* hand. `read_ink.py`
feeds it to Claude alongside each page so it can disambiguate your handwriting. It's
optional — without it the read still works, just with less context on your quirks.

Keep it short and specific. The useful entries are the letters/words Claude tends to
misread for you, plus any personal shorthand or domain vocabulary it should expect.

## Ambiguities to watch

List the confusions specific to your hand, with the rule for resolving them. Examples:

- **`a` vs `o`** — your `a` is often open at the top and reads as `o`; prefer the one
  that fits the word.
- **trailing `g`/`y` tails** look alike — disambiguate by the word, not the descender.
- A circled or boxed token (e.g. a `@name` mention) is a deliberate marker — trust it.

## Vocabulary / shorthand to expect

Words, names, or abbreviations you write often that aren't everyday English, so Claude
doesn't "correct" them to a more common word. Examples:

- Project / product names you use.
- Personal shorthand (e.g. "EOD", "wks", your own abbreviations).

## Notes

Anything else about how you mark up a page — e.g. "a strike-through means delete",
"margin text is a note on the nearest line", "an arrow means move/relocate".
