from rules_engine import evaluate_month_rules


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


def decision_rank(decision):
    order = {
        "Approved": 1,
        "Caution": 2,
        "Not Recommended": 3,
        "Blocked": 4,
    }

    return order.get(decision, 1)


def max_decision(current, new):
    if decision_rank(new) > decision_rank(current):
        return new

    return current


def decision_style(decision):
    if decision == "Approved":
        return {
            "emoji": "✅",
            "tone": "Safe",
            "message": "This spend looks manageable under current rules.",
        }

    if decision == "Caution":
        return {
            "emoji": "⚠️",
            "tone": "Careful",
            "message": "This spend is possible, but it reduces your recovery room.",
        }

    if decision == "Not Recommended":
        return {
            "emoji": "🟠",
            "tone": "Avoid if possible",
            "message": "This spend may slow recovery. Avoid unless necessary.",
        }

    return {
        "emoji": "⛔",
        "tone": "Do not spend",
        "message": "This spend breaks recovery rules or creates future pressure.",
    }


def evaluate_pre_spend(
    data,
    selected_month,
    selected_week,
    amount,
    category,
    payment_mode,
    notes="",
):
    amount = to_number(amount)
    category = safe_text(category)
    payment_mode = safe_text(payment_mode)
    notes = safe_text(notes)

    result = evaluate_month_rules(data, selected_month, selected_week)
    summary = result["summary"]

    categories_df = data.get("Categories")
    category_info = get_category_info(categories_df, category)

    category_type = category_info["Type"]
    risk_level = category_info["Risk_Level"]

    weekly_spent = to_number(summary.get("Weekly Spent", 0))
    weekly_green_target = to_number(summary.get("Weekly Green Target", 0))
    weekly_practical_target = to_number(summary.get("Weekly Practical Target", 0))
    weekly_hard_cap = to_number(summary.get("Weekly Hard Cap", 0))
    current_card_pending = to_number(summary.get("Current Card Pending", 0))
    confirmed_next_cycle_liability = to_number(summary.get("Confirmed Next-Cycle Liability", 0))
    estimated_recovery_buffer = to_number(summary.get("Estimated Recovery Buffer", 0))

    projected_weekly_spent = weekly_spent + amount
    projected_target_left = weekly_practical_target - projected_weekly_spent
    projected_hard_cap_left = weekly_hard_cap - projected_weekly_spent

    is_credit_card_spend = payment_mode == "Credit Card"
    is_insurance = category == "Insurance"

    if is_credit_card_spend and not is_insurance:
        projected_next_cycle_liability = confirmed_next_cycle_liability + amount
        projected_recovery_buffer = estimated_recovery_buffer
    else:
        projected_next_cycle_liability = confirmed_next_cycle_liability
        projected_recovery_buffer = estimated_recovery_buffer - amount

    decision = "Approved"
    reasons = []
    recommended_action = []

    if amount <= 0:
        return {
            "decision": "Blocked",
            "style": decision_style("Blocked"),
            "reasons": ["Amount must be greater than zero."],
            "recommended_action": ["Enter a valid amount."],
            "metrics": {
                "Current Weekly Spend": weekly_spent,
                "Projected Weekly Spend": projected_weekly_spent,
                "Weekly Practical Target": weekly_practical_target,
                "Weekly Hard Cap": weekly_hard_cap,
                "Projected Target Left": projected_target_left,
                "Projected Hard Cap Left": projected_hard_cap_left,
                "Current Card Pending": current_card_pending,
                "Current Next-Cycle Liability": confirmed_next_cycle_liability,
                "Projected Next-Cycle Liability": projected_next_cycle_liability,
                "Current Recovery Buffer": estimated_recovery_buffer,
                "Projected Recovery Buffer": projected_recovery_buffer,
            },
        }

    # Rule 1: Credit-card detox
    if is_credit_card_spend and not is_insurance:
        decision = max_decision(decision, "Blocked")
        reasons.append(
            "Non-insurance credit-card spending is blocked during detox mode."
        )
        recommended_action.append(
            "Use UPI, debit card, or cash instead. Do not push this expense to next month."
        )

    # Rule 2: Amazon Pay coupon masking
    if category == "Coupon Masking" or payment_mode == "Amazon Pay Coupon":
        decision = max_decision(decision, "Not Recommended")
        reasons.append(
            "Amazon Pay coupon usage can hide the real expense category."
        )
        recommended_action.append(
            "Pay the actual bill directly by UPI/debit and classify it properly."
        )

    # Rule 3: Unknown expense
    if category == "Unknown Leak":
        decision = max_decision(decision, "Not Recommended")
        reasons.append(
            "Unknown expenses must be classified before spending."
        )
        recommended_action.append(
            "Choose the real category first: groceries, utilities, transport, medical, food, or shopping."
        )

    # Rule 4: Weekly hard cap
    if projected_weekly_spent > weekly_hard_cap:
        decision = max_decision(decision, "Blocked")
        reasons.append(
            f"This would cross the weekly hard cap of {money(weekly_hard_cap)}."
        )
        recommended_action.append(
            "Delay this spend or reduce the amount until it fits inside the hard cap."
        )

    # Rule 5: Weekly practical target
    elif projected_weekly_spent > weekly_practical_target:
        decision = max_decision(decision, "Not Recommended")
        reasons.append(
            f"This would cross the weekly practical target of {money(weekly_practical_target)}."
        )
        recommended_action.append(
            "Spend only if essential. Avoid eating out, quick commerce, shopping, and treats."
        )

    # Rule 6: Weekly green zone
    elif projected_weekly_spent > weekly_green_target:
        decision = max_decision(decision, "Caution")
        reasons.append(
            f"This would move the week above the green target of {money(weekly_green_target)}."
        )
        recommended_action.append(
            "Keep the rest of the week essentials-only."
        )

    # Rule 7: Recovery buffer
    if projected_recovery_buffer < 0:
        decision = max_decision(decision, "Blocked")
        reasons.append(
            "This would make your estimated recovery buffer negative."
        )
        recommended_action.append(
            "Do not spend unless it is an emergency. Review card dues and fixed commitments."
        )
    elif projected_recovery_buffer < 5000 and not is_credit_card_spend:
        decision = max_decision(decision, "Not Recommended")
        reasons.append(
            "This would leave your recovery buffer very low."
        )
        recommended_action.append(
            "Keep cash for bills, groceries, transport, and unavoidable needs."
        )
    elif projected_recovery_buffer < 10000 and not is_credit_card_spend:
        decision = max_decision(decision, "Caution")
        reasons.append(
            "Recovery buffer will remain positive, but thin."
        )
        recommended_action.append(
            "Avoid discretionary spending after this."
        )

    # Rule 8: Category risk
    if category in ["Quick Commerce", "Treats", "Shopping"]:
        decision = max_decision(decision, "Not Recommended")
        reasons.append(
            f"{category} is a leakage category during recovery mode."
        )
        recommended_action.append(
            "Avoid Blinkit/Instamart snacks, ice creams, impulse shopping, and non-essential orders."
        )

    elif category_type == "Leakage":
        decision = max_decision(decision, "Not Recommended")
        reasons.append(
            "This category is marked as leakage."
        )
        recommended_action.append(
            "Avoid this unless it is truly necessary."
        )

    elif risk_level == "High":
        decision = max_decision(decision, "Caution")
        reasons.append(
            "This is a high-risk category and should be monitored."
        )
        recommended_action.append(
            "Keep the amount small and do not repeat this category often."
        )

    # Rule 9: Existing card pressure
    if current_card_pending > 0 and category_type in ["Discretionary", "Leakage"]:
        decision = max_decision(decision, "Not Recommended")
        reasons.append(
            "You still have current card dues pending, so discretionary spending is risky."
        )
        recommended_action.append(
            "Clear current card dues before discretionary spending."
        )

    # Rule 10: Next-cycle liability pressure
    if confirmed_next_cycle_liability >= 30000 and category_type in ["Discretionary", "Leakage"]:
        decision = max_decision(decision, "Not Recommended")
        reasons.append(
            "Next-cycle card liability is already high."
        )
        recommended_action.append(
            "Protect next month by avoiding discretionary expenses now."
        )

    if not reasons:
        reasons.append(
            "The amount, category, and payment mode fit within current recovery rules."
        )
        recommended_action.append(
            "Proceed only if this is genuinely needed and pay through UPI/debit/cash."
        )

    metrics = {
        "Current Weekly Spend": weekly_spent,
        "Projected Weekly Spend": projected_weekly_spent,
        "Weekly Green Target": weekly_green_target,
        "Weekly Practical Target": weekly_practical_target,
        "Weekly Hard Cap": weekly_hard_cap,
        "Projected Target Left": projected_target_left,
        "Projected Hard Cap Left": projected_hard_cap_left,
        "Current Card Pending": current_card_pending,
        "Current Next-Cycle Liability": confirmed_next_cycle_liability,
        "Projected Next-Cycle Liability": projected_next_cycle_liability,
        "Current Recovery Buffer": estimated_recovery_buffer,
        "Projected Recovery Buffer": projected_recovery_buffer,
    }

    return {
        "decision": decision,
        "style": decision_style(decision),
        "reasons": reasons,
        "recommended_action": recommended_action,
        "metrics": metrics,
        "category_type": category_type,
        "risk_level": risk_level,
    }
