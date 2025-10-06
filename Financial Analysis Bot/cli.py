"""
Command-line interface (CLI) for the Financial Analysis Bot.

Main commands:
- research: research a topic or URLs and write a CSV
- chat: ask a single-turn question or use an interactive chat REPL
"""

import csv
from pathlib import Path
from typing import Optional, List

import click
import pandas as pd

from src.finbot.agent import analyze, analyze_from_urls, crawl_from_index


def _rows_from_inputs(urls: Optional[List[str]], query_text: Optional[str], crawl: bool, max_crawl: int, max_results: int) -> List[dict]:
	"""Decide how to get rows based on either URLs (with optional crawl) or a search query."""
	if urls:
		if crawl:
			rows: List[dict] = []
			for u in urls:
				rows.extend(crawl_from_index(u, max_links=max_crawl))
			return rows
		return analyze_from_urls(urls)
	if query_text:
		return analyze(query_text, max_results=max_results)
	return []


def _write_csv(rows: List[dict], out: Path) -> int:
	"""Write rows to CSV and return the number of rows written."""
	df = pd.DataFrame(rows)
	df.to_csv(out, index=False, quoting=csv.QUOTE_MINIMAL)
	return len(df)


@click.group()
def cli() -> None:
	"""Top-level CLI group. Type `python cli.py --help` to see commands."""
	pass


@cli.command()
@click.argument("query", nargs=-1, required=False)
@click.option("--urls", multiple=True, help="One or more URLs to analyze directly; bypass web search")
@click.option("--crawl", is_flag=True, help="If a URL is an index page, discover and analyze top press-release links")
@click.option("--max-crawl", type=int, default=5, show_default=True, help="Max links to discover per index URL when --crawl is set")
@click.option("--max-results", type=int, default=10, show_default=True, help="Number of links to fetch for query-based search")
@click.option("--out", type=click.Path(path_type=Path), default=Path("results.csv"), show_default=True, help="Output CSV path")
def research(query: tuple[str, ...], urls: tuple[str, ...], crawl: bool, max_crawl: int, max_results: int, out: Path) -> None:
	"""Research a financial topic and export a CSV.

	Examples:
	- Query-based: python cli.py research "NVIDIA Q2 2025 earnings" --out results.csv
	- Direct URLs: python cli.py research --urls "https://example.com/press" --out results.csv
	- Crawl index: python cli.py research --urls "https://example.com/news" --crawl --max-crawl 3
	"""
	query_text = " ".join(query) if query else ""
	urls_list: Optional[List[str]] = list(urls) if urls else None
	rows = _rows_from_inputs(urls_list, query_text, crawl=crawl, max_crawl=max_crawl, max_results=max_results)
	if not rows:
		click.echo("No results found.")
		return
	count = _write_csv(rows, out)
	click.echo(f"Wrote {count} rows to {out}")


@cli.command()
@click.option("--message", help="Single-turn chat message to the finance bot")
@click.option("--urls", multiple=True, help="Optional URLs to ground the chat answer; bypass search")
@click.option("--max-results", type=int, default=8, show_default=True, help="Max links if searching the web")
@click.option("--out", type=click.Path(path_type=Path), required=False, help="Optional CSV path to write sources and summary")
def chat(message: Optional[str], urls: tuple[str, ...], max_results: int, out: Optional[Path]) -> None:
	"""Chat with the finance bot. Provide --message for single-turn or enter interactive mode."""
	def run_once(prompt: str) -> pd.DataFrame:
		urls_list: Optional[List[str]] = list(urls) if urls else None
		rows = _rows_from_inputs(urls_list, prompt, crawl=False, max_crawl=0, max_results=max_results)
		return pd.DataFrame(rows)

	if message:
		df = run_once(message)
		if df.empty:
			click.echo("No results found.")
			return
		summaries = df["summary"].dropna().tolist()
		click.echo("\n".join(summaries) if summaries else "No narrative could be composed from sources.")
		if out:
			df.to_csv(out, index=False, quoting=csv.QUOTE_MINIMAL)
			click.echo(f"Wrote {len(df)} rows to {out}")
		return

	click.echo("Finance Chatbot (type 'exit' to quit). Ask about companies, earnings, metrics...")
	while True:
		try:
			prompt = click.prompt("")
		except (EOFError, KeyboardInterrupt):
			click.echo("\nBye.")
			return
		if prompt.strip().lower() in {"exit", "quit"}:
			click.echo("Bye.")
			return
		df = run_once(prompt)
		if df.empty:
			click.echo("No results found.")
			continue
		summaries = df["summary"].dropna().tolist()
		click.echo("\n".join(summaries) if summaries else "No narrative could be composed from sources.")
		if out:
			df.to_csv(out, index=False, quoting=csv.QUOTE_MINIMAL)
			click.echo(f"Wrote {len(df)} rows to {out}")


if __name__ == "__main__":
	cli()
