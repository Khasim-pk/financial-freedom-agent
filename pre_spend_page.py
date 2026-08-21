import pandas as pd
import streamlit as st

from sheets_client import read_sheet
from pre_spend_engine import evaluate_pre_spend, money


PRE_SPEND_TABS = [
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


PAYMENT_MODES = [
    "UPI",
    "Debit Card",
    "Cash",
    "Credit Card",
    "Amazon Pay Coupon",
    "Bank Transfer",
]


FALLBACK_CATEGORIES = [
    "Groceries",
    "Milk",
    "Home Essentials",
    "Utilities",
    "Recharges",
    "Transport",
    "Medical",
    "Eating Out",
    "Quick Commerce",
    "Treats",
    "Shopping",
    "Coupon Masking",
    "Credit Card Leak",
    "Unknown Leak",
    "Insurance",
]


@st.cache_data(ttl=10)
def load_pre_spend_data():
    data = {}

    for tab in PRE_SPEND_TABS:
        data[tab] = read_sheet(tab)

    return data


def safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def get_category_options(categories_df):
    if categories_df is None or categories_df.empty or "Category" not in categories_df.columns:
        return FALLBACK_CATEGORIES

    options = [
        safe_text(x)
        for x in categories_df["Category"].dropna().tolist()
        if safe_text(x)
    ]

    for category in FALLBACK_CATEGORIES:
        if category not in options:
            options.append(category)

    return options


def show_decision_box(decision_result):
    decision = decision_result["decision"]
    style = decision_result["style"]

    css_class = str(decision).replace(" ", "-")

    html = f'<div class="decision-card {css_class}"><div class="decision-header"><span style="font-size: 2.2rem; line-height: 1;">{style["emoji"]}</span><div><div class="decision-title">{decision} — {style["tone"]}</div><div class="decision-message">{style["message"]}</div></div></div></div>'
    st.markdown(html, unsafe_allow_html=True)


def show_pre_spend_page(selected_month, selected_week):
    st.title("Can I Spend?")
    st.caption("Check a spend before doing it. This helps prevent credit-card relapse and weekly budget damage.")

    if st.button("Refresh pre-spend data"):
        st.cache_data.clear()
        st.rerun()

    try:
        data = load_pre_spend_data()
    except Exception as error:
        st.error("Could not load pre-spend data from Google Sheets.")
        st.exception(error)
        return

    categories_df = data.get("Categories", pd.DataFrame())
    category_options = get_category_options(categories_df)

    st.subheader("Ask Before Spending")

    with st.form("pre_spend_form"):
        col1, col2 = st.columns(2)

        with col1:
            amount = st.number_input(
                "Amount you want to spend",
                min_value=0,
                step=50,
                value=0,
            )

            category = st.selectbox(
                "Category",
                category_options,
            )

        with col2:
            payment_mode = st.selectbox(
                "Payment Mode",
                PAYMENT_MODES,
            )

            notes = st.text_input(
                "What is this for?",
                placeholder="Example: dinner, power bill, D-Mart essentials, ice cream",
            )

        submitted = st.form_submit_button("Check Spend", type="primary")

    if not submitted:
        st.info(
            "Enter an amount, category, and payment mode, then click Check Spend. "
            "The system will compare it with weekly limits, card dues, next-cycle liability, and recovery buffer."
        )

        st.subheader("Example Checks")

        examples = pd.DataFrame(
            [
                ["₹450 groceries by UPI", "Usually Approved if weekly budget allows"],
                ["₹1,200 dinner by UPI", "Often Not Recommended during recovery"],
                ["₹800 D-Mart by credit card", "Blocked because it uses credit card"],
                ["₹500 Blinkit snacks", "Not Recommended because it is leakage"],
                ["₹2,300 power bill by UPI", "May be Approved or Caution depending on weekly balance"],
            ],
            columns=["Question", "Likely Decision"]
        )

        st.dataframe(examples, use_container_width=True, hide_index=True)
        return

    decision_result = evaluate_pre_spend(
        data=data,
        selected_month=selected_month,
        selected_week=selected_week,
        amount=amount,
        category=category,
        payment_mode=payment_mode,
        notes=notes,
    )

    show_decision_box(decision_result)

    st.subheader("Why")

    reasons = decision_result["reasons"]

    for reason in reasons:
        st.write(f"- {reason}")

    st.subheader("Recommended Action")

    for action in decision_result["recommended_action"]:
        st.write(f"- {action}")

    st.subheader("Impact Preview")

    metrics = decision_result["metrics"]

    metric_rows = [
        ["Current weekly spend", money(metrics["Current Weekly Spend"])],
        ["Projected weekly spend", money(metrics["Projected Weekly Spend"])],
        ["Weekly practical target", money(metrics["Weekly Practical Target"])],
        ["Weekly hard cap", money(metrics["Weekly Hard Cap"])],
        ["Projected target left", money(metrics["Projected Target Left"])],
        ["Projected hard cap left", money(metrics["Projected Hard Cap Left"])],
        ["Current card pending", money(metrics["Current Card Pending"])],
        ["Current next-cycle liability", money(metrics["Current Next-Cycle Liability"])],
        ["Projected next-cycle liability", money(metrics["Projected Next-Cycle Liability"])],
        ["Current recovery buffer", money(metrics["Current Recovery Buffer"])],
        ["Projected recovery buffer", money(metrics["Projected Recovery Buffer"])],
        ["Category type", decision_result["category_type"]],
        ["Risk level", decision_result["risk_level"]],
    ]

    st.dataframe(
        pd.DataFrame(metric_rows, columns=["Metric", "Value"]),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "This page only gives a decision. It does not save a transaction. "
        "If you actually spend, log it from Transactions or later from Telegram."
    )
