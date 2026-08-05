# Данные

Проект использует открытый [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

Исходные CSV намеренно не публикуются отдельными файлами в GitHub:

- это делает репозиторий компактнее;
- исключает дублирование открытого источника;
- сохраняет воспроизводимость через упакованный Tableau workbook `.twbx`.

## Использованные таблицы

| Таблица | Назначение |
|---|---|
| `olist_orders_dataset.csv` | заказ, клиент, статус и даты |
| `olist_order_items_dataset.csv` | товарные позиции, цена и доставка |
| `olist_customers_dataset.csv` | уникальный клиент и штат |
| `olist_products_dataset.csv` | товар и категория |
| `product_category_name_translation.csv` | английские названия категорий |
| `olist_order_reviews_dataset.csv` | оценка и текст отзыва |

## Grain

- `orders`: одна строка на заказ;
- `order_items`: одна строка на товарную позицию заказа;
- `customers`: одна строка на `customer_id`;
- `reviews`: одна строка на отзыв.

Из-за разного grain таблицы соединены через Tableau Relationships, а не одним физическим JOIN.
