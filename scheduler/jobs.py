# scheduler/jobs.py
# Registro de todos los jobs del scheduler

from datetime import datetime, timedelta

from pipelines.treasury_pipeline import TreasuryPipeline
from pipelines.nfci_pipeline import NFCIPipeline
from pipelines.repo_pipeline import RepoPipeline
from pipelines.indices_pipeline import IndicesPipeline
from pipelines.ecb_pipeline import ECBPipeline
from pipelines.fed_balance_pipeline import FedBalancePipeline
from pipelines.cot_pipeline import COTPipeline
from pipelines.commodity_price_pipeline import CommodityPricePipeline
from pipelines.liquidity_pipeline import LiquidityPipeline
from pipelines.signals_pipeline import SignalsPipeline
from pipelines.funding_pipeline import FundingPipeline
from pipelines.ofr_repo_pipeline import OFRRepoPipeline
from pipelines.ofr_rates_pipeline import OFRRatesPipeline
from pipelines.ofr_dealer_pipeline import OFRDealerPipeline
from pipelines.ofr_sponsored_pipeline import OFRSponsoredPipeline
from utils.logger import get_logger

logger = get_logger("scheduler")

# Orden en que se comprueban/ejecutan los pipelines en el catch-up de arranque.
# Los más críticos o ligeros van primero.
ALL_PIPELINES = [
    TreasuryPipeline,
    NFCIPipeline,
    RepoPipeline,
    IndicesPipeline,
    ECBPipeline,
    FedBalancePipeline,
    COTPipeline,
    CommodityPricePipeline,
    LiquidityPipeline,
    SignalsPipeline,
    FundingPipeline,
    OFRRepoPipeline,
    OFRRatesPipeline,
    OFRDealerPipeline,
    OFRSponsoredPipeline,
]


def run_pipeline_safe(pipeline_class):
    """
    Wrapper que instancia y ejecuta un pipeline con manejo de errores.
    Comprueba frescura antes de ejecutar: si los datos están vigentes, omite la descarga.
    """
    try:
        pipeline = pipeline_class()
        if pipeline.is_fresh():
            logger.info(f"[{pipeline.name}] Datos vigentes (dentro de {pipeline.min_interval_hours:.0f}h). Omitiendo ejecución.")
            return
        logger.info(f"[{pipeline.name}] Iniciando descarga...")
        pipeline.run()
    except Exception as e:
        logger.error(f"Error ejecutando {pipeline_class.__name__}: {e}")


def schedule_startup_catchup(scheduler):
    """
    Al arrancar la aplicación, comprueba qué pipelines tienen datos desactualizados
    y programa ejecuciones one-shot escalonadas para ponerlos al día.

    Los pipelines se ejecutan de uno en uno con un margen de tiempo entre ellos
    para no saturar las APIs ni la base de datos.
    """
    FIRST_DELAY_MINUTES = 2   # El primer pipeline desactualizado arranca a los 2 min
    STEP_MINUTES = 8          # Cada pipeline adicional espera 8 min más

    scheduled = 0
    for pipeline_class in ALL_PIPELINES:
        try:
            pipeline = pipeline_class()
            if not pipeline.is_fresh():
                run_at = datetime.now() + timedelta(
                    minutes=FIRST_DELAY_MINUTES + scheduled * STEP_MINUTES
                )
                scheduler.add_job(
                    run_pipeline_safe,
                    trigger='date',
                    run_date=run_at,
                    args=[pipeline_class],
                    id=f'catchup_{pipeline.name}',
                    replace_existing=True
                )
                logger.info(
                    f"[{pipeline.name}] Desactualizado. Catch-up programado a las {run_at.strftime('%H:%M:%S')}"
                )
                scheduled += 1
            else:
                logger.info(f"[{pipeline.name}] Al día. No necesita catch-up.")
        except Exception as e:
            logger.warning(f"Error comprobando {pipeline_class.__name__}: {e}")

    if scheduled == 0:
        logger.info("Todos los pipelines están al día. No se necesita catch-up.")
    else:
        total_minutes = FIRST_DELAY_MINUTES + (scheduled - 1) * STEP_MINUTES
        logger.info(
            f"{scheduled} pipeline(s) desactualizados. "
            f"Catch-up escalonado completado en ~{total_minutes} min."
        )


def register_jobs(scheduler):
    """
    Registra todos los pipelines como jobs cron recurrentes.
    Añadir nuevos jobs aquí cuando se creen nuevos pipelines.
    """

    # Treasury: diariamente a las 8:00
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[TreasuryPipeline],
        hour=8, minute=0,
        id='treasury_daily',
        replace_existing=True
    )

    # NFCI: viernes a las 12:00 (publicación semanal)
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[NFCIPipeline],
        day_of_week='fri', hour=12, minute=0,
        id='nfci_weekly',
        replace_existing=True
    )

    # Repo: diariamente a las 10:00
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[RepoPipeline],
        hour=10, minute=0,
        id='repo_daily',
        replace_existing=True
    )

    # Índices globales (S&P 500, Bitcoin): cada 6h desde Yahoo Finance.
    # Datos diarios; el intervalo corto capta el cierre en cuanto se publica.
    scheduler.add_job(
        run_pipeline_safe,
        trigger='interval',
        args=[IndicesPipeline],
        hours=6,
        id='indices_interval',
        replace_existing=True
    )

    # BCE: día 5 de cada mes a las 8:00 (datos MMSR son mensuales)
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[ECBPipeline],
        day=5, hour=8, minute=0,
        id='ecb_monthly',
        replace_existing=True
    )

    # Fed Balance: jueves a las 20:00 (H.4.1 se publica ~17:00-18:00 ET)
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[FedBalancePipeline],
        day_of_week='thu', hour=20, minute=0,
        id='fed_balance_weekly',
        replace_existing=True
    )

    # COT: viernes a las 22:00 (~15:30 ET = ~21:30 Madrid)
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[COTPipeline],
        day_of_week='fri', hour=22, minute=0,
        id='cot_weekly',
        replace_existing=True
    )

    # Precios commodities: lunes a las 8:30
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[CommodityPricePipeline],
        day_of_week='mon', hour=8, minute=30,
        id='commodity_prices_weekly',
        replace_existing=True
    )

    # Liquidez neta (WALCL, TGA, RRP): diaria a las 21:00.
    # RRP es diaria; WALCL/TGA semanales (jueves H.4.1). Refresco diario capta ambas.
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[LiquidityPipeline],
        hour=21, minute=0,
        id='liquidity_daily',
        replace_existing=True
    )

    # Señales de mercado (HY OAS, curva, VIX): diaria a las 21:15.
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[SignalsPipeline],
        hour=21, minute=15,
        id='signals_daily',
        replace_existing=True
    )

    # Financiación (SOFR, EFFR, IORB): diaria a las 21:20.
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[FundingPipeline],
        hour=21, minute=20,
        id='funding_daily',
        replace_existing=True
    )

    # OFR — U.S. Repo Markets Data Release (DVP/GCF/tri-party): diaria a las 22:30.
    # El release preliminar sale a las 15:00 ET; a las 22:30 Madrid ya está publicado.
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[OFRRepoPipeline],
        hour=22, minute=30,
        id='ofr_repo_daily',
        replace_existing=True
    )

    # OFR — tasas de referencia NY Fed (FNYR: SOFR/BGCR/TGCR + percentiles): diaria 22:40.
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[OFRRatesPipeline],
        hour=22, minute=40,
        id='ofr_rates_daily',
        replace_existing=True
    )

    # OFR — financiación repo de primary dealers (FR2004/NYPD): semanal, jueves 22:50.
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[OFRDealerPipeline],
        day_of_week='thu', hour=22, minute=50,
        id='ofr_dealer_weekly',
        replace_existing=True
    )

    # OFR Hedge Fund Monitor — repo patrocinado (FICC Sponsored): semanal, viernes 23:00.
    scheduler.add_job(
        run_pipeline_safe,
        trigger='cron',
        args=[OFRSponsoredPipeline],
        day_of_week='fri', hour=23, minute=0,
        id='ofr_sponsored_weekly',
        replace_existing=True
    )

    logger.info(f"Registrados {len(scheduler.get_jobs())} jobs.")
