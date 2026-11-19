#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_web_assets —— 把素材库转成网页可用的集成包

用法:
  python3 make_web_assets.py --lib <素材库A> --lib <素材库B> --out <输出目录> \
      [--prefixes p1,p2] [--eq 2560] [--thumb 480] [--quality 82]

输入约定：每个 --lib 指向一个素材库目录，其下需有 01_等距柱状全景_*/
输出：
  out/img/equirect/*.webp   网页用全景（默认 2560×1280）
  out/img/thumb/*.jpg       缩略图（默认 480×240）
  out/img/contact-sheet.jpg 全部点位拼版
  out/data/points.json      清单（同时写 js/pano-data.js）
模板（js/css/index.html）不在这里生成，需从 skill 的 assets/web-kit-template 复制。
"""
import argparse, glob, json, os
from PIL import Image, ImageDraw, ImageFont


def font(sz):
    for p in ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
              '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
              '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def sheet(pts, cols, tw, th, out, title):
    rows = (len(pts) + cols - 1) // cols
    pad, lab = 8, 22
    img = Image.new('RGB', (cols * (tw + pad) + pad, rows * (th + lab + pad) + pad + 44), (18, 20, 24))
    dr = ImageDraw.Draw(img)
    dr.text((pad, 10), title, font=font(28), fill=(235, 238, 242))
    f2 = font(15)
    for i, p in enumerate(pts):
        x = pad + (i % cols) * (tw + pad)
        y = 44 + pad + (i // cols) * (th + lab + pad)
        im = Image.open(p['_thumb_path']).resize((tw, th), Image.LANCZOS)
        img.paste(im, (x, y))
        dr.text((x, y + th + 3), (p['id'] + ' ' + p['name'])[:26], font=f2, fill=(200, 205, 212))
    img.save(out, quality=88, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lib', action='append', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--prefixes', default=None)
    ap.add_argument('--eq', type=int, default=2560)
    ap.add_argument('--thumb', type=int, default=480)
    ap.add_argument('--quality', type=int, default=82)
    ap.add_argument('--title', default='全景点位库')
    a = ap.parse_args()

    for d in ('img/equirect', 'img/thumb', 'js', 'css', 'data', 'vector'):
        os.makedirs(os.path.join(a.out, d), exist_ok=True)

    prefixes = (a.prefixes.split(',') if a.prefixes else
                ['p%d' % (i + 1) for i in range(len(a.lib))])
    points = []
    for lib, pre in zip(a.lib, prefixes):
        src = glob.glob(os.path.join(lib, '01_等距柱状全景_*'))[0]
        for fp in sorted(glob.glob(os.path.join(src, '*.jpg'))):
            base = os.path.basename(fp)[:-4]
            nn = base.split('_')[0]
            name = base.split('_', 1)[1].replace('_360', '') if '_' in base else base
            pid = '%s-%s' % (pre, nn)
            eq = os.path.join(a.out, 'img/equirect', pid + '.webp')
            th = os.path.join(a.out, 'img/thumb', pid + '.jpg')
            if not os.path.exists(eq):
                Image.open(fp).convert('RGB').resize((a.eq, a.eq // 2), Image.LANCZOS) \
                    .save(eq, 'WEBP', quality=a.quality, method=5)
            if not os.path.exists(th):
                Image.open(fp).convert('RGB').resize((a.thumb, a.thumb // 2), Image.LANCZOS) \
                    .save(th, quality=82, optimize=True)
            points.append({
                'id': pid, 'name': name, 'source': os.path.basename(lib.rstrip('/')),
                'img': 'img/equirect/%s.webp' % pid, 'thumb': 'img/thumb/%s.jpg' % pid,
                'type': '航拍' if '航拍' in name else ('校门' if '门' in name else '全景'),
                '_thumb_path': th,
            })
            print('.', pid, name)

    if points:
        sheet(points, 6, 300, 150, os.path.join(a.out, 'img/contact-sheet.jpg'), a.title)

    for p in points:
        p.pop('_thumb_path', None)
    json.dump(points, open(os.path.join(a.out, 'data/points.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    with open(os.path.join(a.out, 'js/pano-data.js'), 'w', encoding='utf-8') as f:
        f.write('window.PANO_POINTS = ' + json.dumps(points, ensure_ascii=False, indent=1) + ';\n')
    print('points:', len(points))


if __name__ == '__main__':
    main()
