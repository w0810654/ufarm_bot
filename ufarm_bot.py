#!/usr/bin/env python3
"""
alias bot
"""

import asyncio
import random
import string
import logging
import os
from datetime import datetime, timedelta
from io import BytesIO

from playwright.async_api import async_playwright
from telegram import Bot, Update, InputMediaPhoto
from telegram.ext import (
    Application,
    MessageHandler,
    ChatMemberHandler,
    filters,
    ContextTypes,
)
from telegram.error import TelegramError

# ─────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────
BOT_TOKEN             = os.environ.get("BOT_TOKEN", "8979778871:AAE_E7ppuK-2hJIsuln6JcNd_KHVV1t-XtI")
POST_INTERVAL_MINUTES = int(os.environ.get("POST_INTERVAL_MINUTES", "30"))
# ─────────────────────────────────────────────────────────────────

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

known_channels: set[int] = set()
last_message_ids: dict[int, list[int]] = {}  # Maps channel_id → list of last message_ids

# ─── Name pools (grouped by ethnicity so first + last names stay consistent) ───
NAME_GROUPS = {
    "igbo": {
        "first": [
            "CHUKWUEMEKA","ADAEZE","TOCHUKWU","AMAKA","CHIDINMA","EMEKA","IFEANYI",
            "KINGSLEY","NGOZI","OBIORA","UCHE","CHIDI","IFEOMA","KELECHI","CHIAMAKA",
            "OBINNA","EKENE","CHINYERE","CHINAGOROM","ONYEKA","NNAMDI","CHIKA",
        ],
        "last": [
            "OKAFOR","NWOSU","EZE","NWACHUKWU","OKONKWO","CHUKWU","DIKE","MADUKA",
            "NNAMDI","CHUKWUDI","ODINAKA","NNAETOO","KANU","OBI",
        ],
    },
    "yoruba": {
        "first": [
            "OLUWASEUN","BABATUNDE","FUNMI","GBENGA","JUMOKE","SOLA","TEMITOPE",
            "WUNMI","YETUNDE","ADEWALE","BUKOLA","DAMILOLA","FOLAKE","TUNDE",
            "ABIODUN","OLAMIDE","TAIWO","KEHINDE",
        ],
        "last": [
            "ADEYEMI","BALOGUN","LAWAL","QUADRI","RAJI","FADAHUNSI","IDOWU","LEKE",
            "ABIODUN","BABATOLA","DARAMOLA","ADELEKE","OGUNDIMU","SHITTU",
        ],
    },
    "hausa": {
        "first": [
            "HALIMA","ZAINAB","HAUWA","IBRAHIM","USMAN","MUSA","ALIYU","AMINU",
            "FATIMA","ABUBAKAR","SADIQ","BASHIR","MARYAM","YUSUF",
        ],
        "last": [
            "IBRAHIM","MUSA","USMAN","GARBA","HARUNA","BELLO","SANI","ABUBAKAR",
            "ALIYU","DANJUMA","LAWAL","MOHAMMED",
        ],
    },
    "general": {
        # Christian / Niger-Delta / pan-Nigerian names that pair broadly
        "first": [
            "MICHAEL","PATIENCE","QUEEN","RAPHAEL","DAVID","BLESSING","DIVINE",
            "ELISHA","FLORENCE","GRACE","HENRY","JOSEPH","GODWIN","PAUL","JOY",
            "VICTOR","LILIAN","DAMIETE",
        ],
        "last": [
            "JOHNSON","PETERS","SMITH","VINCENT","WILLIAMS","JAMES","PIUS",
            "AKPAN","EFFIONG","IMEH","EKWERRE","IDA-EREFA","BRIGGS","OSEI","EBOIGBE",
        ],
    },
}

def random_name() -> str:
    group = random.choice(list(NAME_GROUPS.values()))
    first = random.choice(group["first"]).upper()
    last = random.choice(group["last"]).upper()
    return f"{first} {last}"

def random_amount() -> int:
    pool = [
        random.randint(200_000,   999_999),
        random.randint(1_000_000, 2_999_999),
        random.randint(3_000_000, 5_000_000),
    ]
    return round(random.choice(pool) / 1_000) * 1_000

def fmt_ngn(amount: int) -> str:
    return f"{amount:,.2f}"

def fmt_ngn_full(amount: int) -> str:
    return f"{amount:,.2f} NGN"

def fmt_caption(amount: int) -> str:
    return f"{amount:,}"

def rand_ref_S() -> str:
    return "S" + "".join(random.choices(string.digits, k=8))

def rand_ref_hex(n=42) -> str:
    return "".join(random.choices("0123456789abcdef", k=n))

def rand_digits(n) -> str:
    return "".join(random.choices(string.digits, k=n))

def rand_session_id() -> str:
    return "000017" + rand_digits(24)

def transaction_time(post_time: datetime) -> datetime:
    return post_time - timedelta(minutes=random.randint(30, 60))

def fmt_date_dmy(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y")

def fmt_date_long(dt: datetime) -> str:
    days   = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    h = dt.hour % 12 or 12
    ampm = "am" if dt.hour < 12 else "pm"
    return f"{days[dt.weekday()]}, {months[dt.month-1]} {dt.day}, {dt.year}, {h}:{dt.strftime('%M')} {ampm}"

def fmt_date_short(dt: datetime) -> str:
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    h = dt.hour % 12 or 12
    ampm = "PM" if dt.hour >= 12 else "AM"
    return f"{months[dt.month-1]} {dt.day}, {dt.year} {h}:{dt.strftime('%M')} {ampm}"

def fmt_date_uba(dt: datetime) -> str:
    days   = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return f"{days[dt.weekday()]} {months[dt.month-1]} {dt.day:02d} {dt.year}"

def fmt_time_hms(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")

def fmt_time_hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")

def fmt_gtbank_dt(dt: datetime) -> str:
    return f"{dt.day} {['January','February','March','April','May','June','July','August','September','October','November','December'][dt.month-1]} {dt.year} at {fmt_time_hm(dt)}"

def rand_at_ref() -> str:
    chars = string.ascii_letters + string.digits
    return "AT" + rand_digits(2) + "_TRF2MPT" + "".join(random.choices(chars, k=8))

def number_to_words(n: int) -> str:
    if n == 0: return "Zero"
    ones = ["","One","Two","Three","Four","Five","Six","Seven","Eight","Nine",
            "Ten","Eleven","Twelve","Thirteen","Fourteen","Fifteen","Sixteen",
            "Seventeen","Eighteen","Nineteen"]
    tens_w = ["","","Twenty","Thirty","Forty","Fifty","Sixty","Seventy","Eighty","Ninety"]
    def below1000(x):
        if x == 0: return ""
        elif x < 20: return ones[x]
        elif x < 100: return tens_w[x//10] + (" " + ones[x%10] if x%10 else "")
        else: return ones[x//100] + " Hundred" + (" " + below1000(x%100) if x%100 else "")
    parts, labels, i = [], ["","Thousand","Million","Billion"], 0
    while n > 0:
        if n % 1000: parts.append(below1000(n%1000) + (" " + labels[i] if labels[i] else ""))
        n //= 1000; i += 1
    return " ".join(reversed(parts))

def mask_account(acc: str) -> str:
    """Mask middle digits: 0812345678 → 081****678"""
    acc = str(acc).strip()
    if len(acc) <= 6:
        return acc[:2] + "****"
    return acc[:3] + "****" + acc[-3:]


def mask_account_sup(acc: str) -> str:
    """Mask middle digits with superscript asterisks for Assets MFB style:
       0812345678 → 081<sup class='asterisk'>*</sup>...678"""
    acc = str(acc).strip()
    stars = '<sup class="asterisk">*</sup>' * 3
    if len(acc) <= 6:
        return acc[:2] + stars
    return acc[:4] + stars + acc[-3:]


# ══════════════════════════════════════════════════════     ═════════
# SHARED CONSTANTS
# ════════════════════════════════════════════════════════════════
TAILWIND   = '<script src="https://cdn.tailwindcss.com"></script>'
INTER_FONT = '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'


SENDER_BANK = "Moniepoint MFB"


OPAY_BANKS = {
    "Wema Bank PLC": "https://s3-symbol-logo.tradingview.com/wema-bank-plc--600.png",
    "PAYSTACK-TITAN": "https://i.ibb.co/fLkMFXr/paystack-logo-modified.png",
}


# ════════════════════════════════════════════════════════════════
# TEMPLATE BUILDERS
# ════════════════════════════════════════════════════════════════

# ── UBA Classic (UBA 1) ───────────────────────────────────────────────────────
def tpl_uba1(receiver: str, amount: int, tx: datetime) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Transaction Details</title>
{TAILWIND}
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
*{{font-size:14px}}
body{{font-family:'Inter',sans-serif;background:white;margin:0;padding:0}}
.border-thin{{border-bottom-width:1px!important;border-color:#000!important}}
.section-title{{font-size:16px;font-weight:600}}
</style></head>
<body class="bg-white">
<div style="width:100%;line-height:0">
  <img src="https://i.ibb.co/MkMxhN90/photo-2025-10-05-12-11-43.jpg"
       style="width:100%;height:auto;display:block;max-width:100%"
       onerror="this.style.display='none'">
</div>
<div class="max-w-4xl p-4" style="position:relative">
  <img src="https://i.ibb.co/1f3RKwzD/trba.png"
       alt=""
       style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:85%;max-width:520px;height:auto;opacity:0.15;z-index:0;pointer-events:none"
       onerror="this.style.display='none'">
  <div style="position:relative;z-index:1">
    <h1 class="section-title mb-2">Transaction Details:-</h1>
    <div class="border-thin mb-4"></div>
    <div class="space-y-3 mb-6">
      <div><span class="font-semibold">Date:</span> {fmt_date_uba(tx)}</div>
      <div><span class="font-semibold">Time:</span> {fmt_time_hms(tx)}</div>
      <div><span class="font-semibold">Reference:</span> {rand_ref_S()}</div>
      <div><span class="font-semibold">Amount:</span> {fmt_ngn_full(amount)}</div>
      <div><span class="font-semibold">Status:</span> SUCCESSFUL</div>
      <div><span class="font-semibold">Type:</span> Credit</div>
    </div>
    <h2 class="section-title mb-2">Accounts Details:-</h2>
    <div class="border-thin mb-4"></div>
    <div><span class="font-semibold">Narration:</span> TNF-USDT Farm Limited/Transfer/ To {receiver}</div>
  </div>
</div>
</body></html>"""


# ── UBA Modern (UBA 2) ────────────────────────────────────────────────────────
def tpl_uba2(receiver: str, amount: int, tx: datetime) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Transaction Details</title>
{TAILWIND}
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
*{{font-size:14px}}html,body{{height:100%;margin:0;padding:0}}
body{{font-family:'Inter',sans-serif}}
.border-thin{{border-bottom-width:1px!important;border-color:#000!important}}
.section-title{{font-size:16px;font-weight:600}}
</style></head>
<body class="min-h-screen bg-gradient-to-b from-[#fbfbfb] to-[#f8f8fa]">
<div style="width:100%;line-height:0">
  <img src="https://i.ibb.co/n8P6m7J2/topp.jpg"
       style="width:100%;height:auto;display:block;max-width:100%"
       onerror="this.style.display='none'">
</div>
<div class="max-w-4xl p-4 mx-auto">
  <h1 class="section-title mb-2">Transaction Details:-</h1>
  <div class="border-thin mb-4"></div>
  <div class="space-y-3 mb-6">
    <div><span class="font-semibold">Date:</span> {fmt_date_uba(tx)}</div>
    <div><span class="font-semibold">Time:</span> {fmt_time_hms(tx)}</div>
    <div><span class="font-semibold">Reference:</span> {rand_ref_S()}</div>
    <div><span class="font-semibold">Amount:</span> {fmt_ngn_full(amount)}</div>
    <div><span class="font-semibold">Status:</span> SUCCESSFUL</div>
    <div><span class="font-semibold">Type:</span> Credit</div>
  </div>
  <h2 class="section-title mb-2">Accounts Details:-</h2>
  <div class="border-thin mb-4"></div>
  <div><span class="font-semibold">Narration:</span> TNF-USDT Farm Limited/Transfer/ To {receiver}</div>
</div>
<div style="width:100%;line-height:0">
  <img src="https://i.ibb.co/Pvmp72tz/photo-2025-10-05-21-15-20.jpg"
       style="width:100%;height:auto;display:block;max-width:100%"
       onerror="this.style.display='none'">
</div>
</body></html>"""


# ── Roqqu ─────────────────────────────────────────────────────────────────────
def tpl_roqqu(receiver: str, amount: int, tx: datetime) -> str:
    usdt   = round(amount / 1600, 2)
    tx_id  = random.randint(10_000_000, 99_999_999)
    months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Roqqu Transaction Receipt</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-size:10px}}
body{{font-family:'Inter',sans-serif;background:#fff;min-height:100vh}}
.container{{max-width:400px;margin:0 auto;padding:32px 20px 0}}
.amount-label{{color:#454545;margin-bottom:3px;font-weight:500;font-size:8px}}
.amount-value{{color:#333;font-weight:900;letter-spacing:0.5px;line-height:1.2;font-size:14px}}
.section-title{{color:#000;font-weight:700;margin-bottom:5px}}
.detail-row{{display:flex;justify-content:space-between;align-items:flex-start;padding:12px 0}}
.detail-label{{color:#666;flex-shrink:0;margin-right:16px}}
.detail-value{{color:#333;text-align:right;flex:1;word-break:break-word}}
</style></head>
<body>
<img src="https://hebbkx1anhila5yf.public.blob.vercel-storage.com/roqqu-header-w-100.jpg-gNB09nGLs4Hxbn9VtsgOHxOUq8nclB.jpeg"
     alt="Roqqu Header" style="width:100%;height:auto;display:block" onerror="this.style.display='none'">
<div class="container">
  <div style="margin-bottom:32px">
    <div class="amount-label">USDT Received</div>
    <div class="amount-value">{usdt} USDT</div>
  </div>
  <h2 class="section-title">Transaction Details</h2>
  <div style="background:#FAFAFA;padding:5px;border-radius:6px">
    <div class="detail-row"><span class="detail-label">ID</span><span class="detail-value">{tx_id}</span></div>
    <div class="detail-row"><span class="detail-label">Amount</span><span class="detail-value">{usdt} USDT</span></div>
    <div class="detail-row"><span class="detail-label">Type</span><span class="detail-value">USDT Received</span></div>
    <div class="detail-row"><span class="detail-label">Description</span><span class="detail-value">Received {usdt}3200 USDT from transfer</span></div>
    <div class="detail-row"><span class="detail-label">Transaction date</span><span class="detail-value">{months[tx.month-1]} {tx.day}, {tx.year}</span></div>
  </div>
  <img src="https://hebbkx1anhila5yf.public.blob.vercel-storage.com/roqqu-footer-w-100.jpg-7boq5JInokxi7bRQmcdVOHw19dEjxy.jpeg"
       alt="Roqqu Footer" style="width:100%;height:auto;display:block;margin-top:32px" onerror="this.style.display='none'">
</div>
</body></html>"""


# ── Kuda ──────────────────────────────────────────────────────────────────────
def tpl_kuda(receiver: str, amount: int, tx: datetime, kuda_acct: str = "9720396770") -> str:
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    paid_date = f"{months[tx.month-1]} {tx.day}, {tx.year}"
    h = tx.hour % 12 or 12
    ampm = "PM" if tx.hour >= 12 else "AM"
    paid_time = f"{h}:{tx.strftime('%M')} {ampm}"
    seg = [8, 4, 4, 4, 12]
    tx_ref = "ITR-" + "-".join("".join(random.choices("0123456789abcdef", k=n)) for n in seg)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,100;0,300;0,400;0,700;0,900;1,100;1,300;1,400;1,700;1,900&display=swap" rel="stylesheet">
    <title>Kuda</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: "Lato", sans-serif;
            background-color: #FFFFFF;
        }}

        .container {{
            max-width: 400px;
            margin: 0 auto;
            background: white;
            min-height: 100vh;
        }}

        .header img {{
            width: 100%;
            display: block;
        }}

        .details {{
            padding: 10px;
        }}

        .amount-section {{
            text-align: center;
            margin-bottom: 0px;
        }}

        .detail-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            padding: 8px 0;
            border-bottom: 1.3px solid #CACACA;
        }}

        .detail-label {{
            color: #AAAAAA;
            font-size: 10px;
            flex: 1;
        }}

        .detail-value {{
            text-align: right;
            flex: 1;
            font-size: 10px;
            color: #000;
            font-weight: 450;
        }}

        .detail-value .sub-text {{
            color: #999;
            font-size: 10px;
            display: block;
            margin-top: 2px;
        }}

        .sub-text {{
            font-weight: normal;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="https://i.ibb.co/mCzs4NRm/Kuda-Header.jpg" alt="" srcset="" width="100%">
        </div>

        <div class="details">
            <div class="amount-section">
                <div class="amount-label" style="font-size: 10px; font-weight: 600;">Transaction Amount</div>
                <div class="amount" style="font-size: 14px; font-weight: 1000;">₦{fmt_ngn(amount)}</div>
            </div>

            <div class="detail-row">
                <div class="detail-label">Beneficiary Details</div>
                <div class="detail-value">
                    <span>{receiver}</span>
                    <span class="sub-text">Kuda | <span>{mask_account(kuda_acct)}</span></span>
                </div>
            </div>

            <div class="detail-row">
                <div class="detail-label">Sender Details</div>
                <div class="detail-value">
                    <span>USDT Farm Limited</span>
                    <span class="sub-text">Kuda | <span>{mask_account("10121")}</span></span>
                </div>
            </div>

            <div class="detail-row">
                <div class="detail-label">Paid On</div>
                <div class="detail-value">
                    <span>{paid_date}</span>
                    <span class="sub-text">{paid_time}</span>
                </div>
            </div>

            <div class="detail-row">
                <div class="detail-label">Fees</div>
                <div class="detail-value">₦0.00</div>
            </div>

            <div class="detail-row">
                <div class="detail-label">Description</div>
                <div class="detail-value">Transfer from USDT Farm Limited</div>
            </div>

            <div class="detail-row">
                <div class="detail-label">Transaction Reference</div>
                <div class="detail-value">{tx_ref}</div>
            </div>

            <div class="detail-row">
                <div class="detail-label">Payment Type</div>
                <div class="detail-value">Local Funds Transfer</div>
            </div>
        </div>

        <div class="footer">
            <img src="https://i.ibb.co/rRTcWN4g/photo-5877306125311479666-w.jpg" alt="" srcset="" width="100%">
        </div>
    </div>
</body>
</html>"""


# ── USDT Farm Limited Withdrawal Page (paired with each bank receipt) ─────────
# Bank details shown on the withdrawal page, matched to the receipt being posted.
USDT_FARM_BANKS = {
    "UBA Classic": ("United Bank for Africa", None),
    "UBA Modern":  ("United Bank for Africa", None),
    "Kuda":        ("Kuda Microfinance Bank", None),
    "Sparkle":     ("Sparkle", None),
    "Access Bank": ("Access Bank", None),
}

# NGN value of 1 USD, used to show the USD figure on the withdrawal page.
USD_RATE = 1600


def usdt_farm_details_for(tpl_name: str, receiver: str, acct: str = "") -> tuple[str, str, str]:
    """Return (bank_name, account_number, account_name) matching the receipt."""
    bank, _ = USDT_FARM_BANKS.get(tpl_name, ("United Bank for Africa", None))
    # If no account was passed (None), generate a random one
    if not acct:
        acct = rand_digits(10)
    return bank, acct, receiver


def tpl_usdt_farm(amount: int, tx: datetime, bank_name: str,
                  account_number: str, account_name: str) -> str:
    """
    USDT Farm Limited 'Transaction Details' withdrawal page, paired with a bank
    receipt. Light theme: green→emerald gradient summary card, status pill, and
    a divided list of detail rows with a reference ID footer.
    """
    net_ngn = amount
    usd     = net_ngn / USD_RATE
    wit_id  = random.randint(0, 999_999)
    ref     = "WIT-" + str(wit_id).zfill(6)
    date_time = fmt_date_short(tx)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Transaction Details</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    body {{
        font-family: 'Inter', sans-serif;
        padding-bottom: 24px;
        background: linear-gradient(to bottom, #f0fdf4 0%, #ffffff 300px);
    }}
</style>
</head>
<body>
<div class="container mx-auto px-3 mt-3" style="max-width:420px">
    <a href="#" class="inline-flex items-center text-sm text-gray-600 mb-3">
        <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>
        </svg>
        Back to Transactions
    </a>

    <!-- Summary card -->
    <div class="bg-white rounded-xl shadow-lg overflow-hidden mb-4">
        <div class="bg-gradient-to-r from-green-500 to-emerald-600 p-6 text-center text-white">
            <div class="text-4xl mb-2">📤</div>
            <div class="text-sm opacity-90">Withdrawal</div>
            <div class="text-3xl font-bold mt-1">-${usd:,.2f}</div>
            <div class="mt-3">
                <span class="px-3 py-1 text-xs rounded-full bg-green-100 text-green-800 font-medium">✓ Completed</span>
            </div>
        </div>

        <!-- Detail rows -->
        <div class="divide-y divide-gray-100">
            <div class="flex justify-between items-center px-4 py-3">
                <span class="text-xs text-gray-500">Date &amp; Time</span>
                <span class="text-xs font-medium text-gray-900 text-right">{date_time}</span>
            </div>
            <div class="flex justify-between items-start px-4 py-3 gap-3">
                <span class="text-xs text-gray-500 flex-shrink-0">Method</span>
                <span class="text-xs font-medium text-gray-900 text-right break-words">Bank Transfer</span>
            </div>
            <div class="flex justify-between items-start px-4 py-3 gap-3">
                <span class="text-xs text-gray-500 flex-shrink-0">Amount</span>
                <span class="text-xs font-medium text-gray-900 text-right break-words">${usd:,.2f}</span>
            </div>
            <div class="flex justify-between items-start px-4 py-3 gap-3">
                <span class="text-xs text-gray-500 flex-shrink-0">Amount (Local)</span>
                <span class="text-xs font-medium text-gray-900 text-right break-words">₦{fmt_ngn(net_ngn)}</span>
            </div>
            <div class="flex justify-between items-start px-4 py-3 gap-3">
                <span class="text-xs text-gray-500 flex-shrink-0">Bank</span>
                <span class="text-xs font-medium text-gray-900 text-right break-words">{bank_name}</span>
            </div>
            <div class="flex justify-between items-start px-4 py-3 gap-3">
                <span class="text-xs text-gray-500 flex-shrink-0">Account Number</span>
                <span class="text-xs font-medium text-gray-900 text-right break-words font-mono">{mask_account(account_number)}</span>
            </div>
            <div class="flex justify-between items-start px-4 py-3 gap-3">
                <span class="text-xs text-gray-500 flex-shrink-0">Account Name</span>
                <span class="text-xs font-medium text-gray-900 text-right break-words">{account_name}</span>
            </div>
            <div class="flex justify-between items-center px-4 py-3">
                <span class="text-xs text-gray-500">Processed At</span>
                <span class="text-xs font-medium text-gray-900 text-right">{date_time}</span>
            </div>
            <div class="flex justify-between items-center px-4 py-3">
                <span class="text-xs text-gray-500">Reference ID</span>
                <span class="text-xs font-medium text-gray-900 font-mono">#{ref}</span>
            </div>
        </div>
    </div>

    <div class="text-center text-[11px] text-gray-400 mt-4">
        Powered by USDT Farm Limited
    </div>
</div>
</body>
</html>"""


# ── Sparkle ───────────────────────────────────────────────────────────────────
def tpl_sparkle(receiver: str, amount: int, tx: datetime) -> str:
    months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
    days   = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    day_name = days[tx.weekday()]
    date_str = f"{day_name}, {str(tx.day).zfill(2)} {months[tx.month-1]}, {tx.year}. {str(tx.hour).zfill(2)}:{str(tx.minute).zfill(2)} {'pm' if tx.hour >= 12 else 'am'}"
    session_id = "".join(random.choices("0123456789", k=30))
    comment_num = "F2MPTb3nfs" + "".join(random.choices("0123456789", k=20))
    sender_name = "USDT Farm Limited"
    sender_acct = mask_account(rand_digits(10))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@300..700&family=Inter:wght@300..700&display=swap" rel="stylesheet">
    <title>Sparkle</title>
    <style>
        * {{
            font-size: 14px;
            background-color: #F9F9F9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }}
        span {{
            float: right;
            color: #737373;
            font-weight: 700;
        }}
        .details p {{
            color: #797979;
            font-weight: 400;
        }}
        hr {{
            border: none;
            height: 1px;
            background-color: #E9E9E9;
            margin: 8px 0;
        }}
        .container {{
            margin: 5px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="head-logo">
            <img src="https://i.ibb.co/4ZYs3tdn/header-logo.jpg" alt="" srcset="" width="100%">
        </div>

        <div class="details">
            <p>Session Id <span>{session_id}</span></p>
            <hr>
            <p>Type <span>Deposit</span></p>
            <hr>
            <p>Date and Time <span>{date_str}</span></p>
            <hr>
            <p>Sender <span>{sender_name} - {sender_acct}</span></p>
            <hr>
            <p>Recipient <span>{receiver}</span></p>
            <hr>
            <p>Amount <span>₦ {fmt_ngn(amount)}</span></p>
            <hr>
            <p>Status <span>Successful</span></p>
            <hr>
            <p>Comment 
                <span>{receiver.upper()} Trf for Customer/AT68_TR</span>
                <span>{comment_num}</span>
            </p>
        </div>
    </div>
</body>
</html>"""


# ── Access Bank ───────────────────────────────────────────────────────────────
def tpl_access_bank(receiver: str, amount: int, tx: datetime) -> str:
    months = ["January","February","March","April","May","June","July","August","September","October","November","December"]
    date_str = f"{months[tx.month-1]} {tx.day}, {tx.year}"
    reference = "".join(random.choices("0123456789", k=30))
    narration = f"USDT Farm Limited to {receiver.upper()}:{reference}"
    theme = random.choice(["orange", "green", "blue"])
    
    # Theme colors
    colors = {
        "orange": {"header": "#f7941d", "accent": "#f7941d", "icon": "https://i.postimg.cc/XqgVPQkH/ACCESSICON.jpg", "bottom": "https://i.postimg.cc/HxxjbG0p/ACCESSB-UTTOM.jpg"},
        "green": {"header": "#97b517", "accent": "#97b517", "icon": "https://hebbkx1anhila5yf.public.blob.vercel-storage.com/Green%20Icon-NLJgYEjjReT5r1vNzfe7T6UwF3U2LW.jpg", "bottom": "https://hebbkx1anhila5yf.public.blob.vercel-storage.com/Green%20Bottom-SQlB4sxXWK6OILsYyl5uW1cdF67eEa.jpg"},
        "blue": {"header": "#3b5998", "accent": "#3b5998", "icon": "https://hebbkx1anhila5yf.public.blob.vercel-storage.com/Blue%20Icon-NALvbaR35w5Uv1f9R0kXiUpFgiqrJ5.jpg", "bottom": "https://i.ibb.co/G3p0bphM/aef36c1e-2af9-45bd-ab6e-a2e593924348.jpg"},
    }
    c = colors[theme]
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <title>Access Bank</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Nunito Sans', sans-serif; background: #f5f5f5; }}
        .divider {{ height: 1px; background-color: #e5e5e5; }}
        .header-top {{ background-color: {c['header']}; padding: 12px 24px; display: flex; align-items: center; }}
        .header-top svg {{ width: 24px; height: 24px; stroke: white; }}
    </style>
</head>
<body>
<div style="max-width: 430px; margin: 0 auto; height: 100vh; overflow: hidden; display: flex; flex-direction: column; background: white;">
    <!-- MAIN HEADER (with back arrow) -->
    <div style="background-color: {c['header']}; padding: 40px 24px 28px 24px; flex-shrink: 0; text-align: center; position: relative;">
        <button style="position: absolute; left: 20px; top: 40px; background: none; border: none; cursor: pointer; padding: 0;">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/>
            </svg>
        </button>
        <p style="color: white; font-size: 16px; font-weight: 600; margin-bottom: 22px;">{date_str}</p>
        <div style="margin-bottom: 10px;">
            <img src="{c['icon']}" alt="Transaction Icon" style="width: 80px; height: 80px; border-radius: 16px; object-fit: cover; display: inline-block;">
        </div>
        <p style="color: rgba(255,255,255,0.75); font-size: 13px; font-weight: 500; margin-bottom: 6px;">Others</p>
        <p style="color: white; font-size: 20px; letter-spacing: 0.9px; font-weight: 600;">₦{fmt_ngn(amount)}</p>
    </div>
    <div style="height: 5px; background-color: #f2f3ef; flex-shrink: 0;"></div>
    <!-- TRANSACTION DETAILS -->
    <div style="background-color: #ffffff; padding: 0 24px; flex-shrink: 0;">
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 18px 0;">
            <span style="font-size: 14px; color: #444; font-weight: 400;">To</span>
            <span style="font-size: 14px; color: {c['accent']}; font-weight: 700;">{receiver.upper()}</span>
        </div>
        <div class="divider"></div>
        <div style="display: flex; justify-content: space-between; align-items: flex-start; padding: 18px 0;">
            <span style="font-size: 14px; color: #444; font-weight: 400; margin-right: 20px;">Narration</span>
            <span style="font-size: 14px; color: {c['accent']}; font-weight: 700; text-align: right; line-height: 1.55; max-width: 65%; word-wrap: break-word;">{narration}</span>
        </div>
        <div class="divider"></div>
        <div style="display: flex; justify-content: space-between; align-items: flex-start; padding: 18px 0; margin-bottom: 12px;">
            <span style="font-size: 14px; color: #444; font-weight: 400; margin-right: 20px;">Reference</span>
            <span style="font-size: 14px; color: {c['accent']}; font-weight: 700; text-align: right; line-height: 1.55; max-width: 65%; word-wrap: break-word;">{reference}</span>
        </div>
    </div>
    <!-- BOTTOM IMAGE -->
    <div style="flex: 1; min-height: 0; overflow: hidden; display: flex; flex-direction: column; flex-shrink: 0;">
        <img src="{c['bottom']}" alt="Access Bank Bottom" style="width: 100%; height: 100%; display: block; object-fit: fill;">
    </div>
</div>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════
# TEMPLATE REGISTRY  (6 templates)
# ════════════════════════════════════════════════════════════════
TEMPLATES = [
    ("UBA Classic",       tpl_uba1),
    ("UBA Modern",        tpl_uba2),
    ("Roqqu",             tpl_roqqu),
    ("Kuda",              tpl_kuda),
    ("Sparkle",           tpl_sparkle),
    ("Access Bank",       tpl_access_bank),
]


# ════════════════════════════════════════════════════════════════
# PLAYWRIGHT RENDERER
# ════════════════════════════════════════════════════════════════
def get_chromium_path():
    for p in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
        if os.path.exists(p):
            return p
    return None


async def html_to_image(html: str) -> BytesIO:
    """
    Render HTML → PNG.
    Viewport: 390 px (iPhone 14 logical), device_scale_factor=3 → 1170 px wide output.
    Waits for networkidle + 3 s extra + JS img promise for CDN images.
    """
    kwargs = {
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]
    }
    cp = get_chromium_path()
    if cp:
        kwargs["executable_path"] = cp

    async with async_playwright() as p:
        browser = await p.chromium.launch(**kwargs)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
        )
        page = await context.new_page()

        # Load page; allow 30 s for CDN resources
        await page.set_content(html, wait_until="networkidle", timeout=30_000)

        # Extra pause for slower CDN hosts (ibb.co, vercel blob, postimg…)
        await asyncio.sleep(3)

        # Wait for every <img> to finish loading
        await page.evaluate("""() => {
            return Promise.all(
                Array.from(document.images)
                    .filter(img => !img.complete)
                    .map(img => new Promise(resolve => {
                        img.onload = resolve;
                        img.onerror = resolve;
                    }))
            );
        }""")

        # Expand viewport to full page height then screenshot
        height = await page.evaluate("document.documentElement.scrollHeight")
        await page.set_viewport_size({"width": 390, "height": max(height, 100)})
        data = await page.screenshot(full_page=True)
        await browser.close()

    buf = BytesIO(data)
    buf.name = "receipt.png"
    return buf


# ═══════════════    ════════════════════════════════════════════════
# CHANNEL AUTO-DISCOVERY
# ════════════════════════════════════════════════════════════════
def register_channel(chat_id: int, title: str = ""):
    if chat_id not in known_channels:
        known_channels.add(chat_id)
        logger.info(f"✅ Registered channel: {chat_id}" + (f" ({title})" if title else ""))


async def on_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.channel_post:
        register_channel(update.channel_post.chat.id, update.channel_post.chat.title or "")


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.my_chat_member:
        return
    chat   = update.my_chat_member.chat
    member = update.my_chat_member.new_chat_member
    if chat.type == "channel":
        if member.status in ("administrator", "creator"):
            register_channel(chat.id, chat.title or "")
        elif member.status in ("left", "kicked", "restricted", "member"):
            known_channels.discard(chat.id)
            logger.info(f"🗑  Removed channel (lost admin): {chat.id}")


async def scan_history(bot: Bot):
    try:
        updates = await bot.get_updates(limit=100, timeout=0)
        for u in updates:
            if u.channel_post:
                register_channel(u.channel_post.chat.id, u.channel_post.chat.title or "")
            if u.my_chat_member:
                chat   = u.my_chat_member.chat
                member = u.my_chat_member.new_chat_member
                if chat.type == "channel" and member.status in ("administrator", "creator"):
                    register_channel(chat.id, chat.title or "")
        logger.info(f"📋 History scan done — {len(known_channels)} channel(s) found")
    except Exception as e:
        logger.warning(f"History scan failed: {e}")


# ═════════════════════════════════════════════════════════════  ══
# POSTER
# ════════════════════════════════════════════════════════════════
async def post_to_all_channels(bot: Bot):
    if not known_channels:
        logger.warning("⚠️  No channels found. Make the bot admin in a channel and send a message there.")
        return

    now      = datetime.now()
    tx_time  = transaction_time(now)
    amount   = random_amount()
    receiver = random_name()

    tpl_name, tpl_fn = random.choice(TEMPLATES)
    logger.info(f"🎲 Template: {tpl_name} | ₦{amount:,} → {receiver}")

    # Generate a shared account number for Kuda (randomized each posting)
    kuda_acct = rand_digits(10) if tpl_name == "Kuda" else ""

    # Render the receipt image
    if tpl_name == "Kuda":
        html  = tpl_fn(receiver, amount, tx_time, kuda_acct)
    else:
        html  = tpl_fn(receiver, amount, tx_time)
    image = await html_to_image(html)

    # Build the paired USDT Farm Limited withdrawal page (skip for Roqqu / crypto)
    withdrawal_image = None
    if tpl_name != "Roqqu":
        bank_name, account_number, account_name = usdt_farm_details_for(tpl_name, receiver, kuda_acct)
        withdrawal_html  = tpl_usdt_farm(amount, tx_time, bank_name, account_number, account_name)
        withdrawal_image = await html_to_image(withdrawal_html)

    if tpl_name == "Roqqu":
        usdt = round(amount / 1600, 2)
        caption = (
            "🚨 <b>Credit Alert!</b>\n\n"
            f"<b>USDT Farm Limited has successfully credited a user with {usdt} USDT just now.</b>\n\n"
            "<blockquote>Don't hold back any longer, what are you waiting for? 💰</blockquote>\n\n"
            "<b>Go to: <a href='https://1ufarm.com'>1ufarm.com</a> and get started.</b>"
        )
    else:
        caption = (
            "🚨 <b>Credit Alert!</b>\n\n"
            f"<b>USDT Farm Limited has successfully credited {receiver} with {fmt_caption(amount)}.00 just now.</b>\n\n"
            "<blockquote>Don't hold back any longer, what are you waiting for? 💰</blockquote>\n\n"
            "<b>Go to: <a href='https://1ufarm.com'>1ufarm.com</a> and get started.</b>"
        )

    for cid in list(known_channels):
        try:
            # Delete previous message(s) if any exist
            if cid in last_message_ids:
                for mid in last_message_ids[cid]:
                    try:
                        await bot.delete_message(chat_id=cid, message_id=mid)
                        logger.info(f"🗑  Deleted previous message {mid} from {cid}")
                    except TelegramError as e:
                        logger.warning(f"⚠️  Could not delete message {mid} from {cid}: {e}")

            if withdrawal_image is not None:
                # Post the USDT Farm Limited withdrawal page + receipt together as one album
                withdrawal_image.seek(0)
                image.seek(0)
                media = [
                    InputMediaPhoto(media=withdrawal_image, caption=caption, parse_mode="HTML"),
                    InputMediaPhoto(media=image),
                ]
                messages = await bot.send_media_group(chat_id=cid, media=media)
                last_message_ids[cid] = [m.message_id for m in messages]
                logger.info(f"📤 Sent album {last_message_ids[cid]} to {cid}")
            else:
                # Roqqu: receipt only, no paired page
                image.seek(0)
                message = await bot.send_photo(chat_id=cid, photo=image, caption=caption, parse_mode="HTML")
                last_message_ids[cid] = [message.message_id]
                logger.info(f"📤 Sent message {message.message_id} to {cid}")
        except TelegramError as e:
            logger.error(f"❌ Failed to send to {cid}: {e}")


# ════════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════  ════  ═══════════════════════════════════
async def scheduler(bot: Bot):
    logger.info(f"    Posting every {POST_INTERVAL_MINUTES} minute(s)")
    while True:
        await post_to_all_channels(bot)
        await asyncio.sleep(POST_INTERVAL_MINUTES * 60)


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════  ═══════════════════════════════════════════════
async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, on_channel_post))
    app.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    bot = app.bot
    me  = await bot.get_me()
    logger.info(f"🤖 Started as @{me.username} | {len(TEMPLATES)} templates loaded")

    await scan_history(bot)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        allowed_updates=["channel_post", "my_chat_member"],
        drop_pending_updates=False,
    )
    await scheduler(bot)


if __name__ == "__main__":
    asyncio.run(main())
