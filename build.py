#!/usr/bin/env python3
"""
build.py — Parse all newsletter XML files and generate data.json for the site.

Usage: python build.py
"""

import json
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

ANALYTICS_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(ANALYTICS_DIR, "data.json")
FILENAME_PATTERN = re.compile(r'^([a-z]+)-(\d{4}-\d{2}-\d{2})\.xml$')


def clean_url_for_display(raw_url):
    """Return a human-readable version of a URL with UTM params stripped."""
    try:
        parsed = urlparse(raw_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in params.items() if not k.startswith('utm_')}
        clean_query = urlencode(filtered, doseq=True)
        clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path,
                            parsed.params, clean_query, parsed.fragment))
        # Show host + path only, strip trailing ?
        display = parsed.netloc + parsed.path
        if filtered:
            display += '?' + clean_query
        return display.rstrip('/')
    except Exception:
        return raw_url


def get_text(element, tag, default=''):
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return default


def get_int(element, tag, default=0):
    try:
        return int(get_text(element, tag, str(default)))
    except ValueError:
        return default


def parse_xml_file(filepath, filename):
    """Parse a single XML file and return a mailing dict, or None on error."""
    match = FILENAME_PATTERN.match(filename)
    if not match:
        return None

    list_type = match.group(1)
    date_str = match.group(2)
    year = int(date_str[:4])
    month = int(date_str[5:7])
    semester = 'Spring' if month <= 6 else 'Fall'

    try:
        tree = ET.parse(filepath)
    except ET.ParseError:
        # File may have HTML wrapper — strip it and re-parse
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        # Extract just the XML portion
        start = content.find('<trackingsummarydata>')
        end = content.find('</trackingsummarydata>') + len('</trackingsummarydata>')
        if start == -1 or end == -1:
            print(f"  WARNING: Could not parse {filename}")
            return None
        try:
            root = ET.fromstring(content[start:end])
        except ET.ParseError as e:
            print(f"  WARNING: Parse error in {filename}: {e}")
            return None
    else:
        root = tree.getroot()
        # If root is html/body, find trackingsummarydata
        if root.tag != 'trackingsummarydata':
            root = root.find('.//trackingsummarydata')
            if root is None:
                print(f"  WARNING: No trackingsummarydata in {filename}")
                return None

    mailed = get_int(root, 'mailed')
    unique_opens = get_int(root, 'unique_opens')
    unique_clicks = get_int(root, 'unique_clicks')
    total_clicks = get_int(root, 'total_clicks')

    open_rate = round(unique_opens / mailed * 100, 1) if mailed else 0
    click_rate = round(unique_clicks / mailed * 100, 1) if mailed else 0

    # Parse URLs — XML mislabels clicks as <opens>/<uniqueopens>
    urls = []
    url_elements = root.findall('urls')
    # The XML has a single <urls> block with interleaved <opens>, <uniqueopens>, <url> tags
    if url_elements:
        urls_el = url_elements[0]
        opens_els = urls_el.findall('opens')
        uniqueopens_els = urls_el.findall('uniqueopens')
        url_els = urls_el.findall('url')
        page_title_els   = urls_el.findall('page_title')
        page_summary_els = urls_el.findall('page_summary')
        for i, url_el in enumerate(url_els):
            raw_url = url_el.text.strip() if url_el.text else ''
            clicks = int(opens_els[i].text) if i < len(opens_els) and opens_els[i].text else 0
            unique = int(uniqueopens_els[i].text) if i < len(uniqueopens_els) and uniqueopens_els[i].text else 0
            page_title   = page_title_els[i].text.strip()   if i < len(page_title_els)   and page_title_els[i].text   else None
            page_summary = page_summary_els[i].text.strip() if i < len(page_summary_els) and page_summary_els[i].text else None
            if raw_url:
                urls.append({
                    'url': raw_url,
                    'display': clean_url_for_display(raw_url),
                    'page_title': page_title,
                    'page_summary': page_summary,
                    'total_clicks': clicks,
                    'unique_clicks': unique,
                })
    urls.sort(key=lambda x: x['total_clicks'], reverse=True)

    return {
        'filename': filename,
        'type': list_type,
        'date': date_str,
        'year': year,
        'semester': semester,
        'subject': get_text(root, 'subject'),
        'mailed': mailed,
        'unique_opens': unique_opens,
        'opens': get_int(root, 'opens'),
        'open_rate': open_rate,
        'unique_clicks': unique_clicks,
        'total_clicks': total_clicks,
        'click_rate': click_rate,
        'unsubs': get_int(root, 'unsubs'),
        'urls': urls,
    }


def main():
    mailings = []
    xml_files = sorted([
        f for f in os.listdir(ANALYTICS_DIR)
        if FILENAME_PATTERN.match(f)
    ])

    print(f"Found {len(xml_files)} XML files.")
    for filename in xml_files:
        filepath = os.path.join(ANALYTICS_DIR, filename)
        result = parse_xml_file(filepath, filename)
        if result:
            mailings.append(result)
            print(f"  OK  {filename}")
        else:
            print(f"  --  {filename} (skipped)")

    # Sort newest-first
    mailings.sort(key=lambda x: x['date'], reverse=True)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(mailings, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(mailings)} mailings to data.json")


if __name__ == '__main__':
    main()
