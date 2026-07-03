"""
Meta (Facebook) Marketing API helpers.

Handles fetching active campaigns/ad sets/ads, their insights (spend, clicks,
purchases, etc.), and reconciling budget info into a single flat dataset that
gets handed to the local LLM for summarization.

Note on units: Meta's Marketing API returns budget-related fields
(daily_budget, lifetime_budget, budget_remaining) in the ad account's
currency's smallest unit (e.g. cents / poisha), but Insights fields like
"spend" are already returned in the account's *major* currency unit.
MINOR_UNIT_DIVISOR below corrects for that. It assumes a 2-decimal currency
(true for BDT, USD, EUR, etc.) -- if your ad account uses a zero-decimal
currency (e.g. JPY, KRW), set this to 1.
"""

import json
from datetime import datetime, timedelta

import requests

from logger import get_logger

logger = get_logger()

GRAPH_API_VERSION = "v21.0"  # bump this periodically -- Meta deprecates old versions
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

MINOR_UNIT_DIVISOR = 100

PURCHASE_ACTION_TYPES = {
    "purchase",
    "omni_purchase",
    "offsite_conversion.fb_pixel_purchase",
}


class MetaAdsError(Exception):
    pass


def _get(path, params, access_token):
    params = dict(params)
    params["access_token"] = access_token

    # Log the request with token redacted
    safe_params = {k: ("<REDACTED>" if k == "access_token" else v) for k, v in params.items()}
    logger.info("GET %s  params=%s", path, safe_params)

    resp = requests.get(f"{GRAPH_BASE}/{path}", params=params, timeout=30)
    logger.info("GET %s  -> HTTP %s", path, resp.status_code)

    data = resp.json()
    logger.debug("GET %s  response body: %s", path, json.dumps(data, default=str))

    if "error" in data:
        logger.error("GET %s  Meta API error: %s", path, json.dumps(data["error"], default=str))
        raise MetaAdsError(data["error"].get("message", "Unknown Meta API error"))
    return data


def _get_all_pages(path, params, access_token):
    data = _get(path, params, access_token)
    out = list(data.get("data", []))
    page_num = 1
    while "paging" in data and "next" in data["paging"]:
        page_num += 1
        next_url = data["paging"]["next"]
        # Redact access_token from the pagination URL for safe logging
        safe_url = next_url
        if "access_token=" in safe_url:
            safe_url = safe_url.split("access_token=")[0] + "access_token=<REDACTED>"
        logger.info("GET (page %s)  %s", page_num, safe_url)
        resp = requests.get(next_url, timeout=30)
        logger.info("GET (page %s)  -> HTTP %s", page_num, resp.status_code)
        data = resp.json()
        logger.debug("GET (page %s)  response body: %s", page_num, json.dumps(data, default=str))
        if "error" in data:
            logger.error("GET (page %s)  Meta API error: %s", page_num, json.dumps(data["error"], default=str))
            raise MetaAdsError(data["error"].get("message", "Unknown Meta API error"))
        out.extend(data.get("data", []))
    return out


def fetch_campaigns(ad_account_id, access_token):
    fields = "id,name,daily_budget,lifetime_budget,budget_remaining,effective_status"
    return _get_all_pages(f"{ad_account_id}/campaigns", {"fields": fields, "limit": 200}, access_token)


def fetch_adsets(ad_account_id, access_token):
    fields = "id,name,campaign_id,daily_budget,lifetime_budget,budget_remaining,effective_status"
    return _get_all_pages(f"{ad_account_id}/adsets", {"fields": fields, "limit": 200}, access_token)


def fetch_ad_insights(ad_account_id, access_token, since, until):
    fields = (
        "ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,"
        "spend,impressions,clicks,ctr,cpc,cpm,actions,cost_per_action_type"
    )
    params = {
        "level": "ad",
        "fields": fields,
        "time_range": json.dumps({"since": since, "until": until}),
        "filtering": json.dumps(
            [{"field": "ad.effective_status", "operator": "IN", "value": ["ACTIVE"]}]
        ),
        "limit": 200,
    }
    return _get_all_pages(f"{ad_account_id}/insights", params, access_token)


def money(raw):
    """Convert a budget field from minor units to major currency units."""
    if raw is None:
        return None
    try:
        return round(float(raw) / MINOR_UNIT_DIVISOR, 2)
    except (TypeError, ValueError):
        return None


def extract_purchases(actions):
    if not actions:
        return 0
    total = 0
    for a in actions:
        if a.get("action_type") in PURCHASE_ACTION_TYPES:
            try:
                total += int(float(a.get("value", 0)))
            except (TypeError, ValueError):
                pass
    return total


def resolve_budget(adset, campaign):
    """
    Ad-set budget takes priority. Falls back to the campaign's budget for
    accounts using Campaign Budget Optimization (CBO), where the ad set
    itself won't carry budget fields.
    """
    source = adset if (adset.get("daily_budget") or adset.get("lifetime_budget")) else campaign

    if source.get("daily_budget"):
        return {"type": "daily", "amount": money(source["daily_budget"])}

    if source.get("lifetime_budget"):
        return {
            "type": "lifetime",
            "amount": money(source["lifetime_budget"]),
            "remaining": money(source.get("budget_remaining")),
        }

    return {"type": "unknown", "amount": None}


def build_report_dataset(ad_account_id, access_token, days_back):
    """
    Returns a list of dicts, one per active ad, with spend/purchase metrics
    for the requested period plus resolved budget info.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    until = today
    since = (datetime.now() - timedelta(days=days_back - 1)).strftime("%Y-%m-%d")

    logger.info(
        "build_report_dataset  account=%s  days_back=%s  since=%s  until=%s",
        ad_account_id, days_back, since, until,
    )

    campaigns = {c["id"]: c for c in fetch_campaigns(ad_account_id, access_token)}
    logger.info("build_report_dataset  campaigns fetched: %s", len(campaigns))

    adsets = {a["id"]: a for a in fetch_adsets(ad_account_id, access_token)}
    logger.info("build_report_dataset  adsets fetched: %s", len(adsets))

    insights = fetch_ad_insights(ad_account_id, access_token, since, until)
    logger.info("build_report_dataset  insight rows fetched: %s", len(insights))
    if len(insights) == 0:
        logger.warning("build_report_dataset  fetch_ad_insights returned 0 rows — this is the most likely point of failure")

    # For daily-budget ads we also need *today's* spend specifically, to
    # compute "remaining today" -- even when the requested period is a
    # full week, since a daily budget resets every day.
    if since == today:
        today_insights = insights
    else:
        today_insights = fetch_ad_insights(ad_account_id, access_token, today, today)
        logger.info("build_report_dataset  today insight rows fetched: %s", len(today_insights))

    spend_today_by_adset = {}
    for row in today_insights:
        adset_id = row.get("adset_id")
        spend_today_by_adset[adset_id] = spend_today_by_adset.get(adset_id, 0.0) + float(
            row.get("spend", 0) or 0
        )

    rows = []
    for row in insights:
        adset = adsets.get(row.get("adset_id"), {})
        campaign = campaigns.get(row.get("campaign_id"), {})
        budget = resolve_budget(adset, campaign)

        spend = float(row.get("spend", 0) or 0)
        purchases = extract_purchases(row.get("actions"))
        cost_per_purchase = round(spend / purchases, 2) if purchases else None

        if budget["type"] == "daily":
            spent_today = spend_today_by_adset.get(row.get("adset_id"), 0.0)
            budget["spent_today"] = round(spent_today, 2)
            budget["remaining_today"] = (
                round(max(budget["amount"] - spent_today, 0), 2) if budget["amount"] else None
            )

        rows.append({
            "ad_name": row.get("ad_name"),
            "adset_name": row.get("adset_name"),
            "campaign_name": row.get("campaign_name"),
            "period_spend": round(spend, 2),
            "impressions": int(row.get("impressions", 0) or 0),
            "clicks": int(row.get("clicks", 0) or 0),
            "ctr": row.get("ctr"),
            "cpc": row.get("cpc"),
            "purchases": purchases,
            "cost_per_purchase": cost_per_purchase,
            "budget": budget,
        })

    logger.info("build_report_dataset  final row count: %s", len(rows))
    return rows
