"""
Minimal Flask web app to chat with the finance bot.
Open http://127.0.0.1:5000 in your browser.
"""

from pathlib import Path
from typing import List
import sys
from io import StringIO

from flask import Flask, render_template, request, jsonify, Response
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from src.finbot.agent import analyze, analyze_from_urls

app = Flask(__name__, static_folder="static", template_folder="templates")


@app.get("/")
def index():
	"""Serve the chat UI page."""
	return render_template("index.html")


@app.post("/api/chat")
def chat_api():
	"""Simple JSON API: send message and optional URLs, get summaries and rows back."""
	data = request.get_json(silent=True) or {}
	message: str = data.get("message", "")
	urls: List[str] = data.get("urls") or []
	max_results: int = int(data.get("max_results", 8))
	if urls:
		rows = analyze_from_urls(urls)
	else:
		rows = analyze(message, max_results=max_results)
	df = pd.DataFrame(rows)
	summaries = df["summary"].dropna().tolist() if not df.empty else []
	return jsonify({
		"summaries": summaries,
		"rows": rows,
	})


@app.post("/api/chat_csv")
def chat_csv():
	"""Return a CSV built from the current chat request (message/urls)."""
	data = request.get_json(silent=True) or {}
	message: str = data.get("message", "")
	urls: List[str] = data.get("urls") or []
	max_results: int = int(data.get("max_results", 8))
	if urls:
		rows = analyze_from_urls(urls)
	else:
		rows = analyze(message, max_results=max_results)
	df = pd.DataFrame(rows)
	buf = StringIO()
	df.to_csv(buf, index=False)
	csv_bytes = buf.getvalue().encode("utf-8")
	return Response(csv_bytes, mimetype="text/csv", headers={
		"Content-Disposition": "attachment; filename=finance_results.csv"
	})


if __name__ == "__main__":
	app.run(host="127.0.0.1", port=5000, debug=True)
