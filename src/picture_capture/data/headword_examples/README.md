# Project Profile headword example crops

Wizard step ③ shows real, locally cropped dictionary examples in the right image pane.

The packaged examples are stored in a compact atlas:

- `classic_headword_examples.jpg`
- canvas: 1080 × 474
- grid: 3 columns × 3 rows
- each cell: 360 × 158

Atlas cells, in reading order:

1. `latin_regular_NewApproach`
2. `latin_regular_LDER`
3. `numbered_prefix_RUIGO`
4. `cjk_visual_HZYLDZD`
5. `cjk_visual_XDHYCD`
6. `cjk_visual_TimesCED`
7. `cjk_visual_shueisha`
8. `edge_visual_regular_XAHDCD`
9. `marker_prefixed_HanYi`

These are tight local crops from the real test dictionaries, not full-page screenshots. Each crop keeps the headword and enough neighboring definition text to make the entry boundary understandable.

Individual files remain supported and override the atlas when present. Lookup order is:

1. `<profile_key>_<dictionary_name>.png/jpg/jpeg/webp`
2. `<dictionary_name>.png/jpg/jpeg/webp`
3. `<profile_key>.png/jpg/jpeg/webp`
4. bundled atlas cell

`custom` intentionally has no fixed classic example because it represents layouts not covered by the predefined structure families; users can start from the closest preset and then customize parser checkboxes.
