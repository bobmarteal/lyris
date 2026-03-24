#!/usr/bin/env python3
"""
rename.py — Rename raw Lyris XML exports and enrich URLs with page titles and summaries.

Usage: python rename.py [directory]

Two steps:
  1. Rename any .html / .xml.html Lyris exports to type-YYYY-MM-DD.xml
  2. Fetch HTML <title> and meta description for any URL missing enrichment in any XML file
"""

import os
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
import urllib.request
from html.parser import HTMLParser

ALREADY_NAMED = re.compile(r'^([a-z]+)-\d{4}-\d{2}-\d{2}\.xml$')


# ---------------------------------------------------------------------------
# Page info fetching
# ---------------------------------------------------------------------------

class PageInfoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = None
        self.summary = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == 'title':
            self._in_title = True
            self.title = ''
        elif tag == 'meta':
            attrs_dict = dict(attrs)
            content = attrs_dict.get('content', '').strip()
            prop = attrs_dict.get('property', '').lower()
            name = attrs_dict.get('name', '').lower()
            if prop == 'og:description' and content:
                self.summary = content
            elif name == 'description' and content and not self.summary:
                self.summary = content

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or '') + data


def fetch_page_info(url, timeout=8):
    """Fetch a URL and return (title, summary), or ('Not Available', 'Not Available') on failure."""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return 'Not Available', 'Not Available'
            content_type = resp.headers.get('Content-Type', '')
            if 'html' not in content_type.lower():
                return 'Not Available', 'Not Available'
            html = resp.read(32768).decode('utf-8', errors='ignore')
        parser = PageInfoParser()
        parser.feed(html)
        title = (parser.title or '').strip() or 'Not Available'
        summary = (parser.summary or '').strip()
        if len(summary) > 250:
            summary = summary[:247] + '...'
        return title, summary or 'Not Available'
    except Exception:
        return 'Not Available', 'Not Available'


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def normalize_xml(xml_chunk):
    """Lowercase all tag names and escape bare & characters."""
    xml_chunk = re.sub(r'</?[A-Za-z][A-Za-z0-9_-]*', lambda m: m.group().lower(), xml_chunk)
    xml_chunk = re.sub(r'&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)', '&amp;', xml_chunk)
    return xml_chunk


def extract_xml_root(filepath):
    """Parse a Lyris file (HTML-wrapped or plain XML). Returns root element or None."""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    lower = content.lower()
    start = lower.find('<trackingsummarydata>')
    end   = lower.find('</trackingsummarydata>')
    if start == -1 or end == -1:
        return None
    xml_chunk = normalize_xml(content[start:end + len('</trackingsummarydata>')])
    try:
        return ET.fromstring(xml_chunk)
    except ET.ParseError:
        return None


def extract_fields(filepath):
    """Return (list_value, start_date_str) from a Lyris file."""
    root = extract_xml_root(filepath)
    if root is None:
        return None, None
    list_el = root.find('list')
    date_el = root.find('start_date')
    list_val = list_el.text.strip() if list_el is not None and list_el.text else None
    date_val = date_el.text.strip().split(' ')[0] if date_el is not None and date_el.text else None
    return list_val, date_val


def derive_type(list_val):
    """'as-faculty-update-l' -> 'faculty'"""
    if not list_val:
        return None
    t = list_val
    if t.startswith('as-'):
        t = t[3:]
    if t.endswith('-update-l'):
        t = t[:-9]
    return t


def enrich_xml_file(filepath):
    """
    Add <page_title> and <page_summary> after each <url> if not already present.
    Rewrites the file as clean XML. Returns count of URLs enriched.
    """
    root = extract_xml_root(filepath)
    if root is None:
        return 0

    urls_el = root.find('urls')
    if urls_el is None:
        return 0

    # Already has titles — summaries handled by enrich_summaries_file
    if urls_el.find('page_title') is not None:
        return 0

    children = list(urls_el)
    url_indices = [i for i, el in enumerate(children) if el.tag == 'url']
    if not url_indices:
        return 0

    # Fetch titles and summaries (forward order, with polite delay)
    fetched = []
    for idx in url_indices:
        raw_url = (children[idx].text or '').strip()
        print(f'      → {raw_url[:75]}')
        if raw_url:
            title, summary = fetch_page_info(raw_url)
        else:
            title, summary = 'Not Available', 'Not Available'
        print(f'         {title[:75]}')
        fetched.append((idx, title, summary))
        time.sleep(0.4)

    # Insert <page_title> and <page_summary> after each <url> — reverse order preserves indices
    for idx, title, summary in reversed(fetched):
        summary_el = ET.Element('page_summary')
        summary_el.text = summary
        title_el = ET.Element('page_title')
        title_el.text = title
        urls_el.insert(idx + 1, title_el)
        urls_el.insert(idx + 2, summary_el)

    # Write clean XML (replaces HTML-wrapped original)
    ET.indent(root, space='    ')
    ET.ElementTree(root).write(filepath, encoding='utf-8', xml_declaration=True)
    return len(fetched)


def enrich_summaries_file(filepath):
    """
    Add <page_summary> to files that already have <page_title> but lack summaries.
    Returns count of summaries fetched.
    """
    root = extract_xml_root(filepath)
    if root is None:
        return 0

    urls_el = root.find('urls')
    if urls_el is None:
        return 0

    children = list(urls_el)

    # Find URL elements whose page_title has no following page_summary
    to_fetch = []  # list of (title_child_index, raw_url)
    for i, el in enumerate(children):
        if el.tag != 'url':
            continue
        raw_url = (el.text or '').strip()
        title_idx = None
        has_summary = False
        for j in range(i + 1, len(children)):
            if children[j].tag == 'url':
                break
            if children[j].tag == 'page_title':
                title_idx = j
            if children[j].tag == 'page_summary':
                has_summary = True
        if title_idx is not None and not has_summary:
            to_fetch.append((title_idx, raw_url))

    if not to_fetch:
        return 0

    # Fetch summaries (forward order, with polite delay)
    fetched = []
    for title_idx, raw_url in to_fetch:
        print(f'      → {raw_url[:75]}')
        _, summary = fetch_page_info(raw_url) if raw_url else ('', 'Not Available')
        print(f'         {summary[:75]}')
        fetched.append((title_idx, summary))
        time.sleep(0.4)

    # Insert <page_summary> after each <page_title> — reverse order preserves indices
    for title_idx, summary in reversed(fetched):
        summary_el = ET.Element('page_summary')
        summary_el.text = summary
        urls_el.insert(title_idx + 1, summary_el)

    ET.indent(root, space='    ')
    ET.ElementTree(root).write(filepath, encoding='utf-8', xml_declaration=True)
    return len(fetched)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    directory = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(directory, 'temporary')
    os.makedirs(temp_dir, exist_ok=True)

    # ── Step 1: Rename raw Lyris exports ────────────────────────────────────
    candidates = sorted([
        f for f in os.listdir(directory)
        if (f.endswith('.html') or f.endswith('.xml.html'))
        and not ALREADY_NAMED.match(f)
        and os.path.isfile(os.path.join(directory, f))
    ])

    renamed, skipped = [], []

    for filename in candidates:
        filepath = os.path.join(directory, filename)
        list_val, date_val = extract_fields(filepath)
        list_type = derive_type(list_val)

        if not list_type or not date_val:
            skipped.append((filename, 'could not parse list or date'))
            continue

        new_name = f'{list_type}-{date_val}.xml'
        dest = os.path.join(directory, new_name)

        if os.path.exists(dest):
            shutil.copy2(filepath, os.path.join(temp_dir, filename))
            os.remove(filepath)
            skipped.append((filename, f'DUPLICATE — {new_name} already exists, original archived to temporary/'))
            continue

        shutil.copy2(filepath, os.path.join(temp_dir, filename))
        shutil.copy2(filepath, dest)
        os.remove(filepath)
        renamed.append((filename, new_name))

    if renamed:
        print(f'Renamed {len(renamed)} file(s):')
        for old, new in renamed:
            print(f'  {old}  →  {new}')
    else:
        print('No files to rename.')

    duplicates    = [(n, r) for n, r in skipped if r.startswith('DUPLICATE')]
    other_skipped = [(n, r) for n, r in skipped if not r.startswith('DUPLICATE')]

    if duplicates:
        print(f'\n*** DUPLICATE file(s) — already in the directory, nothing changed:')
        for name, reason in duplicates:
            print(f'  {name}  ({reason})')

    if other_skipped:
        print(f'\nSkipped {len(other_skipped)} file(s):')
        for name, reason in other_skipped:
            print(f'  {name}  ({reason})')

    # ── Step 2: Enrich all XML files with page titles and summaries ───────────
    xml_files = sorted([
        f for f in os.listdir(directory)
        if ALREADY_NAMED.match(f) and os.path.isfile(os.path.join(directory, f))
    ])

    needs_titles    = []
    needs_summaries = []
    for filename in xml_files:
        root = extract_xml_root(os.path.join(directory, filename))
        if root is None:
            continue
        urls_el = root.find('urls')
        if urls_el is None:
            continue
        if urls_el.find('page_title') is None:
            needs_titles.append(filename)
        elif urls_el.find('page_summary') is None:
            needs_summaries.append(filename)

    if not needs_titles and not needs_summaries:
        print('\nAll files already have page titles and summaries.')
        return

    if needs_titles:
        print(f'\nFetching page titles and summaries for {len(needs_titles)} file(s)...')
        for filename in needs_titles:
            print(f'  {filename}')
            count = enrich_xml_file(os.path.join(directory, filename))
            print(f'    {count} URL(s) enriched.')

    if needs_summaries:
        print(f'\nBackfilling summaries for {len(needs_summaries)} file(s)...')
        for filename in needs_summaries:
            print(f'  {filename}')
            count = enrich_summaries_file(os.path.join(directory, filename))
            print(f'    {count} summary/summaries added.')


if __name__ == '__main__':
    main()
