import uuid
import tempfile
from pathlib import Path

from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

from app.config import get_settings


settings = get_settings()

# ─────────────────────────────────────────────
# Blob Client Initialization
# ─────────────────────────────────────────────

blob_service_client = BlobServiceClient.from_connection_string(
    settings.azure_storage_connection_string
)

RAW_CONTAINER = settings.azure_storage_container_raw
STAGED_CONTAINER = settings.azure_storage_container_staged
CURATED_CONTAINER = settings.azure_storage_container_curated


# ─────────────────────────────────────────────
# Ensure Containers Exist
# ─────────────────────────────────────────────

def ensure_containers_exist():

    for container_name in [
        RAW_CONTAINER,
        STAGED_CONTAINER,
        CURATED_CONTAINER,
    ]:

        try:
            blob_service_client.create_container(container_name)

        except ResourceExistsError:
            pass


ensure_containers_exist()


# ─────────────────────────────────────────────
# Generate Unique Blob Name
# ─────────────────────────────────────────────

def generate_blob_name(
    store_id: str,
    original_filename: str
) -> str:

    extension = Path(original_filename).suffix

    unique_id = uuid.uuid4().hex

    return f"{store_id}/{unique_id}{extension}"


# ─────────────────────────────────────────────
# Upload Bytes to Blob Storage
# ─────────────────────────────────────────────

def upload_bytes_to_blob(
    file_bytes: bytes,
    original_filename: str,
    store_id: str,
    container: str = RAW_CONTAINER,
) -> dict:

    blob_name = generate_blob_name(
        store_id=store_id,
        original_filename=original_filename,
    )

    blob_client = blob_service_client.get_blob_client(
        container=container,
        blob=blob_name,
    )

    blob_client.upload_blob(
        file_bytes,
        overwrite=True,
    )

    return {
        "container": container,
        "blob_name": blob_name,
        "blob_url": blob_client.url,
    }


def upload_to_specific_blob(
    file_path: str,
    blob_url: str,
) -> bool:
    """
    Overwrites a specific blob identified by its full URL.
    Used for updating datasets after order injection.
    """
    try:
        # 1. Strip query params (e.g. SAS tokens) from the URL
        clean_url = blob_url.split("?")[0]
        
        # 2. Extract container and blob name
        parts = clean_url.split("/")
        if len(parts) < 5:
            raise ValueError(f"Invalid Blob URL: {blob_url}")
            
        container_name = parts[3]
        blob_name = "/".join(parts[4:])

        print(f"☁️ Cloud Overwrite: container='{container_name}', blob='{blob_name}'")

        blob_client = blob_service_client.get_blob_client(
            container=container_name,
            blob=blob_name,
        )

        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)

        print(f"✅ Cloud overwrite successful for {blob_name}")
        return True

    except Exception as e:
        print(f"❌ Blob overwrite failed: {e}")
        return False


# ─────────────────────────────────────────────
# Download Blob Temporarily
# ─────────────────────────────────────────────

def download_blob_temp(
    blob_name: str,
    container: str = RAW_CONTAINER,
) -> str:

    blob_client = blob_service_client.get_blob_client(
        container=container,
        blob=blob_name,
    )

    blob_data = blob_client.download_blob().readall()

    suffix = Path(blob_name).suffix

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
    ) as temp_file:

        temp_file.write(blob_data)

        return temp_file.name


# ─────────────────────────────────────────────
# Delete Blob
# ─────────────────────────────────────────────

def delete_blob(
    blob_name: str,
    container: str = RAW_CONTAINER,
):

    blob_client = blob_service_client.get_blob_client(
        container=container,
        blob=blob_name,
    )

    blob_client.delete_blob()


# ─────────────────────────────────────────────
# Upload DataFrame as Parquet
# ─────────────────────────────────────────────

def upload_dataframe_parquet(
    df,
    filename: str,
    store_id: str,
    container: str = STAGED_CONTAINER,
) -> dict:

    import io

    parquet_buffer = io.BytesIO()

    df.to_parquet(
        parquet_buffer,
        index=False,
        engine="pyarrow",
    )

    parquet_buffer.seek(0)

    blob_name = generate_blob_name(
        store_id=store_id,
        original_filename=filename.replace(".csv", ".parquet"),
    )

    blob_client = blob_service_client.get_blob_client(
        container=container,
        blob=blob_name,
    )

    blob_client.upload_blob(
        parquet_buffer.getvalue(),
        overwrite=True,
    )

    return {
        "container": container,
        "blob_name": blob_name,
        "blob_url": blob_client.url,
    }