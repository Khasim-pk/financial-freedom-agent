import pandas as pd
import streamlit as st

from sheets_client import read_sheet
from rules_engine import evaluate_month_rules, money


RULE_TABS = [
    "Settings",
    "Months",
    "Fixed_Commitments",
    "Credit_Card_Dues",
    "Next_Cycle_Liability",
    "Weekly_Envelopes",
    "Transactions",
    "Handloans",
    "Categories",
]


@st.cache_data(ttl=10)
def load_rules_data():
    data = {}

    for tab in RULE_TABS:
        data[tab] = read_sheet(tab)

    return data


def severity_badge_text(severity):
    if severity == "Red":
        return "🔴 Red"
    if severity == "Orange":
        return "🟠 Orange"
    if severity == "Yellow":
        return "🟡 Yellow"
    if severity == "Green":
        return "🟢 Green"
    return "ℹ️ Info"


def render_glass_metrics(metrics_list):
    html = '<div class="glass-grid">'
    for item in metrics_list:
        title = item[0]
        value = item[1]
        footer = item[2] if len(item) > 2 else ""
        footer_html = f'<div class="glass-card-footer">{footer}</div>' if footer else ''
        html += f'<div class="glass-card"><div><div class="glass-card-header">{title}</div><div class="glass-card-value">{value}</div></div>{footer_html}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_key_value_table(rows):
    html = '<div style="background: rgba(30, 41, 59, 0.3); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 12px; margin-bottom: 24px;">'
    for label, val in rows:
        html += f'<div style="display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255, 255, 255, 0.05); padding: 8px 12px; font-size: 0.95rem;"><span style="color: #94a3b8; font-weight: 500;">{label}</span><span style="color: #ffffff; font-weight: 600;">{val}</span></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_alert_list(alerts):
    html = '<div style="margin: 16px 0;">'
    for alert in alerts:
        severity = alert.get("Severity", "Info")
        area = alert.get("Area", "")
        message = alert.get("Message", "")
        amount = alert.get("Amount", "")
        action = alert.get("Recommended Action", "")
        
        html += f'<div class="alert-card {severity}"><div style="flex-grow: 1; margin-right: 16px;"><div style="font-weight: 700; font-size: 1rem; color: #ffffff; margin-bottom: 4px;">{area}</div><div style="color: #cbd5e1; font-size: 0.9rem; margin-bottom: 4px;">{message}</div><div style="color: #94a3b8; font-size: 0.8rem; font-style: italic;">Action: {action}</div></div><div style="font-size: 1.25rem; font-weight: 700; color: #ffffff; min-width: 80px; text-align: right;">{amount}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def show_rules_page(selected_month, selected_week):
    st.title("Rules Engine")
    st.caption("This page checks your financial recovery rules and highlights danger areas.")

    if st.button("Refresh rules"):
        st.cache_data.clear()
        st.rerun()

    try:
        data = load_rules_data()
        result = evaluate_month_rules(data, selected_month, selected_week)
    except Exception as error:
        st.error("Could not evaluate rules.")
        st.exception(error)
        return

    summary = result["summary"]
    alerts = result["alerts"]
    transaction_risks = result["transaction_risks"]

    st.subheader("Recovery Status")

    score = summary["Recovery Score"]
    status = summary["Recovery Status"]

    status_emoji_map = {
        "Controlled": "🟢 Controlled",
        "Watch": "🟡 Watch",
        "Risk": "🟠 Risk",
        "Critical": "🔴 Critical",
    }
    status_text = status_emoji_map.get(status, status)

    render_glass_metrics([
        ("Recovery Score", f"{score}/100"),
        ("Recovery Status", status_text),
        ("Current Card Pending", money(summary["Current Card Pending"])),
        ("Next-Cycle Liability", money(summary["Confirmed Next-Cycle Liability"])),
    ])

    if status == "Controlled":
        st.success("Recovery status is controlled. Continue the same discipline.")
    elif status == "Watch":
        st.warning("Recovery is okay but needs attention. Avoid unnecessary spending.")
    elif status == "Risk":
        st.warning("Recovery is risky. Reduce spending and avoid all card usage.")
    else:
        st.error("Recovery is critical. Stop non-essential spending and protect cash immediately.")

    st.subheader("Core Metrics")

    metric_rows = [
        ["Total Available", money(summary["Total Available"])],
        ["Direct Fixed Burden", money(summary["Direct Fixed Burden"])],
        ["Current Card Pending", money(summary["Current Card Pending"])],
        ["Month Cash Spend", money(summary["Month Cash Spend"])],
        ["Estimated Recovery Buffer", money(summary["Estimated Recovery Buffer"])],
        ["Base Next-Cycle Liability", money(summary["Base Next-Cycle Liability"])],
        ["New Card Leaks Added", money(summary["New Card Leaks Amount"])],
        ["Confirmed Next-Cycle Liability", money(summary["Confirmed Next-Cycle Liability"])],
        ["Weekly Spent", money(summary["Weekly Spent"])],
        ["Weekly Practical Target", money(summary["Weekly Practical Target"])],
        ["Weekly Target Left", money(summary["Weekly Target Left"])],
        ["Weekly Hard Cap Left", money(summary["Weekly Hard Cap Left"])],
        ["Unknown Expenses", money(summary["Unknown Amount"])],
        ["Coupon Masking", money(summary["Coupon Masking Amount"])],
        ["Quick Commerce / Treats", money(summary["Quick Commerce Amount"])],
        ["Handloan Balance", money(summary["Total Handloan Balance"])],
    ]

    render_key_value_table(metric_rows)

    st.subheader("Alerts")

    if not alerts:
        st.success("No alerts found.")
    else:
        render_alert_list(alerts)

    st.subheader("Transaction Risk Review")

    if transaction_risks.empty:
        st.info("No transactions found for this month.")
    else:
        view = transaction_risks.copy()
        view["Amount"] = view["Amount"].apply(money)
        view["Severity"] = view["Severity"].apply(severity_badge_text)

        st.dataframe(
            view,
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("How to use this page")

    st.info(
        "Use this page as your daily risk check. "
        "Red means immediate action. Orange means recovery pressure. "
        "Yellow means watch carefully. Green means the rule is currently safe."
    )
