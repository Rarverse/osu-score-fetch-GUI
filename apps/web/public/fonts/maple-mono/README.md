Maple Mono CN v7.9, from https://github.com/subframe7536/maple-font/releases/tag/v7.9
Source: MapleMono-CN-unhinted.zip; SIL Open Font License (LICENSE.txt).

Regular is used for weights 400–500; SemiBold for 600–900.
WOFF2 files are Unicode subsets of the corresponding TTF, grouped in blocks of
1024 code points with FontTools (all layout features retained). CSS unicode-range
loads only blocks required by the displayed text. No local() font lookup is used.

To regenerate: install fonttools and brotli in an isolated Python environment,
extract the two source TTFs, then run `python apps/web/scripts/subset-maple.py /path/to/extracted/fonts`
and format src/fonts.css with the project's formatter.
