import streamlit as st
import pandas as pd
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sheets_client import (
    read_sheet_with_row_numbers,
    append_row,
    append_rows,
    update_row_cells,
    delete_row,
    delete_rows,
)


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
    "Credit Card Payment",
    "Handloan Repayment",
]


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


def current_timestamp():
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return now.strftime("%Y-%m-%d %H:%M:%S")


def make_id(prefix):
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return f"{prefix}-{now.strftime('%Y%m%d%H%M%S%f')}"


def parse_date(value):
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return date.today()


def index_or_zero(options, value):
    value = safe_text(value)

    if value in options:
        return options.index(value)

    return 0


@st.cache_data(ttl=10)
def load_tm_tab(tab_name):
    return read_sheet_with_row_numbers(tab_name)


def filter_month(df, month_id):
    if df.empty or "Month_ID" not in df.columns:
        return df

    selected_month = normalize_month_id(month_id)

    return df[
        df["Month_ID"].apply(normalize_month_id) == selected_month
    ].copy()


def get_category_options(categories_df):
    if categories_df.empty or "Category" not in categories_df.columns:
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


def get_category_info(categories_df, category_name):
    if categories_df.empty or "Category" not in categories_df.columns:
        return {
            "Type": "Unknown",
            "Risk_Level": "Unknown",
        }

    matches = categories_df[
        categories_df["Category"].astype(str).str.strip() == safe_text(category_name)
    ]

    if matches.empty:
        return {
            "Type": "Unknown",
            "Risk_Level": "Unknown",
        }

    row = matches.iloc[0]

    return {
        "Type": safe_text(row.get("Type", "Unknown")),
        "Risk_Level": safe_text(row.get("Risk_Level", "Unknown")),
    }


def calculate_flags(categories_df, category, payment_mode):
    category_info = get_category_info(categories_df, category)
    category_type = category_info["Type"]
    risk_level = category_info["Risk_Level"]

    is_credit_card_leak = (
        "Yes"
        if payment_mode == "Credit Card" and category != "Insurance"
        else "No"
    )

    is_unknown = "Yes" if category == "Unknown Leak" else "No"

    return {
        "category_type": category_type,
        "risk_level": risk_level,
        "is_credit_card_leak": is_credit_card_leak,
        "is_unknown": is_unknown,
    }


def is_leak_transaction(
    category,
    payment_mode,
    category_type,
    risk_level,
    is_credit_card_leak,
    is_unknown,
):
    category = safe_text(category)
    payment_mode = safe_text(payment_mode)
    category_type = safe_text(category_type)
    risk_level = safe_text(risk_level)

    if is_credit_card_leak == "Yes":
        return True

    if is_unknown == "Yes":
        return True

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
    category = safe_text(category)
    payment_mode = safe_text(payment_mode)

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


def make_transaction_label(row):
    transaction_id = safe_text(row.get("Transaction_ID"))
    txn_date = safe_text(row.get("Date"))
    amount = money(to_number(row.get("Amount")))
    category = safe_text(row.get("Category"))
    subcategory = safe_text(row.get("Subcategory"))
    payment_mode = safe_text(row.get("Payment_Mode"))
    row_number = safe_text(row.get("_row_number"))

    return (
        f"{transaction_id} | {txn_date} | {amount} | "
        f"{category} | {subcategory} | {payment_mode} | Row {row_number}"
    )


def append_transaction(
    month_id,
    week_name,
    transaction_date,
    amount,
    category,
    subcategory,
    payment_mode,
    notes,
    source,
    categories_df,
):
    flags = calculate_flags(categories_df, category, payment_mode)

    transaction_row = [
        make_id("TXN"),
        current_timestamp(),
        month_id,
        week_name,
        str(transaction_date),
        amount,
        category,
        subcategory,
        payment_mode,
        flags["category_type"],
        flags["is_credit_card_leak"],
        flags["is_unknown"],
        notes,
        source,
    ]

    append_row("Transactions", transaction_row)


def sync_leaks_for_month(month_id):
    """
    Rebuilds the Leaks tab for one month based on current Transactions.
    This prevents old leak rows from staying after edits, deletes, or splits.
    """
    leaks_df = read_sheet_with_row_numbers("Leaks")

    if not leaks_df.empty and "Month_ID" in leaks_df.columns:
        selected_month = normalize_month_id(month_id)
        rows_to_delete = leaks_df[
            leaks_df["Month_ID"].apply(normalize_month_id) == selected_month
        ]["_row_number"].tolist()

        delete_rows("Leaks", rows_to_delete)

    transactions_df = read_sheet_with_row_numbers("Transactions")
    categories_df = read_sheet_with_row_numbers("Categories")

    if transactions_df.empty or "Month_ID" not in transactions_df.columns:
        return 0

    selected_month = normalize_month_id(month_id)
    month_tx = transactions_df[
        transactions_df["Month_ID"].apply(normalize_month_id) == selected_month
    ].copy()

    if month_tx.empty:
        return 0

    leak_rows = []

    for _, row in month_tx.iterrows():
        category = safe_text(row.get("Category"))
        payment_mode = safe_text(row.get("Payment_Mode"))
        amount = to_number(row.get("Amount"))

        category_info = get_category_info(categories_df, category)
        category_type = safe_text(row.get("Essential_Type")) or category_info["Type"]
        risk_level = category_info["Risk_Level"]

        is_credit_card_leak = safe_text(row.get("Is_Credit_Card_Leak"))
        is_unknown = safe_text(row.get("Is_Unknown"))

        if payment_mode == "Credit Card" and category != "Insurance":
            is_credit_card_leak = "Yes"

        if category == "Unknown Leak":
            is_unknown = "Yes"

        should_log_leak = is_leak_transaction(
            category=category,
            payment_mode=payment_mode,
            category_type=category_type,
            risk_level=risk_level,
            is_credit_card_leak=is_credit_card_leak,
            is_unknown=is_unknown,
        )

        if should_log_leak:
            leak_type = get_leak_type(
                category,
                payment_mode,
                is_credit_card_leak,
                is_unknown,
            )

            notes = safe_text(row.get("Notes")) or safe_text(row.get("Subcategory"))

            leak_rows.append(
                [
                    make_id("LEAK"),
                    current_timestamp(),
                    month_id,
                    safe_text(row.get("Week_Name")),
                    amount,
                    leak_type,
                    "Open",
                    notes,
                ]
            )

    append_rows("Leaks", leak_rows)

    return len(leak_rows)


def get_week_options(week_names):
    options = list(week_names)

    if "Bill/Debt Payment" not in options:
        options.append("Bill/Debt Payment")

    return options


def show_selected_transaction_card(selected_tx):
    st.write("### Selected Transaction")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Amount", money(to_number(selected_tx.get("Amount"))))
    col2.metric("Category", safe_text(selected_tx.get("Category")))
    col3.metric("Payment Mode", safe_text(selected_tx.get("Payment_Mode")))
    col4.metric("Week", safe_text(selected_tx.get("Week_Name")))

    display_fields = {
        "Transaction ID": safe_text(selected_tx.get("Transaction_ID")),
        "Date": safe_text(selected_tx.get("Date")),
        "Subcategory": safe_text(selected_tx.get("Subcategory")),
        "Notes": safe_text(selected_tx.get("Notes")),
        "Credit Card Leak": safe_text(selected_tx.get("Is_Credit_Card_Leak")),
        "Unknown": safe_text(selected_tx.get("Is_Unknown")),
        "Source": safe_text(selected_tx.get("Source")),
    }

    st.dataframe(
        pd.DataFrame(display_fields.items(), columns=["Field", "Value"]),
        use_container_width=True,
        hide_index=True,
    )


# ----------------------------
# Main page
# ----------------------------

def show_transaction_manager_page(selected_month, selected_week, week_names):
    st.title("Transaction Manager")
    st.caption("Single-page view for adding, correcting, splitting, deleting, and syncing transactions.")

    if "flash_message" in st.session_state:
        st.success(st.session_state.pop("flash_message"))

    try:
        transactions_df = load_tm_tab("Transactions")
        categories_df = load_tm_tab("Categories")
    except Exception as error:
        st.error("Could not load transaction data from Google Sheets.")
        st.exception(error)
        return

    category_options = get_category_options(categories_df)
    week_options = get_week_options(week_names)
    transactions_month = filter_month(transactions_df, selected_month)

    # ----------------------------
    # 1. Quick Add Transaction
    # ----------------------------

    with st.expander("1. Quick Add Transaction", expanded=True):
        st.caption("Use this for manual dashboard entries. Telegram entries will come later.")

        with st.form("single_add_transaction_form"):
            col1, col2 = st.columns(2)

            with col1:
                txn_date = st.date_input(
                    "Date",
                    value=date.today(),
                    key="single_add_date",
                )

                week_name = st.selectbox(
                    "Week",
                    week_options,
                    index=index_or_zero(week_options, selected_week),
                    key="single_add_week",
                )

                amount = st.number_input(
                    "Amount",
                    min_value=0,
                    step=50,
                    key="single_add_amount",
                )

            with col2:
                category = st.selectbox(
                    "Category",
                    category_options,
                    key="single_add_category",
                )

                payment_mode = st.selectbox(
                    "Payment Mode",
                    PAYMENT_MODES,
                    key="single_add_payment_mode",
                )

                subcategory = st.text_input(
                    "Subcategory / Item",
                    placeholder="Example: vegetables and rice",
                    key="single_add_subcategory",
                )

            notes = st.text_input(
                "Notes",
                placeholder="Optional",
                key="single_add_notes",
            )

            submitted = st.form_submit_button("Save Transaction", type="primary")

        if submitted:
            if amount <= 0:
                st.error("Amount must be greater than 0.")
            else:
                append_transaction(
                    month_id=selected_month,
                    week_name=week_name,
                    transaction_date=txn_date,
                    amount=amount,
                    category=category,
                    subcategory=subcategory,
                    payment_mode=payment_mode,
                    notes=notes,
                    source="Transaction Manager",
                    categories_df=categories_df,
                )

                leak_count = sync_leaks_for_month(selected_month)

                st.session_state["flash_message"] = (
                    f"Transaction added. Leak table synced with {leak_count} leak rows."
                )
                st.cache_data.clear()
                st.rerun()

    # ----------------------------
    # 2. This Month's Transactions
    # ----------------------------

    st.write("## 2. This Month's Transactions")

    if transactions_month.empty:
        st.info("No transactions found for this month yet.")
        st.write("Use Quick Add Transaction above to add your first transaction.")
        st.markdown("---")
        st.write("## 3. Sync Leaks")
        if st.button("Rebuild Leak Table for Selected Month", type="primary"):
            leak_count = sync_leaks_for_month(selected_month)
            st.session_state["flash_message"] = (
                f"Leak table rebuilt for {selected_month}. Current leak rows: {leak_count}."
            )
            st.cache_data.clear()
            st.rerun()
        return

    view = transactions_month.copy()
    view["Amount_Number"] = view["Amount"].apply(to_number)
    view["Label"] = view.apply(make_transaction_label, axis=1)

    total_logged = view["Amount_Number"].sum()
    total_credit_card_leaks = view[
        view["Is_Credit_Card_Leak"].astype(str) == "Yes"
    ]["Amount_Number"].sum()
    total_unknowns = view[
        (view["Category"].astype(str) == "Unknown Leak")
        | (view["Is_Unknown"].astype(str) == "Yes")
    ]["Amount_Number"].sum()

    render_glass_metrics([
        ("Total Logged", money(total_logged)),
        ("Credit-Card Leaks", money(total_credit_card_leaks)),
        ("Unknown Expenses", money(total_unknowns)),
    ])

    search_text = st.text_input(
        "Search transactions",
        placeholder="Search by category, item, payment mode, notes, amount...",
    )

    filtered_view = view.copy()

    if search_text.strip():
        search = search_text.lower().strip()

        searchable = filtered_view[
            [
                "Transaction_ID",
                "Date",
                "Amount",
                "Category",
                "Subcategory",
                "Payment_Mode",
                "Notes",
                "Source",
            ]
        ].astype(str).agg(" ".join, axis=1).str.lower()

        filtered_view = filtered_view[searchable.str.contains(search, na=False)]

    if filtered_view.empty:
        st.warning("No transactions matched your search.")
        return

    display_cols = [
        "Date",
        "Week_Name",
        "Amount",
        "Category",
        "Subcategory",
        "Payment_Mode",
        "Is_Credit_Card_Leak",
        "Is_Unknown",
        "Source",
        "Notes",
    ]

    available_display_cols = [
        col for col in display_cols if col in filtered_view.columns
    ]

    st.dataframe(
        filtered_view.sort_values("Timestamp", ascending=False)[available_display_cols],
        use_container_width=True,
        hide_index=True,
    )

    # ----------------------------
    # 3. Select One Transaction
    # ----------------------------

    st.write("## 3. Select One Transaction")

    selected_label = st.selectbox(
        "Choose a transaction to manage",
        filtered_view["Label"].tolist(),
        key="single_selected_transaction",
    )

    selected_tx = filtered_view[filtered_view["Label"] == selected_label].iloc[0]
    selected_row_number = int(selected_tx["_row_number"])
    selected_transaction_id = safe_text(selected_tx.get("Transaction_ID"))
    selected_category = safe_text(selected_tx.get("Category"))
    selected_payment_mode = safe_text(selected_tx.get("Payment_Mode"))
    selected_week_value = safe_text(selected_tx.get("Week_Name"))
    selected_source = safe_text(selected_tx.get("Source"))

    show_selected_transaction_card(selected_tx)

    if selected_category in ["Credit Card Payment", "Handloan Repayment"] or selected_source == "Action Center":
        st.warning(
            "This transaction appears to be connected to Action Center. "
            "Editing or deleting it here will not automatically undo the related card bill or handloan balance update."
        )

    st.markdown("---")

    # ----------------------------
    # 4. Edit Selected Transaction
    # ----------------------------

    with st.expander("4. Edit Selected Transaction", expanded=False):
        with st.form("single_edit_transaction_form"):
            col1, col2 = st.columns(2)

            with col1:
                edit_date = st.date_input(
                    "Date",
                    value=parse_date(selected_tx.get("Date")),
                    key=f"single_edit_date_{selected_transaction_id}",
                )

                edit_week = st.selectbox(
                    "Week",
                    week_options,
                    index=index_or_zero(week_options, selected_week_value),
                    key=f"single_edit_week_{selected_transaction_id}",
                )

                edit_amount = st.number_input(
                    "Amount",
                    min_value=0,
                    value=int(to_number(selected_tx.get("Amount"))),
                    step=50,
                    key=f"single_edit_amount_{selected_transaction_id}",
                )

            with col2:
                edit_category = st.selectbox(
                    "Category",
                    category_options,
                    index=index_or_zero(category_options, selected_category),
                    key=f"single_edit_category_{selected_transaction_id}",
                )

                edit_payment_mode = st.selectbox(
                    "Payment Mode",
                    PAYMENT_MODES,
                    index=index_or_zero(PAYMENT_MODES, selected_payment_mode),
                    key=f"single_edit_payment_{selected_transaction_id}",
                )

                edit_subcategory = st.text_input(
                    "Subcategory / Item",
                    value=safe_text(selected_tx.get("Subcategory")),
                    key=f"single_edit_subcategory_{selected_transaction_id}",
                )

            edit_notes = st.text_input(
                "Notes",
                value=safe_text(selected_tx.get("Notes")),
                key=f"single_edit_notes_{selected_transaction_id}",
            )

            edit_submitted = st.form_submit_button("Save Edited Transaction", type="primary")

        if edit_submitted:
            if edit_amount <= 0:
                st.error("Amount must be greater than 0.")
            else:
                flags = calculate_flags(categories_df, edit_category, edit_payment_mode)

                update_row_cells(
                    "Transactions",
                    selected_row_number,
                    {
                        "Week_Name": edit_week,
                        "Date": str(edit_date),
                        "Amount": edit_amount,
                        "Category": edit_category,
                        "Subcategory": edit_subcategory,
                        "Payment_Mode": edit_payment_mode,
                        "Essential_Type": flags["category_type"],
                        "Is_Credit_Card_Leak": flags["is_credit_card_leak"],
                        "Is_Unknown": flags["is_unknown"],
                        "Notes": edit_notes,
                    },
                )

                leak_count = sync_leaks_for_month(selected_month)

                st.session_state["flash_message"] = (
                    f"Transaction updated. Leak table synced with {leak_count} leak rows."
                )
                st.cache_data.clear()
                st.rerun()

    # ----------------------------
    # 5. Split Selected Transaction
    # ----------------------------

    with st.expander("5. Split Selected Transaction", expanded=False):
        st.caption(
            "Use this when one transaction contains mixed spending. "
            "Example: Blinkit ₹650 = ₹400 groceries + ₹250 snacks."
        )

        original_amount = to_number(selected_tx.get("Amount"))

        st.info(f"Original amount: {money(original_amount)}")

        with st.form("single_split_transaction_form"):
            st.write("### Split 1")

            col1, col2 = st.columns(2)

            with col1:
                split1_amount = st.number_input(
                    "Split 1 Amount",
                    min_value=0,
                    value=0,
                    step=50,
                    key=f"single_split1_amount_{selected_transaction_id}",
                )

                split1_category = st.selectbox(
                    "Split 1 Category",
                    category_options,
                    index=index_or_zero(category_options, selected_category),
                    key=f"single_split1_category_{selected_transaction_id}",
                )

            with col2:
                split1_payment_mode = st.selectbox(
                    "Split 1 Payment Mode",
                    PAYMENT_MODES,
                    index=index_or_zero(PAYMENT_MODES, selected_payment_mode),
                    key=f"single_split1_payment_{selected_transaction_id}",
                )

                split1_subcategory = st.text_input(
                    "Split 1 Subcategory",
                    value=safe_text(selected_tx.get("Subcategory")),
                    key=f"single_split1_subcategory_{selected_transaction_id}",
                )

            st.write("### Split 2")

            col3, col4 = st.columns(2)

            with col3:
                split2_amount = st.number_input(
                    "Split 2 Amount",
                    min_value=0,
                    value=0,
                    step=50,
                    key=f"single_split2_amount_{selected_transaction_id}",
                )

                split2_category = st.selectbox(
                    "Split 2 Category",
                    category_options,
                    key=f"single_split2_category_{selected_transaction_id}",
                )

            with col4:
                split2_payment_mode = st.selectbox(
                    "Split 2 Payment Mode",
                    PAYMENT_MODES,
                    index=index_or_zero(PAYMENT_MODES, selected_payment_mode),
                    key=f"single_split2_payment_{selected_transaction_id}",
                )

                split2_subcategory = st.text_input(
                    "Split 2 Subcategory",
                    key=f"single_split2_subcategory_{selected_transaction_id}",
                )

            split_notes = st.text_input(
                "Split Notes",
                value=f"Split from {selected_transaction_id}",
                key=f"single_split_notes_{selected_transaction_id}",
            )

            split_confirm = st.checkbox(
                "I understand this will replace the original transaction with two new transactions.",
                key=f"single_split_confirm_{selected_transaction_id}",
            )

            split_submitted = st.form_submit_button("Split Transaction", type="primary")

        if split_submitted:
            total_split = split1_amount + split2_amount

            if not split_confirm:
                st.error("Please tick the confirmation checkbox before splitting.")
            elif split1_amount <= 0 or split2_amount <= 0:
                st.error("Both split amounts must be greater than 0.")
            elif abs(total_split - original_amount) > 0.01:
                st.error(
                    f"Split amounts must equal original amount. "
                    f"Current split total is {money(total_split)}, original is {money(original_amount)}."
                )
            else:
                original_date = parse_date(selected_tx.get("Date"))

                delete_row("Transactions", selected_row_number)

                append_transaction(
                    month_id=selected_month,
                    week_name=selected_week_value,
                    transaction_date=original_date,
                    amount=split1_amount,
                    category=split1_category,
                    subcategory=split1_subcategory,
                    payment_mode=split1_payment_mode,
                    notes=split_notes,
                    source="Transaction Manager Split",
                    categories_df=categories_df,
                )

                append_transaction(
                    month_id=selected_month,
                    week_name=selected_week_value,
                    transaction_date=original_date,
                    amount=split2_amount,
                    category=split2_category,
                    subcategory=split2_subcategory,
                    payment_mode=split2_payment_mode,
                    notes=split_notes,
                    source="Transaction Manager Split",
                    categories_df=categories_df,
                )

                leak_count = sync_leaks_for_month(selected_month)

                st.session_state["flash_message"] = (
                    f"Transaction split successfully. Leak table synced with {leak_count} leak rows."
                )
                st.cache_data.clear()
                st.rerun()

    # ----------------------------
    # 6. Delete Selected Transaction
    # ----------------------------

    with st.expander("6. Delete Selected Transaction", expanded=False):
        st.warning(
            "Delete carefully. This permanently removes the transaction row from Google Sheets."
        )

        with st.form("single_delete_transaction_form"):
            delete_confirm = st.checkbox(
                "I understand. Delete this transaction permanently.",
                key=f"single_delete_confirm_{selected_transaction_id}",
            )

            delete_submitted = st.form_submit_button("Delete Transaction", type="primary")

        if delete_submitted:
            if not delete_confirm:
                st.error("Please tick the confirmation checkbox before deleting.")
            else:
                delete_row("Transactions", selected_row_number)
                leak_count = sync_leaks_for_month(selected_month)

                st.session_state["flash_message"] = (
                    f"Transaction deleted. Leak table synced with {leak_count} leak rows."
                )
                st.cache_data.clear()
                st.rerun()

    # ----------------------------
    # 7. Resolve Unknown Expense
    # ----------------------------

    with st.expander("7. Resolve Unknown Expense", expanded=False):
        is_selected_unknown = (
            selected_category == "Unknown Leak"
            or safe_text(selected_tx.get("Is_Unknown")) == "Yes"
        )

        if not is_selected_unknown:
            st.info("The selected transaction is not marked as Unknown Leak.")
        else:
            st.caption("Classify this unknown expense into the correct category.")

            with st.form("single_resolve_unknown_form"):
                resolve_category = st.selectbox(
                    "Correct Category",
                    category_options,
                    index=index_or_zero(category_options, "Groceries"),
                    key=f"single_resolve_category_{selected_transaction_id}",
                )

                resolve_payment_mode = st.selectbox(
                    "Payment Mode",
                    PAYMENT_MODES,
                    index=index_or_zero(PAYMENT_MODES, selected_payment_mode),
                    key=f"single_resolve_payment_{selected_transaction_id}",
                )

                resolve_subcategory = st.text_input(
                    "Subcategory / Item",
                    value=safe_text(selected_tx.get("Subcategory")),
                    key=f"single_resolve_subcategory_{selected_transaction_id}",
                )

                resolve_notes = st.text_input(
                    "Notes",
                    value=safe_text(selected_tx.get("Notes")),
                    key=f"single_resolve_notes_{selected_transaction_id}",
                )

                resolve_submitted = st.form_submit_button("Resolve Unknown", type="primary")

            if resolve_submitted:
                flags = calculate_flags(categories_df, resolve_category, resolve_payment_mode)

                update_row_cells(
                    "Transactions",
                    selected_row_number,
                    {
                        "Category": resolve_category,
                        "Subcategory": resolve_subcategory,
                        "Payment_Mode": resolve_payment_mode,
                        "Essential_Type": flags["category_type"],
                        "Is_Credit_Card_Leak": flags["is_credit_card_leak"],
                        "Is_Unknown": flags["is_unknown"],
                        "Notes": resolve_notes,
                    },
                )

                leak_count = sync_leaks_for_month(selected_month)

                st.session_state["flash_message"] = (
                    f"Unknown expense resolved. Leak table synced with {leak_count} leak rows."
                )
                st.cache_data.clear()
                st.rerun()

    # ----------------------------
    # 8. Sync Leaks
    # ----------------------------

    with st.expander("8. Sync Leaks / Repair Leak Table", expanded=False):
        st.caption(
            "Use this after manual edits in Google Sheets, or if the Leaks page looks incorrect."
        )

        st.info(
            "This will delete existing leak rows for the selected month and rebuild them from Transactions. "
            "It will not delete transactions."
        )

        if st.button("Rebuild Leak Table for Selected Month", type="primary"):
            leak_count = sync_leaks_for_month(selected_month)

            st.session_state["flash_message"] = (
                f"Leak table rebuilt for {selected_month}. Current leak rows: {leak_count}."
            )
            st.cache_data.clear()
            st.rerun()
