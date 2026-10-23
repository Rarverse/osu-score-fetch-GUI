from fontTools.ttLib import TTFont
from fontTools import subset
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]
out=root/'public/fonts/maple-mono'
source_dir=Path(sys.argv[1])
def unicode_ranges(points):
    runs = []
    start = end = sorted(points)[0]
    for cp in sorted(points)[1:]:
        if cp == end + 1:
            end = cp
        else:
            runs.append(f'U+{start:X}' if start == end else f'U+{start:X}-{end:X}')
            start = end = cp
    runs.append(f'U+{start:X}' if start == end else f'U+{start:X}-{end:X}')
    return ','.join(runs)

css=[]
for style,weight in [('Regular','400 500'),('SemiBold','600 900')]:
    source=source_dir/f'MapleMono-CN-{style}.ttf'
    cmap=TTFont(source).getBestCmap()
    groups={cp//1024 for cp in cmap}
    for group in sorted(groups):
        points=[cp for cp in cmap if cp//1024==group]
        font=TTFont(source)
        opts=subset.Options();opts.flavor='woff2';opts.layout_features=['*']
        worker=subset.Subsetter(options=opts);worker.populate(unicodes=points);worker.subset(font)
        name=f'{style.lower()}-{group:x}.woff2';font.flavor='woff2';font.save(out/name)
        ranges=unicode_ranges(points)
        css.append(f'@font-face {{font-family: "Maple Mono CN"; font-style: normal; font-weight: {weight}; font-display: swap; src: url("/fonts/maple-mono/{name}") format("woff2"); unicode-range: {ranges};}}')
    print(style,flush=True)
(root/'src/fonts.css').write_text('\n'.join(css)+'\n')
