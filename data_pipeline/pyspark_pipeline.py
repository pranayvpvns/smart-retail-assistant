import os
import sys
import tempfile
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    trim,
    to_date,
    when,
    month,
    dayofweek,
)

CURRENT_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

PROJECT_ROOT = os.path.dirname(
    CURRENT_DIR
)

BACKEND_DIR = os.path.join(
    PROJECT_ROOT,
    "backend"
)

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

from app.config import get_settings
from app.services.blob_service import (
    blob_service_client,
    RAW_CONTAINER,
    STAGED_CONTAINER,
    CURATED_CONTAINER,
)

# ─────────────────────────────────────────────
# Spark Session
# ─────────────────────────────────────────────

spark = (
    SparkSession.builder
    .appName("SmartRetailETL")
    .config(
        "spark.jars.packages",
        "io.delta:delta-core_2.12:2.4.0"
    )
    .getOrCreate()
)

settings = get_settings()

# ─────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────

def get_blob_url(container, blob_name):

    account_name = (
        blob_service_client.account_name
    )

    return (
        f"wasbs://{container}@"
        f"{account_name}.blob.core.windows.net/"
        f"{blob_name}"
    )


# ─────────────────────────────────────────────
# Read RAW CSV from Azure Blob
# ─────────────────────────────────────────────

def read_raw_csv(blob_name: str):

    blob_client = (
        blob_service_client
        .get_blob_client(
            container=RAW_CONTAINER,
            blob=blob_name,
        )
    )

    # Windows-safe temp directory
    temp_dir = tempfile.gettempdir()

    download_path = os.path.join(
        temp_dir,
        os.path.basename(blob_name)
    )

    with open(download_path, "wb") as f:

        f.write(
            blob_client.download_blob().readall()
        )

    df = spark.read.csv(
        download_path,
        header=True,
        inferSchema=True,
    )

    return df


# ─────────────────────────────────────────────
# Cleaning Layer
# ─────────────────────────────────────────────

def clean_dataframe(df):

    # Clean string columns
    string_cols = [
        "product_id",
        "product_name",
        "store_id",
        "category",
    ]

    for column in string_cols:

        if column in df.columns:

            df = df.withColumn(
                column,
                trim(col(column))
            )

    # Parse dates
    df = df.withColumn(
        "date",
        to_date(
            col("date"),
            "yyyy-MM-dd"
        )
    )

    # Remove invalid dates
    df = df.filter(
        col("date").isNotNull()
    )

    # Numeric casting
    numeric_cols = [
        "quantity_sold",
        "revenue",
        "cost",
        "stock_level",
    ]

    for column in numeric_cols:

        if column in df.columns:

            df = df.withColumn(
                column,
                col(column).cast("double")
            )

    # Remove critical nulls
    df = df.dropna(
        subset=[
            "date",
            "product_id",
            "product_name",
        ]
    )

    return df


# ─────────────────────────────────────────────
# Feature Engineering Layer
# ─────────────────────────────────────────────

def add_features(df):

    # Weekend feature
    df = df.withColumn(
        "is_weekend",
        when(
            dayofweek(col("date")).isin([1, 7]),
            1
        ).otherwise(0)
    )

    # Holiday feature
    df = df.withColumn(
        "is_holiday",
        when(
            col("date").cast("string").isin([
                "2026-01-01",
                "2026-10-24",
                "2026-12-25",
            ]),
            1
        ).otherwise(0)
    )

    # Seasonal feature
    df = df.withColumn(
        "season_encoded",
        when(month(col("date")).isin([12,1,2]), 0)
        .when(month(col("date")).isin([3,4,5,6]), 1)
        .when(month(col("date")).isin([7,8,9]), 2)
        .otherwise(3)
    )

    return df


# ─────────────────────────────────────────────
# Upload Parquet to Blob
# ─────────────────────────────────────────────

def upload_parquet(
    df,
    container,
    store_id,
    layer_name,
):

    timestamp = datetime.utcnow().strftime(
        "%Y%m%d_%H%M%S"
    )

    # Windows-safe temp directory
    temp_dir = tempfile.gettempdir()

    local_output = os.path.join(
        temp_dir,
        f"{layer_name}_{timestamp}"
    )

    df.write.mode("overwrite").parquet(
        local_output
    )

    uploaded_files = []

    for root, _, files in os.walk(local_output):

        for file in files:

            if file.endswith(".parquet"):

                local_file = os.path.join(
                    root,
                    file
                )

                blob_name = (
                    f"{store_id}/"
                    f"{layer_name}/"
                    f"{timestamp}/"
                    f"{file}"
                )

                blob_client = (
                    blob_service_client
                    .get_blob_client(
                        container=container,
                        blob=blob_name,
                    )
                )

                with open(local_file, "rb") as data:

                    blob_client.upload_blob(
                        data,
                        overwrite=True,
                    )

                uploaded_files.append(
                    blob_name
                )

    return uploaded_files


# ─────────────────────────────────────────────
# Main ETL Pipeline
# ─────────────────────────────────────────────

def run_pipeline(
    blob_name: str,
    store_id: str,
):

    print("\n🚀 Starting PySpark ETL Pipeline")

    # ─────────────────────────────────────
    # RAW → Spark
    # ─────────────────────────────────────

    raw_df = read_raw_csv(blob_name)

    print(
        f"📦 RAW rows: "
        f"{raw_df.count()}"
    )

    # ─────────────────────────────────────
    # CLEANING
    # ─────────────────────────────────────

    cleaned_df = clean_dataframe(
        raw_df
    )

    print(
        f"🧹 Cleaned rows: "
        f"{cleaned_df.count()}"
    )

    # ─────────────────────────────────────
    # STAGED PARQUET
    # ─────────────────────────────────────

    staged_files = upload_parquet(
        df=cleaned_df,
        container=STAGED_CONTAINER,
        store_id=store_id,
        layer_name="staged",
    )

    print(
        f"✅ STAGED parquet uploaded"
    )

    # ─────────────────────────────────────
    # FEATURE ENGINEERING
    # ─────────────────────────────────────

    curated_df = add_features(
        cleaned_df
    )

    print(
        f"🧠 Curated rows: "
        f"{curated_df.count()}"
    )

    # ─────────────────────────────────────
    # CURATED PARQUET
    # ─────────────────────────────────────

    curated_files = upload_parquet(
        df=curated_df,
        container=CURATED_CONTAINER,
        store_id=store_id,
        layer_name="curated",
    )

    print(
        f"✅ CURATED parquet uploaded"
    )

    return {

        "success": True,

        "raw_blob": blob_name,

        "staged_files": staged_files,

        "curated_files": curated_files,

        "records_processed": curated_df.count(),
    }


# ─────────────────────────────────────────────
# CLI Runner
# ─────────────────────────────────────────────

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--blob-name",
        required=True,
    )

    parser.add_argument(
        "--store-id",
        required=True,
    )

    args = parser.parse_args()

    result = run_pipeline(
        blob_name=args.blob_name,
        store_id=args.store_id,
    )

    print(result)