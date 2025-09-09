import os, time, math
from datetime import datetime, timedelta, timezone, date
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
import openai
import smtplib
from email.mime.text import MIMEText

# Alpaca setup
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame
API_KEY     = os.getenv("ALPACA_API_KEY")
API_SECRET  = os.getenv("ALPACA_API_SECRET")
TRADING_URL = os.getenv("ALPACA_BASE_URL")
DATA_URL    = "https://data.alpaca.markets"

#configuration
openai.api_key = os.getenv("OPENAI_API_KEY")
EMAIL_USER  = os.getenv("EMAIL_USER")
EMAIL_PASS  = os.getenv("EMAIL_PASS")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
RECIPIENT   = os.getenv("RECIPIENT")

trade_client = tradeapi.REST(API_KEY, API_SECRET, TRADING_URL, api_version='v2')
data_client  = tradeapi.REST(API_KEY, API_SECRET, DATA_URL,    api_version='v2')

USER_AGENT  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


#main
def load_tickers():
    assets = trade_client.list_assets()
    return [
        a.symbol for a in assets
        if a.status=='active'
        and a.tradable
        and a.marginable
        and a.shortable
        and a.exchange in ('NYSE','NASDAQ','AMEX')
        and a.symbol.isalpha()
    ]

def fetch_bars(symbol, days=60):
    """Fetch up to `days` of daily bars, require ≥2."""
    end_dt   = datetime.now(timezone.utc) - timedelta(minutes=15)
    start_dt = end_dt - timedelta(days=days)
    df = data_client.get_bars(
        symbol, TimeFrame.Day,
        start=start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end=  end_dt.  strftime("%Y-%m-%dT%H:%M:%SZ"),
        limit=days, feed="iex"
    ).df
    return df if (df is not None and len(df)>=2) else None

def find_ep():
    eps = []
    for sym in load_tickers():
        bars = fetch_bars(sym)
        if bars is None:
            continue
        df     = bars.reset_index()
        recent = df.iloc[-1]
        prev   = df.iloc[-2]

        o    = recent.open
        pc   = prev.close
        gap  = (o - pc)/pc*100 if pc else math.nan

        vol50 = df.volume.iloc[:-1].mean()
        volx  = recent.volume/vol50 if vol50 else math.nan

        high52 = df.high.max()
        prox   = recent.close/high52*100 if high52 else math.nan

        if gap>=5 and volx>=3 and prox>=90:
            eps.append({
                "symbol": sym,
                "open": o, "prev_close": pc,
                "gap": gap, "volx": volx, "prox": prox
            })
        time.sleep(0.05)
    return eps


#news
def get_finviz_news(ticker):
    """Return Finviz headlines from last 24h."""
    url  = f"https://finviz.com/quote.ashx?t={ticker}"
    resp = requests.get(url, headers={"User-Agent":USER_AGENT},timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text,"html.parser")
    tbl  = soup.find("table", class_="fullview-news-outer")
    out, now = [], datetime.now(timezone.utc)
    if not tbl:
        return out

    for row in tbl.find_all("tr"):
        raw = row.td.text.strip()
        try:
            dt = date_parser.parse(raw)
        except:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if now - dt <= timedelta(hours=24):
            out.append({
                "datetime": dt,
                "headline": row.a.text.strip(),
                "link":      row.a["href"],
            })
    return out

#AI summary using chatgpt
def summarise(ticker, news):
    """GPT-4: explain *why* each item drove an abnormal move."""
    system = (
        "You’re a senior equity analyst. For each news item, explain *why* "
        "it would cause an abnormal price or volume move. At the end, provide a brief summary of the key reasons for the stock's movement.\n"
    )
    user = (
        f"Ticker: {ticker}\nRecent news (last 24h):\n" +
        "\n".join(
            f"- {ni['datetime'].strftime('%Y-%m-%d %H:%M %Z')}: "
            f"{ni['headline']} ({ni['link']})"
            for ni in news
        )
    )
    resp = openai.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role":"system", "content":system},
            {"role":"user",   "content":user}
        ],
        max_tokens=1000,
        temperature=0.4
    )
    return resp.choices[0].message.content.strip()


#email
def send_email(subject, html_body):
    msg = MIMEText(html_body, "html")
    msg["From"]    = EMAIL_USER
    msg["To"]      = RECIPIENT
    msg["Subject"] = subject
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.send_message(msg)


# call all the functions 
def main():
    eps = find_ep()
    #build a summary table of EP stocks
    html = [
        "<h1 style='font-size:24px'>Episodic Pivot Report: {}</h1>".format(date.today()),
        "<table border='1' cellpadding='5' cellspacing='0'>",
        "<tr><th>Ticker</th><th>Open</th><th>PrevClose</th><th>Gap%</th>"
         "<th>Vol×</th><th>Prox%</th></tr>"
    ]
    for e in eps:
        html.append(
            "<tr>"
            f"<td>{e['symbol']}</td>"
            f"<td>{e['open']:.2f}</td>"
            f"<td>{e['prev_close']:.2f}</td>"
            f"<td>{e['gap']:.2f}%</td>"
            f"<td>{e['volx']:.2f}</td>"
            f"<td>{e['prox']:.2f}%</td>"
            "</tr>"
        )
    html.append("</table><br><hr><br>")

    #for each EP, fetch news&summarise
    for e in eps:
        sym = e["symbol"]
        news = get_finviz_news(sym)
        if not news:
            summ = "No significant news in the last 24h."
        else:
            summ = summarise(sym, news)
        #add section
        html.append(f"<h2>{sym}</h2>")
        #bold bullets 1.–9.
        summ_html = summ.replace("\n","<br>")
        for i in range(1,10):
            summ_html = summ_html.replace(f"{i}.", f"<strong>{i}.</strong>")
        html.append(f"<p>{summ_html}</p><hr>")
        time.sleep(0.5)

    body = "\n".join(html)
    send_email(f"Episodic Pivot & News {date.today()}", body)
    print("Done. Email sent.")

if __name__=="__main__":
    main()
