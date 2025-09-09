**Episodic Pivot (EP) Stock Screener**

This project is a Python-based stock screener that automatically identifies Episodic Pivot (EP) setups in the US stock market. It combines price action, volume analysis, and proximity to highs with recent news scraping (via Finviz) and AI-powered summaries (using OpenAI’s GPT). The final results are delivered as a neatly formatted daily email report.

🔑 **Key Features**
Scans all major US exchange tickers via Alpaca API
Detects Episodic Pivot candidates based on:
- Price gap %
- Volume multiples
- Proximity to 52-week highs
Scrapes recent headlines from Finviz
Summarizes news with GPT-4 for trading insights
Sends an HTML email report with tables and summaries

⚠️ **Important Note on Confidentiality**
This script requires access to API keys and email credentials.
👉 For security reasons, make sure to store all **sensitive information** (Alpaca API keys, OpenAI API key, SMTP/email credentials, recipient address, etc.) in your **environment variables** rather than hardcoding them in the script.
