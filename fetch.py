#!/usr/bin/env python3
"""
Fetch tennis news feeds, pull out injury / MTO events, save to events.json.
Runs in GitHub Actions on a schedule. Uses only the Python standard library.
"""
import hashlib
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape

from extractor import extract, player_key, strip_source

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = ROOT
EVENTS_FILE = os.path.join(DATA_DIR, "events.json")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")
FEEDS_FILE = os.path.join(ROOT, "feeds.json")

MAX_AGE_DAYS = 30
MAX_EVENTS = 800
MERGE_WINDOW_H = 12
UA = "Mozilla/5.0 (compatible; TennisWatch/1.0; personal use)"


def now():
    return datetime.now(timezone.utc)


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def local(tag):
    return tag.rsplit("}", 1)[-1]


def clean(html):
    t = unescape(html or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def child_text(el, *names):
    for c in el:
        if local(c.tag) in names and (c.text or "").strip():
            return c.text.strip()
    return ""


def parse_feed(data):
    """Handles RSS (<item>) and Atom (<entry>)."""
    root = ET.fromstring(data)
    out = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = clean(child_text(el, "title"))
        link = child_text(el, "link")
        if not link:
            for c in el:
                if local(c.tag) == "link" and c.get("href"):
                    link = c.get("href")
                    break
        if not title:
            continue
        out.append({
            "title": title,
            "link": link,
            "summary": clean(child_text(el, "description", "summary", "content")),
            "published": parse_date(child_text(el, "pubDate", "published", "updated", "date")),
            "source": clean(child_text(el, "source")),
        })
    return out


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def load_feeds():
    with open(FEEDS_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def find_match(events, ev):
    """Same story already stored? (same headline, or same player+type within a few hours)"""
    for old in events:
        if old["id"] == ev["id"] or norm(old["headline"]) == norm(ev["headline"]):
            return old
        if (ev["player"] != "Unknown" and player_key(old["player"]) == player_key(ev["player"])
                and old["type"] == ev["type"]):
            gap = abs(parse_iso(old["published"]) - parse_iso(ev["published"]))
            if gap < timedelta(hours=MERGE_WINDOW_H):
                return old
    return None


def refresh(events):
    """Re-check stored events with the current extractor, so improvements also clean up old entries."""
    out = []
    for e in sorted(events, key=lambda x: x["published"], reverse=True):
        res = extract(e["headline"], e.get("snippet", ""), clean=True)
        if not res:
            continue
        e.update({"player": res["player"], "type": res["type"],
                  "reason": res["reason"], "confidence": res["confidence"]})
        old = find_match(out, e)
        if old:
            for s in e.get("sources", []):
                if s not in old["sources"]:
                    old["sources"].append(s)
            continue
        out.append(e)
    return out


def same(a, b):
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")


def main():
    feeds = load_feeds()
    old_file = load_json(EVENTS_FILE, {"events": []})
    events = list(old_file.get("events", []))
    old_events_snapshot = json.loads(json.dumps(events))
    events = refresh(events)

    cutoff = now() - timedelta(days=MAX_AGE_DAYS)
    status, failed, added = [], 0, 0

    for feed in feeds:
        name, url = feed["name"], feed["url"]
        try:
            items = parse_feed(get(url))
            status.append({"name": name, "ok": True, "error": ""})
        except Exception as e:  # one broken feed must not stop the rest
            failed += 1
            status.append({"name": name, "ok": False, "error": str(e)[:120]})
            print(f"[fail] {name}: {e}")
            continue

        new_here = 0
        for it in items:
            published = it["published"] or now()
            if published < cutoff:
                continue
            res = extract(it["title"], it["summary"])
            if not res:
                continue
            headline = strip_source(it["title"])
            source = it["source"] or (it["title"].rsplit(" - ", 1)[-1] if " - " in it["title"] else name)
            ev = {
                "id": hashlib.sha1((it["link"] or it["title"]).encode("utf-8")).hexdigest()[:12],
                "player": res["player"],
                "type": res["type"],
                "reason": res["reason"],
                "confidence": res["confidence"],
                "headline": headline,
                "snippet": it["summary"][:240] if norm(it["summary"]) != norm(it["title"]) else "",
                "url": it["link"],
                "sources": [source],
                "published": iso(published),
                "found_at": iso(now()),
            }
            old = find_match(events, ev)
            if old:
                if source not in old["sources"]:
                    old["sources"].append(source)
                continue
            events.append(ev)
            added += 1
            new_here += 1
        print(f"[ok] {name}: {len(items)} items, {new_here} new events")

    events = [e for e in events if parse_iso(e["published"]) >= cutoff]
    events.sort(key=lambda e: e["published"], reverse=True)
    events = events[:MAX_EVENTS]

    # Only rewrite files when something changed, so the repo (and the site) only update on real news.
    if not same(events, old_events_snapshot):
        write_json(EVENTS_FILE, {"generated_at": iso(now()), "events": events})
        print(f"Saved {len(events)} events ({added} new)")
    else:
        print("No new events")

    if not same(status, load_json(STATUS_FILE, {}).get("feeds")):
        write_json(STATUS_FILE, {"feeds": status})

    if feeds and failed == len(feeds):
        print("All feeds failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
