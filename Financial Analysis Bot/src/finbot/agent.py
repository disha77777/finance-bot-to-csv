"""
Beginner-friendly financial analysis helpers.

What this file does:
- Fetch a web page (press release, article, filing)
- Extract readable text
- Find simple financial figures (revenue, net income, EPS, YoY)
- Build a short summary and a CSV-ready row

Public functions you can call:
- analyze(query, max_results): search the web, then analyze each result
- analyze_from_urls(urls): analyze specific URLs you pass in
- crawl_from_index(index_url, max_links): discover press-release links on an index page
"""

import json
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse, urljoin, quote_plus

import requests
from bs4 import BeautifulSoup
import trafilatura
from duckduckgo_search import DDGS


# ---------------------------
# Core helpers (simple)
# ---------------------------

def _normalize_url(url: str) -> str:
	"""Ensure a URL has a scheme (https) so requests can fetch it."""
	if not url:
		return url
	parsed = urlparse(url)
	if not parsed.scheme:
		return f"https://{url}"
	return url


def _fetch_html(url: str) -> Optional[str]:
	"""Download the raw HTML of a page. Returns None if it fails."""
	try:
		headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
		resp = requests.get(url, headers=headers, timeout=20)
		if resp.status_code != 200:
			return None
		return resp.text
	except Exception:
		return None


def _extract_text(url: str, html: Optional[str]) -> Optional[str]:
	"""Try to extract clean text using trafilatura; fall back to plain HTML text."""
	# Prefer trafilatura (handles boilerplate); fall back to visible text from HTML
	try:
		extracted = trafilatura.extract(trafilatura.fetch_url(url), include_comments=False, include_tables=False)
		if extracted:
			return extracted
	except Exception:
		pass
	if not html:
		return None
	try:
		soup = BeautifulSoup(html, "lxml")
		for tag in soup(["script", "style", "noscript", "template"]):
			tag.extract()
		text = soup.get_text(" ")
		text = re.sub(r"\s+", " ", text).strip()
		return text if text else None
	except Exception:
		return None


# ---------------------------
# Light figure extraction + summary
# ---------------------------

def _to_float(num_str: str) -> Optional[float]:
	"""Convert a number string like '1,234.56' into a float, or return None."""
	try:
		return float(num_str.replace(",", "").strip())
	except Exception:
		return None


def _parse_money(value: str) -> Optional[float]:
	"""Parse amounts like '$14.9 billion' into a numeric value in USD."""
	m = re.search(r"\$?\s*([0-9.,]+)\s*(billion|bn|million|mn|thousand|k)?", value, re.I)
	if not m:
		return None
	num = _to_float(m.group(1))
	if num is None:
		return None
	unit = (m.group(2) or '').lower()
	if unit in ("billion", "bn"):
		return num * 1_000_000_000
	if unit in ("million", "mn"):
		return num * 1_000_000
	if unit in ("thousand", "k"):
		return num * 1_000
	return num


def extract_financial_figures(text: str) -> Dict[str, Any]:
	"""Find simple financial figures in text using friendly regex patterns."""
	if not text:
		return {}
	text_norm = re.sub(r"\s+", " ", text)
	figs: Dict[str, Any] = {}
	# Simple patterns that match many press releases. These are intentionally basic.
	patterns = {
		"revenue": r"(?:total\s+)?revenue\s*(?:was|were|of|to)\s*([^\.\;\n]+)",
		"net_income": r"(?:gaap\s+)?net\s+income\s*(?:was|were|of|to)\s*([^\.\;\n]+)",
		"eps": r"earnings\s+per\s+share[^\.\n]*?\s(?:was|were|of|to)\s*([^\.\;\n]+)",
		"yoy": r"(?:year[- ]over[- ]year|YoY)[^0-9%]*([+\-]?[0-9.,]+\s*%)",
	}
	m = re.search(patterns["revenue"], text_norm, re.I)
	if m:
		val = _parse_money(m.group(1))
		if val is not None:
			figs["revenue"] = val
	m = re.search(patterns["net_income"], text_norm, re.I)
	if m:
		val = _parse_money(m.group(1))
		if val is not None:
			figs["net_income"] = val
	m = re.search(patterns["eps"], text_norm, re.I)
	if m:
		candidate = m.group(1).replace("$", "").split()[0]
		val = _to_float(candidate)
		if val is not None:
			figs["eps"] = val
	m = re.search(patterns["yoy"], text_norm, re.I)
	if m:
		pct = _to_float(m.group(1).replace("%", ""))
		if pct is not None:
			figs["yoy_percent"] = pct
	return figs


def compose_summary(title: Optional[str], figs: Dict[str, Any]) -> str:
	"""Make a short, human-readable one-line summary from detected figures."""
	parts: List[str] = []
	if title:
		parts.append(f"Report: {title}")
	if "revenue" in figs:
		parts.append(f"Revenue: ${figs['revenue']:,.0f}")
	if "net_income" in figs:
		parts.append(f"Net income: ${figs['net_income']:,.0f}")
	if "eps" in figs:
		parts.append(f"EPS: {figs['eps']:.2f}")
	if "yoy_percent" in figs:
		y = figs['yoy_percent']
		parts.append(f"YoY: {abs(y):.1f}% {'up' if y>=0 else 'down'}")
	return " | ".join(parts) if parts else "Summary: No explicit financial figures detected in the source text."


# ---------------------------
# Row assembly
# ---------------------------

def _build_row(url: str, title: Optional[str], text: Optional[str]) -> Dict[str, Any]:
	"""Create one CSV-ready dictionary row for a given page."""
	host = urlparse(url).netloc
	figs = extract_financial_figures(text or "")
	summary = compose_summary(title, figs)
	return {
		"title": title,
		"url": url,
		"site": host,
		"author": None,
		"date": None,
		"snippet": None,
		"language": None,
		"length_chars": len(text or ""),
		"revenue_usd": figs.get("revenue"),
		"net_income_usd": figs.get("net_income"),
		"eps": figs.get("eps"),
		"yoy_percent": figs.get("yoy_percent"),
		"guidance": None,
		"summary": summary,
	}


# ---------------------------
# Public API (preserved)
# ---------------------------

def analyze_from_urls(urls: List[str]) -> List[Dict[str, Any]]:
	"""Analyze specific URLs you provide and return CSV-ready rows."""
	rows: List[Dict[str, Any]] = []
	for u in urls:
		url = _normalize_url(u)
		html = _fetch_html(url)
		title = None
		if html:
			try:
				soup = BeautifulSoup(html, "lxml")
				title_tag = soup.find("title")
				title = title_tag.get_text(strip=True) if title_tag else None
			except Exception:
				title = None
		text = _extract_text(url, html)
		rows.append(_build_row(url, title, text))
	return rows


def analyze(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
	"""Search the web (DuckDuckGo) for a query, then analyze each result."""
	# Simpler search: use DDG HTML backend; return top N results
	links: List[str] = []
	try:
		with DDGS() as ddgs:
			for r in ddgs.text(query, max_results=max_results, safesearch="Off", backend="html"):
				href = _normalize_url(r.get("href"))
				if href:
					links.append(href)
	except Exception:
		pass
	if not links:
		return []
	return analyze_from_urls(links)


def _discover_press_release_links(index_url: str, max_links: int = 3) -> List[str]:
	"""Find likely press-release detail links on an index page (same site)."""
	try:
		html = _fetch_html(index_url)
		if not html:
			return []
		soup = BeautifulSoup(html, "lxml")
		candidates: List[str] = []
		for a in soup.find_all("a", href=True):
			href = a["href"].strip()
			text = a.get_text(" ", strip=True).lower()
			abs_url = urljoin(index_url, href)
			if re.search(r"press[-]?release|news[-]?release|financial-results|financial-results|earnings", href, re.I) or \
			   ("press release" in text or "financial results" in text or "earnings" in text):
				candidates.append(abs_url)
			if len(candidates) >= max_links:
				break
		return candidates
	except Exception:
		return []


def crawl_from_index(index_url: str, max_links: int = 5) -> List[Dict[str, Any]]:
	"""If you pass an index page, try to discover detail pages and analyze them."""
	links = _discover_press_release_links(index_url, max_links=max_links)
	return analyze_from_urls(links or [index_url])
