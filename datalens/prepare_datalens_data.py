from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_DIR = ROOT / "datalens" / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_data() -> dict[str, pd.DataFrame]:
    return {
        "customers": pd.read_csv(RAW_DIR / "olist_customers_dataset.csv"),
        "orders": pd.read_csv(RAW_DIR / "olist_orders_dataset.csv"),
        "items": pd.read_csv(RAW_DIR / "olist_order_items_dataset.csv"),
        "reviews": pd.read_csv(RAW_DIR / "olist_order_reviews_dataset.csv"),
        "products": pd.read_csv(RAW_DIR / "olist_products_dataset.csv"),
        "categories": pd.read_csv(RAW_DIR / "product_category_name_translation.csv"),
    }


def build_order_mart(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    orders = data["orders"].copy()
    for column in [
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]:
        orders[column] = pd.to_datetime(orders[column], errors="coerce")

    order_items = (
        data["items"]
        .groupby("order_id", as_index=False)
        .agg(
            items_qty=("order_item_id", "count"),
            product_revenue=("price", "sum"),
            freight_value=("freight_value", "sum"),
        )
    )

    reviews = (
        data["reviews"]
        .groupby("order_id", as_index=False)
        .agg(review_score=("review_score", "mean"))
    )

    main_category = (
        data["items"][["order_id", "product_id", "price"]]
        .merge(
            data["products"][["product_id", "product_category_name"]],
            on="product_id",
            how="left",
        )
        .merge(data["categories"], on="product_category_name", how="left")
        .sort_values(["order_id", "price"], ascending=[True, False])
        .drop_duplicates("order_id")
        [["order_id", "product_category_name_english"]]
    )

    mart = (
        orders.merge(data["customers"], on="customer_id", how="left")
        .merge(order_items, on="order_id", how="left")
        .merge(reviews, on="order_id", how="left")
        .merge(main_category, on="order_id", how="left")
    )

    mart["gmv"] = mart["product_revenue"].fillna(0) + mart["freight_value"].fillna(0)
    mart["purchase_month"] = mart["order_purchase_timestamp"].dt.to_period("M").dt.to_timestamp()
    mart["delivery_days"] = (
        mart["order_delivered_customer_date"] - mart["order_purchase_timestamp"]
    ).dt.total_seconds() / 86_400
    mart["delay_days"] = (
        mart["order_delivered_customer_date"] - mart["order_estimated_delivery_date"]
    ).dt.total_seconds() / 86_400
    mart["is_late"] = mart["delay_days"].gt(0).where(mart["delay_days"].notna())
    mart["bad_review"] = mart["review_score"].le(2).where(mart["review_score"].notna())

    return mart.loc[mart["order_status"].eq("delivered")].copy()


def export_executive_kpis(delivered: pd.DataFrame) -> None:
    orders_per_customer = delivered.groupby("customer_unique_id")["order_id"].nunique()

    kpis = pd.DataFrame(
        {
            "metric": [
                "Доставленные заказы",
                "Уникальные клиенты",
                "GMV с учетом доставки",
                "Средний чек",
                "Доля повторных клиентов",
                "Средняя оценка",
                "Доля опозданий",
            ],
            "value": [
                delivered["order_id"].nunique(),
                delivered["customer_unique_id"].nunique(),
                delivered["gmv"].sum(),
                delivered["gmv"].sum() / delivered["order_id"].nunique(),
                orders_per_customer.gt(1).mean(),
                delivered["review_score"].mean(),
                delivered["is_late"].mean(),
            ],
            "format": ["integer", "integer", "currency", "currency", "percent", "decimal", "percent"],
        }
    )
    kpis.to_csv(OUTPUT_DIR / "executive_kpis.csv", index=False)


def export_monthly_sales(delivered: pd.DataFrame) -> None:
    monthly_sales = (
        delivered.groupby("purchase_month", as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            customers=("customer_unique_id", "nunique"),
            gmv=("gmv", "sum"),
        )
        .sort_values("purchase_month")
    )
    monthly_sales["aov"] = monthly_sales["gmv"] / monthly_sales["orders"]
    monthly_sales.to_csv(OUTPUT_DIR / "monthly_sales.csv", index=False)


def export_categories(delivered: pd.DataFrame) -> None:
    categories = (
        delivered.dropna(subset=["product_category_name_english"])
        .groupby("product_category_name_english", as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            customers=("customer_unique_id", "nunique"),
            gmv=("gmv", "sum"),
            average_review=("review_score", "mean"),
            late_share=("is_late", "mean"),
            bad_review_share=("bad_review", "mean"),
        )
        .sort_values("gmv", ascending=False)
    )
    categories.to_csv(OUTPUT_DIR / "category_performance.csv", index=False)


def export_delivery(delivered: pd.DataFrame) -> None:
    delivery = (
        delivered.dropna(subset=["delay_days", "review_score", "customer_state"])
        .groupby(["customer_state", "is_late"], as_index=False)
        .agg(
            orders=("order_id", "nunique"),
            average_delivery_days=("delivery_days", "mean"),
            average_delay_days=("delay_days", "mean"),
            average_review=("review_score", "mean"),
            bad_review_share=("bad_review", "mean"),
        )
    )
    delivery["delivery_status"] = delivery["is_late"].map(
        {False: "Вовремя", True: "С опозданием"}
    )
    delivery.to_csv(OUTPUT_DIR / "delivery_quality.csv", index=False)


def export_retention(delivered: pd.DataFrame) -> None:
    cohort = (
        delivered[["customer_unique_id", "order_id", "purchase_month"]]
        .dropna()
        .drop_duplicates()
    )
    first_orders = (
        cohort.groupby("customer_unique_id", as_index=False)["purchase_month"]
        .min()
        .rename(columns={"purchase_month": "cohort_month"})
    )
    cohort = cohort.merge(first_orders, on="customer_unique_id", how="left")
    cohort["cohort_index"] = (
        (cohort["purchase_month"].dt.year - cohort["cohort_month"].dt.year) * 12
        + cohort["purchase_month"].dt.month
        - cohort["cohort_month"].dt.month
    )

    cohort_counts = (
        cohort.groupby(["cohort_month", "cohort_index"], as_index=False)
        .agg(active_customers=("customer_unique_id", "nunique"))
    )
    cohort_sizes = (
        cohort_counts.loc[cohort_counts["cohort_index"].eq(0), ["cohort_month", "active_customers"]]
        .rename(columns={"active_customers": "cohort_size"})
    )
    retention = cohort_counts.merge(cohort_sizes, on="cohort_month", how="left")
    retention["retention"] = retention["active_customers"] / retention["cohort_size"]
    retention.to_csv(OUTPUT_DIR / "cohort_retention.csv", index=False)


def export_rfm(delivered: pd.DataFrame) -> None:
    snapshot_date = delivered["order_purchase_timestamp"].max() + pd.Timedelta(days=1)
    rfm = (
        delivered.groupby("customer_unique_id")
        .agg(
            recency=("order_purchase_timestamp", lambda x: (snapshot_date - x.max()).days),
            frequency=("order_id", "nunique"),
            monetary=("gmv", "sum"),
        )
        .reset_index()
    )

    rfm["R"] = pd.qcut(
        rfm["recency"].rank(method="first"),
        5,
        labels=[5, 4, 3, 2, 1],
    ).astype(int)
    rfm["F"] = pd.cut(
        rfm["frequency"],
        bins=[0, 1, 2, 3, 4, np.inf],
        labels=[1, 2, 3, 4, 5],
    ).astype(int)
    rfm["M"] = pd.qcut(
        rfm["monetary"].rank(method="first"),
        5,
        labels=[1, 2, 3, 4, 5],
    ).astype(int)
    rfm["segment"] = np.select(
        [
            (rfm["R"] >= 4) & (rfm["F"] >= 2) & (rfm["M"] >= 4),
            (rfm["R"] >= 4) & (rfm["F"] == 1),
            (rfm["R"] <= 2) & (rfm["F"] >= 2),
            rfm["R"] <= 2,
        ],
        ["Чемпионы", "Новые клиенты", "Под риском", "Неактивные"],
        default="Обычные",
    )

    segments = (
        rfm.groupby("segment", as_index=False)
        .agg(
            customers=("customer_unique_id", "nunique"),
            average_recency=("recency", "mean"),
            average_frequency=("frequency", "mean"),
            average_monetary=("monetary", "mean"),
        )
        .sort_values("customers", ascending=False)
    )
    segments.to_csv(OUTPUT_DIR / "rfm_segments.csv", index=False)


def main() -> None:
    data = load_data()
    delivered = build_order_mart(data)

    export_executive_kpis(delivered)
    export_monthly_sales(delivered)
    export_categories(delivered)
    export_delivery(delivered)
    export_retention(delivered)
    export_rfm(delivered)

    print(f"Витрины DataLens сохранены в {OUTPUT_DIR}")
    for path in sorted(OUTPUT_DIR.glob("*.csv")):
        print(f"- {path.name}: {path.stat().st_size / 1024:.1f} КБ")


if __name__ == "__main__":
    main()
