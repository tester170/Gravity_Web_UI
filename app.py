"""Веб-интерфейс для расчёта гравитационного влияния рельефа через API."""

import json  # Преобразование результата в текст GeoJSON.
from pathlib import Path  # Путь к демонстрационному файлу.

import pandas as pd  # Чтение CSV и работа с таблицами.
import requests  # Отправка HTTP-запросов к API.
import streamlit as st  # Элементы веб-интерфейса.
import streamlit.components.v1 as components  # Показ готовой HTML-карты.


DEMO_FILE = Path(__file__).parent / "data" / "terrain_demo.csv"  # Пример для первого запуска.
DEFAULT_SERVER = "https://gravity-api-server-9b82fcce.fastapicloud.dev"  # Адрес развернутого API.
REQUIRED_COLUMNS = [  # Координаты и признаки, которые принимает сервер.
    "latitude", "longitude", "elevation_m", "slope", "curvature",
    "tpi_7", "tpi_31", "tpi_121", "roughness_7", "roughness_31", "relief_31",
]


def clear_result():
    """Убрать прежний расчёт при смене файла или сервера."""
    st.session_state.pop("result", None)  # Отсутствие прежнего результата не вызывает ошибку.


def request_result(url, rows, output):
    """Передать подготовленные признаки серверу и получить ответ."""
    response = requests.post(url, params={"output": output}, json=rows, timeout=120)  # Передаём строки в JSON.
    if not response.ok:  # Обрабатываем неуспешный ответ API.
        try:  # FastAPI обычно возвращает пояснение ошибки в поле detail.
            message = response.json().get("detail", response.text)
        except ValueError:  # Прокси или другой сервер может ответить обычным текстом.
            message = response.text
        raise ValueError(f"Ошибка сервера ({response.status_code}): {message}")
    return response.text if output == "html" else response.json()  # Разбираем выбранный формат ответа.


def result_to_geojson(data):
    """Представить строки расчёта как географические точки GeoJSON."""
    features = []  # Каждая строка результата станет отдельной точкой.
    for row in data.to_dict(orient="records"):  # Получаем значения строки по именам столбцов.
        features.append({  # В GeoJSON координаты записываются в порядке «долгота, широта».
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["longitude"], row["latitude"]]},
            "properties": {key: value for key, value in row.items() if key not in ("latitude", "longitude")},
        })
    return json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False)  # Готовый файл.


st.set_page_config(page_title="Гравитационное влияние рельефа", layout="wide")  # Широкая область для карты.
st.title("🏔️ Гравитационное влияние рельефа")  # Заголовок приложения.
st.write(  # Кратко поясняем назначение приложения.
    "Загрузите CSV с координатами и подготовленными признаками рельефа. "
    "Веб-интерфейс передаст их в API: модель и расчёт выполняются на сервере."
)

st.sidebar.header("⚙️ Параметры")  # Все элементы управления размещаем слева.
server = st.sidebar.text_input("Адрес сервера API", DEFAULT_SERVER, on_change=clear_result).strip().rstrip("/")
uploaded = st.sidebar.file_uploader("📂 CSV с признаками рельефа", type="csv", on_change=clear_result)
if uploaded is None:  # При отсутствии своего файла используем пример.
    st.sidebar.caption("Используется демонстрационный файл terrain_demo.csv.")

try:  # Читаем выбранный CSV или демонстрационные данные.
    # Без загруженного файла показываем данные, включённые в проект.
    data = pd.read_csv(uploaded if uploaded is not None else DEMO_FILE)
except (OSError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
    st.error(f"Не удалось прочитать CSV: {error}")
    st.stop()  # Останавливаем построение страницы, если файл не удалось прочитать.

missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]  # Ищем недостающие поля.
if data.empty or missing:  # Неполную таблицу не отправляем в API.
    st.error(f"Нужна непустая таблица. Отсутствующие столбцы: {missing}")
    st.stop()  # Продолжим после выбора подходящего файла.

st.sidebar.caption(f"Точек: {len(data)} · столбцов: {len(data.columns)}")  # Объём выбранных данных.
with st.expander("📋 Исходные данные — первые 10 строк"):  # Предпросмотр раскрывается по нажатию.
    st.dataframe(data.head(10), hide_index=True, width="stretch")

if st.sidebar.button("🚀 Рассчитать", type="primary", width="stretch", disabled=not server):
    clear_result()  # Убираем прежний результат перед новой попыткой расчёта.
    try:
        # Отправляем только те поля, которые ожидает API.
        rows = data[REQUIRED_COLUMNS].to_dict(orient="records")
        url = f"{server}/predict"  # Адрес метода расчёта выбранного сервера.
        with st.spinner("Сервер выполняет расчёт и строит карту..."):
            # Один запрос возвращает таблицу, второй — готовую HTML-карту.
            result = pd.DataFrame(request_result(url, rows, "json"))
            map_html = request_result(url, rows, "html")
        # Streamlit перерисовывает страницу после нажатий; храним результат в сеансе.
        st.session_state["result"] = (result, map_html)
    except (requests.RequestException, ValueError) as error:
        st.error(f"Не удалось получить результат: {error}")

if "result" in st.session_state:  # Показываем результат только после успешного ответа API.
    result, map_html = st.session_state["result"]  # Получаем сохранённые таблицу и карту.
    st.subheader("🗺️ Карта расчётного поля")
    st.caption(f"Обработано точек: {len(result)}. Значения гравитационного влияния рельефа — в мГал.")
    components.html(map_html, height=740)  # Встраиваем HTML, полученный от API.

    csv_column, geojson_column, map_column = st.columns(3)  # Три равные колонки для скачивания.
    csv_column.download_button(
        "📄 Скачать CSV", result.to_csv(index=False).encode("utf-8-sig"),
        file_name="terrain_predictions.csv", mime="text/csv", type="primary", width="stretch",
    )
    geojson_column.download_button(
        "📍 Скачать GeoJSON", result_to_geojson(result),
        file_name="terrain_predictions.geojson", mime="application/geo+json", type="primary", width="stretch",
    )
    map_column.download_button(
        "🗺️ Скачать HTML", map_html,
        file_name="terrain_map.html", mime="text/html", type="primary", width="stretch",
    )

    st.subheader("📊 Таблица результатов")  # Показываем полную таблицу сразу после расчёта.
    st.dataframe(result, hide_index=True, width="stretch", height=300)
