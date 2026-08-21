import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, date
from zoneinfo import ZoneInfo

from sheets_client import read_sheet, append_row
from monthly_reset_page import show_monthly_setup_page
from transaction_manager_page import show_transaction_manager_page
from rules_page import show_rules_page
from pre_spend_page import show_pre_spend_page


st.set_page_config(
    page_title="Financial Freedom Dashboard",
    page_icon="💰",
    layout="wide"
)


def inject_custom_css():
    try:
        with open("style.css", "r") as f:
            css = f.read()
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except Exception:
        pass


inject_custom_css()


# ----------------------------
# Expected Google Sheet columns
# ----------------------------

EXPECTED_COLUMNS = {
    "Settings": ["Key", "Value", "Notes"],
    "Months": [
        "Month_ID", "Month_Name", "Year", "Opening_Bank_Cash",
        "Salary_Received", "Handloan_Received", "Fixed_Burden",
        "Current_Card_Dues", "Next_Cycle_Liability", "Status"
    ],
    "Fixed_Commitments": [
        "Month_ID", "Commitment_Name", "Amount", "Payment_Mode",
        "Due_Date", "Status", "Is_Fixed", "Notes"
    ],
    "Credit_Card_Dues": [
        "Month_ID", "Card_Name", "Due_Amount", "Due_Date",
        "Status", "Paid_Amount", "Payment_Date", "Notes"
    ],
    "Next_Cycle_Liability": [
        "Month_ID", "Item", "Amount", "Source",
        "Is_Fixed", "Is_Card_Leak", "Status", "Notes"
    ],
    "Weekly_Envelopes": [
        "Month_ID", "Week_Name", "Start_Date", "End_Date",
        "Green_Target", "Practical_Target", "Hard_Cap",
        "Spent", "Status", "Notes"
    ],
    "Transactions": [
        "Transaction_ID", "Timestamp", "Month_ID", "Week_Name",
        "Date", "Amount", "Category", "Subcategory",
        "Payment_Mode", "Essential_Type", "Is_Credit_Card_Leak",
        "Is_Unknown", "Notes", "Source"
    ],
    "Handloans": [
        "Loan_ID", "Lender", "Starting_Amount", "Amount_Repaid",
        "Balance", "Status", "Priority", "Notes"
    ],
    "Categories": [
        "Category", "Type", "Risk_Level", "Keywords",
        "Default_Payment_Mode"
    ],
    "Leaks": [
        "Leak_ID", "Timestamp", "Month_ID", "Week_Name",
        "Amount", "Leak_Type", "Status", "Notes"
    ],
}


# ----------------------------
# Helper functions
# ----------------------------

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


def render_custom_progress_bar(percentage, status):
    status_lower = str(status).lower()
    if status_lower == "green":
        bar_class = "progress-bar-green"
    elif status_lower == "caution":
        bar_class = "progress-bar-yellow"
    elif status_lower == "warning":
        bar_class = "progress-bar-orange"
    else:
        bar_class = "progress-bar-red"
        
    html = f'<div class="progress-container-custom"><div class="progress-bar-custom {bar_class}" style="width: {min(percentage, 100.0):.1f}%;"></div></div>'
    st.markdown(html, unsafe_allow_html=True)


def render_priority_list(priorities_data):
    html = '<div class="priority-list">'
    for row in priorities_data:
        rank = row[0]
        focus = row[1]
        amount = row[2]
        status = row[3]
        
        status_lower = str(status).lower()
        if "green" in status_lower:
            badge_class = "normal"
            status_text = "Green"
        elif "caution" in status_lower:
            badge_class = "high"
            status_text = "Caution"
        elif "warning" in status_lower:
            badge_class = "critical"
            status_text = "Warning"
        elif "red" in status_lower:
            badge_class = "urgent"
            status_text = "Red"
        elif "urgent" in status_lower:
            badge_class = "urgent"
            status_text = "Urgent"
        elif "critical" in status_lower:
            badge_class = "critical"
            status_text = "Critical"
        elif "high" in status_lower:
            badge_class = "high"
            status_text = "High"
        elif "later" in status_lower:
            badge_class = "later"
            status_text = "Later"
        else:
            badge_class = "normal"
            status_text = status
            
        html += f'<div class="priority-item"><div class="priority-rank">{rank}</div><div class="priority-label">{focus} <span style="color: #94a3b8; font-size: 0.85rem; margin-left: 8px;">({amount})</span></div><div class="priority-badge {badge_class}">{status_text}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def money(amount):
    """Format number as Indian rupees."""
    try:
        return f"₹{float(amount):,.0f}"
    except Exception:
        return "₹0"


def to_number(value):
    """Convert Google Sheet cell value to number safely."""
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace("₹", "").replace(",", "").strip()

    if text == "":
        return 0.0

    try:
        return float(text)
    except ValueError:
        return 0.0


def safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_month_id(value):
    text = safe_text(value)

    if len(text) >= 7 and text[4] == "-" and text[:4].isdigit() and text[5:7].isdigit():
        return text[:7]

    parts = text.split()
    month_lookup = {
        "Jan": "01",
        "Feb": "02",
        "Mar": "03",
        "Apr": "04",
        "May": "05",
        "Jun": "06",
        "Jul": "07",
        "Aug": "08",
        "Sep": "09",
        "Oct": "10",
        "Nov": "11",
        "Dec": "12",
    }

    if len(parts) >= 4 and parts[1] in month_lookup and parts[3].isdigit():
        return f"{parts[3]}-{month_lookup[parts[1]]}"

    parsed = pd.to_datetime(text, errors="coerce")

    if pd.isna(parsed):
        return text

    return parsed.strftime("%Y-%m")


def ensure_columns(df, tab_name):
    """Make sure a dataframe has the columns we expect."""
    expected = EXPECTED_COLUMNS.get(tab_name, [])

    for col in expected:
        if col not in df.columns:
            df[col] = ""

    if expected:
        return df[expected]

    return df


def filter_month(df, month_id):
    if df.empty or "Month_ID" not in df.columns:
        return df

    selected_month = normalize_month_id(month_id)

    return df[
        df["Month_ID"].apply(normalize_month_id) == selected_month
    ].copy()


def first_row_as_dict(df):
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


def current_timestamp():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return now.strftime("%Y-%m-%d %H:%M:%S")


def make_id(prefix):
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return f"{prefix}-{now.strftime('%Y%m%d%H%M%S')}"


def get_settings_dict(settings_df):
    if settings_df.empty:
        return {}

    if "Key" not in settings_df.columns or "Value" not in settings_df.columns:
        return {}

    result = {}

    for _, row in settings_df.iterrows():
        key = safe_text(row.get("Key"))
        value = row.get("Value")

        if key:
            result[key] = value

    return result


def get_setting(settings_dict, key, default=None):
    return settings_dict.get(key, default)


def calculate_week_status(spent, green_target, practical_target, hard_cap):
    if spent <= green_target:
        return "Green"
    if spent <= practical_target:
        return "Caution"
    if spent <= hard_cap:
        return "Warning"
    return "Red"


def calculate_month_status(spent, green_target, practical_target, hard_cap):
    if hard_cap <= 0:
        return "Unknown"

    if spent <= green_target:
        return "Green"
    if spent <= practical_target:
        return "Caution"
    if spent <= hard_cap:
        return "Warning"
    return "Red"


def get_category_info(categories_df, category_name):
    if categories_df.empty:
        return {"Type": "Unknown", "Risk_Level": "Unknown"}

    matches = categories_df[
        categories_df["Category"].astype(str).str.strip() == str(category_name).strip()
    ]

    if matches.empty:
        return {"Type": "Unknown", "Risk_Level": "Unknown"}

    row = matches.iloc[0].to_dict()

    return {
        "Type": safe_text(row.get("Type", "Unknown")),
        "Risk_Level": safe_text(row.get("Risk_Level", "Unknown")),
    }


def is_leak_transaction(category, payment_mode, category_type, risk_level):
    category = safe_text(category)
    payment_mode = safe_text(payment_mode)
    category_type = safe_text(category_type)
    risk_level = safe_text(risk_level)

    if payment_mode == "Credit Card" and category != "Insurance":
        return True

    if category in [
        "Unknown Leak",
        "Credit Card Leak",
        "Coupon Masking",
        "Quick Commerce",
        "Treats",
        "Shopping",
    ]:
        return True

    if category_type == "Leakage":
        return True

    if risk_level in ["High", "Critical"]:
        return True

    return False


def get_leak_type(category, payment_mode, is_credit_card_leak, is_unknown):
    if is_credit_card_leak == "Yes":
        return "Credit Card Leak"

    if is_unknown == "Yes":
        return "Unknown Leak"

    if category == "Coupon Masking":
        return "Coupon Masking"

    if category == "Quick Commerce":
        return "Quick Commerce"

    if category == "Treats":
        return "Treats"

    if category == "Shopping":
        return "Shopping"

    if payment_mode == "Amazon Pay Coupon":
        return "Coupon Masking"

    return category


# ----------------------------
# Google Sheets loading
# ----------------------------

@st.cache_data(ttl=10)
def load_tab(tab_name):
    df = read_sheet(tab_name)
    return ensure_columns(df, tab_name)


@st.cache_data(ttl=10)
def load_all_data():
    data = {}

    for tab_name in EXPECTED_COLUMNS.keys():
        data[tab_name] = load_tab(tab_name)

    return data


try:
    data = load_all_data()
except Exception as error:
    st.error("Could not load data from Google Sheets.")
    st.exception(error)
    st.stop()


# ----------------------------
# Sidebar controls
# ----------------------------

settings_df = data["Settings"]
months_df = data["Months"]
weekly_df = data["Weekly_Envelopes"]

settings = get_settings_dict(settings_df)

if months_df.empty:
    month_ids = ["2026-06"]
else:
    month_ids = [
        str(x).strip()
        for x in months_df["Month_ID"].dropna().tolist()
        if str(x).strip()
    ]

    if not month_ids:
        month_ids = ["2026-06"]

st.sidebar.title("Financial Freedom")
st.sidebar.caption("Local dashboard connected to Google Sheets")

selected_month = st.sidebar.selectbox(
    "Current Month",
    month_ids,
    index=len(month_ids) - 1
)

weekly_for_month = filter_month(weekly_df, selected_month)

if weekly_for_month.empty:
    week_names = ["Week 1", "Week 2", "Week 3", "Week 4"]
else:
    week_names = [
        str(x).strip()
        for x in weekly_for_month["Week_Name"].dropna().tolist()
        if str(x).strip()
    ]

    if not week_names:
        week_names = ["Week 1", "Week 2", "Week 3", "Week 4"]

selected_week = st.sidebar.selectbox("Current Week", week_names)

page = st.sidebar.radio(
    "Go to",
    [
        "Dashboard",
        "Can I Spend?",
        "Rules",
        "Monthly Setup",
        "Weekly Envelopes",
        "Credit Cards",
        "Bills",
        "Transactions",
        "Leaks",
        "Handloans",
        "Settings",
    ]
)

st.sidebar.markdown("---")

if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.write("Emergency Mode:", get_setting(settings, "emergency_recovery_mode", "ON"))
st.sidebar.write("Credit Card Detox:", get_setting(settings, "credit_card_detox_mode", "ON"))


# ----------------------------
# Current month calculations
# ----------------------------

month_rows = filter_month(months_df, selected_month)
month_row = first_row_as_dict(month_rows)

opening_bank_cash = to_number(
    month_row.get("Opening_Bank_Cash", get_setting(settings, "current_bank_cash", 0))
)
net_salary = to_number(
    month_row.get("Salary_Received", get_setting(settings, "net_salary", 0))
)
handloan_received = to_number(
    month_row.get("Handloan_Received", get_setting(settings, "planned_new_handloan", 0))
)

total_available = opening_bank_cash + net_salary + handloan_received

fixed_df = filter_month(data["Fixed_Commitments"], selected_month)
credit_card_dues_df = filter_month(data["Credit_Card_Dues"], selected_month)
next_cycle_df = filter_month(data["Next_Cycle_Liability"], selected_month)
transactions_df = filter_month(data["Transactions"], selected_month)
handloans_df = data["Handloans"]
categories_df = data["Categories"]
leaks_df = filter_month(data["Leaks"], selected_month)

if not fixed_df.empty:
    fixed_df["Amount_Number"] = fixed_df["Amount"].apply(to_number)
    total_fixed_burden = fixed_df["Amount_Number"].sum()

    direct_fixed_df = fixed_df[
        ~fixed_df["Payment_Mode"].astype(str).str.lower().str.contains("credit card", na=False)
    ]
    direct_fixed_burden = direct_fixed_df["Amount_Number"].sum()
else:
    total_fixed_burden = to_number(
        month_row.get("Fixed_Burden", get_setting(settings, "total_fixed_burden", 0))
    )
    direct_fixed_burden = total_fixed_burden

if not credit_card_dues_df.empty:
    credit_card_dues_df["Due_Number"] = credit_card_dues_df["Due_Amount"].apply(to_number)
    credit_card_dues_df["Paid_Number"] = credit_card_dues_df["Paid_Amount"].apply(to_number)
    credit_card_dues_df["Pending_Number"] = (
        credit_card_dues_df["Due_Number"] - credit_card_dues_df["Paid_Number"]
    ).clip(lower=0)

    current_card_due_total = credit_card_dues_df["Due_Number"].sum()
    current_card_pending = credit_card_dues_df["Pending_Number"].sum()
else:
    current_card_due_total = to_number(
        month_row.get("Current_Card_Dues", get_setting(settings, "current_card_dues_total", 0))
    )
    current_card_pending = current_card_due_total

if not next_cycle_df.empty:
    next_cycle_df["Amount_Number"] = next_cycle_df["Amount"].apply(to_number)
    base_next_cycle_liability = next_cycle_df["Amount_Number"].sum()
else:
    base_next_cycle_liability = to_number(
        month_row.get("Next_Cycle_Liability", get_setting(settings, "next_cycle_liability", 0))
    )

if not transactions_df.empty:
    transactions_df["Amount_Number"] = transactions_df["Amount"].apply(to_number)

    card_leak_transactions = transactions_df[
        transactions_df["Is_Credit_Card_Leak"].astype(str) == "Yes"
    ]
    new_card_leaks_amount = card_leak_transactions["Amount_Number"].sum()

    non_card_transactions = transactions_df[
        transactions_df["Payment_Mode"].astype(str) != "Credit Card"
    ]
    month_cash_spend = non_card_transactions["Amount_Number"].sum()
    monthly_spent = transactions_df["Amount_Number"].sum()
else:
    new_card_leaks_amount = 0
    month_cash_spend = 0
    monthly_spent = 0

confirmed_next_cycle_liability = base_next_cycle_liability + new_card_leaks_amount

estimated_recovery_buffer = (
    total_available
    - direct_fixed_burden
    - current_card_pending
    - month_cash_spend
)

if not weekly_for_month.empty:
    monthly_green_target = weekly_for_month["Green_Target"].apply(to_number).sum()
    monthly_practical_target = weekly_for_month["Practical_Target"].apply(to_number).sum()
    monthly_hard_cap = weekly_for_month["Hard_Cap"].apply(to_number).sum()
else:
    monthly_green_target = to_number(get_setting(settings, "weekly_green_target", 4000)) * 4
    monthly_practical_target = to_number(get_setting(settings, "weekly_practical_target", 4500)) * 4
    monthly_hard_cap = to_number(get_setting(settings, "weekly_hard_cap", 6000)) * 4

monthly_spend_left = monthly_hard_cap - monthly_spent
monthly_usage_percent = (
    monthly_spent / monthly_hard_cap * 100
    if monthly_hard_cap > 0
    else 0
)
monthly_status = calculate_month_status(
    monthly_spent,
    monthly_green_target,
    monthly_practical_target,
    monthly_hard_cap,
)

weekly_current_rows = weekly_for_month[
    weekly_for_month["Week_Name"].astype(str) == str(selected_week)
].copy()

weekly_row = first_row_as_dict(weekly_current_rows)

weekly_green_target = to_number(
    weekly_row.get("Green_Target", get_setting(settings, "weekly_green_target", 4000))
)
weekly_practical_target = to_number(
    weekly_row.get("Practical_Target", get_setting(settings, "weekly_practical_target", 4500))
)
weekly_hard_cap = to_number(
    weekly_row.get("Hard_Cap", get_setting(settings, "weekly_hard_cap", 6000))
)

if not transactions_df.empty:
    week_transactions = transactions_df[
        transactions_df["Week_Name"].astype(str) == str(selected_week)
    ].copy()

    if not week_transactions.empty:
        week_transactions["Amount_Number"] = week_transactions["Amount"].apply(to_number)
        weekly_spent = week_transactions["Amount_Number"].sum()
    else:
        weekly_spent = 0
else:
    week_transactions = pd.DataFrame(columns=EXPECTED_COLUMNS["Transactions"])
    weekly_spent = 0

weekly_target_left = weekly_practical_target - weekly_spent
weekly_hard_cap_left = weekly_hard_cap - weekly_spent
weekly_status = calculate_week_status(
    weekly_spent,
    weekly_green_target,
    weekly_practical_target,
    weekly_hard_cap,
)


# ----------------------------
# Flash message after saving
# ----------------------------

if "flash_message" in st.session_state:
    st.success(st.session_state.pop("flash_message"))


# ----------------------------
# Dashboard page
# ----------------------------

if page == "Dashboard":
    st.title("Financial Freedom Dashboard")
    st.caption("Live view from your Google Sheets database.")

    st.subheader("Current Recovery Snapshot")

    render_glass_metrics([
        ("Opening Bank Cash", money(opening_bank_cash)),
        ("Net Salary", money(net_salary)),
        ("Handloan Received", money(handloan_received)),
        ("Total Available", money(total_available)),
    ])

    render_glass_metrics([
        ("Direct Fixed Burden", money(direct_fixed_burden)),
        ("Current Card Pending", money(current_card_pending)),
        ("Next-Cycle Liability", money(confirmed_next_cycle_liability)),
        ("Recovery Buffer Estimate", money(estimated_recovery_buffer)),
    ])

    st.markdown("---")
    st.subheader("📊 Spend Analytics")

    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.write("### Category Breakdown")
        
        # Prepare category data for the selected month
        df_spend = transactions_df.copy() if not transactions_df.empty else pd.DataFrame()
        if not df_spend.empty:
            df_spend["Amount_Number"] = df_spend["Amount"].apply(to_number)
            # Exclude internal payments and only keep actual spends > 0
            df_spend = df_spend[~df_spend["Category"].isin(["Credit Card Payment", "Handloan Repayment"])]
            df_spend = df_spend[df_spend["Amount_Number"] > 0]
            
        if df_spend.empty:
            st.info("No transaction spends logged for this month.")
        else:
            category_spend = df_spend.groupby("Category", as_index=False)["Amount_Number"].sum()
            category_spend = category_spend.sort_values(by="Amount_Number", ascending=False)
            total_month_spend = category_spend["Amount_Number"].sum()
            category_spend["Percentage"] = (category_spend["Amount_Number"] / total_month_spend * 100).round(1)
            
            # Format columns for tooltips
            category_spend["Amount_Formatted"] = category_spend["Amount_Number"].apply(lambda x: f"₹{x:,.0f}")
            category_spend["Percent_Formatted"] = category_spend["Percentage"].apply(lambda x: f"{x:.1f}%")
            
            # Sage green palette mapping
            colors = ["#4a7559", "#799f84", "#a1c2ac", "#c5ded0", "#6b8b76", "#8fa998", "#b6cdbe", "#dbe8df", "#566e5f", "#34453b"]
            color_scale = alt.Scale(
                domain=category_spend["Category"].tolist(),
                range=colors[:len(category_spend)]
            )
            
            donut_chart = alt.Chart(category_spend).mark_arc(innerRadius=65, stroke="#ffffff", strokeWidth=2).encode(
                theta=alt.Theta(field="Amount_Number", type="quantitative"),
                color=alt.Color(field="Category", type="nominal", scale=color_scale, legend=alt.Legend(title="Category", orient="bottom")),
                tooltip=[
                    alt.Tooltip(field="Category", title="Category"),
                    alt.Tooltip(field="Amount_Formatted", title="Amount Spent"),
                    alt.Tooltip(field="Percent_Formatted", title="Percentage Share")
                ]
            ).properties(
                height=300,
                background='transparent'
            ).configure_view(
                strokeWidth=0
            )
            
            st.altair_chart(donut_chart, use_container_width=True)

    with col_chart2:
        st.write("### Spending Trend Timeline")
        
        # Prepare trend data across all-time transactions
        df_trend_all = data["Transactions"].copy() if not data["Transactions"].empty else pd.DataFrame()
        if not df_trend_all.empty:
            df_trend_all["Amount_Number"] = df_trend_all["Amount"].apply(to_number)
            df_trend_all["Month_ID_Normalized"] = df_trend_all["Month_ID"].apply(normalize_month_id)
            # Exclude internal payments and only keep actual spends > 0
            df_trend_all = df_trend_all[~df_trend_all["Category"].isin(["Credit Card Payment", "Handloan Repayment"])]
            df_trend_all = df_trend_all[df_trend_all["Amount_Number"] > 0]
            
        if df_trend_all.empty:
            st.info("No transaction spends logged yet.")
        else:
            # Horizontal radio button toggle for trend type
            trend_type = st.radio(
                "Select Trend Interval",
                ["Weekly Spends", "Monthly Spends"],
                horizontal=True,
                label_visibility="collapsed",
                key="trend_interval_selector_radio"
            )
            
            if trend_type == "Weekly Spends":
                def format_week(week_str):
                    week_str = str(week_str).strip()
                    if "Week" in week_str:
                        return week_str.replace("Week", "W").replace(" ", "")
                    return week_str
                    
                df_trend_all["Week_Short"] = df_trend_all["Week_Name"].apply(format_week)
                df_trend_all["Interval"] = df_trend_all["Month_ID_Normalized"] + " " + df_trend_all["Week_Short"]
                
                trend_data = df_trend_all.groupby("Interval", as_index=False)["Amount_Number"].sum()
                trend_data = trend_data.sort_values(by="Interval")
            else:
                trend_data = df_trend_all.groupby("Month_ID_Normalized", as_index=False)["Amount_Number"].sum()
                trend_data = trend_data.rename(columns={"Month_ID_Normalized": "Interval"})
                trend_data = trend_data.sort_values(by="Interval")
                
            trend_data["Amount_Formatted"] = trend_data["Amount_Number"].apply(lambda x: f"₹{x:,.0f}")
            
            trend_chart = alt.Chart(trend_data).mark_bar(
                color="#4a7559",
                cornerRadiusTopLeft=4,
                cornerRadiusTopRight=4
            ).encode(
                x=alt.X("Interval:N", title="Time Period", sort=None),
                y=alt.Y("Amount_Number:Q", title="Amount Spent (₹)"),
                tooltip=[
                    alt.Tooltip("Interval:N", title="Period"),
                    alt.Tooltip("Amount_Formatted:N", title="Spent")
                ]
            ).properties(
                height=260,
                background='transparent'
            ).configure_view(
                strokeWidth=0
            )
            
            st.altair_chart(trend_chart, use_container_width=True)

    st.markdown("---")
    st.subheader("Monthly Spend Tracker")

    status_emoji_map = {
        "Green": "🟢 Green",
        "Caution": "🟡 Caution",
        "Warning": "🟠 Warning",
        "Red": "🔴 Red",
    }
    monthly_status_text = status_emoji_map.get(monthly_status, monthly_status)
    weekly_status_text = status_emoji_map.get(weekly_status, weekly_status)

    render_glass_metrics([
        ("Spent This Month", money(monthly_spent)),
        ("Monthly Green Target", money(monthly_green_target)),
        ("Monthly Hard Cap Left", money(monthly_spend_left)),
        ("Monthly Status", monthly_status_text),
    ])

    if monthly_hard_cap > 0:
        render_custom_progress_bar(monthly_usage_percent, monthly_status)
        st.caption(
            f"You have used {monthly_usage_percent:.1f}% of the monthly hard cap. "
            f"Practical target: {money(monthly_practical_target)}. "
            f"Hard cap: {money(monthly_hard_cap)}."
        )

    if monthly_status == "Green":
        st.success("Monthly spending is inside the green zone.")
    elif monthly_status == "Caution":
        st.warning("Monthly spending is still under control, but getting close.")
    elif monthly_status == "Warning":
        st.warning("Monthly spending is near the limit. Keep only essentials now.")
    elif monthly_status == "Red":
        st.error("Monthly spending crossed the limit. Stop non-essential spending.")

    st.subheader(f"{selected_week} Envelope")

    render_glass_metrics([
        ("Spent This Week", money(weekly_spent)),
        ("Target Left", money(weekly_target_left)),
        ("Hard Cap Left", money(weekly_hard_cap_left)),
        ("Week Status", weekly_status_text),
    ])

    if weekly_status == "Green":
        st.success("You are inside the green recovery zone. Stay in UPI/debit/cash mode.")
    elif weekly_status == "Caution":
        st.warning("You are near the weekly practical target. Spend only on essentials.")
    elif weekly_status == "Warning":
        st.warning("You crossed the practical target. Hard cap is still available, but recovery is under pressure.")
    else:
        st.error("Red alert. You crossed the weekly hard cap. Stop non-essential spending until next week.")

    st.subheader("Recovery Priorities")

    priorities_list = [
        ["1", "Clear current credit-card dues", money(current_card_pending), "Urgent" if current_card_pending > 0 else "Normal"],
        ["2", "Stop discretionary credit-card use", "₹0 allowed", "Critical"],
        ["3", "Prepare for next-cycle card liability", money(confirmed_next_cycle_liability), "High" if confirmed_next_cycle_liability > 0 else "Normal"],
        ["4", "Control weekly spending", f"{money(weekly_practical_target)} target / {money(weekly_hard_cap)} cap", weekly_status],
        ["5", "Repay handloans later", "After card stability", "Later"],
    ]
    render_priority_list(priorities_list)



# ----------------------------
# Can I Spend page
# ----------------------------

elif page == "Can I Spend?":
    show_pre_spend_page(selected_month, selected_week)


# ----------------------------
# Rules page
# ----------------------------

elif page == "Rules":
    show_rules_page(selected_month, selected_week)


# ----------------------------
# Monthly setup page
# ----------------------------

elif page == "Monthly Setup":
    show_monthly_setup_page(selected_month)


# ----------------------------
# Weekly envelopes page
# ----------------------------

elif page == "Weekly Envelopes":
    st.title("Weekly Envelopes")
    st.caption("Live weekly spending is calculated from the Transactions tab.")

    if weekly_for_month.empty:
        st.info("No weekly envelope rows found for this month.")
    else:
        view = weekly_for_month.copy()

        if not transactions_df.empty:
            spend_by_week = (
                transactions_df.assign(Amount_Number=transactions_df["Amount"].apply(to_number))
                .groupby("Week_Name", as_index=False)["Amount_Number"]
                .sum()
            )
        else:
            spend_by_week = pd.DataFrame(columns=["Week_Name", "Amount_Number"])

        view = view.merge(spend_by_week, on="Week_Name", how="left")
        view["Amount_Number"] = view["Amount_Number"].fillna(0)

        view["Green_Target_Number"] = view["Green_Target"].apply(to_number)
        view["Practical_Target_Number"] = view["Practical_Target"].apply(to_number)
        view["Hard_Cap_Number"] = view["Hard_Cap"].apply(to_number)

        view["Live_Spent"] = view["Amount_Number"]
        view["Target_Left"] = view["Practical_Target_Number"] - view["Live_Spent"]
        view["Hard_Cap_Left"] = view["Hard_Cap_Number"] - view["Live_Spent"]

        view["Live_Status"] = view.apply(
            lambda row: calculate_week_status(
                row["Live_Spent"],
                row["Green_Target_Number"],
                row["Practical_Target_Number"],
                row["Hard_Cap_Number"],
            ),
            axis=1
        )

        status_map = {
            "Green": "🟢 Green",
            "Caution": "🟡 Caution",
            "Warning": "🟠 Warning",
            "Red": "🔴 Red",
        }
        view["Live_Status"] = view["Live_Status"].map(status_map).fillna(view["Live_Status"])

        display_cols = [
            "Month_ID", "Week_Name", "Green_Target", "Practical_Target",
            "Hard_Cap", "Live_Spent", "Target_Left", "Hard_Cap_Left",
            "Live_Status"
        ]

        # Format columns as money
        for col in ["Green_Target", "Practical_Target", "Hard_Cap", "Live_Spent", "Target_Left", "Hard_Cap_Left"]:
            if col in view.columns:
                view[col] = view[col].apply(to_number).apply(money)

        st.dataframe(view[display_cols], use_container_width=True, hide_index=True)


# ----------------------------
# Credit cards page
# ----------------------------

elif page == "Credit Cards":
    st.title("Credit Cards")
    st.caption("Current dues and next-cycle liability from Google Sheets.")

    st.subheader("Current Billed Credit-Card Dues")

    if credit_card_dues_df.empty:
        st.info("No credit-card due rows found for this month.")
    else:
        cc_view = credit_card_dues_df.copy()
        cc_view["Pending_Amount"] = cc_view["Pending_Number"]
        
        # Format columns as money
        for col in ["Due_Amount", "Paid_Amount", "Pending_Amount"]:
            if col in cc_view.columns:
                cc_view[col] = cc_view[col].apply(to_number).apply(money)
                
        st.dataframe(
            cc_view[
                [
                    "Month_ID", "Card_Name", "Due_Amount", "Due_Date",
                    "Status", "Paid_Amount", "Pending_Amount", "Payment_Date", "Notes"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    render_glass_metrics([
        ("Original Current Dues", money(current_card_due_total)),
        ("Current Pending Dues", money(current_card_pending)),
        ("New Card Leaks", money(new_card_leaks_amount)),
    ])

    st.subheader("Next-Cycle Liability")

    if next_cycle_df.empty:
        st.info("No next-cycle liability rows found.")
    else:
        nc_view = next_cycle_df.copy()
        nc_view["Amount"] = nc_view["Amount"].apply(to_number).apply(money)
        st.dataframe(
            nc_view[
                ["Month_ID", "Item", "Amount", "Source", "Is_Fixed", "Is_Card_Leak", "Status", "Notes"]
            ],
            use_container_width=True,
            hide_index=True
        )

    st.error(
        f"Confirmed next-cycle liability is now {money(confirmed_next_cycle_liability)}. "
        "Any new non-insurance credit-card spending increases this number."
    )


# ----------------------------
# Bills page
# ----------------------------

elif page == "Bills":
    st.title("Bills and Fixed Commitments")
    st.caption("Fixed monthly commitments from the Fixed_Commitments tab.")

    if fixed_df.empty:
        st.info("No fixed commitment rows found for this month.")
    else:
        f_view = fixed_df.copy()
        f_view["Amount"] = f_view["Amount"].apply(to_number).apply(money)
        st.dataframe(
            f_view[
                [
                    "Month_ID", "Commitment_Name", "Amount", "Payment_Mode",
                    "Due_Date", "Status", "Is_Fixed", "Notes"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    render_glass_metrics([
        ("Total Fixed Burden", money(total_fixed_burden)),
        ("Direct Bank/Cash Burden", money(direct_fixed_burden)),
        ("Credit-Card Fixed Burden", money(total_fixed_burden - direct_fixed_burden)),
    ])


# ----------------------------
# Transactions page
# ----------------------------

elif page == "Transactions":
    show_transaction_manager_page(selected_month, selected_week, week_names)


# ----------------------------
# Leaks page
# ----------------------------

elif page == "Leaks":
    st.title("Leaks")
    st.caption("This page shows expenses that can silently drain your salary.")

    if leaks_df.empty:
        st.info("No leaks logged yet.")
    else:
        leak_view = leaks_df.copy()
        leak_view["Amount_Number"] = leak_view["Amount"].apply(to_number)

        summary = (
            leak_view.groupby("Leak_Type", as_index=False)["Amount_Number"]
            .sum()
            .sort_values("Amount_Number", ascending=False)
        )
        summary["Amount"] = summary["Amount_Number"].apply(money)

        st.subheader("Leak Summary")

        st.dataframe(
            summary[["Leak_Type", "Amount"]].rename(columns={"Amount": "Total Amount"}),
            use_container_width=True,
            hide_index=True
        )

        st.subheader("Leak Details")

        leak_view_display = leak_view.copy()
        leak_view_display["Amount"] = leak_view_display["Amount_Number"].apply(money)
        st.dataframe(
            leak_view_display.sort_values("Timestamp", ascending=False)[["Leak_ID", "Timestamp", "Month_ID", "Week_Name", "Amount", "Leak_Type", "Status", "Notes"]],
            use_container_width=True,
            hide_index=True
        )

        render_glass_metrics([
            ("Total Leaks This Month", money(leak_view["Amount_Number"].sum())),
        ])


# ----------------------------
# Handloans page
# ----------------------------

elif page == "Handloans":
    st.title("Handloans")
    st.caption("Friend loans should be repaid after credit-card stability.")

    if handloans_df.empty:
        st.info("No handloan rows found.")
    else:
        handloans_view = handloans_df.copy()
        handloans_view["Balance_Number"] = handloans_view["Balance"].apply(to_number)

        hl_view = handloans_view.copy()
        for col in ["Starting_Amount", "Amount_Repaid", "Balance"]:
            if col in hl_view.columns:
                hl_view[col] = hl_view[col].apply(to_number).apply(money)

        st.dataframe(
            hl_view[["Loan_ID", "Lender", "Starting_Amount", "Amount_Repaid", "Balance", "Status", "Priority", "Notes"]],
            use_container_width=True,
            hide_index=True
        )

        render_glass_metrics([
            ("Total Handloan Balance", money(handloans_view["Balance_Number"].sum())),
        ])

    st.warning(
        "Do not aggressively repay handloans until current card dues and next-cycle liability are under control."
    )


# ----------------------------
# Settings page
# ----------------------------

elif page == "Settings":
    st.title("Settings")
    st.caption("These values come from the Settings and Categories tabs.")

    st.subheader("Settings")

    if settings_df.empty:
        st.info("No settings found.")
    else:
        st.dataframe(settings_df, use_container_width=True, hide_index=True)

    st.subheader("Categories")

    if categories_df.empty:
        st.info("No categories found.")
    else:
        st.dataframe(categories_df, use_container_width=True, hide_index=True)
