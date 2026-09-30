"""Push new alerts to your phone/inbox. Every channel is optional and configured by env vars:

  NTFY_TOPIC            ntfy.sh topic name (install the ntfy app and subscribe to it) — simplest option
  NTFY_SERVER           defaults to https://ntfy.sh
  WEBHOOK_URL           Slack or Discord incoming webhook
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL_TO   email via SMTP (e.g. Gmail app password)
  ALERT_MIN_SEVERITY    "opportunity" (default: opportunities + warnings) or "info" (everything)
  SITE_URL              link included in notifications
"""
import json
import os
import smtplib
import urllib.request
from email.mime.text import MIMEText

ICON = {"opportunity": "🟢", "warning": "🔴", "info": "🔵"}


def _filter(alerts):
    include_info = os.environ.get("ALERT_MIN_SEVERITY", "opportunity").lower() == "info"
    return [a for a in alerts if a["severity"] != "info" or include_info]


def _post(url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def send(alerts, regime):
    alerts = _filter(alerts)
    if not alerts:
        print("notify: no new alerts to send")
        return
    site = os.environ.get("SITE_URL", "")
    lines = [f"{ICON.get(a['severity'], '•')} {a['title']}\n   {a['detail']}" for a in alerts]
    body = f"Market regime: {regime['label']} ({regime['score']:+d})\n\n" + "\n\n".join(lines)
    if site:
        body += f"\n\nDashboard: {site}"
    title = f"{len(alerts)} new market signal{'s' if len(alerts) != 1 else ''}"

    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        headers = {"Title": title.encode("utf-8").decode("latin-1", "ignore"), "Tags": "chart_with_upwards_trend"}
        if site:
            headers["Click"] = site
        try:
            _post(f"{server}/{topic}", body.encode("utf-8"), headers)
            print("notify: ntfy sent")
        except Exception as exc:
            print(f"notify: ntfy failed: {exc}")

    hook = os.environ.get("WEBHOOK_URL")
    if hook:
        text = f"*{title}*\n{body}"
        try:
            _post(hook, json.dumps({"text": text, "content": text[:1900]}).encode(), {"Content-Type": "application/json"})
            print("notify: webhook sent")
        except Exception as exc:
            print(f"notify: webhook failed: {exc}")

    host, to = os.environ.get("SMTP_HOST"), os.environ.get("ALERT_EMAIL_TO")
    if host and to:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[Market Signals] {title}"
        msg["From"] = os.environ.get("SMTP_USER", to)
        msg["To"] = to
        try:
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=30) as smtp:
                smtp.starttls()
                if os.environ.get("SMTP_USER"):
                    smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASS", ""))
                smtp.sendmail(msg["From"], [x.strip() for x in to.split(",")], msg.as_string())
            print("notify: email sent")
        except Exception as exc:
            print(f"notify: email failed: {exc}")
