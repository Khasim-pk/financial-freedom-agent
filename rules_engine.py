import pandas as pd


# ----------------------------
# Basic helpers
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


def filter_month(df, month_id):
    if df is None or df.empty or "Month_ID" not in df.columns:
        return pd.DataFrame()

    selected_month = normalize_month_id(month_id)

    return df[
        df["Month_ID"].apply(normalize_month_id) == selected_month
    ].copy()


def first_row_as_dict(df):
    if df is None or df.empty:
        return {}
    return df.iloc[0].to_dict()


def get_setting(settings_df, key, default=None):
    if settings_df is None or settings_df.empty:
        return default

    if "Key" not in settings_df.columns or "Value" not in settings_df.columns:
        return default

    matches = settings_df[settings_df["Key"].astype(str) == key]

    if matches.empty:
        return default

    return matches.iloc[0]["Value"]


def get_category_info(categories_df, category_name):
    if categories_df is None or categories_df.empty or "Category" not in categories_df.columns:
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


# ----------------------------
# Severity helpers
# ----------------------------

SEVERITY_ORDER = {
    "Red": 1,
    "Orange": 2,
    "Yellow": 3,
    "Green": 4,
    "Info": 5,
}


def make_alert(severity, area, message, amount="", action=""):
    return {
        "Severity": severity,
        "Area": area,
        "Message": message,
        "Amount": amount,
        "Recommended Action": action,
    }


def sort_alerts(alerts):
    if not alerts:
        return alerts

    return sorted(
        alerts,
        key=lambda item: SEVERITY_ORDER.get(item.get("Severity", "Info"), 99)
    )


def recovery_score_from_alerts(alerts):
    score = 100

    for alert in alerts:
        severity = alert.get("Severity")

        if severity == "Red":
            score -= 25
        elif severity == "Orange":
            score -= 15
        elif severity == "Yellow":
            score -= 8

    if score < 0:
        score = 0

    if score >= 80:
        status = "Controlled"
    elif score >= 60:
        status = "Watch"
    elif score >= 40:
        status = "Risk"
    else:
        status = "Critical"

    return score, status


# ----------------------------
# Transaction rules
# ----------------------------

def is_credit_card_leak(row):
    category = safe_text(row.get("Category"))
    payment_mode = safe_text(row.get("Payment_Mode"))
    explicit_flag = safe_text(row.get("Is_Credit_Card_Leak"))

    if explicit_flag == "Yes":
        return True

    if payment_mode == "Credit Card" and category != "Insurance":
        return True

    return False


def is_unknown(row):
    category = safe_text(row.get("Category"))
    explicit_flag = safe_text(row.get("Is_Unknown"))

    if explicit_flag == "Yes":
        return True

    if category == "Unknown Leak":
        return True

    return False


def classify_transaction_risk(row, categories_df):
    category = safe_text(row.get("Category"))
    payment_mode = safe_text(row.get("Payment_Mode"))
    amount = to_number(row.get("Amount"))

    category_info = get_category_info(categories_df, category)
    category_type = category_info["Type"]
    risk_level = category_info["Risk_Level"]

    if is_credit_card_leak(row):
        return {
            "Severity": "Red",
            "Risk_Type": "Credit Card Leak",
            "Reason": "Non-insurance credit-card spending creates future salary pressure.",
        }

    if payment_mode == "Amazon Pay Coupon" or category == "Coupon Masking":
        return {
            "Severity": "Red",
            "Risk_Type": "Coupon Masking",
            "Reason": "Amazon Pay coupon spending can hide the real expense category.",
        }

    if is_unknown(row):
        return {
            "Severity": "Orange",
            "Risk_Type": "Unknown Expense",
            "Reason": "This expense is not classified yet.",
        }

    if category in ["Quick Commerce", "Treats", "Shopping"]:
        return {
            "Severity": "Orange",
            "Risk_Type": category,
            "Reason": "This is a known leakage category during recovery mode.",
        }

    if category_type == "Leakage":
        return {
            "Severity": "Orange",
            "Risk_Type": "Leakage",
            "Reason": "This category is marked as leakage.",
        }

    if risk_level == "High":
        return {
            "Severity": "Yellow",
            "Risk_Type": "High-Risk Category",
            "Reason": "This category needs monitoring.",
        }

    if amount <= 0:
        return {
            "Severity": "Yellow",
            "Risk_Type": "Invalid Amount",
            "Reason": "Amount is zero or invalid.",
        }

    return {
        "Severity": "Green",
        "Risk_Type": "Normal",
        "Reason": "No major rule violation detected.",
    }


# ----------------------------
# Monthly evaluation
# ----------------------------

def evaluate_month_rules(data, selected_month, selected_week):
    settings_df = data.get("Settings", pd.DataFrame())
    months_df = data.get("Months", pd.DataFrame())
    fixed_df_all = data.get("Fixed_Commitments", pd.DataFrame())
    cards_df_all = data.get("Credit_Card_Dues", pd.DataFrame())
    next_cycle_df_all = data.get("Next_Cycle_Liability", pd.DataFrame())
    weekly_df_all = data.get("Weekly_Envelopes", pd.DataFrame())
    transactions_df_all = data.get("Transactions", pd.DataFrame())
    handloans_df = data.get("Handloans", pd.DataFrame())
    categories_df = data.get("Categories", pd.DataFrame())

    alerts = []

    month_rows = filter_month(months_df, selected_month)
    month_row = first_row_as_dict(month_rows)

    opening_bank_cash = to_number(
        month_row.get("Opening_Bank_Cash", get_setting(settings_df, "current_bank_cash", 0))
    )
    salary_received = to_number(
        month_row.get("Salary_Received", get_setting(settings_df, "net_salary", 0))
    )
    handloan_received = to_number(
        month_row.get("Handloan_Received", get_setting(settings_df, "planned_new_handloan", 0))
    )

    total_available = opening_bank_cash + salary_received + handloan_received

    # Fixed commitments
    fixed_df = filter_month(fixed_df_all, selected_month)

    if not fixed_df.empty:
        fixed_df["Amount_Number"] = fixed_df["Amount"].apply(to_number)
        total_fixed_burden = fixed_df["Amount_Number"].sum()

        direct_fixed_df = fixed_df[
            ~fixed_df["Payment_Mode"].astype(str).str.lower().str.contains("credit card", na=False)
        ]

        direct_fixed_burden = direct_fixed_df["Amount_Number"].sum()
        card_fixed_burden = total_fixed_burden - direct_fixed_burden
    else:
        total_fixed_burden = to_number(
            month_row.get("Fixed_Burden", get_setting(settings_df, "total_fixed_burden", 0))
        )
        direct_fixed_burden = total_fixed_burden
        card_fixed_burden = 0

    # Current credit-card dues
    cards_df = filter_month(cards_df_all, selected_month)

    if not cards_df.empty:
        cards_df["Due_Number"] = cards_df["Due_Amount"].apply(to_number)
        cards_df["Paid_Number"] = cards_df["Paid_Amount"].apply(to_number)
        cards_df["Pending_Number"] = (
            cards_df["Due_Number"] - cards_df["Paid_Number"]
        ).clip(lower=0)

        current_card_due_total = cards_df["Due_Number"].sum()
        current_card_pending = cards_df["Pending_Number"].sum()
    else:
        current_card_due_total = to_number(month_row.get("Current_Card_Dues", 0))
        current_card_pending = current_card_due_total

    # Next-cycle liability
    next_cycle_df = filter_month(next_cycle_df_all, selected_month)

    if not next_cycle_df.empty:
        next_cycle_df["Amount_Number"] = next_cycle_df["Amount"].apply(to_number)
        base_next_cycle_liability = next_cycle_df["Amount_Number"].sum()
    else:
        base_next_cycle_liability = to_number(month_row.get("Next_Cycle_Liability", 0))

    # Transactions
    transactions_df = filter_month(transactions_df_all, selected_month)

    if not transactions_df.empty:
        transactions_df["Amount_Number"] = transactions_df["Amount"].apply(to_number)

        transactions_df["Rule_Severity"] = transactions_df.apply(
            lambda row: classify_transaction_risk(row, categories_df)["Severity"],
            axis=1,
        )

        card_leaks_df = transactions_df[
            transactions_df.apply(is_credit_card_leak, axis=1)
        ].copy()

        unknown_df = transactions_df[
            transactions_df.apply(is_unknown, axis=1)
        ].copy()

        coupon_masking_df = transactions_df[
            (transactions_df["Category"].astype(str) == "Coupon Masking")
            | (transactions_df["Payment_Mode"].astype(str) == "Amazon Pay Coupon")
        ].copy()

        quick_commerce_df = transactions_df[
            transactions_df["Category"].astype(str).isin(["Quick Commerce", "Treats"])
        ].copy()

        non_card_transactions = transactions_df[
            transactions_df["Payment_Mode"].astype(str) != "Credit Card"
        ].copy()

        month_cash_spend = non_card_transactions["Amount_Number"].sum()
        new_card_leaks_amount = card_leaks_df["Amount_Number"].sum()
        unknown_amount = unknown_df["Amount_Number"].sum()
        coupon_masking_amount = coupon_masking_df["Amount_Number"].sum()
        quick_commerce_amount = quick_commerce_df["Amount_Number"].sum()
    else:
        card_leaks_df = pd.DataFrame()
        unknown_df = pd.DataFrame()
        coupon_masking_df = pd.DataFrame()
        quick_commerce_df = pd.DataFrame()

        month_cash_spend = 0
        new_card_leaks_amount = 0
        unknown_amount = 0
        coupon_masking_amount = 0
        quick_commerce_amount = 0

    confirmed_next_cycle_liability = base_next_cycle_liability + new_card_leaks_amount

    estimated_recovery_buffer = (
        total_available
        - direct_fixed_burden
        - current_card_pending
        - month_cash_spend
    )

    # Weekly envelope
    weekly_df = filter_month(weekly_df_all, selected_month)
    selected_week_rows = pd.DataFrame()

    weekly_spent = 0
    weekly_green_target = to_number(get_setting(settings_df, "weekly_green_target", 4000))
    weekly_practical_target = to_number(get_setting(settings_df, "weekly_practical_target", 4500))
    weekly_hard_cap = to_number(get_setting(settings_df, "weekly_hard_cap", 6000))

    if not weekly_df.empty:
        selected_week_rows = weekly_df[
            weekly_df["Week_Name"].astype(str) == str(selected_week)
        ].copy()

        if not selected_week_rows.empty:
            weekly_row = selected_week_rows.iloc[0]
            weekly_green_target = to_number(weekly_row.get("Green_Target", weekly_green_target))
            weekly_practical_target = to_number(weekly_row.get("Practical_Target", weekly_practical_target))
            weekly_hard_cap = to_number(weekly_row.get("Hard_Cap", weekly_hard_cap))

    if not transactions_df.empty:
        week_transactions = transactions_df[
            transactions_df["Week_Name"].astype(str) == str(selected_week)
        ].copy()

        if not week_transactions.empty:
            weekly_spent = week_transactions["Amount_Number"].sum()

    weekly_target_left = weekly_practical_target - weekly_spent
    weekly_hard_cap_left = weekly_hard_cap - weekly_spent

    # Handloans
    if handloans_df is not None and not handloans_df.empty and "Balance" in handloans_df.columns:
        handloans_df = handloans_df.copy()
        handloans_df["Balance_Number"] = handloans_df["Balance"].apply(to_number)
        total_handloan_balance = handloans_df["Balance_Number"].sum()
    else:
        total_handloan_balance = 0

    # ----------------------------
    # Alerts
    # ----------------------------

    if current_card_pending > 0:
        alerts.append(
            make_alert(
                "Red",
                "Current Credit-Card Dues",
                "You still have billed credit-card dues pending.",
                money(current_card_pending),
                "Clear billed card dues before normal spending or friend-loan repayment."
            )
        )
    else:
        alerts.append(
            make_alert(
                "Green",
                "Current Credit-Card Dues",
                "No pending billed credit-card dues found for the selected month.",
                money(0),
                "Keep card usage at zero except protected insurance if still active."
            )
        )

    if confirmed_next_cycle_liability >= 30000:
        alerts.append(
            make_alert(
                "Red",
                "Next-Cycle Liability",
                "Next-cycle credit-card liability is already high.",
                money(confirmed_next_cycle_liability),
                "Avoid all new card spending. Protect next month from salary drain."
            )
        )
    elif confirmed_next_cycle_liability > 0:
        alerts.append(
            make_alert(
                "Orange",
                "Next-Cycle Liability",
                "There is still future credit-card liability waiting.",
                money(confirmed_next_cycle_liability),
                "Reserve money for this before discretionary spending."
            )
        )
    else:
        alerts.append(
            make_alert(
                "Green",
                "Next-Cycle Liability",
                "No next-cycle card liability detected.",
                money(0),
                "Maintain card detox."
            )
        )

    if new_card_leaks_amount > 0:
        alerts.append(
            make_alert(
                "Red",
                "Credit-Card Detox",
                "Non-insurance credit-card spending detected.",
                money(new_card_leaks_amount),
                "Stop discretionary card use immediately. Use UPI/debit/cash only."
            )
        )
    else:
        alerts.append(
            make_alert(
                "Green",
                "Credit-Card Detox",
                "No discretionary credit-card leak detected in transactions.",
                money(0),
                "Continue card detox."
            )
        )

    if coupon_masking_amount > 0:
        alerts.append(
            make_alert(
                "Red",
                "Amazon Pay Coupon Masking",
                "Amazon Pay coupon or coupon masking transactions found.",
                money(coupon_masking_amount),
                "Classify coupon purpose and stop buying coupons with credit cards."
            )
        )

    if unknown_amount > 0:
        alerts.append(
            make_alert(
                "Orange",
                "Unknown Expenses",
                "Some expenses are still unclassified.",
                money(unknown_amount),
                "Resolve unknown expenses from Transaction Manager."
            )
        )

    if quick_commerce_amount > 1000:
        alerts.append(
            make_alert(
                "Orange",
                "Quick Commerce / Treats",
                "Quick-commerce or treats spending is getting high.",
                money(quick_commerce_amount),
                "Avoid Blinkit/Instamart snacks and ice creams during recovery mode."
            )
        )
    elif quick_commerce_amount > 0:
        alerts.append(
            make_alert(
                "Yellow",
                "Quick Commerce / Treats",
                "Quick-commerce or treats spending exists this month.",
                money(quick_commerce_amount),
                "Watch this category closely."
            )
        )

    if weekly_spent > weekly_hard_cap:
        alerts.append(
            make_alert(
                "Red",
                "Weekly Envelope",
                f"{selected_week} has crossed the weekly hard cap.",
                money(weekly_spent),
                "Stop non-essential spending until next week."
            )
        )
    elif weekly_spent > weekly_practical_target:
        alerts.append(
            make_alert(
                "Orange",
                "Weekly Envelope",
                f"{selected_week} has crossed the practical target.",
                money(weekly_spent),
                "Essentials only. Avoid delivery, snacks, shopping, and card use."
            )
        )
    elif weekly_spent > weekly_green_target:
        alerts.append(
            make_alert(
                "Yellow",
                "Weekly Envelope",
                f"{selected_week} is above green target but below practical target.",
                money(weekly_spent),
                "Stay careful for the rest of the week."
            )
        )
    else:
        alerts.append(
            make_alert(
                "Green",
                "Weekly Envelope",
                f"{selected_week} is within green target.",
                money(weekly_spent),
                "Good control. Continue UPI/debit/cash mode."
            )
        )

    if estimated_recovery_buffer < 0:
        alerts.append(
            make_alert(
                "Red",
                "Recovery Buffer",
                "Estimated recovery buffer is negative.",
                money(estimated_recovery_buffer),
                "Reduce spending immediately and review pending dues."
            )
        )
    elif estimated_recovery_buffer < 5000:
        alerts.append(
            make_alert(
                "Orange",
                "Recovery Buffer",
                "Recovery buffer is very low.",
                money(estimated_recovery_buffer),
                "Spend only on essentials."
            )
        )
    elif estimated_recovery_buffer < 10000:
        alerts.append(
            make_alert(
                "Yellow",
                "Recovery Buffer",
                "Recovery buffer is positive but thin.",
                money(estimated_recovery_buffer),
                "Avoid unnecessary spending."
            )
        )
    else:
        alerts.append(
            make_alert(
                "Green",
                "Recovery Buffer",
                "Recovery buffer is currently positive.",
                money(estimated_recovery_buffer),
                "Maintain discipline."
            )
        )

    if total_handloan_balance > 0:
        alerts.append(
            make_alert(
                "Info",
                "Handloans",
                "Friend handloan balance still exists.",
                money(total_handloan_balance),
                "Repay only after card cycle is stable."
            )
        )

    alerts = sort_alerts(alerts)
    score, score_status = recovery_score_from_alerts(alerts)

    summary = {
        "Opening Bank Cash": opening_bank_cash,
        "Salary Received": salary_received,
        "Handloan Received": handloan_received,
        "Total Available": total_available,
        "Total Fixed Burden": total_fixed_burden,
        "Direct Fixed Burden": direct_fixed_burden,
        "Card Fixed Burden": card_fixed_burden,
        "Current Card Due Total": current_card_due_total,
        "Current Card Pending": current_card_pending,
        "Base Next-Cycle Liability": base_next_cycle_liability,
        "New Card Leaks Amount": new_card_leaks_amount,
        "Confirmed Next-Cycle Liability": confirmed_next_cycle_liability,
        "Month Cash Spend": month_cash_spend,
        "Unknown Amount": unknown_amount,
        "Coupon Masking Amount": coupon_masking_amount,
        "Quick Commerce Amount": quick_commerce_amount,
        "Weekly Green Target": weekly_green_target,
        "Weekly Practical Target": weekly_practical_target,
        "Weekly Hard Cap": weekly_hard_cap,
        "Weekly Spent": weekly_spent,
        "Weekly Target Left": weekly_target_left,
        "Weekly Hard Cap Left": weekly_hard_cap_left,
        "Estimated Recovery Buffer": estimated_recovery_buffer,
        "Total Handloan Balance": total_handloan_balance,
        "Recovery Score": score,
        "Recovery Status": score_status,
    }

    transaction_risks = pd.DataFrame()

    if not transactions_df.empty:
        risk_rows = []

        for _, row in transactions_df.iterrows():
            risk = classify_transaction_risk(row, categories_df)

            risk_rows.append(
                {
                    "Date": safe_text(row.get("Date")),
                    "Week": safe_text(row.get("Week_Name")),
                    "Amount": to_number(row.get("Amount")),
                    "Category": safe_text(row.get("Category")),
                    "Subcategory": safe_text(row.get("Subcategory")),
                    "Payment Mode": safe_text(row.get("Payment_Mode")),
                    "Severity": risk["Severity"],
                    "Risk Type": risk["Risk_Type"],
                    "Reason": risk["Reason"],
                    "Source": safe_text(row.get("Source")),
                }
            )

        transaction_risks = pd.DataFrame(risk_rows)

        if not transaction_risks.empty:
            transaction_risks["Severity_Order"] = transaction_risks["Severity"].map(SEVERITY_ORDER).fillna(99)
            transaction_risks = transaction_risks.sort_values(
                ["Severity_Order", "Date"],
                ascending=[True, False],
            ).drop(columns=["Severity_Order"])

    return {
        "summary": summary,
        "alerts": alerts,
        "transaction_risks": transaction_risks,
    }
