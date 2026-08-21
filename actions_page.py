import streamlit as st
import pandas as pd
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sheets_client import (
    read_sheet_with_row_numbers,
    update_row_cells,
    append_row,
)


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


def make_id(prefix):
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return f"{prefix}-{now.strftime('%Y%m%d%H%M%S')}"


@st.cache_data(ttl=10)
def load_action_tab(tab_name):
    return read_sheet_with_row_numbers(tab_name)


def filter_month(df, month_id):
    if df.empty or "Month_ID" not in df.columns:
        return df

    return df[df["Month_ID"].astype(str) == str(month_id)].copy()


def append_action_transaction(
    month_id,
    transaction_date,
    amount,
    category,
    subcategory,
    payment_mode,
    essential_type,
    notes,
):
    transaction_row = [
        make_id("TXN"),
        current_timestamp(),
        month_id,
        "Bill/Debt Payment",
        str(transaction_date),
        amount,
        category,
        subcategory,
        payment_mode,
        essential_type,
        "No",
        "No",
        notes,
        "Action Center",
    ]

    append_row("Transactions", transaction_row)


# ----------------------------
# Main Actions page
# ----------------------------

def show_actions_page(selected_month):
    st.title("Actions")
    st.caption("Update paid card bills, fixed commitments, and handloan repayments from one place.")

    try:
        credit_cards_df = load_action_tab("Credit_Card_Dues")
        fixed_df = load_action_tab("Fixed_Commitments")
        handloans_df = load_action_tab("Handloans")
    except Exception as error:
        st.error("Could not load Action Center data from Google Sheets.")
        st.exception(error)
        return

    tab_cards, tab_bills, tab_handloans = st.tabs(
        [
            "Credit Card Payments",
            "Fixed Bills",
            "Handloan Repayments",
        ]
    )

    # ----------------------------
    # Tab 1: Credit-card payments
    # ----------------------------

    with tab_cards:
        st.subheader("Mark Credit-Card Bill as Paid")
        st.caption(
            "Use this only when you actually pay a credit-card bill. "
            "This updates Credit_Card_Dues and records a cash outflow in Transactions."
        )

        cc_month = filter_month(credit_cards_df, selected_month)

        if cc_month.empty:
            st.info("No credit-card dues found for this month.")
        else:
            cc_month = cc_month.copy()
            cc_month["Due_Number"] = cc_month["Due_Amount"].apply(to_number)
            cc_month["Paid_Number"] = cc_month["Paid_Amount"].apply(to_number)
            cc_month["Pending_Number"] = (
                cc_month["Due_Number"] - cc_month["Paid_Number"]
            ).clip(lower=0)

            cc_month["Label"] = cc_month.apply(
                lambda row: (
                    f"{row['Card_Name']} | Due {money(row['Due_Number'])} | "
                    f"Paid {money(row['Paid_Number'])} | Pending {money(row['Pending_Number'])} | "
                    f"Due Date {row['Due_Date']} | Row {row['_row_number']}"
                ),
                axis=1,
            )

            cc_view = cc_month.copy()
            for col in ["Due_Amount", "Paid_Amount"]:
                if col in cc_view.columns:
                    cc_view[col] = cc_view[col].apply(to_number).apply(money)

            st.dataframe(
                cc_view[
                    [
                        "Card_Name",
                        "Due_Amount",
                        "Due_Date",
                        "Status",
                        "Paid_Amount",
                        "Payment_Date",
                        "Notes",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            selected_card_label = st.selectbox(
                "Choose card bill",
                cc_month["Label"].tolist(),
                key="actions_selected_card",
            )

            selected_card = cc_month[
                cc_month["Label"] == selected_card_label
            ].iloc[0]

            card_row_number = int(selected_card["_row_number"])
            card_name = safe_text(selected_card["Card_Name"])
            due_amount = to_number(selected_card["Due_Amount"])
            already_paid = to_number(selected_card["Paid_Amount"])
            pending_amount = max(0, due_amount - already_paid)

            if pending_amount <= 0:
                st.success("This card bill is already fully paid.")
            else:
                with st.form("credit_card_payment_form"):
                    payment_amount = st.number_input(
                        "Payment amount now",
                        min_value=1,
                        max_value=int(pending_amount),
                        value=int(pending_amount),
                        step=500,
                    )

                    payment_date = st.date_input(
                        "Payment date",
                        value=date.today(),
                    )

                    payment_mode = st.selectbox(
                        "Payment mode",
                        ["Bank Transfer", "UPI", "Debit Card"],
                    )

                    notes = st.text_input(
                        "Notes",
                        value=f"Paid {card_name} bill",
                    )

                    submitted = st.form_submit_button(
                        "Mark Credit-Card Payment",
                        type="primary",
                    )

                if submitted:
                    new_paid_total = already_paid + payment_amount

                    if new_paid_total >= due_amount:
                        new_status = "Paid"
                    else:
                        new_status = "Partially Paid"

                    update_row_cells(
                        "Credit_Card_Dues",
                        card_row_number,
                        {
                            "Status": new_status,
                            "Paid_Amount": new_paid_total,
                            "Payment_Date": str(payment_date),
                            "Notes": notes,
                        },
                    )

                    append_action_transaction(
                        month_id=selected_month,
                        transaction_date=payment_date,
                        amount=payment_amount,
                        category="Credit Card Payment",
                        subcategory=card_name,
                        payment_mode=payment_mode,
                        essential_type="Debt Payment",
                        notes=notes,
                    )

                    st.session_state["flash_message"] = (
                        f"Marked {money(payment_amount)} payment for {card_name}."
                    )
                    st.cache_data.clear()
                    st.rerun()

    # ----------------------------
    # Tab 2: Fixed bills
    # ----------------------------

    with tab_bills:
        st.subheader("Mark Fixed Commitment as Paid")
        st.caption(
            "This updates Fixed_Commitments only. "
            "Fixed commitments are already reserved in the main dashboard, so we do not add them again to Transactions."
        )

        fixed_month = filter_month(fixed_df, selected_month)

        if fixed_month.empty:
            st.info("No fixed commitments found for this month.")
        else:
            fixed_month = fixed_month.copy()
            fixed_month["Amount_Number"] = fixed_month["Amount"].apply(to_number)

            fixed_month["Label"] = fixed_month.apply(
                lambda row: (
                    f"{row['Commitment_Name']} | {money(row['Amount_Number'])} | "
                    f"{row['Payment_Mode']} | Status {row['Status']} | Row {row['_row_number']}"
                ),
                axis=1,
            )

            f_view = fixed_month.copy()
            f_view["Amount"] = f_view["Amount"].apply(to_number).apply(money)

            st.dataframe(
                f_view[
                    [
                        "Commitment_Name",
                        "Amount",
                        "Payment_Mode",
                        "Due_Date",
                        "Status",
                        "Is_Fixed",
                        "Notes",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            selected_bill_label = st.selectbox(
                "Choose fixed commitment",
                fixed_month["Label"].tolist(),
                key="actions_selected_bill",
            )

            selected_bill = fixed_month[
                fixed_month["Label"] == selected_bill_label
            ].iloc[0]

            bill_row_number = int(selected_bill["_row_number"])
            bill_name = safe_text(selected_bill["Commitment_Name"])

            with st.form("fixed_bill_form"):
                new_status = st.selectbox(
                    "New status",
                    ["Paid", "Pending"],
                    index=0,
                )

                payment_date = st.date_input(
                    "Payment / deduction date",
                    value=date.today(),
                )

                notes = st.text_input(
                    "Notes",
                    value=f"{new_status} on {payment_date}",
                )

                submitted = st.form_submit_button(
                    "Update Fixed Commitment",
                    type="primary",
                )

            if submitted:
                update_row_cells(
                    "Fixed_Commitments",
                    bill_row_number,
                    {
                        "Status": new_status,
                        "Notes": notes,
                    },
                )

                st.session_state["flash_message"] = (
                    f"Updated {bill_name} status to {new_status}."
                )
                st.cache_data.clear()
                st.rerun()

    # ----------------------------
    # Tab 3: Handloan repayments
    # ----------------------------

    with tab_handloans:
        st.subheader("Record Handloan Repayment")
        st.caption(
            "Use this only when you actually repay your friend. "
            "This updates Handloans and records a debt-payment cash outflow in Transactions."
        )

        if handloans_df.empty:
            st.info("No handloans found.")
        else:
            loans = handloans_df.copy()
            loans["Balance_Number"] = loans["Balance"].apply(to_number)
            loans["Repaid_Number"] = loans["Amount_Repaid"].apply(to_number)

            loans["Label"] = loans.apply(
                lambda row: (
                    f"{row['Lender']} | Balance {money(row['Balance_Number'])} | "
                    f"Status {row['Status']} | Row {row['_row_number']}"
                ),
                axis=1,
            )

            loans_view = loans.copy()
            for col in ["Starting_Amount", "Amount_Repaid", "Balance"]:
                if col in loans_view.columns:
                    loans_view[col] = loans_view[col].apply(to_number).apply(money)

            st.dataframe(
                loans_view[
                    [
                        "Loan_ID",
                        "Lender",
                        "Starting_Amount",
                        "Amount_Repaid",
                        "Balance",
                        "Status",
                        "Priority",
                        "Notes",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            selected_loan_label = st.selectbox(
                "Choose handloan",
                loans["Label"].tolist(),
                key="actions_selected_loan",
            )

            selected_loan = loans[
                loans["Label"] == selected_loan_label
            ].iloc[0]

            loan_row_number = int(selected_loan["_row_number"])
            lender = safe_text(selected_loan["Lender"])
            old_repaid = to_number(selected_loan["Amount_Repaid"])
            old_balance = to_number(selected_loan["Balance"])

            if old_balance <= 0:
                st.success("This handloan is already closed.")
            else:
                default_payment = min(5000, int(old_balance))

                with st.form("handloan_repayment_form"):
                    repayment_amount = st.number_input(
                        "Repayment amount",
                        min_value=1,
                        max_value=int(old_balance),
                        value=default_payment,
                        step=500,
                    )

                    repayment_date = st.date_input(
                        "Repayment date",
                        value=date.today(),
                    )

                    payment_mode = st.selectbox(
                        "Payment mode",
                        ["UPI", "Bank Transfer", "Cash"],
                    )

                    notes = st.text_input(
                        "Notes",
                        value=f"Repayment to {lender}",
                    )

                    submitted = st.form_submit_button(
                        "Record Handloan Repayment",
                        type="primary",
                    )

                if submitted:
                    new_repaid = old_repaid + repayment_amount
                    new_balance = max(0, old_balance - repayment_amount)

                    if new_balance <= 0:
                        new_status = "Closed"
                    else:
                        new_status = "Active"

                    update_row_cells(
                        "Handloans",
                        loan_row_number,
                        {
                            "Amount_Repaid": new_repaid,
                            "Balance": new_balance,
                            "Status": new_status,
                            "Notes": notes,
                        },
                    )

                    append_action_transaction(
                        month_id=selected_month,
                        transaction_date=repayment_date,
                        amount=repayment_amount,
                        category="Handloan Repayment",
                        subcategory=lender,
                        payment_mode=payment_mode,
                        essential_type="Debt Payment",
                        notes=notes,
                    )

                    st.session_state["flash_message"] = (
                        f"Recorded {money(repayment_amount)} repayment to {lender}."
                    )
                    st.cache_data.clear()
                    st.rerun()
