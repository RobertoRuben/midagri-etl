from system.core.env import SETTINGS
from system.core.logging import LOGGER
from system.database.repository import get_connection, fetch_catalog_products, fetch_ubigeo, merge_prices
from system.network.downloader import fetch_prices, fetch_prices_mayorista  # importa ambos
from system.utils.merge import prepare_for_merge
import sys
import datetime


def main():
    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=5)

    # dd/mm/YYYY
    fecha = ayer.strftime("%d/%m/%Y")
    desde = ayer.strftime("%d/%m/%Y")
    hasta = hoy.strftime("%d/%m/%Y")

    with get_connection() as conn:
        cats = fetch_catalog_products(conn)
        ubis = fetch_ubigeo(conn)

        codes = cats["code"].dropna().astype(str).str.zfill(6).tolist()
        LOGGER.info(f"Total de códigos a consultar (por lotes): {len(codes)}")

        # 🔀 Selector dinámico según entorno
        mode = getattr(SETTINGS, "sisap_mode", "ciudades").lower()
        LOGGER.info(f"Modo SISAP activo: {mode}")

        if mode == "mayorista":
            prices = fetch_prices_mayorista(
                codes,
                fecha,
                desde,
                hasta,
                batch_size=SETTINGS.batch_size or 40,
                periodicidad=SETTINGS.periodicidad or "intervalo",
            )
        else:
            prices = fetch_prices(
                codes,
                fecha,
                desde,
                hasta,
                batch_size=SETTINGS.batch_size or 40,
                periodicidad=SETTINGS.periodicidad or "intervalo",
            )

        LOGGER.info(f"Filas descargadas: {len(prices)}")
        if prices.empty:
            LOGGER.warning("No se descargaron filas; fin.")
            sys.exit(0)

        # MERGE local
        merge_ready = prepare_for_merge(prices, cats, ubis)
        LOGGER.info(f"Filas listas para MERGE (con IDs): {len(merge_ready)}")
        if merge_ready.empty:
            LOGGER.warning("Nada que mergear (sin IDs).")
            sys.exit(0)

        merge_prices(conn, merge_ready, price_type=SETTINGS.price_type, registered_by="etl-sisap")


if __name__ == "__main__":
    main()
