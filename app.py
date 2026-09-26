"""Application Streamlit de gestion quotidienne d'une station-service.

Lancement :
    streamlit run app.py

Les données permanentes sont conservées sous forme de CSV dans une branche
GitHub privée. SQLite sert uniquement de cache temporaire pendant l'exécution.
Les montants USD et LBP restent toujours séparés ; les conversions ne servent
qu'aux indicateurs consolidés.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from github_storage import (
    GitHubStorage,
    GitHubStorageConflictError,
    GitHubStorageError,
)


APP_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(tempfile.gettempdir()) / "station_pilot_runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = RUNTIME_DIR / "station_data.db"
CSV_PATH = RUNTIME_DIR / "station_data.csv"
CREDITS_CSV_PATH = RUNTIME_DIR / "station_credits.csv"
CREDIT_PAYMENTS_CSV_PATH = RUNTIME_DIR / "station_credit_payments.csv"
REMOTE_HEAD_PATH = RUNTIME_DIR / ".github_data_head"

REMOTE_DATA_FILES = {
    "data/station_data.csv": CSV_PATH,
    "data/station_credits.csv": CREDITS_CSV_PATH,
    "data/station_credit_payments.csv": CREDIT_PAYMENTS_CSV_PATH,
}


class StorageConfigurationError(RuntimeError):
    """Le stockage GitHub n'est pas configuré dans les secrets Streamlit."""


def get_github_storage() -> GitHubStorage:
    """Construit le client GitHub sans exposer le jeton dans le dépôt."""
    try:
        secrets = st.secrets.get("github_storage", {})
    except Exception:  # Aucun fichier de secrets pendant certains tests locaux.
        secrets = {}

    token = str(
        secrets.get("token", os.environ.get("STATION_PILOT_GITHUB_TOKEN", ""))
    ).strip()
    if not token:
        raise StorageConfigurationError(
            "Ajoutez un nouveau jeton GitHub dans les Secrets de Streamlit Cloud."
        )

    return GitHubStorage(
        token=token,
        owner=str(secrets.get("owner", "narvall018")),
        repo=str(secrets.get("repo", "station-pilot")),
        branch=str(secrets.get("branch", "data")),
        source_branch=str(secrets.get("source_branch", "main")),
    )

MONTHS_FR = {
    1: "Janvier",
    2: "Février",
    3: "Mars",
    4: "Avril",
    5: "Mai",
    6: "Juin",
    7: "Juillet",
    8: "Août",
    9: "Septembre",
    10: "Octobre",
    11: "Novembre",
    12: "Décembre",
}

EXPENSE_CATEGORIES = {
    "Achat d'essence": "fuel_purchase",
    "Électricité / Générateur": "electricity",
    "Salaires": "salaries",
    "Achat de pneus": "tires_purchase",
    "Pourboire livreur": "delivery_tip",
    "Travaux / Maintenance": "maintenance",
    "Autres dépenses": "other_expenses",
}

SALES_CATEGORIES = {
    "Essence": "fuel_sales",
    "Pneus": "tires_sales",
    "Bouteilles de gaz": "gas_sales",
    "Lavage": "wash_sales",
    "Autres ventes": "other_sales",
}

NAVIGATION_LABELS = {
    "Accueil": ":material/home:  Accueil",
    "Saisie": ":material/edit_note:  Saisie",
    "Tableau de bord": ":material/analytics:  Tableau de bord",
    "Crédits": ":material/account_balance_wallet:  Crédits",
    "Historique": ":material/database:  Historique",
}

PLOTLY_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
}

# ---------------------------------------------------------------------------
# Thèmes
#
# Les couleurs de série (sales / expenses / net / categorical) sont choisies
# puis validées pour chaque mode : bande de clarté, plancher de chroma,
# séparation daltonisme et contraste face à la surface réelle des cartes
# (#ffffff en clair, #141b18 en sombre). Les deux jeux ne sont pas la simple
# inversion l'un de l'autre : chaque teinte est re-échelonnée pour son fond.
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, Any]] = {
    "light": {
        "base": "light",
        "bg": "#f3f6f4",
        "surface": "#ffffff",
        "surface_2": "#f8faf9",
        "surface_3": "#e6eee9",
        "text": "#0b1712",
        "muted": "#42544b",
        "line": "#c9d6d0",
        "line_strong": "#afc2b9",
        "accent": "#0d684d",
        "accent_strong": "#07543e",
        "accent_soft": "#d7ece3",
        "accent_wash": "#edf7f2",
        "on_accent": "#ffffff",
        "glow_1": "rgba(25, 156, 113, 0.10)",
        "glow_2": "rgba(216, 155, 39, 0.07)",
        "shadow": "0 1px 2px rgba(15, 46, 36, .08), 0 12px 32px rgba(15, 46, 36, .10)",
        "sales": "#087a57",
        "expenses": "#c44a21",
        "net": "#1e5fa8",
        "sales_prev": "#5f907f",
        "expenses_prev": "#bf795e",
        "net_prev": "#6c8fb7",
        "positive": "#067238",
        "negative": "#b4232d",
        "warning": "#7a5310",
        "warning_soft": "#fff1cc",
        "danger_soft": "#fbe7e8",
        "info": "#245a84",
        "info_soft": "#e5f0f8",
        "grid": "#d7e0db",
        "axis": "#afc0b8",
        "tick": "#4b5e54",
        "tooltip_bg": "#072d22",
        "tooltip_text": "#ffffff",
        "categorical": [
            "#1e5fa8", "#c44a21", "#087a57", "#956600",
            "#a23b6e", "#3f7d20", "#5847a6", "#b83238",
        ],
    },
    "dark": {
        "base": "dark",
        "bg": "#0c1210",
        "surface": "#141b18",
        "surface_2": "#18211d",
        "surface_3": "#1d2723",
        "text": "#e6efeb",
        "muted": "#93a79f",
        "line": "#253029",
        "line_strong": "#32403a",
        "accent": "#34c48d",
        "accent_strong": "#4bd7a0",
        "accent_soft": "rgba(52, 196, 141, 0.16)",
        "accent_wash": "rgba(52, 196, 141, 0.08)",
        "on_accent": "#06231a",
        "glow_1": "rgba(26, 92, 68, 0.28)",
        "glow_2": "rgba(102, 84, 46, 0.14)",
        "shadow": "0 1px 2px rgba(0, 0, 0, .32), 0 12px 34px rgba(0, 0, 0, .34)",
        "sales": "#199e70",
        "expenses": "#d95926",
        "net": "#3987e5",
        "sales_prev": "#0f5b41",
        "expenses_prev": "#7d3416",
        "net_prev": "#204d83",
        "positive": "#3ecf95",
        "negative": "#e07b7b",
        "warning": "#e0a944",
        "warning_soft": "rgba(250, 178, 25, 0.14)",
        "danger_soft": "rgba(208, 59, 59, 0.14)",
        "info": "#6ba4de",
        "info_soft": "rgba(57, 135, 229, 0.14)",
        "grid": "#22302b",
        "axis": "#35473f",
        "tick": "#94a8a0",
        "tooltip_bg": "#0b1613",
        "tooltip_text": "#eaf3ef",
        "categorical": [
            "#3987e5", "#d95926", "#199e70", "#c98500",
            "#d55181", "#008300", "#9085e9", "#e66767",
        ],
    },
}

# Le rail de navigation reste sombre dans les deux thèmes : c'est le repère
# fixe de l'application, comme sur l'application web.
SIDEBAR_GRADIENTS = {
    "light": "linear-gradient(178deg, #06271d 0%, #0b3c2e 58%, #0d4b38 100%)",
    "dark": "linear-gradient(178deg, #071d16 0%, #0a2c22 58%, #0b3628 100%)",
}


def resolve_theme() -> str:
    """Thème actif : choix explicite de l'utilisateur, sinon réglage du navigateur."""
    chosen = st.session_state.get("app_theme")
    if chosen in THEMES:
        return chosen
    detected = "light"
    try:
        detected = st.context.theme.type or "light"
    except Exception:  # pragma: no cover - dépend de la version de Streamlit
        detected = "light"
    if detected not in THEMES:
        detected = "light"
    st.session_state["app_theme"] = detected
    return detected


def theme_palette() -> dict[str, Any]:
    """Palette du thème actif, accessible depuis n'importe quel écran."""
    return THEMES[st.session_state.get("app_theme", "light")]


def apply_theme_config(palette: Mapping[str, Any]) -> None:
    """Aligne le thème natif de Streamlit (champs, tableaux) sur notre palette.

    ``st._config`` est une API interne : en cas de changement côté Streamlit,
    l'application continue de fonctionner avec le thème par défaut.
    """
    options = {
        "theme.base": palette["base"],
        "theme.primaryColor": palette["accent"],
        "theme.backgroundColor": palette["bg"],
        "theme.secondaryBackgroundColor": palette["surface"],
        "theme.textColor": palette["text"],
        "theme.linkColor": palette["accent"],
        "theme.borderColor": palette["line_strong"],
        "theme.greenColor": palette["positive"],
        "theme.redColor": palette["negative"],
        "theme.orangeColor": palette["warning"],
        "theme.blueColor": palette["info"],
        "theme.grayColor": palette["muted"],
        "theme.dataframeBorderColor": palette["line"],
        "theme.dataframeHeaderBackgroundColor": palette["surface_3"],
        "theme.chartCategoricalColors": palette["categorical"],
    }
    for name, value in options.items():
        try:
            st._config.set_option(name, value)
        except Exception:  # pragma: no cover - API interne
            return

DB_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "record_date": "TEXT NOT NULL UNIQUE",
    "exchange_rate": "REAL NOT NULL DEFAULT 0",
    "tank_capacity_l": "REAL NOT NULL DEFAULT 0",
    "opening_stock_l": "REAL NOT NULL DEFAULT 0",
    "fuel_input_l": "REAL NOT NULL DEFAULT 0",
    "stock_available_l": "REAL NOT NULL DEFAULT 0",
    "fuel_cost_usd_per_l": "REAL NOT NULL DEFAULT 0",
    "stock_value_usd": "REAL NOT NULL DEFAULT 0",
    "fuel_volume_sold_l": "REAL NOT NULL DEFAULT 0",
    "fuel_sales_usd": "REAL NOT NULL DEFAULT 0",
    "fuel_sales_lbp": "REAL NOT NULL DEFAULT 0",
    "tires_sales_amount": "REAL NOT NULL DEFAULT 0",
    "tires_sales_currency": "TEXT NOT NULL DEFAULT 'USD'",
    "tires_sales_usd": "REAL NOT NULL DEFAULT 0",
    "tires_sales_lbp": "REAL NOT NULL DEFAULT 0",
    "gas_sales_amount": "REAL NOT NULL DEFAULT 0",
    "gas_sales_currency": "TEXT NOT NULL DEFAULT 'USD'",
    "gas_sales_usd": "REAL NOT NULL DEFAULT 0",
    "gas_sales_lbp": "REAL NOT NULL DEFAULT 0",
    "wash_sales_amount": "REAL NOT NULL DEFAULT 0",
    "wash_sales_currency": "TEXT NOT NULL DEFAULT 'USD'",
    "wash_sales_usd": "REAL NOT NULL DEFAULT 0",
    "wash_sales_lbp": "REAL NOT NULL DEFAULT 0",
    "other_sales_usd": "REAL NOT NULL DEFAULT 0",
    "other_sales_lbp": "REAL NOT NULL DEFAULT 0",
    "credit_customer": "TEXT NOT NULL DEFAULT ''",
    "credit_amount": "REAL NOT NULL DEFAULT 0",
    "credit_currency": "TEXT NOT NULL DEFAULT 'USD'",
    "credit_sales_usd": "REAL NOT NULL DEFAULT 0",
    "credit_sales_lbp": "REAL NOT NULL DEFAULT 0",
    "credit_collected_usd": "REAL NOT NULL DEFAULT 0",
    "credit_collected_lbp": "REAL NOT NULL DEFAULT 0",
    "fuel_purchase_usd": "REAL NOT NULL DEFAULT 0",
    "fuel_purchase_lbp": "REAL NOT NULL DEFAULT 0",
    "electricity_usd": "REAL NOT NULL DEFAULT 0",
    "electricity_lbp": "REAL NOT NULL DEFAULT 0",
    "salaries_usd": "REAL NOT NULL DEFAULT 0",
    "salaries_lbp": "REAL NOT NULL DEFAULT 0",
    "tires_purchase_usd": "REAL NOT NULL DEFAULT 0",
    "tires_purchase_lbp": "REAL NOT NULL DEFAULT 0",
    "delivery_tip_usd": "REAL NOT NULL DEFAULT 0",
    "delivery_tip_lbp": "REAL NOT NULL DEFAULT 0",
    "maintenance_usd": "REAL NOT NULL DEFAULT 0",
    "maintenance_lbp": "REAL NOT NULL DEFAULT 0",
    "other_expenses_usd": "REAL NOT NULL DEFAULT 0",
    "other_expenses_lbp": "REAL NOT NULL DEFAULT 0",
    "cash_opening_usd": "REAL NOT NULL DEFAULT 0",
    "cash_opening_lbp": "REAL NOT NULL DEFAULT 0",
    "cash_actual_end_usd": "REAL NOT NULL DEFAULT 0",
    "cash_actual_end_lbp": "REAL NOT NULL DEFAULT 0",
    "notes": "TEXT NOT NULL DEFAULT ''",
    "created_at": "TEXT NOT NULL DEFAULT ''",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
}

EDITABLE_COLUMNS = [
    column for column in DB_COLUMNS if column not in {"id", "created_at", "updated_at"}
]


def get_connection() -> sqlite3.Connection:
    """Ouvre une connexion SQLite configurée pour un usage local fiable."""
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def initialize_database() -> None:
    """Crée la table et ajoute les colonnes manquantes lors d'une mise à jour."""
    definitions = ",\n".join(
        f'"{name}" {definition}' for name, definition in DB_COLUMNS.items()
    )
    with get_connection() as connection:
        connection.execute(f"CREATE TABLE IF NOT EXISTS daily_records ({definitions})")

        existing = {
            row["name"] for row in connection.execute("PRAGMA table_info(daily_records)")
        }
        for name, definition in DB_COLUMNS.items():
            if name not in existing:
                # SQLite ne permet pas d'ajouter a posteriori une clé UNIQUE ou PRIMARY.
                safe_definition = definition.replace(" PRIMARY KEY AUTOINCREMENT", "").replace(
                    " UNIQUE", ""
                )
                connection.execute(
                    f'ALTER TABLE daily_records ADD COLUMN "{name}" {safe_definition}'
                )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_date TEXT NOT NULL,
                client_name TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (record_date) REFERENCES daily_records(record_date)
                    ON UPDATE CASCADE ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_credit_sales_date ON credit_sales(record_date)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_date TEXT NOT NULL,
                client_name TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'USD',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (record_date) REFERENCES daily_records(record_date)
                    ON UPDATE CASCADE ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_credit_payments_date "
            "ON credit_payments(record_date)"
        )


def record_exists(record_date: str) -> bool:
    with get_connection() as connection:
        result = connection.execute(
            "SELECT 1 FROM daily_records WHERE record_date = ? LIMIT 1", (record_date,)
        ).fetchone()
    return result is not None


def save_record(
    record: Mapping[str, Any], allow_update: bool = False, sync_csv: bool = True
) -> str:
    """Insère une journée ou la met à jour explicitement si elle existe."""
    day = str(record["record_date"])
    exists = record_exists(day)
    if exists and not allow_update:
        raise ValueError(
            f"Une saisie existe déjà pour le {format_date_fr(day)}. "
            "Cochez l'autorisation de remplacement pour la modifier."
        )

    now = datetime.now().isoformat(timespec="seconds")
    payload = {column: record.get(column, "" if "currency" not in column else "USD") for column in EDITABLE_COLUMNS}
    payload["created_at"] = now
    payload["updated_at"] = now

    columns = EDITABLE_COLUMNS + ["created_at", "updated_at"]
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)

    if exists:
        assignments = ", ".join(
            f'"{column}" = ?' for column in EDITABLE_COLUMNS if column != "record_date"
        )
        values = [payload[column] for column in EDITABLE_COLUMNS if column != "record_date"]
        values.extend([now, day])
        with get_connection() as connection:
            connection.execute(
                f"UPDATE daily_records SET {assignments}, updated_at = ? WHERE record_date = ?",
                values,
            )
        if sync_csv:
            sync_csv_backup()
        return "updated"

    with get_connection() as connection:
        connection.execute(
            f"INSERT INTO daily_records ({quoted_columns}) VALUES ({placeholders})",
            [payload[column] for column in columns],
        )
    if sync_csv:
        sync_csv_backup()
    return "inserted"


def load_data() -> pd.DataFrame:
    """Charge l'historique, avec des types cohérents même si la base est vide."""
    with get_connection() as connection:
        frame = pd.read_sql_query(
            "SELECT * FROM daily_records ORDER BY record_date ASC", connection
        )

    if frame.empty:
        frame = pd.DataFrame(columns=DB_COLUMNS.keys())
    frame["record_date"] = pd.to_datetime(frame["record_date"], errors="coerce")
    return enrich_data(frame)


def load_credit_entries(record_date: str | None = None) -> pd.DataFrame:
    """Charge les ventes à crédit détaillées, éventuellement pour une seule date."""
    query = "SELECT * FROM credit_sales"
    parameters: tuple[Any, ...] = ()
    if record_date is not None:
        query += " WHERE record_date = ?"
        parameters = (record_date,)
    query += " ORDER BY record_date ASC, id ASC"
    with get_connection() as connection:
        frame = pd.read_sql_query(query, connection, params=parameters)
    if frame.empty:
        return pd.DataFrame(
            columns=["id", "record_date", "client_name", "amount", "currency", "note", "created_at"]
        )
    frame["record_date"] = pd.to_datetime(frame["record_date"], errors="coerce")
    return frame


def save_credit_entries(
    record_date: str, entries: list[Mapping[str, Any]], sync_csv: bool = True
) -> None:
    """Remplace atomiquement la liste des crédits d'une journée."""
    now = datetime.now().isoformat(timespec="seconds")
    total_usd = sum(
        float(entry["amount"])
        for entry in entries
        if str(entry["currency"]).upper() == "USD"
    )
    total_lbp = sum(
        float(entry["amount"])
        for entry in entries
        if str(entry["currency"]).upper() == "LBP"
    )
    currencies = {str(entry["currency"]).upper() for entry in entries}
    legacy_currency = next(iter(currencies)) if len(currencies) == 1 else "MIXED"
    legacy_amount = sum(float(entry["amount"]) for entry in entries) if len(currencies) == 1 else 0
    client_summary = ", ".join(dict.fromkeys(str(entry["client_name"]).strip() for entry in entries))
    with get_connection() as connection:
        connection.execute("DELETE FROM credit_sales WHERE record_date = ?", (record_date,))
        connection.executemany(
            """
            INSERT INTO credit_sales
                (record_date, client_name, amount, currency, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record_date,
                    str(entry["client_name"]).strip(),
                    float(entry["amount"]),
                    str(entry["currency"]).upper(),
                    str(entry.get("note", "")).strip(),
                    now,
                )
                for entry in entries
            ],
        )
        connection.execute(
            """
            UPDATE daily_records
            SET credit_customer = ?, credit_amount = ?, credit_currency = ?,
                credit_sales_usd = ?, credit_sales_lbp = ?, updated_at = ?
            WHERE record_date = ?
            """,
            (
                client_summary,
                legacy_amount,
                legacy_currency,
                total_usd,
                total_lbp,
                now,
                record_date,
            ),
        )
    if sync_csv:
        sync_csv_backup()


def load_credit_payments(record_date: str | None = None) -> pd.DataFrame:
    """Charge les encaissements de crédits, avec le client et la devise."""
    query = "SELECT * FROM credit_payments"
    parameters: tuple[Any, ...] = ()
    if record_date is not None:
        query += " WHERE record_date = ?"
        parameters = (record_date,)
    query += " ORDER BY record_date ASC, id ASC"
    with get_connection() as connection:
        frame = pd.read_sql_query(query, connection, params=parameters)
    if frame.empty:
        return pd.DataFrame(
            columns=["id", "record_date", "client_name", "amount", "currency", "note", "created_at"]
        )
    frame["record_date"] = pd.to_datetime(frame["record_date"], errors="coerce")
    return frame


def load_known_credit_clients() -> list[str]:
    """Renvoie les clients déjà utilisés, sans doublons de casse."""
    clients_by_key: dict[str, str] = {}
    for frame in (load_credit_entries(), load_credit_payments()):
        for value in frame["client_name"].dropna():
            client_name = str(value).strip()
            if client_name:
                clients_by_key.setdefault(client_name.casefold(), client_name)
    return sorted(clients_by_key.values(), key=str.casefold)


def save_credit_payments(
    record_date: str, entries: list[Mapping[str, Any]], sync_csv: bool = True
) -> None:
    """Remplace les crédits encaissés d'une journée et actualise leurs totaux."""
    now = datetime.now().isoformat(timespec="seconds")
    totals = {
        currency: sum(
            float(entry["amount"])
            for entry in entries
            if str(entry["currency"]).upper() == currency
        )
        for currency in ("USD", "LBP")
    }
    with get_connection() as connection:
        connection.execute("DELETE FROM credit_payments WHERE record_date = ?", (record_date,))
        connection.executemany(
            """
            INSERT INTO credit_payments
                (record_date, client_name, amount, currency, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    record_date,
                    str(entry["client_name"]).strip(),
                    float(entry["amount"]),
                    str(entry["currency"]).upper(),
                    str(entry.get("note", "")).strip(),
                    now,
                )
                for entry in entries
            ],
        )
        connection.execute(
            """
            UPDATE daily_records
            SET credit_collected_usd = ?, credit_collected_lbp = ?,
                updated_at = ?
            WHERE record_date = ?
            """,
            (totals["USD"], totals["LBP"], now, record_date),
        )
    if sync_csv:
        sync_csv_backup()


def migrate_legacy_credits() -> int:
    """Transforme une ancienne vente à crédit unique en ligne détaillée."""
    migrated = 0
    with get_connection() as connection:
        legacy_rows = connection.execute(
            """
            SELECT record_date, credit_customer, credit_amount, credit_currency
            FROM daily_records AS daily
            WHERE credit_amount > 0
              AND NOT EXISTS (
                  SELECT 1 FROM credit_sales AS credit
                  WHERE credit.record_date = daily.record_date
              )
            """
        ).fetchall()
        for row in legacy_rows:
            currency = str(row["credit_currency"]).upper()
            amount = float(row["credit_amount"])
            connection.execute(
                """
                INSERT INTO credit_sales
                    (record_date, client_name, amount, currency, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["record_date"],
                    row["credit_customer"] or "Client non renseigné",
                    amount,
                    currency,
                    "Importé depuis l'ancienne saisie",
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            target_column = "credit_sales_lbp" if currency == "LBP" else "credit_sales_usd"
            connection.execute(
                f'UPDATE daily_records SET "{target_column}" = ? WHERE record_date = ?',
                (amount, row["record_date"]),
            )
            migrated += 1
    return migrated


def _number(record: Mapping[str, Any], field: str) -> float:
    value = record.get(field, 0)
    if value is None or pd.isna(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def calculate_totals(record: Mapping[str, Any]) -> dict[str, float]:
    """Calcule stock, ventes, dépenses, crédits et rapprochement des caisses."""
    currencies = ("usd", "lbp")
    sales = {
        currency: _number(record, f"fuel_sales_{currency}") for currency in currencies
    }

    for prefix, legacy_amount, legacy_currency in (
        ("tires_sales", "tires_sales_amount", "tires_sales_currency"),
        ("gas_sales", "gas_sales_amount", "gas_sales_currency"),
        ("wash_sales", "wash_sales_amount", "wash_sales_currency"),
    ):
        explicit = {currency: _number(record, f"{prefix}_{currency}") for currency in currencies}
        if any(explicit.values()):
            for currency in currencies:
                sales[currency] += explicit[currency]
        else:
            amount = _number(record, legacy_amount)
            target = str(record.get(legacy_currency, "USD")).lower()
            sales[target if target in currencies else "usd"] += amount

    for currency in currencies:
        sales[currency] += _number(record, f"other_sales_{currency}")

    credit_sold = {
        currency: _number(record, f"credit_sales_{currency}") for currency in currencies
    }
    if not any(credit_sold.values()):
        legacy_credit = _number(record, "credit_amount")
        target = str(record.get("credit_currency", "USD")).lower()
        credit_sold[target if target in currencies else "usd"] = legacy_credit
    for currency in currencies:
        sales[currency] += credit_sold[currency]

    credit_collected = {
        currency: _number(record, f"credit_collected_{currency}")
        for currency in currencies
    }
    expenses = {
        currency: sum(
            _number(record, f"{prefix}_{currency}")
            for prefix in EXPENSE_CATEGORIES.values()
        )
        for currency in currencies
    }

    usd_lbp_rate = _number(record, "exchange_rate")

    def usd_equivalent(values: Mapping[str, float]) -> float:
        return (
            values["usd"]
            + (values["lbp"] / usd_lbp_rate if usd_lbp_rate > 0 else 0)
        )

    sales_equiv = usd_equivalent(sales)
    expenses_equiv = usd_equivalent(expenses)
    credit_sold_equiv = usd_equivalent(credit_sold)
    credit_collected_equiv = usd_equivalent(credit_collected)

    theoretical_stock = (
        _number(record, "opening_stock_l")
        + _number(record, "fuel_input_l")
        - _number(record, "fuel_volume_sold_l")
    )
    actual_stock = _number(record, "stock_available_l")

    result: dict[str, float] = {
        "total_sales_usd_equiv": sales_equiv,
        "total_expenses_usd_equiv": expenses_equiv,
        "net_usd_equiv": sales_equiv - expenses_equiv,
        "credit_sold_usd_equiv": credit_sold_equiv,
        "credit_collected_usd_equiv": credit_collected_equiv,
        "theoretical_stock_end_l": theoretical_stock,
        "stock_variance_l": actual_stock - theoretical_stock,
        "calculated_stock_value_usd": actual_stock
        * _number(record, "fuel_cost_usd_per_l"),
    }
    for currency in currencies:
        theoretical_cash = (
            _number(record, f"cash_opening_{currency}")
            + sales[currency]
            - credit_sold[currency]
            + credit_collected[currency]
            - expenses[currency]
        )
        actual_cash = _number(record, f"cash_actual_end_{currency}")
        result.update(
            {
                f"total_sales_{currency}": sales[currency],
                f"total_expenses_{currency}": expenses[currency],
                f"net_{currency}": sales[currency] - expenses[currency],
                f"cash_theoretical_end_{currency}": theoretical_cash,
                f"cash_variance_{currency}": actual_cash - theoretical_cash,
            }
        )
    return result


def enrich_data(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        for column in calculate_totals({}):
            frame[column] = pd.Series(dtype="float64")
        return frame
    totals = frame.apply(lambda row: pd.Series(calculate_totals(row)), axis=1)
    return pd.concat([frame.reset_index(drop=True), totals.reset_index(drop=True)], axis=1)


def _write_remote_head(commit_sha: str) -> None:
    temporary_path = REMOTE_HEAD_PATH.with_suffix(".tmp")
    temporary_path.write_text(commit_sha, encoding="utf-8")
    temporary_path.replace(REMOTE_HEAD_PATH)


def _read_remote_head() -> str | None:
    try:
        value = REMOTE_HEAD_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _write_bytes_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_bytes(content)
    temporary_path.replace(path)


def sync_csv_backup(expected_head: str | None = None) -> None:
    """Réécrit les trois CSV puis les valide ensemble sur GitHub."""
    frame = load_data().copy()
    if "record_date" in frame:
        frame["record_date"] = pd.to_datetime(frame["record_date"], errors="coerce").dt.strftime(
            "%Y-%m-%d"
        )
    temporary_path = CSV_PATH.with_suffix(".csv.tmp")
    frame.to_csv(temporary_path, index=False, encoding="utf-8-sig")
    temporary_path.replace(CSV_PATH)

    credits = load_credit_entries().copy()
    if "record_date" in credits:
        credits["record_date"] = pd.to_datetime(
            credits["record_date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")
    temporary_credits_path = CREDITS_CSV_PATH.with_suffix(".csv.tmp")
    credits.to_csv(temporary_credits_path, index=False, encoding="utf-8-sig")
    temporary_credits_path.replace(CREDITS_CSV_PATH)

    payments = load_credit_payments().copy()
    if "record_date" in payments:
        payments["record_date"] = pd.to_datetime(
            payments["record_date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")
    temporary_payments_path = CREDIT_PAYMENTS_CSV_PATH.with_suffix(".csv.tmp")
    payments.to_csv(temporary_payments_path, index=False, encoding="utf-8-sig")
    temporary_payments_path.replace(CREDIT_PAYMENTS_CSV_PATH)

    storage = get_github_storage()
    parent_commit = expected_head or _read_remote_head()
    try:
        new_commit = storage.commit_files(
            {
                remote_path: local_path.read_bytes()
                for remote_path, local_path in REMOTE_DATA_FILES.items()
            },
            message=(
                "data: synchronisation Station Pilot "
                f"{datetime.now().isoformat(timespec='seconds')}"
            ),
            expected_head=parent_commit,
        )
    except GitHubStorageError:
        # Un prochain rerun rechargera la version distante au lieu de garder
        # silencieusement une modification non sauvegardée dans le cache.
        REMOTE_HEAD_PATH.unlink(missing_ok=True)
        raise
    _write_remote_head(new_commit)


def backup_database() -> str:
    """Renvoie le commit GitHub qui précède une suppression."""
    commit_sha = _read_remote_head() or get_github_storage().head_sha()
    return f"commit GitHub {commit_sha[:7]}"


def delete_records(record_dates: Sequence[str]) -> tuple[list[str], str]:
    """Supprime des journées et tout ce qui leur est rattaché.

    Renvoie les dates réellement supprimées et le nom de la sauvegarde créée.
    Aucune sauvegarde n'est produite si rien ne correspond à la demande.
    """
    wanted = sorted({str(value).strip() for value in record_dates if str(value).strip()})
    if not wanted:
        return [], ""

    placeholders = ", ".join("?" for _ in wanted)
    connection = get_connection()
    try:
        existing = [
            row[0]
            for row in connection.execute(
                f"SELECT record_date FROM daily_records WHERE record_date IN ({placeholders})",
                wanted,
            )
        ]
    finally:
        connection.close()
    if not existing:
        return [], ""

    backup_name = backup_database()

    existing_placeholders = ", ".join("?" for _ in existing)
    connection = get_connection()
    try:
        with connection:
            connection.execute(
                f"DELETE FROM credit_sales WHERE record_date IN ({existing_placeholders})",
                existing,
            )
            connection.execute(
                f"DELETE FROM credit_payments WHERE record_date IN ({existing_placeholders})",
                existing,
            )
            connection.execute(
                f"DELETE FROM daily_records WHERE record_date IN ({existing_placeholders})",
                existing,
            )
    finally:
        connection.close()

    # Le nouveau commit conserve l'ancien commit dans l'historique GitHub : une
    # suppression accidentelle reste donc récupérable.
    sync_csv_backup()
    return existing, backup_name

def restore_database_from_csv() -> int:
    """Restaure SQLite depuis le CSV seulement lorsque la base est vide."""
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return 0
    try:
        csv_frame = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return 0
    if csv_frame.empty or "record_date" not in csv_frame.columns:
        return 0

    text_fields = {"record_date", "credit_customer", "notes"}
    restored = 0
    for _, row in csv_frame.iterrows():
        record: dict[str, Any] = {}
        for column in EDITABLE_COLUMNS:
            value = row.get(column, pd.NA)
            if pd.isna(value):
                if "currency" in column:
                    value = "USD"
                elif column in text_fields:
                    value = ""
                else:
                    value = 0
            record[column] = value
        parsed_date = pd.to_datetime(record["record_date"], errors="coerce")
        if pd.isna(parsed_date):
            continue
        record["record_date"] = parsed_date.date().isoformat()
        save_record(record, allow_update=True, sync_csv=False)
        restored += 1

    if CREDITS_CSV_PATH.exists() and CREDITS_CSV_PATH.stat().st_size > 0:
        try:
            credits_frame = pd.read_csv(CREDITS_CSV_PATH, encoding="utf-8-sig")
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
            credits_frame = pd.DataFrame()
        required = {"record_date", "client_name", "amount", "currency"}
        if not credits_frame.empty and required.issubset(credits_frame.columns):
            for credit_date, group in credits_frame.groupby("record_date"):
                entries = [
                    {
                        "client_name": row["client_name"],
                        "amount": row["amount"],
                        "currency": row["currency"],
                        "note": "" if pd.isna(row.get("note", "")) else row.get("note", ""),
                    }
                    for _, row in group.iterrows()
                    if not pd.isna(row["client_name"]) and float(row["amount"]) > 0
                ]
                if entries:
                    save_credit_entries(str(credit_date), entries, sync_csv=False)
    if CREDIT_PAYMENTS_CSV_PATH.exists() and CREDIT_PAYMENTS_CSV_PATH.stat().st_size > 0:
        try:
            payments_frame = pd.read_csv(
                CREDIT_PAYMENTS_CSV_PATH, encoding="utf-8-sig"
            )
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
            payments_frame = pd.DataFrame()
        required = {"record_date", "client_name", "amount", "currency"}
        if not payments_frame.empty and required.issubset(payments_frame.columns):
            for payment_date, group in payments_frame.groupby("record_date"):
                entries = [
                    {
                        "client_name": row["client_name"],
                        "amount": row["amount"],
                        "currency": row["currency"],
                        "note": "" if pd.isna(row.get("note", "")) else row.get("note", ""),
                    }
                    for _, row in group.iterrows()
                    if not pd.isna(row["client_name"]) and float(row["amount"]) > 0
                ]
                if entries:
                    save_credit_payments(str(payment_date), entries, sync_csv=False)
    return restored


def initialize_storage() -> int:
    """Synchronise le cache temporaire avec la branche GitHub de données."""
    storage = get_github_storage()
    remote_head = storage.head_sha()
    cache_ready = DB_PATH.exists() and all(
        path.exists() for path in REMOTE_DATA_FILES.values()
    )

    if cache_ready and _read_remote_head() == remote_head:
        initialize_database()
        migrated = migrate_legacy_credits()
        if migrated:
            sync_csv_backup(expected_head=remote_head)
        return 0

    remote_files, stable_head = storage.download_files(list(REMOTE_DATA_FILES))
    remote_was_empty = all(content is None for content in remote_files.values())
    if remote_was_empty:
        # Première installation : une exécution locale peut importer les anciens
        # CSV placés à côté de app.py. Sur Streamlit Cloud, une base vide est créée.
        for remote_path, runtime_path in REMOTE_DATA_FILES.items():
            legacy_path = APP_DIR / runtime_path.name
            if legacy_path.exists():
                remote_files[remote_path] = legacy_path.read_bytes()

    main_remote_path = "data/station_data.csv"
    if remote_files[main_remote_path] is None:
        for path in (DB_PATH, Path(f"{DB_PATH}-wal"), Path(f"{DB_PATH}-shm")):
            path.unlink(missing_ok=True)
        initialize_database()
        _write_remote_head(stable_head)
        sync_csv_backup(expected_head=stable_head)
        return 0

    missing_remote_file = False
    for remote_path, runtime_path in REMOTE_DATA_FILES.items():
        content = remote_files[remote_path]
        if content is None:
            runtime_path.unlink(missing_ok=True)
            missing_remote_file = True
        else:
            _write_bytes_atomically(runtime_path, content)

    for path in (DB_PATH, Path(f"{DB_PATH}-wal"), Path(f"{DB_PATH}-shm")):
        path.unlink(missing_ok=True)
    initialize_database()
    restored = restore_database_from_csv()
    _write_remote_head(stable_head)
    migrated = migrate_legacy_credits()
    if migrated or missing_remote_file or remote_was_empty:
        sync_csv_backup(expected_head=stable_head)
    return restored


def format_fr(value: float, decimals: int = 2) -> str:
    """Nombre au format français : espace fine insécable, virgule décimale."""
    formatted = f"{value:,.{decimals}f}"
    # U+202F : espace fine insécable, séparateur de milliers français.
    return formatted.replace(",", " ").replace(".", ",")


def format_usd(value: float) -> str:
    return f"{format_fr(value)} $"


def format_lbp(value: float) -> str:
    return f"{format_fr(value, 0)} LL"


def format_date_fr(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "—" if pd.isna(parsed) else parsed.strftime("%d/%m/%Y")


def build_credit_activity(
    history: pd.DataFrame,
    credits: pd.DataFrame,
    payments: pd.DataFrame,
) -> pd.DataFrame:
    """Réunit ventes à crédit et encaissements dans un historique homogène."""
    columns = [
        "Date",
        "Opération",
        "Client",
        "Client_key",
        "Montant",
        "Devise",
        "Taux LL/USD",
        "Équivalent USD",
        "Note",
    ]
    rates_by_date = {
        row["record_date"].date(): _number(row, "exchange_rate")
        for _, row in history.dropna(subset=["record_date"]).iterrows()
    }
    latest_rate = 0.0
    if not history.empty:
        dated_history = history.dropna(subset=["record_date"]).sort_values("record_date")
        if not dated_history.empty:
            latest_rate = _number(dated_history.iloc[-1], "exchange_rate")

    rows: list[dict[str, Any]] = []

    def append_operations(source: pd.DataFrame, operation: str) -> None:
        for _, entry in source.iterrows():
            parsed_date = pd.to_datetime(entry.get("record_date"), errors="coerce")
            if pd.isna(parsed_date):
                continue
            client_value = entry.get("client_name", "")
            client = "" if pd.isna(client_value) else " ".join(str(client_value).split())
            if not client:
                client = "Client non renseigné"
            currency = str(entry.get("currency", "USD")).upper()
            amount = _number(entry, "amount")
            rate = rates_by_date.get(parsed_date.date(), latest_rate)
            note_value = entry.get("note", "")
            note = "" if pd.isna(note_value) else str(note_value).strip()
            equivalent = amount if currency == "USD" else amount / rate if rate > 0 else 0
            rows.append(
                {
                    "Date": parsed_date,
                    "Opération": operation,
                    "Client": client,
                    "Client_key": client.casefold(),
                    "Montant": amount,
                    "Devise": currency,
                    "Taux LL/USD": rate,
                    "Équivalent USD": equivalent,
                    "Note": note,
                }
            )

    append_operations(credits, "Vente à crédit")
    append_operations(payments, "Encaissement")
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns).sort_values("Date", ascending=False)


def build_credit_balances(
    activity: pd.DataFrame, current_exchange_rate: float
) -> pd.DataFrame:
    """Calcule les montants vendus, encaissés et restant dus par client."""
    columns = [
        "Client",
        "Vendu USD",
        "Encaissé USD",
        "Solde USD",
        "Vendu LL",
        "Encaissé LL",
        "Solde LL",
        "Vendu équiv. USD",
        "Encaissé équiv. USD",
        "Encours équiv. USD",
        "Dernière activité",
        "Statut",
    ]
    if activity.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for _, client_activity in activity.groupby("Client_key", sort=False):
        sales = client_activity[client_activity["Opération"] == "Vente à crédit"]
        payments = client_activity[client_activity["Opération"] == "Encaissement"]
        sold_usd = float(sales.loc[sales["Devise"] == "USD", "Montant"].sum())
        paid_usd = float(payments.loc[payments["Devise"] == "USD", "Montant"].sum())
        sold_lbp = float(sales.loc[sales["Devise"] == "LBP", "Montant"].sum())
        paid_lbp = float(payments.loc[payments["Devise"] == "LBP", "Montant"].sum())
        balance_usd = sold_usd - paid_usd
        balance_lbp = sold_lbp - paid_lbp
        balance_equivalent = balance_usd + (
            balance_lbp / current_exchange_rate if current_exchange_rate > 0 else 0
        )
        if abs(balance_usd) < 0.005 and abs(balance_lbp) < 0.5:
            status = "Soldé"
        elif balance_usd > 0.005 or balance_lbp > 0.5:
            status = "À encaisser"
        else:
            status = "Avance client"
        latest_row = client_activity.sort_values("Date").iloc[-1]
        rows.append(
            {
                "Client": latest_row["Client"],
                "Vendu USD": sold_usd,
                "Encaissé USD": paid_usd,
                "Solde USD": balance_usd,
                "Vendu LL": sold_lbp,
                "Encaissé LL": paid_lbp,
                "Solde LL": balance_lbp,
                "Vendu équiv. USD": float(sales["Équivalent USD"].sum()),
                "Encaissé équiv. USD": float(payments["Équivalent USD"].sum()),
                "Encours équiv. USD": balance_equivalent,
                "Dernière activité": latest_row["Date"],
                "Statut": status,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(
        "Encours équiv. USD", ascending=False
    )


def build_sales_breakdown(record: Mapping[str, Any], credits: pd.DataFrame) -> pd.DataFrame:
    """Produit une lecture exhaustive des ventes d'une journée."""
    rate = _number(record, "exchange_rate")
    rows: list[dict[str, Any]] = []

    def add_row(category: str, detail: str, usd: float, lbp: float) -> None:
        rows.append(
            {
                "Catégorie": category,
                "Détail": detail,
                "USD": usd,
                "LL": lbp,
                "Équivalent USD": usd + (lbp / rate if rate > 0 else 0),
            }
        )

    add_row(
        "Essence",
        f"{format_fr(_number(record, 'fuel_volume_sold_l'), 1)} litres vendus",
        _number(record, "fuel_sales_usd"),
        _number(record, "fuel_sales_lbp"),
    )
    for label, prefix in list(SALES_CATEGORIES.items())[1:]:
        add_row(
            label,
            "Vente comptant",
            _number(record, f"{prefix}_usd"),
            _number(record, f"{prefix}_lbp"),
        )

    for _, credit in credits.iterrows():
        currency = str(credit.get("currency", "USD")).upper()
        amount = _number(credit, "amount")
        note_value = credit.get("note", "")
        note = "" if pd.isna(note_value) else str(note_value).strip()
        add_row(
            "Vente à crédit",
            f"{credit.get('client_name', '')}{' — ' + note if note else ''}",
            amount if currency == "USD" else 0,
            amount if currency == "LBP" else 0,
        )
    return pd.DataFrame(rows)


def build_expense_breakdown(record: Mapping[str, Any]) -> pd.DataFrame:
    """Affiche toutes les catégories de dépenses, y compris celles à zéro."""
    rate = _number(record, "exchange_rate")
    rows = []
    for label, prefix in EXPENSE_CATEGORIES.items():
        usd = _number(record, f"{prefix}_usd")
        lbp = _number(record, f"{prefix}_lbp")
        rows.append(
            {
                "Catégorie": label,
                "USD": usd,
                "LL": lbp,
                "Équivalent USD": usd + (lbp / rate if rate > 0 else 0),
            }
        )
    return pd.DataFrame(rows)


def build_transaction_ledger(
    history: pd.DataFrame,
    credits: pd.DataFrame,
    payments: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Transforme les journées en journal comptable : une opération par ligne."""
    columns = [
        "Date",
        "Type",
        "Catégorie",
        "Détail",
        "Devise",
        "Montant",
        "Taux LL/USD",
        "Équivalent USD",
    ]
    rows: list[dict[str, Any]] = []
    credits_by_date = {
        key: group for key, group in credits.groupby(credits["record_date"].dt.date)
    } if not credits.empty else {}
    if payments is None:
        payments = load_credit_payments()
    payments_by_date = {
        key: group for key, group in payments.groupby(payments["record_date"].dt.date)
    } if not payments.empty else {}

    def add(
        day: date,
        operation_type: str,
        category: str,
        detail: str,
        currency: str,
        amount: float,
        rate: float,
    ) -> None:
        if amount <= 0:
            return
        rows.append(
            {
                "Date": day,
                "Type": operation_type,
                "Catégorie": category,
                "Détail": detail,
                "Devise": currency,
                "Montant": amount,
                "Taux LL/USD": rate,
                "Équivalent USD": amount
                if currency == "USD"
                else amount / rate
                if currency == "LBP" and rate > 0
                else 0,
            }
        )

    for _, record in history.sort_values("record_date").iterrows():
        if pd.isna(record["record_date"]):
            continue
        day = record["record_date"].date()
        rate = _number(record, "exchange_rate")
        for label, prefix in SALES_CATEGORIES.items():
            detail = (
                f"{format_fr(_number(record, 'fuel_volume_sold_l'), 1)} L"
                if prefix == "fuel_sales"
                else "Comptant"
            )
            for currency in ("USD", "LBP"):
                add(
                    day,
                    "Vente",
                    label,
                    detail,
                    currency,
                    _number(record, f"{prefix}_{currency.lower()}"),
                    rate,
                )
        for _, credit in credits_by_date.get(day, pd.DataFrame()).iterrows():
            note_value = credit.get("note", "")
            note = "" if pd.isna(note_value) else str(note_value).strip()
            detail = f"Client : {credit['client_name']}{' — ' + note if note else ''}"
            add(day, "Vente à crédit", "Crédit client", detail, str(credit["currency"]).upper(), _number(credit, "amount"), rate)
        for _, payment in payments_by_date.get(day, pd.DataFrame()).iterrows():
            note_value = payment.get("note", "")
            note = "" if pd.isna(note_value) else str(note_value).strip()
            detail = f"Client : {payment['client_name']}{' — ' + note if note else ''}"
            add(day, "Crédit encaissé", "Encaissement client", detail, str(payment["currency"]).upper(), _number(payment, "amount"), rate)
        for label, prefix in EXPENSE_CATEGORIES.items():
            for currency in ("USD", "LBP"):
                add(day, "Dépense", label, "", currency, _number(record, f"{prefix}_{currency.lower()}"), rate)
    return pd.DataFrame(rows, columns=columns)


def build_grouped_daily_export(history: pd.DataFrame) -> pd.DataFrame:
    """Construit le grand tableau de clôture, une ligne complète par journée."""
    rows: list[dict[str, Any]] = []
    for _, record in history.sort_values("record_date").iterrows():
        other_expenses = {
            currency: sum(
                _number(record, f"{prefix}_{currency}")
                for prefix in ("delivery_tip", "maintenance", "other_expenses")
            )
            for currency in ("usd", "lbp")
        }
        row: dict[str, Any] = {
            "Date": record["record_date"],
            "Taux USD/LBP": _number(record, "exchange_rate"),
            "Stock ouverture L": _number(record, "opening_stock_l"),
            "Entrées carburant L": _number(record, "fuel_input_l"),
            "Ventes essence L": _number(record, "fuel_volume_sold_l"),
            "Stock théorique fin L": _number(record, "theoretical_stock_end_l"),
            "Stock réel fin L": _number(record, "stock_available_l"),
            "Écart stock L": _number(record, "stock_variance_l"),
            "Coût carburant USD/L": _number(record, "fuel_cost_usd_per_l"),
            "Valeur stock USD": _number(record, "stock_value_usd"),
        }
        for label, prefix in (
            ("Électricité", "electricity"),
            ("Pneu", "tires_purchase"),
            ("Achat essence", "fuel_purchase"),
            ("Salaire", "salaries"),
        ):
            for currency, display in (("usd", "USD"), ("lbp", "LBP")):
                row[f"{label} {display}"] = _number(record, f"{prefix}_{currency}")
        for currency, display in (("usd", "USD"), ("lbp", "LBP")):
            row[f"Autres dépenses {display}"] = other_expenses[currency]
        for label, prefix in SALES_CATEGORIES.items():
            for currency, display in (("usd", "USD"), ("lbp", "LBP")):
                row[f"Vente {label.lower()} {display}"] = _number(
                    record, f"{prefix}_{currency}"
                )
        for currency, display in (("usd", "USD"), ("lbp", "LBP")):
            row[f"Crédit vendu {display}"] = _number(record, f"credit_sales_{currency}")
            row[f"Crédit encaissé {display}"] = _number(
                record, f"credit_collected_{currency}"
            )
            row[f"Total ventes {display}"] = _number(record, f"total_sales_{currency}")
            row[f"Total dépenses {display}"] = _number(
                record, f"total_expenses_{currency}"
            )
        row.update(
            {
                "Ventes USD équiv.": _number(record, "total_sales_usd_equiv"),
                "Dépenses USD équiv.": _number(record, "total_expenses_usd_equiv"),
                "Solde ventes-dépenses USD": _number(record, "net_usd_equiv"),
                "Crédit vendu USD équiv.": _number(record, "credit_sold_usd_equiv"),
                "Crédit encaissé USD équiv.": _number(
                    record, "credit_collected_usd_equiv"
                ),
            }
        )
        for currency, display in (("usd", "USD"), ("lbp", "LBP")):
            row[f"Ouverture {display}"] = _number(record, f"cash_opening_{currency}")
            row[f"Caisse réelle fin {display}"] = _number(
                record, f"cash_actual_end_{currency}"
            )
            row[f"Caisse théorique fin {display}"] = _number(
                record, f"cash_theoretical_end_{currency}"
            )
            row[f"Écart caisse {display}"] = _number(
                record, f"cash_variance_{currency}"
            )
        clients = str(record.get("credit_customer", "") or "").strip()
        notes = str(record.get("notes", "") or "").strip()
        row["Notes / clients crédit"] = " | ".join(
            value for value in (clients, notes) if value
        )
        rows.append(row)
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False, max_entries=6)
def build_excel_export(
    frame: pd.DataFrame,
    credits: pd.DataFrame | None = None,
    payments: pd.DataFrame | None = None,
) -> bytes:
    """Construit un classeur avec une synthèse lisible et les données complètes."""
    output = BytesIO()
    summary_columns = [
        "record_date",
        "exchange_rate",
        "fuel_volume_sold_l",
        "stock_available_l",
        "total_sales_usd",
        "total_sales_lbp",
        "total_expenses_usd",
        "total_expenses_lbp",
        "net_usd",
        "net_lbp",
        "net_usd_equiv",
        "credit_customer",
        "credit_sales_usd",
        "credit_sales_lbp",
    ]
    labels = {
        "record_date": "Date",
        "exchange_rate": "Taux LL / USD",
        "fuel_volume_sold_l": "Litres vendus",
        "stock_available_l": "Stock disponible (L)",
        "total_sales_usd": "Ventes USD",
        "total_sales_lbp": "Ventes LL",
        "total_expenses_usd": "Dépenses USD",
        "total_expenses_lbp": "Dépenses LL",
        "net_usd": "Solde USD",
        "net_lbp": "Solde LL",
        "net_usd_equiv": "Résultat équiv. USD",
        "credit_customer": "Client à crédit",
        "credit_sales_usd": "Crédits USD",
        "credit_sales_lbp": "Crédits LL",
    }
    summary = frame[summary_columns].copy().rename(columns=labels)
    summary["Date"] = pd.to_datetime(summary["Date"]).dt.date

    raw = frame[[column for column in DB_COLUMNS if column in frame.columns]].copy()
    raw["record_date"] = pd.to_datetime(raw["record_date"]).dt.date

    if credits is None:
        credits = load_credit_entries()
    credit_export = credits.copy()
    if not credit_export.empty:
        credit_export["record_date"] = pd.to_datetime(credit_export["record_date"]).dt.date
    if payments is None:
        payments = load_credit_payments()
    payment_export = payments.copy()
    if not payment_export.empty:
        payment_export["record_date"] = pd.to_datetime(
            payment_export["record_date"]
        ).dt.date
    grouped_report = build_grouped_daily_export(frame)
    grouped_report["Date"] = pd.to_datetime(grouped_report["Date"]).dt.date
    ledger = build_transaction_ledger(frame, credits, payments)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, index=False, sheet_name="Synthèse")
        raw.to_excel(writer, index=False, sheet_name="Données complètes")
        grouped_report.to_excel(writer, index=False, sheet_name="Rapport journalier complet")
        credit_export.to_excel(writer, index=False, sheet_name="Clients à crédit")
        payment_export.to_excel(writer, index=False, sheet_name="Crédits encaissés")
        ledger.to_excel(writer, index=False, sheet_name="Journal ligne par ligne")
        for sheet_name in (
            "Synthèse",
            "Données complètes",
            "Rapport journalier complet",
            "Clients à crédit",
            "Crédits encaissés",
            "Journal ligne par ligne",
        ):
            sheet = writer.book[sheet_name]
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column_cells in sheet.columns:
                width = min(
                    max(len(str(cell.value or "")) for cell in column_cells) + 2,
                    32,
                )
                sheet.column_dimensions[column_cells[0].column_letter].width = width
    return output.getvalue()


def apply_styles(palette: Mapping[str, Any]) -> None:
    """Applique la feuille de style de l'application pour le thème actif."""
    st.markdown(
        f"""
        <style>
        :root {{
            --sp-bg: {palette["bg"]};
            --sp-surface: {palette["surface"]};
            --sp-surface-2: {palette["surface_2"]};
            --sp-surface-3: {palette["surface_3"]};
            --sp-ink: {palette["text"]};
            --sp-muted: {palette["muted"]};
            --sp-line: {palette["line"]};
            --sp-line-strong: {palette["line_strong"]};
            --sp-accent: {palette["accent"]};
            --sp-accent-strong: {palette["accent_strong"]};
            --sp-accent-soft: {palette["accent_soft"]};
            --sp-accent-wash: {palette["accent_wash"]};
            --sp-on-accent: {palette["on_accent"]};
            --sp-positive: {palette["positive"]};
            --sp-negative: {palette["negative"]};
            --sp-warning: {palette["warning"]};
            --sp-warning-soft: {palette["warning_soft"]};
            --sp-danger-soft: {palette["danger_soft"]};
            --sp-info: {palette["info"]};
            --sp-info-soft: {palette["info_soft"]};
            --sp-shadow: {palette["shadow"]};
        }}

        [data-testid="stAppViewContainer"] {{
            background:
                radial-gradient(circle at 91% 4%, {palette["glow_1"]}, transparent 24rem),
                radial-gradient(circle at 52% 102%, {palette["glow_2"]}, transparent 28rem),
                var(--sp-bg);
        }}
        [data-testid="stHeader"] {{ background: transparent; }}
        .block-container {{ max-width: 1480px; padding: 1.6rem 2.15rem 4.5rem; }}
        .stApp h1, .stApp h2, .stApp h3, .stApp h4 {{ letter-spacing: -0.035em; }}
        .stApp h2 {{ font-size: clamp(1.55rem, 2vw, 2rem); }}
        .stApp h3 {{ font-size: 1.2rem; }}
        .stApp h4 {{ font-size: 1.02rem; margin-top: 0.4rem; }}
        .stApp [data-testid="stMain"] [data-testid="stWidgetLabel"] p {{
            color: var(--sp-ink);
            font-weight: 650;
        }}
        .stApp [data-testid="stMain"] [data-testid="stCaptionContainer"],
        .stApp [data-testid="stMain"] [data-testid="stCaptionContainer"] p {{
            color: var(--sp-muted);
            font-weight: 500;
        }}
        .stApp [data-testid="stMain"] input::placeholder,
        .stApp [data-testid="stMain"] textarea::placeholder {{
            color: var(--sp-muted);
            opacity: 0.82;
        }}

        /* ------------------------------------------------------ Rail ---- */
        section[data-testid="stSidebar"] {{
            background: {SIDEBAR_GRADIENTS[palette["base"]]};
            border-right: 1px solid rgba(255, 255, 255, 0.08);
        }}
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: 1.1rem; }}
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{ color: #eaf6f1; }}
        section[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 0.42rem; }}
        section[data-testid="stSidebar"] [role="radiogroup"] label {{
            border: 1px solid transparent;
            border-radius: 12px;
            padding: 0.62rem 0.72rem;
            transition: background 150ms ease, border-color 150ms ease, transform 150ms ease;
        }}
        section[data-testid="stSidebar"] [role="radiogroup"] label:hover {{
            background: rgba(255, 255, 255, 0.08);
            transform: translateX(2px);
        }}
        section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
            background: rgba(61, 211, 157, 0.18);
            border-color: rgba(103, 232, 183, 0.30);
        }}
        section[data-testid="stSidebar"] hr {{ border-color: rgba(255, 255, 255, 0.13); }}
        section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
            background: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(255, 255, 255, 0.14);
            color: #eaf6f1;
            border-radius: 999px;
        }}
        section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {{
            background: rgba(255, 255, 255, 0.13);
            border-color: rgba(103, 232, 183, 0.40);
            color: #ffffff;
        }}
        .sidebar-brand {{ padding: 0.65rem 0.45rem 1rem; }}
        .sidebar-brand__mark {{
            align-items: center;
            background: linear-gradient(135deg, #34d399, #f2b84b);
            border-radius: 14px;
            box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
            color: #09291f;
            display: inline-flex;
            font-size: 1.25rem;
            height: 2.7rem;
            justify-content: center;
            margin-bottom: 0.85rem;
            width: 2.7rem;
        }}
        .sidebar-brand__name {{
            color: #ffffff;
            font-size: 1.22rem;
            font-weight: 800;
            letter-spacing: -0.03em;
            line-height: 1.1;
        }}
        .sidebar-brand__tagline {{ color: #a9cabe; font-size: 0.78rem; margin-top: 0.3rem; }}
        .sidebar-status {{
            background: rgba(255, 255, 255, 0.07);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 12px;
            color: #d9eee6;
            font-size: 0.78rem;
            line-height: 1.45;
            padding: 0.8rem 0.9rem;
        }}

        /* --------------------------------------------------- Bandeau ---- */
        .page-hero {{
            background: linear-gradient(126deg, #072d22 0%, #0b4937 56%, #126b4e 100%);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 24px;
            box-shadow: 0 20px 52px rgba(7, 45, 34, 0.22);
            margin-bottom: 1.5rem;
            overflow: hidden;
            padding: clamp(1.4rem, 3vw, 2.3rem);
            position: relative;
        }}
        .page-hero::after {{
            background: radial-gradient(circle, rgba(121, 232, 187, 0.30), transparent 68%);
            content: "";
            height: 17rem;
            position: absolute;
            right: -5rem;
            top: -7.5rem;
            width: 17rem;
        }}
        .page-hero__eyebrow {{
            color: #a9f2d8;
            font-size: 0.7rem;
            font-weight: 800;
            letter-spacing: 0.15em;
            margin-bottom: 0.55rem;
            text-transform: uppercase;
        }}
        .page-hero__title {{
            color: #ffffff;
            font-size: clamp(1.7rem, 3vw, 2.6rem);
            font-weight: 800;
            letter-spacing: -0.048em;
            line-height: 1.06;
            margin: 0;
            max-width: 850px;
            position: relative;
        }}
        .page-hero__description {{
            color: #c3ddd3;
            font-size: 0.97rem;
            line-height: 1.6;
            margin: 0.75rem 0 0;
            max-width: 760px;
            position: relative;
        }}
        .page-hero__badge {{
            background: rgba(255, 255, 255, 0.10);
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 999px;
            color: #ffffff;
            display: inline-flex;
            font-size: 0.76rem;
            font-weight: 700;
            margin-top: 1.05rem;
            padding: 0.42rem 0.78rem;
            position: relative;
        }}
        .section-heading {{
            align-items: flex-end;
            display: flex;
            gap: 0.75rem;
            justify-content: space-between;
            margin: 1.6rem 0 0.75rem;
        }}
        .section-heading__title {{
            color: var(--sp-ink);
            font-size: 1.12rem;
            font-weight: 800;
            letter-spacing: -0.025em;
        }}
        .section-heading__hint {{ color: var(--sp-muted); font-size: 0.78rem; text-align: right; }}

        /* ------------------------------------------------ Indicateurs --- */
        div[data-testid="stMetric"] {{
            background: var(--sp-surface);
            border: 1px solid var(--sp-line);
            border-radius: 16px;
            box-shadow: var(--sp-shadow);
            min-height: 116px;
            padding: 1rem 1.05rem;
        }}
        div[data-testid="stMetricLabel"],
        div[data-testid="stMetricLabel"] p {{
            color: var(--sp-muted);
            font-size: 0.78rem;
            font-weight: 700;
        }}
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] > div {{
            color: var(--sp-ink);
            font-variant-numeric: tabular-nums;
            font-weight: 800;
            letter-spacing: -0.02em;
        }}
        .stat-card {{
            background: var(--sp-surface);
            border: 1px solid var(--sp-line);
            border-radius: 18px;
            box-shadow: var(--sp-shadow);
            min-height: 134px;
            overflow: hidden;
            padding: 1rem 1.05rem;
            position: relative;
            transition: transform 160ms ease, box-shadow 160ms ease;
        }}
        .stat-card:hover {{ transform: translateY(-2px); }}
        .stat-card::before {{
            background: var(--card-accent, var(--sp-accent));
            content: "";
            height: 4px;
            left: 0;
            position: absolute;
            right: 0;
            top: 0;
        }}
        .stat-card--success {{ --card-accent: var(--sp-accent); --card-soft: var(--sp-accent-soft); }}
        .stat-card--warning {{ --card-accent: var(--sp-warning); --card-soft: var(--sp-warning-soft); }}
        .stat-card--danger {{ --card-accent: var(--sp-negative); --card-soft: var(--sp-danger-soft); }}
        .stat-card--info {{ --card-accent: var(--sp-info); --card-soft: var(--sp-info-soft); }}
        .stat-card__top {{ align-items: center; display: flex; justify-content: space-between; }}
        .stat-card__label {{
            color: var(--sp-muted);
            font-size: 0.72rem;
            font-weight: 750;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }}
        .stat-card__icon {{
            background: var(--card-soft, var(--sp-accent-soft));
            border-radius: 10px;
            color: var(--card-accent, var(--sp-accent));
            font-size: 0.92rem;
            padding: 0.32rem 0.46rem;
        }}
        .stat-card__value {{
            color: var(--sp-ink);
            font-size: clamp(1.3rem, 2vw, 1.75rem);
            font-variant-numeric: tabular-nums;
            font-weight: 850;
            letter-spacing: -0.02em;
            line-height: 1.15;
            margin-top: 0.72rem;
        }}
        .stat-card__detail {{ color: var(--sp-muted); font-size: 0.74rem; margin-top: 0.4rem; }}
        .stat-card__delta {{
            align-items: center;
            border-radius: 999px;
            display: inline-flex;
            font-size: 0.72rem;
            font-variant-numeric: tabular-nums;
            font-weight: 800;
            gap: 0.3rem;
            margin-top: 0.55rem;
            padding: 0.24rem 0.5rem;
        }}
        .stat-card__delta--up {{ background: var(--sp-accent-soft); color: var(--sp-positive); }}
        .stat-card__delta--down {{ background: var(--sp-danger-soft); color: var(--sp-negative); }}
        .stat-card__delta--flat {{ background: var(--sp-surface-3); color: var(--sp-muted); }}
        .stat-card__delta small {{ font-size: 0.66rem; font-weight: 650; opacity: 0.82; }}

        .alert-card {{
            align-items: flex-start;
            background: var(--sp-surface);
            border: 1px solid var(--sp-line);
            border-left: 4px solid var(--alert-accent, var(--sp-info));
            border-radius: 14px;
            box-shadow: var(--sp-shadow);
            display: flex;
            gap: 0.72rem;
            margin-bottom: 0.65rem;
            min-height: 88px;
            padding: 0.85rem 0.95rem;
        }}
        .alert-card--success {{ --alert-accent: var(--sp-accent); }}
        .alert-card--warning {{ --alert-accent: var(--sp-warning); }}
        .alert-card--danger {{ --alert-accent: var(--sp-negative); }}
        .alert-card--info {{ --alert-accent: var(--sp-info); }}
        .alert-card__icon {{ font-size: 1.05rem; line-height: 1.25; }}
        .alert-card__title {{ color: var(--sp-ink); font-size: 0.86rem; font-weight: 800; }}
        .alert-card__text {{
            color: var(--sp-muted);
            font-size: 0.76rem;
            line-height: 1.45;
            margin-top: 0.18rem;
        }}

        /* ------------------------------------------------- Conteneurs --- */
        div[data-testid="stForm"] {{
            background: var(--sp-surface);
            border: 1px solid var(--sp-line);
            border-radius: 20px;
            box-shadow: var(--sp-shadow);
            padding: 1.3rem 1.35rem 0.4rem;
        }}
        .stApp [data-testid="stDataFrame"],
        .stApp [data-testid="stDataEditor"] {{
            border: 1px solid var(--sp-line);
            border-radius: 14px;
            box-shadow: var(--sp-shadow);
            overflow: hidden;
        }}
        .stApp [data-testid="stPlotlyChart"] {{
            background: var(--sp-surface);
            border: 1px solid var(--sp-line);
            border-radius: 18px;
            box-shadow: var(--sp-shadow);
            overflow: hidden;
            padding: 0.4rem;
        }}
        .stApp details {{
            background: var(--sp-surface);
            border: 1px solid var(--sp-line);
            border-radius: 14px;
        }}
        .stApp [data-testid="stExpander"] summary:hover {{ color: var(--sp-accent); }}

        /* ---------------------------------------------------- Onglets --- */
        .stApp [data-testid="stTabs"] [data-baseweb="tab-list"] {{
            background: var(--sp-surface-3);
            border-radius: 14px;
            gap: 0.25rem;
            padding: 0.3rem;
        }}
        .stApp [data-testid="stTabs"] [data-baseweb="tab-list"] button {{
            border-radius: 10px;
            color: var(--sp-muted);
            font-weight: 750;
            padding: 0.55rem 1rem;
        }}
        .stApp [data-testid="stTabs"] [data-baseweb="tab-list"] button[aria-selected="true"] {{
            background: var(--sp-surface);
            box-shadow: 0 3px 11px rgba(17, 51, 39, 0.10);
            color: var(--sp-ink);
        }}
        .stApp [data-testid="stTabs"] [data-baseweb="tab-highlight"],
        .stApp [data-testid="stTabs"] [data-baseweb="tab-border"] {{ display: none; }}

        /* ---------------------------------------------------- Boutons --- */
        .stApp button[kind="primary"],
        .stApp [data-testid="stBaseButton-primary"] {{
            background: linear-gradient(135deg, var(--sp-accent-strong), var(--sp-accent));
            border: 0;
            border-radius: 11px;
            box-shadow: 0 9px 20px rgba(15, 138, 102, 0.22);
            color: var(--sp-on-accent);
            min-height: 2.75rem;
        }}
        .stApp button[kind="primary"] p,
        .stApp [data-testid="stBaseButton-primary"] p {{ color: var(--sp-on-accent); }}
        /* Sans cela, le dégradé ci-dessus masque l'état grisé de Streamlit et un
           bouton destructif désactivé paraît actif. */
        .stApp button[kind="primary"]:disabled,
        .stApp [data-testid="stBaseButton-primary"]:disabled {{
            background: var(--sp-surface-3);
            box-shadow: none;
            cursor: not-allowed;
            opacity: 1;
        }}
        .stApp button[kind="primary"]:disabled p,
        .stApp [data-testid="stBaseButton-primary"]:disabled p {{
            color: var(--sp-muted);
        }}
        .stApp [data-testid="stDownloadButton"] button {{
            background: var(--sp-surface);
            border: 1px solid var(--sp-line-strong);
            border-radius: 11px;
            color: var(--sp-accent);
            min-height: 2.65rem;
        }}
        .stApp [data-testid="stDownloadButton"] button:hover {{
            background: var(--sp-accent-wash);
            border-color: var(--sp-accent);
        }}

        .section-note {{ color: var(--sp-muted); margin-bottom: 0.8rem; margin-top: -0.7rem; }}
        .empty-state {{
            background: var(--sp-surface);
            border: 1px dashed var(--sp-line-strong);
            border-radius: 18px;
            color: var(--sp-muted);
            padding: 2rem;
            text-align: center;
        }}
        .legend-row {{
            align-items: center;
            color: var(--sp-muted);
            display: flex;
            flex-wrap: wrap;
            font-size: 0.74rem;
            gap: 0.9rem;
            margin: -0.35rem 0 0.55rem;
        }}
        .legend-row span {{ align-items: center; display: inline-flex; gap: 0.4rem; }}
        .legend-row i {{ border-radius: 999px; display: inline-block; height: 3px; width: 18px; }}
        .legend-row i.dashed {{ border-top: 3px dashed currentColor; height: 0; }}

        @media (max-width: 900px) {{
            .block-container {{ padding-left: 1.1rem; padding-right: 1.1rem; }}
            div[data-testid="stColumn"] {{ min-width: calc(50% - 0.7rem); }}
        }}
        @media (max-width: 640px) {{
            .block-container {{ padding: 0.9rem 0.75rem 3rem; }}
            .page-hero {{ border-radius: 18px; padding: 1.25rem; }}
            .page-hero__title {{ font-size: 1.6rem; }}
            .page-hero__description {{ font-size: 0.87rem; }}
            .section-heading {{ align-items: flex-start; flex-direction: column; gap: 0.15rem; }}
            .section-heading__hint {{ text-align: left; }}
            div[data-testid="stColumn"] {{ flex: 1 1 100%; min-width: 100%; width: 100%; }}
            div[data-testid="stMetric"], .stat-card {{ min-height: auto; }}
            .stApp [data-testid="stPlotlyChart"] {{ border-radius: 14px; padding: 0; }}
            div[data-testid="stForm"] {{ border-radius: 16px; padding: 0.9rem 0.85rem 0.2rem; }}
            .stApp [data-testid="stTabs"] [data-baseweb="tab-list"] {{ overflow-x: auto; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_hero(
    eyebrow: str,
    title: str,
    description: str,
    badge: str | None = None,
) -> None:
    badge_html = f'<div class="page-hero__badge">{badge}</div>' if badge else ""
    st.markdown(
        f"""
        <div class="page-hero">
            <div class="page-hero__eyebrow">{eyebrow}</div>
            <div class="page-hero__title">{title}</div>
            <div class="page-hero__description">{description}</div>
            {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_heading(title: str, hint: str = "") -> None:
    hint_html = f'<span class="section-heading__hint">{hint}</span>' if hint else ""
    st.markdown(
        f"""
        <div class="section-heading">
            <span class="section-heading__title">{title}</span>
            {hint_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stat_card(
    label: str,
    value: str,
    detail: str,
    icon: str,
    tone: str = "success",
    delta_html: str = "",
) -> None:
    safe_tone = tone if tone in {"success", "warning", "danger", "info"} else "info"
    st.markdown(
        f"""
        <div class="stat-card stat-card--{safe_tone}">
            <div class="stat-card__top">
                <span class="stat-card__label">{label}</span>
                <span class="stat-card__icon">{icon}</span>
            </div>
            <div class="stat-card__value">{value}</div>
            <div class="stat-card__detail">{detail}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_alert_card(title: str, message: str, icon: str, tone: str = "info") -> None:
    safe_tone = tone if tone in {"success", "warning", "danger", "info"} else "info"
    st.markdown(
        f"""
        <div class="alert-card alert-card--{safe_tone}">
            <span class="alert-card__icon">{icon}</span>
            <div>
                <div class="alert-card__title">{title}</div>
                <div class="alert-card__text">{message}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stat_delta(percentage: float | None, label: str, higher_is_better: bool = True) -> str:
    """Pastille d'écart : flèche + signe, la couleur ne porte jamais seule le sens."""
    if percentage is None:
        return ""
    flat = abs(percentage) < 0.05
    rising = percentage > 0
    if flat:
        tone, arrow, text = "flat", "→", "stable"
    else:
        tone = "up" if rising == higher_is_better else "down"
        arrow = "↗" if rising else "↘"
        text = f"{'+' if rising else '−'}{abs(percentage):,.1f} %".replace(",", " ").replace(".", ",")
    return (
        f'<div class="stat-card__delta stat-card__delta--{tone}">'
        f"{arrow} {text} <small>{label}</small></div>"
    )


def apply_chart_style(
    figure: go.Figure,
    height: int = 360,
    legend: bool = True,
    palette: Mapping[str, Any] | None = None,
) -> go.Figure:
    """Applique la base visuelle commune à tous les graphiques du thème actif."""
    palette = palette or theme_palette()
    figure.update_layout(
        height=height,
        margin={"l": 14, "r": 14, "t": 20, "b": 14},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={
            "color": palette["tick"],
            "family": "system-ui, -apple-system, Segoe UI, sans-serif",
            "size": 12,
        },
        hoverlabel={
            "bgcolor": palette["tooltip_bg"],
            "font_color": palette["tooltip_text"],
            "bordercolor": palette["tooltip_bg"],
        },
        separators=", ",
        showlegend=legend,
        legend={
            "orientation": "h",
            "y": 1.14,
            "x": 0,
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"color": palette["muted"], "size": 11},
        },
        colorway=list(palette["categorical"]),
    )
    axis = {
        "gridcolor": palette["grid"],
        "zerolinecolor": palette["axis"],
        "linecolor": palette["axis"],
        "tickfont": {"color": palette["tick"], "size": 11},
        "title_font": {"color": palette["muted"], "size": 11},
    }
    figure.update_xaxes(showgrid=False, **axis)
    figure.update_yaxes(showgrid=True, griddash="dot", **axis)
    return figure


def row_value(row: pd.Series | None, field: str, default: Any = 0.0) -> Any:
    """Lit une valeur de formulaire depuis une ancienne journée sans propager NaN."""
    if row is None or field not in row or pd.isna(row[field]):
        return default
    return row[field]


def amount_with_currency(
    label: str,
    key: str,
    key_suffix: str,
    default_amount: float = 0.0,
    default_currency: str = "USD",
) -> tuple[float, str]:
    amount_col, currency_col = st.columns([3, 1])
    amount = amount_col.number_input(
        label,
        min_value=0.0,
        value=float(default_amount),
        step=0.01,
        key=f"{key}_{key_suffix}_amount",
    )
    currency = currency_col.selectbox(
        "Devise",
        ["USD", "LBP"],
        index=0 if default_currency == "USD" else 1,
        key=f"{key}_{key_suffix}_currency",
    )
    return amount, currency


def expense_inputs(
    label: str,
    key: str,
    key_suffix: str,
    default_usd: float = 0.0,
    default_lbp: float = 0.0,
 ) -> tuple[float, float]:
    st.markdown(f"**{label}**")
    usd_col, lbp_col = st.columns(2)
    usd = usd_col.number_input(
        "Montant USD",
        min_value=0.0,
        value=float(default_usd),
        step=0.01,
        key=f"expense_{key}_{key_suffix}_usd",
    )
    lbp = lbp_col.number_input(
        "Montant LL",
        min_value=0.0,
        value=float(default_lbp),
        step=1.0,
        format="%.0f",
        key=f"expense_{key}_{key_suffix}_lbp",
    )
    return usd, lbp


def currency_pair_inputs(
    label: str,
    key: str,
    key_suffix: str,
    default_usd: float = 0.0,
    default_lbp: float = 0.0,
) -> tuple[float, float]:
    """Saisie compacte d'une même catégorie en USD et en LL."""
    st.markdown(f"**{label}**")
    usd_col, lbp_col = st.columns(2)
    usd = usd_col.number_input(
        "USD",
        min_value=0.0,
        value=float(default_usd),
        step=0.01,
        key=f"{key}_{key_suffix}_usd",
    )
    lbp = lbp_col.number_input(
        "LL",
        min_value=0.0,
        value=float(default_lbp),
        step=1.0,
        format="%.0f",
        key=f"{key}_{key_suffix}_lbp",
    )
    return usd, lbp


def render_saved_summary(summary: Mapping[str, float], record_date: str, action: str) -> None:
    verb = "mise à jour" if action == "updated" else "enregistrée"
    st.success(f"Journée du {format_date_fr(record_date)} {verb} avec succès.")

    st.markdown("### Résumé de fin de journée")
    sales_col, expense_col, net_col = st.columns(3)
    with sales_col:
        st.metric("Ventes USD", format_usd(summary["total_sales_usd"]))
        st.metric("Ventes LL", format_lbp(summary["total_sales_lbp"]))
    with expense_col:
        st.metric("Dépenses USD", format_usd(summary["total_expenses_usd"]))
        st.metric("Dépenses LL", format_lbp(summary["total_expenses_lbp"]))
    with net_col:
        st.metric("Solde USD", format_usd(summary["net_usd"]))
        st.metric("Solde LL", format_lbp(summary["net_lbp"]))

    st.markdown("##### Rapprochement automatique")
    stock_col, cash_usd_col, cash_lbp_col = st.columns(3)
    stock_col.metric(
        "Écart stock",
        f"{format_fr(summary['stock_variance_l'], 1)} L",
        delta=f"{format_fr(summary['stock_variance_l'], 1)} L",
    )
    cash_usd_col.metric("Écart caisse USD", format_usd(summary["cash_variance_usd"]))
    cash_lbp_col.metric("Écart caisse LL", format_lbp(summary["cash_variance_lbp"]))


def navigate_to(page: str) -> None:
    """Change de page depuis une action rapide sans dupliquer la navigation."""
    st.session_state["main_navigation"] = page


def render_home_page(history: pd.DataFrame) -> None:
    """Affiche le cockpit opérationnel qui ouvre l'application."""
    palette = theme_palette()
    dated_history = history.dropna(subset=["record_date"]).sort_values("record_date")
    latest_label = (
        f"Dernière clôture · {format_date_fr(dated_history.iloc[-1]['record_date'])}"
        if not dated_history.empty
        else "Prêt pour votre première clôture"
    )
    render_page_hero(
        "Pilotage quotidien",
        "Bonjour, voici l'essentiel de votre station.",
        "Ventes, trésorerie, stock et crédits clients réunis dans une vue claire pour agir rapidement.",
        latest_label,
    )

    render_section_heading(
        "Actions rapides",
        "Les tâches les plus fréquentes restent accessibles en un clic",
    )
    with st.container(horizontal=True, wrap=True):
        st.button(
            "Nouvelle clôture",
            icon=":material/add_circle:",
            type="primary",
            key="home_new_entry",
            on_click=navigate_to,
            args=("Saisie",),
        )
        st.button(
            "Suivre les crédits",
            icon=":material/account_balance_wallet:",
            key="home_open_credits",
            on_click=navigate_to,
            args=("Crédits",),
        )
        st.button(
            "Analyser les performances",
            icon=":material/analytics:",
            key="home_open_dashboard",
            on_click=navigate_to,
            args=("Tableau de bord",),
        )

    if dated_history.empty:
        st.markdown(
            """
            <div class="empty-state">
                <div style="font-size:2rem">⛽</div>
                <strong>Aucune journée enregistrée</strong><br>
                Commencez dans la section <em>Saisie</em> du menu pour alimenter votre cockpit.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    latest = dated_history.iloc[-1]
    previous = dated_history.iloc[-2] if len(dated_history) > 1 else None
    current_rate = _number(latest, "exchange_rate")
    credits = load_credit_entries()
    payments = load_credit_payments()
    credit_activity = build_credit_activity(dated_history, credits, payments)
    balances = build_credit_balances(credit_activity, current_rate)
    outstanding_usd = (
        float(balances["Solde USD"].clip(lower=0).sum()) if not balances.empty else 0.0
    )
    outstanding_lbp = (
        float(balances["Solde LL"].clip(lower=0).sum()) if not balances.empty else 0.0
    )
    outstanding_equivalent = outstanding_usd + (
        outstanding_lbp / current_rate if current_rate > 0 else 0
    )

    def comparison_detail(field: str, neutral_text: str) -> str:
        if previous is None:
            return neutral_text
        previous_value = _number(previous, field)
        current_value = _number(latest, field)
        if abs(previous_value) < 0.005:
            return "Première base de comparaison disponible"
        change = (current_value - previous_value) / abs(previous_value) * 100
        direction = "hausse" if change >= 0 else "baisse"
        return f"{format_fr(abs(change), 1)} % de {direction} vs clôture précédente"

    capacity = _number(latest, "tank_capacity_l")
    stock = _number(latest, "stock_available_l")
    stock_ratio = stock / capacity if capacity > 0 else 0
    stock_tone = "danger" if capacity > 0 and stock_ratio <= 0.2 else "warning" if stock_ratio <= 0.35 else "success"
    net_value = _number(latest, "net_usd_equiv")

    render_section_heading("Indicateurs de la dernière clôture", "Montants LL convertis au taux du jour")
    kpi_1, kpi_2, kpi_3, kpi_4 = st.columns(4)
    with kpi_1:
        render_stat_card(
            "Ventes · équiv. USD",
            format_usd(_number(latest, "total_sales_usd_equiv")),
            comparison_detail("total_sales_usd_equiv", "Clôture de référence"),
            "↗",
            "success",
        )
    with kpi_2:
        render_stat_card(
            "Résultat opérationnel",
            format_usd(net_value),
            comparison_detail("net_usd_equiv", "Ventes moins dépenses du jour"),
            "◎",
            "success" if net_value >= 0 else "danger",
        )
    with kpi_3:
        render_stat_card(
            "Stock disponible",
            f"{format_fr(stock, 0)} L",
            f"{format_fr(stock_ratio * 100, 1)} % de la capacité" if capacity > 0 else "Capacité non renseignée",
            "⛽",
            stock_tone,
        )
    with kpi_4:
        render_stat_card(
            "Crédits à encaisser",
            format_usd(outstanding_equivalent),
            f"{format_usd(outstanding_usd)} · {format_lbp(outstanding_lbp)}",
            "◷",
            "warning" if outstanding_equivalent > 0 else "success",
        )

    render_section_heading("Alertes opérationnelles", "Priorités calculées depuis la dernière journée")
    alerts: list[tuple[str, str, str, str]] = []
    latest_day = latest["record_date"].date()
    days_since_close = (date.today() - latest_day).days
    if days_since_close > 2:
        alerts.append(
            (
                "Clôture à actualiser",
                f"La dernière journée enregistrée remonte au {format_date_fr(latest_day)} ({days_since_close} jours).",
                "◷",
                "warning",
            )
        )
    if capacity <= 0:
        alerts.append(
            (
                "Capacité du réservoir manquante",
                "Renseignez-la dans la prochaine saisie pour activer le suivi du niveau de stock.",
                "⛽",
                "info",
            )
        )
    elif stock_ratio <= 0.2:
        alerts.append(
            (
                "Stock critique",
                f"Il ne reste que {format_fr(stock_ratio * 100, 1)} % de la capacité, soit {format_fr(stock, 0)} litres.",
                "!",
                "danger",
            )
        )
    elif stock_ratio <= 0.35:
        alerts.append(
            (
                "Stock à surveiller",
                f"Le réservoir est rempli à {format_fr(stock_ratio * 100, 1)} %. Anticipez la prochaine livraison.",
                "⛽",
                "warning",
            )
        )

    stock_variance = _number(latest, "stock_variance_l")
    stock_tolerance = max(10.0, capacity * 0.002)
    if abs(stock_variance) > stock_tolerance:
        alerts.append(
            (
                "Écart de stock inhabituel",
                f"Le stock réel diffère du stock théorique de {format_fr(stock_variance, 1)} L.",
                "Δ",
                "danger",
            )
        )

    cash_gap_equivalent = _number(latest, "cash_variance_usd") + (
        _number(latest, "cash_variance_lbp") / current_rate if current_rate > 0 else 0
    )
    if abs(cash_gap_equivalent) > 10:
        alerts.append(
            (
                "Écart de caisse à contrôler",
                f"L'écart combiné représente {format_usd(cash_gap_equivalent)}. Vérifiez les encaissements et dépenses.",
                "≋",
                "danger",
            )
        )
    if outstanding_equivalent > 0:
        active_clients = int(
            (
                (balances["Solde USD"] > 0.005)
                | (balances["Solde LL"] > 0.5)
            ).sum()
        )
        alerts.append(
            (
                "Crédits clients en attente",
                f"{active_clients} client(s) représentent {format_usd(outstanding_equivalent)} à encaisser.",
                "◷",
                "warning",
            )
        )
    if not alerts:
        alerts.append(
            (
                "Situation sous contrôle",
                "Aucune anomalie prioritaire détectée sur la dernière clôture.",
                "✓",
                "success",
            )
        )

    alert_left, alert_right = st.columns(2)
    for index, (title, message, icon, tone) in enumerate(alerts):
        with alert_left if index % 2 == 0 else alert_right:
            render_alert_card(title, message, icon, tone)

    visual_left, visual_right = st.columns([0.88, 1.55])
    with visual_left:
        render_section_heading("Niveau du réservoir", "Dernière mesure")
        gauge_max = max(capacity, stock, 1.0)
        gauge = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=stock,
                number={"suffix": " L", "valueformat": ",.0f", "font": {"size": 30}},
                gauge={
                    "axis": {"range": [0, gauge_max], "tickformat": ",.0f"},
                    "bar": {
                        "color": palette["negative"]
                        if stock_ratio <= 0.2
                        else palette["warning"]
                        if stock_ratio <= 0.35
                        else palette["sales"]
                    },
                    "bgcolor": palette["surface_3"],
                    "borderwidth": 0,
                    "steps": [
                        {"range": [0, gauge_max * 0.2], "color": palette["danger_soft"]},
                        {"range": [gauge_max * 0.2, gauge_max * 0.4], "color": palette["warning_soft"]},
                        {"range": [gauge_max * 0.4, gauge_max], "color": palette["accent_soft"]},
                    ],
                    "threshold": {
                        "line": {"color": palette["axis"], "width": 3},
                        "thickness": 0.7,
                        "value": gauge_max * 0.2,
                    },
                },
            )
        )
        apply_chart_style(gauge, height=330)
        gauge.update_layout(margin={"l": 28, "r": 28, "t": 38, "b": 20})
        st.plotly_chart(gauge, width="stretch", config=PLOTLY_CONFIG)

    with visual_right:
        render_section_heading("Activité récente", "14 dernières clôtures")
        recent = dated_history.tail(14).copy()
        recent["Libellé"] = recent["record_date"].dt.strftime("%d/%m")
        trend = go.Figure()
        trend.add_bar(
            x=recent["Libellé"],
            y=recent["total_sales_usd_equiv"],
            name="Ventes",
            marker_color=palette["sales"],
            hovertemplate="%{x}<br>Ventes : $%{y:,.2f}<extra></extra>",
        )
        trend.add_bar(
            x=recent["Libellé"],
            y=recent["total_expenses_usd_equiv"],
            name="Dépenses",
            marker_color=palette["expenses"],
            hovertemplate="%{x}<br>Dépenses : $%{y:,.2f}<extra></extra>",
        )
        trend.add_scatter(
            x=recent["Libellé"],
            y=recent["net_usd_equiv"],
            name="Résultat",
            mode="lines+markers",
            line={"color": palette["net"], "width": 2},
            marker={"size": 7},
            hovertemplate="%{x}<br>Résultat : $%{y:,.2f}<extra></extra>",
        )
        apply_chart_style(trend, height=330)
        trend.update_layout(
            barmode="group",
            hovermode="x unified",
            legend={"orientation": "h", "y": 1.14, "x": 0},
            xaxis_title=None,
            yaxis_title="Équivalent USD",
        )
        st.plotly_chart(trend, width="stretch", config=PLOTLY_CONFIG)

    render_section_heading("Contrôle de clôture", "Valeurs réelles comparées aux calculs")
    close_1, close_2, close_3, close_4 = st.columns(4)
    close_1.metric("Écart stock", f"{format_fr(stock_variance, 1)} L")
    close_2.metric("Écart caisse USD", format_usd(_number(latest, "cash_variance_usd")))
    close_3.metric("Écart caisse LL", format_lbp(_number(latest, "cash_variance_lbp")))
    close_4.metric("Taux LL / USD", format_fr(current_rate, 0))


def render_credits_page(history: pd.DataFrame) -> None:
    """Affiche les encours et mouvements de crédit regroupés par client."""
    palette = theme_palette()
    render_page_hero(
        "Crédit clients",
        "Suivez ce qui a été vendu, encaissé et reste à recevoir.",
        "Les soldes USD et LL restent séparés. L'équivalent USD sert uniquement à la lecture consolidée.",
        "Vue consolidée par client",
    )
    credits = load_credit_entries()
    payments = load_credit_payments()
    activity = build_credit_activity(history, credits, payments)

    if activity.empty:
        st.markdown(
            """
            <div class="empty-state">
                <div style="font-size:2rem">◷</div>
                <strong>Aucun mouvement de crédit</strong><br>
                Les ventes à crédit et leurs encaissements apparaîtront ici après une saisie journalière.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    dated_history = history.dropna(subset=["record_date"]).sort_values("record_date")
    current_rate = _number(dated_history.iloc[-1], "exchange_rate") if not dated_history.empty else 0
    balances = build_credit_balances(activity, current_rate)

    render_section_heading("Filtres", "Les indicateurs et le tableau clients se mettent à jour")
    filter_1, filter_2, filter_3 = st.columns([1.55, 1, 1])
    search = filter_1.text_input(
        "Rechercher un client",
        placeholder="Nom du client…",
        key="credits_client_search",
    )
    status_filter = filter_2.selectbox(
        "Statut",
        ["Tous les statuts", "À encaisser", "Soldé", "Avance client"],
        key="credits_status_filter",
    )
    currency_filter = filter_3.selectbox(
        "Devise",
        ["Toutes les devises", "USD", "LL"],
        key="credits_currency_filter",
    )

    filtered_balances = balances.copy()
    if search.strip():
        needle = search.strip().casefold()
        filtered_balances = filtered_balances[
            filtered_balances["Client"].str.casefold().str.contains(needle, regex=False)
        ]
    if status_filter != "Tous les statuts":
        filtered_balances = filtered_balances[filtered_balances["Statut"] == status_filter]
    if currency_filter == "USD":
        filtered_balances = filtered_balances[
            (filtered_balances["Vendu USD"] != 0) | (filtered_balances["Encaissé USD"] != 0)
        ]
    elif currency_filter == "LL":
        filtered_balances = filtered_balances[
            (filtered_balances["Vendu LL"] != 0) | (filtered_balances["Encaissé LL"] != 0)
        ]

    positive_usd = (
        float(filtered_balances["Solde USD"].clip(lower=0).sum())
        if not filtered_balances.empty
        else 0.0
    )
    positive_lbp = (
        float(filtered_balances["Solde LL"].clip(lower=0).sum())
        if not filtered_balances.empty
        else 0.0
    )
    outstanding_equivalent = positive_usd + (
        positive_lbp / current_rate if current_rate > 0 else 0
    )
    sold_equivalent = (
        float(filtered_balances["Vendu équiv. USD"].sum())
        if not filtered_balances.empty
        else 0.0
    )
    paid_equivalent = (
        float(filtered_balances["Encaissé équiv. USD"].sum())
        if not filtered_balances.empty
        else 0.0
    )
    active_clients = (
        int((filtered_balances["Statut"] == "À encaisser").sum())
        if not filtered_balances.empty
        else 0
    )

    kpi_1, kpi_2, kpi_3, kpi_4 = st.columns(4)
    with kpi_1:
        render_stat_card(
            "Clients à relancer",
            f"{active_clients}",
            f"{len(filtered_balances)} client(s) dans la vue",
            "☷",
            "warning" if active_clients else "success",
        )
    with kpi_2:
        render_stat_card(
            "Crédit vendu",
            format_usd(sold_equivalent),
            "Équivalent au taux de chaque opération",
            "↗",
            "info",
        )
    with kpi_3:
        render_stat_card(
            "Déjà encaissé",
            format_usd(paid_equivalent),
            "Équivalent au taux de chaque opération",
            "✓",
            "success",
        )
    with kpi_4:
        render_stat_card(
            "Encours actuel",
            format_usd(outstanding_equivalent),
            f"{format_usd(positive_usd)} · {format_lbp(positive_lbp)}",
            "◷",
            "danger" if outstanding_equivalent > 500 else "warning" if outstanding_equivalent > 0 else "success",
        )

    chart_col, table_col = st.columns([0.92, 1.55])
    with chart_col:
        render_section_heading("Encours par client", "12 soldes les plus importants")
        chart_data = filtered_balances[filtered_balances["Encours équiv. USD"] > 0].head(12)
        if chart_data.empty:
            st.info("Aucun solde positif pour les filtres sélectionnés.")
        else:
            chart_data = chart_data.sort_values("Encours équiv. USD")
            credit_chart = go.Figure(
                go.Bar(
                    x=chart_data["Encours équiv. USD"],
                    y=chart_data["Client"],
                    orientation="h",
                    marker={
                        "color": chart_data["Encours équiv. USD"],
                        "colorscale": [[0, palette["warning"]], [1, palette["negative"]]],
                        "showscale": False,
                    },
                    text=[format_usd(value) for value in chart_data["Encours équiv. USD"]],
                    textposition="auto",
                    hovertemplate="%{y}<br>Encours : $%{x:,.2f}<extra></extra>",
                )
            )
            apply_chart_style(credit_chart, height=390)
            credit_chart.update_layout(xaxis_title="Équivalent USD", yaxis_title=None)
            st.plotly_chart(credit_chart, width="stretch", config=PLOTLY_CONFIG)

    with table_col:
        render_section_heading("Soldes clients", "Montants natifs et vue consolidée")
        if filtered_balances.empty:
            st.info("Aucun client ne correspond aux filtres sélectionnés.")
        else:
            balance_view = filtered_balances[
                [
                    "Client",
                    "Solde USD",
                    "Solde LL",
                    "Encours équiv. USD",
                    "Statut",
                    "Dernière activité",
                ]
            ]
            st.dataframe(
                balance_view,
                hide_index=True,
                width="stretch",
                height=min(430, 42 + len(balance_view) * 36),
                column_config={
                    "Client": st.column_config.TextColumn("Client", width="medium"),
                    "Solde USD": st.column_config.NumberColumn(format="$%.2f"),
                    "Solde LL": st.column_config.NumberColumn(format="%.0f LL"),
                    "Encours équiv. USD": st.column_config.NumberColumn(format="$%.2f"),
                    "Statut": st.column_config.TextColumn(width="small"),
                    "Dernière activité": st.column_config.DateColumn(format="DD/MM/YYYY"),
                },
            )

    render_section_heading("Historique des mouvements", "Ventes à crédit et remboursements")
    operation_filter = st.segmented_control(
        "Type de mouvement",
        ["Tous", "Vente à crédit", "Encaissement"],
        default="Tous",
        required=True,
        width="stretch",
        key="credits_operation_filter",
    )
    filtered_activity = activity.copy()
    if search.strip():
        needle = search.strip().casefold()
        filtered_activity = filtered_activity[
            filtered_activity["Client"].str.casefold().str.contains(needle, regex=False)
        ]
    if currency_filter != "Toutes les devises":
        target_currency = "LBP" if currency_filter == "LL" else "USD"
        filtered_activity = filtered_activity[filtered_activity["Devise"] == target_currency]
    if operation_filter != "Tous":
        filtered_activity = filtered_activity[
            filtered_activity["Opération"] == operation_filter
        ]

    if filtered_activity.empty:
        st.info("Aucun mouvement ne correspond à ces filtres.")
    else:
        activity_view = filtered_activity[
            [
                "Date",
                "Opération",
                "Client",
                "Montant",
                "Devise",
                "Équivalent USD",
                "Note",
            ]
        ]
        st.dataframe(
            activity_view,
            hide_index=True,
            width="stretch",
            height=min(520, 42 + len(activity_view) * 36),
            column_config={
                "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Montant": st.column_config.NumberColumn(format="%.2f"),
                "Équivalent USD": st.column_config.NumberColumn(format="$%.2f"),
                "Note": st.column_config.TextColumn(width="large"),
            },
        )
    if current_rate > 0:
        st.caption(
            f"Les encours LL sont convertis pour la synthèse au dernier taux connu : 1 USD = {format_fr(current_rate, 0)} LL."
        )


def render_entry_tab(history: pd.DataFrame) -> bool:
    """Affiche la saisie et renvoie True si l'historique a changé."""
    render_page_hero(
        "Clôture de journée",
        "Saisie journalière",
        "Enregistrez le stock, les ventes, les dépenses, les crédits et les caisses dans un même flux sécurisé.",
        "USD et LL conservés séparément",
    )

    editable_history = history.dropna(subset=["record_date"]).sort_values(
        "record_date", ascending=False
    )
    continuity_row = editable_history.iloc[0] if not editable_history.empty else None
    modes = ["Nouvelle saisie"]
    if not editable_history.empty:
        modes.append("Modifier une journée")
    mode_col, selector_col = st.columns([1, 2])
    entry_mode = mode_col.segmented_control(
        "Action",
        modes,
        default=modes[0],
        required=True,
        width="stretch",
        key="entry_mode",
    )

    selected_row: pd.Series | None = None
    if entry_mode == "Modifier une journée":
        date_options = editable_history["record_date"].dt.strftime("%d/%m/%Y").tolist()
        selected_edit_label = selector_col.selectbox(
            "Journée à modifier",
            date_options,
            key="selected_edit_date",
        )
        selected_edit_date = datetime.strptime(selected_edit_label, "%d/%m/%Y").date()
        selected_row = editable_history[
            editable_history["record_date"].dt.date == selected_edit_date
        ].iloc[0]
        st.info(
            f"Les valeurs du {selected_edit_date.strftime('%d/%m/%Y')} ont été chargées. "
            "L'enregistrement remplacera uniquement cette journée."
        )
        form_token = f"edit_{selected_edit_date.isoformat()}"
        default_record_date = selected_edit_date
    else:
        selector_col.caption(
            "Les valeurs de continuité sont reprises automatiquement depuis la dernière clôture."
        )
        form_token = "new"
        default_record_date = date.today()

    if entry_mode == "Nouvelle saisie" and continuity_row is not None:
        latest_day_label = format_date_fr(continuity_row["record_date"])
        render_alert_card(
            "Continuité automatique",
            (
                f"Clôture du {latest_day_label} reprise : "
                f"stock d'ouverture {format_fr(_number(continuity_row, 'stock_available_l'), 0)} L, "
                f"caisse {format_usd(_number(continuity_row, 'cash_actual_end_usd'))} et "
                f"{format_lbp(_number(continuity_row, 'cash_actual_end_lbp'))}."
            ),
            "↻",
            "info",
        )

    def previous(field: str, default: Any = 0.0) -> Any:
        if selected_row is not None:
            return row_value(selected_row, field, default)
        if continuity_row is None:
            return default
        carry_fields = {
            "exchange_rate": "exchange_rate",
            "tank_capacity_l": "tank_capacity_l",
            "opening_stock_l": "stock_available_l",
            "fuel_cost_usd_per_l": "fuel_cost_usd_per_l",
            "cash_opening_usd": "cash_actual_end_usd",
            "cash_opening_lbp": "cash_actual_end_lbp",
        }
        source_field = carry_fields.get(field)
        if source_field is None:
            return default
        return row_value(continuity_row, source_field, default)

    if entry_mode == "Modifier une journée":
        credit_seed = load_credit_entries(default_record_date.isoformat())[
            ["client_name", "amount", "currency", "note"]
        ].copy()
        payment_seed = load_credit_payments(default_record_date.isoformat())[
            ["client_name", "amount", "currency", "note"]
        ].copy()
    else:
        credit_seed = pd.DataFrame(columns=["client_name", "amount", "currency", "note"])
        payment_seed = pd.DataFrame(columns=["client_name", "amount", "currency", "note"])
    if credit_seed.empty:
        credit_seed = pd.DataFrame(
            [{"client_name": "", "amount": 0.0, "currency": "USD", "note": ""}]
        )
    if payment_seed.empty:
        payment_seed = pd.DataFrame(
            [{"client_name": "", "amount": 0.0, "currency": "USD", "note": ""}]
        )

    known_clients = load_known_credit_clients()
    client_options = ["", *known_clients]
    credit_seed.insert(1, "new_client_name", "")
    payment_seed.insert(1, "new_client_name", "")

    with st.form(f"daily_entry_form_{form_token}", clear_on_submit=False):
        # Le formulaire reste unique : les onglets ne font que répartir la
        # saisie, tous les champs sont soumis ensemble par le bouton du bas.
        (
            entry_step_0,
            entry_step_1,
            entry_step_2,
            entry_step_3,
            entry_step_4,
        ) = st.tabs(["1 · Général", "2 · Stock", "3 · Ventes & crédits", "4 · Dépenses", "5 · Caisse"])

        with entry_step_0:
            general_1, general_2 = st.columns(2)
            record_day = general_1.date_input(
                "Date de la journée",
                value=default_record_date,
                max_value=date.today(),
                disabled=entry_mode == "Modifier une journée",
                key=f"record_day_{form_token}",
            )
            exchange_rate = general_2.number_input(
                "Taux de change (LL pour 1 USD)",
                min_value=1.0,
                value=float(previous("exchange_rate", 89_500.0)),
                step=1.0,
                format="%.0f",
                help="Exemple : 89 500 signifie que 1 USD = 89 500 LL.",
                key=f"exchange_rate_{form_token}",
            )

        with entry_step_1:
            tank_1, tank_2, tank_3 = st.columns(3)
            tank_capacity = tank_1.number_input(
                "Capacité totale (litres)",
                min_value=0.0,
                value=float(previous("tank_capacity_l")),
                step=0.01,
                key=f"tank_capacity_{form_token}",
            )
            opening_stock = tank_2.number_input(
                "Stock ouverture (litres)",
                min_value=0.0,
                value=float(previous("opening_stock_l")),
                step=0.01,
                key=f"opening_stock_{form_token}",
            )
            fuel_input = tank_3.number_input(
                "Entrées carburant (litres)",
                min_value=0.0,
                value=float(previous("fuel_input_l")),
                step=0.01,
                key=f"fuel_input_{form_token}",
            )
            stock_1, stock_2, stock_3 = st.columns(3)
            stock_available = stock_1.number_input(
                "Stock réel fin (litres)",
                min_value=0.0,
                value=float(previous("stock_available_l")),
                step=0.01,
                key=f"stock_available_{form_token}",
            )
            fuel_cost = stock_2.number_input(
                "Coût carburant (USD/litre)",
                min_value=0.0,
                value=float(previous("fuel_cost_usd_per_l")),
                step=0.0001,
                format="%.4f",
                key=f"fuel_cost_{form_token}",
            )
            stock_value = stock_3.number_input(
                "Valeur stock (USD)",
                min_value=0.0,
                value=float(previous("stock_value_usd")),
                step=0.01,
                key=f"stock_value_{form_token}",
                help="Vous pouvez utiliser stock réel × coût USD/litre.",
            )

        with entry_step_2:
            fuel_1, fuel_2, fuel_3 = st.columns(3)
            fuel_volume = fuel_1.number_input(
                "Essence vendue (litres)",
                min_value=0.0,
                value=float(previous("fuel_volume_sold_l")),
                step=0.01,
                key=f"fuel_volume_{form_token}",
            )
            fuel_sales_usd = fuel_2.number_input(
                "Ventes essence (USD)",
                min_value=0.0,
                value=float(previous("fuel_sales_usd")),
                step=0.01,
                key=f"fuel_sales_usd_{form_token}",
            )
            fuel_sales_lbp = fuel_3.number_input(
                "Ventes essence (LL)",
                min_value=0.0,
                value=float(previous("fuel_sales_lbp")),
                step=1.0,
                format="%.0f",
                key=f"fuel_sales_lbp_{form_token}",
            )
            sale_left, sale_right = st.columns(2)
            with sale_left:
                tires_sales = currency_pair_inputs(
                    "Ventes pneus",
                    "tires",
                    form_token,
                    previous("tires_sales_usd"),
                    previous("tires_sales_lbp"),
                )
                gas_sales = currency_pair_inputs(
                    "Ventes bouteilles de gaz",
                    "gas",
                    form_token,
                    previous("gas_sales_usd"),
                    previous("gas_sales_lbp"),
                )
            with sale_right:
                wash_sales = currency_pair_inputs(
                    "Lavage de voitures",
                    "wash",
                    form_token,
                    previous("wash_sales_usd"),
                    previous("wash_sales_lbp"),
                )
                other_sales = currency_pair_inputs(
                    "Autres ventes",
                    "other_sales",
                    form_token,
                    previous("other_sales_usd"),
                    previous("other_sales_lbp"),
                )

            st.markdown("##### Clients à crédit")
            st.caption(
                "Choisissez un client enregistré dans la liste, ou renseignez la colonne "
                "« Nouveau client ». Ajoutez autant de lignes que nécessaire avec le bouton +."
            )
            edited_credits = st.data_editor(
                credit_seed,
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                key=f"credit_editor_{form_token}",
                column_config={
                    "client_name": st.column_config.SelectboxColumn(
                        "Client enregistré",
                        options=client_options,
                        default="",
                        width="medium",
                        help="Clients déjà présents dans l’historique des crédits.",
                    ),
                    "new_client_name": st.column_config.TextColumn(
                        "Nouveau client",
                        width="medium",
                        help="Si ce champ est rempli, il remplace le client sélectionné.",
                    ),
                    "amount": st.column_config.NumberColumn(
                        "Montant", min_value=0.0, step=0.01, format="%.2f"
                    ),
                    "currency": st.column_config.SelectboxColumn(
                        "Devise", options=["USD", "LBP"], required=True
                    ),
                    "note": st.column_config.TextColumn(
                        "Note / référence", width="large"
                    ),
                },
            )

            st.markdown("##### Crédits encaissés")
            st.caption(
                "Sélectionnez le client enregistré qui rembourse, ou saisissez un nouveau nom "
                "si son ancien crédit ne figure pas encore dans l’application."
            )
            edited_payments = st.data_editor(
                payment_seed,
                num_rows="dynamic",
                hide_index=True,
                width="stretch",
                key=f"payment_editor_{form_token}",
                column_config={
                    "client_name": st.column_config.SelectboxColumn(
                        "Client enregistré",
                        options=client_options,
                        default="",
                        width="medium",
                    ),
                    "new_client_name": st.column_config.TextColumn(
                        "Nouveau client",
                        width="medium",
                        help="Si ce champ est rempli, il remplace le client sélectionné.",
                    ),
                    "amount": st.column_config.NumberColumn(
                        "Montant encaissé", min_value=0.0, step=0.01, format="%.2f"
                    ),
                    "currency": st.column_config.SelectboxColumn(
                        "Devise", options=["USD", "LBP"], required=True
                    ),
                    "note": st.column_config.TextColumn("Note / référence", width="large"),
                },
            )

        with entry_step_3:
            st.caption("Chaque catégorie accepte simultanément des montants USD et LL.")
            expense_values: dict[str, tuple[float, float]] = {}
            expense_left, expense_right = st.columns(2)
            categories = list(EXPENSE_CATEGORIES.items())
            with expense_left:
                for label, prefix in categories[:3]:
                    expense_values[prefix] = expense_inputs(
                        label,
                        prefix,
                        form_token,
                        previous(f"{prefix}_usd"),
                        previous(f"{prefix}_lbp"),
                    )
            with expense_right:
                for label, prefix in categories[3:]:
                    expense_values[prefix] = expense_inputs(
                        label,
                        prefix,
                        form_token,
                        previous(f"{prefix}_usd"),
                        previous(f"{prefix}_lbp"),
                    )

        with entry_step_4:
            st.caption(
                "La caisse théorique sera calculée ainsi : ouverture + ventes encaissées "
                "+ crédits encaissés − dépenses."
            )
            cash_opening = currency_pair_inputs(
                "Caisses à l'ouverture",
                "cash_opening",
                form_token,
                previous("cash_opening_usd"),
                previous("cash_opening_lbp"),
            )
            cash_actual_end = currency_pair_inputs(
                "Caisses réelles comptées en fin de journée",
                "cash_actual_end",
                form_token,
                previous("cash_actual_end_usd"),
                previous("cash_actual_end_lbp"),
            )

            st.divider()
            notes = st.text_area(
                "Notes / observations",
                value=str(previous("notes", "")),
                placeholder="Événement particulier, écart de caisse, livraison attendue…",
                key=f"notes_{form_token}",
            )

        st.divider()
        submitted = st.form_submit_button(
            "Mettre à jour la journée"
            if entry_mode == "Modifier une journée"
            else "Enregistrer la journée",
            type="primary",
            icon=":material/save:",
            width="stretch",
        )

    changed = False
    if submitted:
        errors: list[str] = []

        def normalize_client_rows(
            edited_frame: pd.DataFrame, operation_label: str
        ) -> list[dict[str, Any]]:
            normalized: list[dict[str, Any]] = []
            for _, client_row in edited_frame.iterrows():
                client_value = client_row.get("client_name", "")
                selected_client = (
                    "" if pd.isna(client_value) else str(client_value).strip()
                )
                new_client_value = client_row.get("new_client_name", "")
                new_client = (
                    "" if pd.isna(new_client_value) else str(new_client_value).strip()
                )
                client_name = new_client or selected_client
                amount_value = pd.to_numeric(client_row.get("amount", 0), errors="coerce")
                amount = 0.0 if pd.isna(amount_value) else float(amount_value)
                currency_value = client_row.get("currency", "USD")
                currency = "USD" if pd.isna(currency_value) else str(currency_value).upper()
                note_value = client_row.get("note", "")
                client_note = "" if pd.isna(note_value) else str(note_value).strip()
                if not client_name and amount <= 0 and not client_note:
                    continue
                if not client_name:
                    errors.append(f"Chaque {operation_label} doit avoir un nom de client.")
                    continue
                if amount <= 0:
                    errors.append(
                        f"Le montant pour {client_name} ({operation_label}) doit être supérieur à zéro."
                    )
                    continue
                if currency not in {"USD", "LBP"}:
                    errors.append(f"Devise incorrecte pour {client_name}.")
                    continue
                normalized.append(
                    {
                        "client_name": client_name,
                        "amount": amount,
                        "currency": currency,
                        "note": client_note,
                    }
                )
            return normalized

        credit_entries = normalize_client_rows(edited_credits, "vente à crédit")
        payment_entries = normalize_client_rows(edited_payments, "crédit encaissé")

        if tank_capacity > 0 and stock_available > tank_capacity:
            errors.append("Le stock disponible ne peut pas dépasser la capacité du réservoir.")
        theoretical_stock = opening_stock + fuel_input - fuel_volume
        if theoretical_stock < 0:
            errors.append(
                "Le stock théorique devient négatif : vérifiez le stock d'ouverture, "
                "les entrées et les litres vendus."
            )
        if fuel_volume > 0 and (fuel_sales_usd + fuel_sales_lbp) == 0:
            errors.append("Un volume vendu a été saisi, mais aucune vente d'essence.")

        if errors:
            for error in errors:
                st.error(error)
        else:
            credit_totals = {
                currency: sum(
                    entry["amount"]
                    for entry in credit_entries
                    if entry["currency"] == currency
                )
                for currency in ("USD", "LBP")
            }
            payment_totals = {
                currency: sum(
                    entry["amount"]
                    for entry in payment_entries
                    if entry["currency"] == currency
                )
                for currency in ("USD", "LBP")
            }
            credit_currencies = {entry["currency"] for entry in credit_entries}
            record: dict[str, Any] = {
                "record_date": record_day.isoformat(),
                "exchange_rate": exchange_rate,
                "tank_capacity_l": tank_capacity,
                "opening_stock_l": opening_stock,
                "fuel_input_l": fuel_input,
                "stock_available_l": stock_available,
                "fuel_cost_usd_per_l": fuel_cost,
                "stock_value_usd": stock_value
                if stock_value > 0
                else stock_available * fuel_cost,
                "fuel_volume_sold_l": fuel_volume,
                "fuel_sales_usd": fuel_sales_usd,
                "fuel_sales_lbp": fuel_sales_lbp,
                "tires_sales_usd": tires_sales[0],
                "tires_sales_lbp": tires_sales[1],
                "gas_sales_usd": gas_sales[0],
                "gas_sales_lbp": gas_sales[1],
                "wash_sales_usd": wash_sales[0],
                "wash_sales_lbp": wash_sales[1],
                "other_sales_usd": other_sales[0],
                "other_sales_lbp": other_sales[1],
                "tires_sales_amount": 0,
                "tires_sales_currency": "USD",
                "gas_sales_amount": 0,
                "gas_sales_currency": "USD",
                "wash_sales_amount": 0,
                "wash_sales_currency": "USD",
                "credit_customer": ", ".join(
                    dict.fromkeys(entry["client_name"] for entry in credit_entries)
                ),
                "credit_amount": sum(entry["amount"] for entry in credit_entries)
                if len(credit_currencies) == 1
                else 0,
                "credit_currency": next(iter(credit_currencies))
                if len(credit_currencies) == 1
                else "MIXED",
                "credit_sales_usd": credit_totals["USD"],
                "credit_sales_lbp": credit_totals["LBP"],
                "credit_collected_usd": payment_totals["USD"],
                "credit_collected_lbp": payment_totals["LBP"],
                "cash_opening_usd": cash_opening[0],
                "cash_opening_lbp": cash_opening[1],
                "cash_actual_end_usd": cash_actual_end[0],
                "cash_actual_end_lbp": cash_actual_end[1],
                "notes": notes.strip(),
            }
            for prefix, (usd, lbp) in expense_values.items():
                record[f"{prefix}_usd"] = usd
                record[f"{prefix}_lbp"] = lbp

            try:
                action = save_record(
                    record,
                    allow_update=entry_mode == "Modifier une journée",
                    sync_csv=False,
                )
                save_credit_entries(record["record_date"], credit_entries, sync_csv=False)
                save_credit_payments(record["record_date"], payment_entries, sync_csv=True)
                summary = calculate_totals(record)
                st.session_state["last_saved_summary"] = {
                    "summary": summary,
                    "record_date": record["record_date"],
                    "action": action,
                }
                changed = True
            except (OSError, sqlite3.Error, GitHubStorageError, ValueError) as exc:
                st.error(f"Enregistrement impossible : {exc}")

    if "last_saved_summary" in st.session_state:
        saved = st.session_state["last_saved_summary"]
        render_saved_summary(saved["summary"], saved["record_date"], saved["action"])

    if not history.empty:
        latest = history.sort_values("record_date").iloc[-1]
        with st.expander("Dernier état enregistré", expanded=False):
            stock_ratio = (
                latest["stock_available_l"] / latest["tank_capacity_l"]
                if latest["tank_capacity_l"] > 0
                else 0
            )
            st.write(
                f"**{format_date_fr(latest['record_date'])}** — "
                f"{format_fr(latest['stock_available_l'], 0)} L disponibles sur "
                f"{format_fr(latest['tank_capacity_l'], 0)} L."
            )
            st.progress(min(max(float(stock_ratio), 0.0), 1.0))
    return changed


def _period_slice(
    valid_dates: pd.DataFrame,
    mode: str,
    year: int,
    month: int | None = None,
    week: int | None = None,
    day: date | None = None,
) -> pd.DataFrame:
    """Sous-ensemble des clôtures correspondant à une période donnée."""
    rows = valid_dates[valid_dates["record_date"].dt.year == year]
    if mode == "Année":
        return rows.copy()
    if mode == "Semaine":
        if week is None:
            return rows.iloc[0:0].copy()
        return rows[rows["record_date"].dt.isocalendar().week == week].copy()
    if month is None:
        return rows.iloc[0:0].copy()
    monthly = rows[rows["record_date"].dt.month == month]
    if mode == "Jour":
        if day is None:
            return monthly.iloc[0:0].copy()
        return monthly[monthly["record_date"].dt.date == day].copy()
    return monthly.copy()


def _previous_period(
    valid_dates: pd.DataFrame,
    mode: str,
    year: int,
    month: int | None,
    week: int | None,
    day: date | None,
) -> tuple[pd.DataFrame, str]:
    """Période précédente de même nature, avec son libellé."""
    empty = valid_dates.iloc[0:0].copy()

    if mode == "Année":
        return _period_slice(valid_dates, "Année", year - 1), f"{year - 1}"

    if mode == "Mois":
        previous_month = 12 if month == 1 else (month or 1) - 1
        previous_year = year - 1 if month == 1 else year
        rows = _period_slice(valid_dates, "Mois", previous_year, month=previous_month)
        return rows, f"{MONTHS_FR[previous_month].lower()} {previous_year}"

    if mode == "Semaine":
        if week is None:
            return empty, "—"
        if week > 1:
            return _period_slice(valid_dates, "Semaine", year, week=week - 1), f"semaine {week - 1:02d}"
        previous_year_rows = valid_dates[valid_dates["record_date"].dt.year == year - 1]
        if previous_year_rows.empty:
            return empty, "—"
        last_week = int(previous_year_rows["record_date"].dt.isocalendar().week.max())
        rows = _period_slice(valid_dates, "Semaine", year - 1, week=last_week)
        return rows, f"semaine {last_week:02d} · {year - 1}"

    if day is None:
        return empty, "—"
    earlier = valid_dates[valid_dates["record_date"].dt.date < day]
    if earlier.empty:
        return empty, "—"
    previous_day = earlier["record_date"].max().date()
    rows = valid_dates[valid_dates["record_date"].dt.date == previous_day].copy()
    return rows, previous_day.strftime("%d/%m/%Y")


def _variation(current: float, previous: float) -> float | None:
    """Écart en %, ou ``None`` quand la référence est nulle."""
    if not previous:
        return None
    return (current - previous) / abs(previous) * 100


def _equivalent_sum(rows: pd.DataFrame, prefix: str) -> float:
    """Somme USD + LL converti au taux propre à chaque journée."""
    if rows.empty:
        return 0.0
    rates = rows["exchange_rate"].replace(0, pd.NA)
    return float((rows[f"{prefix}_usd"] + rows[f"{prefix}_lbp"].div(rates).fillna(0)).sum())


def render_dashboard_tab(history: pd.DataFrame) -> None:
    palette = theme_palette()
    render_page_hero(
        "Analyse",
        "Tableau de bord",
        "Explorez les performances par jour, semaine, mois ou année, comparez avec la "
        "période précédente et identifiez rapidement les tendances importantes.",
        "Filtres par période · Comparaison",
    )
    if history.empty:
        st.info("Enregistrez une première journée pour alimenter le tableau de bord.")
        return

    valid_dates = history.dropna(subset=["record_date"]).copy()
    available_years = sorted(valid_dates["record_date"].dt.year.unique(), reverse=True)
    current_year = date.today().year
    default_year_index = (
        available_years.index(current_year) if current_year in available_years else 0
    )

    filter_1, filter_2, filter_3, filter_4 = st.columns([1, 1, 1.2, 1.3])
    period_mode = filter_1.selectbox(
        "Vue",
        ["Mois", "Semaine", "Année", "Jour"],
        key="dashboard_period_mode",
    )
    selected_year = filter_2.selectbox(
        "Année", available_years, index=default_year_index, key="dashboard_year"
    )
    year_rows_for_filters = valid_dates[valid_dates["record_date"].dt.year == selected_year]

    selected_month: int | None = None
    selected_week: int | None = None
    selected_day: date | None = None

    if period_mode in {"Mois", "Jour"}:
        available_months = sorted(
            int(month) for month in year_rows_for_filters["record_date"].dt.month.unique()
        )
        if not available_months:
            st.warning(f"Aucune donnée pour l'année {selected_year}.")
            return
        month_names = [MONTHS_FR[month] for month in available_months]
        selected_month_name = filter_3.selectbox(
            "Mois", month_names, index=len(month_names) - 1, key="dashboard_month"
        )
        selected_month = next(
            number for number, name in MONTHS_FR.items() if name == selected_month_name
        )
    elif period_mode == "Semaine":
        available_weeks = sorted(
            (
                int(week)
                for week in year_rows_for_filters["record_date"].dt.isocalendar().week.unique()
            ),
            reverse=True,
        )
        if not available_weeks:
            st.warning(f"Aucune donnée pour l'année {selected_year}.")
            return
        current_week = date.today().isocalendar().week
        week_index = available_weeks.index(current_week) if current_week in available_weeks else 0
        selected_week_label = filter_3.selectbox(
            "Semaine ISO",
            [f"Semaine {week:02d}" for week in available_weeks],
            index=week_index,
            key="dashboard_week",
        )
        selected_week = int(selected_week_label.split()[-1])
    else:
        filter_3.selectbox("Mois", ["Toute l'année"], disabled=True, key="dashboard_month_all")

    if period_mode == "Jour":
        monthly_days = _period_slice(valid_dates, "Mois", selected_year, month=selected_month)
        available_days = (
            monthly_days.sort_values("record_date")["record_date"].dt.strftime("%d/%m/%Y").tolist()
        )
        if not available_days:
            st.warning(f"Aucune donnée pour {MONTHS_FR[selected_month]} {selected_year}.")
            return
        today_label = date.today().strftime("%d/%m/%Y")
        default_day_index = (
            available_days.index(today_label)
            if today_label in available_days
            else len(available_days) - 1
        )
        selected_day_label = filter_4.selectbox(
            "Journée", available_days, index=default_day_index, key="dashboard_day"
        )
        selected_day = datetime.strptime(selected_day_label, "%d/%m/%Y").date()
        compare_column = st.columns(1)[0]
    else:
        compare_column = filter_4

    compare = compare_column.toggle(
        "Comparer à la période précédente",
        key="dashboard_compare",
        help="Superpose les totaux et l'évolution de la période équivalente qui précède.",
    )

    period = _period_slice(
        valid_dates,
        period_mode,
        selected_year,
        month=selected_month,
        week=selected_week,
        day=selected_day,
    )
    if period.empty:
        st.warning("Aucune donnée enregistrée pour cette période.")
        return

    if period_mode == "Année":
        period_label = f"Année {selected_year}"
    elif period_mode == "Semaine":
        week_start = period["record_date"].min().date()
        week_end = period["record_date"].max().date()
        period_label = (
            f"Semaine {int(selected_week):02d} — "
            f"du {week_start.strftime('%d/%m/%Y')} au {week_end.strftime('%d/%m/%Y')}"
        )
    elif period_mode == "Jour":
        period_label = f"Journée du {selected_day.strftime('%d/%m/%Y')}"
    else:
        period_label = f"{MONTHS_FR[selected_month]} {selected_year}"

    previous_period, previous_label = (
        _previous_period(
            valid_dates, period_mode, selected_year, selected_month, selected_week, selected_day
        )
        if compare
        else (valid_dates.iloc[0:0].copy(), "—")
    )
    comparing = compare and not previous_period.empty

    if compare and previous_period.empty:
        render_alert_card(
            "Comparaison indisponible",
            "Aucune journée n'est enregistrée sur la période précédente.",
            "⇄",
            "info",
        )
    elif comparing and len(period) != len(previous_period):
        render_alert_card(
            "Périodes de durées différentes",
            f"{len(period)} journée(s) enregistrée(s) contre {len(previous_period)} sur "
            f"{previous_label} : les écarts en % sont à lire avec cette réserve.",
            "⚠",
            "warning",
        )

    summary_tab, evolution_tab, breakdown_tab, detail_tab = st.tabs(
        [
            ":material/space_dashboard: Synthèse",
            ":material/show_chart: Évolution",
            ":material/donut_large: Répartition",
            ":material/receipt_long: Journal",
        ],
        key="dashboard_sections",
        on_change="rerun",
    )

    # ------------------------------------------------------------ Synthèse --
    if summary_tab.open:
        _render_dashboard_summary(
            period, previous_period, previous_label, period_label, period_mode, comparing, palette
        )

    # ----------------------------------------------------------- Évolution --
    elif evolution_tab.open:
        _render_dashboard_evolution(
            period, previous_period, previous_label, period_mode, comparing, palette
        )

    # ---------------------------------------------------------- Répartition -
    elif breakdown_tab.open:
        _render_dashboard_breakdown(period, palette)

    # -------------------------------------------------------------- Journal -
    elif detail_tab.open:
        _render_dashboard_journal(period, period_mode, selected_day, palette, valid_dates)


def _render_dashboard_summary(
    period: pd.DataFrame,
    previous_period: pd.DataFrame,
    previous_label: str,
    period_label: str,
    period_mode: str,
    comparing: bool,
    palette: Mapping[str, Any],
) -> None:
    equivalent_sales = period["total_sales_usd_equiv"].sum()
    equivalent_expenses = period["total_expenses_usd_equiv"].sum()
    equivalent_net = period["net_usd_equiv"].sum()
    volume = period["fuel_volume_sold_l"].sum()
    margin = (equivalent_net / equivalent_sales * 100) if equivalent_sales else 0

    delta_label = f"vs {previous_label}"

    def delta(current: float, column: str, higher_is_better: bool = True) -> str:
        if not comparing:
            return ""
        return render_stat_delta(
            _variation(current, previous_period[column].sum()), delta_label, higher_is_better
        )

    render_section_heading(
        f"Résultats — {period_label}",
        "Équivalents USD calculés au taux enregistré chaque jour.",
    )
    card_1, card_2, card_3, card_4 = st.columns(4)
    with card_1:
        render_stat_card(
            "Ventes équiv. USD",
            format_usd(equivalent_sales),
            f"{format_usd(period['total_sales_usd'].sum())} + {format_lbp(period['total_sales_lbp'].sum())}",
            "↗",
            "success",
            delta(equivalent_sales, "total_sales_usd_equiv"),
        )
    with card_2:
        render_stat_card(
            "Dépenses équiv. USD",
            format_usd(equivalent_expenses),
            f"{format_usd(period['total_expenses_usd'].sum())} + {format_lbp(period['total_expenses_lbp'].sum())}",
            "↘",
            "danger",
            delta(equivalent_expenses, "total_expenses_usd_equiv", higher_is_better=False),
        )
    with card_3:
        render_stat_card(
            "Résultat net",
            format_usd(equivalent_net),
            f"{format_fr(margin, 1)} % de marge",
            "◆",
            "success" if equivalent_net >= 0 else "danger",
            delta(equivalent_net, "net_usd_equiv"),
        )
    with card_4:
        render_stat_card(
            "Volume vendu",
            f"{format_fr(volume, 0)} L",
            f"{len(period)} journée(s) enregistrée(s)",
            "◉",
            "info",
            delta(volume, "fuel_volume_sold_l"),
        )

    render_section_heading(
        "Du chiffre d'affaires au résultat",
        "Chaque étape montre ce qui construit puis entame le résultat.",
    )
    waterfall = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "total"],
            x=["Ventes", "Dépenses", "Résultat"],
            y=[equivalent_sales, -equivalent_expenses, 0],
            text=[
                format_usd(equivalent_sales),
                f"− {format_usd(equivalent_expenses)}",
                format_usd(equivalent_net),
            ],
            textposition="outside",
            textfont={"color": palette["muted"], "size": 12},
            connector={"line": {"color": palette["axis"], "width": 1}},
            increasing={"marker": {"color": palette["sales"]}},
            decreasing={"marker": {"color": palette["expenses"]}},
            totals={"marker": {"color": palette["net"] if equivalent_net >= 0 else palette["expenses"]}},
            hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
        )
    )
    waterfall.add_hline(y=0, line_width=1, line_color=palette["axis"])
    waterfall.update_layout(yaxis_title="Équivalent USD")
    st.plotly_chart(
        apply_chart_style(waterfall, height=340, legend=False, palette=palette),
        width="stretch",
        config=PLOTLY_CONFIG,
    )

    if comparing:
        render_section_heading(
            f"{period_label} vs {previous_label}",
            f"{len(period)} journée(s) contre {len(previous_period)} de référence.",
        )
        labels = ["Ventes", "Dépenses", "Résultat"]
        current_values = [equivalent_sales, equivalent_expenses, equivalent_net]
        previous_values = [
            previous_period["total_sales_usd_equiv"].sum(),
            previous_period["total_expenses_usd_equiv"].sum(),
            previous_period["net_usd_equiv"].sum(),
        ]
        comparison = go.Figure()
        comparison.add_bar(
            x=labels,
            y=previous_values,
            name=f"Période précédente ({previous_label})",
            marker_color=palette["sales_prev"],
            hovertemplate="%{x} — précédent<br>$%{y:,.2f}<extra></extra>",
        )
        comparison.add_bar(
            x=labels,
            y=current_values,
            name="Période actuelle",
            marker_color=palette["sales"],
            hovertemplate="%{x} — actuel<br>$%{y:,.2f}<extra></extra>",
        )
        comparison.update_layout(barmode="group", bargap=0.32, yaxis_title="Équivalent USD")
        st.plotly_chart(
            apply_chart_style(comparison, height=360, palette=palette),
            width="stretch",
            config=PLOTLY_CONFIG,
        )

    render_section_heading("Vue globale", "Tous les enregistrements confondus.")
    global_1, global_2, global_3 = st.columns(3)
    global_1.metric("Journées de la période", format_fr(len(period), 0))
    global_2.metric(
        "Moyenne ventes / jour",
        format_usd(period["total_sales_usd_equiv"].mean()),
    )
    global_3.metric("Dernier stock connu", f"{format_fr(period.sort_values('record_date').iloc[-1]['stock_available_l'], 0)} L")


def _chart_frame(period: pd.DataFrame, period_mode: str) -> pd.DataFrame:
    """Série temporelle agrégée selon la granularité choisie."""
    source = period.sort_values("record_date").copy()
    columns = ["total_sales_usd_equiv", "total_expenses_usd_equiv", "net_usd_equiv"]
    if period_mode == "Année":
        source["Période"] = source["record_date"].dt.month
        frame = source.groupby("Période", as_index=False)[columns].sum().sort_values("Période")
        frame["Libellé"] = frame["Période"].map(MONTHS_FR)
        return frame
    frame = source[["record_date", *columns]].copy()
    frame["Libellé"] = frame["record_date"].dt.strftime(
        "%d/%m/%Y" if period_mode == "Jour" else "%d/%m"
    )
    return frame


def _render_dashboard_evolution(
    period: pd.DataFrame,
    previous_period: pd.DataFrame,
    previous_label: str,
    period_mode: str,
    comparing: bool,
    palette: Mapping[str, Any],
) -> None:
    chart_data = _chart_frame(period, period_mode)
    granularity = "un mois" if period_mode == "Année" else "une journée"

    render_section_heading(
        "Revenus et dépenses",
        f"Chaque barre représente {granularity} de la période.",
    )
    bar = go.Figure()
    bar.add_bar(
        x=chart_data["Libellé"],
        y=chart_data["total_sales_usd_equiv"],
        name="Revenus",
        marker_color=palette["sales"],
        hovertemplate="%{x}<br>Revenus : $%{y:,.2f}<extra></extra>",
    )
    bar.add_bar(
        x=chart_data["Libellé"],
        y=chart_data["total_expenses_usd_equiv"],
        name="Dépenses",
        marker_color=palette["expenses"],
        hovertemplate="%{x}<br>Dépenses : $%{y:,.2f}<extra></extra>",
    )
    bar.update_layout(barmode="group", bargap=0.28, yaxis_title="Équivalent USD", hovermode="x unified")
    st.plotly_chart(
        apply_chart_style(bar, height=390, palette=palette),
        width="stretch",
        config=PLOTLY_CONFIG,
    )

    if period_mode != "Jour":
        hint = (
            f"En pointillés : {previous_label}, aligné rang par rang."
            if comparing
            else "Vert : revenus · Orange : dépenses · Bleu : résultat net."
        )
        render_section_heading("Évolution financière", hint)
        line = go.Figure()
        if comparing:
            previous_data = _chart_frame(previous_period, period_mode)
            aligned = previous_data.head(len(chart_data))
            for column, color, name in (
                ("total_sales_usd_equiv", palette["sales_prev"], "Revenus"),
                ("total_expenses_usd_equiv", palette["expenses_prev"], "Dépenses"),
                ("net_usd_equiv", palette["net_prev"], "Résultat"),
            ):
                line.add_scatter(
                    x=chart_data["Libellé"].head(len(aligned)),
                    y=aligned[column],
                    mode="lines",
                    name=f"{name} ({previous_label})",
                    line={"color": color, "width": 2, "dash": "dash"},
                    hovertemplate=f"{name} précédent : $%{{y:,.2f}}<extra></extra>",
                )
        for column, color, name in (
            ("total_sales_usd_equiv", palette["sales"], "Revenus"),
            ("total_expenses_usd_equiv", palette["expenses"], "Dépenses"),
            ("net_usd_equiv", palette["net"], "Résultat net"),
        ):
            line.add_scatter(
                x=chart_data["Libellé"],
                y=chart_data[column],
                mode="lines+markers",
                name=name,
                line={"color": color, "width": 2},
                marker={"size": 6},
                hovertemplate=f"%{{x}}<br>{name} : $%{{y:,.2f}}<extra></extra>",
            )
        line.add_hline(y=0, line_width=1, line_color=palette["axis"])
        line.update_layout(yaxis_title="Équivalent USD", hovermode="x unified")
        st.plotly_chart(
            apply_chart_style(line, height=400, palette=palette),
            width="stretch",
            config=PLOTLY_CONFIG,
        )

    render_section_heading(
        "Évolution du stock d'essence",
        "Niveau réel en fin de journée, rapporté à la capacité de la cuve.",
    )
    stock_history = period.sort_values("record_date")
    stock = go.Figure()
    stock.add_scatter(
        x=stock_history["record_date"],
        y=stock_history["stock_available_l"],
        mode="lines",
        name="Stock disponible",
        line={"color": palette["sales"], "width": 2},
        fill="tozeroy",
        fillcolor=_fill(palette["sales"], 0.18),
        hovertemplate="%{x|%d/%m/%Y}<br>%{y:,.0f} L<extra></extra>",
    )
    stock.add_scatter(
        x=stock_history["record_date"],
        y=stock_history["tank_capacity_l"],
        mode="lines",
        name="Capacité de la cuve",
        line={"color": palette["tick"], "width": 1.5, "dash": "dash"},
        hovertemplate="Capacité : %{y:,.0f} L<extra></extra>",
    )
    stock.update_layout(yaxis_title="Litres", hovermode="x unified")
    stock.update_xaxes(tickformat="%d/%m")
    st.plotly_chart(
        apply_chart_style(stock, height=360, palette=palette),
        width="stretch",
        config=PLOTLY_CONFIG,
    )


def _fill(hex_color: str, alpha: float) -> str:
    """Convertit un hex en rgba pour les aplats de surface."""
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _render_dashboard_breakdown(period: pd.DataFrame, palette: Mapping[str, Any]) -> None:
    render_section_heading(
        "Répartition des dépenses", "Valeurs consolidées en équivalent USD sur la période."
    )
    expense_frame = pd.DataFrame(
        [
            {"Poste": label, "Montant": _equivalent_sum(period, prefix)}
            for label, prefix in EXPENSE_CATEGORIES.items()
        ]
    )
    expense_frame = expense_frame[expense_frame["Montant"] > 0].sort_values(
        "Montant", ascending=False
    )

    if expense_frame.empty:
        st.markdown(
            '<div class="empty-state">Aucune dépense enregistrée sur cette période.</div>',
            unsafe_allow_html=True,
        )
    else:
        total = expense_frame["Montant"].sum()
        pie_column, table_column = st.columns([1.35, 1])
        with pie_column:
            pie = go.Figure(
                go.Pie(
                    labels=expense_frame["Poste"],
                    values=expense_frame["Montant"],
                    hole=0.52,
                    sort=False,
                    textinfo="percent",
                    insidetextfont={"color": "#ffffff", "size": 12},
                    marker={
                        "colors": list(palette["categorical"])[: len(expense_frame)],
                        "line": {"color": palette["surface"], "width": 2},
                    },
                    hovertemplate="%{label}<br>$%{value:,.2f}<br>%{percent}<extra></extra>",
                )
            )
            st.plotly_chart(
                apply_chart_style(pie, height=380, palette=palette),
                width="stretch",
                config=PLOTLY_CONFIG,
            )
        with table_column:
            # Table de relief : l'identité d'un poste ne repose jamais sur la seule couleur.
            detail = pd.DataFrame(
                {
                    "Poste": expense_frame["Poste"],
                    "Équiv. USD": expense_frame["Montant"].map(format_usd),
                    "Part": (expense_frame["Montant"] / total * 100).map(
                        lambda part: f"{format_fr(part, 1)} %"
                    ),
                }
            )
            st.dataframe(detail, hide_index=True, width="stretch")

    render_section_heading("Analyse par groupe", "Un angle à la fois, sans surcharger l'écran.")
    analysis_group = st.selectbox(
        "Groupe à visualiser",
        ["Stock & change", "Dépenses", "Ventes", "Crédits", "Totaux", "Caisses", "Notes"],
        key="dashboard_analysis_group",
    )

    if analysis_group == "Notes":
        notes_view = period[["record_date", "notes"]].copy()
        notes_view = notes_view[notes_view["notes"].fillna("").str.strip() != ""]
        if notes_view.empty:
            st.markdown(
                '<div class="empty-state">Aucune note sur cette période.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.dataframe(
                notes_view,
                hide_index=True,
                width="stretch",
                column_config={
                    "record_date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                    "notes": st.column_config.TextColumn("Notes", width="large"),
                },
            )
        return

    group_figure = go.Figure()
    show_legend = False
    if analysis_group == "Stock & change":
        variances = period["stock_variance_l"]
        if variances.abs().max() < 0.01:
            st.markdown(
                '<div class="empty-state">Aucun écart de stock sur la période : '
                "le stock réel correspond au stock théorique chaque jour.</div>",
                unsafe_allow_html=True,
            )
            return
        group_figure.add_bar(
            x=period["record_date"],
            y=variances,
            name="Écart réel − théorique",
            marker_color=[
                palette["sales"] if abs(value) < 0.01 else palette["expenses"] for value in variances
            ],
            hovertemplate="%{x|%d/%m/%Y}<br>Écart : %{y:,.1f} L<extra></extra>",
        )
        group_figure.update_xaxes(tickformat="%d/%m", title=None)
        group_figure.update_yaxes(title="Écart en litres")
    elif analysis_group == "Dépenses":
        values = [_equivalent_sum(period, prefix) for prefix in EXPENSE_CATEGORIES.values()]
        group_figure.add_bar(
            y=list(EXPENSE_CATEGORIES.keys()),
            x=values,
            orientation="h",
            marker_color=palette["expenses"],
            hovertemplate="%{y}<br>$%{x:,.2f}<extra></extra>",
        )
        group_figure.update_xaxes(title="Équivalent USD")
    elif analysis_group == "Ventes":
        values = [_equivalent_sum(period, prefix) for prefix in SALES_CATEGORIES.values()]
        values.append(period["credit_sold_usd_equiv"].sum())
        group_figure.add_bar(
            y=[*SALES_CATEGORIES.keys(), "Ventes à crédit"],
            x=values,
            orientation="h",
            marker_color=palette["sales"],
            hovertemplate="%{y}<br>$%{x:,.2f}<extra></extra>",
        )
        group_figure.update_xaxes(title="Équivalent USD")
    elif analysis_group == "Crédits":
        group_figure.add_bar(
            x=["Crédit vendu", "Crédit encaissé"],
            y=[
                period["credit_sold_usd_equiv"].sum(),
                period["credit_collected_usd_equiv"].sum(),
            ],
            marker_color=[palette["expenses"], palette["sales"]],
            hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
        )
        group_figure.update_yaxes(title="Équivalent USD")
    elif analysis_group == "Totaux":
        net = period["net_usd_equiv"].sum()
        group_figure.add_bar(
            x=["Ventes", "Dépenses", "Résultat"],
            y=[
                period["total_sales_usd_equiv"].sum(),
                period["total_expenses_usd_equiv"].sum(),
                net,
            ],
            marker_color=[
                palette["sales"],
                palette["expenses"],
                palette["sales"] if net >= 0 else palette["expenses"],
            ],
            hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
        )
        group_figure.update_yaxes(title="Équivalent USD")
    else:
        rates = period["exchange_rate"].replace(0, pd.NA)
        cash_gap = period["cash_variance_usd"] + period["cash_variance_lbp"].div(rates).fillna(0)
        group_figure.add_bar(
            x=period["record_date"],
            y=cash_gap,
            marker_color=[
                palette["sales"] if value >= 0 else palette["expenses"] for value in cash_gap
            ],
            hovertemplate="%{x|%d/%m/%Y}<br>Écart caisse : $%{y:,.2f}<extra></extra>",
        )
        group_figure.update_xaxes(tickformat="%d/%m", title=None)
        group_figure.update_yaxes(title="Écart équivalent USD")

    st.plotly_chart(
        apply_chart_style(group_figure, height=390, legend=show_legend, palette=palette),
        width="stretch",
        config=PLOTLY_CONFIG,
    )


def _render_dashboard_journal(
    period: pd.DataFrame,
    period_mode: str,
    selected_day: date | None,
    palette: Mapping[str, Any],
    valid_dates: pd.DataFrame,
) -> None:
    if period_mode != "Jour":
        render_section_heading(
            "Journal de la période", "Une ligne par journée enregistrée, montants d'origine."
        )
        ledger = period.sort_values("record_date", ascending=False)[
            [
                "record_date",
                "exchange_rate",
                "fuel_volume_sold_l",
                "stock_available_l",
                "total_sales_usd",
                "total_sales_lbp",
                "total_expenses_usd",
                "total_expenses_lbp",
                "net_usd_equiv",
            ]
        ]
        st.dataframe(
            ledger,
            hide_index=True,
            width="stretch",
            column_config={
                "record_date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "exchange_rate": st.column_config.NumberColumn("Taux LL/USD", format="%.0f"),
                "fuel_volume_sold_l": st.column_config.NumberColumn("Litres vendus", format="%.0f"),
                "stock_available_l": st.column_config.NumberColumn("Stock fin", format="%.0f"),
                "total_sales_usd": st.column_config.NumberColumn("Ventes USD", format="$%.2f"),
                "total_sales_lbp": st.column_config.NumberColumn("Ventes LL", format="%.0f"),
                "total_expenses_usd": st.column_config.NumberColumn("Dépenses USD", format="$%.2f"),
                "total_expenses_lbp": st.column_config.NumberColumn("Dépenses LL", format="%.0f"),
                "net_usd_equiv": st.column_config.NumberColumn("Résultat équiv.", format="$%.2f"),
            },
        )
        st.download_button(
            "Télécharger le journal de la période en CSV",
            data=ledger.to_csv(index=False).encode("utf-8-sig"),
            file_name="journal_periode.csv",
            mime="text/csv",
            key="download_period_journal",
            width="stretch",
        )
        return

    day_record = period.iloc[0]
    render_section_heading(
        f"Détail du {selected_day.strftime('%d/%m/%Y')}",
        f"Taux utilisé : 1 USD = {format_fr(day_record['exchange_rate'], 0)} LL",
    )
    detail_1, detail_2, detail_3, detail_4 = st.columns(4)
    detail_1.metric("Stock ouverture", f"{format_fr(day_record['opening_stock_l'], 0)} L")
    detail_2.metric("Entrées carburant", f"{format_fr(day_record['fuel_input_l'], 0)} L")
    detail_3.metric("Stock théorique fin", f"{format_fr(day_record['theoretical_stock_end_l'], 0)} L")
    detail_4.metric(
        "Écart stock",
        f"{format_fr(day_record['stock_variance_l'], 1)} L",
        delta=f"{format_fr(day_record['stock_variance_l'], 1)} L",
    )

    day_credits = load_credit_entries(selected_day.isoformat())
    day_payments = load_credit_payments(selected_day.isoformat())
    money_columns = {
        "USD": st.column_config.NumberColumn(format="$%.2f"),
        "LL": st.column_config.NumberColumn(format="%.0f LL"),
        "Équivalent USD": st.column_config.NumberColumn(format="$%.2f"),
    }
    sales_column, expenses_column = st.columns(2)
    with sales_column:
        st.markdown("##### Toutes les ventes")
        st.dataframe(
            build_sales_breakdown(day_record, day_credits),
            hide_index=True,
            width="stretch",
            column_config=money_columns,
        )
    with expenses_column:
        st.markdown("##### Toutes les dépenses et achats")
        st.dataframe(
            build_expense_breakdown(day_record),
            hide_index=True,
            width="stretch",
            column_config=money_columns,
        )

    st.markdown("##### Rapprochement des caisses")
    cash_rows = [
        {
            "Devise": "USD" if currency == "usd" else "LL",
            "Ouverture": formatter(day_record[f"cash_opening_{currency}"]),
            "Théorique fin": formatter(day_record[f"cash_theoretical_end_{currency}"]),
            "Réelle fin": formatter(day_record[f"cash_actual_end_{currency}"]),
            "Écart": formatter(day_record[f"cash_variance_{currency}"]),
        }
        for currency, formatter in (("usd", format_usd), ("lbp", format_lbp))
    ]
    st.dataframe(pd.DataFrame(cash_rows), hide_index=True, width="stretch")

    if not day_payments.empty:
        st.markdown("##### Crédits encaissés auprès des clients")
        st.dataframe(
            day_payments[["client_name", "amount", "currency", "note"]],
            hide_index=True,
            width="stretch",
        )
    if day_record["notes"]:
        st.markdown("##### Notes")
        st.write(day_record["notes"])

    day_ledger = build_transaction_ledger(period, day_credits, day_payments)
    st.download_button(
        "Télécharger le détail de cette journée en CSV",
        data=day_ledger.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"detail_station_{selected_day.isoformat()}.csv",
        mime="text/csv",
        key="download_day_detail",
        width="stretch",
    )


def render_history_tab(history: pd.DataFrame) -> None:
    render_page_hero(
        "Données & exports",
        "Historique des clôtures",
        "Retrouvez chaque journée, consultez le journal comptable et exportez les données dont vous avez besoin.",
        "SQLite + sauvegardes CSV",
    )
    if history.empty:
        st.info("L'historique est vide. Les nouvelles saisies apparaîtront ici.")
        return

    filter_col, view_col = st.columns([2, 1])
    search = filter_col.text_input(
        "Rechercher",
        placeholder="Nom du client, note…",
        key="history_search",
    )
    view_mode = view_col.segmented_control(
        "Affichage",
        ["Synthèse", "Rapport complet", "Technique"],
        default="Synthèse",
        required=True,
        width="stretch",
        key="history_view",
    )

    displayed = history.sort_values("record_date", ascending=False).copy()
    if search.strip():
        needle = search.strip().casefold()
        mask = (
            displayed["credit_customer"].fillna("").str.casefold().str.contains(needle, regex=False)
            | displayed["notes"].fillna("").str.casefold().str.contains(needle, regex=False)
        )
        displayed = displayed[mask]

    if view_mode == "Synthèse":
        columns = [
            "record_date",
            "exchange_rate",
            "fuel_volume_sold_l",
            "stock_available_l",
            "stock_variance_l",
            "total_sales_usd",
            "total_sales_lbp",
            "total_expenses_usd",
            "total_expenses_lbp",
            "net_usd",
            "net_lbp",
            "net_usd_equiv",
            "credit_customer",
        ]
        table = displayed[columns].copy()
    elif view_mode == "Rapport complet":
        table = build_grouped_daily_export(displayed)
    else:
        columns = [column for column in DB_COLUMNS if column in displayed.columns]
        table = displayed[columns].copy()

    column_config = {
        "record_date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
        "exchange_rate": st.column_config.NumberColumn("Taux LL/USD", format="%.0f"),
        "fuel_volume_sold_l": st.column_config.NumberColumn("Litres vendus", format="%.1f L"),
        "stock_available_l": st.column_config.NumberColumn("Stock", format="%.1f L"),
        "stock_variance_l": st.column_config.NumberColumn("Écart stock", format="%.1f L"),
        "total_sales_usd": st.column_config.NumberColumn("Ventes USD", format="$%.2f"),
        "total_sales_lbp": st.column_config.NumberColumn("Ventes LL", format="%.0f LL"),
        "total_expenses_usd": st.column_config.NumberColumn("Dépenses USD", format="$%.2f"),
        "total_expenses_lbp": st.column_config.NumberColumn("Dépenses LL", format="%.0f LL"),
        "net_usd": st.column_config.NumberColumn("Solde USD", format="$%.2f"),
        "net_lbp": st.column_config.NumberColumn("Solde LL", format="%.0f LL"),
        "net_usd_equiv": st.column_config.NumberColumn("Résultat équiv. USD", format="$%.2f"),
        "credit_customer": st.column_config.TextColumn("Client à crédit"),
    }
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config=column_config,
        height=min(620, 42 + len(table) * 35),
    )
    st.caption(f"{len(displayed)} journée(s) affichée(s) — {len(history)} au total.")

    render_delete_section(history)

    st.divider()
    st.markdown("### Journal comptable ligne par ligne")
    st.caption(
        "Chaque vente, achat, dépense et crédit client apparaît sur sa propre ligne "
        "avec le taux de change de la journée."
    )
    all_credits = load_credit_entries()
    all_payments = load_credit_payments()
    ledger = build_transaction_ledger(history, all_credits, all_payments)
    journal_years = sorted(history["record_date"].dt.year.dropna().unique(), reverse=True)
    current_year = date.today().year
    journal_year_index = journal_years.index(current_year) if current_year in journal_years else 0
    journal_filter_1, journal_filter_2 = st.columns(2)
    journal_year = journal_filter_1.selectbox(
        "Année du journal",
        journal_years,
        index=journal_year_index,
        key="journal_year",
    )
    journal_month_options = ["Tous les mois", *MONTHS_FR.values()]
    journal_default_month = (
        date.today().month
        if journal_year == date.today().year
        else int(
            history[history["record_date"].dt.year == journal_year]["record_date"].dt.month.max()
        )
    )
    journal_month_name = journal_filter_2.selectbox(
        "Mois du journal",
        journal_month_options,
        index=journal_default_month,
        key="journal_month",
    )

    if not ledger.empty:
        ledger_dates = pd.to_datetime(ledger["Date"])
        journal_mask = ledger_dates.dt.year == journal_year
        if journal_month_name != "Tous les mois":
            journal_month = next(
                number for number, name in MONTHS_FR.items() if name == journal_month_name
            )
            journal_mask &= ledger_dates.dt.month == journal_month
        filtered_ledger = ledger[journal_mask].copy()
    else:
        filtered_ledger = ledger

    if filtered_ledger.empty:
        st.info("Aucune opération monétaire sur cette période.")
    else:
        journal_sales = filtered_ledger[
            filtered_ledger["Type"].isin(["Vente", "Vente à crédit"])
        ]["Équivalent USD"].sum()
        journal_expenses = filtered_ledger[filtered_ledger["Type"] == "Dépense"][
            "Équivalent USD"
        ].sum()
        journal_1, journal_2, journal_3, journal_4 = st.columns(4)
        journal_1.metric("Lignes d'opérations", f"{len(filtered_ledger):,}")
        journal_2.metric("Ventes (équiv. USD)", format_usd(journal_sales))
        journal_3.metric("Dépenses (équiv. USD)", format_usd(journal_expenses))
        journal_4.metric("Résultat", format_usd(journal_sales - journal_expenses))
        st.dataframe(
            filtered_ledger.sort_values(["Date", "Type"], ascending=[False, True]),
            hide_index=True,
            width="stretch",
            height=min(650, 42 + len(filtered_ledger) * 35),
            column_config={
                "Date": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "Montant": st.column_config.NumberColumn(format="%.2f"),
                "Taux LL/USD": st.column_config.NumberColumn(format="%.0f"),
                "Équivalent USD": st.column_config.NumberColumn(format="$%.2f"),
            },
        )
        period_slug = (
            str(journal_year)
            if journal_month_name == "Tous les mois"
            else f"{journal_year}_{journal_month_name.lower()}"
        )
        st.download_button(
            "Télécharger ce journal détaillé en CSV",
            data=filtered_ledger.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"journal_detaille_{period_slug}.csv",
            mime="text/csv",
            key="download_filtered_ledger",
            width="stretch",
        )

    download_excel_col, download_csv_col = st.columns(2)
    try:
        excel_data = build_excel_export(
            history.sort_values("record_date"), all_credits, all_payments
        )
        download_excel_col.download_button(
            "Télécharger tout l'historique en Excel",
            data=excel_data,
            file_name=f"historique_station_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    except Exception as exc:  # L'application reste utilisable si le moteur Excel manque.
        st.warning(f"Export Excel temporairement indisponible : {exc}")

    csv_export = build_grouped_daily_export(history.sort_values("record_date"))
    csv_export["Date"] = pd.to_datetime(csv_export["Date"]).dt.strftime("%Y-%m-%d")
    download_csv_col.download_button(
        "Télécharger tout l'historique en CSV",
        data=csv_export.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"historique_station_{date.today().isoformat()}.csv",
        mime="text/csv",
        width="stretch",
    )

    with st.expander("Informations sur le stockage GitHub"):
        st.write("Source permanente : dépôt GitHub privé `narvall018/station-pilot`.")
        st.write("Branche de données : `data`.")
        st.write("Fichiers : `station_data.csv`, `station_credits.csv` et "
                 "`station_credit_payments.csv`.")
        st.write(
            "Chaque modification crée un commit atomique. SQLite est seulement un "
            "cache temporaire de calcul et peut être supprimé sans perdre les données."
        )



def render_delete_section(history: pd.DataFrame) -> None:
    """Suppression de journées, repliée par défaut et protégée par confirmation."""
    feedback = st.session_state.pop("delete_feedback", None)
    if feedback:
        render_alert_card(
            "Suppression effectuée",
            feedback,
            "✓",
            "success",
        )

    with st.expander("Supprimer des journées", expanded=False):
        st.caption(
            "La suppression crée un nouveau commit. La version précédente reste "
            "récupérable dans l'historique de la branche GitHub « data »."
        )
        available = (
            history.dropna(subset=["record_date"])
            .sort_values("record_date", ascending=False)["record_date"]
            .dt.strftime("%Y-%m-%d")
            .tolist()
        )
        selected = st.multiselect(
            "Journées à supprimer",
            available,
            format_func=format_date_fr,
            key="delete_selection",
            placeholder="Choisissez une ou plusieurs dates",
        )

        if not selected:
            st.caption("Sélectionnez au moins une journée pour activer la suppression.")
            return

        st.warning(
            f"{len(selected)} journée(s) seront supprimées, ainsi que les crédits "
            "et remboursements enregistrés ces jours-là."
        )
        confirmation = st.text_input(
            "Tapez SUPPRIMER pour confirmer",
            key="delete_confirmation",
            placeholder="SUPPRIMER",
        )
        ready = confirmation.strip().upper() == "SUPPRIMER"
        if st.button(
            "Supprimer définitivement",
            type="primary",
            disabled=not ready,
            width="stretch",
            key="delete_button",
        ):
            try:
                deleted, backup_name = delete_records(selected)
            except (OSError, sqlite3.Error, GitHubStorageError) as exc:
                st.error(f"Suppression impossible : {exc}")
                return
            if not deleted:
                st.error("Aucune des journées sélectionnées n'a été trouvée en base.")
                return
            dates = ", ".join(format_date_fr(value) for value in deleted)
            st.session_state["delete_feedback"] = (
                f"{len(deleted)} journée(s) supprimée(s) : {dates}. "
                f"Point de restauration : {backup_name}."
            )
            st.session_state.pop("delete_selection", None)
            st.session_state.pop("delete_confirmation", None)
            st.rerun()

def render_sidebar_navigation(history: pd.DataFrame) -> str:
    """Construit la navigation principale et renvoie la page active."""
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-brand__mark">⛽</div>
                <div class="sidebar-brand__name">Station Pilot</div>
                <div class="sidebar-brand__tagline">Votre copilote de gestion quotidienne</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        selected_page = st.radio(
            "Navigation principale",
            list(NAVIGATION_LABELS),
            index=0,
            format_func=NAVIGATION_LABELS.__getitem__,
            label_visibility="collapsed",
            key="main_navigation",
        )
        st.space("small")

        theme = st.session_state.get("app_theme", "light")
        next_theme = "dark" if theme == "light" else "light"
        if st.button(
            "Thème sombre" if theme == "light" else "Thème clair",
            icon=":material/dark_mode:" if theme == "light" else ":material/light_mode:",
            key="theme_toggle",
            width="stretch",
        ):
            st.session_state["app_theme"] = next_theme
            st.rerun()
        st.space("small")
        valid_history = history.dropna(subset=["record_date"])
        latest_date = (
            format_date_fr(valid_history["record_date"].max())
            if not valid_history.empty
            else "Aucune clôture"
        )
        record_count = len(valid_history)
        st.markdown(
            f"""
            <div class="sidebar-status">
                <strong>Données GitHub synchronisées</strong><br>
                Dernière clôture : {latest_date}<br>
                {record_count} journée(s) enregistrée(s)
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("Les CSV permanents sont enregistrés sur la branche GitHub « data ».")
    return selected_page


def main() -> None:
    st.set_page_config(
        page_title="Station Pilot — Gestion de station-service",
        page_icon=":material/local_gas_station:",
        layout="wide",
        initial_sidebar_state="auto",
    )
    palette = THEMES[resolve_theme()]
    apply_theme_config(palette)
    apply_styles(palette)

    try:
        restored_rows = initialize_storage()
        history = load_data()
    except StorageConfigurationError:
        st.error("Le stockage GitHub n'est pas encore configuré.")
        st.code(
            '[github_storage]\n'
            'token = "NOUVEAU_TOKEN_GITHUB"\n'
            'owner = "narvall018"\n'
            'repo = "station-pilot"\n'
            'branch = "data"',
            language="toml",
        )
        st.caption(
            "Ajoutez ces valeurs dans les Secrets de Streamlit Cloud, avec un nouveau "
            "token autorisé à lire et écrire le contenu du dépôt."
        )
        st.stop()
    except GitHubStorageConflictError as exc:
        st.warning(str(exc))
        st.stop()
    except (OSError, sqlite3.Error, GitHubStorageError) as exc:
        st.error(f"Impossible de synchroniser les données GitHub : {exc}")
        st.stop()

    if restored_rows:
        st.toast(f"{restored_rows} journée(s) restaurée(s) depuis le CSV.", icon="✅")

    active_page = render_sidebar_navigation(history)
    if active_page == "Accueil":
        render_home_page(history)
    elif active_page == "Saisie":
        if render_entry_tab(history):
            st.rerun()
    elif active_page == "Tableau de bord":
        render_dashboard_tab(history)
    elif active_page == "Crédits":
        render_credits_page(history)
    else:
        render_history_tab(history)


if __name__ == "__main__":
    main()
