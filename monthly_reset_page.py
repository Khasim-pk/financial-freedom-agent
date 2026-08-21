import calendar
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from sheets_client import read_sheet, append_row


# ----------------------------
# Helper functions
# ----------------------------

def money(amount):
    try:
        return f"₹{float(amount):,.0f}"
    except Exception:
        return "₹0"


def to_number(value):
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


def current_timestamp():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return now.strftime("%Y-%m-%d %H:%M:%S")


def parse_month_id(month_id):
    try:
        year_text, month_text = str(month_id).split("-")
        year = int(year_text)
        month = int(month_text)

        if month < 1 or month > 12:
            return None, None

        return year, month
    except Exception:
        return None, None


def next_month_id(current_month_id):
    year, month = parse_month_id(current_month_id)

    if year is None:
        return "2026-07"

    if month == 12:
        return f"{year + 1}-01"

    return f"{year}-{month + 1:02d}"


def get_month_name(month_id):
    year, month = parse_month_id(month_id)

    if year is None:
        return "", ""

    return calendar.month_name[month], year


def get_setting(settings_df, key, default):
    if settings_df.empty:
        return default

    if "Key" not in settings_df.columns or "Value" not in settings_df.columns:
        return default

    matches = settings_df[settings_df["Key"].astype(str) == key]

    if matches.empty:
        return default

    return matches.iloc[0]["Value"]


def filter_month(df, month_id):
    if df.empty or "Month_ID" not in df.columns:
        return df

    return df[df["Month_ID"].astype(str) == str(month_id)].copy()


def get_week_ranges(year, month, week_count):
    last_day = calendar.monthrange(year, month)[1]

    if week_count == 5:
        ranges = [
            (1, 7),
            (8, 14),
            (15, 21),
            (22, 28),
            (29, last_day),
        ]
    else:
        ranges = [
            (1, 7),
            (8, 14),
            (15, 21),
            (22, last_day),
        ]

    clean_ranges = []

    for start_day, end_day in ranges:
        if start_day <= last_day:
            start_date = f"{year}-{month:02d}-{start_day:02d}"
            end_date = f"{year}-{month:02d}-{end_day:02d}"
            clean_ranges.append((start_date, end_date))

    return clean_ranges


@st.cache_data(ttl=10)
def load_tab(tab_name):
    return read_sheet(tab_name)


# ----------------------------
# Main page
# ----------------------------

def show_monthly_setup_page(selected_month):
    st.title("Monthly Setup / Reset")
    st.caption("Create a new month without deleting old data.")

    if "flash_message" in st.session_state:
        st.success(st.session_state.pop("flash_message"))

    try:
        months_df = load_tab("Months")
        settings_df = load_tab("Settings")
        credit_cards_df = load_tab("Credit_Card_Dues")
    except Exception as error:
        st.error("Could not load monthly setup data from Google Sheets.")
        st.exception(error)
        return

    existing_month_ids = []

    if not months_df.empty and "Month_ID" in months_df.columns:
        existing_month_ids = [
            safe_text(x)
            for x in months_df["Month_ID"].dropna().tolist()
            if safe_text(x)
        ]

    suggested_month_id = next_month_id(selected_month)

    st.subheader("Existing Months")

    if months_df.empty:
        st.info("No months found yet.")
    else:
        st.dataframe(months_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    st.subheader("Create New Month")

    previous_cc = filter_month(credit_cards_df, selected_month)

    previous_pending_total = 0
    previous_pending_rows = pd.DataFrame()

    if not previous_cc.empty:
        previous_cc = previous_cc.copy()
        previous_cc["Due_Number"] = previous_cc["Due_Amount"].apply(to_number)
        previous_cc["Paid_Number"] = previous_cc["Paid_Amount"].apply(to_number)
        previous_cc["Pending_Number"] = (
            previous_cc["Due_Number"] - previous_cc["Paid_Number"]
        ).clip(lower=0)

        previous_pending_rows = previous_cc[previous_cc["Pending_Number"] > 0].copy()
        previous_pending_total = previous_pending_rows["Pending_Number"].sum()

    if previous_pending_total > 0:
        st.warning(
            f"Selected month {selected_month} still has pending card dues of "
            f"{money(previous_pending_total)}. You can carry this forward."
        )
    else:
        st.success(f"No pending credit-card dues found in {selected_month}.")

    default_salary = int(to_number(get_setting(settings_df, "net_salary", 98000)))
    default_green_target = int(to_number(get_setting(settings_df, "weekly_green_target", 4000)))
    default_practical_target = int(to_number(get_setting(settings_df, "weekly_practical_target", 4500)))
    default_hard_cap = int(to_number(get_setting(settings_df, "weekly_hard_cap", 6000)))

    with st.form("monthly_reset_form"):
        st.write("### 1. Month Details")

        col1, col2, col3 = st.columns(3)

        with col1:
            new_month_id = st.text_input(
                "New Month ID",
                value=suggested_month_id,
                help="Use YYYY-MM format, for example 2026-07.",
            )

        month_name, year_value = get_month_name(new_month_id)

        with col2:
            st.text_input("Month Name", value=month_name, disabled=True)

        with col3:
            st.text_input("Year", value=str(year_value), disabled=True)

        opening_bank_cash = st.number_input(
            "Opening Bank Cash",
            min_value=0,
            value=0,
            step=500,
            help="Enter the bank balance available at the start of this new month.",
        )

        salary_received = st.number_input(
            "Salary Received",
            min_value=0,
            value=default_salary,
            step=500,
        )

        handloan_received = st.number_input(
            "New Handloan Received This Month",
            min_value=0,
            value=0,
            step=500,
            help="Usually 0 for future months unless you take a new handloan.",
        )

        status = st.selectbox(
            "Month Status",
            ["Emergency", "Recovery", "Stabilising", "Savings Mode"],
            index=0,
        )

        st.write("### 2. Fixed Monthly Commitments")

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            home_loan = st.number_input("Home Loan EMI", min_value=0, value=27000, step=500)
            personal_loan = st.number_input("Personal Loan EMI", min_value=0, value=20000, step=500)

        with col_b:
            govt_loan = st.number_input("Govt Loan EMI", min_value=0, value=8500, step=500)
            rent = st.number_input("House Rent", min_value=0, value=10000, step=500)

        with col_c:
            insurance = st.number_input(
                "Parents Health + Term Insurance",
                min_value=0,
                value=8000,
                step=500,
            )

            insurance_payment_mode = st.selectbox(
                "Insurance Payment Mode",
                ["Credit Card Auto-Debit", "UPI/Debit", "Bank Deduction"],
                index=0,
            )

        fixed_burden = home_loan + personal_loan + govt_loan + rent + insurance

        st.info(f"Total fixed monthly burden for new month: {money(fixed_burden)}")

        st.write("### 3. Current Credit-Card Bills for New Month")

        carry_forward_pending = st.checkbox(
            f"Carry forward unpaid card dues from {selected_month}: {money(previous_pending_total)}",
            value=previous_pending_total > 0,
            disabled=previous_pending_total <= 0,
        )

        st.caption("Enter the card bills that are already billed and due in the new month. Leave amount as 0 if not applicable.")

        card_entries = []

        for index in range(1, 4):
            st.write(f"Card Bill {index}")

            c1, c2, c3 = st.columns(3)

            with c1:
                card_name = st.text_input(
                    f"Card {index} Name",
                    value=f"Credit Card {index}",
                    key=f"card_name_{index}",
                )

            with c2:
                card_amount = st.number_input(
                    f"Card {index} Due Amount",
                    min_value=0,
                    value=0,
                    step=500,
                    key=f"card_amount_{index}",
                )

            with c3:
                card_due_date = st.text_input(
                    f"Card {index} Due Date",
                    value="",
                    placeholder="Example: 4th",
                    key=f"card_due_{index}",
                )

            card_entries.append(
                {
                    "name": card_name,
                    "amount": card_amount,
                    "due_date": card_due_date,
                }
            )

        st.write("### 4. Next-Cycle Credit-Card Liability")

        existing_unbilled = st.number_input(
            "Existing Unbilled Transactions for Next Statement",
            min_value=0,
            value=0,
            step=500,
            help="Enter current unbilled amount after statement generation or at month start.",
        )

        include_insurance_in_next_cycle = st.checkbox(
            "Include insurance in next-cycle card liability",
            value=insurance_payment_mode == "Credit Card Auto-Debit" and insurance > 0,
            help="Keep this ON while insurance is still charged to the credit card.",
        )

        next_cycle_liability = existing_unbilled

        if include_insurance_in_next_cycle:
            next_cycle_liability += insurance

        st.info(f"Next-cycle liability for new month: {money(next_cycle_liability)}")

        st.write("### 5. Weekly Envelopes")

        week_count = st.selectbox(
            "Number of weekly envelopes",
            [4, 5],
            index=0,
            help="Use 4 for strict recovery mode. Use 5 only if you want a separate final-week envelope.",
        )

        weekly_green_target = st.number_input(
            "Weekly Green Target",
            min_value=0,
            value=default_green_target,
            step=100,
        )

        weekly_practical_target = st.number_input(
            "Weekly Practical Target",
            min_value=0,
            value=default_practical_target,
            step=100,
        )

        weekly_hard_cap = st.number_input(
            "Weekly Hard Cap",
            min_value=0,
            value=default_hard_cap,
            step=100,
        )

        submitted = st.form_submit_button("Create New Month", type="primary")

    if submitted:
        year, month = parse_month_id(new_month_id)

        if year is None:
            st.error("Invalid Month ID. Use YYYY-MM format, for example 2026-07.")
            return

        if new_month_id in existing_month_ids:
            st.error(f"{new_month_id} already exists. Choose a new Month ID.")
            return

        month_name, year_value = get_month_name(new_month_id)

        direct_card_total = sum(entry["amount"] for entry in card_entries)
        carry_forward_total = previous_pending_total if carry_forward_pending else 0
        current_card_dues_total = direct_card_total + carry_forward_total

        rows_created = 0

        # Months row
        append_row(
            "Months",
            [
                new_month_id,
                month_name,
                year_value,
                opening_bank_cash,
                salary_received,
                handloan_received,
                fixed_burden,
                current_card_dues_total,
                next_cycle_liability,
                status,
            ],
        )
        rows_created += 1

        # Fixed commitments
        fixed_rows = [
            [
                new_month_id,
                "Home Loan EMI",
                home_loan,
                "Bank Deduction",
                "Monthly",
                "Pending",
                "Yes",
                "Hard commitment",
            ],
            [
                new_month_id,
                "Personal Loan EMI",
                personal_loan,
                "Bank Deduction",
                "Monthly",
                "Pending",
                "Yes",
                "Hard commitment",
            ],
            [
                new_month_id,
                "Govt Loan EMI",
                govt_loan,
                "Bank Deduction",
                "Monthly",
                "Pending",
                "Yes",
                "Hard commitment",
            ],
            [
                new_month_id,
                "House Rent",
                rent,
                "Cash/UPI",
                "Monthly",
                "Pending",
                "Yes",
                "Rent",
            ],
            [
                new_month_id,
                "Parents Health + Term Insurance",
                insurance,
                insurance_payment_mode,
                "Monthly",
                "Pending",
                "Yes",
                "Protected fixed bill",
            ],
        ]

        for row in fixed_rows:
            append_row("Fixed_Commitments", row)
            rows_created += 1

        # Carry-forward card dues
        if carry_forward_pending and not previous_pending_rows.empty:
            for _, row in previous_pending_rows.iterrows():
                pending_amount = to_number(row.get("Pending_Number", 0))

                if pending_amount > 0:
                    append_row(
                        "Credit_Card_Dues",
                        [
                            new_month_id,
                            f"Carry Forward - {safe_text(row.get('Card_Name'))}",
                            pending_amount,
                            safe_text(row.get("Due_Date")),
                            "Pending",
                            0,
                            "",
                            f"Carried forward from {selected_month}",
                        ],
                    )
                    rows_created += 1

        # New card dues
        for entry in card_entries:
            if entry["amount"] > 0:
                append_row(
                    "Credit_Card_Dues",
                    [
                        new_month_id,
                        entry["name"],
                        entry["amount"],
                        entry["due_date"],
                        "Pending",
                        0,
                        "",
                        "Created during monthly reset",
                    ],
                )
                rows_created += 1

        # Next-cycle liability rows
        if existing_unbilled > 0:
            append_row(
                "Next_Cycle_Liability",
                [
                    new_month_id,
                    "Existing Unbilled Transactions",
                    existing_unbilled,
                    "Credit Card",
                    "No",
                    "No",
                    "Pending",
                    "Entered during monthly reset",
                ],
            )
            rows_created += 1

        if include_insurance_in_next_cycle and insurance > 0:
            append_row(
                "Next_Cycle_Liability",
                [
                    new_month_id,
                    "Insurance Auto-Debit",
                    insurance,
                    "Credit Card",
                    "Yes",
                    "No",
                    "Pending",
                    "Protected fixed bill",
                ],
            )
            rows_created += 1

        # Weekly envelopes
        week_ranges = get_week_ranges(year, month, week_count)

        for index, date_range in enumerate(week_ranges, start=1):
            start_date, end_date = date_range

            append_row(
                "Weekly_Envelopes",
                [
                    new_month_id,
                    f"Week {index}",
                    start_date,
                    end_date,
                    weekly_green_target,
                    weekly_practical_target,
                    weekly_hard_cap,
                    0,
                    "Not Started",
                    "Created during monthly reset",
                ],
            )
            rows_created += 1

        st.session_state["flash_message"] = (
            f"Created {new_month_id} successfully. Rows created: {rows_created}."
        )

        st.cache_data.clear()
        st.rerun()
