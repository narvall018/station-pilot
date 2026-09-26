"""Tests des calculs financiers : caisse, stock, crédits, bénéfice, contrôle des ventes."""

import pandas as pd
import pytest

from app import (
    build_credit_activity,
    build_credit_balances,
    calculate_totals,
    enrich_data,
    fuel_sales_gap_tolerance,
)

RATE = 100_000.0  # 1 USD = 100 000 LL : conversions faciles à vérifier de tête


def test_cash_reconciliation_per_currency():
    totals = calculate_totals(
        {
            "exchange_rate": RATE,
            "fuel_sales_usd": 1500,
            "fuel_sales_lbp": 50_000_000,
            "wash_sales_usd": 20,
            "credit_sales_usd": 100,
            "credit_collected_usd": 30,
            "credit_collected_lbp": 1_000_000,
            "salaries_usd": 50,
            "electricity_lbp": 2_000_000,
            "cash_opening_usd": 200,
            "cash_opening_lbp": 5_000_000,
            "cash_actual_end_usd": 1690,
            "cash_actual_end_lbp": 54_000_000,
        }
    )
    # Les crédits vendus comptent dans les ventes mais pas dans la caisse.
    assert totals["total_sales_usd"] == pytest.approx(1620)
    assert totals["cash_theoretical_end_usd"] == pytest.approx(200 + 1620 - 100 + 30 - 50)
    assert totals["cash_variance_usd"] == pytest.approx(-10)
    assert totals["cash_theoretical_end_lbp"] == pytest.approx(54_000_000)
    assert totals["cash_variance_lbp"] == pytest.approx(0)
    assert totals["total_sales_usd_equiv"] == pytest.approx(2120)
    assert totals["total_expenses_usd_equiv"] == pytest.approx(70)
    assert totals["net_usd_equiv"] == pytest.approx(2050)
    assert totals["credit_sold_usd_equiv"] == pytest.approx(100)
    assert totals["credit_collected_usd_equiv"] == pytest.approx(40)


def test_stock_reconciliation():
    totals = calculate_totals(
        {
            "opening_stock_l": 5000,
            "fuel_input_l": 2000,
            "fuel_volume_sold_l": 1000,
            "stock_available_l": 5980,
            "fuel_cost_usd_per_l": 1.2,
        }
    )
    assert totals["theoretical_stock_end_l"] == pytest.approx(6000)
    assert totals["stock_variance_l"] == pytest.approx(-20)
    assert totals["calculated_stock_value_usd"] == pytest.approx(5980 * 1.2)


def test_profit_ignores_delivery_payment_and_counts_fuel_at_cost():
    totals = calculate_totals(
        {
            "exchange_rate": RATE,
            "fuel_volume_sold_l": 1000,
            "fuel_cost_usd_per_l": 1.2,
            "fuel_price_usd_per_l": 1.5,
            "fuel_sales_usd": 1400,
            "credit_sales_usd": 100,
            "fuel_purchase_usd": 2400,  # livraison de 2 000 L payée ce jour-là
            "salaries_usd": 50,
        }
    )
    # Vue trésorerie : la livraison fait apparaître une perte…
    assert totals["net_usd_equiv"] == pytest.approx(1500 - 2450)
    # … alors que la journée est bénéficiaire.
    assert totals["fuel_cost_of_sales_usd"] == pytest.approx(1200)
    assert totals["operating_expenses_usd_equiv"] == pytest.approx(50)
    assert totals["profit_usd_equiv"] == pytest.approx(1500 - 1200 - 50)
    assert totals["fuel_revenue_usd_equiv"] == pytest.approx(1500)
    assert totals["fuel_margin_usd_equiv"] == pytest.approx(300)


def test_fuel_purchase_in_lbp_is_also_excluded_from_profit():
    totals = calculate_totals(
        {
            "exchange_rate": RATE,
            "fuel_sales_usd": 100,
            "fuel_purchase_lbp": 10_000_000,
            "maintenance_lbp": 2_000_000,
        }
    )
    assert totals["operating_expenses_usd_equiv"] == pytest.approx(20)
    assert totals["profit_usd_equiv"] == pytest.approx(80)


def test_fuel_sales_gap_includes_credits_and_lbp():
    totals = calculate_totals(
        {
            "exchange_rate": RATE,
            "fuel_volume_sold_l": 1000,
            "fuel_price_usd_per_l": 1.5,
            "fuel_sales_usd": 1300,
            "fuel_sales_lbp": 10_000_000,
            "credit_sales_usd": 50,
        }
    )
    assert totals["expected_fuel_sales_usd"] == pytest.approx(1500)
    assert totals["fuel_sales_gap_usd"] == pytest.approx(-50)
    assert abs(totals["fuel_sales_gap_usd"]) > fuel_sales_gap_tolerance(1500)


def test_no_price_means_no_gap():
    totals = calculate_totals(
        {"exchange_rate": RATE, "fuel_volume_sold_l": 1000, "fuel_sales_usd": 1}
    )
    assert totals["expected_fuel_sales_usd"] == 0
    assert totals["fuel_sales_gap_usd"] == 0


def test_gap_tolerance():
    assert fuel_sales_gap_tolerance(0) == 5
    assert fuel_sales_gap_tolerance(100) == 5
    assert fuel_sales_gap_tolerance(1500) == pytest.approx(15)


def test_missing_exchange_rate_ignores_lbp_in_equivalents():
    totals = calculate_totals({"exchange_rate": 0, "fuel_sales_usd": 10, "fuel_sales_lbp": 1_000_000})
    assert totals["total_sales_lbp"] == pytest.approx(1_000_000)
    assert totals["total_sales_usd_equiv"] == pytest.approx(10)


def test_legacy_single_currency_fields():
    totals = calculate_totals(
        {
            "exchange_rate": RATE,
            "tires_sales_amount": 300_000,
            "tires_sales_currency": "LBP",
            "credit_amount": 40,
            "credit_currency": "USD",
        }
    )
    assert totals["total_sales_lbp"] == pytest.approx(300_000)
    assert totals["credit_sold_usd_equiv"] == pytest.approx(40)
    assert totals["total_sales_usd"] == pytest.approx(40)


def test_enrich_data_adds_every_total_column():
    empty = enrich_data(pd.DataFrame({"record_date": pd.Series(dtype="object")}))
    for column in calculate_totals({}):
        assert column in empty.columns

    frame = enrich_data(
        pd.DataFrame(
            [
                {"record_date": "2026-09-01", "fuel_sales_usd": 100, "salaries_usd": 10},
                {"record_date": "2026-09-02", "fuel_sales_usd": 200, "salaries_usd": 0},
            ]
        )
    )
    assert frame["profit_usd_equiv"].tolist() == pytest.approx([90, 200])


def test_credit_balances_group_clients_and_convert_lbp():
    history = pd.DataFrame(
        [{"record_date": pd.Timestamp("2026-09-01"), "exchange_rate": RATE}]
    )
    credits = pd.DataFrame(
        [
            {"record_date": "2026-09-01", "client_name": "Hakim", "amount": 100, "currency": "USD"},
            {"record_date": "2026-09-01", "client_name": " hakim ", "amount": 1_000_000, "currency": "LBP"},
            {"record_date": "2026-09-01", "client_name": "Sami", "amount": 20, "currency": "USD"},
            {"record_date": "2026-09-01", "client_name": "Nour", "amount": 10, "currency": "USD"},
        ]
    )
    payments = pd.DataFrame(
        [
            {"record_date": "2026-09-01", "client_name": "HAKIM", "amount": 30, "currency": "USD"},
            {"record_date": "2026-09-01", "client_name": "Sami", "amount": 20, "currency": "USD"},
            {"record_date": "2026-09-01", "client_name": "Nour", "amount": 15, "currency": "USD"},
        ]
    )
    activity = build_credit_activity(history, credits, payments)
    balances = build_credit_balances(activity, RATE)
    by_client = {row["Client"].casefold(): row for _, row in balances.iterrows()}

    assert set(by_client) == {"hakim", "sami", "nour"}
    hakim = by_client["hakim"]
    assert hakim["Solde USD"] == pytest.approx(70)
    assert hakim["Solde LL"] == pytest.approx(1_000_000)
    assert hakim["Encours équiv. USD"] == pytest.approx(80)
    assert hakim["Statut"] == "À encaisser"
    assert by_client["sami"]["Statut"] == "Soldé"
    assert by_client["nour"]["Statut"] == "Avance client"
