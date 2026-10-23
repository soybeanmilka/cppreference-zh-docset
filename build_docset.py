# -*- coding: utf-8 -*-
"""Build a Zeal / Dash / Velocity docset out of an offline HTML book.

Written for the Chinese cppreference offline book produced by
https://github.com/myfreeer/cppreference2mshelp, but the two knobs that
matter are exposed as CLI options (--root / --site), so it should work for
other devhelp-style HTML books too.

Why a converter is needed at all:

  * The official Zeal feed (api.zealdocs.org / kapeli.com) ships no Chinese
    C++ docset. The offline Chinese HTML book is just a plain directory tree
    meant for a browser: there is no docSet.dsidx, so Zeal finds nothing.
  * The devhelp2 index that comes with the book is useless: every one of its
    14342 links is a literal "404" placeholder.
  * Relative links in the book carry redundant levels
    (`../../../../zh.cppreference.com/../../../../common/x.css`) and operator
    pages are URL-encoded (`operator%3D.html` while the file on disk is
    `operator=.html`). Dropped in as-is, styles, images and cross-references
    all break.

Usage:

    python build_docset.py html-book.tar.xz ./out
    python build_docset.py html-book.tar.xz ./out --name "My Docs" --site zh.cppreference.com

Result: ./out/中文C++参考手册.docset -- copy it into Zeal's docsets folder
(Windows: %LOCALAPPDATA%\\Zeal\\Zeal\\docsets) and restart Zeal.
"""

import argparse
import collections
import io
import os
import plistlib
import re
import shutil
import sqlite3
import sys
import tarfile
import urllib.parse

# Windows consoles default to GBK and blow up on the Chinese output.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ASSET_EXT = (
    ".css", ".js", ".png", ".svg", ".gif", ".ico",
    ".jpg", ".jpeg", ".webp", ".ttf", ".woff", ".woff2", ".eot",
)
ATTR = re.compile(r'(href|src)="([^"]+)"')
TAG = re.compile(r"<[^>]+>")
HTML_HREF = re.compile(r'href="([^"]*\.html[^"]*)"')


def clean(s):
    """Strip tags and collapse whitespace."""
    return re.sub(r"\s+", " ", TAG.sub("", s)).strip()


class DocsetBuilder:
    def __init__(self, tar_path, dest_dir, name, site, root, index_page):
        self.tar_path = tar_path
        self.dest_dir = dest_dir
        self.name = name
        self.site = site
        self.root = root
        self.index_page = index_page
        self.docset = os.path.join(dest_dir, name)
        self.res = os.path.join(self.docset, "Contents", "Resources")
        self.docs = os.path.join(self.res, "Documents")
        # Where the book's own tree is mounted inside Documents. Pages live in
        # <docs>/<site>/..., so `../../../common/x.css` from
        # <site>/cpp/container/ lands on <docs>/common/ -- the book's `common`
        # sibling directory therefore has to sit flat under <docs>.
        self.site_root = os.path.join(self.docs, site)
        self.common_prefix = os.path.dirname(root) if "/" in root else ""

    # ---------------------------------------------------------------- 1. unpack
    def unpack(self):
        if os.path.isdir(self.docset):
            shutil.rmtree(self.docset)
        os.makedirs(self.docs, exist_ok=True)
        tar = tarfile.open(self.tar_path, "r:*")
        files = [m for m in tar.getmembers() if m.isfile()]

        prefix = self.root.rstrip("/") + "/"
        pages = [m for m in files if m.name.startswith(prefix) and m.name.endswith(".html")]
        book_files = [m for m in files if m.name.startswith(prefix)]
        shared = []
        if self.common_prefix:
            shared_prefix = self.common_prefix + "/"
            shared = [
                m for m in files
                if m.name.startswith(shared_prefix) and not m.name.startswith(prefix)
            ]

        for m in shared:
            rel = m.name[len(shared_prefix):]
            dst = os.path.join(self.docs, rel.replace("/", os.sep))
            self._write(tar, m, dst)
        for m in book_files:
            rel = m.name[len(prefix):]
            dst = os.path.join(self.site_root, rel.replace("/", os.sep))
            self._write(tar, m, dst)

        print(f"[1/4] unpacked: {len(pages)} html pages, {len(shared)} shared assets")
        return tar, pages

    @staticmethod
    def _write(tar, member, dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(tar.extractfile(member).read())

    # --------------------------------------------------------------- 2. index
    def build_index(self, tar, pages):
        db = os.path.join(self.res, "docSet.dsidx")
        os.makedirs(self.res, exist_ok=True)
        if os.path.exists(db):
            os.remove(db)
        con = sqlite3.connect(db)
        con.execute(
            "CREATE TABLE searchIndex("
            "id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);"
        )
        con.execute("CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);")

        rows = []
        for m in pages:
            rel = m.name[len(self.root.rstrip("/")) + 1:]
            txt = tar.extractfile(m).read().decode("utf-8", "replace")
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", txt, re.S)
            title = clean(h1.group(1)) if h1 else ""
            if not title:
                tm = re.search(r"<title>(.*?)</title>", txt, re.S)
                title = clean(tm.group(1)) if tm else rel.rsplit("/", 1)[-1][:-5]
            # cppreference writes `std:: vector` in some h1s
            title = title.replace(":: ", "::")
            docpath = f"{self.site}/{rel}"
            leaf = rel.rsplit("/", 1)[-1]
            typ = "Operator" if leaf.startswith("operator") else "Guide"
            rows.append((title, typ, docpath))
            # section-level anchors, so "std::vector › 迭代器失效" is searchable
            for hh in re.finditer(r"<(h2|h3)[^>]*>(.*?)</\1>", txt, re.S):
                sec = clean(hh.group(2))
                if not sec or len(sec) > 60 or sec in ("导航", "参阅"):
                    continue
                rows.append((f"{title} › {sec}", "Section", docpath))

        con.executemany(
            "INSERT OR IGNORE INTO searchIndex(name,type,path) VALUES (?,?,?)", rows
        )
        con.commit()
        total = con.execute("select count(*) from searchIndex").fetchone()[0]
        con.close()
        kinds = collections.Counter(t for _, t, _ in rows).most_common()
        print(f"[2/4] indexed {total} entries {kinds}")

    # --------------------------------------------------------------- 3. links
    def fix_links(self):
        img_by_name = collections.defaultdict(list)
        for dirpath, _, files in os.walk(self.docs):
            if "images" in dirpath.lower():
                for f in files:
                    img_by_name[f].append(os.path.join(dirpath, f))

        page_by_base = {}
        for dirpath, _, files in os.walk(self.site_root):
            for f in files:
                if f.endswith(".html"):
                    page_by_base.setdefault(f, os.path.join(dirpath, f))

        def site_path(url):
            """Rewind any flavour of site URL back to a site-relative path."""
            for needle, skip in (
                ("/" + self.site + "/", len(self.site) + 2),
                (self.site + "/", len(self.site) + 1),
            ):
                i = url.find(needle)
                if i >= 0:
                    return url[i + skip:]
            if "://" in url or url.startswith("//"):
                return None
            return url

        changed = 0
        for dirpath, _, files in os.walk(self.docs):
            for f in files:
                if not f.endswith(".html"):
                    continue
                path = os.path.join(dirpath, f)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                original = text
                prefix = os.path.relpath(self.docs, dirpath).replace(os.sep, "/")
                if prefix == ".":
                    prefix = ""

                def repl(match, dirpath=dirpath, prefix=prefix):
                    attr, url = match.group(1), match.group(2)
                    if url.startswith(("#", "mailto:", "javascript:", "data:")):
                        return match.group(0)
                    sp = site_path(url)
                    if sp is None:  # genuine external link, leave it alone
                        return match.group(0)
                    frag = ""
                    if "#" in sp:
                        sp, frag = sp.split("#", 1)
                        frag = "#" + frag
                    sp = sp.split("?")[0]
                    low = sp.lower()
                    new = None

                    if self.common_prefix and low.startswith(self.common_prefix + "/"):
                        # shared asset: recompute from the Documents root
                        new = (prefix + "/" if prefix else "") + sp + frag
                    elif low.endswith(ASSET_EXT):
                        # `File:xxx.svg` refs, match by file name inside images/<hash>/
                        name = urllib.parse.unquote(sp.rsplit("/", 1)[-1])
                        cand = (
                            img_by_name.get(name)
                            or img_by_name.get(name.replace(" ", "_"))
                        )
                        if cand:
                            new = os.path.relpath(cand[0], dirpath).replace(os.sep, "/") + frag
                    elif low.endswith(".html"):
                        base = sp.rsplit("/", 1)[-1]
                        # operator pages are URL-encoded in hrefs
                        # (operator%3D.html) but plain on disk (operator=.html)
                        dec = urllib.parse.unquote(sp)
                        target = page_by_base.get(base) or page_by_base.get(
                            dec.rsplit("/", 1)[-1]
                        )
                        if target is None:
                            for candidate in (sp, dec):
                                nxt = os.path.normpath(
                                    os.path.join(dirpath, candidate.replace("/", os.sep))
                                )
                                if os.path.exists(nxt):
                                    target = nxt
                                    break
                        if target:
                            new = os.path.relpath(target, dirpath).replace(os.sep, "/") + frag

                    if new is None:
                        return match.group(0)
                    return f'{attr}="{new}"'

                text = ATTR.sub(repl, text)

                def repl2(match, dirpath=dirpath):
                    """Second pass: double-encoded links (operator%2522%2522i)."""
                    url = match.group(1)
                    if "%25" not in url:
                        return match.group(0)
                    dec = urllib.parse.unquote(url)
                    target = os.path.normpath(
                        os.path.join(dirpath, dec.split("#")[0].replace("/", os.sep))
                    )
                    return f'href="{dec}"' if os.path.exists(target) else match.group(0)

                text = HTML_HREF.sub(repl2, text)

                if text != original:
                    with open(path, "w", encoding="utf-8", newline="") as fh:
                        fh.write(text)
                    changed += 1
        print(f"[3/4] rewrote links in {changed} pages")

    # ---------------------------------------------------------------- 4. finsh
    def finish(self):
        info = {
            "CFBundleIdentifier": "cppreference-zh-cn",
            "CFBundleName": self.name.replace(".docset", ""),
            "DocSetPlatformFamily": "cppreference-zh",
            "isDashDocset": True,
            "dashIndexFilePath": f"{self.site}/{self.index_page}",
            "isJavaScriptEnabled": False,
        }
        os.makedirs(os.path.join(self.docset, "Contents"), exist_ok=True)
        with open(os.path.join(self.docset, "Contents", "Info.plist"), "wb") as fh:
            plistlib.dump(info, fh)
        size = sum(
            os.path.getsize(os.path.join(d, x))
            for d, _, fx in os.walk(self.docset)
            for x in fx
        )
        print(f"[4/4] done: {size / 1048576:.1f} MB -> {self.docset}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Convert an offline HTML book (tar.xz) into a Zeal/Dash docset."
    )
    ap.add_argument("tarball", help="html book archive (.tar.xz / .tar.gz / .tgz)")
    ap.add_argument("outdir", help="output directory, the .docset goes inside it")
    ap.add_argument(
        "--name", default="中文C++参考手册.docset",
        help="docset folder name (default: 中文C++参考手册.docset)",
    )
    ap.add_argument(
        "--site", default="zh.cppreference.com",
        help="folder name the book tree is mounted under (default: zh.cppreference.com)",
    )
    ap.add_argument(
        "--root", default="reference/zh",
        help="path of the book root inside the archive (default: reference/zh)",
    )
    ap.add_argument(
        "--index-page", default="cpp.html",
        help="page opened by default (default: cpp.html)",
    )
    args = ap.parse_args(argv)

    builder = DocsetBuilder(
        args.tarball, args.outdir, args.name, args.site, args.root, args.index_page
    )
    tar, pages = builder.unpack()
    builder.build_index(tar, pages)
    tar.close()
    builder.fix_links()
    builder.finish()


if __name__ == "__main__":
    main()
